"""Thin wrapper around the Gemini SDK for chat + structured output."""
import json
import os
from typing import AsyncIterator

import google.generativeai as genai

from ..config import settings


def _get_api_key() -> str:
    """Prefer the encrypted key stored in app_settings, fall back to the env var."""
    try:
        from ..database import SessionLocal
        from ..crypto import decrypt
        from ..models import AppSettings

        db = SessionLocal()
        try:
            row = db.query(AppSettings).first()
            if row and row.encrypted_gemini_api_key:
                return decrypt(row.encrypted_gemini_api_key)
        finally:
            db.close()
    except Exception:
        pass
    return settings.gemini_api_key or ""


def _configure() -> None:
    key = _get_api_key()
    if not key:
        raise RuntimeError(
            "Gemini API key is not set. Configure it under Settings, or set GEMINI_API_KEY in .env."
        )
    genai.configure(api_key=key)
    # Also expose it via env so langchain-google-genai picks it up.
    os.environ["GOOGLE_API_KEY"] = key


def list_available_models() -> list[dict]:
    """Return Gemini models that support generateContent, using the configured API key."""
    _configure()
    out: list[dict] = []
    for m in genai.list_models():
        methods = set(getattr(m, "supported_generation_methods", []) or [])
        if "generateContent" not in methods:
            continue
        name = getattr(m, "name", "") or ""
        short = name.split("/", 1)[1] if name.startswith("models/") else name
        out.append({
            "name": short,
            "display_name": getattr(m, "display_name", "") or short,
            "input_token_limit": getattr(m, "input_token_limit", None),
            "output_token_limit": getattr(m, "output_token_limit", None),
        })
    out.sort(key=lambda x: x["name"])
    return out


def _extract_usage(response) -> dict:
    um = getattr(response, "usage_metadata", None)
    if not um:
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    return {
        "input_tokens": int(getattr(um, "prompt_token_count", 0) or 0),
        "output_tokens": int(getattr(um, "candidates_token_count", 0) or 0),
        "total_tokens": int(getattr(um, "total_token_count", 0) or 0),
    }


def make_model(model_name: str, system_instruction: str | None = None, **params) -> "genai.GenerativeModel":
    _configure()
    generation_config = {}
    for k in ("temperature", "top_p", "top_k", "max_output_tokens"):
        if k in params:
            generation_config[k] = params[k]
    return genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_instruction,
        generation_config=generation_config or None,
    )


async def stream_chat(
    model_name: str,
    history: list[dict],
    user_message: str,
    system_instruction: str | None = None,
    usage_out: dict | None = None,
    **params,
) -> AsyncIterator[str]:
    """Stream response tokens. If `usage_out` is provided, it's populated after the stream completes."""
    model = make_model(model_name, system_instruction=system_instruction, **params)
    chat = model.start_chat(history=history)
    response = chat.send_message(user_message, stream=True)
    for chunk in response:
        text = getattr(chunk, "text", None)
        if text:
            yield text
    if usage_out is not None:
        usage_out.update(_extract_usage(response))


def generate_json(
    model_name: str,
    prompt: str,
    schema: dict | None = None,
    system_instruction: str | None = None,
    usage_out: dict | None = None,
    **params,
) -> dict:
    """Generate a structured JSON response. Uses response_mime_type=application/json."""
    _configure()
    generation_config: dict = {"response_mime_type": "application/json"}
    if schema:
        generation_config["response_schema"] = schema
    for k in ("temperature", "top_p", "top_k", "max_output_tokens"):
        if k in params:
            generation_config[k] = params[k]
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_instruction,
        generation_config=generation_config,
    )
    resp = model.generate_content(prompt)
    if usage_out is not None:
        usage_out.update(_extract_usage(resp))
    text = resp.text or "{}"
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Model returned invalid JSON: {e}\n---\n{text}")
