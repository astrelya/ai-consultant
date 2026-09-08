import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine, ensure_columns
from .routers import chat, configs, gemini as gemini_router, projects, runs, settings as settings_router, tickets
from .workers.poller import poller_loop


Base.metadata.create_all(bind=engine)
ensure_columns()


@asynccontextmanager
async def lifespan(app: FastAPI):
    poller_task = asyncio.create_task(poller_loop())
    try:
        yield
    finally:
        poller_task.cancel()
        try:
            await poller_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="AI Consultant API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(projects.router)
app.include_router(configs.router)
app.include_router(gemini_router.router)
app.include_router(settings_router.router)
app.include_router(chat.router)
app.include_router(tickets.router)
app.include_router(runs.router)
