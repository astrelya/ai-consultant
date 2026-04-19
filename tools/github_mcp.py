import os
import contextlib
from typing import AsyncGenerator, List
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_core.tools import BaseTool

@contextlib.asynccontextmanager
async def load_github_mcp_tools() -> AsyncGenerator[List[BaseTool], None]:
    """
    Connects to the Github MCP Server via stdio and returns LangChain compatible tools 
    using the official langchain-mcp-adapters package.
    """
    github_token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", os.environ.get("GITHUB_TOKEN"))
    if not github_token:
        raise ValueError("GITHUB_PERSONAL_ACCESS_TOKEN is not set.")

    # Using the official Docker container maintained by GitHub natively
    server_params = StdioServerParameters(
        command="docker",
        args=["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "-e", "GITHUB_TOOLSETS", "ghcr.io/github/github-mcp-server"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": github_token, "GITHUB_TOOLSETS": "all", "PATH": os.environ.get("PATH", "")}
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            yield tools
