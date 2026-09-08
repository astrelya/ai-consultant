# Spec-Driven Development App — Technical Specification

## 1. Overview

### 1.1 Goal
Turn the existing CLI-based agent pipeline (Jira ticket → implementation → PR) into a full web application that adds a **spec-authoring front end**: users brainstorm requirements with an agent, the agent drafts one or more Jira tickets from that conversation, the user reviews/edits/accepts them in the UI, and only then are they posted to Jira. The existing "read ticket → implement → open PR" pipeline becomes the second half of the same app.

### 1.2 Core capabilities to build
1. **Project setup** — link a GitHub repo and a Jira workspace/project to a "Project" entity in the app.
2. **Brainstorm chat** — conversational agent that helps the user clarify a rough spec/idea into something ticket-ready.
3. **Ticket drafting agent** — turns the finalized conversation into one or more structured ticket drafts (not yet in Jira).
4. **Ticket review UI** — a board/list of draft tickets, grouped by project, each editable and individually accept/reject-able.
5. **Jira push** — only accepted tickets are POSTed to Jira, via the Jira REST API.
6. **Existing implementation pipeline** — read accepted/assigned Jira tickets → implement in the linked repo → open a PR (already exists in CLI form; needs to be wrapped as a service the app can trigger/monitor).
7. **Model configuration** — Gemini models, configurable independently for the **chat/brainstorm agent** vs the **coding/implementation agent**, per project (with a global default).

### 1.3 Confirmed scope decisions
- **Single user, local-only.** No multi-tenant accounts, no login/auth system, no hosted deployment. The app runs on the user's machine (e.g. via Docker Compose) and is used by one person.
- **GitHub auth: Personal Access Token (PAT).** Simplest fit for a local single-user tool — no GitHub App registration needed.
- **Implementation trigger: both manual and automatic**, switchable in Settings (see §4.4a).
- **Ticket-drafting agent uses the chat model** (same slot as the brainstorm agent).

### 1.4 Out of scope (initial version, list explicitly so nothing is assumed)
- Multi-user accounts, permissions, or org-level billing.
- Hosted/cloud deployment (see §8.1 for what this simplifies).
- Non-Jira issue trackers (Linear, GitHub Issues) — architecture should allow adding later, not build now.
- Non-GitHub repo hosts (GitLab, Bitbucket) — same note.
- Real-time multi-user collaborative editing of a single ticket.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                        │
│  Project setup | Brainstorm chat | Ticket review board | Runs   │
└───────────────┬───────────────────────────────────┬─────────────┘
                │ REST + WebSocket                   │
┌───────────────▼───────────────────────────────────▼─────────────┐
│                     Backend API (FastAPI)                       │
│  - Auth & project config                                        │
│  - Chat session management (streams via WebSocket)              │
│  - Ticket draft CRUD + status transitions                       │
│  - Job orchestration (enqueue agent runs)                       │
│  - Integration clients: Jira, GitHub, Gemini                    │
└───────┬───────────────────┬───────────────────┬─────────────────┘
        │                   │                   │
┌───────▼──────┐   ┌────────▼───────┐   ┌───────▼────────┐
│ Postgres DB  │   │ Task queue      │   │ Secrets store   │
│ (projects,   │   │ (Celery/RQ +    │   │ (encrypted API  │
│ chats,       │   │ Redis) — runs   │   │ keys: Jira,     │
│ tickets,     │   │ chat-to-ticket, │   │ GitHub, Gemini) │
│ runs, PRs)   │   │ implement, PR   │   │                 │
└──────────────┘   └────────┬────────┘   └─────────────────┘
                             │
                    ┌────────▼─────────┐
                    │ Agent workers     │
                    │ - Brainstorm agent│
                    │ - Ticket-drafting │
                    │   agent           │
                    │ - Implementation  │
                    │   agent (existing │
                    │   CLI logic)      │
                    └────────┬──────────┘
                             │
                ┌────────────┼─────────────┐
                ▼            ▼             ▼
             Gemini API   Jira API     GitHub API
