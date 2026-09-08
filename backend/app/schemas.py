from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, ConfigDict


# ---------- Projects ----------
class ProjectCreate(BaseModel):
    name: str
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str | None
    implementation_trigger_mode: str | None
    created_at: datetime
    updated_at: datetime


# ---------- Repo Config ----------
class RepoConfigIn(BaseModel):
    org_or_owner: str
    repo_name: str
    default_branch: str = "main"
    pat: str  # plaintext, encrypted server-side


class RepoConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    provider: str
    org_or_owner: str
    repo_name: str
    default_branch: str


# ---------- Jira Config ----------
class JiraConfigIn(BaseModel):
    site_url: str
    jira_project_key: str
    default_issue_type: str = "Story"
    auth_email: str
    api_token: str  # plaintext, encrypted server-side


class JiraConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    site_url: str
    jira_project_key: str
    default_issue_type: str
    auth_email: str


# ---------- Model Config ----------
class ModelConfigIn(BaseModel):
    chat_model: str
    coding_model: str
    chat_model_params: dict[str, Any] = Field(default_factory=dict)
    coding_model_params: dict[str, Any] = Field(default_factory=dict)


class ModelConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str | None
    chat_model: str
    coding_model: str
    chat_model_params: dict[str, Any]
    coding_model_params: dict[str, Any]


# ---------- App Settings ----------
class AppSettingsIn(BaseModel):
    implementation_trigger_mode: str = "manual"
    poll_interval_seconds: int = 60
    auto_trigger_jira_status: str = "Ready for Dev"
    gemini_api_key: str | None = None  # plaintext, encrypted server-side; null = leave unchanged


class AppSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    implementation_trigger_mode: str
    poll_interval_seconds: int
    auto_trigger_jira_status: str
    gemini_api_key_set: bool = False


# ---------- Chat ----------
class ChatSessionCreate(BaseModel):
    title: str | None = None


class ChatSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    title: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class ChatMessageIn(BaseModel):
    content: str


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    session_id: str
    role: str
    content: str
    model_used: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    created_at: datetime


# ---------- Tickets ----------
class TicketDraftUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    acceptance_criteria: list[str] | None = None
    issue_type: str | None = None
    priority: str | None = None
    labels: list[str] | None = None
    epic_link: str | None = None


class TicketDraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    chat_session_id: str | None
    title: str
    description: str
    acceptance_criteria: list[str]
    issue_type: str
    priority: str
    labels: list[str]
    epic_link: str | None
    status: str
    jira_issue_key: str | None
    push_error: str | None
    order_index: int
    created_at: datetime


class BatchIdsIn(BaseModel):
    draft_ids: list[str]


# ---------- Runs ----------
class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    run_type: str
    related_id: str | None
    model_used: str | None
    status: str
    input_summary: str | None
    output_summary: str | None
    error_message: str | None
    input_tokens: int | None = None
    output_tokens: int | None = None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class ImplementIn(BaseModel):
    jira_issue_key: str


class PullRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    jira_issue_key: str
    pr_url: str | None
    pr_number: int | None
    status: str
    created_at: datetime


class TriggerModeIn(BaseModel):
    implementation_trigger_mode: str | None = None
