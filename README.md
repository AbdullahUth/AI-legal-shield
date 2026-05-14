# AI Legal Shield

A hackathon legal assistant (HackAgents BIU 2026) that uses **three AI agents** —
a **Lawyer**, a **Risk** agent, and a **Judge** — to produce safer, clearer, and
more complete **general legal information**.

> **Disclaimer:** AI Legal Shield provides *general legal information only*. It is
> **not** official legal advice and is **not** a substitute for a licensed lawyer.
> Every answer ends with this disclaimer.

---

## What it does

1. You ask a legal question and pick a mode (**quick / normal / thinking**).
2. The **Lawyer Agent** writes a first draft. In parallel, the **Risk Agent**
   builds a *fixed checklist* of everything the answer must contain.
3. **Lawyer ↔ Risk loop:** Risk checks the draft against the fixed checklist and
   sends it back until it is approved (or the iteration limit triggers the
   *Emergency Risk Completion Patch*).
4. **Lawyer ↔ Judge loop:** the Judge reviews overall quality. Every Lawyer
   revision must re-pass Risk before returning to the Judge. If the limit is
   hit, the *Emergency Final Judge Patch* runs so the system never gets stuck.
5. You get a clean, sectioned answer — and an optional **Show Agent Trace** panel
   with the full visible agent conversation.

Uploaded **PDFs** are chunked and stored in **SQLite**, then used as **RAG**
context for the Lawyer and Risk agents. The system works fine with no PDFs too.

---

## Project structure

```
main.py                 FastAPI app + endpoints + serves the frontend
database.py             DatabaseService - SQLite (6 tables)
rag_service.py          RAGService - PDF text extraction, chunking, keyword search
llm_client.py           LLMClient - openrouter / gemini / local / mock
parsing.py              Shared parsing + clean-output helpers
agents/
  lawyer_agent.py       LawyerAgent
  risk_agent.py         RiskAgent
  judge_agent.py        JudgeAgent
services/
  legal_pipeline.py     LegalPipeline - orchestrates the 3 agents + emergencies
index.html app.js styles.css   Existing frontend (only lightly modified)
uploads/                Uploaded PDFs (created at runtime)
requirements.txt  .env.example  .gitignore  README.md
```

---

## Run it on Windows

Open **PowerShell** in this folder.

### 1. Install dependencies

```powershell
pip install -r requirements.txt
```

### 2. Create your `.env`

```powershell
copy .env.example .env
```

Then edit `.env` (see the modes below).

### 3. Start the backend

```powershell
uvicorn main:app --reload
```

### 4. Open the frontend

Open <http://127.0.0.1:8000> in your browser. The backend serves the frontend,
so everything works from one URL. (You can also open `index.html` directly as a
file — CORS is enabled — but serving it from the backend is recommended.)

---

## `.env` configuration

### Mock mode — no tokens, no keys (great for development/testing)

```
LLM_PROVIDER=mock
MOCK_MODE=true
```

The full pipeline still runs (agents, loops, emergencies, database, agent trace)
using realistic fake output. **Zero token cost.**

### OpenRouter — PRESENTATION mode (final hackathon demo)

```
LLM_PROVIDER=openrouter
MOCK_MODE=false
OPENROUTER_API_KEY=your_real_presentation_key
OPENROUTER_MODEL=openai/gpt-4o-mini
```

> Put the **real key only in `.env`** (which is git-ignored). Never commit it.

### Gemini — TEST mode (development only)

```
LLM_PROVIDER=gemini
MOCK_MODE=false
GEMINI_API_KEY=your_test_gemini_key
GEMINI_MODEL=gemini-1.5-flash
```

The Gemini section in `llm_client.py` is clearly marked as a **TEST PROVIDER**
and can be safely deleted later if you only use OpenRouter.

### Local model (Podman AI Lab / Ollama / LM Studio)

```
LLM_PROVIDER=local
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=llama3
```

If a provider is selected but its key is missing, the client automatically
falls back to **mock mode** so the demo never breaks.

---

## API endpoints

| Method | Path       | Purpose                                              |
|--------|------------|------------------------------------------------------|
| GET    | `/health`  | Backend status + active LLM provider                 |
| POST   | `/ask`     | Run the multi-agent pipeline, return a clean answer  |
| POST   | `/upload`  | Upload a PDF (multipart: `user_id`, `file`)          |
| GET    | `/history` | Previous questions + final answers (`?user_id=...`)  |

`POST /ask` returns: `summary`, `legal_explanation`, `important_risks`,
`missing_information`, `next_steps`, `documents_to_collect`, `disclaimer`,
`emergency_notes`, `agent_trace` (plus `final_answer`, `trial_chat` for the UI).

---

## Testing

### Example legal questions

- "Can my employer fire me for refusing to work weekends?"
- "What should I do if I received a cease and desist letter?"
- "How do I protect my startup's intellectual property?"
- "My landlord is keeping my security deposit — what are my options?"

### Test the chat flow

1. Open <http://127.0.0.1:8000>, enter a name, click **Begin Consultation**.
2. Pick a mode (Quick / Normal / Thinking), type a question, press **Send**.
3. Watch the live courtroom animation, read the clean sectioned answer.
4. Click **🔍 Show Agent Trace** to see every Lawyer/Risk/Judge step.

### Test PDF upload (RAG)

1. In the consultation screen, click **Attach PDF** and pick any `.pdf`.
2. You'll see `✓ filename — N chunk(s) ready`.
3. Ask a question related to the document — the agents now use it as context.

### Test history

Click **History** to load your previous questions and their final answers.

### Quick API check (PowerShell)

```powershell
curl http://127.0.0.1:8000/health
```

---

## Notes

- Database file `legal_shield.db` is created automatically on first run.
- The frontend was **not** rebuilt — only `app.js` was modified for backend
  connection, plus minimal `index.html` / `styles.css` changes for the PDF
  upload control, the 3-mode selector, and the Show Agent Trace panel.
