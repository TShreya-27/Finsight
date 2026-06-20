# FinSight AI - Structured GitHub Package

This repository splits the original monolithic `agents.py` into a package with:
- core config
- schemas
- tools
- guardrails
- evals
- hooks
- agents
- teams
- workflows

## Run locally

### 1. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install backend dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy the example environment file, then update values such as `GROQ_API_KEY`, `PG_URL`, `AUTH_PG_URL`, and `REDIS_URL` if needed.
Item .env.example .env

For a basic local run without Temporal, keep:

```env
TEMPORAL_ENABLED=false
```

### 4. Start the backend

Run the FastAPI backend with Uvicorn:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Backend URLs:

- API health check: `http://127.0.0.1:8010/api/v1/health`
- API docs: `http://127.0.0.1:8010/docs`

### 5. Open the frontend

The frontend is served by the FastAPI backend from `app/static`, so no separate frontend server is required.

Open:

```text
http://127.0.0.1:8010/
```

The review page is opened automatically after a PDF upload. You can also open it directly with a document ID:

```text
http://127.0.0.1:8010/static/review.html?document_id=<document_id>
```

### Optional: run Temporal worker

Only run this if `TEMPORAL_ENABLED=true` and Temporal is available at `TEMPORAL_ADDRESS`.

```powershell
python worker.py
```
