import os
import uuid
import asyncio
from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.database import init_db, get_db, SessionLocal, JobModel, SpecAnalysisModel
from backend.config_manager import ConfigManager
from backend.websocket import manager, broadcast_log, broadcast_input_required, pending_inputs, start_heartbeat
from tools.ticket_manager import TicketManager

app = FastAPI(title="Spec-Driven Dev Agent API")

# Enable CORS for Next.js frontend connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global supervisor singleton — persists chat history across requests
_supervisor = None

def get_supervisor():
    global _supervisor
    if _supervisor is None:
        from agents.main_agent import SupervisorAgent
        _supervisor = SupervisorAgent()
    return _supervisor

@app.on_event("startup")
async def startup_event():
    print("[FastAPI] Starting up server...")
    try:
        init_db()
        print("[FastAPI] Database initialized successfully.")
    except Exception as e:
        print(f"[FastAPI] WARNING: Could not initialize database: {e}")
        print("Please check your DATABASE_URL configuration.")
    
    # Pre-initialize MCPManager so the first API request is not slow
    try:
        from tools.mcp_loader import MCPManager
        print("[FastAPI] Pre-initializing MCP connections...")
        await MCPManager.get_instance()
        print("[FastAPI] MCP connections ready.")
    except Exception as e:
        print(f"[FastAPI] WARNING: MCP pre-initialization failed: {e}")

# WebSocket for streaming logs
@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# 1. Config Routes
@app.get("/api/config")
def get_config():
    try:
        return ConfigManager.get_all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/config")
