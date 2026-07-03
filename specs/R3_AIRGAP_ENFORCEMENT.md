# R3 — AIR-GAP ENFORCEMENT: make "offline" architecturally impossible to break

> Risk: when the local model underperforms, the temptation is a silent cloud fallback — which
> destroys the entire trust claim. Fix: make air-gap a SEALED MODE, not a config flag.

## The enforcement model (defense in depth)
1. **Two build profiles.** `kairo-sealed` ships with **no network client code linked at all** —
   no HTTP stack, no telemetry SDK, no LiteLLM cloud provider. You cannot phone home because the
   capability isn't compiled in. `kairo-connected` is a separate build for non-regulated users.
2. **Capability-based egress control.** Even in `kairo-connected`, network is a capability the
   privileged planner must be granted per-flow; tainted/perceived content can never grant it
   (ties to prompts/05 out-of-band injection defense).
3. **The egress oracle runs live.** loopback + NIC capture during every flow; asserts **0**
   outbound packets in sealed mode (LAN-only stays within subnet for CRDT collaboration).
   Kill-proof: open a socket → oracle fails the run and the UI shows it.
4. **Signed egress report per session** (CLAIM_DISCIPLINE wording): "reproducible, signed report
   showing zero outbound connections; source open for audit." NOT "cryptographic proof forever."
5. **No cloud fallback path exists in sealed mode.** The R1 fallback ladder degrades to a
   visible "low-confidence, human review" flag — it never reaches for the cloud. This is a
   compile-time guarantee, verified by `license_gate`-style static scan for network symbols.

## CI gate (add to ci/)
`sealed_no_network.yml`: static-analyze the `kairo-sealed` artifact for ANY networking symbol
(sockets, DNS, TLS, HTTP libs, telemetry). Build fails if found. This is the machine-checkable
version of the trust promise.

## Oracle
`airgap_egress` (already in VERIFICATION_ORACLES): 0 outbound in sealed mode; kill-proof = a test
build that opens a socket must turn the gate red. Plus `sealed_binary_scan`: the shipped sealed
binary contains no network symbols.

## Why this is the moat, not a feature
A cloud tool can claim privacy; it can never ship a binary with the network stack removed and a
live packet report at zero. Sealed mode is the physically-demonstrable difference — and the
reason regulated buyers can say yes.
