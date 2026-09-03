"""
Main Supervisor Agent Module
This agent leverages sub-agents to complete the software development lifecycle tasks based on User Stories.
"""
import asyncio
import re
import uuid
from typing import List, Dict
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent
from git import Repo

from agents.local_developer_agent import LocalDeveloperAgent
from agents.developer_agent import RemoteDeveloperAgent
from agents.tester_agent import TesterAgent
from agents.environment_agent import EnvironmentAgent
from agents import token_tracker
from agents.token_tracker import tracked_ainvoke
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
        # Story 6.1: lazily created per-instance chat session id for cost accumulation.
        self._chat_session_id: str | None = None
        
        # Initialize Gemini for true LLM-based routing
        model_name = os.environ.get("TICKET_MODEL", "gemini-2.5-flash")
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    async def run(self, issue_identifier: str):
        print(f"[Supervisor] Fetching ticket details for {issue_identifier}...")
        
        # 1. Fetch User Story
        story_details = await self.ticket_manager.get_ticket_details(issue_identifier)
        if not story_details:
            return f"Failed to retrieve ticket {issue_identifier}"
            
        # Transition to In Progress
        await self.ticket_manager.transition_ticket(issue_identifier, "In Progress")
            
        print(f"[Supervisor] Analyzing User Story: {story_details.get('title')}")
        
        # 2. Delegate to Environment Agent to setup workspace
        print("[Supervisor] Delegating to Environment Agent...")
        env_result = self.environment.prepare_environment(story_details)
        print(f"[Supervisor] Environment setup finished with status: {env_result.get('status')}")
        
        if env_result.get('status') != 'success':
            return "Environment preparation failed."
            
        workspace_path = env_result.get('workspace_path')
        story_details['repo_full_name'] = env_result.get('repo_full_name')
        
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
        test_result = await self.tester.write_and_run_tests(story_details, dev_result.get('code_files', []), workspace_path)
        print(f"[Supervisor] Tester finished with status: {test_result.get('status')}")
        print(f"  [TesterAgent] Test artifact: {test_result.get('test_artifact_ref')}")
        
        # Transition to In Review
        await self.ticket_manager.transition_ticket(issue_identifier, "In Review")
        
        # 5. Final synthesis and output
        return {
            "status": "completed",
            "issue": issue_identifier,
            "development": dev_result,
            "testing": test_result
        }

    def parse_pr_identifier(self, pr_url_or_number: str):
        """
        Parses PR URL or identifier into (owner, repo, pr_number).
        Supported formats:
        - https://github.com/owner/repo/pull/12
        - owner/repo#12
        - repo#12
        - 12
        """
        pr_url_or_number = pr_url_or_number.strip()
        
        # 1. Check URL
        url_match = re.search(r"github\.com/([\w\-]+)/([\w\-]+)/pull/(\d+)", pr_url_or_number)
        if url_match:
            return url_match.group(1), url_match.group(2), int(url_match.group(3))
            
        # 2. Check repo#number or owner/repo#number
        hash_match = re.search(r"(?:([\w\-]+)/)?([\w\-]+)#(\d+)", pr_url_or_number)
        if hash_match:
            owner = hash_match.group(1) or os.environ.get("GITHUB_OWNER", "astrelya")
            return owner, hash_match.group(2), int(hash_match.group(3))
            
        # 3. Check just a number
        number_match = re.match(r"^(\d+)$", pr_url_or_number)
        if number_match:
            owner = os.environ.get("GITHUB_OWNER", "astrelya")
            repo = os.environ.get("GITHUB_REPO", "appstrelya")
            return owner, repo, int(number_match.group(1))
            
        raise ValueError(f"Could not parse Pull Request identifier: {pr_url_or_number}. Please provide a full GitHub PR URL.")

    async def implement_pr_recommendations(self, pr_url_or_number: str) -> str:
        print(f"[Supervisor] Starting PR Review Correction flow for {pr_url_or_number}...")
        
        # 1. Parse PR Identifier
        try:
            owner, repo, pr_number = self.parse_pr_identifier(pr_url_or_number)
        except ValueError as e:
            return str(e)
            
        # 2. Fetch PR details using TicketManager
        pr_details = await self.ticket_manager.get_pr_details(owner, repo, pr_number)
        if not pr_details or "branch_name" not in pr_details:
            return f"Failed to retrieve PR details or branch name for PR #{pr_number}."
            
        recommendations = pr_details.get("recommendations", "Apply requested PR review edits.")
        print(f"[Supervisor] Retrieved recommendations for PR #{pr_number}: {recommendations}")
        
        # 3. Prepare workspace with EnvironmentAgent
        story_details = {
            "id": f"{repo}#{pr_number}",
            "title": f"Fix PR #{pr_number} Recommendations",
            "description": recommendations
        }
        env_result = self.environment.prepare_environment(story_details)
        if env_result.get("status") != "success":
            return "Environment preparation failed for PR review recommendations flow."
            
        workspace_path = env_result.get("workspace_path")
        story_details['repo_full_name'] = env_result.get('repo_full_name')
        branch_name = pr_details["branch_name"]
        
        # 4. Checkout the PR branch
        try:
            repo_obj = Repo(workspace_path)
            repo_obj.git.fetch("origin")
            repo_obj.git.checkout(branch_name)
            print(f"[Supervisor] Successfully checked out branch '{branch_name}'.")
        except Exception as e:
            try:
                repo_obj.git.checkout("-b", branch_name, f"origin/{branch_name}")
                print(f"[Supervisor] Successfully checked out and tracked branch '{branch_name}'.")
            except Exception as ex:
                return f"Could not checkout branch '{branch_name}': {ex}"
                
        # 5. Search for associated Jira ticket from branch name/recommendations to transition it
        ticket_id = None
        jira_pattern = re.compile(r"([A-Z]+-\d+)")
        match = jira_pattern.search(branch_name)
        if match:
            ticket_id = match.group(1)
        else:
            match = jira_pattern.search(recommendations)
            if match:
                ticket_id = match.group(1)
                
        if ticket_id:
            print(f"[Supervisor] Found associated Jira ticket {ticket_id}. Transitioning to In Progress...")
            await self.ticket_manager.transition_ticket(ticket_id, "In Progress")
            
        # 6. Delegate to Developer Agent based on mode
        print(f"[Supervisor] Delegating to {self.mode.capitalize()} Developer Agent for PR recommendations...")
        if self.mode == "local":
            dev_result = await self.local_developer.implement_pr_recommendations(
                story_details, branch_name, workspace_path
            )
        else:
            dev_result = await self.remote_developer.implement_pr_recommendations(
                story_details, branch_name, workspace_path
            )
            
        print(f"[Supervisor] Developer finished with status: {dev_result.get('status')}")
        if dev_result.get("status") != "success":
            return "PR recommendations development phase failed."
            
        # 7. Run/write tests
        print("[Supervisor] Delegating to Tester Agent...")
        test_result = await self.tester.write_and_run_tests(story_details, dev_result.get('code_files', []), workspace_path)
        print(f"[Supervisor] Tester finished with status: {test_result.get('status')}")
        print(f"  [TesterAgent] Test artifact: {test_result.get('test_artifact_ref')}")
        
        # 8. Transition Jira ticket to In Review
        if ticket_id:
            print(f"[Supervisor] Transitioning Jira ticket {ticket_id} to In Review...")
            await self.ticket_manager.transition_ticket(ticket_id, "In Review")
            
        # 9. Return summary
        summary = f"PR Recommendations fix applied successfully! Strategy: {self.mode}. "
        summary += f"Branch '{branch_name}' updated and pushed. "
        return summary + f"Test coverage: {test_result.get('coverage', 'N/A')}."

    async def process_chat(self, user_command: str, project_id: str | None = None) -> str:
        """
        Uses an LLM and LangGraph ReAct agent to route user intents interactively.
        """
        # Story 6.1: wire ContextVars for token tracking. When called from the CLI
        # without a project_id there is no ledger to update — record_llm_call will
        # short-circuit on the empty ContextVar and skip persistence.
        if project_id is not None:
            token_tracker.CURRENT_PROJECT_ID.set(project_id)
        if self._chat_session_id is None:
            self._chat_session_id = str(uuid.uuid4())
            token_tracker.reset_session(self._chat_session_id)
        token_tracker.CURRENT_SESSION_ID.set(self._chat_session_id)

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
            pr_url = result['development'].get('pr_url')
            if pr_url:
                summary += f"PR URL: {pr_url}. "
            return summary + f"Test coverage: {result['testing'].get('coverage', 'N/A')}."

        async def fix_pr(pr_url_or_number: str) -> str:
            """Triggers the PR review correction workflow. Fetches PR comments, checks out the PR branch, implements recommendations, runs tests, and pushes updates. Requires a PR URL or ID."""
            result = await self.implement_pr_recommendations(pr_url_or_number)
            return result

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
            StructuredTool.from_function(coroutine=fix_pr, name="ImplementPRRecommendations", description="Reviews a GitHub Pull Request by fetching comments, making requested code edits, running tests, and pushing updates directly to the PR branch."),
            StructuredTool.from_function(coroutine=set_mode, name="SetDeveloperMode", description="Changes implementation strategy between 'local' and 'remote'.")
        ] + manager.doc_tools
        
        # Create an intelligent routing agent bound with the tools
        router_agent = create_react_agent(self.llm, supervisor_tools)
        
        # Prepare messages including history
        messages = [("system", "You are the orchestrating supervisor. You have access to project management, code implementation, and technical documentation tools (Context7). If a user asks a technical question about a library like Javelit, use Context7 to find the answer.")]
        messages.extend(self.chat_history)
        messages.append(("user", user_command))
        
        # Execute the routing agent
        result = await tracked_ainvoke(router_agent, {"messages": messages})
        
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
