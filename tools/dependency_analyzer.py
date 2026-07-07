import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from tools.ticket_manager import TicketManager
from tools.mcp_loader import MCPManager

class DependencyAnalyzer:
    def __init__(self):
        model_name = os.environ.get("TICKET_MODEL", "gemini-2.5-flash")
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)
        self.ticket_manager = TicketManager()

    async def build_dag(self, ticket_ids: list) -> dict:
        """
        Builds a Directed Acyclic Graph (DAG) of dependencies for the given ticket IDs.
        Returns:
            dict: Adjacency list mapping node -> list of successor nodes (nodes it blocks).
            Example: { "PROJ-101": ["PROJ-102"], "PROJ-102": [] }
        """
        print(f"[DependencyAnalyzer] Building DAG for: {ticket_ids}")
        
        # 1. Fetch all ticket details
        tickets_details = {}
        for tid in ticket_ids:
            try:
                details = await self.ticket_manager.get_ticket_details(tid)
                tickets_details[tid] = details
            except Exception as e:
                print(f"[DependencyAnalyzer] Warning: failed to fetch details for {tid}: {e}")
                tickets_details[tid] = {
                    "id": tid,
                    "title": f"Ticket {tid}",
                    "description": "",
                    "status": "TODO"
                }

        # 2. Use Gemini to analyze descriptions and build the dependency edges
        # We also pass any explicit links we found.
        # Format the ticket list context for the LLM
        tickets_context = []
        for tid, details in tickets_details.items():
            tickets_context.append({
                "id": tid,
                "title": details.get("title", ""),
                "description": details.get("description", ""),
                "explicit_links": details.get("links", [])
            })
            
        system_prompt = """You are a Technical Project Architect.
Your task is to analyze a list of software tickets and construct a Directed Acyclic Graph (DAG) representing their logical execution order.

If Ticket A must be completed before Ticket B can begin (e.g. A is a backend API, B is the frontend integration, or they edit the exact same files/functions causing conflicts), then Ticket A blocks Ticket B.

For each ticket, return its list of successor tickets (the tickets it blocks, i.e., tickets that depend on it).

Output format:
Return the dependency graph as a raw JSON object mapping ticket keys to a list of keys they block (no markdown blocks, just raw valid JSON):
{
  "PROJ-101": ["PROJ-102"],
  "PROJ-102": [],
  "PROJ-103": []
}

Make sure:
1. The graph is Acyclic (no dependency loops).
2. Every input ticket ID must be a key in the output JSON.
3. Keep the JSON perfectly valid. Do not write extra text.
"""

        user_message = f"Construct the dependency graph for these tickets:\n\n{json.dumps(tickets_context, indent=2)}"
        
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message)
            ])
            
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:-3].strip()
            if content.startswith("```"):
                content = content[3:-3].strip()
                
            dag = json.loads(content)
            
            # Sanity check: ensure all input ticket IDs are present as keys
            for tid in ticket_ids:
                if tid not in dag:
                    dag[tid] = []
                    
            print(f"[DependencyAnalyzer] Constructed DAG: {dag}")
            return dag
            
        except Exception as e:
            print(f"[DependencyAnalyzer] Error building DAG with LLM: {e}. Falling back to linear graph.")
            # Fallback to linear execution (conservative approach)
            dag = {}
            for i, tid in enumerate(ticket_ids):
                dag[tid] = [ticket_ids[i+1]] if i < len(ticket_ids) - 1 else []
            return dag
