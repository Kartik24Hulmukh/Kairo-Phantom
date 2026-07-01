"""
Metamorphic and property-based test generator for Kairo Phantom.
Auto-generates test scenario variations from seed scenarios to scale the test gauntlet from 40 to 200+ cases.
"""

import copy
import logging
from typing import Dict, Any, List
from hypothesis import strategies as st

log = logging.getLogger("kairo.test_generator")


class TestGenerator:
    """Generates metamorphic test variants from a set of seed scenarios."""

    def __init__(self):
        pass

    def generate_variants(
        self, seed_scenarios: List[Dict[str, Any]], target_count: int = 200
    ) -> List[Dict[str, Any]]:
        """Scale seed scenarios to target count using metamorphic perturbations."""
        log.info(
            f"[Test Gen] Scaling {len(seed_scenarios)} seed scenarios to {target_count} variants..."
        )

        variants = []
        # Copy original seeds first
        for seed in seed_scenarios:
            cleaned_seed = copy.deepcopy(seed)
            # Ensure seed itself has no null or empty fields
            for key, val in list(cleaned_seed.items()):
                if val is None or val == "":
                    if key == "prompt":
                        cleaned_seed[key] = "Default task prompt"
                    elif key == "category":
                        cleaned_seed[key] = "general"
                    elif key == "id":
                        cleaned_seed[key] = "seed_default"
                    else:
                        del cleaned_seed[key]
            variants.append(cleaned_seed)

        if not seed_scenarios:
            return variants

        perturbation_index = 0
        while len(variants) < target_count:
            # Pick a seed to perturb
            seed = seed_scenarios[perturbation_index % len(seed_scenarios)]

            # Apply a perturbation strategy
            strategy = perturbation_index % 4
            new_id = f"{seed.get('id')}_var_{perturbation_index}"

            variant = copy.deepcopy(seed)
            variant["id"] = new_id
            variant["is_variant"] = True

            # Ensure base fields are present before perturbing
            orig_prompt = seed.get("prompt")
            if orig_prompt is None or orig_prompt == "":
                orig_prompt = "Default task prompt"

            if strategy == 0:
                # Metamorphic: Whitespace & Casing
                variant["prompt"] = self._apply_whitespace_casing(orig_prompt)
                variant["strategy"] = "whitespace_casing"
            elif strategy == 1:
                # Metamorphic: Irrelevant preamble noise
                variant["prompt"] = self._apply_preamble_noise(orig_prompt)
                variant["strategy"] = "preamble_noise"
            elif strategy == 2:
                # Metamorphic: Terminology synonym swap
                variant["prompt"] = self._apply_synonym_swap(orig_prompt)
                variant["strategy"] = "synonym_swap"
            elif strategy == 3:
                # Metamorphic: Append polite query wrapper
                variant["prompt"] = self._apply_politeness_wrapper(orig_prompt)
                variant["strategy"] = "politeness_wrapper"

            # Clean up the generated variant to guarantee no empty prompts or null/invalid properties
            for key, val in list(variant.items()):
                if val is None or val == "":
                    if key == "prompt":
                        variant[key] = "Default task prompt"
                    elif key == "category":
                        variant[key] = seed.get("category") or "general"
                    elif key == "id":
                        variant[key] = new_id
                    elif key in ["oracle", "fix_budget"]:
                        if key in seed and seed[key] not in [None, ""]:
                            variant[key] = seed[key]
                        else:
                            del variant[key]
                    else:
                        del variant[key]

            # Validate that the prompt is not empty after potential perturbation
            if not variant.get("prompt") or not variant["prompt"].strip():
                variant["prompt"] = orig_prompt if orig_prompt.strip() else "Default task prompt"

            # Structure consistency check: category, oracle, and fix_budget properties of the variant scenarios
            # must be identical to their respective seed scenarios.
            for key in ["category", "oracle", "fix_budget"]:
                if key in seed:
                    variant[key] = seed[key]
                elif key in variant:
                    del variant[key]

            variants.append(variant)
            perturbation_index += 1

        log.info(f"[Test Gen] Generated {len(variants)} total scenarios.")
        return variants[:target_count]

    def _apply_whitespace_casing(self, prompt: str) -> str:
        """Apply random whitespace and capitalization changes without affecting intent."""
        if not prompt:
            return prompt

        words = prompt.split()
        if not words:
            return prompt

        casing_strategy = st.sampled_from(["upper", "lower", "title", "swapcase", "keep"])
        whitespace_char_strategy = st.sampled_from([" ", "  ", "\t", "\n", " \n", "\n  "])

        try:
            case = casing_strategy.example()
            pad_start = whitespace_char_strategy.example()
            pad_end = whitespace_char_strategy.example()
            seps = [whitespace_char_strategy.example() for _ in range(len(words) - 1)]
        except Exception:
            case = "upper"
            pad_start, pad_end = "\n  ", "  \n"
            seps = [" "] * (len(words) - 1)

        transformed_words = []
        for w in words:
            if case == "upper":
                transformed_words.append(w.upper())
            elif case == "lower":
                transformed_words.append(w.lower())
            elif case == "title":
                transformed_words.append(w.title())
            elif case == "swapcase":
                transformed_words.append(w.swapcase())
            else:
                transformed_words.append(w)

        middle = ""
        for i, w in enumerate(transformed_words):
            middle += w
            if i < len(seps):
                middle += seps[i]

        result = f"{pad_start}{middle}{pad_end}"
        if not result.strip():
            return prompt
        return result

    def _apply_preamble_noise(self, prompt: str) -> str:
        """Add irrelevant noise sentences at the beginning of the prompt using st.text."""
        noise_templates = [
            "Today is a sunny day.",
            "Please process this request.",
            "System instruction follow-up:",
            "We have a new update.",
            "Regarding the current workspace context:",
            "Hello, hope you are doing well.",
        ]

        noise_tag_strategy = st.text(
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_ ",
            min_size=3,
            max_size=15,
        )

        try:
            base_noise = st.sampled_from(noise_templates).example()
            tag = noise_tag_strategy.example().strip()
            if tag:
                preamble = f"{base_noise} [{tag}]"
            else:
                preamble = base_noise
        except Exception:
            preamble = "Today is a sunny day and the birds are chirping. Regarding the document:"

        return f"{preamble} {prompt}"

    def _apply_synonym_swap(self, prompt: str) -> str:
        """Swap standard words with synonyms dynamically using hypothesis."""
        synonyms = {
            "contract": ["agreement", "treaty", "deal", "pact"],
            "document": ["file", "paper", "record", "doc"],
            "edit": ["modify", "alter", "change", "update"],
            "verify": ["check", "validate", "confirm", "audit"],
            "indemnity": ["liability protection", "compensation", "insurance", "protection"],
            "budget": ["allowance", "funding", "allocation", "finances"],
        }

        words = prompt.split()
        if not words:
            return prompt

        perturbed_words = []
        for word in words:
            clean_word = word.lower().strip(".,;:!?()\"'")
            if clean_word in synonyms:
                try:
                    syn = st.sampled_from(synonyms[clean_word]).example()

                    if word.istitle():
                        syn = syn.title()
                    elif word.isupper():
                        syn = syn.upper()

                    replaced = word.lower().replace(clean_word, syn)
                    perturbed_words.append(replaced)
                except Exception:
                    perturbed_words.append(word)
            else:
                perturbed_words.append(word)

        return " ".join(perturbed_words)

    def _apply_politeness_wrapper(self, prompt: str) -> str:
        """Wrap with polite phrases dynamically using hypothesis."""
        starters = st.sampled_from(
            [
                "Would you please be so kind as to assist me with the following task:",
                "Could you help me with this, please:",
                "If you have a moment, I would appreciate your help with:",
                "Kindly assist with the following request:",
                "Could you please perform this task:",
            ]
        )

        enders = st.sampled_from(
            [
                "Thank you very much!",
                "Thanks in advance.",
                "I appreciate your help.",
                "Thank you!",
                "Much appreciated.",
            ]
        )

        filler_space = st.text(alphabet=" \t", min_size=1, max_size=3)

        try:
            start = starters.example()
            end = enders.example()
            sp1 = filler_space.example()
            sp2 = filler_space.example()
        except Exception:
            start = "Would you please be so kind as to assist me with the following task:"
            end = "Thank you very much!"
            sp1 = " "
            sp2 = " "

        return f"{start}{sp1}{prompt}{sp2}{end}"
