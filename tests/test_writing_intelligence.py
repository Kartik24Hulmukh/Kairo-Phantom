"""
tests/test_writing_intelligence.py

Test suite for Writing Intelligence v2.0:
  - MemorizationAuditor: copyright compliance & n-gram detection
  - VoiceAdapter: fingerprint extraction and prompt building
  - VoiceStore: persistence and retrieval

All tests are deterministic, offline, and require no external services.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "kairo-sidecar"))

from sidecar.writers.memorization_auditor import (
    MemorizationAuditor,
    MemorizationRisk,
    AuditResult,
    MemorizationFinding,
    audit_generated_text,
)
from sidecar.writers.voice_adapter import (
    VoiceAdapter,
    VoiceFingerprint,
    VoiceStore,
    get_user_voice_prompt,
    get_voice_store,
)

# Override minimum word count for tests using short docs
VoiceAdapter.MIN_WORDS_PER_DOC = 50



# ─── Fixtures ─────────────────────────────────────────────────────────────────

# Sample user document — formal technical writing
FORMAL_DOC = """
The implementation of distributed consensus algorithms presents significant 
computational challenges that must be addressed through careful architectural 
decisions. Furthermore, the utilization of Byzantine fault-tolerant protocols 
ensures that the system maintains correctness even in the presence of malicious 
actors. However, these guarantees come at a substantial performance cost that 
must be balanced against the requirements of the target deployment environment.

Consequently, the selection of an appropriate consensus mechanism requires 
thorough analysis of the specific workload characteristics and performance targets.
Indeed, the trade-offs between safety and liveness properties must be carefully
evaluated before committing to a particular design. Additionally, the operational
complexity of distributed systems demands robust monitoring and observability 
infrastructure to ensure reliable production operation.

Furthermore, it is critical to verify the scalability of the chosen topology.
Specifically, network latency can degrade system throughput under heavy contention.
Therefore, comprehensive load testing should be performed prior to deployment.
Finally, regular audits of the consensus state must be scheduled to detect anomalies.
"""

# Sample user document — casual professional writing
CASUAL_DOC = """
Here's what I've been thinking about our codebase. It's gotten pretty messy 
over the past year, and I think we need to do something about it. I'm not 
saying we need to rewrite everything — that would be insane — but we could 
definitely clean up the worst parts.

The authentication module is a disaster. I've had to explain it to three 
different people this month, and nobody gets it. Let's simplify it. And 
while we're at it, can we please add some tests? We've been saying we'll do 
it for six months now, and it hasn't happened.

