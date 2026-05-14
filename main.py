"""
main.py
-------
FastAPI backend for AI Legal Shield.

Endpoints:
  GET  /health   -> backend status + which LLM provider is active
  POST /ask      -> run the full multi-agent pipeline, return structured answer
  POST /upload   -> upload a PDF, extract + chunk + store it for RAG
  GET  /history  -> previous questions and final answers for a user

It also serves the existing frontend (index.html / app.js / styles.css) so the
whole thing runs from a single `uvicorn main:app` command, and CORS is wide
open so the frontend also works if opened directly as a file.

Run:  uvicorn main:app --reload   then open  http://127.0.0.1:8000
"""

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from database import DatabaseService
from rag_service import RAGService
from llm_client import LLMClient, get_provider_info
from services.legal_pipeline import LegalPipeline

# ---------------------------------------------------------------------------
# Paths + service singletons
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = BASE_DIR / "legal_shield.db"

db = DatabaseService(str(DB_PATH))
db.init()
rag = RAGService(db)
llm = LLMClient()
pipeline = LegalPipeline(llm)

# Map the existing frontend's mode names onto the pipeline's three modes.
MODE_MAP = {
    "quick": "quick",
    "normal": "normal",
    "thinking": "thinking",
    # Legacy names from the original UI, kept so nothing breaks:
    "consult": "normal",
    "defense": "thinking",
}

app = FastAPI(title="AI Legal Shield", version="1.0")

# Backend supports the frontend through CORS (and also serves it directly).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class AskRequest(BaseModel):
    user_id: str = "anon"
    # Accept both "question" (spec) and "prompt" (existing frontend field).
    question: Optional[str] = None
    prompt: Optional[str] = None
    mode: str = "normal"


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    """Simple status check for the frontend / team."""
    return {
        "status": "ok",
        "service": "AI Legal Shield",
        "llm": get_provider_info(),
    }


@app.post("/ask")
def ask(req: AskRequest):
    """Run the full Lawyer / Risk / Judge pipeline and return a clean answer."""
    question = (req.question or req.prompt or "").strip()
    if not question:
        return JSONResponse(status_code=400, content={"error": "Question is required."})

    mode = MODE_MAP.get((req.mode or "normal").lower(), "normal")
    user_id = (req.user_id or "anon").strip() or "anon"

    # Persist the user + question.
    db.create_user(user_id, user_id)
    question_id = db.add_question(user_id, question, mode)

    # RAG: retrieve relevant chunks from uploaded PDFs (may be empty).
    rag_chunks = rag.search(question)

    # Run the multi-agent pipeline.
    result = pipeline.run(question, mode, rag_chunks)

    # Persist every visible agent step + the final answer.
    for item in result["agent_trace"]:
        db.add_agent_run(
            question_id=question_id,
            agent_name=item["agent"],
            phase=item["phase"],
            iteration_number=item["iteration"],
            input_text="",
            output_text=item["message"],
            approved=item["approved"],
            emergency_used=item["emergency_used"],
        )
    db.add_final_answer(
        question_id=question_id,
        final_answer=result["final_answer"],
        disclaimer=result["disclaimer"],
        unresolved_issues="; ".join(result["emergency_notes"]),
    )

    result["question_id"] = question_id
    return result


@app.post("/upload")
async def upload(user_id: str = Form("anon"), file: UploadFile = File(...)):
    """Receive a PDF, store it, extract text, chunk it, and save chunks for RAG."""
    user_id = (user_id or "anon").strip() or "anon"
    filename = file.filename or "document.pdf"

    if not filename.lower().endswith(".pdf"):
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Only PDF files are supported."},
        )

    db.create_user(user_id, user_id)

    # Save the uploaded file to the uploads/ folder.
    safe_name = Path(filename).name
    file_path = UPLOAD_DIR / f"{user_id}_{safe_name}"
    contents = await file.read()
    file_path.write_bytes(contents)

    # Extract -> chunk -> store in SQLite.
    try:
        document_id, chunks_created = rag.ingest(user_id, safe_name, str(file_path))
    except Exception as exc:  # noqa: BLE001 - keep the demo alive
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Could not read that PDF: {exc}",
            },
        )

    return {
        "success": True,
        "document_id": document_id,
        "filename": safe_name,
        "chunks_created": chunks_created,
        "message": (
            f"'{safe_name}' uploaded successfully — {chunks_created} text "
            f"chunk(s) are now available for legal questions."
        ),
    }


@app.get("/history")
def history(user_id: str = "anon"):
    """Return previous questions and their final answers for a user."""
    user_id = (user_id or "anon").strip() or "anon"
    return {"user_id": user_id, "history": db.get_history(user_id)}


# ---------------------------------------------------------------------------
# Serve the existing frontend (kept exactly where it already lives).
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/app.js")
def app_js():
    return FileResponse(BASE_DIR / "app.js")


@app.get("/styles.css")
def styles_css():
    return FileResponse(BASE_DIR / "styles.css")
