# R5 — LEGACY-APP GROUNDING: hybrid AX + vision fusion (2026 SOTA)

> Risk: does grounding hit ≥90% on messy legacy Win32/Electron/Java/Citrix apps — the apps
> whose lack of APIs is the whole reason to buy? Verified 2026 SOTA below; honest about the gap.

## The verified 2026 approach (Microsoft UFO², OmniParser-v2, DirectShell)
No single modality wins. Production grounding on legacy apps = **fused, arbitrated multimodal**:
1. **Accessibility leg** — Win UIA / macOS AX / Linux AT-SPI for standard controls.
   - Pattern to study: **DirectShell** (SQL-queryable UIA scaling to 11k+ elements) for fast,
     structured element access without vision when the tree is rich.
2. **Vision leg** — **OmniParser-v2 (CC-BY-4.0, verified)** set-of-marks parsing + supervision
   (MIT) detectors/trackers for icons/handles/canvas objects the AX tree can't see.
3. **Fusion + dedup** — per Microsoft **UFO²**: merge AX + vision candidates, **deduplicate by
   bounding-box overlap**, confidence-weight each element (cellar's per-element confidence idea).
4. **Verify** — every action is checked by the world-model + UI-state diff BEFORE receipt.

## Why this beats the AX-only cluster (Tarsier/cellar/clawdcursor/Tactile)
Pure-AX tools go blind on canvas/GPU/Citrix/RDP and image-only legacy UIs. Adding the
OmniParser-v2 vision leg is exactly the seam those tools miss — Kairo grounds where they fail.

## Honest gap (OSWorld, 2026)
Humans still beat agents on GUI grounding, multi-app workflows, and long-horizon state. So:
- Target **≥90% on the beachhead app set**, not "any app."
- **Deterministic scripting for critical paths** (record a verified path for the top tasks);
  fall back to live grounding for the long tail.
- Always **verify-before-commit**; a wrong click on a legal doc is unacceptable.

## Oracle + kill-test
- `grounding_accuracy`: labelled corpus of 100 screens across Win32/Electron/Java/Citrix/web +
  canvas (Figma/PPT). Score correct element resolution. Kill-proof = corrupt a leg → accuracy drops.
- Week-1 test (the original Anchor unknown): 10 gnarly apps × 5 target-and-click tasks, hand-scored.
  ≥45/50 incl. ≥7/10 on the two hardest legacy apps → build. <35/50 → web/native-only; narrow scope.

## Licences
OmniParser is **CC-BY-4.0** (attribution — cite it; verify the icon-detector **weights** license
separately before shipping). supervision MIT, page-agent MIT, olmocr Apache — all bundle-safe.
UFO²/DirectShell are **patterns to study**, not code to copy (clean-room per prompts/15).
