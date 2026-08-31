"""
Developer Agent Module
Responsible for analyzing a user story, leveraging MCP tools to branch and PR, and writing code.
"""
import os
import re
import asyncio
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from tools.mcp_loader import load_dev_tools

class RemoteDeveloperAgent:
    def __init__(self):
        # Initialize the Gemini Model
        model_name = os.environ.get("CODING_MODEL", "gemini-3.1-pro-preview")
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    async def implement_feature(self, story_details: dict, workspace_path: str) -> dict:
        title = story_details.get('title')
        description = story_details.get('description', '')
        branch_name = f"feature/{story_details.get('id', 'new-feature')}"
        
        print(f"  [RemoteDeveloperAgent] Starting remote dev flow via MCP for: {title}")
        
        # Build the prompt
        system_prompt = f"""You are an elite Developer Subagent. 
Your workspace path locally is {workspace_path}. 
The target GitHub repository is: '{story_details.get('repo_full_name', 'unknown')}'.
You have access to GitHub and Context7 Documentation via MCP tools.
If you need documentation for libraries/frameworks, use the context7 tools.
Your task:
1. Create a branch named '{branch_name}' in the repository '{story_details.get('repo_full_name', 'unknown')}'.
2. Write/Push code related to solving: {title} ({description}).
3. Create a pull request outlining what you did.
"""

        # Context manager for the MCP connection (GitHub + Context7)
        async with load_dev_tools() as tools:
            # Create a localized ReAct agent incorporating the Gemini model and the loaded MCP tools
            agent_executor = create_react_agent(self.llm, tools)
            
            print("  [DeveloperAgent] Loaded MCP tools, executing ReAct reasoning loop...")
            
            # Execute the LangGraph ReAct agent
            result = await agent_executor.ainvoke({"messages": [("user", system_prompt)]})
            
            # Print the final observation (robustly parsing content list if needed)
            content_raw = result["messages"][-1].content
            if isinstance(content_raw, list):
                content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content_raw])
            else:
                content = str(content_raw)

            print("  [DeveloperAgent] Execution Result:")
            print(content)
            
            # Extract PR URL from logs if it exists
            pr_url = None
            for msg in reversed(result.get("messages", [])):
                content_str = str(msg.content)
                match = re.search(r"https://github\.com/[\w\-]+/[\w\-]+/pull/\d+", content_str)
                if match:
                    pr_url = match.group(0)
                    break
        
        # After remote tools are executed, we return standard workflow output
        return {
            "status": "success",
            "branch": branch_name,
            "pr_url": pr_url,
            "code_files": [f"{workspace_path}/src"], # simplified for now
            "message": "Used MCP to PR feature."
        }

    async def implement_pr_recommendations(self, story_details: dict, branch_name: str, workspace_path: str) -> dict:
        title = story_details.get('title')
        description = story_details.get('description', '')
        
        print(f"  [RemoteDeveloperAgent] Starting remote PR recommendations flow via MCP for: {title}")
        
        system_prompt = f"""You are an elite Developer Subagent. 
Your workspace path locally is {workspace_path}. 
The target GitHub repository is: '{story_details.get('repo_full_name', 'unknown')}'.
You are working on the EXISTING branch '{branch_name}' which is already checked out.
You have access to GitHub and Context7 Documentation via MCP tools.
If you need documentation for libraries/frameworks, use the context7 tools.
Your task:
1. Read/understand the requested changes: {description}.
2. Make the necessary code modifications in the workspace.
3. Commit the changes and push them directly to the existing branch '{branch_name}' in the repository '{story_details.get('repo_full_name', 'unknown')}'. Do NOT create a new branch and do NOT create a new pull request.
"""

        async with load_dev_tools() as tools:
            agent_executor = create_react_agent(self.llm, tools)
            print("  [DeveloperAgent] Loaded MCP tools, executing ReAct reasoning loop...")
            result = await agent_executor.ainvoke({"messages": [("user", system_prompt)]})
            
            content_raw = result["messages"][-1].content
            if isinstance(content_raw, list):
                content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content_raw])
            else:
                content = str(content_raw)

            print("  [DeveloperAgent] Execution Result:")
            print(content)
        
        return {
            "status": "success",
            "branch": branch_name,
            "message": "Used MCP to implement PR recommendations."
        }

    async def implement_task(self, story_details: dict, spec: str, plan: str, task: dict, branch_name: str, workspace_path: str) -> dict:
        """Implements a single task from the approved SDD spec/plan via GitHub MCP (Spec-Driven pipeline)."""
        ac_lines = "\n".join(f"- {ac}" for ac in task.get("acceptance_criteria", [])) or "- (see specification)"

        print(f"  [RemoteDeveloperAgent] Implementing task {task.get('id')} via MCP: {task.get('title')}")

        system_prompt = f"""You are an elite Developer Subagent implementing ONE task from an approved specification.
The target GitHub repository is: '{story_details.get('repo_full_name', 'unknown')}'.
Work on branch '{branch_name}' — push directly to it. Do NOT create a new branch and do NOT create a pull request.

APPROVED SPECIFICATION:
{spec}

IMPLEMENTATION PLAN:
{plan}

CURRENT TASK ({task.get('id')}): {task.get('title')}
{task.get('description', '')}
Task acceptance criteria:
{ac_lines}

Your task:
1. Read the relevant files in the repository to understand the current code.
2. Implement ONLY this task — do not implement other tasks or refactor unrelated code.
3. Commit and push the changes directly to branch '{branch_name}'.
"""

        async with load_dev_tools() as tools:
            agent_executor = create_react_agent(self.llm, tools)
            print("  [DeveloperAgent] Loaded MCP tools, executing ReAct reasoning loop...")
            result = await agent_executor.ainvoke({"messages": [("user", system_prompt)]})

            content_raw = result["messages"][-1].content
            if isinstance(content_raw, list):
                content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content_raw])
            else:
                content = str(content_raw)

            print("  [DeveloperAgent] Execution Result:")
            print(content)

        return {
            "status": "success",
            "task_id": task.get("id"),
            "branch": branch_name,
            "message": f"Task {task.get('id')} pushed to {branch_name} via MCP."
        }

    async def open_pull_request(self, story_details: dict, branch_name: str, body: str) -> dict:
        """Creates a pull request for an already-pushed feature branch via GitHub MCP.
        Used by the SDD pipeline finish node (both local and remote modes — the
        branch has been pushed in either case)."""
        repo = story_details.get("repo_full_name", "unknown")
        title = f"feat({story_details.get('id', 'ticket')}): {story_details.get('title', 'SDD implementation')}"

        print(f"  [RemoteDeveloperAgent] Opening PR for branch '{branch_name}' in '{repo}'...")

        system_prompt = f"""You are a Developer Agent creating a pull request.
The target GitHub repository is: '{repo}'.
The feature branch '{branch_name}' has already been pushed to the remote.
Your task:
1. Create a pull request in '{repo}' from head branch '{branch_name}' to the repository's default base branch (usually 'main'; use 'master' if 'main' does not exist).
2. PR title: {title}
3. PR body (markdown, verbatim):
{body}

Do NOT modify any code and do NOT push anything. When done, reply with ONLY the full pull request URL."""

        async with load_dev_tools() as tools:
            agent_executor = create_react_agent(self.llm, tools)
            print("  [DeveloperAgent] Loaded MCP tools, creating pull request...")
            result = await agent_executor.ainvoke({"messages": [("user", system_prompt)]})

        content_raw = result["messages"][-1].content
        if isinstance(content_raw, list):
            content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content_raw])
        else:
            content = str(content_raw)

        print("  [DeveloperAgent] PR creation result:")
        print(content)

        pr_url = None
        for msg in reversed(result.get("messages", [])):
            match = re.search(r"https://github\.com/[\w\-]+/[\w\-]+/pull/\d+", str(msg.content))
            if match:
                pr_url = match.group(0)
                break

        return {
            "status": "success" if pr_url else "failed",
            "pr_url": pr_url,
            "message": content[:200],
        }
