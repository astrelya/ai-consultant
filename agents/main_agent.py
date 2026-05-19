"""
Main Supervisor Agent Module
This agent leverages sub-agents to complete the software development lifecycle tasks based on User Stories.
"""
import asyncio
from typing import List, Dict
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent

from agents.local_developer_agent import LocalDeveloperAgent
from agents.developer_agent import RemoteDeveloperAgent
from agents.tester_agent import TesterAgent
from agents.environment_agent import EnvironmentAgent
from tools.ticket_manager import TicketManager
from tools.mcp_loader import MCPManager

import os

class SupervisorAgent:
    def __init__(self):
        self.remote_developer = RemoteDeveloperAgent()
        self.local_developer = LocalDeveloperAgent()
        self.tester = TesterAgent()
        self.environment = EnvironmentAgent()
        self.ticket_manager = TicketManager()
        
        # Memory and Configuration
        self.mode = os.environ.get("AGENT_MODE", "remote")
        self.chat_history = []  # Maintain conversation state
        
        # Initialize Gemini for true LLM-based routing
        model_name = os.environ.get("TICKET_MODEL", "gemini-2.5-flash")
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    async def run(self, issue_identifier: str):
        print(f"[Supervisor] Fetching ticket details for {issue_identifier}...")
        
        # 1. Fetch User Story
        story_details = await self.ticket_manager.get_ticket_details(issue_identifier)
        if not story_details:
            return f"Failed to retrieve ticket {issue_identifier}"
            
        print(f"[Supervisor] Analyzing User Story: {story_details.get('title')}")
        
        # 2. Delegate to Environment Agent to setup workspace
        print("[Supervisor] Delegating to Environment Agent...")
        env_result = self.environment.prepare_environment(story_details)
        print(f"[Supervisor] Environment setup finished with status: {env_result.get('status')}")
        
        if env_result.get('status') != 'success':
            return "Environment preparation failed."
            
        workspace_path = env_result.get('workspace_path')
        
        # 3. Delegate to Developer Agent based on mode
        print(f"[Supervisor] Delegating to {self.mode.capitalize()} Developer Agent...")
        if self.mode == "local":
            dev_result = await self.local_developer.implement_feature(story_details, workspace_path)
        else:
            dev_result = await self.remote_developer.implement_feature(story_details, workspace_path)
            
        print(f"[Supervisor] Developer finished with status: {dev_result.get('status')}")
        
        if dev_result.get('status') != 'success':
            return "Development phase failed."

        # 4. Delegate to Tester Agent for Unit Tests
        print("[Supervisor] Delegating to Tester Agent...")
        test_result = self.tester.write_and_run_tests(story_details, dev_result.get('code_files', []), workspace_path)
        print(f"[Supervisor] Tester finished with status: {test_result.get('status')}")
        
        # 5. Final synthesis and output
        return {
            "status": "completed",
            "issue": issue_identifier,
            "development": dev_result,
            "testing": test_result
        }

    async def process_chat(self, user_command: str) -> str:
        """
        Uses an LLM and LangGraph ReAct agent to route user intents interactively.
        """
        # Define the tools available to the Supervisor LLM
        async def fetch_tickets(status_filter: str = None) -> str:
            """Fetches active tickets/projects. You can optionally provide a status_filter like 'TODO', 'In Progress', or 'Done' to only get tickets in that status."""
            tickets = await self.ticket_manager.get_todo_tickets(status_filter)
            if not tickets:
                return f"There are no tickets matching the criteria right now."
            response = f"Tickets (Filter: {status_filter or 'None'}):\n"
            for t in tickets:
                status_str = f" [{t.get('status', 'Open')}]"
                response += f"- {t['id']}: {t['title']}{status_str}\n"
            return response

        async def implement_ticket(ticket_id: str) -> str:
            """Triggers the AI development workflow to build/fix a ticket. Requires a ticket_id like 'PROJ-101'."""
            result = await self.run(ticket_id)
            if isinstance(result, str):
                return result # Error message
            
            summary = f"Implementation complete! Strategy: {self.mode}. "
            if 'branch' in result['development']:
                summary += f"Branch: {result['development']['branch']}. "
            return summary + f"Test coverage: {result['testing'].get('coverage', 'N/A')}."

        async def set_mode(mode: str) -> str:
            """Allows the user to switch between 'local' and 'remote' development modes."""
            if mode.lower() not in ["local", "remote"]:
                return "Invalid mode. Please choose 'local' or 'remote'."
            self.mode = mode.lower()
            return f"Developer mode successfully set to {self.mode}."

        # Load interactive tools + Documentation tools for the chat session
        manager = await MCPManager.get_instance()
        
        supervisor_tools = [
            StructuredTool.from_function(coroutine=fetch_tickets, name="FetchTickets", description="Lists available tickets. Can optionally filter by status (e.g. 'TODO')."),
            StructuredTool.from_function(coroutine=implement_ticket, name="ImplementTicket", description="Develops and implements a specific ticket ID."),
            StructuredTool.from_function(coroutine=set_mode, name="SetDeveloperMode", description="Changes implementation strategy between 'local' and 'remote'.")
        ] + manager.doc_tools
        
        # Create an intelligent routing agent bound with the tools
        router_agent = create_react_agent(self.llm, supervisor_tools)
        
        # Prepare messages including history
        messages = [("system", "You are the orchestrating supervisor. You have access to project management, code implementation, and technical documentation tools (Context7). If a user asks a technical question about a library like Javelit, use Context7 to find the answer.")]
        messages.extend(self.chat_history)
        messages.append(("user", user_command))
        
        # Execute the routing agent
        result = await router_agent.ainvoke({"messages": messages})
        
        # Parse output
        content_raw = result["messages"][-1].content
        if isinstance(content_raw, list):
            final_response = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content_raw])
        else:
            final_response = str(content_raw)

        # Update Memory
        self.chat_history.append(("user", user_command))
        self.chat_history.append(("assistant", final_response))
        
        # Keep history manageable (last 10 turns)
        if len(self.chat_history) > 20: 
            self.chat_history = self.chat_history[-20:]
            
        return final_response
