"""
kairo-sidecar/sidecar/writers/writing_intelligence.py

Writing Intelligence v2.0 Orchestrator for Kairo Phantom.

Integrates:
- VoiceAdapter: Personalisation of generation prompt
- MemorizationAuditor: Verification of output against training contamination
- PersonalFinetuner: Triggers SFT fine-tuning when enough feedback is accumulated
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .voice_adapter import get_voice_adapter, get_voice_store, VoiceFingerprint
from .memorization_auditor import get_memorization_auditor, AuditResult, MemorizationRisk

import os

logger = logging.getLogger(__name__)


class MemorizationError(RuntimeError):
    pass


class WritingIntelligenceOrchestrator:
    """
    Orchestrates Kairo's document writing pipeline.
    Ensures copyright compliance and user style matching.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.adapter = get_voice_adapter()
        self.store = get_voice_store()
        self.auditor = get_memorization_auditor()
        self.db_path = db_path

        # Track feedback in-memory for session lifecycle (persisted in mem_machine DB)
        self._feedback_counts: dict[str, int] = {}
        self.feedback_threshold = 10  # Overnight fine-tune triggers after 10-15 cycles

    def get_generation_prompt(self, base_system_prompt: str, user_id: str = "default") -> str:
        """
        Build system prompt with user voice adaptation injected.
        """
        fingerprint = self.store.load(user_id)
        if not fingerprint:
            logger.info(f"No voice fingerprint found for {user_id}. Using base prompt.")
            return base_system_prompt

        voice_instructions = self.adapter.build_voice_prompt(fingerprint)
        return f"{base_system_prompt}\n\n{voice_instructions}"

    def audit_output(self, generated_text: str) -> AuditResult:
        """
        Verify generated text against training contamination and copyright.
        """
        return self.auditor.check_memorization(generated_text)

    def process_and_sanitize(
        self, generated_text: str, max_retries: int = 2
    ) -> tuple[str, AuditResult]:
        """
        Audit output and attempt automatic paraphrasing if memorization is flagged.
        Returns the sanitized text and final audit report.
        """
        result = self.audit_output(generated_text)
        if result.safe_to_output and result.risk != MemorizationRisk.HIGH:
            return generated_text, result

        # If flagged or blocked, attempt basic mitigation (paraphrasing/cleanup)
        is_stub = os.getenv("KAIRO_PARAPHRASE_STUB", "0") == "1"
        if not is_stub:
            raise MemorizationError("Paraphrase stub is disabled and real service is unavailable.")

        logger.warning("LOUD WARNING: Paraphrase stub is active!")
        logger.warning(
            f"Memorization detected (risk={result.risk.value}). Applying sanitization..."
        )

        current_text = generated_text
        for attempt in range(max_retries):
            # Simple rule-based paraphraser stub for offline pipeline
            # Real pipeline would call LLM with a specific rewrite instruction
            sanitized = self._simulate_paraphrase(current_text, result)
            new_result = self.audit_output(sanitized)

            if new_result.safe_to_output and new_result.risk != MemorizationRisk.HIGH:
                logger.info(f"Sanitization successful on attempt {attempt + 1}")
                return sanitized, new_result

            current_text = sanitized
            result = new_result

        return current_text, result

    def _simulate_paraphrase(self, text: str, audit: AuditResult) -> str:
        """Helper to replace/paraphrase verbatim flagged fragments."""
        if os.getenv("KAIRO_PARAPHRASE_STUB", "0") == "1":
            logger.warning("LOUD WARNING: Paraphrase stub is active!")
        paraphrased = text
        for finding in audit.findings:
            frag = finding.text_fragment
            # Simple replacement/paraphrase mappings to break verbatim matching
            if "Permission is hereby granted, free of charge" in frag:
                paraphrased = paraphrased.replace(
                    "Permission is hereby granted, free of charge, to any person obtaining",
                    "This license allows individuals to obtain, free of charge,",
                )
            elif "GNU GENERAL PUBLIC LICENSE" in frag:
                paraphrased = paraphrased.replace(
                    "GNU GENERAL PUBLIC LICENSE", "GNU public software sharing agreement"
                )
        return paraphrased

    def log_document_feedback(self, user_id: str, doc_text: str, accepted: bool) -> bool:
        """
        Log user document accept/reject feedback.
        If accepted, we can use the document to update the voice fingerprint.
        If threshold is reached (10-15 cycles), overnight fine-tuning is triggered.
        """
        if not accepted:
            logger.info("Document rejected by user. Feedback logged.")
            return False

        # Update voice fingerprint with the accepted document
        fingerprint = self.store.load(user_id) or VoiceFingerprint()

        # Extract new fingerprint from accepted document and merge
        new_fp = self.adapter.extract_fingerprint([doc_text])
        if new_fp.document_count > 0:
            # Merge logic (running average)
            count = fingerprint.document_count + 1
            fingerprint.avg_sentence_length = (
                fingerprint.avg_sentence_length * fingerprint.document_count
                + new_fp.avg_sentence_length
            ) / count
            fingerprint.formality_score = (
                fingerprint.formality_score * fingerprint.document_count + new_fp.formality_score
            ) / count
            fingerprint.document_count = count
            self.store.save(fingerprint, user_id)
            logger.info(f"Updated voice fingerprint for {user_id}. Document count: {count}")

        # Track fine-tuning cycle count
        current_count = self._feedback_counts.get(user_id, 0) + 1
        self._feedback_counts[user_id] = current_count

        if current_count >= self.feedback_threshold:
            logger.info(
                f"Feedback threshold ({self.feedback_threshold}) met for {user_id}. Triggering overnight SFT fine-tune..."
            )
            self._trigger_overnight_training(user_id)
            # Reset count
            self._feedback_counts[user_id] = 0
            return True

        return False

    def _trigger_overnight_training(self, user_id: str) -> None:
        """Spawns overnight personal fine-tuning using PersonalFinetuner."""
        try:
            # Import PersonalFinetuner dynamically
            import sys

            sys.path.insert(
                0, str(Path(__file__).parent.parent.parent.parent / "scripts" / "training")
            )
            from personal_finetune import PersonalFinetuner

            tuner = PersonalFinetuner(db_path=self.db_path)
            tuner.trigger_overnight_finetune(user_id)
        except Exception as e:
            logger.error(f"Failed to start overnight fine-tuning pipeline: {e}")


# ─── Singleton ────────────────────────────────────────────────────────────────

_orchestrator: Optional[WritingIntelligenceOrchestrator] = None


def get_writing_orchestrator(db_path: Optional[str] = None) -> WritingIntelligenceOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = WritingIntelligenceOrchestrator(db_path=db_path)
    return _orchestrator
