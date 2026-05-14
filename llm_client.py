"""
llm_client.py
-------------
One simple LLM client that supports four providers:

  1. openrouter  -> PRESENTATION PROVIDER (final hackathon demo)
  2. gemini      -> TEST PROVIDER (development only)
  3. local       -> OpenAI-compatible local API (Podman AI Lab, Ollama, etc.)
  4. mock        -> no keys, fake-but-realistic output, zero token cost

The provider is chosen with the LLM_PROVIDER env var. If MOCK_MODE=true, or if
the selected provider has no API key, the client automatically falls back to
mock mode so the full pipeline always runs.
"""

import os
import requests
from dotenv import load_dotenv

# Load variables from the local .env file (never committed to git).
load_dotenv()

# ---------------------------------------------------------------------------
# Configuration (everything comes from environment variables / .env)
# ---------------------------------------------------------------------------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock").strip().lower()
MOCK_MODE = os.getenv("MOCK_MODE", "false").strip().lower() == "true"

# PRESENTATION PROVIDER:
# OpenRouter is used for the final hackathon demo.
# The real key must come from OPENROUTER_API_KEY in .env.
# Never paste the real key directly in this file.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# TEST PROVIDER:
# Gemini is only for testing during development.
# This section can be safely deleted later if we only use OpenRouter.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()

# Local OpenAI-compatible API (Podman AI Lab / Ollama / LM Studio ...).
LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1").strip()
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "llama3").strip()

# Optional plain OpenAI key.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

REQUEST_TIMEOUT = 90  # seconds


def _effective_provider():
    """Decide which provider we will actually use (with mock fallbacks)."""
    if MOCK_MODE:
        return "mock"
    if LLM_PROVIDER == "openrouter":
        return "openrouter" if OPENROUTER_API_KEY else "mock"
    if LLM_PROVIDER == "gemini":
        return "gemini" if GEMINI_API_KEY else "mock"
    if LLM_PROVIDER == "local":
        return "local"  # local servers usually need no key
    if LLM_PROVIDER == "openai":
        return "openai" if OPENAI_API_KEY else "mock"
    if LLM_PROVIDER == "mock":
        return "mock"
    # Unknown provider -> safest option.
    return "mock"


def get_provider_info():
    """Small dict used by the /health endpoint so the team can see the setup."""
    provider = _effective_provider()
    model = {
        "openrouter": OPENROUTER_MODEL,
        "gemini": GEMINI_MODEL,
        "local": LOCAL_LLM_MODEL,
        "openai": "gpt-4o-mini",
        "mock": "mock-model",
    }.get(provider, "mock-model")
    return {
        "configured_provider": LLM_PROVIDER,
        "effective_provider": provider,
        "model": model,
        "mock_mode": provider == "mock",
    }


class LLMClient:
    """Thin wrapper. Call .chat(system, user) and get back plain text."""

    def __init__(self):
        self.provider = _effective_provider()

    def chat(self, system, user, task=None, iteration=1, temperature=0.4):
        """
        Send a system + user message and return the model's text reply.
        `task` and `iteration` are only used by mock mode to produce
        realistic, stage-aware fake output.
        """
        try:
            if self.provider == "openrouter":
                return self._openrouter(system, user, temperature)
            if self.provider == "gemini":
                return self._gemini(system, user, temperature)
            if self.provider == "local":
                return self._openai_compatible(
                    LOCAL_LLM_BASE_URL, "", LOCAL_LLM_MODEL, system, user, temperature
                )
            if self.provider == "openai":
                return self._openai_compatible(
                    "https://api.openai.com/v1",
                    OPENAI_API_KEY,
                    "gpt-4o-mini",
                    system,
                    user,
                    temperature,
                )
            return _mock_response(task, user, iteration)
        except Exception as exc:  # noqa: BLE001 - keep the demo alive
            print(f"[llm_client] Provider '{self.provider}' failed: {exc}. "
                  f"Falling back to mock output for task '{task}'.")
            return _mock_response(task, user, iteration)

    # -- OpenRouter -------------------------------------------------------
    # PRESENTATION PROVIDER: uses the OpenAI-compatible chat completions API.
    def _openrouter(self, system, user, temperature):
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            # Optional but recommended by OpenRouter:
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "AI Legal Shield",
        }
        payload = {
            "model": OPENROUTER_MODEL,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        resp = requests.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    # -- Generic OpenAI-compatible (local / openai) -----------------------
    def _openai_compatible(self, base_url, api_key, model, system, user, temperature):
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        resp = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    # -- Gemini -----------------------------------------------------------
    # TEST PROVIDER: this whole method can be safely deleted later if we
    # only ever use OpenRouter for the presentation.
    def _gemini(self, system, user, temperature):
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": temperature},
        }
        resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()


# ---------------------------------------------------------------------------
# MOCK MODE
# Returns fake-but-realistic, stage-aware output so the entire multi-agent
# pipeline (including the database and the agent trace) can be demoed without
# spending a single paid token.
# ---------------------------------------------------------------------------
def _extract_line(marker, text):
    idx = text.find(marker)
    if idx == -1:
        return ""
    seg = text[idx + len(marker):]
    return seg.splitlines()[0].strip() if seg else ""


