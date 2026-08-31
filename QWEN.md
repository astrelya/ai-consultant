# QWEN.md — AI Consultant

Instructional context for AI agents working in this repository. Read `INSTRUCTIONS.md` before making changes — it contains **binding constraints** that take precedence over general conventions.

## Project Overview

**AI Consultant** is a hierarchical, multi-agent system built with **LangGraph** and **Google Gemini** (via `langchain-google-genai`) that automates the software development lifecycle end-to-end:

1. Fetches a ticket from **Jira** (default) or **GitHub Issues** through MCP.
2. Analyzes the user story to identify the target repository.
3. Clones/pulls the repo into an isolated `./workspaces/<repo>` folder.
4. Implements the feature using either a **local** developer agent (physical files + GitPython) or a **remote** developer agent (GitHub MCP API, serverless).
5. Generates real pytest tests from the spec's acceptance criteria, runs them in the workspace, writes a compliance report, and opens a pull request.

All external systems (GitHub, Jira, Context7 docs) are reached exclusively through **Model Context Protocol (MCP)** servers wrapped by `langchain-mcp-adapters`. There are no hand-rolled REST/HTTP client classes.

### Core technologies
- **Python 3.9+**, async-first (`asyncio` throughout — the MCP SDK requires it).
- **LangGraph** (`create_react_agent`) for ReAct reasoning loops.
- **Google Gemini** via `ChatGoogleGenerativeAI`.
- **MCP servers**: official GitHub MCP (Docker), Atlassian Rovo/Jira (via `mcp-remote`), Context7/Upstash (docs, via `npx`).
- **GitPython** for local git operations.

## Building and Running

### Prerequisites
1. Python 3.9+
2. Node.js & npm (Context7 + Jira MCP are launched via `npx`)
3. Docker Desktop (official GitHub MCP server)
4. Git (local mode)

### Setup
```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in the keys below
```

### Run
```bash
python main.py              # interactive agentic chat REPL
python -m app.server        # web backend + dashboard: http://127.0.0.1:8000 (Swagger at /docs)
python test_jira_mcp.py     # standalone smoke test: connect to Jira MCP and list tools
python test_sdd_gates.py    # SDD gate mechanism tests (interrupt/resume, SQLite persistence — no external services)
python test_verify_agent.py # VerifyAgent tests (real pytest execution + graph routing — no external services)
```

With `HUMAN_GATES=1` in `.env`, the pipeline pauses at the spec gate and the plan/tasks gate: the CLI prints the artifact and asks `Approve? [y/n]`; a `n` answer collects feedback and sends the agent back for a revision round.

`main.py` boots the `MCPManager` singleton (starts all MCP servers once), then loops on user input, routing each message through `SupervisorAgent.process_chat()`. Type `exit`/`quit` to close. Example prompts: `list available github projects`, `Implement PROJ-101`, `fix https://github.com/owner/repo/pull/12`, `Switch to local mode`.

> **Note on tests:** `pytest` is a declared dependency. `test_sdd_gates.py` covers the SDD gate mechanism and `test_verify_agent.py` covers the VerifyAgent's real pytest execution + graph routing (both run without any external service); `test_jira_mcp.py` remains a manual MCP smoke script.

## Environment Configuration

Authoritative source is `.env.example` plus what the code actually reads. Key variables:

| Variable | Purpose / Default |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key (required) |
| `GITHUB_TOKEN` or `GITHUB_PERSONAL_ACCESS_TOKEN` | GitHub auth (code falls back from the latter to the former) |
| `GITHUB_OWNER` | Default org/user for repo + PR resolution |
| `JIRA_URL`, `JIRA_USER`, `JIRA_API_TOKEN` | Jira site credentials |
| `CONTEXT7_API_KEY` | Upstash Context7 docs (optional; agent degrades gracefully without it) |
| `TICKET_SYSTEM` | `jira` (default) or `github` — which ticket source to use |
| `TICKET_MODEL` | Model for routing/routine tasks, default `gemini-2.5-flash` |
| `CODING_MODEL` | Model for writing code, default `gemini-3.1-pro-preview` |
| `SPEC_MODEL` | Optional override for the Spec/Plan/Task agents; falls back to `CODING_MODEL` |
| `AGENT_MODE` | `local` or `remote` (default `remote`) — which developer agent runs |
| `HUMAN_GATES` | `1` = enable human approval gates in the SDD pipeline (`interrupt()`); default `0` (auto-approve) |
| `CHECKPOINT_DB` | SQLite checkpoint DB path, default `./workspaces/.sdd/checkpoints.sqlite` |

The README's `.env` sample is slightly out of date relative to `.env.example`; trust `.env.example` and the code.

