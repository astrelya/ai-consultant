import os
import contextlib
import shutil
from typing import AsyncGenerator, List
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_core.tools import BaseTool

@contextlib.asynccontextmanager
async def load_jira_mcp_tools() -> AsyncGenerator[List[BaseTool], None]:
    """
    Connects to the Atlassian Rovo (Jira/Confluence/Compass) MCP Server via stdio 
    and returns LangChain compatible tools.
    """
    # Use npx to run mcp-remote proxy as per Atlassian documentation
    npx_path = shutil.which("npx")
    if not npx_path:
        # Fallback for Windows if shutil.which fails to find it without .cmd
        npx_path = "npx.cmd" if os.name == "nt" else "npx"

    server_params = StdioServerParameters(
        command=npx_path,
        args=["-y", "mcp-remote@latest", "https://mcp.atlassian.com/v1/mcp/authv2"],
        env=os.environ.copy()
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            yield tools