def _mock_draft(question, revised=False):
    extra_risk = ""
    extra_step = ""
    if revised:
        extra_risk = "\n- Relying only on verbal agreements makes your position harder to prove."
        extra_step = "\n- Put any future agreements or important points in writing."
    return f"""SUMMARY: This is general legal information about your question: "{question}". \
The guidance below explains the key legal principles involved, the main risks, \
what information is still missing, and the practical steps you can take next.

LEGAL EXPLANATION: Your situation touches on several common legal principles. \
In general terms, your rights and obligations depend on the specific facts, the \
jurisdiction that applies to you, and any contracts or agreements already in \
place. The law usually tries to balance the interests of everyone involved, and \
the outcome of a real case can change significantly depending on documentation, \
evidence, and deadlines. Because this is general information, the explanation \
focuses on widely-applicable principles rather than a definitive ruling on your \
particular case.

IMPORTANT RISKS:
- Acting before you have all the facts could weaken your legal position.
- Missing a filing deadline or legal time limit may permanently remove options.
- Informal messages and emails can later be used as evidence by either side.{extra_risk}

MISSING INFORMATION:
- The country or state whose laws apply to your situation.
- Any written contracts, notices, or agreements connected to the matter.
- A clear timeline of key dates and what happened.

NEXT STEPS:
- Gather and organize every document and communication related to the issue.
- Write down a clear timeline of events while the details are still fresh.
- Consult a licensed attorney in your jurisdiction for advice on your specific case.{extra_step}

DOCUMENTS TO COLLECT:
- Any contracts, agreements, or terms you signed or received.
- Emails, letters, and messages relating to the dispute or issue.
- Official notices, receipts, payslips, or records that support your account."""


def _mock_checklist():
    return (
        "- The answer must clearly explain the main legal principles involved.\n"
        "- The answer must list the important legal risks for the user.\n"
        "- The answer must identify what information the user still needs to provide.\n"
        "- The answer must point out possible weak areas in the user's position.\n"
        "- The answer must give practical, concrete next steps.\n"
        "- The answer must list documents and evidence the user should collect.\n"
        "- The answer must include any urgency or safety warnings if relevant.\n"
        "- The answer must include a clear disclaimer that this is general legal "
        "information, not official legal advice.\n"
        "- The answer must avoid overclaiming or guaranteeing any legal outcome."
    )


def _mock_judge_prep():
    return (
        "WINNING PATTERNS:\n"
        "Similar arguments tended to succeed when the answer was specific about "
        "the governing rules, backed claims with concrete evidence, and set "
        "realistic expectations instead of guaranteeing an outcome.\n\n"
        "LOSING PATTERNS:\n"
        "Similar arguments tended to fail when key facts or deadlines were "
        "missing, when the reasoning overclaimed, or when no supporting "
        "documents were identified.\n\n"
        "THE FINAL ANSWER MUST AVOID:\n"
        "Vague generalities, overconfident promises, and ignoring missing "
        "information.\n\n"
        "STRONG REASONING SHOULD INCLUDE:\n"
        "Clear principles, the limits of general legal information, concrete "
        "next steps, and the evidence the user should gather.\n\n"
        "REVIEW CRITERIA:\n"
        "Clarity, logical structure, completeness, balance, usefulness, and "
        "whether the answer actually addresses the user's question."
    )


def _mock_response(task, user_text, iteration):
    question = _extract_line("QUESTION:", user_text) or "your legal matter"

    if task == "risk_checklist":
        return _mock_checklist()

    if task == "judge_prepare":
        return _mock_judge_prep()

    if task == "lawyer_draft":
        return _mock_draft(question, revised=False)

    if task == "lawyer_revise":
        return _mock_draft(question, revised=True)

    if task == "risk_review":
        # First pass rejects (so the trace shows a real loop); later passes pass.
        if iteration >= 2:
            return "APPROVED\nThe draft now satisfies every item on the fixed checklist."
        return (
            "REJECTED\n"
            "- The documents and evidence the user should collect are not specific enough.\n"
            "- The answer should state more clearly what information is still missing.\n"
            "- The disclaimer should be stated more explicitly."
        )

    if task == "judge_review":
        if iteration >= 2:
            return "APPROVED\nThe answer is clear, well structured, balanced, and complete."
        return (
            "REJECTED\n"
            "The summary is a little vague and the legal explanation could be clearer. "
            "Please make the recommended next steps more concrete and easier to act on."
        )

    if task == "risk_patch":
        # Emergency patch: keep the draft, just make sure it is complete.
        draft = ""
        idx = user_text.find("DRAFT:")
        if idx != -1:
            draft = user_text[idx + len("DRAFT:"):].strip()
        return draft or _mock_draft(question, revised=True)

    # Fallback.
    return _mock_draft(question, revised=False)
