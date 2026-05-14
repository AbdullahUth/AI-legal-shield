"""
judge_agent.py
--------------
JudgeAgent: the final quality reviewer.

The Judge only ever sees a draft that has ALREADY passed the Risk Agent.
It judges overall quality — clarity, structure, completeness, usefulness,
balance, and whether the answer actually answers the user's question — and
either APPROVES it or REJECTS it with specific feedback for the Lawyer Agent.

The Judge never edits the draft itself and never touches the fixed checklist.
"""

from parsing import parse_review

JUDGE_SYSTEM = """You are the Judge Agent in the AI Legal Shield system.

You review a draft that has ALREADY passed the Risk Agent's checklist.
Judge the OVERALL QUALITY of the answer:
- clarity and readability
- logical structure
- completeness
- usefulness to the user
- balance (not one-sided, not overconfident)
- does it actually answer the user's question?
- is the reasoning understandable?
- is it safe and not overconfident?

Respond like this:
- The FIRST line must be exactly APPROVED or REJECTED.
- If REJECTED, give specific, actionable feedback the Lawyer Agent can use.
- If APPROVED, briefly say why the answer is good enough.
You do NOT edit the draft yourself. No JSON, no markdown symbols like * or #."""


class JudgeAgent:
    name = "Judge"

    def __init__(self, llm):
        self.llm = llm

    def review(self, question, draft, iteration=1):
        """Judge the overall quality of a Risk-approved draft. Returns a dict."""
        user = (
            f"QUESTION: {question}\n\n"
            f"DRAFT (already approved by the Risk Agent):\n{draft}\n\n"
            "Review the overall quality of this answer."
        )
        raw = self.llm.chat(JUDGE_SYSTEM, user, task="judge_review", iteration=iteration)
        return parse_review(raw)
