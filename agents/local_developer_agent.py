import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from git import Repo
from tools.file_ops import read_file, write_file, list_files

@tool
def local_read_file(path: str) -> str:
    """Reads a file from the local filesystem."""
    return read_file(path)

@tool
def local_write_file(path: str, content: str) -> str:
    """Writes content to a file on the local filesystem."""
    return write_file(path, content)

@tool
def local_list_files(directory: str) -> str:
    """Lists all files in the given directory."""
    return list_files(directory)

@tool
def local_git_commit_and_push(repo_path: str, branch_name: str, message: str) -> str:
    """Commits all changes and pushes to the specified branch."""
    repo = Repo(repo_path)
    # Create branch
    new_branch = repo.create_head(branch_name)
    new_branch.checkout()
    # Add and commit
    repo.git.add(A=True)
    repo.index.commit(message)
    # Push
    origin = repo.remote(name='origin')
    origin.push(new_branch)
    return f"Successfully pushed changes to branch {branch_name}"

from tools.context7_mcp import load_context7_mcp_tools

class LocalDeveloperAgent:
    def __init__(self):
        model_name = os.environ.get("CODING_MODEL", "gemini-3.1-pro-preview")
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    async def implement_feature(self, story_details: dict, workspace_path: str) -> dict:
        title = story_details.get('title')
        description = story_details.get('description', '')
        branch_name = f"feature-local/{story_details.get('id', 'new-feature').replace('/', '-').replace('#', '-')}"
        
        print(f"  [LocalDeveloperAgent] Starting local dev flow for: {title}")
        
        system_prompt = f"""You are a Local Developer Agent.
Your workspace is located at: {workspace_path}
You have access to local file tools AND Context7 Documentation tools.
If you need technical documentation to solve the task, use the context7 tools.
Your task:
1. List the files to understand the project structure.
2. Read the relevant files.
3. Modify the code to implement: {title} ({description}).
4. Use the git tool to commit and push your changes to a new branch named '{branch_name}'.

ALWAYS use absolute paths for file operations. The base directory is {workspace_path}.
"""

        local_tools = [local_read_file, local_write_file, local_list_files, local_git_commit_and_push]
        
        async with load_context7_mcp_tools() as doc_tools:
            combined_tools = local_tools + doc_tools
            agent_executor = create_react_agent(self.llm, combined_tools)
            
            result = await agent_executor.ainvoke({"messages": [("user", system_prompt)]})
        
        content_raw = result["messages"][-1].content
        if isinstance(content_raw, list):
            content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content_raw])
        else:
            content = str(content_raw)
            
        return {
            "status": "success",
            "branch": branch_name,
            "message": f"Local implementation finished: {content[:100]}..."
        }
