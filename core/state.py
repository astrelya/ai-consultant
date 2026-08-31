"""
SDD Pipeline State Module
Defines the shared typed state for the Spec-Driven Development LangGraph pipeline.
Every node reads from and returns partial updates of this state.
"""
import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict


class TaskItem(TypedDict, total=False):
    id: str
    title: str
    description: str
    acceptance_criteria: List[str]
    status: str  # "pending" | "in_progress" | "done" | "failed"


class SDDState(TypedDict, total=False):
    # --- Ticket & environment ---
    ticket_id: str
    ticket: Dict[str, Any]          # Raw ticket details (id, title, description, ...)
    repo_full_name: str             # "owner/repo"
    workspace_path: str             # Local clone path under ./workspaces
    mode: str                       # "local" | "remote"

    # --- Phase: Specify (spec.md artifact) ---
    spec: str
    spec_feedback: str              # Reviewer feedback for a revision round

    # --- Phase: Plan & Tasks (plan.md + tasks.md artifacts) ---
    plan: str
    tasks: List[TaskItem]
    plan_feedback: str

    # --- Phase: Implement (one task at a time) ---
    current_task_index: int
    branch_name: str
    pr_url: Optional[str]
    implementation_log: Annotated[List[str], operator.add]

    # --- Phase: Verify ---
    verification: Dict[str, Any]    # {status, test_files, coverage, message}

    # --- Meta ---
    status: str                     # See STATUS_* constants below
    error: Optional[str]


# Pipeline status values (single source of truth for routing)
STATUS_SPEC_DRAFTING = "spec_drafting"
STATUS_PENDING_SPEC_APPROVAL = "pending_spec_approval"
STATUS_PLANNING = "planning"
STATUS_PENDING_PLAN_APPROVAL = "pending_plan_approval"
STATUS_IMPLEMENTING = "implementing"
STATUS_VERIFYING = "verifying"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
