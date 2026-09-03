"""
Config route for the ai-consultant backend API.

GET /config
    → {"agent_mode": "local"|"remote",
       "models": {"ticket": str, "coding": str},
       "available_models": [str, ...]}
PUT /config/models {"ticket"?: str, "coding"?: str}
    → applies the new model(s) to os.environ (picked up on the next LLM call)
       and returns the new `models` map.
"""
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.chat.llm_chat import AVAILABLE_MODELS, get_current_model, set_model

router = APIRouter()


@router.get("/config")
async def get_config() -> dict:
    return {
        "agent_mode": os.environ.get("AGENT_MODE", "remote").lower(),
        "models": {
            "ticket": get_current_model("ticket"),
            "coding": get_current_model("coding"),
        },
        "available_models": AVAILABLE_MODELS,
    }


class ModelUpdate(BaseModel):
    ticket: str | None = None
    coding: str | None = None


@router.put("/config/models")
async def update_models(body: ModelUpdate) -> dict:
    updates: dict[str, str] = {}
    for role, value in (("ticket", body.ticket), ("coding", body.coding)):
        if value is None:
            continue
        if value not in AVAILABLE_MODELS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown model '{value}'. Allowed: {AVAILABLE_MODELS}",
            )
        set_model(role, value)
        updates[role] = value

    return {
        "updated": updates,
        "models": {
            "ticket": get_current_model("ticket"),
            "coding": get_current_model("coding"),
        },
    }