def update_config(configs: dict):
    try:
        for k, v in configs.items():
            ConfigManager.set(k, v)
        return {"status": "success", "message": "Configuration updated."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. Spec Routes
@app.post("/api/spec")
async def upload_spec(
    source_type: str = Form(...),  # "text", "pdf", "url"
    content: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    try:
        job_id = str(uuid.uuid4())
        await broadcast_log(f"Received spec upload of type: {source_type}", job_id)
        
        # Read the specification content
        raw_text = ""
        source_path = ""
        
        if source_type == "text":
            raw_text = content or ""
            source_path = "raw_input.txt"
        elif source_type == "url":
            raw_text = content or ""
            source_path = raw_text
        elif source_type == "pdf" and file:
            # We will parse the file later in the background pipeline
            file_bytes = await file.read()
            # Temporary storage to local directory to process it
            os.makedirs("temp_specs", exist_ok=True)
            source_path = os.path.join("temp_specs", f"{job_id}_{file.filename}")
            with open(source_path, "wb") as f:
                f.write(file_bytes)
            raw_text = f"PDF file uploaded: {file.filename}"
        else:
            raise HTTPException(status_code=400, detail="Invalid request parameters.")

        # Create base database entry
        db_spec = SpecAnalysisModel(
            source_type=source_type,
            source_path=source_path,
            raw_content=raw_text,
            analyzed_stories=[]
        )
        db.add(db_spec)
        db.commit()
        db.refresh(db_spec)
        
        # Trigger parsing and story generation in background
        from agents.spec_analyzer_agent import SpecAnalyzerAgent
        analyzer = SpecAnalyzerAgent()
        
        # Run spec parsing and analysis as background task
        asyncio.create_task(
            run_spec_analysis_pipeline(db_spec.id, source_type, source_path, raw_text, job_id)
        )
        
        return {
            "status": "pending",
            "spec_id": db_spec.id,
            "job_id": job_id,
            "message": "Specification analysis started in the background."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def run_spec_analysis_pipeline(spec_id: int, source_type: str, source_path: str, raw_content: str, job_id: str):
    await broadcast_log(f"[Pipeline] Starting spec parsing for spec ID: {spec_id}...", job_id)
    db = SessionLocal()
    try:
        from tools.spec_parser import SpecParser
        parser = SpecParser()
        
        parsed_text = ""
        if source_type == "text":
            parsed_text = raw_content
        elif source_type == "url":
            parsed_text = await parser.parse_url(source_path)
        elif source_type == "pdf":
            parsed_text = parser.parse_pdf(source_path)
            
        await broadcast_log(f"[Pipeline] Finished parsing. Extracted {len(parsed_text)} characters. Running LLM analysis...", job_id)
        
        from agents.spec_analyzer_agent import SpecAnalyzerAgent
        analyzer = SpecAnalyzerAgent()
        stories = await analyzer.analyze_spec(parsed_text)
        
        # Save to database
        db_spec = db.query(SpecAnalysisModel).filter(SpecAnalysisModel.id == spec_id).first()
        if db_spec:
            db_spec.analyzed_stories = stories
            db.commit()
            
        await broadcast_log(f"[Pipeline] Spec analysis complete. Generated {len(stories)} structured stories.", job_id, "SUCCESS")
        
    except Exception as e:
        await broadcast_log(f"[Pipeline] Spec analysis failed: {e}", job_id, "ERROR")
    finally:
        db.close()

@app.get("/api/spec/{spec_id}")
def get_spec_details(spec_id: int, db: Session = Depends(get_db)):
    spec = db.query(SpecAnalysisModel).filter(SpecAnalysisModel.id == spec_id).first()
    if not spec:
        raise HTTPException(status_code=404, detail="Specification analysis not found.")
    return spec

# 3. Ticket Routes
@app.get("/api/tickets")
async def get_tickets(status: Optional[str] = None):
    try:
        ticket_manager = TicketManager()
        tickets = await ticket_manager.get_todo_tickets(status)
        return tickets
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tickets/create-batch")
async def create_tickets_batch(payload: dict, db: Session = Depends(get_db)):
    """
    Creates Jira tickets from reviewed stories.
    Payload: { "spec_id": 1, "stories": [...] }
    """
    try:
        stories = payload.get("stories", [])
        spec_id = payload.get("spec_id")
        job_id = str(uuid.uuid4())
        
        # Setup running Job in DB
        db_job = JobModel(id=job_id, status="RUNNING", tickets=[], logs="Job started.\n")
        db.add(db_job)
        db.commit()

        # Run Jira tickets creator in background
        asyncio.create_task(
            run_ticket_creation_pipeline(spec_id, stories, job_id)
        )

        return {
            "status": "running",
            "job_id": job_id,
            "message": "Jira ticket creation batch job started."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def run_ticket_creation_pipeline(spec_id: Optional[int], stories: list, job_id: str):
    await broadcast_log(f"[TicketCreator] Starting creation pipeline for {len(stories)} user stories...", job_id)
    db = SessionLocal()
    db_job = db.query(JobModel).filter(JobModel.id == job_id).first()
    heartbeat = await start_heartbeat(job_id)
    try:
        from agents.ticket_creator_agent import TicketCreatorAgent
        creator = TicketCreatorAgent()
        
        created_tickets = await creator.create_tickets(stories, job_id)
        
        if db_job:
            db_job.status = "SUCCESS"
            db_job.tickets = created_tickets
            db_job.logs += f"\nTickets created: {created_tickets}"
            db.commit()
            
        await broadcast_log(f"[TicketCreator] Successfully completed. Pushed {len(created_tickets)} tickets to Jira.", job_id, "SUCCESS")
        
    except Exception as e:
        if db_job:
            db_job.status = "FAILED"
            db_job.logs += f"\nError: {e}"
            db.commit()
        await broadcast_log(f"[TicketCreator] Batch ticket creation failed: {e}", job_id, "ERROR")
    finally:
        heartbeat.cancel()
        db.close()

# 4. Job Routes
@app.get("/api/jobs")
def get_jobs(db: Session = Depends(get_db)):
    try:
        return db.query(JobModel).order_by(JobModel.created_at.desc()).all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/jobs/{job_id}")
def get_job_details(job_id: str, db: Session = Depends(get_db)):
    job = db.query(JobModel).filter(JobModel.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job

@app.post("/api/jobs/input_response")
async def submit_input_response(payload: dict):
    """
    Receives user input (e.g. repo name) from the frontend when the agent
    is waiting for a response. Resolves the pending asyncio.Event.
    Payload: { "job_id": "...", "value": "owner/repo-name" }
    """
    job_id = payload.get("job_id", "")
    value = payload.get("value", "").strip()
    if not job_id or not value:
        raise HTTPException(status_code=400, detail="job_id and value are required.")
    
    entry = pending_inputs.get(job_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"No pending input request found for job {job_id}.")
    
    entry["value"] = value
    entry["event"].set()  # Wake up the waiting coroutine in environment_agent
    await broadcast_log(f"[Input] Received response for job {job_id}.", job_id, "SUCCESS")
    return {"status": "ok", "job_id": job_id, "received": value}

# 5b. Chat with the supervisor agent
@app.post("/api/chat/message")
async def chat_message(payload: dict):
    """
    Send a free-form message to the SupervisorAgent. The response is streamed
    back in real-time via the WebSocket as a 'chat_response' event.
    Payload: { "message": "implement PROJ-1" }
    """
    message = payload.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required.")

    job_id = str(uuid.uuid4())
    asyncio.create_task(_run_supervisor_chat(message, job_id))
    return {"status": "processing", "job_id": job_id}

async def _run_supervisor_chat(message: str, job_id: str):
    heartbeat = await start_heartbeat(job_id)
    try:
        supervisor = get_supervisor()
        response = await supervisor.process_chat(message, job_id)
        await manager.broadcast_json({
            "type": "chat_response",
            "job_id": job_id,
            "message": response,
        })
    except Exception as e:
        await manager.broadcast_json({
            "type": "chat_response",
            "job_id": job_id,
            "message": f"Error: {e}",
            "level": "ERROR",
        })
    finally:
        heartbeat.cancel()

# 5. Implementation Trigger Route
@app.post("/api/jobs/implement")
async def trigger_implementation(payload: dict, db: Session = Depends(get_db)):
    """
    Triggers multi-ticket implementation pipeline.
    Payload: { "ticket_ids": ["PROJ-1", "PROJ-2"] }
    """
    ticket_ids = payload.get("ticket_ids", [])
    if not ticket_ids:
        raise HTTPException(status_code=400, detail="No ticket IDs specified.")
        
    job_id = str(uuid.uuid4())
    db_job = JobModel(id=job_id, status="RUNNING", tickets=ticket_ids, logs=f"Starting implementation for {ticket_ids}...\n")
    db.add(db_job)
    db.commit()
    
    # Run implementation in the background
    asyncio.create_task(run_implementation_pipeline(ticket_ids, job_id))
    
    return {
        "status": "running",
        "job_id": job_id,
        "message": f"Implementation job {job_id} scheduled."
    }

# 6. DAG Build Route
@app.post("/api/dag/build")
async def build_dag(payload: dict):
    """
    Builds a dependency DAG for the given ticket IDs using Gemini LLM analysis.
    Payload: { "ticket_ids": ["PROJ-1", "PROJ-2"] }
    Returns: { "dag": { "PROJ-1": ["PROJ-2"], "PROJ-2": [] } }
    """
    ticket_ids = payload.get("ticket_ids", [])
    if not ticket_ids:
        raise HTTPException(status_code=400, detail="No ticket IDs specified.")
    try:
        from tools.dependency_analyzer import DependencyAnalyzer
        analyzer = DependencyAnalyzer()
        dag = await analyzer.build_dag(ticket_ids)
        return {"dag": dag}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def run_implementation_pipeline(ticket_ids: List[str], job_id: str):
    await broadcast_log(f"[Orchestrator] Starting implementation for tickets: {ticket_ids}", job_id)
    db = SessionLocal()
    db_job = db.query(JobModel).filter(JobModel.id == job_id).first()
    heartbeat = await start_heartbeat(job_id)
    try:
        from agents.multi_ticket_agent import MultiTicketOrchestrator
        orchestrator = MultiTicketOrchestrator()
        
        result = await orchestrator.execute_tickets(ticket_ids, job_id)
        
        if db_job:
            db_job.status = "SUCCESS" if result.get("status") == "success" else "FAILED"
            db_job.logs += f"\nResult: {result.get('message', '')}"
            db.commit()
            
        await broadcast_log(f"[Orchestrator] Job execution complete.", job_id, "SUCCESS" if result.get("status") == "success" else "ERROR")
    except Exception as e:
        if db_job:
            db_job.status = "FAILED"
            db_job.logs += f"\nException: {e}"
            db.commit()
        await broadcast_log(f"[Orchestrator] Job execution crashed: {e}", job_id, "ERROR")
    finally:
        heartbeat.cancel()
        db.close()
