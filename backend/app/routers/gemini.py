from fastapi import APIRouter, HTTPException

from ..services.gemini import list_available_models

router = APIRouter(prefix="/api/v1/gemini", tags=["gemini"])


_FALLBACK_MODELS = [
    {"name": "gemini-2.5-pro", "display_name": "Gemini 2.5 Pro", "input_token_limit": None, "output_token_limit": None},
    {"name": "gemini-2.5-flash", "display_name": "Gemini 2.5 Flash", "input_token_limit": None, "output_token_limit": None},
]


@router.get("/models")
def list_models():
    try:
        models = list_available_models()
        return {"models": models, "source": "api"}
    except Exception as e:
        return {"models": _FALLBACK_MODELS, "source": "fallback", "error": str(e)}
