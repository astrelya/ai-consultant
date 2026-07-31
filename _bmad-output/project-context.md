---
project_name: 'ai-consultant'
user_name: 'astrelya'
date: '2026-07-08'
sections_completed: ['technology_stack', 'architecture', 'language_rules', 'framework_rules', 'testing_rules', 'environment_rules', 'workflow_rules']
---

# Project Context for AI Agents

_Critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

- **Python** 3.9+ (runtime)
- **LangGraph** — `langgraph` — ReAct agent orchestration via `create_react_agent`
- **LangChain** — `langchain`, `langchain-core`, `langchain-google-genai`
- **LLM Backend** — Google Gemini (`langchain_google_genai.ChatGoogleGenerativeAI`)
- **MCP Integration** — `mcp`, `langchain-mcp-adapters` (stdio transport)
- **GitPython** — local git operations
- **python-dotenv** — environment variable loading
- **pytest** — testing framework
- **requests** — HTTP utilities

**External MCP Servers (runtime dependencies):**
- GitHub: Docker image `ghcr.io/github/github-mcp-server` — requires Docker Desktop running
- Context7/Upstash: via `npx` (Node.js required)
- Atlassian Jira: via `npx mcp-remote@latest https://mcp.atlassian.com/v1/mcp/authv2`

---

## Critical Implementation Rules

### Architecture Rules

- **Never break the agent hierarchy**: `SupervisorAgent` → (`EnvironmentAgent`, `LocalDeveloperAgent` / `RemoteDeveloperAgent`, `TesterAgent`). Sub-agents must not call each other directly.
- **MCPManager is a singleton** (`MCPManager._instance`). Never instantiate it directly — always use `await MCPManager.get_instance()`. All MCP connections are managed through its `AsyncExitStack`.
- **MCP connections are long-lived** via `MCPManager.initialize()` and closed only via `manager.close()`. The `load_dev_tools()` context manager yields from the already-initialized singleton — it does NOT open new connections.
- **New MCP tool loaders** (e.g., `load_jira_mcp_tools`) must be registered inside `MCPManager.initialize()`, not called ad-hoc.

### Language-Specific Rules (Python)

- **All agent `invoke` calls must be async** (`await agent_executor.ainvoke(...)`). Never use the synchronous `invoke` on LLM or agent executors.
- **Load environment variables at entry point only** — `load_dotenv()` is called once in `main.py`. Sub-modules read from `os.environ.get(...)`, never call `load_dotenv()` again.
- **LangGraph tool functions decorated with `@tool`** must have a docstring — it is used as the tool description exposed to the LLM.
- **Use `os.environ.get("KEY", "default")`** everywhere — never hard-code model names, credentials, or paths.
- **LLM content responses can be a list** when using Gemini multimodal responses. Always handle: `if isinstance(content_raw, list): content = "".join([item.get("text","") if isinstance(item, dict) else str(item) for item in content_raw])`.
- **`tools/file_ops.py` functions are plain Python**, not `@tool`-decorated — wrap them with `@tool` in agent modules when exposing them to LangGraph agents (see `local_developer_agent.py` pattern).

### Framework-Specific Rules (LangGraph / LangChain MCP)

- **Always use `create_react_agent(llm, tools)`** from `langgraph.prebuilt` — do not build custom graph agents unless necessary.
- **Agent messages are passed as `{"messages": [("user", prompt)]}`** — the standard LangGraph ReAct invocation format.
- **MCP stdio tools require the subprocess to be reachable** — Docker must be running for GitHub MCP, Node.js for Context7 and Jira MCP. Missing prerequisites cause `MCPManager.initialize()` to silently skip that tool set (see try/except blocks).
- **`StdioServerParameters` `env` must include `PATH`** — on Windows especially, child processes launched without `PATH` in env cannot find executables. Pattern: `env=os.environ.copy()` or explicitly pass `"PATH": os.environ.get("PATH", "")`.
- **`ChatGoogleGenerativeAI` model names come from env vars**: `TICKET_MODEL` (fast routing/analysis, default `gemini-2.5-flash`) and `CODING_MODEL` (code generation, default `gemini-3.1-pro-preview`). Never hard-code model strings in agent constructors.
- **Suppress LangChain noise** at the `main.py` entry point using `logging.getLogger("langchain_core").setLevel(logging.ERROR)` — do not add this inside agent modules.

### Dual-Mode Development Rules

