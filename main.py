import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import kinetic
import agent

app = FastAPI(title="Kinetic Communications Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the frontend HTML from the repo root
frontend_dir = os.path.join(os.path.dirname(__file__), "..")
app.mount("/app", StaticFiles(directory=frontend_dir, html=True), name="frontend")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "kinetic_url": os.getenv("KINETIC_BASE_URL", "NOT SET"),
        "anthropic_key_set": bool(os.getenv("ANTHROPIC_API_KEY")),
    }


# ── Scan ──────────────────────────────────────────────────────────────────────

@app.get("/api/scan")
def scan():
    try:
        return kinetic.scan_all()
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Record Detail ─────────────────────────────────────────────────────────────

@app.get("/api/record/order/{order_num}")
def order_detail(order_num: int):
    try:
        return kinetic.get_order_detail(order_num)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/record/job/{job_num:path}")
def job_detail(job_num: str):
    try:
        return kinetic.get_job_detail(job_num)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/record/po/{po_num}")
def po_detail(po_num: int):
    try:
        return kinetic.get_po_detail(po_num)
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Generate ──────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    record_type: str
    comm_type: str
    data: dict
    user_instructions: Optional[str] = ""


@app.post("/api/generate")
def generate(req: GenerateRequest):
    try:
        return agent.generate_draft(
            record_type=req.record_type,
            comm_type=req.comm_type,
            data=req.data,
            user_instructions=req.user_instructions or "",
        )
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Refine ────────────────────────────────────────────────────────────────────

class RefineRequest(BaseModel):
    original_draft: str
    refinement: str


@app.post("/api/refine")
def refine(req: RefineRequest):
    try:
        return agent.refine_draft(req.original_draft, req.refinement)
    except Exception as e:
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