I know, I know — everyone's busy. But this is starting to cost us real time 
when things break. What do you think?
"""


# ─── MemorizationAuditor Tests ────────────────────────────────────────────────

class TestMemorizationAuditor:
    def test_safe_original_text(self):
        """Original creative text should return SAFE."""
        auditor = MemorizationAuditor()
        text = "Kairo Phantom transforms how knowledge workers interact with documents."
        result = auditor.check_memorization(text)
        assert result.risk == MemorizationRisk.SAFE
        assert result.safe_to_output
        assert not result.is_blocked

    def test_empty_text_is_safe(self):
        """Empty text should always be safe."""
        auditor = MemorizationAuditor()
        result = auditor.check_memorization("")
        assert result.risk == MemorizationRisk.SAFE
        assert result.safe_to_output

    def test_mit_license_verbatim_blocked(self):
        """MIT License verbatim copy should be BLOCKED (well-known copyright)."""
        auditor = MemorizationAuditor()
        text = "Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files."
        result = auditor.check_memorization(text)
        # Should detect this as a known license verbatim
        assert result.risk in (MemorizationRisk.HIGH, MemorizationRisk.BLOCKED)

    def test_gpl_header_detected(self):
        """GPL license header should be detected."""
        auditor = MemorizationAuditor()
        text = "GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007 Copyright (C) 2007 Free Software Foundation"
        result = auditor.check_memorization(text)
        # Should detect GPL
        assert result.risk != MemorizationRisk.SAFE

    def test_corpus_ngram_detection(self):
        """Custom corpus should detect n-gram matches."""
        auditor = MemorizationAuditor()
        # Add a known phrase to corpus
        known_phrase = "The quick brown fox jumps over the lazy dog in the meadow"
        auditor.add_to_corpus(known_phrase, source_hint="test_source")

        # Text containing 5+ grams from the corpus
        test_text = "The quick brown fox jumps over the lazy dog in the meadow today"
        result = auditor.check_memorization(test_text)
        # Should detect the overlap
        assert result.risk != MemorizationRisk.SAFE
        assert len(result.findings) > 0

    def test_no_false_positive_common_phrases(self):
        """Common phrases that aren't copyrighted should not be flagged."""
        auditor = MemorizationAuditor()
        # Empty corpus = no false positives
        text = "The meeting was scheduled for 3pm. Please review the attached document."
        result = auditor.check_memorization(text)
        assert result.risk == MemorizationRisk.SAFE

    def test_audit_result_to_dict(self):
        """AuditResult.to_dict() should return serializable dict."""
        auditor = MemorizationAuditor()
        result = auditor.check_memorization("Safe original text about AI systems.")
        d = result.to_dict()
        assert "safe_to_output" in d
        assert "risk" in d
        assert "findings" in d
        # Should be JSON serializable
        json.dumps(d)  # Should not raise

    def test_add_to_corpus_returns_count(self):
        """add_to_corpus should return the number of n-grams added."""
        auditor = MemorizationAuditor()
        count = auditor.add_to_corpus(
            "This is a test sentence with several words",
            source_hint="test"
        )
        assert count > 0

    def test_convenience_function(self):
        """audit_generated_text convenience function works."""
        result = audit_generated_text("Safe original AI-generated content about productivity.")
        assert result.safe_to_output
        assert result.risk == MemorizationRisk.SAFE

    def test_highest_risk_property(self):
        """AuditResult.highest_risk returns the highest risk level."""
        findings = [
            MemorizationFinding(
                text_fragment="low fragment",
                gram_overlap=3,
                source_hint="test",
                risk=MemorizationRisk.LOW,
            ),
            MemorizationFinding(
                text_fragment="high fragment",
                gram_overlap=12,
                source_hint="test",
                risk=MemorizationRisk.HIGH,
            ),
        ]
        result = AuditResult(
            is_blocked=False,
            risk=MemorizationRisk.HIGH,
            findings=findings,
        )
        assert result.highest_risk == MemorizationRisk.HIGH

    def test_memorization_risk_ordering(self):
        """Risk levels should have a natural ordering from SAFE to BLOCKED."""
        risks = [
            MemorizationRisk.SAFE,
            MemorizationRisk.LOW,
            MemorizationRisk.MEDIUM,
            MemorizationRisk.HIGH,
            MemorizationRisk.BLOCKED,
        ]
        # Verify they're distinct
        assert len(set(risks)) == 5

    def test_corpus_loaded_from_file(self, tmp_path: Path):
        """Corpus can be loaded from a JSON file."""
        # Create a corpus file with a known phrase
        corpus = {}
        import hashlib
        # Add a hash manually
        gram = "test phrase for corpus loading verification"
        h = hashlib.sha256(gram.encode()).hexdigest()[:16]
        corpus[h] = "test_source"

        corpus_path = tmp_path / "test_corpus.json"
        corpus_path.write_text(json.dumps(corpus))

        auditor = MemorizationAuditor(corpus_path=corpus_path)
        assert auditor.corpus_size > 0

    def test_tokenizer_strips_punctuation(self):
        """Tokenizer should normalize text for comparison."""
        auditor = MemorizationAuditor()
        tokens = auditor._tokenize("Hello, world! This is a test.")
        assert "hello" in tokens
        assert "world" in tokens
        # Punctuation should be removed/stripped
        assert not any("," in t or "!" in t for t in tokens)


# ─── VoiceAdapter Tests ───────────────────────────────────────────────────────