```

### 2.1 Recommended stack
| Layer | Choice | Why |
|---|---|---|
| Backend | **FastAPI** (Python) | Reuses your existing Python agent code directly; async support for streaming chat and long agent runs; easy WebSocket support. |
| Frontend | **React + TypeScript**, Vite | Standard, works well for a chat UI + kanban-style review board. |
| DB | **PostgreSQL** | Relational data (projects → tickets → runs) with JSON columns for flexible ticket fields/agent metadata. |
| Task queue | **Celery or RQ + Redis** | Agent runs (chat turn, ticket drafting, implementation, PR creation) are long-running/async and should not block API requests. |
| Realtime | **WebSockets** (FastAPI native) | Streaming chat responses token-by-token, and pushing job status updates (e.g., "implementation agent running…") to the UI. |
| Secrets | **Encrypted DB fields** (Fernet, key stored in a local `.env`/config file, never committed) | Stores Jira token, GitHub PAT, Gemini API key. No cloud secrets manager needed — local-only app. |
| Auth | **None.** The app binds to localhost and is used by one person. | Skip login/session/JWT entirely; simplifies the whole API surface. |

---

## 3. Data Model

### 3.1 Entity overview
- **User** — app user (even if single-user initially, model it now).
- **Project** — the central entity; owns one repo config + one Jira config + model config overrides.
- **RepoConfig** — GitHub repo connection for a project.
- **JiraConfig** — Jira workspace/project connection.
- **ModelConfig** — chat model + coding model selection, global or per-project.
- **ChatSession** — a brainstorm conversation, belongs to a project.
- **ChatMessage** — individual messages in a session (user/agent/system).
- **TicketDraft** — a proposed ticket, generated from a chat session, in a review-pending state.
- **AgentRun** — a log/record of any agent invocation (chat turn, ticket drafting, implementation, PR creation) — for observability and retries.
- **PullRequest** — record of a PR opened by the implementation agent, linked to a Jira ticket.

### 3.2 Schema (PostgreSQL DDL sketch)

No `users` table — single-user local app, no ownership/permissions to model.

```sql
-- Projects
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Repo configuration (1:1 or 1:many with project — start 1:1, allow many later)
CREATE TABLE repo_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'github',
    org_or_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    default_branch TEXT DEFAULT 'main',
    encrypted_pat TEXT NOT NULL,     -- GitHub Personal Access Token, encrypted at rest
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Jira configuration
CREATE TABLE jira_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    site_url TEXT NOT NULL,          -- e.g. https://yourcompany.atlassian.net
    jira_project_key TEXT NOT NULL,  -- e.g. "ENG"
    default_issue_type TEXT DEFAULT 'Story',
    auth_email TEXT NOT NULL,
    encrypted_api_token TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Model configuration (nullable project_id = global default)
CREATE TABLE model_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE, -- NULL = global default
    chat_model TEXT NOT NULL DEFAULT 'gemini-2.5-pro',
    coding_model TEXT NOT NULL DEFAULT 'gemini-2.5-pro',
    chat_model_params JSONB DEFAULT '{}',   -- temperature, max_tokens, etc.
    coding_model_params JSONB DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- App-wide settings (singleton row) + per-project override
CREATE TABLE app_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    implementation_trigger_mode TEXT NOT NULL DEFAULT 'manual', -- 'manual' | 'auto_poll'
    poll_interval_seconds INT DEFAULT 60,   -- used when mode = auto_poll
    auto_trigger_jira_status TEXT DEFAULT 'Ready for Dev', -- Jira status that triggers implementation
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE projects ADD COLUMN implementation_trigger_mode TEXT; -- NULL = use app_settings default

