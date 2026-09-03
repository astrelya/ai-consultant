"""
Developer Agent Module
Responsible for analyzing a user story, leveraging MCP tools to branch and PR, and writing code.
"""
import os
import asyncio
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from tools.mcp_loader import load_dev_tools
from agents.context7_grounding import ground_with_context7, Context7GroundingError
from agents.token_tracker import tracked_ainvoke

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

        # AD-8: Context7 grounding is mandatory before any code-generation ainvoke.
        try:
            grounding = await ground_with_context7(
                story_details, story_details.get("project_id")
            )
        except Context7GroundingError as exc:
            return {
                "status": "error",
                "reason": "context7_grounding_failed",
                "message": str(exc),
            }

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

        system_prompt = f"{grounding}\n{system_prompt}"

        # Context manager for the MCP connection (GitHub + Context7)
        async with load_dev_tools() as tools:
            # Create a localized ReAct agent incorporating the Gemini model and the loaded MCP tools
            agent_executor = create_react_agent(self.llm, tools)
            
            print("  [DeveloperAgent] Loaded MCP tools, executing ReAct reasoning loop...")
            
            # Execute the LangGraph ReAct agent
            result = await tracked_ainvoke(agent_executor, {"messages": [("user", system_prompt)]})
            
            # Print the final observation (robustly parsing content list if needed)
            content_raw = result["messages"][-1].content
            if isinstance(content_raw, list):
                content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content_raw])
            else:
                content = str(content_raw)

            print("  [DeveloperAgent] Execution Result:")
            print(content)
            
            # Extract PR URL from logs if it exists
            import re
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

        # AD-8: Context7 grounding is mandatory before any code-generation ainvoke.
        try:
            grounding = await ground_with_context7(
                story_details, story_details.get("project_id")
            )
        except Context7GroundingError as exc:
            return {
                "status": "error",
                "reason": "context7_grounding_failed",
                "message": str(exc),
            }

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

        system_prompt = f"{grounding}\n{system_prompt}"

        async with load_dev_tools() as tools:
            agent_executor = create_react_agent(self.llm, tools)
            print("  [DeveloperAgent] Loaded MCP tools, executing ReAct reasoning loop...")
            result = await tracked_ainvoke(agent_executor, {"messages": [("user", system_prompt)]})
            
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
