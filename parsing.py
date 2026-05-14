"""
parsing.py
----------
Small helper module shared by the agents and the pipeline.

It turns the plain-text agent outputs into structured data WITHOUT ever
showing raw JSON to the user. Everything here is intentionally simple and
forgiving so the hackathon demo never crashes on a slightly odd LLM reply.
"""

import re

# The fixed disclaimer that MUST appear in every final answer.
DISCLAIMER = (
    "This response provides general legal information only. It is not official "
    "legal advice and does not create a lawyer-client relationship. AI Legal "
    "Shield is not a substitute for a licensed attorney. For decisions about "
    "your specific situation, please consult a qualified lawyer in your "
    "jurisdiction."
)

# Maps the section headers the Lawyer Agent writes -> internal field names.
_SECTION_ALIASES = {
    "summary": "summary",
    "short summary": "summary",
    "legal explanation": "legal_explanation",
    "explanation": "legal_explanation",
    "important risks": "important_risks",
    "risks": "important_risks",
    "missing information": "missing_information",
    "next steps": "next_steps",
    "recommended next steps": "next_steps",
    "documents to collect": "documents_to_collect",
    "documents/evidence to collect": "documents_to_collect",
    "documents and evidence to collect": "documents_to_collect",
    "evidence to collect": "documents_to_collect",
}

# These sections are rendered as bullet lists; the rest are paragraphs.
_LIST_SECTIONS = {
    "important_risks",
    "missing_information",
    "next_steps",
    "documents_to_collect",
}


def parse_sections(text):
    """Parse a Lawyer draft (labelled sections) into a dict of fields."""
    text = text or ""
    result = {}
    current = None
    buf = []

    def flush():
        if current is None:
            return
        content = "\n".join(buf).strip()
        if current in _LIST_SECTIONS:
            items = []
            for ln in content.splitlines():
                ln = re.sub(r"^[-*•]\s*", "", ln.strip())
                if ln:
                    items.append(ln)
            result[current] = items
        else:
            result[current] = content

    for raw_line in text.splitlines():
        line = raw_line.strip()
        matched = None
        rest = ""

        # Case 1: "HEADER: some text on the same line"
        if ":" in line:
            head, _, after = line.partition(":")
            key = head.strip().lower()
            if key in _SECTION_ALIASES:
                matched = _SECTION_ALIASES[key]
                rest = after.strip()

        # Case 2: "HEADER" alone on its own line
        if matched is None and line.lower() in _SECTION_ALIASES:
            matched = _SECTION_ALIASES[line.lower()]

        if matched:
            flush()
            current = matched
            buf = [rest] if rest else []
        elif current is not None:
            buf.append(raw_line)

    flush()
    return result


def parse_review(raw):
    """
    Parse an APPROVED / REJECTED review from the Risk or Judge agent.
    Returns {"approved": bool, "feedback": str, "missing": [str, ...]}.
    """
    raw = (raw or "").strip()
    lines = [l for l in raw.splitlines() if l.strip()]
    approved = bool(lines) and lines[0].strip().upper().startswith("APPROVED")

    body = lines[1:] if len(lines) > 1 else (lines if not approved else [])
    missing = [
        re.sub(r"^[-*•]\s*", "", l.strip())
        for l in body
        if l.strip().startswith(("-", "*", "•"))
    ]
    feedback = "\n".join(body).strip()
    if not feedback:
        feedback = (
            "All checklist items are satisfied."
            if approved
            else "Some required points still need to be addressed."
        )
    return {"approved": approved, "feedback": feedback, "missing": missing}


def _as_list(value):
    if isinstance(value, list):
        return value
    if not value:
        return []
    return [value]


def normalize_sections(sections):
    """Guarantee every expected field exists, with sensible fallbacks."""
    return {
        "summary": sections.get("summary")
        or "A short summary could not be generated for this question.",
        "legal_explanation": sections.get("legal_explanation")
        or "A detailed legal explanation could not be generated for this question.",
        "important_risks": _as_list(sections.get("important_risks"))
        or ["No specific risks were identified — this does not mean none exist."],
        "missing_information": _as_list(sections.get("missing_information"))
        or ["No missing information was identified."],
        "next_steps": _as_list(sections.get("next_steps"))
        or ["Consider consulting a licensed attorney about your situation."],
        "documents_to_collect": _as_list(sections.get("documents_to_collect"))
        or ["Any documents, contracts, or communications related to your situation."],
    }


def format_final_answer(sections, disclaimer, emergency_notes):
    """
    Build the clean, human-readable final answer string.
    No JSON, no markdown chaos, no '***' — just clear section titles.
    """
    lines = []

    def add_text(title, body):
        lines.append(title.upper())
        lines.append(str(body).strip())
        lines.append("")

    def add_list(title, items):
        lines.append(title.upper())
        for item in items:
            lines.append("  - " + str(item).strip())
        lines.append("")

    add_text("Short Summary", sections["summary"])
    add_text("Legal Explanation", sections["legal_explanation"])
    add_list("Important Risks", sections["important_risks"])
    add_list("Missing Information", sections["missing_information"])
    add_list("Recommended Next Steps", sections["next_steps"])
    add_list("Documents / Evidence to Collect", sections["documents_to_collect"])

    if emergency_notes:
        add_text("Note", " ".join(emergency_notes))

    add_text("Disclaimer", disclaimer)
    return "\n".join(lines).strip()
