import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from langchain_core.tools import tool
from git import Repo
from tools.file_ops import read_file, write_file, list_files
from tools.context7_mcp import load_context7_mcp_tools
from tools.codegraph_mcp import load_codegraph_mcp_tools



class LocalDeveloperAgent:
    def __init__(self):
        model_name = os.environ.get("CODING_MODEL", "gemini-3.1-pro-preview")
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    def _build_local_tools(self, touched_files: list):
        """
        Builds the local file-op tools for a single agent run, bound (via closure)
        to a `touched_files` list so we can report back exactly which files the
        LLM actually wrote to. This replaces the old module-level @tool functions,
        which had no way to communicate what they touched back to the caller.
        """

        @tool
        def local_read_file(path: str) -> str:
            """Reads a file from the local filesystem."""
            try:
                return read_file(path)
            except Exception as e:
                return f"Error reading {path}: {type(e).__name__}: {e}"

        @tool
        def local_write_file(path: str, content: str) -> str:
            """Writes content to a file on the local filesystem."""
            try:
                result = write_file(path, content)
                abs_path = os.path.abspath(path)
                if abs_path not in touched_files:
                    touched_files.append(abs_path)
                return result
            except Exception as e:
                return f"Error writing {path}: {type(e).__name__}: {e}"

        @tool
        def local_list_files(directory: str) -> str:
            """Lists all files in the given directory."""
            try:
                return list_files(directory)
            except Exception as e:
                return f"Error listing {directory}: {type(e).__name__}: {e}"

        @tool
        def local_git_commit_and_push(repo_path: str, branch_name: str, message: str) -> str:
            """Commits all changes and pushes to the specified branch."""
            try:
                repo = Repo(repo_path)
                # Check if branch exists, otherwise create it
                if branch_name in repo.heads:
                    branch = repo.heads[branch_name]
                else:
                    branch = repo.create_head(branch_name)
                branch.checkout()
                # Add and commit
                repo.git.add(A=True)
                # Avoid committing if no changes exist
                if repo.is_dirty():
                    repo.index.commit(message)
                # Push
                origin = repo.remote(name='origin')
                origin.push(branch)
                return f"Successfully pushed changes to branch {branch_name}"
            except Exception as e:
                return f"Git operation failed: {e}"

        return [local_read_file, local_write_file, local_list_files, local_git_commit_and_push]

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

ALWAYS use absolute paths for file operations, built by joining {workspace_path} with a path you obtained from local_list_files or local_read_file output. NEVER guess a path or construct one using '..' relative traversal — if you are unsure a path exists, call local_list_files on its parent directory first.
"""
        from tools.caveman_prompt import wrap_with_caveman
        system_prompt = wrap_with_caveman(system_prompt)

        touched_files = []
        local_tools = self._build_local_tools(touched_files)

        import time
        async with load_context7_mcp_tools() as doc_tools, load_codegraph_mcp_tools() as codegraph_tools:
            combined_tools = local_tools + doc_tools + codegraph_tools
            print(f"  [LocalDeveloperAgent] {len(local_tools)} local + {len(doc_tools)} doc + {len(codegraph_tools)} codegraph tools loaded.")
            agent_executor = create_agent(self.llm, combined_tools)

            start_time = time.time()
            result = await agent_executor.ainvoke({"messages": [("user", system_prompt)]})

            for msg in result.get("messages", []):
                if msg.type == "ai" and getattr(msg, "tool_calls", None):
                    for tc in msg.tool_calls:
                        print(f"    -> [Debug] LLM called tool '{tc['name']}' with args: {str(tc['args'])[:200]}")
                elif msg.type == "tool":
                    print(f"    <- [Debug] Tool '{msg.name}' returned: {str(msg.content)[:300]}")

            elapsed = time.time() - start_time
            print(f"  [LocalDeveloperAgent] ReAct loop finished in {elapsed:.2f} seconds")

        content_raw = result["messages"][-1].content
        if isinstance(content_raw, list):
            content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content_raw])
        else:
            content = str(content_raw)

        print(f"  [LocalDeveloperAgent] Final LLM message:\n{content}")

        # Only report files that still exist and are real files (defensive:
        # the LLM could in theory pass a directory or a since-deleted path).
        code_files = [f for f in touched_files if os.path.isfile(f)]
        print(f"  [LocalDeveloperAgent] Touched {len(code_files)} file(s): {code_files}")

        return {
            "status": "success",
            "branch": branch_name,
            "code_files": code_files,
            "message": f"Local implementation finished: {content[:100]}..."
        }

    async def implement_pr_recommendations(self, story_details: dict, branch_name: str, workspace_path: str) -> dict:
        title = story_details.get('title')
        description = story_details.get('description', '')

        print(f"  [LocalDeveloperAgent] Starting local PR recommendations flow for: {title}")

        system_prompt = f"""You are a Local Developer Agent.
Your workspace is located at: {workspace_path}
You are working on the EXISTING branch '{branch_name}' which is already checked out.
You have access to local file tools AND Context7 Documentation tools.
If you need technical documentation to solve the task, use the context7 tools.
Your task:
1. List/read the relevant files in the workspace.
2. Modify the code to implement the requested PR recommendations: {description}.
3. Commit all changes and push them directly to the existing branch '{branch_name}'.

