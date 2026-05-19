import contextlib
from typing import AsyncGenerator, List
from langchain_core.tools import BaseTool
from contextlib import AsyncExitStack

from tools.github_mcp import load_github_mcp_tools
from tools.context7_mcp import load_context7_mcp_tools
from tools.jira_mcp import load_jira_mcp_tools
import os

class MCPManager:
    _instance = None
    
    def __init__(self):
        self.stack = AsyncExitStack()
        self.github_tools = []
        self.doc_tools = []
        self.jira_tools = []
        
    @classmethod
    async def get_instance(cls):
        if cls._instance is None:
            cls._instance = MCPManager()
            await cls._instance.initialize()
        return cls._instance
        
    async def initialize(self):
        print("\n  [MCPManager] Starting up MCP servers (this only happens once)...")
        system = os.environ.get("TICKET_SYSTEM", "jira").lower()
        
        # 1. GitHub is ALWAYS needed for code/repo operations
        try:
            print("  [MCPManager] -> Starting GitHub MCP proxy...")
            self.github_tools = await self.stack.enter_async_context(load_github_mcp_tools())
        except Exception as e:
            print(f"  [MCPManager] Failed to load GitHub MCP: {e}")
            
        # 2. Jira is loaded conditionally for tickets
        if system == "jira":
            try:
                print("  [MCPManager] -> Starting Jira MCP proxy...")
                self.jira_tools = await self.stack.enter_async_context(load_jira_mcp_tools())
            except Exception as e:
                print(f"  [MCPManager] Failed to load Jira MCP: {e}")
            
        # 3. Context7 is ALWAYS needed for documentation
        try:
            print("  [MCPManager] -> Starting Context7 MCP proxy...")
            self.doc_tools = await self.stack.enter_async_context(load_context7_mcp_tools())
        except Exception as e:
            print(f"  [MCPManager] Failed to load Context7 MCP: {e}")
            
        print("  [MCPManager] Ready!\n")

    async def close(self):
        await self.stack.aclose()

@contextlib.asynccontextmanager
async def load_dev_tools() -> AsyncGenerator[List[BaseTool], None]:
    manager = await MCPManager.get_instance()
    combined_tools = []
    combined_tools.extend(manager.github_tools)
    combined_tools.extend(manager.doc_tools)
    combined_tools.extend(manager.jira_tools)
    yield combined_tools