## Architecture

Strictly hierarchical — **all orchestration flows through `SupervisorAgent`** (`agents/main_agent.py`). Never bypass it.

- **`main.py`** — Async entry point / chat REPL. Loads dotenv, owns the `MCPManager` lifecycle.
- **`app/` — Web backend + dashboard** — `server.py`: FastAPI app (`python -m app.server`, http://127.0.0.1:8000, Swagger at /docs); calls `load_dotenv()` before agent/MCP env reads; lifespan pre-warms the MCP servers. `runner.py`: `PipelineRunner` (shared module-level singleton) runs pipelines as background asyncio tasks and reads their state from the checkpoint DB via `graph.aget_state()` — checkpoints are the single source of truth, so state survives restarts; `graph_factory` is injectable for tests. `api.py` JSON routes: `GET /api/tickets`, `GET|POST /api/pipelines`, `GET /api/pipelines/{thread_id}` (state + spec/plan/tasks artifacts), `POST /api/pipelines/{thread_id}/approve` (resumes the paused gate via `Command(resume=...)`; 409 if running or no pending gate), `GET /api/pipelines/{thread_id}/events` (SSE, 2s polling). `web.py` + `templates/` + `static/`: Jinja2 dashboard served at `/` (pipeline list + start form) and `/pipelines/{thread_id}` (status badge, gate approval panel with approve / reject+feedback, task progress, spec/plan/tasks tabs rendered client-side with marked.js, live updates via native EventSource on the SSE endpoint).
- **`agents/main_agent.py` — `SupervisorAgent`** (the brain). A LangGraph ReAct agent over Gemini (`TICKET_MODEL`) that routes user intent to these tools: `FetchTickets`, `ImplementTicket`, `ImplementPRRecommendations`, `SetDeveloperMode`, plus Context7 doc tools. Keeps a rolling chat history (last 20 messages) for session memory. Two main flows:
  - `run(issue_id)`: delegates to the **SDD pipeline** (`core.graph.run_sdd_pipeline`) — an explicit LangGraph state machine: fetch ticket → environment setup → spec → gate → plan + tasks → gate → per-task implementation → verify (tests + pytest + report) → PR + Jira *In Review*. See `core/` below.
  - `implement_pr_recommendations(pr_url_or_number)`: parse PR ref (`parse_pr_identifier` handles full URLs, `owner/repo#N`, `repo#N`, bare `N`) → fetch PR details + review comments via `TicketManager` → prepare workspace → checkout the PR branch (GitPython) → infer an associated Jira key from the branch name → delegate to developer → tests → push.
- **`core/` — SDD pipeline (Spec-Driven Development)** — `state.py` defines the shared `SDDState` TypedDict + status constants; `graph.py` builds a LangGraph `StateGraph`: `fetch_ticket → prepare_env → write_spec → gate_spec → write_plan → breakdown_tasks → gate_plan → implement_task (self-loop, one task at a time) → verify --passed--> finish --open PR--> END` (a failed verification routes straight to END). The `verify` node runs the real `VerifyAgent` and stores its report as `verification.md`; the `finish` node opens the pull request via GitHub MCP (`RemoteDeveloperAgent.open_pull_request`, non-fatal on failure) in **both** local and remote modes, then transitions the ticket to *In Review*. Checkpoints persist to SQLite (`AsyncSqliteSaver`, path `CHECKPOINT_DB`) — or `MemorySaver` when building the graph directly. Gates auto-approve when `HUMAN_GATES=0`; with `1` they call LangGraph `interrupt()` and `drive_graph_with_gates()` resumes them via an `on_gate` callback (payload → `{"approved": bool, "feedback": str}`); in the CLI, `SupervisorAgent._cli_gate` prints the artifact and prompts approve/feedback on stdin. With no `on_gate`, a paused state (carrying `__interrupt__`) is returned for external resume (future web backend). `artifacts.py` stores `spec.md` / `plan.md` / `tasks.md` / `verification.md` under `./workspaces/.sdd/<repo>/<ticket>/` — deliberately **outside** the cloned repo so they are never committed.
- **`agents/spec_agent.py` / `plan_agent.py` / `task_agent.py`** — SDD agents: SpecAgent and PlanAgent are ReAct agents with read-only file tools that explore the workspace before writing `spec.md` / `plan.md`; TaskAgent is a pure LLM call returning an ordered JSON task list (falls back to one generic task on parse failure). Both developer agents expose `implement_task()` for the per-task loop.
- **`agents/environment_agent.py` — `EnvironmentAgent`** — Resolves the repo name (from a `repo#N` ticket id, else via LLM; prompts the user if unknown), then clones or pulls into `./workspaces/<repo>` using a token-authenticated HTTPS URL.
- **`agents/local_developer_agent.py` — `LocalDeveloperAgent`** — Works on physical files with local tools (`read/write/list` from `tools/file_ops.py`) + a `local_git_commit_and_push` tool + Context7 MCP docs. Uses `CODING_MODEL`. Branch: `feature-local/<id>`.
- **`agents/developer_agent.py` — `RemoteDeveloperAgent`** — Works purely via GitHub MCP (`load_dev_tools()`). Creates branch `feature/<id>`, writes code, opens a PR; scrapes the PR URL out of the agent's message log with a regex. `open_pull_request()` creates the pipeline-end PR from an already-pushed branch (used by the SDD `finish` node in both modes).
- **`agents/verify_agent.py` — `VerifyAgent`** — Real verification (Phase 4, replaces the old `TesterAgent` stub): syncs the workspace clone to the feature branch (fetch/checkout/pull), generates real pytest tests from the approved spec's acceptance criteria (ReAct agent with local file tools + Context7 docs), commits and pushes the generated tests to the branch, executes `pytest` in the workspace (`run_pytest` is a pure function — unit-tested without any external service), and writes an LLM-driven spec-compliance report (with a non-LLM fallback). A failed verification stops the pipeline. Also exposes `write_and_run_tests()` for the legacy PR-recommendations flow.
- **`tools/mcp_loader.py` — `MCPManager`** (singleton) — Async context manager that starts GitHub MCP (always), Jira MCP (only when `TICKET_SYSTEM=jira`), and Context7 MCP (always). `load_dev_tools()` yields the combined tool set.
- **`tools/github_mcp.py`** — Launches the official GitHub MCP server in Docker (`ghcr.io/github/github-mcp-server`) over stdio, loads tools via `langchain-mcp-adapters`.
- **`tools/jira_mcp.py`** — Connects to Atlassian Rovo MCP via `npx -y mcp-remote@latest https://mcp.atlassian.com/v1/mcp/authv2`.
- **`tools/context7_mcp.py`** — Launches `@upstash/context7-mcp` via `npx`; yields an empty tool list (with a warning) if no API key is set, so the agent never crashes on missing docs.
- **`tools/ticket_manager.py` — `TicketManager`** — Uses a Gemini ReAct agent to interpret MCP tool schemas and fetch ticket details / todo tickets / PR details, and to transition Jira status (step-by-step workflow transitions). Prompts demand raw JSON output; falls back to mock data if the LLM returns unparseable JSON. **Hardcoded Jira `cloudId`** (`95778ac0-3f3b-46a0-95f5-e465d87b6a37`, tied to `astrelya.atlassian.net`) is baked into several prompts — update it if the Jira site changes.
- **`tools/file_ops.py`** — Minimal `read_file` / `write_file` / `list_files` helpers used by the local developer agent.

## Development Conventions (binding — from `INSTRUCTIONS.md`)

- **LLM models:** Do **not** use deprecated `gemini-1.0`/`gemini-1.5` series models. Default to modern Gemini (`gemini-3.1-pro` or generic `gemini-pro`). Always instantiate via `langchain-google-genai` → `ChatGoogleGenerativeAI`.
- **Architecture:** Keep the strict hierarchy. All task delegation/orchestration must route through `SupervisorAgent` (`agents/main_agent.py`). Do not bypass it.
- **External systems:** Do **not** write direct HTTP/REST wrapper classes for external services (GitHub, Jira, etc.). Integrate via MCP using `langchain-mcp-adapters`. Prefer the adapters' context-manager wrapper over the raw `mcp` SDK for tool ingestion.
- **Workspace isolation:** Development artifacts must only be written inside isolated `./workspaces/<repo>` folders produced by `EnvironmentAgent`. Do not write generated artifacts into the repo root unless you are modifying core system architecture.
- **Async:** New agents/workflows must use standard `asyncio` (the MCP SDK demands async execution loops that map to LangGraph primitives).
- **Dependencies:** Do not override the pinned libraries in `requirements.txt`.

## Style Notes (observed)

- Agents follow a consistent pattern: build a system prompt string, wrap tools in an async context manager, run `create_react_agent(self.llm, tools).ainvoke({"messages": [...]})`, then robustly parse `result["messages"][-1].content` (which may be a list of text blocks or a plain string) and return a small dict with a `status` key.
- Verbose logging from `langchain_core`, `langchain_mcp_adapters`, `langgraph`, and `langchain_google_genai` is silenced in `main.py`.
- Branch naming: remote → `feature/<id>`, local → `feature-local/<id>` (with `/` and `#` sanitized to `-`).
