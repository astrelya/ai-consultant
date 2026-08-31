"""
Plan Agent Module
Turns an approved specification into a technical implementation plan (plan.md),
grounded in the real file layout of the cloned repository.
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


class PlanAgent:
    def __init__(self):
        model_name = os.environ.get("SPEC_MODEL", os.environ.get("CODING_MODEL", "gemini-3.1-pro-preview"))
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    async def write_plan(self, story_details: dict, spec: str, workspace_path: str, feedback: str = "") -> str:
        title = story_details.get('title', 'Untitled')

        print(f"  [PlanAgent] Writing implementation plan for: {title}")

        feedback_section = ""
        if feedback:
            feedback_section = f"""
A human reviewer REJECTED the previous plan/tasks with this feedback:
{feedback}
Revise the plan to address every point of the feedback.
"""

        system_prompt = f"""You are a Planning Agent in a Spec-Driven Development workflow.
Given the APPROVED specification below and the codebase, produce a technical implementation plan. Do NOT write implementation code.

TICKET:
- ID: {story_details.get('id', 'unknown')}
- Title: {title}

APPROVED SPECIFICATION:
{spec}

WORKSPACE (the cloned repository): {workspace_path}
Explore the codebase with your tools (read-only) so the plan references real file paths. Do NOT modify any file.
{feedback_section}
Write the plan as pure Markdown (no code fence around the whole document) with EXACTLY these sections:
# Implementation Plan: {title}
## 1. Approach & Architecture
## 2. Files to Create / Modify        (list: path — what changes and why)
## 3. Technical Decisions             (explicit choices + one-line rationale each)
## 4. Data / Interface Changes        (APIs, schemas, config; write "None" if not applicable)
## 5. Risks & Mitigations

Rules:
- Reference real file paths found in the workspace.
- Keep the plan minimal and strictly consistent with the specification scope.
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
