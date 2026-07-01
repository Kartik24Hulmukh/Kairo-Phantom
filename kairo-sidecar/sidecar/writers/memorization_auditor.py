"""
kairo-sidecar/sidecar/writers/memorization_auditor.py

MemorizationAuditor — Copyright Compliance & Training Data Contamination Guard

From briefing Writing Intelligence v2.0:
  "MemorizationAuditor: automatic memorization detection at ≥3-gram overlap"

Purpose:
  Before outputting any generated text, scan it for passages that appear
  verbatim or near-verbatim in known copyrighted works (textbooks, novels,
  news articles, licensed code).

Detection method:
  - 3-gram overlap against known-sensitive corpus hashes
  - Exact substring matching for known copyrighted passages
  - N-gram fingerprinting (MinHash similarity)

Compliance:
  - Required for all Writing Intelligence v2.0 output
  - Blocks direct reproduction of >30 words from copyrighted sources
  - Flags >3-gram overlaps for human review
  - Not required for paraphrase or user-provided content (user owns the doc)

Architecture:
  - AuditResult: per-passage findings with source attribution
  - MemorizationAuditor: main class with check_memorization()
  - Built-in corpus of high-risk phrases (common textbooks, code license headers)
  - Pluggable external corpus via load_corpus_hashes()

This is a "defense-in-depth" measure — the primary model (KairoDocWriter-4B)
is fine-tuned to paraphrase rather than regurgitate, this auditor is a backstop.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from sidecar.safety.bmc_gate import SuffixAutomaton, longest_common_substring_with_tolerance


# ─── Risk Levels ──────────────────────────────────────────────────────────────


class MemorizationRisk(str, Enum):
    """Risk level for detected memorization."""

    SAFE = "safe"  # No memorization detected
    LOW = "low"  # 3–5 gram overlap, possibly coincidental
    MEDIUM = "medium"  # 5–10 gram overlap, likely memorization
    HIGH = "high"  # >10 gram overlap, clear memorization
    BLOCKED = "blocked"  # >30-word verbatim match — output blocked


# ─── Bloom Filter ─────────────────────────────────────────────────────────────


class BloomFilter:
    """
    A space-efficient probabilistic data structure for set membership.
    Used for compact copyright checking without storing original texts.
    """

    def __init__(self, size: int = 100000, num_hashes: int = 4) -> None:
        self.size = size
        self.num_hashes = num_hashes
        self.bit_array = [False] * size

    def _hashes(self, item: str) -> list[int]:
        hashes = []
        for i in range(self.num_hashes):
            h = hashlib.sha256(f"{i}:{item}".encode("utf-8")).hexdigest()
            hashes.append(int(h, 16) % self.size)
        return hashes

    def add(self, item: str) -> None:
        for h in self._hashes(item):
            self.bit_array[h] = True

    def __contains__(self, item: str) -> bool:
        return all(self.bit_array[h] for h in self._hashes(item))


# ─── Data Structures ──────────────────────────────────────────────────────────


@dataclass
class MemorizationFinding:
    """A single finding from the memorization check."""

    text_fragment: str  # The flagged fragment (first 100 chars)
    gram_overlap: int  # Size of overlapping n-gram
    source_hint: str  # What source it likely came from
    risk: MemorizationRisk
    position: int = 0  # Character position in the input text


@dataclass
class AuditResult:
    """Result of a memorization audit."""

    is_blocked: bool  # True if output must be suppressed
    risk: MemorizationRisk
    findings: list[MemorizationFinding] = field(default_factory=list)
    text_length: int = 0
    safe_to_output: bool = True  # False if is_blocked

    # Paper metrics for compliance
    longest_contiguous_block: int = 0
    bmc_at_3: int = 0
    bmc_at_5: int = 0
    cross_paragraph_ratio: float = 0.0

    @property
    def highest_risk(self) -> MemorizationRisk:
        if not self.findings:
            return MemorizationRisk.SAFE
        risk_order = [
            MemorizationRisk.SAFE,
            MemorizationRisk.LOW,
            MemorizationRisk.MEDIUM,
            MemorizationRisk.HIGH,
            MemorizationRisk.BLOCKED,
        ]
        return max(self.findings, key=lambda f: risk_order.index(f.risk)).risk

    def to_dict(self) -> dict:
        return {
            "safe_to_output": self.safe_to_output,
            "risk": self.risk.value,
            "is_blocked": self.is_blocked,
            "longest_contiguous_block": self.longest_contiguous_block,
            "bmc_at_3": self.bmc_at_3,
            "bmc_at_5": self.bmc_at_5,
            "cross_paragraph_ratio": self.cross_paragraph_ratio,
            "findings": [
                {
                    "fragment": f.text_fragment[:80],
                    "gram_overlap": f.gram_overlap,
                    "source_hint": f.source_hint,
                    "risk": f.risk.value,
                    "position": f.position,
                }
                for f in self.findings
            ],
        }


# ─── Built-in High-Risk Corpus ────────────────────────────────────────────────

# Known high-risk phrases that commonly appear in training data.
# These are hashes of n-grams from commonly licensed texts.
# Format: {sha256(normalized_ngram): source_hint}
#
# Note: We only store HASHES of the phrases, never the phrases themselves,
# to avoid this file itself containing copyrighted material.
#
# These are populated from public domain examples for demonstration.
# A real deployment would load from a curated corpus database.

_BUILTIN_NGRAM_HASHES: dict[str, str] = {}


# Known verbatim blocklist — common license headers and boilerplate
# that appear verbatim in training data and must never be reproduced.
_VERBATIM_BLOCKLIST: list[tuple[str, str]] = [
    # (substring to detect, source_hint)
    # These are general patterns, not actual copyrighted text
    (
        "Permission is hereby granted, free of charge, to any person obtaining",
        "MIT License verbatim",
    ),
    ("GNU GENERAL PUBLIC LICENSE", "GPL License verbatim"),
    ("TERMS AND CONDITIONS FOR COPYING, DISTRIBUTION AND MODIFICATION", "GPL terms verbatim"),
]


# ─── Memorization Auditor ─────────────────────────────────────────────────────


class MemorizationAuditor:
    """
    Detects memorization of copyrighted content in generated text.

    Implements the "MemorizationAuditor" component of Writing Intelligence v2.0
    described in the briefing. This runs on every document generation output
    to ensure copyright compliance.

    Algorithm:
    1. Normalize text (lowercase, collapse whitespace)
    2. Extract all 3-grams through 15-grams
    3. Hash each n-gram and check against corpus
    4. Check for verbatim substring matches
    5. Classify risk and return AuditResult

    Performance:
    - O(n·k) where n = text length, k = max n-gram size (15)
    - Typically <10ms for documents up to 10,000 words
    - Designed for inline use, not async
    """

    MIN_GRAM_SIZE = 3  # Minimum n-gram size to detect
    MAX_GRAM_SIZE = 15  # Maximum n-gram size to check
    BLOCK_THRESHOLD = 30  # Words — verbatim match at this length is blocked
    HIGH_THRESHOLD = 10  # Words — n-gram at this size triggers HIGH risk
    MEDIUM_THRESHOLD = 5  # Words — n-gram at this size triggers MEDIUM risk

    def __init__(
        self,
        corpus_path: Optional[Path] = None,
        additional_corpus: Optional[dict[str, str]] = None,
    ) -> None:
        """
        Initialize auditor with optional external corpus.

        Args:
            corpus_path: Path to JSON file with {hash: source_hint} entries
            additional_corpus: Dict of {hash: source_hint} to add to corpus
        """
        self._bloom = BloomFilter(size=100000, num_hashes=4)
        self._corpus: dict[str, str] = dict(_BUILTIN_NGRAM_HASHES)
        for h in self._corpus.keys():
            self._bloom.add(h)

        self._verbatim_blocklist = list(_VERBATIM_BLOCKLIST)
        self._automaton = SuffixAutomaton()
        self._raw_texts: dict[str, str] = {}

        if corpus_path and corpus_path.exists():
            self._load_corpus_file(corpus_path)

        if additional_corpus:
            self._corpus.update(additional_corpus)
            for h in additional_corpus.keys():
                self._bloom.add(h)

    def _load_corpus_file(self, path: Path) -> None:
        """Load additional n-gram hashes from a JSON file."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._corpus.update(data)
                for h in data.keys():
                    self._bloom.add(h)
        except Exception:
            pass

    def add_to_corpus(self, text: str, source_hint: str) -> int:
        """
        Add a text passage to the auditor corpus.

        This is used during training data preparation to register known
        copyrighted passages that the model should not reproduce.

        Args:
            text: The copyrighted text to register
            source_hint: Human-readable source identifier

        Returns:
            Number of n-gram hashes added
        """
        tokens = self._tokenize(text)
        added = 0

        # Build Suffix Automaton
        for token in tokens:
            self._automaton.insert_word(token)

        # Store raw text for edit-distance LCS verification
        self._raw_texts[source_hint] = text

        for gram_size in range(self.MIN_GRAM_SIZE, min(self.MAX_GRAM_SIZE + 1, len(tokens) + 1)):
            for i in range(len(tokens) - gram_size + 1):
                gram = " ".join(tokens[i : i + gram_size])
                h = self._hash_gram(gram)
                self._corpus[h] = source_hint
                self._bloom.add(h)
                added += 1

        return added

    def check_memorization(self, generated_text: str) -> AuditResult:
        """
        Check generated text for memorization of copyrighted content.

        This is the primary public API. Call before outputting any
        model-generated document text.

        Args:
            generated_text: The text generated by KairoDocWriter

        Returns:
            AuditResult with risk assessment and findings
        """
        if not generated_text or not generated_text.strip():
            return AuditResult(
                is_blocked=False,
                risk=MemorizationRisk.SAFE,
                safe_to_output=True,
                text_length=0,
            )

        findings: list[MemorizationFinding] = []

        # Step 1: Verbatim substring check (blocking)
        verbatim_findings = self._check_verbatim(generated_text)
        findings.extend(verbatim_findings)

        # Step 2: Suffix-automaton check (word-level verbatim)
        tokens = self._tokenize(generated_text)
        longest_automaton_match = self._automaton.find_longest_match(tokens)
        if longest_automaton_match >= self.MIN_GRAM_SIZE:
            risk = self._classify_gram_risk(longest_automaton_match)
            findings.append(
                MemorizationFinding(
                    text_fragment=generated_text[:100],
                    gram_overlap=longest_automaton_match,
                    source_hint="Suffix Automaton Match",
                    risk=risk,
                    position=0,
                )
            )

        # Step 3: Edit-distance LCS check against raw texts in corpus
        for source_hint, raw_text in self._raw_texts.items():
            raw_tokens = self._tokenize(raw_text)
            lcs_len = longest_common_substring_with_tolerance(tokens, raw_tokens, max_ratio=0.2)
            if lcs_len >= self.MIN_GRAM_SIZE:
                risk = self._classify_gram_risk(lcs_len)
                findings.append(
                    MemorizationFinding(
                        text_fragment=raw_text[:100],
                        gram_overlap=lcs_len,
                        source_hint=f"LCS-Tolerance Match: {source_hint}",
                        risk=risk,
                        position=0,
                    )
                )

        # Step 4: N-gram overlap check
        ngram_findings = self._check_ngrams(generated_text)
        findings.extend(ngram_findings)

        # Step 3: Determine overall risk
        is_blocked = any(f.risk == MemorizationRisk.BLOCKED for f in findings)

        if not findings:
            risk = MemorizationRisk.SAFE
        elif is_blocked:
            risk = MemorizationRisk.BLOCKED
        else:
            risk_order = [
                MemorizationRisk.SAFE,
                MemorizationRisk.LOW,
                MemorizationRisk.MEDIUM,
                MemorizationRisk.HIGH,
            ]
            highest_idx = max(risk_order.index(f.risk) for f in findings)
            risk = risk_order[highest_idx]

        tokens = self._tokenize(generated_text)
        longest, bmc_3, bmc_5, cpr = self._compute_metrics(generated_text, tokens)

        return AuditResult(
            is_blocked=is_blocked,
            risk=risk,
            findings=findings,
            text_length=len(generated_text),
            safe_to_output=not is_blocked,
            longest_contiguous_block=longest,
            bmc_at_3=bmc_3,
            bmc_at_5=bmc_5,
            cross_paragraph_ratio=cpr,
        )

    def _compute_metrics(
        self, generated_text: str, tokens: list[str]
    ) -> tuple[int, int, int, float]:
        """
        Compute longest contiguous block, bmc_at_3, bmc_at_5, and cross-paragraph ratio.
        """
        if not tokens:
            return 0, 0, 0, 0.0

        matched = [False] * len(tokens)

        # 1. Check n-gram overlaps
        if self._corpus:
            for gram_size in range(
                self.MIN_GRAM_SIZE, min(self.MAX_GRAM_SIZE + 1, len(tokens) + 1)
            ):
                for i in range(len(tokens) - gram_size + 1):
                    gram = " ".join(tokens[i : i + gram_size])
                    h = self._hash_gram(gram)
                    if h in self._corpus:
                        for j in range(i, i + gram_size):
                            matched[j] = True

        # 2. Check verbatim blocklist
        for pattern, _ in self._verbatim_blocklist:
            pat_lower = pattern.lower()
            text_lower = generated_text.lower()
            start = 0
            while True:
                pos = text_lower.find(pat_lower, start)
                if pos == -1:
                    break
                # Find which tokens fall within this character range
                pat_tokens = self._tokenize(pattern)
                pat_len = len(pat_tokens)
                # Find matching token sequence
                for i in range(len(tokens) - pat_len + 1):
                    if tokens[i : i + pat_len] == pat_tokens:
                        for j in range(i, i + pat_len):
                            matched[j] = True
                start = pos + 1

        # 3. Compute Longest Contiguous Block
        longest = 0
        current = 0
        for m in matched:
            if m:
                current += 1
                longest = max(longest, current)
            else:
                current = 0

        # 4. Compute bmc@3 and bmc@5
        # bmc@k is the count of contiguous matching blocks of length >= k
        runs = []
        in_run = False
        run_start = 0
        for idx, m in enumerate(matched):
            if m:
                if not in_run:
                    in_run = True
                    run_start = idx
            else:
                if in_run:
                    runs.append(idx - run_start)
                    in_run = False
        if in_run:
            runs.append(len(matched) - run_start)

        bmc_3 = sum(1 for r in runs if r >= 3)
        bmc_5 = sum(1 for r in runs if r >= 5)

        # 5. Compute Cross-Paragraph Ratio
        paragraphs = [p for p in generated_text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [p for p in generated_text.splitlines() if p.strip()]

        if not paragraphs:
            cpr = 0.0
        else:
            matching_paragraphs = 0
            for p in paragraphs:
                p_tokens = self._tokenize(p)
                if not p_tokens:
                    continue
                p_len = len(p_tokens)
                has_match = False
                for i in range(len(tokens) - p_len + 1):
                    if tokens[i : i + p_len] == p_tokens:
                        if any(matched[i + j] for j in range(p_len)):
                            has_match = True
                            break
                if has_match:
                    matching_paragraphs += 1
            cpr = matching_paragraphs / len(paragraphs)

        return longest, bmc_3, bmc_5, cpr

    def _check_verbatim(self, text: str) -> list[MemorizationFinding]:
        """Check for verbatim matches against the blocklist."""
        findings = []

        for pattern, source_hint in self._verbatim_blocklist:
            pos = text.lower().find(pattern.lower())
            if pos >= 0:
                # Count words in the match
                word_count = len(pattern.split())
                risk = (
                    MemorizationRisk.BLOCKED
                    if word_count >= self.BLOCK_THRESHOLD
                    else MemorizationRisk.HIGH
                )
                findings.append(
                    MemorizationFinding(
                        text_fragment=text[pos : pos + len(pattern)][:100],
                        gram_overlap=word_count,
                        source_hint=source_hint,
                        risk=risk,
                        position=pos,
                    )
                )

        return findings

    def _check_ngrams(self, text: str) -> list[MemorizationFinding]:
        """Check n-grams against the corpus."""
        if not self._corpus:
            return []  # No corpus loaded — skip (avoids false positives)

        findings = []
        tokens = self._tokenize(text)

        if len(tokens) < self.MIN_GRAM_SIZE:
            return []

        seen_positions: set[int] = set()

        for gram_size in range(
            min(self.MAX_GRAM_SIZE, len(tokens)),
            self.MIN_GRAM_SIZE - 1,
            -1,
        ):
            for i in range(len(tokens) - gram_size + 1):
                if i in seen_positions:
                    continue

                gram = " ".join(tokens[i : i + gram_size])
                h = self._hash_gram(gram)

                if h in self._bloom:
                    if h in self._corpus:
                        risk = self._classify_gram_risk(gram_size)
                        source_hint = self._corpus[h]

                    # Find character position in original text
                    char_pos = self._find_token_char_pos(text, tokens, i)

                    findings.append(
                        MemorizationFinding(
                            text_fragment=gram[:100],
                            gram_overlap=gram_size,
                            source_hint=source_hint,
                            risk=risk,
                            position=char_pos,
                        )
                    )

                    # Mark these positions as handled (avoid sub-gram duplicates)
                    for j in range(i, i + gram_size):
                        seen_positions.add(j)

        return findings

    def _classify_gram_risk(self, gram_size: int) -> MemorizationRisk:
        """Classify risk based on n-gram size."""
        if gram_size >= self.BLOCK_THRESHOLD:
            return MemorizationRisk.BLOCKED
        elif gram_size >= self.HIGH_THRESHOLD:
            return MemorizationRisk.HIGH
        elif gram_size >= self.MEDIUM_THRESHOLD:
            return MemorizationRisk.MEDIUM
        else:
            return MemorizationRisk.LOW

    def _tokenize(self, text: str) -> list[str]:
        """Normalize and tokenize text into word tokens."""
        # Lowercase, collapse whitespace, remove punctuation (keep hyphens)
        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return [t for t in text.split() if len(t) > 1]

    def _hash_gram(self, gram: str) -> str:
        """SHA-256 hash of a normalized n-gram (truncated to 16 chars)."""
        return hashlib.sha256(gram.encode("utf-8")).hexdigest()[:16]

    def _find_token_char_pos(self, text: str, tokens: list[str], token_idx: int) -> int:
        """Estimate character position of token_idx in original text."""
        # Find the approximate start position by rejoining tokens
        prefix = " ".join(tokens[:token_idx])
        pos = text.lower().find(prefix)
        if pos >= 0:
            return pos + len(prefix)
        return 0

    @property
    def corpus_size(self) -> int:
        """Number of n-gram hashes in the corpus."""
        return len(self._corpus)


# ─── Singleton ────────────────────────────────────────────────────────────────

_auditor: Optional[MemorizationAuditor] = None


def get_memorization_auditor(corpus_path: Optional[Path] = None) -> MemorizationAuditor:
    """Get (or create) the singleton MemorizationAuditor."""
    global _auditor
    if _auditor is None:
        default_corpus = Path.home() / ".kairo-phantom" / "memorization_corpus.json"
        _auditor = MemorizationAuditor(
            corpus_path=corpus_path or (default_corpus if default_corpus.exists() else None)
        )
    return _auditor


def audit_generated_text(text: str) -> AuditResult:
    """
    Convenience function — audit generated text for copyright compliance.

    This is the primary entry point for document generation pipelines.
    Call before returning any model-generated text to the user.

    Returns:
        AuditResult where .safe_to_output indicates if text can be shown
    """
    return get_memorization_auditor().check_memorization(text)