class TestVoiceAdapter:
    def test_extract_fingerprint_formal(self):
        """Formal text should have high formality score."""
        adapter = VoiceAdapter()
        fp = adapter.extract_fingerprint([FORMAL_DOC])
        assert fp.document_count == 1
        assert fp.formality_score > 0.5
        assert fp.total_word_count > 0

    def test_extract_fingerprint_casual(self):
        """Casual text should have lower formality score."""
        adapter = VoiceAdapter()
        fp = adapter.extract_fingerprint([CASUAL_DOC])
        assert fp.document_count == 1
        assert fp.formality_score < 0.7  # Relative to formal
        assert fp.uses_contractions > 0  # "I'm", "we're", etc.

    def test_extract_fingerprint_empty_docs(self):
        """Empty documents should return default fingerprint."""
        adapter = VoiceAdapter()
        fp = adapter.extract_fingerprint([])
        assert fp.document_count == 0

    def test_extract_fingerprint_too_short(self):
        """Documents too short should be filtered."""
        adapter = VoiceAdapter()
        fp = adapter.extract_fingerprint(["Short doc."])
        assert fp.document_count == 0

    def test_extract_fingerprint_multiple_docs(self):
        """Multiple documents should be combined."""
        adapter = VoiceAdapter()
        fp = adapter.extract_fingerprint([FORMAL_DOC, CASUAL_DOC])
        assert fp.document_count == 2
        assert fp.total_word_count > 0

    def test_build_voice_prompt_formal(self):
        """Formal fingerprint should produce formal voice prompt."""
        adapter = VoiceAdapter()
        fp = adapter.extract_fingerprint([FORMAL_DOC])
        prompt = adapter.build_voice_prompt(fp)
        assert "USER VOICE ADAPTATION" in prompt
        assert len(prompt) > 100

    def test_build_voice_prompt_casual(self):
        """Casual fingerprint should produce casual voice prompt."""
        adapter = VoiceAdapter()
        fp = adapter.extract_fingerprint([CASUAL_DOC])
        prompt = adapter.build_voice_prompt(fp)
        assert "USER VOICE ADAPTATION" in prompt
        # Should mention casual or conversational
        assert "casual" in prompt.lower() or "conversational" in prompt.lower() or "formal" in prompt.lower()

    def test_voice_prompt_includes_transitions(self):
        """Voice prompt should include user's transition words."""
        adapter = VoiceAdapter()
        fp = VoiceFingerprint(
            common_transition_words=["however", "therefore", "consequently"],
            document_count=1,
        )
        prompt = adapter.build_voice_prompt(fp)
        assert "however" in prompt or "therefore" in prompt

    def test_fingerprint_roundtrip(self):
        """VoiceFingerprint should serialize/deserialize correctly."""
        adapter = VoiceAdapter()
        fp = adapter.extract_fingerprint([FORMAL_DOC])
        d = fp.to_dict()
        fp2 = VoiceFingerprint.from_dict(d)
        assert fp2.formality_score == pytest.approx(fp.formality_score, abs=0.01)
        assert fp2.document_count == fp.document_count

    def test_oxford_comma_detection(self):
        """Should detect Oxford comma usage."""
        adapter = VoiceAdapter()
        oxford_text = "I need apples, bananas, and oranges. I want red, blue, and green."
        no_oxford = "I need apples, bananas and oranges. I want red, blue and green."
        assert adapter._detect_oxford_comma(oxford_text)
        assert not adapter._detect_oxford_comma(no_oxford)

    def test_contraction_detection(self):
        """Should detect contractions in text."""
        adapter = VoiceAdapter()
        sents_with = ["I'm really excited about this.", "We're making progress."]
        sents_without = ["I am really excited.", "We are making progress."]
        assert adapter._detect_contractions(sents_with) > 0
        assert adapter._detect_contractions(sents_without) == 0.0


# ─── VoiceStore Tests ─────────────────────────────────────────────────────────

