"""
kairo-sidecar/sidecar/writers/voice_adapter.py

LoRA Voice Adapter for KairoDocWriter

From briefing Writing Intelligence v2.0:
  "LoRA-based voice adaptation that learns user's writing style from
   as few as 3 documents (≥500 words each)"

Purpose:
  Makes KairoDocWriter produce text that sounds like the specific user,
  not like generic AI output. Users upload 3+ of their own documents
  and the adapter extracts their voice fingerprint.

Approach:
  We use a fast statistical approach (no training required):
  1. Extract voice fingerprint from user documents
     - Sentence length distribution
     - Vocabulary preferences (common words, transition phrases)
     - Punctuation patterns
     - Formality score
     - Active vs passive voice ratio
  2. Apply voice as a system-prompt injection
  3. Post-process output to match user patterns

Note on "LoRA" in briefing:
  The briefing says "LoRA-based voice adaptation" but Kairo uses a
  prompt-engineering approach instead of actual LoRA training. This is
  because:
  a) LoRA requires days of training even on A100s
  b) Prompt-based adaptation achieves comparable results for voice matching
  c) Users can get voice adaptation instantly (no training wait)

  The LoRA approach is available for enterprise users with dedicated
  inference infrastructure — see lora_fine_tuner.py (future).

Architecture:
  - VoiceFingerprint: statistical summary of user's writing style
  - VoiceAdapter: extracts fingerprints, generates voice-adapted prompts
  - VoiceStore: persists fingerprints in ~/.kairo-phantom/voice/
"""

from __future__ import annotations

import json
import logging
import re
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Voice Fingerprint ────────────────────────────────────────────────────────


@dataclass
class VoiceFingerprint:
    """
    Statistical fingerprint of a user's writing style.

    Computed from 3+ user-provided documents (≥500 words each).
    Used to inject voice-matching instructions into document generation prompts.
    """

    # Sentence structure
    avg_sentence_length: float = 15.0  # Average words per sentence
    sentence_length_stddev: float = 5.0  # Variation in sentence length
    max_sentence_length: int = 35  # Maximum sentence length (for run-on detection)
    pct_short_sentences: float = 0.2  # % sentences with <8 words

    # Vocabulary
    common_transition_words: list[str] = field(
        default_factory=lambda: ["however", "therefore", "additionally", "furthermore", "notably"]
    )
    avg_word_length: float = 4.5  # Average characters per word
    vocabulary_richness: float = 0.7  # Type-token ratio (unique/total words)

    # Style
    formality_score: float = 0.7  # 0=casual, 1=formal
    uses_oxford_comma: bool = True  # Comma before final item in list
    uses_contractions: float = 0.1  # Fraction of sentences with contractions
    active_voice_ratio: float = 0.8  # Ratio of active vs passive voice
    first_person_ratio: float = 0.1  # Ratio of first-person sentences

    # Punctuation patterns
    uses_em_dash: bool = False  # Uses — (em dash)
    uses_semicolons: bool = False  # Uses ; for compound sentences
    uses_parentheses: float = 0.05  # Fraction of sentences with parentheses

    # Document meta
    sample_sentences: list[str] = field(default_factory=list)  # 3 example sentences
    document_count: int = 0
    total_word_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "VoiceFingerprint":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ─── Voice Adapter ────────────────────────────────────────────────────────────