-- Chat sessions (brainstorming)
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'active', -- active | ready_for_tickets | archived
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,             -- user | assistant | system
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Ticket drafts (pre-Jira)
CREATE TABLE ticket_drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    chat_session_id UUID REFERENCES chat_sessions(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    acceptance_criteria JSONB DEFAULT '[]',  -- array of strings
    issue_type TEXT NOT NULL DEFAULT 'Story', -- Story | Task | Bug | Epic
    priority TEXT DEFAULT 'Medium',
    labels JSONB DEFAULT '[]',
    epic_link TEXT,                          -- optional parent epic key or draft group id
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | edited | accepted | rejected | pushed | push_failed
    jira_issue_key TEXT,                     -- populated after successful push
    order_index INT DEFAULT 0,               -- display ordering within a batch
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Agent run log (any agent invocation: chat turn, drafting, implementation, PR)
CREATE TABLE agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    run_type TEXT NOT NULL,          -- chat | draft_tickets | implement | open_pr
    related_id UUID,                 -- chat_session_id / ticket_draft_id / jira_issue key context
    model_used TEXT,
    status TEXT NOT NULL DEFAULT 'queued', -- queued | running | succeeded | failed
    input_summary TEXT,
    output_summary TEXT,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- PRs opened by the implementation agent
CREATE TABLE pull_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    jira_issue_key TEXT NOT NULL,
    repo_config_id UUID REFERENCES repo_configs(id),
    pr_url TEXT,
    pr_number INT,
    status TEXT NOT NULL DEFAULT 'open', -- open | merged | closed
    agent_run_id UUID REFERENCES agent_runs(id),
    created_at TIMESTAMPTZ DEFAULT now()
);
```

### 3.3 Notes on the ticket draft grouping ("which belongs to which project")
- Every `ticket_draft` row already carries `project_id` directly — so the review UI can group/filter by project without joins through the chat session.
- A single brainstorm session can produce **multiple** ticket drafts in one batch; use `chat_session_id` to group drafts that came from the same conversation, and `order_index` to preserve the order the agent proposed them in.
- `epic_link` lets the agent optionally propose that several drafts belong under one epic — surfaced in the UI as a group header.

---

## 4. User Flows

### 4.1 Project setup
1. User creates a Project (name + description).
2. User connects a GitHub repo: org/owner, repo name, auth (PAT or GitHub App install).
   - Validate by making a lightweight API call (e.g., fetch repo metadata) before saving.
3. User connects a Jira workspace: site URL, project key, email + API token.
   - Validate via a call to `/rest/api/3/myself` or similar before saving.
4. User optionally sets project-level model overrides (chat model, coding model); otherwise global defaults apply.

### 4.2 Brainstorm → tickets
1. User opens a new chat session under a Project.
2. User describes a feature/spec in free text.
3. Chat agent (using the **chat model**) asks clarifying questions, proposes scope boundaries, flags ambiguities — standard back-and-forth, streamed to the UI.
4. When the user feels the spec is clear, they click **"Generate tickets"** (or the agent proactively suggests it once it judges the spec is sufficiently clear — but the action is always user-triggered, not automatic).
5. Backend enqueues a `draft_tickets` agent run: the full chat transcript is sent to the ticket-drafting agent (can reuse the chat model or a distinct prompt/config — see §6.1), which returns a **structured list** of ticket drafts (JSON) matching the `ticket_drafts` schema fields.
6. Drafts are inserted into `ticket_drafts` with status `pending`, all sharing `chat_session_id`.
7. Chat session status flips to `ready_for_tickets`.

### 4.3 Ticket review board
1. UI shows a board/list view, **grouped by project**, then by batch (chat session) or epic group within a project.
2. Each ticket draft card shows: title, issue type, priority, description preview, acceptance criteria count, labels, and the project it belongs to (always visible, even in a cross-project "all drafts" view).
3. Actions per ticket:
   - **Edit** — inline form (title, description, acceptance criteria, type, priority, labels, epic link) → status becomes `edited`.
   - **Accept** — status becomes `accepted`.
   - **Reject** — status becomes `rejected` (excluded from push, kept for audit).
4. Batch actions: **Accept all**, **Push accepted to Jira**.
5. **Push to Jira** only sends tickets with status `accepted` (or `edited` then explicitly accepted — edited alone should not be pushable, to force a conscious accept step). On success, store `jira_issue_key` and set status `pushed`; on failure, set `push_failed` with the error surfaced in the UI and a retry action.

### 4.4 Implementation pipeline (wraps existing CLI logic)
1. Once tickets exist in Jira (either pushed from this app or pre-existing tickets picked up the old way), the user (or an automated trigger, e.g., a ticket moved to "Ready for Dev" in Jira) starts an implementation run for a given Jira issue key.
2. Backend enqueues an `implement` agent run: fetch ticket details from Jira → implementation agent (using the **coding model**) reads the linked repo, makes changes → commits to a branch.
3. Backend enqueues an `open_pr` run: push branch, open PR via GitHub API, link PR back to the Jira ticket (comment or PR description referencing the issue key), record in `pull_requests`.
4. UI shows a "Runs" view listing agent runs (chat/draft/implement/PR) per project with status and links to the resulting PR.

### 4.4a Implementation trigger mode (manual + automatic)
Configurable in Settings, globally and per-project (per-project overrides the global default):
- **Manual** — user explicitly clicks "Implement" on a Jira issue in the app.
- **Auto (poll)** — a background job polls the linked Jira project on an interval (`poll_interval_seconds`) for issues matching `auto_trigger_jira_status` (e.g. "Ready for Dev") that don't already have an `agent_runs` record, and enqueues an `implement` run automatically.

> Note: because the app is local-only, Jira Cloud cannot push a webhook to your machine directly (localhost isn't reachable from the internet). **Polling is the realistic "automatic" mechanism** here rather than a Jira webhook. If you later want true webhook push, you'd need a tunnel (e.g. ngrok) — worth keeping in mind but not needed for v1.
- Manual mode remains available at all times regardless of the auto setting, so you can always force a run on a specific ticket.

### 4.5 Model configuration flow
1. Settings page: global default `chat_model` / `coding_model` (Gemini model names, e.g. `gemini-2.5-pro`, `gemini-2.5-flash`).
2. Per-project override section: same two fields, falls back to global default if unset.
3. Changing a model does not affect in-flight `agent_runs`; new runs pick up the current config at enqueue time (store `model_used` on the run for traceability).

---

## 5. API Design (REST + WebSocket)

Base path: `/api/v1`

### 5.1 Projects & config
```
POST   /projects                          Create project
GET    /projects                          List projects
GET    /projects/{project_id}             Get project (incl. repo/jira/model config)
PATCH  /projects/{project_id}              Update name/description
DELETE /projects/{project_id}