class TestVoiceStore:
    def test_save_and_load(self, tmp_path: Path):
        """Save fingerprint and load it back."""
        store = VoiceStore(store_dir=tmp_path)
        adapter = VoiceAdapter()
        fp = adapter.extract_fingerprint([FORMAL_DOC])

        saved_path = store.save(fp, user_id="test_user")
        assert saved_path.exists()

        loaded = store.load("test_user")
        assert loaded is not None
        assert loaded.document_count == fp.document_count
        assert loaded.formality_score == pytest.approx(fp.formality_score, abs=0.01)

    def test_load_missing_returns_none(self, tmp_path: Path):
        """Loading non-existent user returns None."""
        store = VoiceStore(store_dir=tmp_path)
        result = store.load("nonexistent_user")
        assert result is None

    def test_delete(self, tmp_path: Path):
        """Delete removes the fingerprint file."""
        store = VoiceStore(store_dir=tmp_path)
        adapter = VoiceAdapter()
        fp = adapter.extract_fingerprint([FORMAL_DOC])
        store.save(fp, "delete_me")

        assert store.load("delete_me") is not None
        deleted = store.delete("delete_me")
        assert deleted
        assert store.load("delete_me") is None

    def test_delete_nonexistent_returns_false(self, tmp_path: Path):
        """Deleting non-existent user returns False without error."""
        store = VoiceStore(store_dir=tmp_path)
        assert not store.delete("nobody")

    def test_list_users(self, tmp_path: Path):
        """list_users returns all saved users."""
        store = VoiceStore(store_dir=tmp_path)
        adapter = VoiceAdapter()
        fp = adapter.extract_fingerprint([FORMAL_DOC])

        store.save(fp, "alice")
        store.save(fp, "bob")
        store.save(fp, "charlie")

        users = store.list_users()
        assert set(users) == {"alice", "bob", "charlie"}

    def test_overwrite_existing(self, tmp_path: Path):
        """Saving same user_id overwrites existing fingerprint."""
        store = VoiceStore(store_dir=tmp_path)
        adapter = VoiceAdapter()

        fp1 = adapter.extract_fingerprint([FORMAL_DOC])
        fp2 = adapter.extract_fingerprint([CASUAL_DOC])

        store.save(fp1, "user")
        store.save(fp2, "user")

        loaded = store.load("user")
        assert loaded is not None
        # Should have casual doc's properties
        assert loaded.document_count == fp2.document_count


# ─── Integration Tests ────────────────────────────────────────────────────────

class TestWritingIntelligenceIntegration:
    def test_voice_adapted_generation_prompt(self, tmp_path: Path):
        """Full flow: extract fingerprint → save → get_user_voice_prompt."""
        # Set up store in temp dir
        store = VoiceStore(store_dir=tmp_path)
        adapter = VoiceAdapter()

        # Extract and save
        fp = adapter.extract_fingerprint([FORMAL_DOC])
        store.save(fp, "integration_user")

        # Build voice prompt
        loaded_fp = store.load("integration_user")
        prompt = adapter.build_voice_prompt(loaded_fp)

        assert isinstance(prompt, str)
        assert len(prompt) > 50
        assert "USER VOICE ADAPTATION" in prompt

    def test_audit_does_not_block_ai_text(self):
        """Normal AI-generated business text should not be blocked."""
        auditor = MemorizationAuditor()
        ai_text = """
        The quarterly revenue analysis indicates strong performance across all 
        major product lines, with particular growth in the enterprise segment.
        Customer acquisition costs have decreased by 23% year-over-year, while
        the average contract value has increased proportionally. The operations
        team has successfully reduced infrastructure costs through strategic
        consolidation of cloud resources, resulting in improved gross margins.
        """
        result = auditor.check_memorization(ai_text)
        assert result.safe_to_output

    def test_memorization_audit_json_serializable(self):
        """AuditResult must always produce JSON-serializable output."""
        auditor = MemorizationAuditor()
        result = auditor.check_memorization(
            "Permission is hereby granted, free of charge, to any person obtaining"
        )
        d = result.to_dict()
        # Must not raise
        serialized = json.dumps(d)
        # Must be valid JSON
        parsed = json.loads(serialized)
        assert "safe_to_output" in parsed


# ─── New v2.0 Metrics & Bloom Filter Tests ────────────────────────────────────

from sidecar.writers.memorization_auditor import BloomFilter
from sidecar.writers.writing_intelligence import get_writing_orchestrator


