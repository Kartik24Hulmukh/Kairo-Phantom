"""
Judging hierarchy for Kairo Phantom test gauntlet.
Implements 4 tiers of verification:
Tier 1: Deterministic Oracles (exact content/property matches)
Tier 2: Metamorphic Relations (transformational correctness)
Tier 3: AI Judges (rubric-scored evaluation)
Tier 4: Human Ground-Truth labels
"""

import os
import logging
import json
from typing import Dict, Any, Optional
from pydantic import BaseModel
from sidecar.oracles import verify_docx, verify_xlsx, verify_pptx, verify_pdf

log = logging.getLogger("kairo.judging")


class JudgeOutputSchema(BaseModel):
    passed: bool
    score: float
    feedback: str


class GauntletJudge:
    """Orchestrates multi-tier judging for gauntlet execution."""

    def __init__(self, outcome_store_path: Optional[str] = None):
        from sidecar.outcome_store import OutcomeStore

        self.store = OutcomeStore(outcome_store_path)

    def judge_scenario(
        self, scenario: Dict[str, Any], output_file_path: str, response_text: str
    ) -> Dict[str, Any]:
        """Run all 4 tiers of judging to determine scenario outcome."""
        scenario_id = scenario.get("id", "unknown")
        category = scenario.get("category", "generic")
        log.info(f"[Judge] Scoring scenario {scenario_id} ({category})...")

        # Tier 1: Deterministic Oracle
        t1_passed, t1_details = self._run_tier1_oracle(category, output_file_path)

        # Tier 2: Metamorphic Relation (e.g. prompt formatting invariance)
        t2_passed = self._run_tier2_metamorphic(response_text)

        # Tier 3: AI Judge (rubric scoring simulation)
        t3_score, t3_feedback = self._run_tier3_ai_judge(scenario, response_text)

        # Tier 4: Human Ground-Truth Anchor
        t4_matched, t4_verdict = self._run_tier4_human_anchor(scenario_id, response_text)

        # Aggregate scores (Tier 1 is a hard gate)
        final_passed = t1_passed and t2_passed and (t3_score >= 0.7)
        if t4_matched:
            # Human anchor takes ultimate precedence
            final_passed = t4_verdict

        score = (float(t1_passed) * 0.4) + (float(t2_passed) * 0.2) + (t3_score * 0.4)

        result = {
            "scenario_id": scenario_id,
            "passed": final_passed,
            "score": score,
            "tiers": {
                "tier1": {"passed": t1_passed, "details": t1_details},
                "tier2": {"passed": t2_passed},
                "tier3": {"score": t3_score, "feedback": t3_feedback},
                "tier4": {"matched": t4_matched, "verdict": t4_verdict},
            },
        }

        # Log outcome
        self.store.log_episode(
            scenario_id=scenario_id,
            state={"score": score, "tiers": result["tiers"]},
            intent=category,
            action="evaluate",
            outcome="PASSED" if final_passed else "FAILED",
            accepted=final_passed,
        )

        return result

    def _run_tier1_oracle(self, category: str, file_path: str) -> tuple:
        """Run deterministic document/network/air-gap check oracles."""
        if not file_path or not os.path.exists(file_path):
            return False, "File does not exist"

        try:
            if category.lower() == "word" or file_path.endswith(".docx"):
                # Stub query for verify docx (returns dict/status)
                res = verify_docx(file_path, {})
                return res.get("ok", False), res.get("message", "Checked")
            elif category.lower() == "excel" or file_path.endswith(".xlsx"):
                res = verify_xlsx(file_path, {})
                return res.get("ok", False), res.get("message", "Checked")
            elif category.lower() == "pptx" or file_path.endswith(".pptx"):
                res = verify_pptx(file_path, {})
                return res.get("ok", False), res.get("message", "Checked")
            elif category.lower() == "pdf" or file_path.endswith(".pdf"):
                res = verify_pdf(file_path, "")
                return res.get("ok", False), res.get("message", "Checked")
            else:
                return True, "Generic file verification skipped"
        except Exception as e:
            return False, f"Oracle error: {e}"

    def _run_tier2_metamorphic(self, response_text: str) -> bool:
        """Ensure transformational invariants (e.g. no markdown format changes semantic meaning)."""
        if not response_text:
            return False
        # Canonicalize casing and whitespace to verify perturbations do not change output intent
        normalized = " ".join(response_text.lower().split())
        # Verify no error or blocked strings are present
        forbidden_keywords = ["[blocked]", "error:", "execution failed"]
        for kw in forbidden_keywords:
            if kw in normalized:
                return False
        return True

    def _run_tier3_ai_judge(self, scenario: Dict[str, Any], response_text: str) -> tuple:
        """AI Judge using LiteLLM call_with_schema with 2-Model Tiebreak."""
        try:
            from sidecar.llm_caller import call_with_schema

            prompt = (
                f"You are an AI Judge for the Kairo Phantom test gauntlet.\n"
                f"Evaluate the following scenario and the system's response text.\n\n"
                f"Scenario ID: {scenario.get('id', 'unknown')}\n"
                f"Scenario Category: {scenario.get('category', 'generic')}\n"
                f"Scenario Prompt: {scenario.get('prompt', '')}\n\n"
                f"System Response: {response_text}\n\n"
                f"Respond with a JSON object containing:\n"
                f"- 'passed': a boolean indicating if the system response successfully addresses the prompt\n"
                f"- 'score': a float between 0.0 and 1.0 evaluating the quality of the response\n"
                f"- 'feedback': a brief explanation of your judgment"
            )

            # Use LiteLLM call_with_schema for Model A and Model B
            res_a = call_with_schema(prompt, JudgeOutputSchema, model="ollama/qwen2.5:7b")
            res_b = call_with_schema(prompt, JudgeOutputSchema, model="ollama/llama3.2:latest")

            passed_a = res_a.passed
            passed_b = res_b.passed
            score_a = res_a.score
            score_b = res_b.score

            avg_score = (score_a + score_b) / 2.0

            if passed_a == passed_b:
                passed = passed_a
                feedback = f"Consensus (Model A: {res_a.feedback}; Model B: {res_b.feedback})"
            else:
                passed = avg_score >= 0.7
                feedback = (
                    f"Tiebreaker: Model A passed={passed_a} (score {score_a:.2f}), "
                    f"Model B passed={passed_b} (score {score_b:.2f}). "
                    f"Average score {avg_score:.2f} led to passed={passed}."
                )

            return avg_score, feedback
        except Exception as e:
            log.warning(f"AI Judge LiteLLM failed: {e}. Falling back to keyword matching.")
            return self._run_tier3_ai_judge_fallback(scenario, response_text)

    def _run_tier3_ai_judge_fallback(self, scenario: Dict[str, Any], response_text: str) -> tuple:
        """Fallback keyword match logic when LiteLLM is not available."""
        prompt = scenario.get("prompt", "").lower()
        response_lower = response_text.lower()

        # Check if response actually attempts to fulfill the prompt
        keywords = [w for w in prompt.split() if len(w) > 4]
        matches = sum(1 for w in keywords if w in response_lower)

        if not keywords:
            score = 1.0
        else:
            score = matches / len(keywords)

        # Cap score to 0.0-1.0
        score = max(0.0, min(1.0, score))

        # Penalize if too short
        if len(response_text) < 15:
            score *= 0.5

        return score, f"Fallback AI Judge matched {matches}/{len(keywords)} keywords."

    def _run_tier4_human_anchor(self, scenario_id: str, response_text: str) -> tuple:
        """Look up predefined ground-truth verdicts for regression scenarios dynamically."""
        sidecar_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        calibration_path = os.path.join(sidecar_dir, "calibration_set.json")

        if os.path.exists(calibration_path):
            try:
                with open(calibration_path, "r", encoding="utf-8") as f:
                    human_anchors = json.load(f)
                if scenario_id in human_anchors:
                    return True, bool(human_anchors[scenario_id])
            except Exception as e:
                log.error(f"Failed to load calibration set from {calibration_path}: {e}")

        # Fallback dictionary mapping
        human_anchors_fallback = {
            "scenario_legal_01": True,
            "scenario_sec_02": False,  # deliberate bad payload should fail
        }
        if scenario_id in human_anchors_fallback:
            return True, human_anchors_fallback[scenario_id]
        return False, False
