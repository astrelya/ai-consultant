import asyncio
import sys
import os
import logging
import warnings

warnings.filterwarnings("ignore")
logging.getLogger("langchain_core").setLevel(logging.ERROR)
logging.getLogger("langchain_mcp_adapters").setLevel(logging.ERROR)

# Add the current directory to sys.path so we can import from tools
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tools.jira_mcp import load_jira_mcp_tools

async def main():
    print("Starting Jira MCP connection test...")
    try:
        async with load_jira_mcp_tools() as tools:
            print("\n[SUCCESS] Successfully connected to the Jira MCP Server!")
            print(f"Loaded {len(tools)} tools.\n")
            
            print("Available Tools:")
            for tool in tools:
                print(f" - {tool.name}")
                print(f"    {tool.description[:120]}...\n")
                
    except Exception as e:
        print(f"\n[ERROR] Error connecting to Jira MCP Server:")
        print(e)

if __name__ == "__main__":
    asyncio.run(main())
