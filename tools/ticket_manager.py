"""
Ticket Manager Tool
Interacts with GitHub or Jira via MCP to fetch User Stories/Issues.
"""
import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from tools.mcp_loader import MCPManager

class TicketManager:
    def __init__(self):
        # We use the LLM to interpret standard natural language fetches against the MCP tool schemas
        model_name = os.environ.get("TICKET_MODEL", "gemini-2.5-flash")
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)
        # Default to jira, can be set to 'github' or 'jira'
        self.system = os.environ.get("TICKET_SYSTEM", "jira").lower()
        
    async def get_ticket_details(self, issue_identifier: str) -> dict:
        if self.system == "github":
            return await self._get_github_ticket_details(issue_identifier)
        else:
            return await self._get_jira_ticket_details(issue_identifier)
            
    async def _get_github_ticket_details(self, issue_identifier: str) -> dict:
        print(f"  [TicketManager] Querying GitHub MCP for issue {issue_identifier}...")
        owner_name = os.environ.get("GITHUB_OWNER", "your-github-username")
        
        system_prompt = f"""
        You are a helpful assistant with access to GitHub MCP tools.
        Extract the details for the GitHub issue using the identifier '{issue_identifier}'. This issue sits within the organization/user scope '{owner_name}'.
        If the identifier includes a repository name, ensure you use the correct repository parameter when fetching the issue.
        Return the result EXACTLY as a raw JSON string (no markdown blocks, just raw JSON) matching this schema:
        {{
            "id": "PROJ-123",
            "title": "Title of the issue",
            "description": "Body/description of the issue",
            "status": "TODO",
            "acceptance_criteria": []
        }}
        """
        manager = await MCPManager.get_instance()
        return await self._run_agent(manager.github_tools, system_prompt, issue_identifier)
            
    async def _get_jira_ticket_details(self, issue_identifier: str) -> dict:
        print(f"  [TicketManager] Querying Jira MCP for issue {issue_identifier}...")
        
        system_prompt = f"""
        You are a helpful assistant with access to Jira MCP tools.
        Extract the details for the Jira issue using the issue key/identifier '{issue_identifier}'.
        
        CRITICAL: When using the Jira MCP tool to fetch the issue, you MUST use the 'fields' parameter to limit the response to ONLY what is necessary (e.g., 'summary,description,status'). Otherwise, the payload is too large and takes too long to process.
        
        Return the result EXACTLY as a raw JSON string (no markdown blocks, just raw JSON) matching this schema:
        {{
            "id": "PROJ-123",
            "title": "Title of the issue",
            "description": "Body/description of the issue",
            "status": "TODO",
            "acceptance_criteria": []
        }}
        """
        manager = await MCPManager.get_instance()
        return await self._run_agent(manager.jira_tools, system_prompt, issue_identifier)

    async def _run_agent(self, tools, system_prompt, issue_identifier):
        import time
        start_time = time.time()
        print(f"  [TicketManager] Agent started at {time.strftime('%H:%M:%S')}")
        
        agent_executor = create_react_agent(self.llm, tools)
        result = await agent_executor.ainvoke({"messages": [("user", system_prompt)]})
        
        for msg in result.get("messages", []):
            if msg.type == "ai" and getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    print(f"    -> [Debug] LLM called tool '{tc['name']}' with args: {tc['args']}")
            elif msg.type == "tool":
                print(f"    <- [Debug] Tool '{msg.name}' returned {len(str(msg.content))} characters.")
                
        elapsed = time.time() - start_time
        print(f"  [TicketManager] Agent finished in {elapsed:.2f} seconds")
        
        content_raw = result["messages"][-1].content
        if isinstance(content_raw, list):
            content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content_raw])
        else:
            content = str(content_raw)
        content = content.strip()
        
        # Simple cleanup in case the LLM returned markdown blocks
        if content.startswith("```json"):
            content = content[7:-3].strip()
        if content.startswith("```"):
            content = content[3:-3].strip()
            
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            print("  [TicketManager] Failed to decode LLM response into JSON.")
            return {
                "id": issue_identifier,
                "title": f"Mock Title due to {self.system.title()} API failure",
                "description": "Mocked description.",
                "status": "TODO",
                "acceptance_criteria": ["Mock AC"]
            }

    async def get_todo_tickets(self, status_filter: str = None) -> list:
        if self.system == "github":
            return await self._get_github_todo_tickets(status_filter)
        else:
            return await self._get_jira_todo_tickets(status_filter)
            
    async def _get_github_todo_tickets(self, status_filter: str = None) -> list:
        print("  [TicketManager] Fetching all tickets using GitHub MCP...")
        owner_name = os.environ.get("GITHUB_OWNER", "your-github-username")
        
        filter_instruction = f"The user has provided a status filter: '{status_filter}'. If it is a generic word like 'open' or 'active', DO NOT filter tightly. Otherwise, ONLY return tickets matching this state." if status_filter else "DO NOT filter out 'In Progress' issues."
        
        system_prompt = f"""
        You are a helpful assistant with access to GitHub MCP tools.
        I want to find active issues that are ready to be worked on or currently being worked on (e.g., TODO, Open, In Progress) across the entire scope '{owner_name}'. 
        
        {filter_instruction}
        
        Since we use GitHub Projects V2, you should:
        1. Use the 'projects_list' tool with method='list_projects' and owner='{owner_name}' to find the relevant Project boards.
        2. Use the 'projects_list' tool with method='list_project_items' (and the appropriate project_number) to list the tasks/issues.
        
        Extract the matching tickets. Return the result EXACTLY as a raw JSON list (no markdown blocks) containing objects with 'id' (which MUST include the repository name or full URL so it can be identified later), 'title', and 'status'.
        Example:
        [
            {{"id": "repo-name#1", "title": "Setup CI/CD", "status": "To Do"}},
            {{"id": "repo-name#2", "title": "Add User Authentication", "status": "In Progress"}}
        ]
        If you cannot find any, return:
        [
            {{"id": "MOCK-1", "title": "Mock Issue (GitHub Context Not Set up)", "status": "To Do"}}
        ]
        """
        
        manager = await MCPManager.get_instance()
        return await self._run_agent_list(manager.github_tools, system_prompt)
            
    async def _get_jira_todo_tickets(self, status_filter: str = None) -> list:
        print("  [TicketManager] Fetching all tickets using Jira MCP...")
        
        filter_instruction = f"The user has provided a status filter: '{status_filter}'. If it means 'todo' or 'to do', map it to `status = \"To Do\"`. If it means 'in progress', map to `status = \"In Progress\"`. If it is generic like 'open' or 'all', use `statusCategory != Done`." if status_filter else "DO NOT filter out 'In Progress' tickets."
        
        system_prompt = f"""
        You are a helpful assistant with access to Jira MCP tools.
        I want to find active Jira issues (tickets) in the project. This includes issues in ANY open state (e.g., "To Do", "In Progress", "In Review"). 
        
        {filter_instruction}
        
        Use the appropriate Jira search/JQL tools provided by the MCP server to find these issues.
        IMPORTANT: Jira status names are case-sensitive and typically include spaces (e.g., "To Do", not "TODO").
        
        CRITICAL: When using the Jira search/JQL tool, you MUST use the 'fields' parameter to limit the response to ONLY 'summary,status', AND you MUST use the 'maxResults' parameter set to 15 to strictly limit the number of tickets returned. If you request all fields or too many results, the response payload will be massive and cause severe performance degradation (taking over 2 minutes).
        
        Extract the matching tickets. Return the result EXACTLY as a raw JSON list (no markdown blocks) containing objects with 'id' (the Jira issue key), 'title', and 'status' (the actual string status).
        Example:
        [
            {{"id": "PROJ-101", "title": "Setup CI/CD", "status": "To Do"}},
            {{"id": "PROJ-102", "title": "Add User Authentication", "status": "In Progress"}}
        ]
        If you cannot find any, return:
        [
            {{"id": "MOCK-1", "title": "Mock Issue (Jira Context Not Set up)", "status": "To Do"}}
        ]
        """
        
        manager = await MCPManager.get_instance()
        return await self._run_agent_list(manager.jira_tools, system_prompt)

    async def _run_agent_list(self, tools, system_prompt):
        import time
        start_time = time.time()
        print(f"  [TicketManager] Agent started at {time.strftime('%H:%M:%S')}")
        
        agent_executor = create_react_agent(self.llm, tools)
        result = await agent_executor.ainvoke({"messages": [("user", system_prompt)]})
        
        for msg in result.get("messages", []):
            if msg.type == "ai" and getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    print(f"    -> [Debug] LLM called tool '{tc['name']}' with args: {tc['args']}")
            elif msg.type == "tool":
                print(f"    <- [Debug] Tool '{msg.name}' returned {len(str(msg.content))} characters.")
                
        elapsed = time.time() - start_time
        print(f"  [TicketManager] Agent finished in {elapsed:.2f} seconds")
        
        content_raw = result["messages"][-1].content
        if isinstance(content_raw, list):
            content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content_raw])
        else:
            content = str(content_raw)
        content = content.strip()
        
        if content.startswith("```json"):
            content = content[7:-3].strip()
        if content.startswith("```"):
            content = content[3:-3].strip()
            
        try:
            tickets = json.loads(content)
            if isinstance(tickets, list):
                return tickets
            return [tickets]
        except json.JSONDecodeError:
            print("  [TicketManager] Failed to decode LLM response into JSON.")
            return [
                {"id": "PROJ-101", "title": "Setup CI/CD"},
                {"id": "PROJ-123", "title": "Add User Authentication"},
                {"id": "PROJ-105", "title": "Create User API endpoints"}
            ]
