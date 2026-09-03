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
import os
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
    chat_history: list = []
    jira_configured: bool = False


@router.get("/projects", response_model=list[ProjectListItem])
async def list_projects_endpoint() -> list[ProjectListItem]:
    results = await project_store.list_projects()
    return [ProjectListItem(**r) for r in results]


@router.get("/projects/{project_id}", response_model=ProjectDetail)
async def get_project_endpoint(project_id: uuid.UUID) -> ProjectDetail:
    result = await project_store.get_project(str(project_id))
    if result is None:
        raise HTTPException(status_code=404, detail="Project not found")
        
    jira_configured = bool(
        os.environ.get("JIRA_URL") and 
        os.environ.get("JIRA_USER") and 
        os.environ.get("JIRA_API_TOKEN")
    )
    result["jira_configured"] = jira_configured
    
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

class TicketUpdate(BaseModel):
    status: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    acceptance_criteria: Optional[str] = None


@router.patch("/projects/{project_id}/tickets/{ticket_id}", status_code=200)
async def update_ticket_endpoint(
    project_id: uuid.UUID,
    ticket_id: str,
    body: TicketUpdate,
) -> dict:
    await project_store.update_ticket_fields(str(project_id), ticket_id, body.model_dump(exclude_unset=True))
    
    jira_configured = bool(
        os.environ.get("JIRA_URL") and 
        os.environ.get("JIRA_USER") and 
        os.environ.get("JIRA_API_TOKEN")
    )
    if jira_configured and body.status:
        from tools.ticket_manager import TicketManager
        tm = TicketManager()
        if body.status == "Accepted":
            project = await project_store.get_project(str(project_id))
            if project:
                tickets = json.loads(project.get("ticket_history", "[]")) if isinstance(project.get("ticket_history"), str) else (project.get("ticket_history") or [])
                ticket = next((t for t in tickets if t["id"] == ticket_id), None)
                if ticket:
                    # Create the issue in Jira
                    jira_key = await tm.create_jira_ticket(ticket["title"], ticket.get("description", ""))
                    if jira_key:
                        # Could save the Jira key back to DB here if needed
                        pass
        elif body.status in ["In Progress", "Done", "Error"]:
            await tm.transition_ticket(ticket_id, body.status)
            
    return {"ok": True}


import json
from langchain_google_genai import ChatGoogleGenerativeAI
from backend.chat.actions import generate_tickets_from_spec

class GeneratedTicket(BaseModel):
    title: str
    description: str
    acceptance_criteria: str
    
class TicketListResponse(BaseModel):
    tickets: list[dict]

@router.post("/projects/{project_id}/tickets/generate", response_model=TicketListResponse)
async def generate_tickets_endpoint(project_id: uuid.UUID):
    project = await project_store.get_project(str(project_id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    spec = project.get("spec")
    if not spec:
        raise HTTPException(status_code=400, detail="Cannot generate tickets: spec is empty or missing")

    tickets = await generate_tickets_from_spec(str(project_id), spec)
    return TicketListResponse(tickets=tickets)

class TicketRevisionRequest(BaseModel):
    instruction: str

class RevisedTicket(BaseModel):
    id: str
    title: str
    description: str
    acceptance_criteria: str
    blocking: list[str] = []
    blocked_by: list[str] = []

class RevisedTicketList(BaseModel):
    tickets: list[RevisedTicket]

@router.post("/projects/{project_id}/tickets/{ticket_id}/revise", response_model=TicketListResponse)
async def revise_ticket_endpoint(project_id: uuid.UUID, ticket_id: str, body: TicketRevisionRequest):
    project = await project_store.get_project(str(project_id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    tickets_json = project.get("ticket_history")
    if not tickets_json:
        raise HTTPException(status_code=400, detail="No tickets to revise")

    tickets = json.loads(tickets_json) if isinstance(tickets_json, str) else tickets_json

    model_name = os.environ.get("TICKET_MODEL", "gemini-2.5-flash")
    llm = ChatGoogleGenerativeAI(model=model_name)
    structured_llm = llm.with_structured_output(RevisedTicketList)

    prompt = f"""
You are a technical planner.
Here is the current list of tickets for a project:
{json.dumps(tickets, indent=2)}

The user wants to revise ticket '{ticket_id}' with the following instruction:
{body.instruction}

Please output the updated ticket. If this change affects other tickets (e.g. dependencies or scope), output those modified tickets as well.
Output ONLY the tickets that were modified. Do NOT output tickets that were unaffected.
Preserve the exact 'id' for any existing tickets you modify.
    """

    result = await structured_llm.ainvoke(prompt)

    updated_tickets_map = {t.id: t.model_dump() for t in result.tickets}
    
    for i, t in enumerate(tickets):
        if t["id"] in updated_tickets_map:
            status = t.get("status", "Pending")
            updated = updated_tickets_map[t["id"]]
            updated["status"] = status
            tickets[i] = updated
            
    existing_ids = {t["id"] for t in tickets}
    for t in result.tickets:
        if t.id not in existing_ids:
            new_ticket = t.model_dump()
            new_ticket["status"] = "Pending"
            tickets.append(new_ticket)

    await project_store.overwrite_ticket_history(str(project_id), tickets)

    from backend.api.sse import publish_event
    await publish_event(str(project_id), "tickets_generated", {"tickets": tickets})

    return TicketListResponse(tickets=tickets)
