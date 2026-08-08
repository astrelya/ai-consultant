import contextlib
import traceback
from typing import AsyncGenerator, List
from langchain_core.tools import BaseTool
from contextlib import AsyncExitStack

from tools.github_mcp import load_github_mcp_tools
from tools.context7_mcp import load_context7_mcp_tools
from tools.jira_mcp import load_jira_mcp_tools
import os


def _apply_gemini_enum_fix() -> None:
    """
    One-time monkey-patch: Gemini requires enum values to be strings.
    Some MCP servers (e.g. GitHub MCP) emit boolean values in enums
    which fail Pydantic validation inside langchain_google_genai.
    """
    try:
        import langchain_google_genai._function_utils as _fu
        _orig = _fu._dict_to_genai_schema

        def _fixed(d: dict, **kwargs) -> object:
            if isinstance(d, dict) and "enum" in d:
                d = {**d, "enum": [str(v) if not isinstance(v, str) else v for v in d["enum"]]}
            return _orig(d, **kwargs)

        _fu._dict_to_genai_schema = _fixed
    except Exception as e:
        print(f"  [MCPManager] WARNING: Could not apply Gemini schema fix: {e}")


_apply_gemini_enum_fix()

def _log_exception(label: str, e: BaseException, indent: str = "  ") -> None:
    """Logs an exception with full traceback, unpacking ExceptionGroup sub-exceptions."""
    print(f"{indent}[MCPManager] ERROR in {label}: {type(e).__name__}: {e}")
    if isinstance(e, BaseExceptionGroup):
        for i, sub in enumerate(e.exceptions, 1):
            print(f"{indent}[MCPManager]   sub-exception {i}/{len(e.exceptions)}:")
            _log_exception(label, sub, indent + "    ")
    else:
        tb = traceback.format_exception(type(e), e, e.__traceback__)
        for line in "".join(tb).splitlines():
            print(f"{indent}  {line}")

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
            print(f"  [MCPManager] GitHub MCP loaded ({len(self.github_tools)} tools)")
        except BaseException as e:
            print(f"  [MCPManager] Failed to load GitHub MCP: {type(e).__name__}: {e}")
            _log_exception("GitHub MCP", e)
            
        # 2. Jira is loaded conditionally for tickets
        if system == "jira":
            try:
                print("  [MCPManager] -> Starting Jira MCP proxy...")
                self.jira_tools = await self.stack.enter_async_context(load_jira_mcp_tools())
                print(f"  [MCPManager] Jira MCP loaded ({len(self.jira_tools)} tools)")
            except BaseException as e:
                print(f"  [MCPManager] Failed to load Jira MCP: {type(e).__name__}: {e}")
                _log_exception("Jira MCP", e)
            
        # 3. Context7 is ALWAYS needed for documentation
        try:
            print("  [MCPManager] -> Starting Context7 MCP proxy...")
            self.doc_tools = await self.stack.enter_async_context(load_context7_mcp_tools())
            print(f"  [MCPManager] Context7 MCP loaded ({len(self.doc_tools)} tools)")
        except BaseException as e:
            print(f"  [MCPManager] Failed to load Context7 MCP: {type(e).__name__}: {e}")
            _log_exception("Context7 MCP", e)
            
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
