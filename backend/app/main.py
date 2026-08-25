"""PrintForge backend entry point (FastAPI).

Serves both the JSON API and the static frontend from one process/one
Render service -- simplest possible deploy for a small site, no second
hosting pipeline to keep in sync. FRONTEND_DIR points at the sibling
frontend/ folder (repo root, not inside backend/), same layout convention
as kaggle_kernel/ living outside backend/ too.
"""
import os

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.vendored.request_classifier import classify_request
from app.routes.create import router as create_router

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FRONTEND_DIR = os.path.join(REPO_ROOT, "frontend")

app = FastAPI(title="PrintForge API")
app.include_router(create_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")


def _page(name):
    return FileResponse(os.path.join(FRONTEND_DIR, name))


@app.get("/")
def landing_page():
    return _page("index.html")


@app.get("/create")
def create_page():
    return _page("create.html")


@app.get("/job")
def job_page():
    return _page("job.html")


@app.get("/result")
def result_page():
    return _page("result.html")


@app.get("/robots.txt")
def robots():
    return FileResponse(os.path.join(FRONTEND_DIR, "robots.txt"), media_type="text/plain")


@app.exception_handler(404)
async def not_found(request: Request, exc: HTTPException):
    """API 404s stay JSON (a job/asset genuinely not existing is a normal,
    programmatic response the frontend JS handles) -- only page routes get
    the styled 404.html.
    """
    if request.url.path.startswith("/api/"):
        return await http_exception_handler(request, exc)
    return FileResponse(os.path.join(FRONTEND_DIR, "404.html"), status_code=404)


@app.get("/api/status")
def api_status():
    return {"service": "PrintForge", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


class ClassifyRequest(BaseModel):
    text: str


@app.post("/api/classify")
def classify(payload: ClassifyRequest):
    """Proves the vendored request_classifier is wired up correctly.

    Superseded by the full /api/create flow in milestone 2 -- kept as a
    minimal smoke-test endpoint for the milestone 1 deploy check.
    """
    return {"classification": classify_request(payload.text)}
