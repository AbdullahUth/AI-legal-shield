"""
risk_agent.py
-------------
RiskAgent: the safety / completeness agent.

It does THREE distinct jobs (each with its own prompt):
  1. create_checklist() -> builds the FIXED checklist once, at the start.
  2. review()           -> checks a draft against that fixed checklist.
  3. patch()            -> emergency: directly adds missing checklist points.

Very important rule: the checklist is created ONCE and never rewritten during
the loop. review() only checks compliance — it must not invent a new checklist.
"""

from parsing import parse_review

CHECKLIST_SYSTEM = """You are the Risk Agent in the AI Legal Shield system.

Right now you are in CHECKLIST mode. You have NOT seen any draft yet.
Create a FIXED checklist of everything the final answer MUST contain.

The checklist must cover:
- important legal risks that must be mentioned
- key points that must be addressed
- required disclaimers (general legal information, not official legal advice)
- information the user still needs to provide
- possible weak areas in the user's position
- safety or urgency warnings, if relevant
- evidence / documents the user should collect
- practical next steps that must appear in the answer

Output ONLY a list of short "-" bullet points. No headers, no JSON, no markdown
symbols like * or #. This checklist will stay FIXED for the whole process."""

REVIEW_SYSTEM = """You are the Risk Agent in the AI Legal Shield system.

You are in REVIEW mode. You are given a FIXED checklist and a draft answer.
Do NOT create a new checklist. Only check whether the draft satisfies the
existing checklist.

Check carefully:
- Does the draft cover every required checklist point?
- Does it mention the important risks?
- Does it avoid overclaiming or guaranteeing outcomes?
- Does it clearly state what information is still missing?
- Does it include the required disclaimer?
- Does it give practical next steps?
- Did the draft remove or weaken any required checklist item?

Respond like this:
- The FIRST line must be exactly APPROVED or REJECTED.
- If REJECTED, list the missing or weak checklist items as short "-" bullets.
- If APPROVED, briefly say the checklist is fully satisfied.
No JSON, no markdown symbols like * or #."""

PATCH_SYSTEM = """You are the Risk Agent performing an EMERGENCY COMPLETION PATCH.

You are given a FIXED checklist, a list of missing items, and the current draft.
Directly add ONLY the missing checklist points into the draft.

Rules:
- Do NOT rewrite the whole answer.
- Do NOT delete or weaken any useful existing content.
- Preserve the original structure and the six section headers
  (SUMMARY, LEGAL EXPLANATION, IMPORTANT RISKS, MISSING INFORMATION,
  NEXT STEPS, DOCUMENTS TO COLLECT).
- Only add or lightly correct what is necessary to satisfy the checklist.
- No JSON, no markdown symbols like * or #.
Return the full patched draft using the same six section headers."""


class RiskAgent:
    name = "Risk"

    def __init__(self, llm):
        self.llm = llm

    def create_checklist(self, question, context):
        """Build the fixed checklist ONCE, before any draft exists."""
        user = (
            f"QUESTION: {question}\n\n"
            f"CONTEXT FROM UPLOADED DOCUMENTS:\n{context or 'None provided.'}\n\n"
            "Create the fixed checklist now."
        )
        return self.llm.chat(CHECKLIST_SYSTEM, user, task="risk_checklist")

    def review(self, draft, checklist, iteration=1):
        """Check the draft against the fixed checklist. Returns a dict."""
        user = (
            f"FIXED CHECKLIST:\n{checklist}\n\n"
            f"DRAFT:\n{draft}\n\n"
            "Review the draft against the fixed checklist."
        )
        raw = self.llm.chat(REVIEW_SYSTEM, user, task="risk_review", iteration=iteration)
        return parse_review(raw)

    def patch(self, draft, checklist, missing_items):
        """Emergency: directly add missing checklist points into the draft."""
        missing_text = "\n".join(f"- {m}" for m in missing_items) or "- (none specified)"
        user = (
            f"FIXED CHECKLIST:\n{checklist}\n\n"
            f"MISSING ITEMS TO ADD:\n{missing_text}\n\n"
            f"DRAFT:\n{draft}"
        )
        return self.llm.chat(PATCH_SYSTEM, user, task="risk_patch")
