# ANCHOR — perception & grounding substrate (integrated INTO Kairo, not sold)

Anchor replaces Kairo's `vlm_bridge`, upgrades `world_model`, and removes the mocked
context-capture path. It is local + MCP-native. It is a DEPENDENCY/substrate, not the
product — the horizontal "grounding layer" market is already crowded (see
research/EVIDENCE_INDEX.md), so we consume it and win on domain depth + trust + voice.

## Pipeline
```
 screen (desktop app / browser)
   │
   ├─ AX-tree leg   : Win UIA · macOS AX · Linux AT-SPI      (role/name/value/bounds)
   ├─ OCR leg       : olmocr (Apache-2.0)                    (text on canvas)
   ├─ vision leg    : supervision (MIT) + small YOLO/RT-DETR/SAM  (icons/handles/shapes)
   │                   + supervision trackers -> STABLE ids across frames
   │                   + OBB-aware anchors -> rotated canvas objects
   ▼
 fusion  -> unified element graph {role,name,value,bounds,affordance,confidence}
   ▼
 compaction -> token-efficient map  (target >= 70% reduction vs raw screenshot)
   ▼
 world_model (CUWM) -> predict next UI state for a candidate action
   ▼
 CUA planner (privileged, TRUSTED input only)  ->  action
   ▼
 Universal Verifier + uistate diff  ->  verify BEFORE receipt
```

## Why the vision leg is the differentiator
Pure AX-tree tools (Tarsier, cellar, ScreenHand, clawdcursor) go blind on canvas/GPU
surfaces (Figma, PPT canvas, games, Citrix/RDP). supervision's detection + tracking
gives Kairo grounding where the whole cluster fails.

## Security coupling
All perception output is TAINTED (untrusted) and feeds the out-of-band policy monitor
(prompts/05). Perceived text can inform content but can never authorise a capability.

## Licences (verify before bundling)
- olmocr: Apache-2.0 (OK) · supervision: MIT (OK) · page-agent: MIT (OK)
- Tarsier / clawdcursor / cellar: STUDY patterns only; cellar core Apache but rest
  BSL-1.1; do NOT copy incompatible code. Skyvern/chunkr: AGPL — never bundle.