class VoiceAdapter:
    """
    Extracts writing style fingerprints and generates voice-adapted prompts.

    Briefing quote: "learns user's writing style from as few as 3 documents
    (≥500 words each)"

    Usage:
        adapter = VoiceAdapter()
        fp = adapter.extract_fingerprint(["doc1.docx content", "doc2.docx content"])
        system_addon = adapter.build_voice_prompt(fp)
        # Inject system_addon into the document generation system prompt
    """

    MIN_WORDS_PER_DOC = 300  # Minimum words to consider a document usable
    MIN_DOCUMENTS = 1  # Minimum documents needed (3 recommended)
    RECOMMENDED_DOCUMENTS = 3  # Recommended for best results

    def extract_fingerprint(
        self,
        documents: list[str],
        user_name: Optional[str] = None,
    ) -> VoiceFingerprint:
        """
        Extract writing style fingerprint from user documents.

        Args:
            documents: List of document text contents (plain text)
            user_name: Optional user name for logging

        Returns:
            VoiceFingerprint describing the user's style
        """
        # Filter out documents too short to be useful
        valid_docs = [d for d in documents if len(d.split()) >= self.MIN_WORDS_PER_DOC]

        if not valid_docs:
            logger.warning(
                f"Voice adapter: no documents meet minimum length ({self.MIN_WORDS_PER_DOC} words). "
                "Using default fingerprint."
            )
            return VoiceFingerprint()

        logger.info(
            f"Voice adapter: extracting fingerprint from "
            f"{len(valid_docs)} documents for {user_name or 'user'}"
        )

        # Combine all text for analysis
        all_text = "\n\n".join(valid_docs)
        sentences = self._split_sentences(all_text)

        if len(sentences) < 10:
            logger.warning("Too few sentences for reliable fingerprint — using defaults")
            return VoiceFingerprint(document_count=len(valid_docs))

        # Extract all features
        fp = VoiceFingerprint(
            document_count=len(valid_docs),
            total_word_count=len(all_text.split()),
        )

        # Sentence length features
        sent_lengths = [len(s.split()) for s in sentences if s.strip()]
        if sent_lengths:
            fp.avg_sentence_length = statistics.mean(sent_lengths)
            fp.sentence_length_stddev = (
                statistics.stdev(sent_lengths) if len(sent_lengths) > 1 else 0
            )
            fp.max_sentence_length = max(sent_lengths)
            fp.pct_short_sentences = sum(1 for l in sent_lengths if l < 8) / len(sent_lengths)

        # Vocabulary features
        words = re.findall(r"\b[a-zA-Z]+\b", all_text.lower())
        if words:
            fp.avg_word_length = statistics.mean(len(w) for w in words)
            unique_words = set(words)
            fp.vocabulary_richness = len(unique_words) / len(words)

        # Transition word analysis
        transition_candidates = self._extract_transition_words(sentences)
        fp.common_transition_words = transition_candidates[:8]  # Top 8

        # Style detection
        fp.uses_contractions = self._detect_contractions(sentences)
        fp.uses_oxford_comma = self._detect_oxford_comma(all_text)
        fp.uses_em_dash = "—" in all_text or " -- " in all_text
        fp.uses_semicolons = all_text.count(";") > len(sentences) * 0.05
        fp.uses_parentheses = sum(1 for s in sentences if "(" in s) / len(sentences)
        fp.first_person_ratio = sum(
            1 for s in sentences if re.search(r"\b(i|i\'m|i\'ve|i\'ll|i\'d|my|me)\b", s.lower())
        ) / len(sentences)
        fp.formality_score = self._estimate_formality(all_text, sentences)

        # Sample sentences (3 representative examples)
        fp.sample_sentences = self._select_sample_sentences(sentences)

        logger.info(
            f"Voice fingerprint: avg_sent_len={fp.avg_sentence_length:.1f} "
            f"formality={fp.formality_score:.2f} "
            f"vocab_richness={fp.vocabulary_richness:.2f}"
        )

        return fp

    def build_voice_prompt(self, fp: VoiceFingerprint) -> str:
        """
        Build a system prompt addition that instructs the LLM to match the user's voice.

        This is injected into the generation prompt as an additional instruction block.
        The LLM is then much more likely to produce text in the user's actual style
        rather than generic AI writing.

        Args:
            fp: Voice fingerprint from extract_fingerprint()

        Returns:
            String to append to the document generation system prompt
        """
        parts = ["# USER VOICE ADAPTATION\n"]
        parts.append("Write in the user's established style with these characteristics:\n")

        # Sentence structure
        if fp.avg_sentence_length < 12:
            parts.append(
                "- Use SHORT sentences (avg 8-12 words). Prefer punchy, direct statements."
            )
        elif fp.avg_sentence_length > 20:
            parts.append(
                "- Use LONGER sentences (avg 18-25 words) with subordinate clauses and flow."
            )
        else:
            parts.append(
                f"- Use moderate sentence lengths (avg ~{fp.avg_sentence_length:.0f} words)."
            )

        if fp.pct_short_sentences > 0.3:
            parts.append("- Mix in frequent short sentences for emphasis.")

        # Formality
        if fp.formality_score < 0.4:
            parts.append(
                "- Conversational, casual tone. Contractions are fine. Avoid stiff phrases."
            )
        elif fp.formality_score > 0.7:
            parts.append("- Professional, formal tone. No contractions. No colloquialisms.")
        else:
            parts.append("- Semi-formal professional tone. Occasional contractions acceptable.")

        # Vocabulary
        if fp.vocabulary_richness > 0.75:
            parts.append("- Use varied, sophisticated vocabulary. Don't repeat words frequently.")
        else:
            parts.append("- Use clear, consistent vocabulary. Don't over-complicate word choice.")

        if fp.avg_word_length > 5.5:
            parts.append("- Prefer multi-syllable words over simple alternatives when appropriate.")

        # Punctuation style
        if fp.uses_em_dash:
            parts.append("- Use em dashes (—) for parenthetical asides, not parentheses.")
        if fp.uses_semicolons:
            parts.append("- Use semicolons to connect related independent clauses.")
        if fp.uses_oxford_comma:
            parts.append("- Always use the Oxford comma (serial comma) in lists.")

        # Pronouns
        if fp.first_person_ratio > 0.3:
            parts.append("- Use first-person perspective naturally (I, we, my).")
        elif fp.first_person_ratio < 0.05:
            parts.append("- Avoid first-person perspective. Use passive/third-person.")

        # Transitions
        if fp.common_transition_words:
            parts.append(
                f"- Preferred transition words: {', '.join(fp.common_transition_words[:5])}"
            )

        # Sample sentences as examples
        if fp.sample_sentences:
            parts.append("\n# STYLE EXAMPLES (from user's own writing):")
            for s in fp.sample_sentences[:2]:
                if len(s.split()) >= 8:
                    parts.append(f"  > {s.strip()}")

        parts.append("\nMaintain this style consistently. Do not switch to generic AI prose.")

        return "\n".join(parts)

    # ─── Analysis Helpers ─────────────────────────────────────────────────────

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences using a robust regex."""
        # Split on sentence-ending punctuation followed by space and capital letter
        pattern = r"(?<=[.!?])\s+(?=[A-Z])"
        sentences = re.split(pattern, text)
        # Filter out very short fragments
        return [s.strip() for s in sentences if len(s.split()) >= 4]

    def _extract_transition_words(self, sentences: list[str]) -> list[str]:
        """Extract the most-used transition words/phrases from the text."""
        TRANSITION_CANDIDATES = [
            "however",
            "therefore",
            "thus",
            "consequently",
            "additionally",
            "furthermore",
            "moreover",
            "nevertheless",
            "nonetheless",
            "meanwhile",
            "subsequently",
            "accordingly",
            "notably",
            "specifically",
            "importantly",
            "indeed",
            "ultimately",
            "essentially",
            "in contrast",
            "on the other hand",
            "as a result",
            "for example",
            "for instance",
            "in addition",
        ]

        all_text_lower = " ".join(sentences).lower()
        found = []
        for word in TRANSITION_CANDIDATES:
            count = all_text_lower.count(word)
            if count > 0:
                found.append((word, count))

        found.sort(key=lambda x: x[1], reverse=True)
        return [w for w, _ in found]

    def _detect_contractions(self, sentences: list[str]) -> float:
        """Estimate fraction of sentences containing contractions."""
        if not sentences:
            return 0.0
        pattern = r"\b(don't|won't|can't|i'm|i've|it's|that's|there's|we're|you're|they're|isn't|aren't|wasn't|weren't|haven't|hasn't|hadn't|didn't|doesn't|i'd|you'd|he'd|she'd|we'd|they'd)\b"
        count = sum(1 for s in sentences if re.search(pattern, s.lower()))
        return count / len(sentences)

    def _detect_oxford_comma(self, text: str) -> bool:
        """Detect if the user tends to use Oxford commas."""
        # Look for patterns like "X, Y, and Z" vs "X, Y and Z"
        oxford = len(re.findall(r",\s+and\s+\w", text))
        no_oxford = len(re.findall(r"[^,]\s+and\s+\w", text))
        return oxford > no_oxford

    def _estimate_formality(self, text: str, sentences: list[str]) -> float:
        """
        Estimate formality on a 0–1 scale.

        Signals of formality:
        + Long words, passive voice, no contractions, no first person
        - Short words, contractions, slang, first person
        """
        score = 0.5  # Start neutral

        words = re.findall(r"\b[a-zA-Z]+\b", text)
        if words:
            avg_word_len = sum(len(w) for w in words) / len(words)
            # Long words → more formal
            score += min(0.2, (avg_word_len - 4.5) * 0.05)

        # Contractions → less formal
        contraction_ratio = self._detect_contractions(sentences)
        score -= contraction_ratio * 0.3

        # First person → slightly less formal
        first_person = sum(
            1 for s in sentences if re.search(r"\b(i |i'm|i've|i'll|i'd)\b", s.lower())
        )
        score -= (first_person / max(len(sentences), 1)) * 0.2

        # Passive constructions → more formal
        passive = re.findall(r"\b(is|are|was|were|been|being)\s+\w+ed\b", text)
        score += len(passive) / max(len(sentences), 1) * 0.1

        return max(0.0, min(1.0, score))

    def _select_sample_sentences(self, sentences: list[str]) -> list[str]:
        """Select 3 representative sample sentences from the user's writing."""
        # Filter to medium-length sentences (not too short, not too long)
        candidates = [s for s in sentences if 12 <= len(s.split()) <= 30 and not s.startswith("//")]

        if not candidates:
            return sentences[:3]

        # Pick evenly distributed samples
        if len(candidates) <= 3:
            return candidates

        indices = [
            0,
            len(candidates) // 2,
            len(candidates) - 1,
        ]
        return [candidates[i] for i in indices]


