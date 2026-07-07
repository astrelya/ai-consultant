import os
import json
import re
import asyncio
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from tools.mcp_loader import MCPManager
from backend.websocket import broadcast_log

class TicketCreatorAgent:
    def __init__(self):
        model_name = os.environ.get("TICKET_MODEL", "gemini-2.5-flash")
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    async def create_tickets(self, stories: list, job_id: str) -> list:
        """
        Creates Jira tickets from structured user stories in a batch.
        Also creates blocks/is-blocked-by dependencies.
        """
        print(f"[TicketCreatorAgent] Initiating batch creation for {len(stories)} stories...")
        await broadcast_log(f"Loading Jira MCP tools to start ticket creation...", job_id)
        
        manager = await MCPManager.get_instance()
        jira_tools = manager.jira_tools
        
        if not jira_tools:
            await broadcast_log("Jira MCP tools are not available. Creating mock tickets instead.", job_id, "WARNING")
            mock_keys = []
            for i, s in enumerate(stories):
                mock_keys.append(f"MOCK-{100 + i}")
            return mock_keys

        # Build prompt instructing the ReAct agent to create tickets and link dependencies
        jira_url = os.environ.get("JIRA_URL", "https://astrelya.atlassian.net")
        cloud_id = "95778ac0-3f3b-46a0-95f5-e465d87b6a37"  # Hardcoded cloudId for target site
        
        # Format stories context
        stories_context = json.dumps(stories, indent=2)
        
        system_prompt = f"""You are a Project Management agent with access to Jira MCP tools.
Your goal is to create issues in Jira for the user stories listed below and link their dependencies.

Jira Cloud ID: {cloud_id}
Jira URL: {jira_url}

Stories to create:
{stories_context}

Step-by-step instructions:
1. For each story, create a Jira issue under the appropriate project (e.g. project key is usually the prefix of stories, or default project like "PROJ" / "AI"). Use issue type "Task" or "Story".
   - Use the story title as the summary.
   - Use the description and acceptance criteria in the description field.
2. Store the key of each created issue (e.g., 'PROJ-101') so you can map 'STORY-0' to its Jira key.
3. For any story that lists a dependency in its 'dependencies' field (e.g. 'STORY-0'), link the created issues:
   - For example, if STORY-1 depends on STORY-0, create an issue link where STORY-0 "blocks" STORY-1, or STORY-1 "is blocked by" STORY-0.
4. Output the final mapping of stories to Jira keys and return the list of Jira keys.
5. Return the list of created Jira keys EXACTLY as a JSON array (no markdown code blocks, just raw JSON) like:
   ["PROJ-101", "PROJ-102", "PROJ-103"]

CRITICAL:
- Use the cloudId '{cloud_id}'.
- Keep your thoughts concise.
- Output ONLY the raw JSON list of Jira keys at the end.
"""
        
        await broadcast_log("Executing ticket creation agent loop...", job_id)
        
        try:
            agent_executor = create_agent(self.llm, jira_tools)
            result = await agent_executor.ainvoke({"messages": [("user", system_prompt)]})
            
            content_raw = result["messages"][-1].content
            if isinstance(content_raw, list):
                content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content_raw])
            else:
                content = str(content_raw)
                
            content = content.strip()
            
            # Extract JSON block
            if content.startswith("```json"):
                content = content[7:-3].strip()
            if content.startswith("```"):
                content = content[3:-3].strip()

            # Real Jira keys look like PROJ-123 but not STORY-0, STORY-1, etc.
            JIRA_KEY_RE = re.compile(r'\b(?!STORY-\d)([A-Z][A-Z0-9]+-\d+)\b')

            created_keys = None

            # Try strict JSON parse of the final message first
            if content:
                try:
                    parsed = json.loads(content)
                    # Keep only real Jira keys (not STORY-* placeholders)
                    if isinstance(parsed, list):
                        real_keys = [k for k in parsed if JIRA_KEY_RE.match(str(k))]
                        if real_keys:
                            created_keys = real_keys
                except json.JSONDecodeError:
                    pass

            # Fallback: find a JSON array in the content that contains real keys
            if created_keys is None:
                for json_match in re.finditer(r'\[.*?\]', content, re.DOTALL):
                    try:
                        parsed = json.loads(json_match.group())
                        real_keys = [k for k in parsed if JIRA_KEY_RE.match(str(k))]
                        if real_keys:
                            created_keys = real_keys
                            break
                    except json.JSONDecodeError:
                        continue

            # Fallback: scrape real Jira keys from tool response messages only
            if created_keys is None:
                tool_texts = []
                for m in result.get("messages", []):
                    # ToolMessage or any message that is a tool response
                    if hasattr(m, "type") and m.type == "tool":
                        tool_texts.append(str(m.content))
                    elif hasattr(m, "name") and m.name:
                        tool_texts.append(str(m.content))
                all_tool_text = " ".join(tool_texts)
                found = list(dict.fromkeys(JIRA_KEY_RE.findall(all_tool_text)))  # deduplicated, ordered
                if found:
                    created_keys = found

            if not created_keys:
                raise ValueError("Could not extract any Jira keys from agent tool responses")

            await broadcast_log(f"Successfully created tickets: {created_keys}", job_id)
            return created_keys
            
        except Exception as e:
            print(f"[TicketCreatorAgent] Error creating tickets: {e}")
            await broadcast_log(f"Ticket creation failed with error: {e}. Falling back to default list.", job_id, "ERROR")
            # Return fallback list
            return [f"PROJ-{100 + i}" for i in range(len(stories))]
