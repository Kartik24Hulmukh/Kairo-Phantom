# CLAIM DISCIPLINE — the wording that survives a hostile security teardown

> Fix G4. The single fastest way to lose the regulated buyers you are courting is to make a
> trust claim a security researcher can break on stage. Every marketing and in-product claim
> must be **literally true and demonstrable**, or it must not ship.

## The air-gap / privacy claim
- ❌ DO NOT say: "We cryptographically prove no bytes ever leave your machine."
  (A packet oracle proves no egress *during an observed run* — not the absence of a covert
  channel, not future runs, not a compromised OS. This claim is falsifiable and will be falsified.)
- ✅ DO say: **"Runs fully on your device. Every run emits a reproducible, signed egress
  report showing zero outbound connections, verifiable by your own network monitor. The
  source is open for audit."**
- The strength is **reproducibility + auditability**, not an absolute impossibility proof.
  That is still a claim no cloud tool can make — and it survives scrutiny.

## The personalization claim (fix G5)
- ❌ DO NOT say: "Local personalization beats cloud Copilot's quality." (Cloud can fine-tune
  per user too; you cannot guarantee you win on raw quality.)
- ✅ DO say: **"Learns your voice from your own documents, on your machine — including the
  documents you are contractually or legally forbidden from sending to any cloud."**
  The moat is **data sovereignty and reach**, not a quality superlative.

## The "real domain" claim (fix, DoD §9)
- ❌ DO NOT label a prompt-only domain "Real."
- ✅ Every domain shows its status in the UI: `Real` (has a passing read-back oracle) vs
  `Experimental` (prompt-only). Shipping a mislabelled domain is a release blocker.

## The provenance claim (fix G6)
- ✅ v1: "Every file change is recorded in a tamper-evident, hash-chained signed audit log."
  (True and verifiable today.)
- ⏳ Fast-follow: "C2PA Content Credentials" — only once a doc-side verifier exists that a
  third party can actually run. Emitting a receipt nobody can verify is not a feature.

## The benchmark claims
- Any "N% grounding accuracy", "≥70% token reduction", "beats cloud on task X" number ships
  with: the dataset, the date, the exact command to reproduce, and the failure cases. No
  cherry-picked hero numbers without the reproducer.

## Golden rule
If you cannot demo the claim live, in under 60 seconds, on a machine you did not pre-rig,
the claim does not ship. This is the same no-mock discipline that makes the engineering
moat real — applied to marketing.
