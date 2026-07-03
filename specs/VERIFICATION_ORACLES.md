# VERIFICATION ORACLES — reference

Every oracle is deterministic and ships with a kill-proof (a known-bad input it must
reject). Oracles live under `kairo.oracles.*` and are used by tests + the gauntlet.

| Oracle | Verifies | Mechanism | Kill-proof |
|---|---|---|---|
| docx_readback | Word edits | re-open with python-docx, assert structure/text/tracked-changes | corrupt a run -> fail |
| xlsx_recompute | Excel VALUES | LibreOffice-headless recalc, read back values, compare to independent Python calc | break recompute -> fail |
| pptx_readback | Slides | python-pptx, assert slide/shape/layout | drop a shape -> fail |
| pdf_roundtrip | PDF extract | PyMuPDF/pdfplumber text+coords | shift coords -> fail |
| airgap_egress | zero network | loopback+NIC capture during flow; assert 0 outbound in air-gap; LAN stays in subnet | open a socket -> fail |
| cua_uistate_diff | action happened | Anchor before/after screen map; assert structural transition | no-op action -> fail |
| cua_verifier | trajectory correct | rubric verifier (process+outcome), all screenshots | reward a failed run -> fail |
| c2pa_verify | provenance | parse crJSON, verify Ed25519 + hash binding | tamper file/receipt -> fail |
| audit_chain | audit integrity | hash-chain continuity | forge entry -> chain breaks |
| style_match | voice fidelity | blind author A/B preference rate | shuffle labels -> no signal |
| injection_block | security | injection corpus (multilingual+adaptive); privileged action blocked from tainted input | disable monitor -> attacks pass |

## Rules
- Seed all randomness; oracles must be reproducible.
- An oracle that cannot be shown to fail on bad input is itself rigged — fix it.
