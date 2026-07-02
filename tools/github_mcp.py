import os
import subprocess
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
    print("  [GitHub MCP] Token found, checking docker availability...")

    import shutil
    docker_path = shutil.which("docker")
    if not docker_path:
        raise RuntimeError("'docker' command not found in PATH. Is Docker Desktop running?")
    print(f"  [GitHub MCP] Docker found at: {docker_path}")

    # Pre-flight: verify Docker daemon is reachable
    try:
        result = subprocess.run(
            [docker_path, "info"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Docker daemon not accessible (exit {result.returncode}):\n{result.stderr.strip()}"
            )
        print("  [GitHub MCP] Docker daemon is running.")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Docker daemon did not respond in 10s. Is Docker Desktop fully started?")

    # Using the official Docker container maintained by GitHub natively
    server_params = StdioServerParameters(
        command="docker",
        args=["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "-e", "GITHUB_TOOLSETS", "ghcr.io/github/github-mcp-server"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": github_token, "GITHUB_TOOLSETS": "all", "PATH": os.environ.get("PATH", "")}
    )
    print("  [GitHub MCP] Spawning docker container (stderr → console)...")

    # On Windows, CREATE_NO_WINDOW + sys.stderr breaks the subprocess pipe.
    # Use a real file descriptor (devnull) as errlog to avoid this.
    with open(os.devnull, "w") as devnull:
        async with stdio_client(server_params, errlog=devnull) as (read, write):
            print("  [GitHub MCP] stdio transport open, initializing session...")
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("  [GitHub MCP] Session initialized, loading tools...")
                tools = await load_mcp_tools(session)
                print(f"  [GitHub MCP] {len(tools)} tools loaded.")
                yield tools
