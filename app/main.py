"""FastAPI application entry point."""

import logging
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routers import auth, documents, health, hitl, reports, webhooks, workflow_stream

logger = logging.getLogger(__name__)

app = FastAPI(title="FinSight", version="0.1.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", include_in_schema=False)
async def frontend() -> FileResponse:
    """Serve the evaluator-facing FinSight UI."""
    return FileResponse("app/static/index.html")


@app.get("/dashboard", include_in_schema=False)
async def dashboard_frontend() -> FileResponse:
    """Serve the authenticated FinSight dashboard."""
    return FileResponse("app/static/dashboard.html")


@app.get("/review/{document_id}", include_in_schema=False)
async def review_frontend(document_id: str) -> FileResponse:
    """Serve the human-review page for a processed document."""
    return FileResponse("app/static/review.html")


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    """Attach a correlation ID to each request and response."""
    correlation_id = request.headers.get("x-correlation-id", str(uuid4()))
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["x-correlation-id"] = correlation_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Return a consistent error payload for intentional API errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": exc.detail,
                "correlation_id": getattr(request.state, "correlation_id", None),
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return a consistent error payload for request validation failures."""
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": 422,
                "message": "Request validation failed",
                "details": exc.errors(),
                "correlation_id": getattr(request.state, "correlation_id", None),
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return JSON for unexpected API failures instead of plain text/HTML."""
    logger.exception("Unhandled request error", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": 500,
                "message": "Internal server error",
                "correlation_id": getattr(request.state, "correlation_id", None),
            }
        },
    )


app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(auth.router, tags=["auth"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
app.include_router(hitl.router, prefix="/api/v1/hitl", tags=["hitl"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["webhooks"])
app.include_router(workflow_stream.router, tags=["workflow"])
