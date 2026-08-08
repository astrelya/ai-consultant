import asyncio
import os
import platform
from tools.ticket_manager import TicketManager

class JiraWatcher:
    def __init__(self, supervisor):
        self.supervisor = supervisor
        self.ticket_manager = TicketManager()
        self.seen_tickets = set()
        self.is_running = False

    def send_notification(self, title, message):
        """Send a desktop notification based on the OS."""
        print(f"\n[JiraWatcher] 🔔 NOTIFICATION: {title} - {message}")
        try:
            system = platform.system()
            if system == "Darwin":  # macOS
                os.system(f"""osascript -e 'display notification "{message}" with title "{title}"'""")
            elif system == "Linux":
                os.system(f'notify-send "{title}" "{message}"')
            elif system == "Windows":
                # Basic windows notification using powershell if needed, or just pass
                pass
        except Exception as e:
            print(f"[JiraWatcher] Failed to send desktop notification: {e}")

    async def start_watching(self, poll_interval=60):
        """Start polling for new tickets."""
        self.is_running = True
        print("[JiraWatcher] Starting background watcher for new tickets...")
        
        # Initial fetch to populate seen_tickets
        try:
            initial_tickets = await self.ticket_manager.get_todo_tickets("To Do")
            for t in initial_tickets:
                self.seen_tickets.add(t['id'])
            print(f"[JiraWatcher] Initialized with {len(self.seen_tickets)} existing tickets.")
        except Exception as e:
            print(f"[JiraWatcher] Error during initial fetch: {e}")

        while self.is_running:
            await asyncio.sleep(poll_interval)
            try:
                current_tickets = await self.ticket_manager.get_todo_tickets("To Do")
                for t in current_tickets:
                    if t['id'] not in self.seen_tickets:
                        self.seen_tickets.add(t['id'])
                        self.send_notification("New Jira Ticket", f"{t['id']}: {t['title']}")
                        
                        # Trigger implementation pipeline
                        print(f"[JiraWatcher] Auto-triggering implementation for {t['id']}...")
                        # Run in background so we don't block the watcher
                        asyncio.create_task(self.supervisor.run(t['id']))
            except Exception as e:
                print(f"[JiraWatcher] Error while polling: {e}")

    def stop(self):
        self.is_running = False