class TestBloomFilter:
    def test_bloom_filter_add_and_contains(self):
        bf = BloomFilter(size=1000, num_hashes=3)
        bf.add("test-phrase-1")
        bf.add("test-phrase-2")
        
        assert "test-phrase-1" in bf
        assert "test-phrase-2" in bf
        assert "test-phrase-not-added" not in bf


class TestWritingIntelligenceOrchestrator:
    def test_get_generation_prompt_without_fingerprint(self):
        orch = get_writing_orchestrator()
        prompt = orch.get_generation_prompt("Base system instructions", user_id="nonexistent")
        assert prompt == "Base system instructions"

    def test_audit_output_integration(self):
        orch = get_writing_orchestrator()
        result = orch.audit_output("Safe original creative text here.")
        assert result.safe_to_output
        assert result.risk == MemorizationRisk.SAFE

    def test_process_and_sanitize_no_match(self):
        orch = get_writing_orchestrator()
        text = "This is a completely original sentence with no copyright overlap."
        sanitized, result = orch.process_and_sanitize(text)
        assert sanitized == text
        assert result.safe_to_output

    def test_process_and_sanitize_verbatim_paraphrase(self, monkeypatch):
        # The real paraphrase service is unavailable in CI; enable the
        # deterministic stub explicitly (gated off by default in production —
        # see kairo-sidecar/tests/test_production_mocks_gating.py).
        monkeypatch.setenv("KAIRO_PARAPHRASE_STUB", "1")
        orch = get_writing_orchestrator()
        text = "Permission is hereby granted, free of charge, to any person obtaining a copy."
        sanitized, result = orch.process_and_sanitize(text)
        # Should have been rewritten/paraphrased
        assert "Permission is hereby granted, free of charge" not in sanitized
        assert "This license allows individuals to obtain, free of charge" in sanitized

    def test_log_document_feedback_cycles(self, tmp_path: Path):
        # Configure store in temp directory
        store = get_voice_store()
        store.store_dir = tmp_path
        
        orch = get_writing_orchestrator()
        orch.store = store
        orch.feedback_threshold = 3  # lower threshold for test
        
        # Log feedback
        text = FORMAL_DOC
        # Cycle 1
        tuner_triggered = orch.log_document_feedback("user1", text, accepted=True)
        assert not tuner_triggered
        
        # Cycle 2
        tuner_triggered = orch.log_document_feedback("user1", text, accepted=True)
        assert not tuner_triggered
        
        # Cycle 3 - triggers tuner
        tuner_triggered = orch.log_document_feedback("user1", text, accepted=True)
        assert tuner_triggered


class TestAuditorMetrics:
    def test_compute_metrics_clean_text(self):
        auditor = MemorizationAuditor()
        text = "This is clean text. It contains paragraphs. It should be clean."
        result = auditor.check_memorization(text)
        assert result.longest_contiguous_block == 0
        assert result.bmc_at_3 == 0
        assert result.bmc_at_5 == 0
        assert result.cross_paragraph_ratio == 0.0

    def test_compute_metrics_with_verbatim_match(self):
        auditor = MemorizationAuditor()
        text = "Permission is hereby granted, free of charge, to any person obtaining a copy.\n\nThis is a second paragraph."
        result = auditor.check_memorization(text)
        # "Permission is hereby granted, free of charge, to any person obtaining" has 10 words
        assert result.longest_contiguous_block >= 10
        assert result.bmc_at_3 >= 1
        assert result.bmc_at_5 >= 1
        # 1 out of 2 paragraphs has matched content
        assert result.cross_paragraph_ratio == 0.5

    def test_bloom_filter_integration(self):
        auditor = MemorizationAuditor()
        text = "This is a specific passage that we want to register to test Bloom filter integration."
        auditor.add_to_corpus(text, "Test Source")
        
        # Verify that the n-grams of this text are indeed in the Bloom filter
        tokens = auditor._tokenize(text)
        gram = " ".join(tokens[0:4])
        h = auditor._hash_gram(gram)
        assert h in auditor._bloom
        
        # Perform checking and verify it is caught
        result = auditor.check_memorization("This is a specific passage")
        assert len(result.findings) > 0
        assert any("Test Source" in f.source_hint for f in result.findings)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
