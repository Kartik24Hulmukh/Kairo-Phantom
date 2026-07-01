"""
Tests for TestGenerator using property-based metamorphic checks.
"""

from hypothesis import given, strategies as st, settings, HealthCheck
from sidecar.test_generator import TestGenerator

# Key nouns mapped to their synonyms in test_generator.py
KEY_NOUNS = {
    "contract": ["contract", "agreement", "treaty", "deal", "pact"],
    "document": ["document", "file", "paper", "record", "doc"],
    "edit": ["edit", "modify", "alter", "change", "update"],
    "verify": ["verify", "check", "validate", "confirm", "audit"],
    "indemnity": ["indemnity", "liability protection", "compensation", "insurance", "protection"],
    "budget": ["budget", "allowance", "funding", "allocation", "finances"],
}


@st.composite
def scenario_with_keywords(draw):
    key_noun = draw(st.sampled_from(list(KEY_NOUNS.keys())))
    prefix = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ",
            min_size=0,
            max_size=20,
        )
    )
    suffix = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ",
            min_size=0,
            max_size=20,
        )
    )

    # Construct prompt ensuring spacing
    prompt = f"{prefix.strip()} {key_noun} {suffix.strip()}".strip()
    if not prompt:
        prompt = key_noun

    category = draw(st.sampled_from(["word", "excel", "ppt", "pdf", "design"]))
    oracle = draw(
        st.one_of(
            st.none(), st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=20)
        )
    )
    fix_budget = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=100)))

    scenario = {
        "id": draw(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=10)
        ),
        "prompt": prompt,
        "category": category,
    }
    if oracle is not None:
        scenario["oracle"] = oracle
    if fix_budget is not None:
        scenario["fix_budget"] = fix_budget

    return scenario, key_noun


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(scenario_with_keywords(), min_size=1, max_size=10))
def test_metamorphic_invariants(scenario_data):
    """
    Test that metamorphic transformations do not violate property invariants.
    """
    seed_scenarios = [item[0] for item in scenario_data]

    generator = TestGenerator()
    # Generate variants
    variants = generator.generate_variants(seed_scenarios, target_count=50)

    # Assert correct count of variants
    assert len(variants) == 50

    L = len(seed_scenarios)
    for idx, var in enumerate(variants):
        # Invariant 4: None of the generated variants contain empty prompts or invalid/null properties.
        assert "prompt" in var
        assert var["prompt"] is not None
        assert var["prompt"].strip() != ""

        for k, v in var.items():
            assert v is not None, f"Property {k} is None in variant {var}"
            assert v != "", f"Property {k} is empty string in variant {var}"

        # Find which seed scenario this variant corresponds to based on index
        if idx < L:
            parent_seed = scenario_data[idx][0]
            parent_key_noun = scenario_data[idx][1]
        else:
            parent_seed = scenario_data[(idx - L) % L][0]
            parent_key_noun = scenario_data[(idx - L) % L][1]

        # Invariant 3: Structure consistency: category, oracle, and fix_budget properties
        # of the variant scenarios must be identical to their respective seed scenarios.
        assert var.get("category") == parent_seed.get("category")
        assert var.get("oracle") == parent_seed.get("oracle")
        assert var.get("fix_budget") == parent_seed.get("fix_budget")

        if var.get("is_variant"):
            strategy = var.get("strategy")
            prompt = var["prompt"]
            orig_prompt = parent_seed["prompt"]

            # Invariant 1: Casing/whitespace normalization:
            # perturbed prompt stripped/lowercased matches original prompt modulo formatting.
            if strategy == "whitespace_casing":
                norm_perturbed = "".join(prompt.split()).lower()
                norm_original = "".join(orig_prompt.split()).lower()
                assert norm_perturbed == norm_original

            # Invariant 2: Semantic containment:
            # synonym/wrapper perturbed prompt must contain key nouns/meaning of the original.
            if strategy in ["synonym_swap", "politeness_wrapper", "preamble_noise"]:
                allowed_words = KEY_NOUNS[parent_key_noun]
                prompt_lower = prompt.lower()

                # Check if any of the allowed words/synonyms are present in the perturbed prompt
                contained = any(allowed in prompt_lower for allowed in allowed_words)
                assert contained, f"Prompt '{prompt}' does not contain any of {allowed_words}"


def test_generate_variants_scaling():
    """
    Ensure generate_variants can scale the seed scenarios (e.g. 40 scenarios) to 200+ total scenarios cleanly.
    """
    generator = TestGenerator()

    # Create 40 seed scenarios
    seeds = []
    for i in range(40):
        seeds.append(
            {
                "id": f"seed_{i}",
                "prompt": f"Please verify contract {i} and check document",
                "category": "word" if i % 2 == 0 else "excel",
                "oracle": "some_oracle" if i % 3 == 0 else None,
                "fix_budget": i * 10 if i % 4 == 0 else None,
            }
        )

    variants = generator.generate_variants(seeds, target_count=250)
    assert len(variants) == 250

    # Check that ids are unique
    ids = [v["id"] for v in variants]
    assert len(ids) == len(set(ids))
