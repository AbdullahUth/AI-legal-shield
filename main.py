"""
main.py
-------
FastAPI backend for AI Legal Shield.

Endpoints:
  GET  /health                 -> backend status + which LLM provider is active
  POST /signup /login /me      -> simple hackathon auth (hashed passwords)
  POST /ask                    -> run the multi-agent pipeline, structured answer
  POST /upload                 -> user PDF upload, extract + chunk + store for RAG
  POST /admin/upload-knowledge -> admin upload of law files / past cases for RAG
  GET  /history                -> previous questions and final answers for a user

It also serves the existing frontend (index.html / app.js / styles.css) so the
whole thing runs from a single `uvicorn main:app` command, and CORS is wide
open so the frontend also works if opened directly as a file.

Run:  uvicorn main:app --reload   then open  http://127.0.0.1:8000
"""

import hashlib
import os
import secrets
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from database import DatabaseService, DOCUMENT_TYPES, DEFAULT_DOCUMENT_TYPE
from rag_service import RAGService
from llm_client import LLMClient, get_provider_info
from services.legal_pipeline import LegalPipeline
from parsing import sanitize_untrusted_text

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

app = FastAPI(title="AI Legal Shield", version="1.1")

# Backend supports the frontend through CORS (and also serves it directly).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Simple hackathon-grade auth (NOT production auth).
# Passwords are hashed with PBKDF2-SHA256 + per-user salt (never stored plain).
# Sessions are kept in-memory: token -> user_id.
# ---------------------------------------------------------------------------
SESSIONS = {}  # token -> user_id

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000
    ).hex()
    return f"{salt}${digest}"

def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = (stored or "").split("$", 1)
    except ValueError:
        return False
    test = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000
    ).hex()
    return secrets.compare_digest(test, digest)

def issue_token(user_id: str) -> str:
    token = secrets.token_urlsafe(24)
    SESSIONS[token] = user_id
    return token

