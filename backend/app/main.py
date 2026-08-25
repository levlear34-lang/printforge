"""PrintForge backend entry point (FastAPI).

Milestone 1 scope: a booting app with a health check and a proof that the
vendored classification logic works, so the deploy pipeline can be verified
before any real feature is built. The full create flow (job submission,
Kaggle dispatch, polling) lands in milestone 2.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.vendored.request_classifier import classify_request
from app.routes.create import router as create_router

app = FastAPI(title="PrintForge API")
app.include_router(create_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
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
