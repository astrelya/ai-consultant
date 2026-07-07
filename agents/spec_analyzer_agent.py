import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

class SpecAnalyzerAgent:
    def __init__(self):
        # Default model for developer thinking
        model_name = os.environ.get("CODING_MODEL", "gemini-3.1-pro-preview")
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    async def analyze_spec(self, spec_text: str) -> list:
        """
        Analyzes specification text and generates structured user stories with acceptance criteria.
        """
        print(f"[SpecAnalyzerAgent] Running analysis on specification ({len(spec_text)} chars)...")
        
        system_prompt = """You are a Principal Product Manager and Technical Architect.
Your task is to analyze the provided software specification document and decompose it into a set of structured, high-quality User Stories.

Each User Story must be small, cohesive, implementable, and represent a distinct feature.
You must also identify dependencies among these user stories (e.g., STORY-1 depends on STORY-0).

Output format:
Return the user stories as a raw JSON list matching this structure exactly (no markdown blocks, just raw valid JSON):
[
  {
    "id": "STORY-0",
    "title": "Setup database configuration",
    "description": "As a developer, I want to establish database connections to store application settings...",
    "acceptance_criteria": [
      "Database schema is initialized on startup.",
      "Connection parameters can be modified via env variables."
    ],
    "dependencies": []
  },
  {
    "id": "STORY-1",
    "title": "Implement API configuration routes",
    "description": "As a frontend app, I want to access GET and POST config endpoints...",
    "acceptance_criteria": [
      "GET /api/config returns current settings.",
      "POST /api/config saves settings to database."
    ],
    "dependencies": ["STORY-0"]
  }
]

Make sure:
1. Every story has clear, actionable acceptance criteria.
2. The list of dependencies maps to the 'id' fields of the dependent stories in the same list.
3. Keep the JSON output perfectly valid. Do not write extra text.
"""

        user_message = f"Here is the specification document content:\n\n{spec_text}\n\nDecompose into structured user stories."
        
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message)
            ])
            
            raw = response.content
            if isinstance(raw, list):
                content = "".join(
                    part["text"] if isinstance(part, dict) else str(part)
                    for part in raw
                ).strip()
            else:
                content = raw.strip()
            
            # Simple markdown cleanup if necessary
            if content.startswith("```json"):
                content = content[7:-3].strip()
            if content.startswith("```"):
                content = content[3:-3].strip()
                
            stories = json.loads(content)
            if not isinstance(stories, list):
                stories = [stories]
            return stories
            
        except Exception as e:
            print(f"[SpecAnalyzerAgent] Error generating stories: {e}")
            # Fallback mock stories if LLM generation fails
            return [
                {
                    "id": "STORY-0",
                    "title": "Decomposed User Story",
                    "description": f"Analyzed feature from specification. Full spec text context size: {len(spec_text)}.",
                    "acceptance_criteria": ["Spec is parsed and analyzed successfully."],
                    "dependencies": []
                }
            ]
