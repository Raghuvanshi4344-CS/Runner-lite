"""The FastAPI application. PROVIDED IN FULL.

Run it with:  uvicorn app.main:app --reload
Then open http://127.0.0.1:8000/docs for an interactive UI over every endpoint — you can create a
task and start a run from the browser without writing any curl.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.api import router

app = FastAPI(
    title="Agent Runner Lite",
    description="A small governed agent runner. See BRIEF.md for the exercise.",
)
app.include_router(router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
