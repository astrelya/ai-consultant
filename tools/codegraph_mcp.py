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
async def load_codegraph_mcp_tools() -> AsyncGenerator[List[BaseTool], None]:
    """
    Connects to the Codegraph MCP Server (SQLite + tree-sitter semantic graph) via stdio
    and returns LangChain compatible tools.
    """
    npx_path = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx_path:
        npx_path = "npx.cmd" if os.name == "nt" else "npx"
        
    print(f"  [Codegraph] Spawning server via npx at: {npx_path}")
    
    # Run the codegraph MCP server package
    server_params = StdioServerParameters(
        command=npx_path,
        args=["-y", "@astudioplus/codegraph-mcp"],
        env=os.environ.copy()
    )

    try:
        # On Windows, stderr pipe could cause hang. Redirect it or ignore.
        with open(os.devnull, "w") as devnull:
            async with stdio_client(server_params, errlog=devnull) as (read, write):
                print("  [Codegraph] Connection open, initializing session...")
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await load_mcp_tools(session)
                    print(f"  [Codegraph] {len(tools)} tools loaded successfully.")
                    yield tools
    except Exception as e:
        print(f"  [Codegraph] Failed to load tools: {e}")
        yield []