POST   /projects/{project_id}/repo-config       Create/update repo connection
POST   /projects/{project_id}/repo-config/test  Validate repo credentials
DELETE /projects/{project_id}/repo-config

POST   /projects/{project_id}/jira-config       Create/update Jira connection
POST   /projects/{project_id}/jira-config/test  Validate Jira credentials
DELETE /projects/{project_id}/jira-config

GET    /model-configs/default              Get global default model config
PUT    /model-configs/default              Update global default
GET    /projects/{project_id}/model-config Get project override (falls back to default)
PUT    /projects/{project_id}/model-config Set project override
```

### 5.2 Chat / brainstorm
```
POST   /projects/{project_id}/chat-sessions          Create session
GET    /projects/{project_id}/chat-sessions          List sessions for project
GET    /chat-sessions/{session_id}                    Get session + messages
POST   /chat-sessions/{session_id}/messages           Send a user message (triggers agent reply)
WS     /ws/chat-sessions/{session_id}                 Stream agent response tokens + status
POST   /chat-sessions/{session_id}/generate-tickets   Trigger ticket-drafting agent run
```

### 5.3 Ticket drafts
```
GET    /ticket-drafts?project_id=&session_id=&status=   List/filter drafts
GET    /ticket-drafts/{draft_id}
PATCH  /ticket-drafts/{draft_id}                          Edit fields (status -> edited)
POST   /ticket-drafts/{draft_id}/accept
POST   /ticket-drafts/{draft_id}/reject
POST   /ticket-drafts/batch-accept                        { draft_ids: [...] }
POST   /ticket-drafts/push                                { draft_ids: [...] } -> pushes accepted ones to Jira
POST   /ticket-drafts/{draft_id}/retry-push
```

### 5.4 Implementation pipeline
```
POST   /projects/{project_id}/implement                  { jira_issue_key } -> enqueues implement run
GET    /agent-runs?project_id=&run_type=&status=          List runs (for a "Runs" dashboard)
GET    /agent-runs/{run_id}
WS     /ws/agent-runs/{run_id}                             Stream status/log updates
GET    /pull-requests?project_id=&jira_issue_key=
```

### 5.5 Settings
```
GET    /settings                                   Get app_settings (trigger mode, poll interval, etc.)
PUT    /settings                                    Update app_settings
PATCH  /projects/{project_id}/implementation-trigger  Set per-project override (or null to inherit)
```

No auth endpoints — local single-user app, no login system.

---

## 6. Agent Design

### 6.1 Agents needed
| Agent | Model slot | Input | Output |
|---|---|---|---|
| **Brainstorm agent** | Chat model | Chat history + user message | Streamed conversational reply; may ask clarifying questions |
| **Ticket-drafting agent** | Chat model (confirmed) | Full chat transcript | Structured JSON list of ticket drafts (title, description, acceptance criteria, type, priority, labels, suggested epic grouping) |
| **Implementation agent** | Coding model | Jira ticket details + repo access | Code changes committed to a branch (existing CLI logic, reused) |
| **PR agent** | Coding model or plain API logic (may not need an LLM call at all — could be templated) | Branch + ticket context | Opened GitHub PR with description linking the Jira issue |

### 6.2 Ticket-drafting agent output contract
Enforce a strict JSON schema so the backend can insert rows directly without fragile parsing:

```json
{
  "tickets": [
    {
      "title": "string",
      "description": "string",
      "acceptance_criteria": ["string", "..."],
      "issue_type": "Story | Task | Bug | Epic",
      "priority": "Highest | High | Medium | Low | Lowest",
      "labels": ["string"],
      "suggested_epic_group": "string | null"
    }
  ]
}
```
Use Gemini's structured output / JSON mode if available, plus server-side schema validation (e.g., Pydantic) before writing to the DB — reject and retry the run if the model returns malformed output.

### 6.3 Reusing the existing CLI code
- Wrap the current CLI's core functions (Jira read, repo implementation, PR creation) as importable Python functions/classes rather than CLI entry points, so both the CLI and the new FastAPI backend/worker can call them directly without shelling out.
- The task queue workers become the new "runner" for what the CLI used to do interactively.

---

## 7. Integrations

### 7.1 Jira
- Auth: API token + email (Basic Auth) for Jira Cloud, or OAuth 2.0 (3LO) if you want per-user Jira identity instead of a shared token.
- Endpoints needed: `POST /rest/api/3/issue` (create), `GET /rest/api/3/issue/{key}` (read), `GET /rest/api/3/myself` (credential validation), `GET /rest/api/3/project/{key}` (validate project key exists).
- Map internal `issue_type`/`priority` strings to the Jira project's actual allowed values (fetch via `/rest/api/3/issue/createmeta` and validate/normalize before push — different Jira projects can have different configured issue types).

### 7.2 GitHub
- Auth: **Personal Access Token (PAT)**, scoped at minimum to `repo` (and `workflow` if the agent ever needs to touch GitHub Actions files). Generated once in GitHub → Settings → Developer settings → Personal access tokens, pasted into the repo config screen, stored encrypted.
- Needed calls: repo metadata (validation), create branch, commit changes, open PR, comment/link back to Jira issue.
- Since this is a single local user acting as themself, the PR will show up as authored by your own GitHub account — that's expected and fine for this setup.

### 7.3 Gemini
- Single client wrapper with a `model_name` parameter resolved per-call from `model_configs` (project override → global default).
- Support at minimum: `gemini-2.5-pro`, `gemini-2.5-flash` (confirm current available model names at build time, since these change).
- Store the API key encrypted; likely one key for the whole app rather than per-project, unless you want per-project billing isolation.

---

## 8. Local Deployment

Since this is single-user and local-only, keep the setup simple:
- **Docker Compose** with three services: `api` (FastAPI), `worker` (Celery/RQ), `db` (Postgres) + `redis` for the queue/broker. Frontend can be served by Vite dev server locally, or built and served as static files by the API for a single-command startup.
- No HTTPS/TLS needed (localhost only) — but still encrypt stored tokens at rest in the DB in case the DB file/volume is ever shared or backed up.
- Encryption key for secrets (Fernet key) lives in a local `.env` file, gitignored, generated once on first run.
- A single `docker-compose up` should bring up the whole stack; a `Makefile` or shell script can wrap common commands (migrate, seed, start).
- Background poller (§4.4a) runs as a periodic task inside the `worker` service (Celery beat, or a simple `asyncio` loop in a dedicated process) — no separate infrastructure needed.

## 9. Non-functional requirements
- **Idempotency**: pushing tickets to Jira should be safe to retry without creating duplicates (check `jira_issue_key` is null before pushing; use per-draft locking).
- **Auditability**: `agent_runs` table gives a full history of what each agent did, which model was used, and the outcome — needed for debugging bad ticket drafts or failed implementations.
- **Error surfacing**: any failure (bad Jira credentials, malformed agent JSON, GitHub push conflict) must be visible in the UI with enough detail to act on, not just a generic "failed" state.
- **Secrets**: never return decrypted tokens to the frontend; only use them server-side.
- **Streaming UX**: chat responses and long-running agent runs (implementation can take minutes) should stream progress rather than leave the user staring at a spinner with no feedback.

---

## 10. Suggested build order
1. DB schema + Project/RepoConfig/JiraConfig CRUD + credential validation endpoints.
2. Model config (global + per-project) + Gemini client wrapper.
3. Brainstorm chat (session + messages + WebSocket streaming) using the chat model.
4. Ticket-drafting agent + `/generate-tickets` + ticket_drafts CRUD.
5. Ticket review UI (board grouped by project) + accept/edit/reject + push-to-Jira.
6. Wrap existing CLI implementation logic as callable functions; wire up `/implement` + PR creation + `agent_runs`/`pull_requests` tracking.
7. Runs dashboard (observability across all agent activity).

---

## 11. Resolved decisions summary
- Chat model handles both brainstorming and ticket-drafting.
- Single-user, local-only — no auth, no multi-tenant model.
- Implementation triggers support both manual and automatic (polling-based, since local can't receive Jira webhooks), switchable in Settings globally or per project.
- GitHub auth via Personal Access Token.
- Deployment: local Docker Compose, no hosted infra, no TLS required.

## 12. Remaining open question
1. For the auto-poll trigger, is polling every Jira issue in the linked project on an interval acceptable, or would you rather explicitly whitelist which Jira statuses/labels should be picked up (already modeled as `auto_trigger_jira_status` in §3.2 — confirm the default status name matches your Jira workflow, e.g. is it really called "Ready for Dev" in your setup, or something else)?