"""
Health check route for the ai-consultant backend API.

GET /health → 200 {"status": "ok"}
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
async def health_check() -> JSONResponse:
    """Return service health status.

    Always returns 200 with {"status": "ok"} when the server is running.
    """
    return JSONResponse(content={"status": "ok"}, status_code=200)
