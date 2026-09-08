FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
COPY backend/requirements-postgres.txt /app/backend/requirements-postgres.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt \
 && pip install --no-cache-dir -r /app/backend/requirements-postgres.txt

# Copy backend and the existing agent package (implementer.py imports `agents.*`)
COPY backend /app/backend
COPY agents /app/agents
COPY tools /app/tools

WORKDIR /app/backend
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
