import os
import asyncio
import time
from dotenv import load_dotenv
from agents.main_agent import SupervisorAgent
from tools.mcp_loader import MCPManager
import logging
import warnings

# Suppress LangChain verbose schema warnings
warnings.filterwarnings("ignore")
logging.getLogger("langchain_core").setLevel(logging.ERROR)
logging.getLogger("langchain_mcp_adapters").setLevel(logging.ERROR)
logging.getLogger("langchain_google_genai").setLevel(logging.ERROR)
logging.getLogger("langgraph").setLevel(logging.ERROR)

load_dotenv()

async def poll_jira_for_new_tickets(supervisor: SupervisorAgent, poll_interval: int = int(os.environ.get("JIRA_WATCHER_POLL_INTERVAL", 500))):
    """
    Polls Jira for new tickets in the 'To Do' or 'Backlog' status.
    When a new ticket is found, it sends a notification and triggers the implementation pipeline.
    """
    print(f"[JiraWatcher] Starting Jira Watcher. Polling every {poll_interval} seconds...")
    
    seen_tickets = set()
    
    # Initial fetch to populate seen_tickets without triggering implementation
    try:
        initial_tickets = await supervisor.ticket_manager.get_todo_tickets("To Do")
        for t in initial_tickets:
            seen_tickets.add(t['id'])
        print(f"[JiraWatcher] Initialized with {len(seen_tickets)} existing tickets.")
    except Exception as e:
        print(f"[JiraWatcher] Error during initial fetch: {e}")

    while True:
        await asyncio.sleep(poll_interval)
        try:
            print("[JiraWatcher] Checking for new tickets...")
            current_tickets = await supervisor.ticket_manager.get_todo_tickets("To Do")
            
            for ticket in current_tickets:
                ticket_id = ticket['id']
                if ticket_id not in seen_tickets and not ticket_id.startswith("MOCK"):
                    print(f"\n=====================================================")
                    print(f"🔔 [NOTIFICATION] New Jira Ticket Detected: {ticket_id} - {ticket.get('title', 'No Title')}")
                    print(f"=====================================================\n")
                    
                    # Send desktop notification (cross-platform)
                    try:
                        from plyer import notification
                        notification.notify(
                            title=f"New Jira Ticket: {ticket_id}",
                            message=ticket.get('title', 'Auto-implementation started'),
                            app_name="AI Consultant",
                            timeout=10
                        )
                    except ImportError:
                        pass # plyer not installed, console notification is sufficient
                    
                    seen_tickets.add(ticket_id)
                    
                    # Trigger the full implementation pipeline
                    print(f"[JiraWatcher] Auto-triggering implementation for {ticket_id}...")
                    result = await supervisor.run(ticket_id)
                    
                    print(f"\n[JiraWatcher] Implementation completed for {ticket_id}.")
                    if isinstance(result, dict):
                        print(f"Status: {result.get('status')}")
                        if 'development' in result and 'branch' in result['development']:
                            print(f"Branch: {result['development']['branch']}")
                        if 'development' in result and 'pr_url' in result['development']:
                            print(f"PR URL: {result['development']['pr_url']}")
                    else:
                        print(f"Result: {result}")
                    
        except Exception as e:
            print(f"[JiraWatcher] Error while polling: {e}")

async def main():
    print("=====================================================")
    print("  Jira Watcher - Auto-Implementation Service")
    print("=====================================================")
    
    manager = await MCPManager.get_instance()
    
    try:
        supervisor = SupervisorAgent()
        # Poll every 500 seconds by default
        poll_interval = int(os.environ.get("JIRA_WATCHER_POLL_INTERVAL", "500"))
        await poll_jira_for_new_tickets(supervisor, poll_interval=poll_interval)
    except KeyboardInterrupt:
        print("\n[JiraWatcher] Shutting down...")
    finally:
        await manager.close()

if __name__ == "__main__":
    asyncio.run(main())
