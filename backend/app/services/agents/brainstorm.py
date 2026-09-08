"""Brainstorm agent: streams a conversational reply using the project's chat model."""
from typing import AsyncIterator

from ..gemini import stream_chat


BRAINSTORM_SYSTEM = (
    "You are a senior product-engineering consultant helping the user refine a rough "
    "feature idea into a well-scoped specification suitable for creating engineering "
    "tickets. Ask clarifying questions, surface ambiguities, propose scope boundaries, "
    "and confirm assumptions. Be concise. When the spec feels ready, tell the user "
    "they can click 'Generate tickets' to produce ticket drafts."
)


async def brainstorm_stream(
    model_name: str,
    history: list[dict],
    user_message: str,
    usage_out: dict | None = None,
    **params,
) -> AsyncIterator[str]:
    async for chunk in stream_chat(
        model_name=model_name,
        history=history,
        user_message=user_message,
        system_instruction=BRAINSTORM_SYSTEM,
        usage_out=usage_out,
        **params,
    ):
        yield chunk
