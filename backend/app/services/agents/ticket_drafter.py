"""Ticket-drafting agent: converts a chat transcript into structured ticket drafts."""
from typing import Any

from ..gemini import generate_json


TICKET_SCHEMA = {
    "type": "object",
    "properties": {
        "tickets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                    "issue_type": {"type": "string"},
                    "priority": {"type": "string"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                    "suggested_epic_group": {"type": "string"},
                },
                "required": ["title", "description", "acceptance_criteria", "issue_type", "priority"],
            },
        }
    },
    "required": ["tickets"],
}


DRAFTER_SYSTEM = (
    "You convert product brainstorm transcripts into a structured list of engineering "
    "tickets. Prefer small, independently deliverable Stories. Use issue_type ∈ "
    "{Story, Task, Bug, Epic}; priority ∈ {Highest, High, Medium, Low, Lowest}. "
    "Write concrete acceptance_criteria that a QA engineer can verify. Group related "
    "tickets under a common suggested_epic_group name when useful; otherwise leave it null."
)


def transcript_to_prompt(messages: list[dict[str, str]]) -> str:
    lines = ["Brainstorm transcript:", ""]
    for m in messages:
        role = m.get("role", "user").upper()
        lines.append(f"[{role}] {m.get('content', '')}")
    lines.append("")
    lines.append("Produce the JSON list of ticket drafts now.")
    return "\n".join(lines)


def draft_tickets(
    model_name: str,
    messages: list[dict[str, str]],
    usage_out: dict | None = None,
    **params,
) -> list[dict[str, Any]]:
    prompt = transcript_to_prompt(messages)
    result = generate_json(
        model_name=model_name,
        prompt=prompt,
        schema=TICKET_SCHEMA,
        system_instruction=DRAFTER_SYSTEM,
        usage_out=usage_out,
        **params,
    )
    tickets = result.get("tickets", [])
    if not isinstance(tickets, list):
        raise RuntimeError("Ticket-drafting agent returned a non-list 'tickets' field")
    return tickets
