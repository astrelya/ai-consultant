import os
import contextlib
from typing import AsyncGenerator, List
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_core.tools import BaseTool

@contextlib.asynccontextmanager
async def load_context7_mcp_tools() -> AsyncGenerator[List[BaseTool], None]:
    """
    Connects to the Context7 MCP Server (Upstash) via stdio and returns LangChain compatible tools.
    Used for retrieving documentation and technical context during development.
    """
    api_key = os.environ.get("CONTEXT7_API_KEY")
    if not api_key:
        # If no API key is set, we return an empty list to avoid crashing the agent, 
        # but we print a warning.
        print("  [Context7] WARNING: CONTEXT7_API_KEY is not set. Documentation tools will be unavailable.")
        yield []
        return

    # Using the official npx package for context7 mcp
    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@upstash/context7-mcp"],
        env={"CONTEXT7_API_KEY": api_key, "PATH": os.environ.get("PATH", "")}
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await load_mcp_tools(session)
                yield tools
    except Exception as e:
        print(f"  [Context7] Failed to load tools: {e}")
        yield []
