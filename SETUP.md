# AI Consultant — Web App

Local, single-user spec-driven development app: brainstorm with an agent → review draft tickets → push accepted ones to Jira → let the implementation agent open a PR against the linked GitHub repo.

Architecture is described in [app_specification.md](app_specification.md).

---

## Quick start (local, no Docker)

### Backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Generate a Fernet key for SECRETS_KEY:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Paste that value into .env as SECRETS_KEY=...
# Also set GEMINI_API_KEY

uvicorn app.main:app --reload --port 8001
```

The API is at http://localhost:8001, health check at `/health`, OpenAPI docs at `/docs`.

Default `DATABASE_URL` is a local SQLite file — no Postgres needed for a first run.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App opens at http://localhost:5173. Vite proxies `/api` and `/ws` to the backend on `:8001`.

---

## Docker Compose (full stack)

```bash
# Generate a Fernet key for SECRETS_KEY:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Then, in the repo root:
export SECRETS_KEY="<paste-key>"
export GEMINI_API_KEY="<your-key>"

docker compose up --build
```

- API:  http://localhost:8001
- Web:  http://localhost:8080

---

## First-run flow

1. **Settings** → set default chat/coding models (defaults to `gemini-2.5-pro`) and implementation trigger mode.
2. **Projects → Create project**, then open it and:
   - Add GitHub repo config (PAT is encrypted at rest); click **Test connection**.
   - Add Jira workspace config (email + API token); click **Test connection**.
   - Optionally override chat/coding models per project.
3. **Brainstorm** — start a new session, chat with the agent to refine your spec, then click **Generate tickets**.
4. **Ticket Review** — edit / accept / reject drafts; **Push accepted → Jira** creates real Jira issues.
5. **Runs** — trigger an implementation run for a Jira issue key (manual), or set the project to `auto_poll` in Settings so the background poller picks up issues in "Ready for Dev".

---

## Notes

- Secrets (GitHub PAT, Jira token) are encrypted at rest with Fernet using `SECRETS_KEY`. **Do not lose that key** — the DB is unreadable without it.
- The implementation agent reuses the existing `agents/` package from this repo (the CLI supervisor).
- Task queue: agent runs execute as asyncio tasks in the FastAPI process. For a single-user local tool this is intentional; the spec's `queue.py` interface is swappable for Celery/RQ later.
- Jira Cloud webhooks can't reach a local machine, so the "auto" trigger is a polling loop (see §4.4a of the spec).
