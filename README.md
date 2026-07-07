# 🤖 AI Consultant: Spec-Driven Autonomous Dev Agent

AI Consultant is a **Spec-Driven**, hierarchical multi-agent system built with **LangGraph**, **Google Gemini**, and **FastAPI + Next.js**. It transforms product specification documents into Jira tickets, resolves their dependencies using topological sorting, and implements them autonomously in parallel — with real-time WebSocket logs streamed to a premium web dashboard.

---

## 🌟 Key Features

- **Spec-to-Jira Pipeline**: Upload Markdown, PDF, or URLs → Gemini decomposes into structured User Stories → pushed to Jira with dependency links.
- **Topological DAG Orchestration**: Analyzes ticket interdependencies and schedules them for parallel or sequential execution.
- **codegraph MCP**: Semantic codebase navigation — agents explore symbols and definitions instead of reading dozens of files.
- **rtk Bash Proxy**: Compresses large CLI outputs (git, pytest, npm test) by 80–90% before the LLM reads them.
- **Caveman Prompt**: Injects telegraphic constraints into all agent prompts — 65% reduction in LLM response verbosity.
- **Real-Time Dashboard**: Next.js frontend with WebSocket log console, DAG visualizer, spec review checkpoint, and settings panel.
- **Dual-Mode Development**: Remote (GitHub MCP API) or Local (cloned workspaces) dev agents.
- **PostgreSQL Backend**: Persistent jobs, specs, and configs via FastAPI + SQLAlchemy.

---

## 🛠 Prerequisites

1. **Python 3.9+**
2. **Node.js & npm** (for Next.js frontend and MCP tools via `npx`)
3. **Docker Desktop** (for GitHub MCP server)
4. **PostgreSQL** (for job/config/spec persistence)
5. **Git**

---

## 🚀 Installation & Setup

### 1. Clone and install Python dependencies
```bash
git clone https://github.com/your-username/ai-consultant.git
cd ai-consultant
pip install -r requirements.txt
```

### 2. Configure environment variables
```bash
cp .env.example .env
# Edit .env and fill in all your API keys and database URL
```

### 3. Setup PostgreSQL
```bash
# Create the database (example using psql)
psql -U postgres -c "CREATE DATABASE spec_driven_dev;"
# The tables are auto-created on first backend startup
```

### 4. Install rtk (optional — for compressed CLI output)
```bash
python scripts/install_rtk.py
```

---

## 💻 Running the System

### Option A — Full Stack (Backend + Frontend + CLI)

**Terminal 1 — FastAPI Backend:**
```bash
python -m uvicorn backend.main:app --reload --port 8000
```

**Terminal 2 — Next.js Frontend:**
```bash
cd frontend
npm run dev
# Open http://localhost:3000
```

**Terminal 3 — CLI Chat Interface (optional):**
```bash
python main.py
```

### Option B — CLI Only
```bash
python main.py
```

---

## 💬 Chat Commands

| Command | Action |
|---|---|
| `analyze spec <path/url>` | Parse spec → generate stories → create Jira tickets |
| `implement tickets PROJ-1, PROJ-2, PROJ-3` | Multi-ticket orchestration with DAG |
| `show dependency graph PROJ-1, PROJ-2` | ASCII DAG of ticket dependencies |
| `list available tickets` | List all Jira tickets |
| `implement PROJ-101` | Implement single ticket |
| `fix pr <url>` | Apply PR review recommendations |
| `switch to local mode` | Use local workspace instead of GitHub API |

---

## 🏗 System Architecture

```
Spec Doc (MD/PDF/txt/URL)
       ↓
SpecAnalyzerAgent  ←── Gemini (story decomposition)
       ↓  [Human checkpoint in UI]
TicketCreatorAgent → Jira (batch + dependency links)
       ↓
DependencyAnalyzer  ←── LLM semantic analysis + Jira links
       ↓  [DAG + topological sort]
MultiTicketOrchestrator
  ├─ Layer 0: PROJ-1 + PROJ-2  (parallel asyncio)
  └─ Layer 1: PROJ-3           (depends on Layer 0)

RemoteDeveloperAgent  [remote by default]
  + codegraph  → understands codebase semantically
  + caveman    → concise LLM output
  + rtk        → compressed test/git output

FastAPI Backend  ←→  WebSocket  ←→  Next.js Dashboard
PostgreSQL       ←→  Jobs/Specs/Configs
```

### Agents
| Agent | File | Role |
|---|---|---|
| `SupervisorAgent` | `agents/main_agent.py` | Routes all commands, manages memory |
| `SpecAnalyzerAgent` | `agents/spec_analyzer_agent.py` | Decomposes specs into User Stories |
| `TicketCreatorAgent` | `agents/ticket_creator_agent.py` | Batch-creates Jira tickets |
| `MultiTicketOrchestrator` | `agents/multi_ticket_agent.py` | Topological DAG + parallel execution |
| `RemoteDeveloperAgent` | `agents/developer_agent.py` | Implements via GitHub MCP API |
| `LocalDeveloperAgent` | `agents/local_developer_agent.py` | Implements in cloned workspaces |
| `TesterAgent` | `agents/tester_agent.py` | Writes and runs tests via rtk |
| `EnvironmentAgent` | `agents/environment_agent.py` | Clones repos into isolated workspaces |

### Tools
| Tool | File | Purpose |
|---|---|---|
| `codegraph` | `tools/codegraph_mcp.py` | Semantic code graph navigation |
| `rtk_wrapper` | `tools/rtk_wrapper.py` | Compressed CLI command execution |
| `caveman_prompt` | `tools/caveman_prompt.py` | Token-saving prompt injection |
| `spec_parser` | `tools/spec_parser.py` | PDF/URL/Markdown spec parsing |
| `dependency_analyzer` | `tools/dependency_analyzer.py` | DAG builder for ticket dependencies |

---

## 📄 License
MIT License. Feel free to fork and build your own autonomous consultant!
