"""
Ticket Manager Tool
Interacts with GitHub via MCP to fetch User Stories/Issues.

NOTE ON JIRA INTEGRATION:
If you decide to migrate back to Jira instead of GitHub Issues:
1. Ensure you have the Jira MCP server available (e.g., via docker `mcp/jira` or equivalent node package).
2. Create a `load_jira_mcp_tools` context manager similarly to `load_github_mcp_tools`.
3. Swap the `load_github_mcp_tools` out for the Jira one here, and update the LLM prompt inside
   these functions to ask the agent to query "Jira sprint tasks" instead of "GitHub issues".
"""
import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from tools.github_mcp import load_github_mcp_tools

class TicketManager:
    def __init__(self):
        # We use the LLM to interpret standard natural language fetches against the MCP tool schemas
        model_name = os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview")
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)
        
    async def get_ticket_details(self, issue_identifier: str) -> dict:
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
        
        async with load_github_mcp_tools() as github_tools:
            agent_executor = create_react_agent(self.llm, github_tools)
            result = await agent_executor.ainvoke({"messages": [("user", system_prompt)]})
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
                ticket_data = json.loads(content)
                return ticket_data
            except json.JSONDecodeError:
                print("  [TicketManager] Failed to decode LLM response into JSON.")
                # Fallback mock if parsing fails or issue isn't real during tests
                return {
                    "id": issue_identifier,
                    "title": "Mock Title due to GitHub API failure",
                    "description": "Mocked description.",
                    "status": "TODO",
                    "acceptance_criteria": ["Mock AC"]
                }

    async def get_todo_tickets(self) -> list:
        print("  [TicketManager] Fetching all tickets using GitHub MCP...")
        owner_name = os.environ.get("GITHUB_OWNER", "your-github-username")
        
        system_prompt = f"""
        You are a helpful assistant with access to GitHub MCP tools.
        I want to find open issues that are ready to be worked on (typically TODO state) across the entire scope '{owner_name}'.
        Since we use GitHub Projects V2, you should:
        1. Use the 'projects_list' tool with method='list_projects' and owner='{owner_name}' to find the relevant Project boards.
        2. Use the 'projects_list' tool with method='list_project_items' (and the appropriate project_number) to list the tasks/issues.
        
        Extract those that are in TODO/Open state. Return the result EXACTLY as a raw JSON list (no markdown blocks) containing objects with 'id' (which MUST include the repository name or full URL so it can be identified later) and 'title'.
        Example:
        [
            {{"id": "repo-name#1", "title": "Setup CI/CD"}},
            {{"id": "repo-name#2", "title": "Add User Authentication"}}
        ]
        If you cannot find any, return:
        [
            {{"id": "MOCK-1", "title": "Mock Issue (GitHub Context Not Set up)"}}
        ]
        """
        
        async with load_github_mcp_tools() as github_tools:
            agent_executor = create_react_agent(self.llm, github_tools)
            result = await agent_executor.ainvoke({"messages": [("user", system_prompt)]})
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
