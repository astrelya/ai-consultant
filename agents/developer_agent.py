"""
Developer Agent Module
Responsible for analyzing a user story, leveraging MCP tools to branch and PR, and writing code.
"""
import os
import asyncio
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
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
        
        repo_full_name = story_details.get('repo_full_name', 'unknown')
        owner, repo = (repo_full_name.split('/') + ['unknown'])[:2]

        # Build the prompt
        system_prompt = f"""You are an elite Developer Subagent working on a GitHub repository.

Repository: owner='{owner}', repo='{repo}'
Task: {title}
Details: {description}

You MUST complete these steps IN ORDER using the GitHub MCP tools:

STEP 1 - Get the default branch SHA:
  Call get_file_contents or list_branches to find the current HEAD SHA of the default branch (usually 'master' or 'main').

STEP 2 - Create a new branch:
  Call create_branch with owner='{owner}', repo='{repo}', branch='{branch_name}', from_branch='master' (or the default branch name found in step 1).

STEP 3 - Read existing code for context:
  Call get_file_contents to read the relevant file(s) in the repository. For example, read 'agents/tester_agent.py' to understand the current implementation.

STEP 4 - Push the new/modified file(s):
  Call create_or_update_file (or push_files) with owner='{owner}', repo='{repo}', branch='{branch_name}' to write your implementation.

STEP 5 - Create a Pull Request:
  Call create_pull_request with owner='{owner}', repo='{repo}', head='{branch_name}', base='master', title and body summarizing your changes.

IMPORTANT:
- Always use owner='{owner}' and repo='{repo}' (NOT the full path '{repo_full_name}').
- Do NOT skip steps. Do NOT explain what you will do without calling tools.
- If a step fails, log the error and try an alternative approach.
"""

        # Context manager for the MCP connection (GitHub + Context7)
        async with load_dev_tools() as tools:
            tool_names = [t.name for t in tools]
            print(f"  [DeveloperAgent] {len(tools)} tools loaded.")

            agent_executor = create_agent(self.llm, tools)
            
            import time, traceback
            start_time = time.time()
            print(f"  [DeveloperAgent] Executing ReAct reasoning loop (ainvoke starting)...")
            
            result = None
            try:
                # Stream events in real-time so we see each step as it happens
                async for event in agent_executor.astream_events(
                    {"messages": [("user", system_prompt)]},
                    config={"recursion_limit": 50},
                    version="v2",
                ):
                    kind = event.get("event")
                    name = event.get("name", "")
                    if kind == "on_chat_model_start":
                        print(f"  [DeveloperAgent] >> LLM thinking (node: {name})...")
                    elif kind == "on_tool_start":
                        inp = str(event.get("data", {}).get("input", ""))[:200]
                        print(f"    -> [Debug] Tool '{name}' called with: {inp}")
                    elif kind == "on_tool_end":
                        out = str(event.get("data", {}).get("output", ""))[:300]
                        print(f"    <- [Debug] Tool '{name}' returned: {out}")
                    elif kind == "on_chain_end" and name == "LangGraph":
                        result = event.get("data", {}).get("output")
                        print(f"  [DeveloperAgent] Graph ended.")

            except Exception as e:
                elapsed = time.time() - start_time
                print(f"  [DeveloperAgent] EXCEPTION after {elapsed:.2f}s: {type(e).__name__}: {e}")
                traceback.print_exc()
                raise

            elapsed = time.time() - start_time
            print(f"  [DeveloperAgent] ReAct loop finished in {elapsed:.2f} seconds")

            if result is None:
                print("  [DeveloperAgent] WARNING: result is None — no on_chain_end event received.")
                raise RuntimeError("DeveloperAgent graph returned no result.")

            messages = result.get("messages", []) if isinstance(result, dict) else []
            print(f"  [DeveloperAgent] Result contains {len(messages)} message(s).")

            content_raw = messages[-1].content if messages else ""
            if isinstance(content_raw, list):
                content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content_raw])
            else:
                content = str(content_raw)

            print("  [DeveloperAgent] Final LLM message:")
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
        
        repo_full_name = story_details.get('repo_full_name', 'unknown')
        owner, repo = (repo_full_name.split('/') + ['unknown'])[:2]

        system_prompt = f"""You are an elite Developer Subagent working on a GitHub repository.

Repository: owner='{owner}', repo='{repo}'
You are working on the EXISTING branch '{branch_name}'. Do NOT create a new branch and do NOT open a new PR.
Task: {description}

You MUST complete these steps IN ORDER using the GitHub MCP tools:

STEP 1 - Read the relevant file(s):
  Call get_file_contents with owner='{owner}', repo='{repo}', branch='{branch_name}' to read the file(s) that need to be changed.

STEP 2 - Push your changes:
  Call create_or_update_file (or push_files) with owner='{owner}', repo='{repo}', branch='{branch_name}' to save your implementation.

IMPORTANT:
- Always use owner='{owner}' and repo='{repo}' (NOT the full path '{repo_full_name}').
- Do NOT create a new branch. Do NOT create a new pull request.
- Do NOT explain what you will do without calling tools.

Your task:
1. Read/understand the requested changes: {description}.
2. Make the necessary code modifications in the workspace.
3. Commit the changes and push them directly to the existing branch '{branch_name}' in the repository '{story_details.get('repo_full_name', 'unknown')}'. Do NOT create a new branch and do NOT create a new pull request.
"""

        async with load_dev_tools() as tools:
            agent_executor = create_agent(self.llm, tools)
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
