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
    npx_path = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx_path:
        # Fallback for Windows if shutil.which fails to find it without .cmd
        npx_path = "npx.cmd" if os.name == "nt" else "npx"
    print(f"  [Jira MCP] Using npx at: {npx_path}")

    server_params = StdioServerParameters(
        command=npx_path,
        args=["-y", "mcp-remote@latest", "https://mcp.atlassian.com/v1/mcp/authv2"],
        env=os.environ.copy()
    )
    print("  [Jira MCP] Spawning mcp-remote proxy (stderr → console)...")

    # On Windows, CREATE_NO_WINDOW + sys.stderr breaks the subprocess pipe.
    # Use a real file descriptor (devnull) as errlog to avoid this.
    with open(os.devnull, "w") as devnull:
        async with stdio_client(server_params, errlog=devnull) as (read, write):
            print("  [Jira MCP] stdio transport open, initializing session...")
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("  [Jira MCP] Session initialized, loading tools...")
                tools = await load_mcp_tools(session)
                print(f"  [Jira MCP] {len(tools)} tools loaded.")
                yield tools
