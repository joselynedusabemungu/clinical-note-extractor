import os

from audit import log_extraction
from extractor import extract
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "").split(",")
    if origin.strip()
]

app = FastAPI(title="Clinical Note Extractor")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS or ["http://localhost:8501", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExtractRequest(BaseModel):
    note: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/extract")
def extract_endpoint(req: ExtractRequest) -> dict:
    if not req.note or not req.note.strip():
        raise HTTPException(status_code=400, detail="note must not be empty")
    ext, err = extract(req.note)
    if ext is None:
        return {"ok": False, "needs_human_review": True, "data": None, "error": err}
    log_extraction(
        req.note, ext.model_dump_json(), ext.needs_human_review, ext.abstention_reason
    )
    return {
        "ok": True,
        "needs_human_review": ext.needs_human_review,
        "data": ext.model_dump(),
        "error": None,
    }
