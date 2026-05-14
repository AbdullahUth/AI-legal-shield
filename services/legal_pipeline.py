"""
legal_pipeline.py
-----------------
LegalPipeline: orchestrates the three agents (Lawyer, Risk, Judge).

Flow (see the project brief for the full description):
  1. Lawyer writes the first draft  +  Risk builds the FIXED checklist.
  2. Lawyer <-> Risk loop until Risk approves (or the limit is hit).
       -> on limit: Emergency Function 1 (Risk Completion Patch).
  3. Lawyer <-> Judge loop. Every Lawyer revision must re-pass Risk before
     going back to the Judge.
       -> on limit: Emergency Function 2 (Final Judge Patch).
  4. Parse the final draft into clean sections and return structured data
     plus a full agent_trace.

Every visible step is recorded in `agent_trace` (drafts, checklist, feedback,
approvals, rejections, emergency notes) — never hidden chain-of-thought.
"""

from datetime import datetime

from agents import LawyerAgent, RiskAgent, JudgeAgent
from parsing import (
    DISCLAIMER,
    parse_sections,
    normalize_sections,
    format_final_answer,
)

# ---------------------------------------------------------------------------
# Iteration limits — configurable constants, NOT hardcoded all over the place.
# The Lawyer<->Risk loop always gets MORE iterations than the Lawyer<->Judge
# loop, because the Lawyer is the weaker agent and leans on the checklist.
# ---------------------------------------------------------------------------
MODE_LIMITS = {
    "quick":    {"risk_max": 8,  "judge_max": 3},
    "normal":   {"risk_max": 20, "judge_max": 8},
    "thinking": {"risk_max": 30, "judge_max": 15},
}
DEFAULT_MODE = "normal"

EMERGENCY_RISK_NOTE = (
    "Risk checklist limit reached. Emergency Risk Completion Patch was activated."
)
EMERGENCY_JUDGE_NOTE = (
    "Judge loop limit reached. Emergency Final Judge Patch was activated."
)


