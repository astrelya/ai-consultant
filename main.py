import os
import asyncio
from dotenv import load_dotenv
from agents.main_agent import SupervisorAgent
import logging
import warnings

# Suppress LangChain verbose schema warnings for MCP tool translation
warnings.filterwarnings("ignore")
logging.getLogger("langchain_core").setLevel(logging.ERROR)
logging.getLogger("langchain_mcp_adapters").setLevel(logging.ERROR)
logging.getLogger("langchain_google_genai").setLevel(logging.ERROR)
logging.getLogger("langgraph").setLevel(logging.ERROR)
# Load environment variables, e.g., API keys for LLM, Jira, GitHub
load_dotenv()

from tools.mcp_loader import MCPManager

async def main():
    print("=====================================================")
    print("  Welcome to the AI Consultant Agentic Chat Interface")
    print("=====================================================")
    
    manager = await MCPManager.get_instance()
    
    print("You can ask me to list TODO tickets, or to implement a specific ticket.")
    print("Type 'exit' or 'quit' to close the application.\n")
    
    try:
        # Initialize the main supervisor agent
        supervisor = SupervisorAgent()
        
        while True:
            try:
                user_input = input("\n[You]: ")
                if user_input.strip().lower() in ['exit', 'quit']:
                    print("[Agent]: Goodbye!")
                    break
                
                if not user_input.strip():
                    continue
                    
                # Route the user input to the supervisor (Now Async)
                response = await supervisor.process_chat(user_input)
                print(f"\n[Agent]:\n{response}")
                
            except KeyboardInterrupt:
                print("\n[Agent]: Goodbye!")
                break
    finally:
        await manager.close()

if __name__ == "__main__":
    asyncio.run(main())
