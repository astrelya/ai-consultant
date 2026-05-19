"""
Developer Agent Module
Responsible for analyzing a user story, leveraging MCP tools to branch and PR, and writing code.
"""
import os
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
You have access to GitHub and Context7 Documentation via MCP tools.
If you need documentation for libraries/frameworks, use the context7 tools.
Your task:
1. Create a branch named '{branch_name}'.
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
        
        # After remote tools are executed, we return standard workflow output
        return {
            "status": "success",
            "branch": branch_name,
            "code_files": [f"{workspace_path}/src"], # simplified for now
            "message": "Used MCP to PR feature."
        }