class LegalPipeline:
    def __init__(self, llm):
        self.lawyer = LawyerAgent(llm)
        self.risk = RiskAgent(llm)
        self.judge = JudgeAgent(llm)

    # ------------------------------------------------------------------
    def run(self, question, mode, rag_chunks):
        mode = mode if mode in MODE_LIMITS else DEFAULT_MODE
        limits = MODE_LIMITS[mode]
        context = _format_context(rag_chunks)

        trace = []
        step = {"n": 0}

        def record(phase, agent, iteration, status, message,
                   approved=None, emergency_used=False):
            step["n"] += 1
            trace.append({
                "step_number": step["n"],
                "phase": phase,
                "agent": agent,
                "iteration": iteration,
                "status": status,
                "message": message,
                "approved": approved,
                "emergency_used": emergency_used,
                "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
            })

        # --- Step 1: Lawyer first draft + Risk fixed checklist -----------
        # (These two tasks are independent and could run in parallel.)
        draft = self.lawyer.draft(question, context)
        record("draft", "Lawyer", 1, "created",
               "Lawyer created the initial legal draft.\n\n" + draft)

        checklist = self.risk.create_checklist(question, context)
        record("checklist", "Risk", 1, "created",
               "Risk created the fixed checklist (this stays fixed for the "
               "whole process).\n\n" + checklist)

        emergency_notes = []
        last_missing = []

        # --- Step 2: Lawyer <-> Risk optimization loop -------------------
        risk_approved = False
        risk_iteration = 0
        while risk_iteration < limits["risk_max"]:
            risk_iteration += 1
            review = self.risk.review(draft, checklist, iteration=risk_iteration)
            if review["approved"]:
                record("risk_review", "Risk", risk_iteration, "approved",
                       "Risk approved the draft — it satisfies the fixed "
                       "checklist.\n\n" + review["feedback"], approved=True)
                risk_approved = True
                break

            last_missing = review["missing"]
            record("risk_review", "Risk", risk_iteration, "rejected",
                   "Risk rejected the draft: missing or weak checklist "
                   "items.\n\n" + review["feedback"], approved=False)

            draft = self.lawyer.revise(
                question, draft, review["feedback"], checklist, context, source="Risk")
            record("lawyer_revision", "Lawyer", risk_iteration, "revised",
                   "Lawyer improved the draft using Risk feedback.\n\n" + draft)

        # --- Emergency Function 1: Risk Completion Patch -----------------
        if not risk_approved:
            draft = self.risk.patch(draft, checklist, last_missing)
            emergency_notes.append(EMERGENCY_RISK_NOTE)
            record("emergency", "Risk", risk_iteration, "patched",
                   EMERGENCY_RISK_NOTE + "\nRisk directly added the missing "
                   "checklist points to the draft.\n\n" + draft,
                   approved=True, emergency_used=True)

        # --- Step 3: Lawyer <-> Judge loop -------------------------------
        judge_approved = False
        judge_iteration = 0
        last_judge_feedback = ""
        while judge_iteration < limits["judge_max"]:
            judge_iteration += 1
            judgement = self.judge.review(question, draft, iteration=judge_iteration)
            if judgement["approved"]:
                record("judge_review", "Judge", judge_iteration, "approved",
                       "Judge approved the final answer.\n\n" + judgement["feedback"],
                       approved=True)
                judge_approved = True
                break

            last_judge_feedback = judgement["feedback"]
            record("judge_review", "Judge", judge_iteration, "rejected",
                   "Judge rejected the draft.\n\n" + judgement["feedback"],
                   approved=False)

            # Lawyer improves using Judge feedback ...
            draft = self.lawyer.revise(
                question, draft, judgement["feedback"], checklist, context, source="Judge")
            record("lawyer_revision", "Lawyer", judge_iteration, "revised",
                   "Lawyer improved the draft using Judge feedback.\n\n" + draft)

            # ... and the new draft MUST re-pass Risk before returning to Judge.
            recheck = self.risk.review(draft, checklist, iteration=2)
            if recheck["approved"]:
                record("risk_recheck", "Risk", judge_iteration, "approved",
                       "Risk rechecked the revised draft — no checklist point "
                       "was removed or weakened.\n\n" + recheck["feedback"],
                       approved=True)
            else:
                draft = self.risk.patch(draft, checklist, recheck["missing"])
                record("risk_recheck", "Risk", judge_iteration, "patched",
                       "Risk rechecked the revised draft, found a weakened "
                       "checklist point, and patched it back in.\n\n"
                       + recheck["feedback"], approved=True)

        # --- Emergency Function 2: Final Judge Patch ---------------------
        if not judge_approved:
            # Lawyer applies the Judge feedback one last time ...
            draft = self.lawyer.revise(
                question, draft, last_judge_feedback or "Improve overall clarity "
                "and usefulness.", checklist, context, source="Judge")
            record("emergency", "Lawyer", judge_iteration, "final-revision",
                   "Lawyer applied the Judge's feedback one final time while "
                   "preserving every checklist point.\n\n" + draft,
                   emergency_used=True)

            # ... and Risk does one final safety/checklist pass.
            final_check = self.risk.review(draft, checklist, iteration=2)
            if not final_check["approved"]:
                draft = self.risk.patch(draft, checklist, final_check["missing"])
            emergency_notes.append(
                EMERGENCY_JUDGE_NOTE + " The answer is returned even though it "
                "may still have unresolved issues.")
            record("emergency", "Risk", judge_iteration, "final-pass",
                   EMERGENCY_JUDGE_NOTE + "\nRisk performed one final checklist "
                   "pass before returning the answer.\n\n" + draft,
                   approved=True, emergency_used=True)

        # --- Step 4: Build the clean final answer ------------------------
        sections = normalize_sections(parse_sections(draft))
        final_answer = format_final_answer(sections, DISCLAIMER, emergency_notes)

        return {
            # Structured fields required by POST /ask:
            "summary": sections["summary"],
            "legal_explanation": sections["legal_explanation"],
            "important_risks": sections["important_risks"],
            "missing_information": sections["missing_information"],
            "next_steps": sections["next_steps"],
            "documents_to_collect": sections["documents_to_collect"],
            "disclaimer": DISCLAIMER,
            "emergency_notes": emergency_notes,
            "agent_trace": trace,
            # Extra fields the existing frontend uses for the clean answer
            # bubble, the live courtroom animation, and the notes card:
            "final_answer": final_answer,
            "trial_chat": _build_trial_chat(trace),
            "warnings": emergency_notes,
            "used_facts": [c[:160] + ("..." if len(c) > 160 else "")
                           for c in (rag_chunks or [])],
            "mode": mode,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _format_context(rag_chunks):
    if not rag_chunks:
        return ""
    parts = [f"[Document excerpt {i}]\n{c}" for i, c in enumerate(rag_chunks, 1)]
    return "\n\n".join(parts)


# Short, friendly one-liners for the live "courtroom" animation in the UI.
_TRIAL_LINES = {
    ("draft", "created"): "I have prepared the initial draft of your legal guidance.",
    ("checklist", "created"): "Here is the fixed checklist the final answer must satisfy.",
    ("risk_review", "approved"): "The draft satisfies the checklist. Approved.",
    ("risk_review", "rejected"): "The draft is missing required checklist points — sending it back.",
    ("lawyer_revision", "revised"): "I have revised the draft to address the feedback.",
    ("risk_recheck", "approved"): "Rechecked — no checklist point was weakened. Approved.",
    ("risk_recheck", "patched"): "Rechecked — I patched a weakened checklist point back in.",
    ("judge_review", "approved"): "The answer is clear, balanced and complete. Approved.",
    ("judge_review", "rejected"): "I have quality concerns with this draft — sending it back.",
    ("emergency", "patched"): "Iteration limit reached — I patched the missing points directly.",
    ("emergency", "final-revision"): "Applying the final round of feedback before we close.",
    ("emergency", "final-pass"): "Final checklist pass complete — returning the answer.",
}


def _build_trial_chat(trace):
    """Turn the detailed trace into short 'Speaker: line' strings for the UI."""
    lines = []
    for item in trace:
        text = _TRIAL_LINES.get(
            (item["phase"], item["status"]),
            item["message"].split("\n", 1)[0],
        )
        lines.append(f"{item['agent']}: {text}")
    return lines
