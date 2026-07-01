import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from sidecar.safety.bmc_gate import (
    SuffixAutomaton,
    longest_common_substring_with_tolerance,
    BmcGate,
    tokenize,
)


def test_suffix_automaton_longest_match():
    sa = SuffixAutomaton()
    text = "The quick brown fox jumps over the lazy dog"
    sa.build_from_text(text)

    # Test perfect match
    assert sa.find_longest_match(tokenize("quick brown fox")) == 3

    # Test partial match
    assert sa.find_longest_match(tokenize("quick brown wolf")) == 2

    # Test no match
    assert sa.find_longest_match(tokenize("hello world")) == 0


def test_longest_common_substring_with_tolerance():
    s1 = tokenize("The quick brown fox jumps over the lazy dog")
    s2 = tokenize("The quick brown cat jumps over the lazy dog")

    # Tolerates 1 replacement ("cat" vs "fox" in 10 words)
    match_len = longest_common_substring_with_tolerance(s1, s2, max_ratio=0.2)
    assert match_len >= 9

    # With low tolerance (0.0), it should be shorter since "cat" vs "fox" splits the match
    match_len_strict = longest_common_substring_with_tolerance(s1, s2, max_ratio=0.0)
    assert match_len_strict < 9


def test_bmc_gate_evaluation():
    gate = BmcGate(threshold=0.1, max_span_limit=5)

    continuations = [
        "The quick brown fox jumps over the lazy dog",
        "Hello world this is a completely fresh sentence with zero copyright overlap",
    ]
    references = [
        "The quick brown fox jumps over the lazy dog and runs away",
        "A book that has nothing to do with the other continuation",
    ]

    # Continuation 1 has a contiguous span >= 5 words. Continuation 2 does not.
    # Total violations = 1. k = 2. bmc = 1/2 = 0.5.
    bmc, max_span, passed = gate.evaluate_bmc(continuations, references)
    assert bmc == 0.5
    assert max_span >= 9
    assert passed is False
