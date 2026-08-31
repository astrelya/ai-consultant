"""
Spec Agent Module
Generates a structured, testable specification (spec.md) from a ticket,
following the Spec-Driven Development workflow. Explores the cloned codebase
(read-only) so the spec is grounded in the actual project.
"""
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from agents.local_developer_agent import local_read_file, local_list_files


def _clean_markdown(content: str) -> str:
    content = content.strip()
    if content.startswith("```markdown"):
        content = content[11:-3].strip()
    elif content.startswith("```"):
        content = content[3:-3].strip()
    return content


class SpecAgent:
    def __init__(self):
        model_name = os.environ.get("SPEC_MODEL", os.environ.get("CODING_MODEL", "gemini-3.1-pro-preview"))
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    async def write_spec(self, story_details: dict, workspace_path: str, feedback: str = "") -> str:
        title = story_details.get('title', 'Untitled')
        description = story_details.get('description', '')
        acceptance = story_details.get('acceptance_criteria') or []

        print(f"  [SpecAgent] Writing specification for: {title}")

        feedback_section = ""
        if feedback:
            feedback_section = f"""
A human reviewer REJECTED the previous specification with this feedback:
{feedback}
Revise the specification to address every point of the feedback.
"""

        system_prompt = f"""You are a Spec Agent in a Spec-Driven Development workflow.
Your job is to write a precise, testable specification for a ticket — NOT to implement anything.

TICKET:
- ID: {story_details.get('id', 'unknown')}
- Title: {title}
- Description: {description}
- Acceptance criteria mentioned in the ticket: {acceptance}

WORKSPACE (the cloned repository): {workspace_path}
First explore the codebase with your tools (list files, read the most relevant ones) so the specification is grounded in the actual project. Do NOT modify any file.
{feedback_section}
Write the specification as pure Markdown (no code fence around the whole document) with EXACTLY these sections:
# Specification: {title}
## 1. Objective
## 2. User Stories
## 3. Functional Requirements        (numbered FR-1, FR-2, ...)
## 4. Acceptance Criteria             (checklist "- [ ] AC-1: ...", each one independently verifiable)
## 5. Scope / Out of Scope
## 6. Technical Constraints & Risks
## 7. Open Questions

Rules:
- Be concrete and testable; every acceptance criterion must be checkable by reading code or running tests.
- If the ticket is ambiguous, state your assumption explicitly in "Open Questions".
- Output ONLY the markdown document.
"""

        agent_executor = create_react_agent(self.llm, [local_read_file, local_list_files])
        result = await agent_executor.ainvoke({"messages": [("user", system_prompt)]})

        content_raw = result["messages"][-1].content
        if isinstance(content_raw, list):
            content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content_raw])
        else:
            content = str(content_raw)

        return _clean_markdown(content)
