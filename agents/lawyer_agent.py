"""
lawyer_agent.py
---------------
LawyerAgent: writes and improves the legal draft.

The Lawyer always answers using a fixed set of section headers so the rest of
the system can parse the draft into clean sections (no JSON ever shown to the
user). It uses RAG context when available and improves drafts based on Risk or
Judge feedback.
"""

# Required section headers. Keep these EXACT — parsing.py depends on them.
_SECTIONS = (
    "SUMMARY:, LEGAL EXPLANATION:, IMPORTANT RISKS:, MISSING INFORMATION:, "
    "NEXT STEPS:, DOCUMENTS TO COLLECT:"
)

SYSTEM_PROMPT = f"""You are the Lawyer Agent in a multi-agent legal assistant called AI Legal Shield.

Your job:
- Write clear, helpful GENERAL legal information in plain, simple language.
- You are NOT a real lawyer and must never pretend to be one or guarantee outcomes.
- Use any provided document context, but never invent facts that were not given.
- Always include practical, concrete next steps the user can actually take.
- When you receive Risk or Judge feedback, improve the draft to address it.

Formatting rules (very important):
- Respond using EXACTLY these section headers, each on its own line, in capitals:
  {_SECTIONS}
- Use simple "-" bullets inside IMPORTANT RISKS, MISSING INFORMATION, NEXT STEPS
  and DOCUMENTS TO COLLECT.
- SUMMARY and LEGAL EXPLANATION are short plain-text paragraphs.
- Do NOT use markdown symbols like *, **, ***, or #. Do NOT output JSON.
- Do NOT add any sections beyond the six listed above."""


class LawyerAgent:
    name = "Lawyer"

    def __init__(self, llm):
        self.llm = llm

    def draft(self, question, context):
        """Create the very first legal draft from the question (+ RAG context)."""
        user = (
            f"QUESTION: {question}\n\n"
            f"CONTEXT FROM UPLOADED DOCUMENTS:\n{context or 'None provided.'}\n\n"
            "Write the first complete legal draft using the required section headers."
        )
        return self.llm.chat(SYSTEM_PROMPT, user, task="lawyer_draft")

    def revise(self, question, draft, feedback, checklist, context, source="Risk"):
        """Improve the draft using feedback from the Risk or Judge agent."""
        user = (
            f"QUESTION: {question}\n\n"
            f"CONTEXT FROM UPLOADED DOCUMENTS:\n{context or 'None provided.'}\n\n"
            f"CURRENT DRAFT:\n{draft}\n\n"
            f"FIXED RISK CHECKLIST (every point must stay satisfied):\n{checklist}\n\n"
            f"{source.upper()} FEEDBACK TO ADDRESS:\n{feedback}\n\n"
            "Improve the draft so it fully addresses the feedback above. "
            "Keep every checklist point. Keep the same six section headers."
        )
        return self.llm.chat(SYSTEM_PROMPT, user, task="lawyer_revise")