def _token_from_header(authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None

def resolve_user(token: Optional[str], user_id: Optional[str]) -> str:
    """Resolve the acting user: a valid token wins, else fall back to user_id
    (guest/anonymous users are still allowed so nothing breaks)."""
    if token and token in SESSIONS:
        return SESSIONS[token]
    if user_id and user_id.strip():
        return user_id.strip()
    return "anon"


# ---------------------------------------------------------------------------
# Upload security + shared PDF ingest helper
# ---------------------------------------------------------------------------
# Optional admin password for the knowledge-upload endpoint. Only enforced when
# ADMIN_PASSWORD is set in .env — so the demo still works out of the box.
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
try:
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
except ValueError:
    MAX_UPLOAD_MB = 10
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def _process_pdf_upload(user_id: str, filename: str, contents: bytes, doc_type: str):
    """
    Shared, security-hardened PDF ingest used by /upload and
    /admin/upload-knowledge. Treats the uploaded file as UNTRUSTED:
    validates type + size, uses a safe filename (no path traversal), stores it
    only inside uploads/, and never executes it. Raises ValueError for client
    errors (-> 400). Reuses the existing RAGService extraction/chunking.
    """
    if not filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF files are supported.")
    if not contents:
        raise ValueError("The uploaded file is empty.")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise ValueError(f"File too large. The maximum size is {MAX_UPLOAD_MB} MB.")
    if not contents[:5] == b"%PDF-":
        raise ValueError("That file does not look like a valid PDF.")

    doc_type = (doc_type or "").strip().lower()
    if doc_type not in DOCUMENT_TYPES:
        doc_type = DEFAULT_DOCUMENT_TYPE

    db.create_user(user_id, user_id)

    # Safe filename: Path(...).name strips any directory components, so a
    # malicious "../../etc/passwd" name becomes just "passwd".
    safe_name = Path(filename).name or "document.pdf"
    file_path = (UPLOAD_DIR / f"{user_id}_{safe_name}").resolve()
    # Defense in depth: the resolved path must stay inside the uploads/ folder.
    if UPLOAD_DIR.resolve() != file_path.parent:
        raise ValueError("Invalid file name.")
    file_path.write_bytes(contents)

    try:
        document_id, chunks_created = rag.ingest(
            user_id, safe_name, str(file_path), document_type=doc_type)
    except Exception:  # noqa: BLE001 - never leak internals to the frontend
        raise ValueError("Could not read that PDF. Please try a different file.")

    return {
        "success": True,
        "document_id": document_id,
        "filename": safe_name,
        "document_type": doc_type,
        "chunks_created": chunks_created,
        "message": (
            f"'{safe_name}' uploaded as {doc_type.replace('_', ' ')} — "
            f"{chunks_created} text chunk(s) are now available for legal questions."
        ),
    }


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class AskRequest(BaseModel):
    user_id: str = "anon"
    token: Optional[str] = None
    # Accept both "question" (spec) and "prompt" (existing frontend field).
    question: Optional[str] = None
    prompt: Optional[str] = None
    mode: str = "normal"


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


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


@app.post("/signup")
def signup(req: SignupRequest):
    """Create an account (hashed password) and return a session token."""
    email = (req.email or "").strip().lower()
    name = (req.name or "").strip()
    if not email or not req.password or not name:
        return JSONResponse(status_code=400, content={
            "success": False, "message": "Name, email and password are required."})
    if db.get_user_by_email(email):
        return JSONResponse(status_code=409, content={
            "success": False, "message": "An account with that email already exists."})

    user_id = "user-" + uuid.uuid4().hex[:12]
    db.create_account(user_id, name, email, hash_password(req.password))
    token = issue_token(user_id)
    return {
        "success": True, "user_id": user_id, "name": name,
        "token": token, "message": f"Welcome, {name}. Your account is ready.",
    }


@app.post("/login")
def login(req: LoginRequest):
    """Log in with email + password and return a session token."""
    email = (req.email or "").strip().lower()
    user = db.get_user_by_email(email)
    if not user or not verify_password(req.password or "", user.get("password_hash")):
        return JSONResponse(status_code=401, content={
            "success": False, "message": "Invalid email or password."})

    token = issue_token(user["id"])
    return {
        "success": True, "user_id": user["id"], "name": user["name"],
        "token": token, "message": f"Welcome back, {user['name']}.",
    }


@app.get("/me")
def me(authorization: Optional[str] = Header(default=None),
       token: Optional[str] = None):
    """Return the currently logged-in user (token via header or query param)."""
    tok = _token_from_header(authorization) or token
    user_id = SESSIONS.get(tok or "")
    if not user_id:
        return JSONResponse(status_code=401, content={
            "success": False, "message": "Not logged in."})
    user = db.get_user_by_id(user_id)
    if not user:
        return JSONResponse(status_code=401, content={
            "success": False, "message": "Not logged in."})
    return {"success": True, "user_id": user["id"], "name": user["name"],
            "email": user.get("email")}


@app.post("/ask")
def ask(req: AskRequest):
    """Run the full Lawyer / Risk / Judge pipeline and return a clean answer."""
    raw_question = (req.question or req.prompt or "").strip()
    if not raw_question:
        return JSONResponse(status_code=400, content={"error": "Question is required."})
    # The user question is UNTRUSTED input — sanitise it before it ever reaches
    # the agents (neutralises obvious prompt-injection phrases, limits length).
    question = sanitize_untrusted_text(raw_question)
    if not question:
        return JSONResponse(status_code=400, content={"error": "Question is required."})

    mode = MODE_MAP.get((req.mode or "normal").lower(), "normal")
    user_id = resolve_user(req.token, req.user_id)

    # Persist the user + question.
    db.create_user(user_id, user_id)
    question_id = db.add_question(user_id, question, mode)

    # RAG: retrieve the SHARED legal memory once, organised by document_type,
    # so the Lawyer, Risk and Judge agents all receive the same context.
    rag_context = rag.retrieve_shared_memory(question)

    # Run the multi-agent pipeline.
    result = pipeline.run(question, mode, rag_context)

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
    # plain_text_answer: the clean, user-facing answer only — no JSON, no trace.
    result["plain_text_answer"] = result["final_answer"]
    return result


@app.post("/upload")
async def upload(
    user_id: str = Form("anon"),
    token: Optional[str] = Form(default=None),
    document_type: str = Form(default=DEFAULT_DOCUMENT_TYPE),
    file: UploadFile = File(...),
):
    """Receive a PDF (law file / past case), store it, extract + chunk for RAG."""
    user_id = resolve_user(token, user_id)
    contents = await file.read()
    try:
        return _process_pdf_upload(
            user_id, file.filename or "document.pdf", contents, document_type)
    except ValueError as exc:
        return JSONResponse(status_code=400,
                            content={"success": False, "message": str(exc)})
    except Exception:  # noqa: BLE001 - never return a stack trace to the frontend
        return JSONResponse(status_code=500, content={
            "success": False, "message": "Upload failed. Please try again."})


@app.post("/admin/upload-knowledge")
async def admin_upload_knowledge(
    document_type: str = Form(default=DEFAULT_DOCUMENT_TYPE),
    admin_password: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
):
    """
    ADMIN-only knowledge upload: load law references and past winning/losing
    case PDFs into the SAME shared RAG knowledge base the Lawyer, Risk and Judge
    agents read from. Optional admin password (only enforced if ADMIN_PASSWORD
    is set in .env). Reuses the existing RAGService extraction + chunking.
    """
    if ADMIN_PASSWORD and (admin_password or "").strip() != ADMIN_PASSWORD:
        return JSONResponse(status_code=401, content={
            "success": False, "message": "Invalid admin password."})

    contents = await file.read()
    try:
        # Admin knowledge is stored under the shared "admin" owner; RAG retrieval
        # searches all chunks by document_type, so every user benefits from it.
        return _process_pdf_upload(
            "admin", file.filename or "document.pdf", contents, document_type)
    except ValueError as exc:
        return JSONResponse(status_code=400,
                            content={"success": False, "message": str(exc)})
    except Exception:  # noqa: BLE001 - never return a stack trace to the frontend
        return JSONResponse(status_code=500, content={
            "success": False, "message": "Upload failed. Please try again."})


@app.get("/history")
def history(user_id: str = "anon",
           token: Optional[str] = None,
           authorization: Optional[str] = Header(default=None)):
    """Return previous questions and final answers for the logged-in user."""
    tok = _token_from_header(authorization) or token
    resolved = resolve_user(tok, user_id)
    return {"user_id": resolved, "history": db.get_history(resolved)}


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