- **`AGENT_MODE` env var** controls which developer agent runs: `local` → `LocalDeveloperAgent`, `remote` (default) → `RemoteDeveloperAgent`.
- **`TICKET_SYSTEM` env var** controls ticket source: `jira` (default) → Jira MCP, `github` → GitHub MCP.
- **Local mode** clones the real repository into `WORKSPACE_DIR` (default `./workspaces`) and operates on disk. Use absolute paths for all file operations in local mode.
- **Remote mode** uses GitHub MCP API — no local clone, no disk writes. Branch names follow `feature/{ticket-id}`.
- **Local mode branch naming**: `feature-local/{ticket-id}` (with `/` and `#` replaced by `-`).

### Workspace & File Operation Rules

- **`workspaces/` directory** is where repositories are cloned in local mode — never commit contents of this directory.
- **`EnvironmentAgent._extract_repo_name()`** uses an LLM call to extract repo name from ticket — when adding new ticket sources, this method must be updated.
- **`tools/file_ops.py` `list_files()` skips `.git` directories** — this is intentional; do not remove that filter.
- **`write_file()` creates intermediate directories** via `os.makedirs(exist_ok=True)` — no need to pre-create directories before writing.

### Testing Rules

- **Test files go in `tests/` directory** with prefix `test_` (e.g., `test_{feature_name}.py`).
- **TesterAgent currently generates scaffold tests only** — real test generation with LLM is a known TODO. When implementing, follow the same async agent pattern as other agents.
- **Use `pytest`** — do not introduce `unittest` or other frameworks.
- **`test_jira_mcp.py`** at root is an integration/smoke test for MCP connectivity — keep it separate from unit tests in `tests/`.

### Environment & Configuration Rules

**Required env vars (application will fail without these):**
- `GEMINI_API_KEY` — Google Gemini API key
- `GITHUB_PERSONAL_ACCESS_TOKEN` — GitHub token with repo scope (also checked as `GITHUB_TOKEN`)

**Required for ticket operations:**
- `TICKET_SYSTEM` — `jira` or `github`
- `GITHUB_OWNER` — GitHub org/user namespace
- For Jira: `JIRA_URL`, `JIRA_USER`, `JIRA_API_TOKEN`

**Optional with defaults:**
- `AGENT_MODE` → `remote`
- `TICKET_MODEL` → `gemini-2.5-flash`
- `CODING_MODEL` → `gemini-3.1-pro-preview`
- `WORKSPACE_DIR` → `./workspaces`
- `CONTEXT7_API_KEY` — needed for Context7 doc lookups

### Development Workflow Rules

- **Add new agents** in `agents/` as a new class module; register as a sub-agent in `SupervisorAgent.__init__()`.
- **Add new MCP tool sources** in `tools/` following the `@contextlib.asynccontextmanager` pattern; register in `MCPManager.initialize()`.
- **Never expose credentials** in `StdioServerParameters` env dict beyond what the MCP server needs — copy only the required keys, not the full `os.environ`.
- **Chat history** is maintained on `SupervisorAgent.chat_history` list — new conversational capabilities must append to this list, not replace it.

### Critical Don't-Miss Rules

- **`langchain-google-genai` Gemini responses may return content as a list of dicts** — always guard against this when reading `result["messages"][-1].content`.
- **GitHub MCP requires Docker to be running** — all code paths that call `load_github_mcp_tools()` will fail silently (logged, not raised) if Docker is unavailable. Do not assume tools are populated.
- **Jira `cloudId` is hardcoded in `TicketManager._get_jira_ticket_details()`** as `95778ac0-3f3b-46a0-95f5-e465d87b6a37` — if the Jira workspace changes, update this value.
- **Jira MCP requires `fields` parameter** to limit payload size — always include `fields=summary,description,status` or the response will be too large to process reliably.
- **`warnings.filterwarnings("ignore")` is set globally** in `main.py` to suppress MCP tool translation schema warnings — this is intentional and must remain at entry point scope only.

---

## Usage Guidelines

**For AI Agents:**
- Read this file before implementing any code
- Follow ALL rules exactly as documented
- When in doubt, prefer the more restrictive option
- Update this file if new patterns emerge

**For Humans:**
- Keep this file lean and focused on agent needs
- Update when technology stack changes
- Review quarterly for outdated rules
- Remove rules that become obvious over time

Last Updated: 2026-07-08
