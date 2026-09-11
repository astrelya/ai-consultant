# 🤖 AI Consultant: Autonomous Agentic Software System

AI Consultant is a hierarchical multi-agent system built with **LangGraph** and **Google Gemini** that automates the software development lifecycle. It can fetch tickets from GitHub Projects, analyze them, clone your repository, implement features, and even search for documentation automatically.

---

## 🌟 Key Features

*   **Hierarchical Agentic Design**: A Supervisor Agent orchestrates specialized sub-agents (Environment, Developer, Tester).
*   **Dual-Mode Development**:
    *   **Local Mode**: Clones the real repository to your local machine, modifies physical files, and runs local Git operations.
    *   **Remote Mode**: Uses the official GitHub MCP server to interact with code directly via API (Serverless coding).
*   **Deep Documentation Integration**: Integrated with **Context7 (Upstash)** MCP server, allowing agents to "read the manual" when encountering unknown libraries.
*   **Official GitHub MCP support**: Uses the official GitHub-maintained Docker image for robust repository management (PRs, Issues, Branching).
*   **Conversation Memory**: The Supervisor remembers your previous requests, context, and preferred settings during a session.
*   **Jira Watcher**: Automatically detects new Jira tickets and triggers the implementation pipeline without manual intervention.

---

## 🛠 Prerequisites

Before starting, ensure you have the following installed:
1.  **Python 3.9+**
2.  **Node.js & npm** (Required for Context7 tools via `npx`).
3.  **Docker Desktop** (Required for the official GitHub MCP server).
4.  **Git** (Required for the Local mode).

---

## 🚀 Installation & Setup

### 1. Clone the repository
```bash
git clone https://github.com/your-username/ai-consultant.git
cd ai-consultant
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Create a `.env` file in the root directory:
```env
# Core API Keys
GEMINI_API_KEY=your_google_gemini_key
GITHUB_PERSONAL_ACCESS_TOKEN=your_token_with_repo_scope

# Strategy Configuration
GITHUB_OWNER=your-github-username-or-org
AGENT_MODE=local  # or 'remote'
GEMINI_MODEL=gemini-3.1-pro-preview

# Optional Documentation Access
CONTEXT7_API_KEY=your_upstash_context7_key

# Jira Configuration
JIRA_URL=https://your-domain.atlassian.net
JIRA_POLL_INTERVAL=60
```

---

## 💻 Usage

Launch the interactive AI Chat Interface:
```bash
python main.py
```

### Example Commands:
*   `list available github projects`: Fetches tickets from your GitHub Projects V2 boards.
*   `Switch to local mode`: Tells the supervisor to start cloning and editing physical files.
*   `Implement repo-name#21`: Starts the full autonomous dev loop for ticket #21.
*   `What is Javelit?`: If Context7 is configured, the Supervisor will search the documentation and explain it to you.

### Jira Watcher (Auto-Implementation)
To run the system in fully autonomous mode where it watches for new Jira tickets and implements them automatically:
```bash
python jira_watcher.py
```

---

## 🏗 System Architecture

*   **SupervisorAgent** (`agents/main_agent.py`): The brain. Routes requests and manages session memory.
*   **EnvironmentAgent** (`agents/environment_agent.py`): Handles real `git clone` and `git pull` operations.
*   **Developer Agents**:
    *   `LocalDeveloperAgent`: Works on files via `tools/file_ops.py`.
    *   `RemoteDeveloperAgent`: Works via `ghcr.io/github/github-mcp-server` Docker container.
*   **TicketManager** (`tools/ticket_manager.py`): Uses advanced GitHub Projects V2 tools.

---

## 📄 License
MIT License. Feel free to fork and build your own autonomous consultant!

AI Form: https://forms.gle/WuhR57JpVFdYwLht5
