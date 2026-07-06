# PROVENANCE: original | On-device style personalization domain descriptor
"""On-device style personalization — per-user style adapter over local model.

Registers the ``personalize`` CLI subcommand with sub-actions:
  - train:   train a style adapter from user writing samples
  - apply:   apply a trained adapter to generate text
  - ab:      generate a blind A/B session for author judgment
  - record:  record author choices for an A/B session
  - status:  show personalization status

Status: Experimental — pending author blind A/B (>=60% preference required).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from kairo.domains.registry import Domain, register


def _register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "personalize",
        help="On-device style personalization (LoRA-analog adapter) — Experimental",
    )
    pz_sub = parser.add_subparsers(dest="action", help="Personalization action")

    # personalize train
    pz_train = pz_sub.add_parser(
        "train", help="Train a style adapter from user samples"
    )
    pz_train.add_argument("samples", help="Path to JSON file with user writing samples")
    pz_train.add_argument(
        "--baseline", default="", help="Path to baseline samples JSON"
    )
    pz_train.add_argument(
        "--out", default="style_adapter.json", help="Output adapter path"
    )
    pz_train.add_argument(
        "--outdir", default="personalization_output", help="Output directory"
    )

    # personalize apply
    pz_apply = pz_sub.add_parser(
        "apply", help="Apply a trained adapter to generate text"
    )
    pz_apply.add_argument("adapter", help="Path to trained adapter JSON")
    pz_apply.add_argument(
        "--baseline", default="", help="Path to baseline samples JSON"
    )
    pz_apply.add_argument("--prompt", default="the", help="Prompt for generation")
    pz_apply.add_argument(
        "--outdir", default="personalization_output", help="Output directory"
    )

    # personalize ab
    pz_ab = pz_sub.add_parser("ab", help="Generate a blind A/B session")
    pz_ab.add_argument("adapter", help="Path to trained adapter JSON")
    pz_ab.add_argument("--baseline", default="", help="Path to baseline samples JSON")
    pz_ab.add_argument("--tasks", default="", help="Path to A/B tasks JSON")
    pz_ab.add_argument(
        "--outdir", default="personalization_output", help="Output directory"
    )

    # personalize record
    pz_record = pz_sub.add_parser(
        "record", help="Record author choices for an A/B session"
    )
    pz_record.add_argument("session", help="Path to A/B session JSON")
    pz_record.add_argument("choices", help="Path to choices JSON (list of 'A' or 'B')")

    # personalize status
    pz_status = pz_sub.add_parser("status", help="Show personalization status")
    pz_status.add_argument(
        "--outdir", default="personalization_output", help="Output directory"
    )


def _run(args: argparse.Namespace) -> int:
    if not hasattr(args, "action") or args.action is None:
        print("ERROR: No personalize action specified. Use --help.", file=sys.stderr)
        return 1

    out_dir = Path(getattr(args, "outdir", "personalization_output")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    from kairo.personalization.engine import (
        BlindABHarness,
        ABSession,
        ABTaskResult,
        TinyNGramModel,
        check_drift,
        load_adapter,
        personalization_pipeline,
    )

    # Default baseline samples (formal/verbose style)
    _DEFAULT_BASELINE = [
        "It is furthermore incumbent upon the committee to deliberate upon the aforementioned matters.",
        "Notwithstanding the foregoing, the parties hereto agree to the terms set forth herein.",
        "Pursuant to the provisions of Article 7, the contractor shall be liable for damages.",
        "The aforementioned analysis notwithstanding, it is imperative that all stakeholders be consulted.",
        "In accordance with established protocols, the procedure shall be initiated forthwith.",
    ]

    def _load_baseline(path: str) -> list[str]:
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return (
                data.get("baseline_samples", data) if isinstance(data, dict) else data
            )
        return _DEFAULT_BASELINE

    if args.action == "train":
        with open(args.samples, encoding="utf-8") as f:
            data = json.load(f)
        user_texts = data.get("user_samples", data) if isinstance(data, dict) else data
        baseline_texts = _load_baseline(args.baseline)

        adapter_path = str(out_dir / args.out)
        result = personalization_pipeline(
            baseline_texts=baseline_texts,
            user_texts=user_texts,
            adapter_path=adapter_path,
        )
        if not result.ok:
            print(f"ERROR: {result.error}", file=sys.stderr)
            return 1

        print()
        print("=" * 60)
        print("  KAIRO PHANTOM — STYLE ADAPTER TRAINED")
        print("=" * 60)
        print(
            f"  Adapter ID:    {result.adapter.adapter_id if result.adapter else 'N/A'}"
        )
        print(
            f"  Samples:       {result.adapter.sample_count if result.adapter else 0}"
        )
        print(f"  Style shift:   {result.style_shift:.4f}")
        print(f"  Adapter file:  {result.adapter_path}")
        print("  Status:        Experimental — pending author blind A/B")
        print("=" * 60)
        return 0

    elif args.action == "apply":
        adapter = load_adapter(args.adapter)
        baseline_texts = _load_baseline(args.baseline)

        baseline_model = TinyNGramModel(n=2)
        baseline_model.train(baseline_texts)
        adapted_model = baseline_model.apply_adapter(adapter)

        baseline_out = baseline_model.generate(args.prompt, seed=42)
        adapted_out = adapted_model.generate(args.prompt, seed=42)

        print()
        print("=" * 60)
        print("  KAIRO PHANTOM — STYLE ADAPTER APPLIED")
        print("=" * 60)
        print(f"  Prompt:        {args.prompt}")
        print(f"  Baseline:      {baseline_out}")
        print(f"  Adapted:       {adapted_out}")
        print(
            f"  Style shift:   {baseline_model.distribution_distance(adapted_model):.4f}"
        )
        print("=" * 60)
        return 0

    elif args.action == "ab":
        adapter = load_adapter(args.adapter)
        baseline_texts = _load_baseline(args.baseline)

        # Load tasks
        if args.tasks and os.path.exists(args.tasks):
            with open(args.tasks, encoding="utf-8") as f:
                tasks = json.load(f).get("ab_tasks", [])
        else:
            tasks = [
                {
                    "prompt": "Finish this section:",
                    "context": "The results show improvement.",
                },
                {
                    "prompt": "Write a conclusion:",
                    "context": "The project was successful.",
                },
                {
                    "prompt": "Add a recommendation:",
                    "context": "Based on our findings.",
                },
            ]

        baseline_model = TinyNGramModel(n=2)
        baseline_model.train(baseline_texts)
        adapted_model = baseline_model.apply_adapter(adapter)

        harness = BlindABHarness(seed=42)
        session = harness.generate_session(baseline_model, adapted_model, tasks)

        session_path = str(out_dir / "ab_session.json")
        harness.save_session(session, session_path)

        print()
        print("=" * 60)
        print("  KAIRO PHANTOM — BLIND A/B SESSION GENERATED")
        print("=" * 60)
        print(f"  Session ID:    {session.session_id}")
        print(f"  Tasks:         {len(session.tasks)}")
        print(f"  Session file:  {session_path}")
        print("  Status:        Experimental — author must judge each pair")
        print()
        print("  INSTRUCTIONS FOR AUTHOR:")
        print("  1. Open the session file")
        print("  2. For each task, read output_a and output_b")
        print("  3. Choose 'A' or 'B' (which better matches YOUR style)")
        print('  4. Save choices as JSON list: ["A", "B", "A", ...]')
        print("  5. Run: kairo personalize record <session> <choices>")
        print("=" * 60)
        return 0

    elif args.action == "record":
        with open(args.session, encoding="utf-8") as f:
            session_data = json.load(f)
        with open(args.choices, encoding="utf-8") as f:
            choices = json.load(f)

        from kairo.personalization.engine import ABSession, ABTaskResult

        session = ABSession(
            session_id=session_data["session_id"],
            tasks=[
                ABTaskResult(
                    task_id=t["task_id"],
                    prompt=t["prompt"],
                    output_a=t["output_a"],
                    output_b=t["output_b"],
                    a_is_adapter=t["a_is_adapter"],
                )
                for t in session_data["tasks"]
            ],
        )

        harness = BlindABHarness(seed=42)
        session = harness.record_choices(session, choices)

        # Check drift alarm
        from kairo.personalization.engine import check_drift

        alarm = check_drift(session.preference_rate, prior_rate=0.5, tolerance=0.10)

        print()
        print("=" * 60)
        print("  KAIRO PHANTOM — A/B RESULTS RECORDED")
        print("=" * 60)
        print(f"  Session:           {session.session_id}")
        print(f"  Tasks:             {len(session.tasks)}")
        print(f"  Preference rate:   {session.preference_rate:.2%}")
        print(f"  Drift alarm:       {'TRIGGERED' if alarm.triggered else 'OK'}")
        print(
            f"  Status:            {'Real' if session.preference_rate >= 0.60 else 'Experimental'}"
        )
        print("=" * 60)
        return 0

    elif args.action == "status":
        print()
        print("=" * 60)
        print("  KAIRO PHANTOM — PERSONALIZATION STATUS")
        print("=" * 60)
        print("  Status: Experimental — pending author blind A/B")
        print("  Requirement: >=60% author preference to become Real")
        print("  If <50%: stays Experimental")
        print()
        print("  To run blind A/B:")
        print("  1. kairo personalize train <samples.json> --out adapter.json")
        print("  2. kairo personalize ab adapter.json --tasks tasks.json")
        print("  3. Judge each pair, save choices")
        print("  4. kairo personalize record session.json choices.json")
        print("=" * 60)
        return 0

    return 1


DOMAIN = Domain(
    name="personalization",
    cli_name="personalize",
    status="Experimental",
    summary=(
        "air_gap_train_infer + adapter_roundtrip + feedback_signal + drift_alarm — "
        "per-user style-adapter (LoRA-analog) over local model, trained on-device "
        "from accept/edit/reject feedback, zero-egress during train+infer, "
        "kill-proven; blind A/B harness built (NOT self-scored); "
        "Experimental — pending author blind A/B (>=60% preference required)"
    ),
    register_cli=_register_cli,
    run=_run,
    requirements=[
        "# pure-stdlib — uses json, math, random, collections (no external dependencies)",
        "# In production: llama.cpp + LoRA/PEFT weights (not required for CI mechanics)",
    ],
)

register(DOMAIN)
