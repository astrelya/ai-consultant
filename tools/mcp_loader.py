import contextlib
from typing import AsyncGenerator, List
from langchain_core.tools import BaseTool
from tools.github_mcp import load_github_mcp_tools
from tools.context7_mcp import load_context7_mcp_tools

@contextlib.asynccontextmanager
async def load_dev_tools() -> AsyncGenerator[List[BaseTool], None]:
    """
    Combines GitHub (remote) and Context7 (documentation) tools into a single context manager.
    """
    async with load_github_mcp_tools() as github_tools:
        async with load_context7_mcp_tools() as doc_tools:
            # Combine both lists of tools
            combined_tools = []
            combined_tools.extend(github_tools)
            combined_tools.extend(doc_tools)
            yield combined_tools
