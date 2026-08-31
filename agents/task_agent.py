"""
Task Agent Module
Decomposes an approved specification + plan into an ordered list of small,
independently verifiable implementation tasks (tasks.md source data).
"""
import os
import json
from typing import List, Dict
from langchain_google_genai import ChatGoogleGenerativeAI


class TaskAgent:
    def __init__(self):
        model_name = os.environ.get("SPEC_MODEL", os.environ.get("CODING_MODEL", "gemini-3.1-pro-preview"))
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    async def breakdown_tasks(self, story_details: dict, spec: str, plan: str) -> List[Dict]:
        title = story_details.get('title', 'Untitled')

        print(f"  [TaskAgent] Breaking down tasks for: {title}")

        system_prompt = f"""You are a Task Breakdown Agent in a Spec-Driven Development workflow.
Decompose the approved specification and plan into an ordered list of implementation tasks.

TICKET:
- ID: {story_details.get('id', 'unknown')}
- Title: {title}

APPROVED SPECIFICATION:
{spec}

APPROVED PLAN:
{plan}

Rules:
- Produce 3 to 10 tasks, ordered so each task builds on the previous ones.
- Each task must be independently verifiable and small enough to implement in one focused pass.
- Every acceptance criterion from the specification must be covered by at least one task.
- Return EXACTLY a raw JSON list (no markdown fences, no commentary) of objects:
[{{"id": "T1", "title": "...", "description": "...", "acceptance_criteria": ["..."]}}]
"""

        response = self.llm.invoke(system_prompt)
        content = str(response.content).strip()

        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()

        try:
            tasks = json.loads(content)
            if isinstance(tasks, dict):
                tasks = [tasks]
            normalized = []
            for i, task in enumerate(tasks, start=1):
                normalized.append({
                    "id": str(task.get("id", f"T{i}")),
                    "title": str(task.get("title", f"Task {i}")),
                    "description": str(task.get("description", "")),
                    "acceptance_criteria": [str(ac) for ac in (task.get("acceptance_criteria") or [])],
                    "status": "pending",
                })
            if normalized:
                return normalized
        except json.JSONDecodeError:
            print("  [TaskAgent] Failed to decode LLM response into JSON, falling back to a single task.")

        # Fallback: one generic task so the pipeline can still proceed
        return [{
            "id": "T1",
            "title": f"Implement the full specification: {title}",
            "description": spec[:2000],
            "acceptance_criteria": [],
            "status": "pending",
        }]