ALWAYS use absolute paths for file operations, built by joining {workspace_path} with a path you obtained from local_list_files or local_read_file output. NEVER guess a path or construct one using '..' relative traversal — if you are unsure a path exists, call local_list_files on its parent directory first.
"""
        from tools.caveman_prompt import wrap_with_caveman
        system_prompt = wrap_with_caveman(system_prompt)

        touched_files = []
        local_tools = self._build_local_tools(touched_files)

        import time
        async with load_context7_mcp_tools() as doc_tools, load_codegraph_mcp_tools() as codegraph_tools:
            combined_tools = local_tools + doc_tools + codegraph_tools
            print(f"  [LocalDeveloperAgent] {len(local_tools)} local + {len(doc_tools)} doc + {len(codegraph_tools)} codegraph tools loaded.")
            agent_executor = create_agent(self.llm, combined_tools)

            start_time = time.time()
            result = await agent_executor.ainvoke({"messages": [("user", system_prompt)]})

            for msg in result.get("messages", []):
                if msg.type == "ai" and getattr(msg, "tool_calls", None):
                    for tc in msg.tool_calls:
                        print(f"    -> [Debug] LLM called tool '{tc['name']}' with args: {str(tc['args'])[:200]}")
                elif msg.type == "tool":
                    print(f"    <- [Debug] Tool '{msg.name}' returned: {str(msg.content)[:300]}")

            elapsed = time.time() - start_time
            print(f"  [LocalDeveloperAgent] ReAct loop finished in {elapsed:.2f} seconds")

        content_raw = result["messages"][-1].content
        if isinstance(content_raw, list):
            content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content_raw])
        else:
            content = str(content_raw)

        print(f"  [LocalDeveloperAgent] Final LLM message:\n{content}")

        code_files = [f for f in touched_files if os.path.isfile(f)]
        print(f"  [LocalDeveloperAgent] Touched {len(code_files)} file(s): {code_files}")

        return {
            "status": "success",
            "branch": branch_name,
            "code_files": code_files,
            "message": f"Local PR recommendations implementation finished: {content[:100]}..."
        }

    async def fix_failing_tests(
        self,
        story_details: dict,
        workspace_path: str,
        branch_name: str,
        test_command: str,
        test_output: str,
        previous_files: list = None,
    ) -> dict:
        """
        Called by the Supervisor's test/fix loop when TesterAgent reports a
        failure. Gives the coding agent the real failure output and asks it
        to patch the code (not the tests) and push the fix to the same branch.
        """
        title = story_details.get('title')
        print(f"  [LocalDeveloperAgent] Attempting to fix failing tests for: {title}")

        previous_files = previous_files or []
        file_hint = "\n".join(f"- {f}" for f in previous_files) or "(none recorded)"

        system_prompt = f"""You are a Local Developer Agent fixing a failing test suite.
Your workspace is located at: {workspace_path}
You are working on the EXISTING branch '{branch_name}' which is already checked out.
You have access to local file tools AND Context7 Documentation tools.

The project's test suite was run with: `{test_command}`
It FAILED with this output:
```
{test_output[:4000]}
```

Files previously modified for this task (may or may not be the cause):
{file_hint}

Your task:
1. Read the relevant file(s) — especially any referenced in the error output/stack trace above.
2. Diagnose the root cause of the failure.
3. Fix the code so the test suite passes. Do NOT modify the test files themselves unless they are clearly wrong.
4. Commit and push your fix to the existing branch '{branch_name}'.

ALWAYS use absolute paths for file operations, built by joining {workspace_path} with a path you obtained from local_list_files or local_read_file output. NEVER guess a path or construct one using '..' relative traversal — if you are unsure a path exists, call local_list_files on its parent directory first.
"""

        touched_files = list(previous_files)
        local_tools = self._build_local_tools(touched_files)

        async with load_context7_mcp_tools() as doc_tools:
            combined_tools = local_tools + doc_tools
            print(f"  [LocalDeveloperAgent] {len(local_tools)} local tools + {len(doc_tools)} doc tools loaded.")
            agent_executor = create_agent(self.llm, combined_tools)

            result = await agent_executor.ainvoke({"messages": [("user", system_prompt)]})

            for msg in result.get("messages", []):
                if msg.type == "ai" and getattr(msg, "tool_calls", None):
                    for tc in msg.tool_calls:
                        print(f"    -> [Debug] LLM called tool '{tc['name']}' with args: {str(tc['args'])[:200]}")
                elif msg.type == "tool":
                    print(f"    <- [Debug] Tool '{msg.name}' returned: {str(msg.content)[:300]}")

        content_raw = result["messages"][-1].content
        if isinstance(content_raw, list):
            content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content_raw])
        else:
            content = str(content_raw)

        print(f"  [LocalDeveloperAgent] Fix attempt result:\n{content}")

        code_files = [f for f in touched_files if os.path.isfile(f)]
        return {
            "status": "success",
            "branch": branch_name,
            "code_files": code_files,
            "message": f"Fix attempt finished: {content[:100]}..."
        }