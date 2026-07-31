"""
POST /projects route — create a new project.
GET /projects — list all projects (lightweight, no heavy fields).
GET /projects/{project_id} — retrieve full project record by ID.

Rules:
- Pydantic v2: use @field_validator, not deprecated @validator.
- Blank/whitespace-only names must be rejected with 422.
- No LLM calls — direct DB write/read only (AD-4).
- Route handlers are async def (AD-9).
- GET /projects must NEVER expose agent_memory in list response (AD-5).
"""
import uuid
import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from backend.store import project_store
from backend.store import spec_store

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str

    @field_validator("name", mode="before")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not str(v).strip():
            raise ValueError("name must not be blank")
        return v


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime.datetime


@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project_endpoint(body: ProjectCreate) -> ProjectResponse:
    result = await project_store.create_project(body.name)
    return ProjectResponse(**result)


class ProjectListItem(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime.datetime


class ProjectDetail(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime.datetime
    agent_memory: dict
    spec: Optional[str]
    ticket_history: list
    cost_ledger: dict


@router.get("/projects", response_model=list[ProjectListItem])
async def list_projects_endpoint() -> list[ProjectListItem]:
    results = await project_store.list_projects()
    return [ProjectListItem(**r) for r in results]


@router.get("/projects/{project_id}", response_model=ProjectDetail)
async def get_project_endpoint(project_id: uuid.UUID) -> ProjectDetail:
    result = await project_store.get_project(str(project_id))
    if result is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectDetail(**result)


class SpecUpdate(BaseModel):
    spec: str
    repo_path: Optional[str] = None

    @field_validator("spec", mode="before")
    @classmethod
    def spec_not_blank(cls, v: str) -> str:
        if not str(v).strip():
            raise ValueError("spec must not be blank")
        return v

class SpecResponse(BaseModel):
    spec: str
    spec_file_written: bool
    spec_file_path: Optional[str]
    updated_at: datetime.datetime

@router.post("/projects/{project_id}/spec", response_model=SpecResponse, status_code=200)
async def update_project_spec_endpoint(project_id: uuid.UUID, body: SpecUpdate) -> SpecResponse:
    result = await spec_store.update_project_spec(str(project_id), body.spec, body.repo_path)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return SpecResponse(**result)

import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from backend.api.sse import SSEManager

class GeneratedTicket(BaseModel):
    title: str
    description: str
    acceptance_criteria: str
    
class TicketListResponse(BaseModel):
    tickets: list[dict]

@router.post("/projects/{project_id}/tickets/generate", response_model=TicketListResponse)
async def generate_tickets_endpoint(project_id: uuid.UUID):
    # Get project and spec
    project = await project_store.get_project(str(project_id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    spec = project.get("spec")
    if not spec:
        raise HTTPException(status_code=400, detail="Cannot generate tickets: spec is empty or missing")

    # Generate tickets using LLM
    model_name = os.environ.get("TICKET_MODEL", "gemini-2.5-flash")
    llm = ChatGoogleGenerativeAI(model=model_name)
    structured_llm = llm.with_structured_output(GeneratedTicket, method="json_schema", include_raw=False)
    
    # We want a list of tickets, so we define a wrapper model
    class TicketGenerationResult(BaseModel):
        tickets: list[GeneratedTicket]
        
    structured_llm = llm.with_structured_output(TicketGenerationResult)
    
    prompt = f"Based on the following specification, generate a comprehensive set of implementation tickets.\n\nSpec:\n{spec}"
    
    result = await structured_llm.ainvoke(prompt)
    
    # Prepare tickets for DB
    new_tickets = []
    for t in result.tickets:
        new_tickets.append({
            "id": str(uuid.uuid4()),
            "title": t.title,
            "description": t.description,
            "acceptance_criteria": t.acceptance_criteria,
            "status": "Pending",
            "blocking": [],
            "blocked_by": []
        })
        
    # Save to DB
    await project_store.save_generated_tickets(str(project_id), new_tickets)
    
    # Publish SSE
    sse_manager = await SSEManager.get_instance()
    await sse_manager.publish(str(project_id), "tickets_generated", {"tickets": new_tickets})
    
    return TicketListResponse(tickets=new_tickets)