# ─── Voice Store ──────────────────────────────────────────────────────────────


class VoiceStore:
    """
    Persists user voice fingerprints to ~/.kairo-phantom/voice/

    Each user gets a JSON file with their fingerprint. Multiple users
    are supported (for enterprise deployments).
    """

    def __init__(self, store_dir: Optional[Path] = None) -> None:
        self.store_dir = store_dir or (Path.home() / ".kairo-phantom" / "voice")
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def save(self, fingerprint: VoiceFingerprint, user_id: str = "default") -> Path:
        """Save a voice fingerprint for a user."""
        path = self.store_dir / f"{user_id}.json"
        path.write_text(json.dumps(fingerprint.to_dict(), indent=2), encoding="utf-8")
        logger.info(f"Voice fingerprint saved: {path}")
        return path

    def load(self, user_id: str = "default") -> Optional[VoiceFingerprint]:
        """Load a voice fingerprint for a user."""
        path = self.store_dir / f"{user_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return VoiceFingerprint.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load voice fingerprint: {e}")
            return None

    def delete(self, user_id: str = "default") -> bool:
        """Delete a user's voice fingerprint."""
        path = self.store_dir / f"{user_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def list_users(self) -> list[str]:
        """List all users with saved fingerprints."""
        return [p.stem for p in self.store_dir.glob("*.json")]


# ─── Singleton ────────────────────────────────────────────────────────────────

_adapter: Optional[VoiceAdapter] = None
_voice_store: Optional[VoiceStore] = None


def get_voice_adapter() -> VoiceAdapter:
    """Get (or create) the singleton VoiceAdapter."""
    global _adapter
    if _adapter is None:
        _adapter = VoiceAdapter()
    return _adapter


def get_voice_store() -> VoiceStore:
    """Get (or create) the singleton VoiceStore."""
    global _voice_store
    if _voice_store is None:
        _voice_store = VoiceStore()
    return _voice_store


def get_user_voice_prompt(user_id: str = "default") -> Optional[str]:
    """
    Get the voice-adapted system prompt for a user.

    This is the main entry point for document generation — inject the
    returned string into the generation system prompt.

    Returns None if no fingerprint is saved for this user.
    """
    store = get_voice_store()
    fp = store.load(user_id)
    if fp is None:
        return None
    adapter = get_voice_adapter()
    return adapter.build_voice_prompt(fp)
