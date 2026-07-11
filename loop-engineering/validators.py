#!/usr/bin/env python3
"""
Semantic evidence validators for the Kairo-Phantom loop (v1.2.1).

WHY THIS FILE EXISTS
--------------------
The co-founder red-team of v1.2 proved the loop still permitted FAKE GREEN:
attesting T3 with an empty `{}` file named `runs/g1_100run_report.json` was
accepted, flipping T3 and G1 to done. A hash proves file IDENTITY, not TRUTH.

v1.2.1 makes every human gate demand a SIGNED evidence MANIFEST plus an
ARTIFACT whose CONTENT is validated against the gate's real definition of done.
Gate outcomes (e.g. G1's 99/100 readback) are COMPUTED from individual run
records here — never trusted from a summary number in the file.

All checks fail CLOSED: if a signer is unknown, a field is missing, the
signature is absent/invalid, or the numbers do not clear the bar, the
attestation is REJECTED.
"""
import base64
import datetime
import hashlib
import json
import os


class EvidenceError(Exception):
    """Raised whenever evidence is missing, stale, unsigned, or insufficient."""


# ----------------------------- helpers -----------------------------

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical(obj):
    """Deterministic bytes for signing/verifying a manifest body."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def _resolve(here, p):
    return p if os.path.isabs(p) else os.path.join(here, p)


def load_trust_roots(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path) as f:
        data = json.load(f)
    return data.get("signers", {})


def verify_signature(manifest, trust_roots):
    """Ed25519-verify the manifest against a registered public key. Fail closed."""
    signer = manifest.get("signer")
    sig_b64 = manifest.get("signature")
    if not signer or not sig_b64:
        raise EvidenceError(
            "manifest has no signer/signature — unsigned attestations are rejected"
        )
    pub_b64 = trust_roots.get(signer)
    if not pub_b64:
        raise EvidenceError(
            f"signer '{signer}' is not in the trust roots (fail-closed). "
            f"Register the founder/assessor public key in schemas/trust_roots.json first."
        )
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
    except Exception as e:  # pragma: no cover
        raise EvidenceError(
            f"signature verification requires the 'cryptography' package ({e}); "
            f"refusing to accept an unverified attestation"
        )
    body = {k: v for k, v in manifest.items() if k != "signature"}
    try:
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64))
        pub.verify(base64.b64decode(sig_b64), canonical(body))
    except Exception:
        raise EvidenceError(
            f"Ed25519 signature is INVALID for signer '{signer}' — rejected"
        )
    return signer


def _parse_ts(v):
    try:
        return datetime.datetime.fromisoformat(str(v).replace("Z", ""))
    except Exception:
        raise EvidenceError(f"timestamp not ISO-8601: {v!r}")


def check_manifest_common(manifest, here, target_id, expected_commit=None,
                          max_age_days=45):
    """Structural + provenance + freshness + artifact-hash checks shared by all
    human attestations. Returns the resolved artifact path."""
    if not isinstance(manifest, dict):
        raise EvidenceError("evidence manifest must be a JSON object")
    if manifest == {} or all(not v for v in manifest.values()):
        raise EvidenceError("evidence manifest is empty — an empty file is not proof")
    for field in ("target", "base_commit", "created_at", "env",
                  "artifact", "signer", "signature"):
        if not manifest.get(field):
            raise EvidenceError(f"manifest missing required field '{field}'")
    if manifest["target"] != target_id:
        raise EvidenceError(
            f"manifest.target '{manifest['target']}' does not match the task/gate "
            f"being attested '{target_id}' (no evidence reuse across gates)"
        )
    env = manifest["env"]
    for k in ("os", "toolchain", "lockfile_sha256"):
        if not env.get(k):
            raise EvidenceError(f"manifest.env missing '{k}' (environment provenance required)")
    created = _parse_ts(manifest["created_at"])
    now = datetime.datetime.now()
    if created > now + datetime.timedelta(days=1):
        raise EvidenceError("manifest.created_at is in the future")
    age = (now - created).days
    if age > max_age_days:
        raise EvidenceError(f"evidence is stale ({age}d old > {max_age_days}d); regenerate it")
    if expected_commit and str(manifest["base_commit"]) != str(expected_commit):
        raise EvidenceError(
            f"base_commit mismatch: manifest {str(manifest['base_commit'])[:12]} "
            f"!= repo head {str(expected_commit)[:12]} (stale/rebased evidence)"
        )
    art = manifest["artifact"]
    if not isinstance(art, dict) or not art.get("path") or not art.get("sha256"):
        raise EvidenceError("manifest.artifact needs {path, sha256}")
    apath = _resolve(here, art["path"])
    if not os.path.exists(apath):
        raise EvidenceError(f"artifact file missing: {art['path']}")
    actual = sha256_file(apath)
    if actual.lower() != str(art["sha256"]).lower():
        raise EvidenceError(
            f"artifact HASH MISMATCH: declared {str(art['sha256'])[:16]}… "
            f"actual {actual[:16]}…"
        )
    return apath


def _load_json(path, what):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        raise EvidenceError(f"{what} is not valid JSON: {e}")


# ----------------------- per-gate semantic validators -----------------------

def validate_G1_desktop(manifest, artifact_path, here):
    """G1 (via T3). Compute the outcome from INDIVIDUAL run records; never trust
    a summary field. Bar: >=100 runs, readback >=99/100, tamper 100% of injected,
    canaries 100%, 0 silent gaps, Windows 11, recording checksum present."""
    rep = _load_json(artifact_path, "G1 run report")
    runs = rep.get("runs")
    if not isinstance(runs, list):
        raise EvidenceError("G1 report has no per-run 'runs' array — cannot verify from a summary")
    n = len(runs)
    readback = sum(1 for r in runs if r.get("readback_match") is True)
    injected = [r for r in runs if r.get("tamper_injected") is True]
    tamper_caught = sum(1 for r in injected if r.get("tamper_detected") is True)
    canaries = sum(1 for r in runs if r.get("canary_present") is True)
    gaps = sum(1 for r in runs if r.get("gap") is True)
    rec = rep.get("recording") or {}
    problems = []
    if n < 100:
        problems.append(f"only {n} runs (<100)")
    if readback < 99:
        problems.append(f"readback {readback}/{n} (<99)")
    if not injected:
        problems.append("no tamper was injected in any run (tamper detection unproven)")
    elif tamper_caught != len(injected):
        problems.append(f"tamper detected {tamper_caught}/{len(injected)} (must be 100%)")
    if canaries != n:
        problems.append(f"canaries {canaries}/{n} (must be 100%)")
    if gaps != 0:
        problems.append(f"{gaps} silent gap(s) (must be 0)")
    if "windows 11" not in str(rep.get("os", "")).lower():
        problems.append(f"os is not Windows 11: {rep.get('os')!r}")
    if not rec.get("sha256"):
        problems.append("no screen-recording checksum")
    if problems:
        raise EvidenceError("G1 FAILED (computed from run records): " + "; ".join(problems))
    return (f"G1 OK — computed from {n} records: readback {readback}/{n}, "
            f"tamper {tamper_caught}/{len(injected)}, canaries {canaries}/{n}, gaps 0")


def _require_list(rep, key, minimum, what):
    v = rep.get(key)
    if not isinstance(v, list) or len(v) < minimum:
        raise EvidenceError(f"{what}: '{key}' must be a list with >={minimum} entries")
    return v


def validate_assessor_outcome(manifest, artifact_path, here):
    """G2 (via T2A). Blind Mode A/B assessor test on DESKTOP OUTCOME evidence."""
    rep = _load_json(artifact_path, "T2A assessor report")
    if rep.get("blind") is not True:
        raise EvidenceError("T2A must be run BLIND (blind=true) — assessors must not know which is Kairo")
    assessors = _require_list(rep, "assessors", 3, "T2A")
    prefer = [a for a in assessors
              if a.get("prefers") == "B" and str(a.get("reason", "")).strip()]
    if len(prefer) < 1:
        raise EvidenceError("T2A: need >=1 assessor who prefers Mode B *with a written reason*")
    if not any(a.get("would_pay") in (True, "yes") for a in assessors):
        raise EvidenceError("T2A: no assessor indicated willingness to pay — record it explicitly (yes/no)")
    return f"T2A OK — {len(prefer)}/{len(assessors)} assessors prefer desktop-outcome Mode B with written reasons"


def validate_assessor_boundary(manifest, artifact_path, here):
    """T2B. Boundary-evidence value test (Mode B1 outcome vs B2 outcome+network)."""
    rep = _load_json(artifact_path, "T2B assessor report")
    if rep.get("blind") is not True:
        raise EvidenceError("T2B must be run BLIND (blind=true)")
    assessors = _require_list(rep, "assessors", 3, "T2B")
    prefer = [a for a in assessors
              if a.get("prefers") == "B2" and str(a.get("reason", "")).strip()]
    if len(prefer) < 1:
        raise EvidenceError("T2B: need >=1 assessor who values network-boundary evidence (B2) with a reason")
    return f"T2B OK — {len(prefer)}/{len(assessors)} value boundary evidence with written reasons"


def validate_boundary_witness(manifest, artifact_path, here):
    """T6. Scoped zero-egress: host observation + INDEPENDENT external witness +
    explicit declared gaps + honest coverage level. No whole-machine claim."""
    rep = _load_json(artifact_path, "T6 boundary report")
    host = rep.get("host_observation") or {}
    witness = rep.get("external_witness") or {}
    if not host.get("observed_channels"):
        raise EvidenceError("T6: host_observation.observed_channels missing")
    if not witness.get("independent") or not witness.get("signer"):
        raise EvidenceError("T6: external_witness must be independent and signed by a second party")
    if "declared_gaps" not in rep:
        raise EvidenceError("T6: must list 'declared_gaps' (honest scope, not a whole-machine claim)")
    level = str(rep.get("coverage_level", ""))
    if not level.startswith("KSEE-L"):
        raise EvidenceError("T6: must emit an honest coverage_level (KSEE-Ln), self-declared")
    return f"T6 OK — host + independent witness, gaps declared, coverage {level} (self-declared)"


def validate_competitive(manifest, artifact_path, here):
    """T1. Competitor verification + FTO; every claim tied to a primary source."""
    rep = _load_json(artifact_path, "T1 competitive/FTO report")
    comps = _require_list(rep, "competitors", 3, "T1")
    for c in comps:
        if not c.get("source_url") or not c.get("fto_status"):
            raise EvidenceError(f"T1: competitor {c.get('name','?')} needs source_url + fto_status")
    if not str(rep.get("frozen_novelty_claims", "")).strip():
        raise EvidenceError("T1: must record the frozen novelty-claim statement")
    return f"T1 OK — {len(comps)} competitors verified with sources + FTO status; novelty frozen"


def validate_verifier_conformance(manifest, artifact_path, here):
    """T4A. Native cryptographic verifier proven with POSITIVE and NEGATIVE
    conformance vectors + a reproducible-build hash. The coverage scorer is a
    helper and can NEVER satisfy this."""
    rep = _load_json(artifact_path, "T4A conformance report")
    pos = _require_list(rep, "positive_vectors", 1, "T4A")
    neg = _require_list(rep, "negative_vectors", 1, "T4A")
    if not all(v.get("result") == "accept" for v in pos):
        raise EvidenceError("T4A: every positive conformance vector must be ACCEPTED")
    if not all(v.get("result") == "reject" for v in neg):
        raise EvidenceError("T4A: every negative conformance vector must be REJECTED (tamper/replay/bad-sig)")
    for k in ("canonical_encoding", "signature_check", "merkle_proof",
              "nonce_freshness", "artifact_byte_hash", "reproducible_build_sha256"):
        if not rep.get(k):
            raise EvidenceError(f"T4A: verifier must demonstrate '{k}'")
    return f"T4A OK — verifier accepts {len(pos)} good / rejects {len(neg)} bad vectors; reproducible build recorded"


def validate_adapter(manifest, artifact_path, here):
    """T4B. First read-only adapter on a REAL public sample, license-checked,
    with positive + negative fixtures and explicit proved/not-proved output."""
    rep = _load_json(artifact_path, "T4B adapter report")
    if not rep.get("sample_source_url") or not rep.get("sample_license"):
        raise EvidenceError("T4B: need a real public sample_source_url + sample_license")
    _require_list(rep, "positive_fixtures", 1, "T4B")
    _require_list(rep, "negative_fixtures", 1, "T4B")
    verdicts = set()
    for f in rep.get("positive_fixtures", []) + rep.get("negative_fixtures", []):
        verdicts.add(f.get("verdict"))
    if not verdicts.issubset({"proved", "not_proved", "unavailable"}):
        raise EvidenceError("T4B: fixtures must output proved/not_proved/unavailable (no implied endorsement)")
    return "T4B OK — real sample normalized with pos+neg fixtures and honest verdicts"


def validate_ksee(manifest, artifact_path, here):
    """T5. KSEE draft only AFTER assessor feedback; needs external reviewers."""
    rep = _load_json(artifact_path, "T5 KSEE draft report")
    if not str(rep.get("spec_version", "")).strip():
        raise EvidenceError("T5: KSEE draft needs a spec_version")
    _require_list(rep, "external_reviewers", 1, "T5")
    if not str(rep.get("free_offline_verifier_url", "")).strip():
        raise EvidenceError("T5: publish the free offline verifier alongside the draft")
    return "T5 OK — KSEE draft with >=1 external reviewer and a free offline verifier"


def validate_funding(manifest, artifact_path, here):
    """G0. Funding eligibility & structure documented; do NOT build cap table
    around a grant."""
    rep = _load_json(artifact_path, "G0 funding decision")
    if not str(rep.get("company_structure", "")).strip():
        raise EvidenceError("G0: document the company structure decision")
    if "sbir_eligible_now" not in rep:
        raise EvidenceError("G0: state sbir_eligible_now (true/false) explicitly")
    if not rep.get("sbir_eligible_now") and not str(rep.get("replacement_funding_spine", "")).strip():
        raise EvidenceError("G0: if SBIR is excluded, name the replacement non-dilutive/revenue funding spine")
    return "G0 OK — structure + funding-eligibility decision documented"


def validate_market(manifest, artifact_path, here):
    """G3. >=1 PAID/budgeted pilot (budget owner, price, start, workflow, decision
    date) + >=1 external reproduction + >=3 qualified workflows. LOIs are only a
    supporting metric — never the gate."""
    rep = _load_json(artifact_path, "G3 market proof")
    pilots = _require_list(rep, "paid_pilots", 1, "G3")
    for p in pilots:
        for k in ("budget_owner", "price", "start_date", "workflow", "decision_date"):
            if not str(p.get(k, "")).strip():
                raise EvidenceError(f"G3: paid pilot missing '{k}' (an LOI is not a paid pilot)")
    _require_list(rep, "external_reproductions", 1, "G3")
    _require_list(rep, "qualified_workflows", 3, "G3")
    return f"G3 OK — {len(pilots)} paid pilot(s), external repro, >=3 workflows"


def validate_busfactor(manifest, artifact_path, here):
    """G4 (day-90, softened). Recovery + reproducible build + key custodian +
    external reviewer + co-founder pipeline. NOT 'co-founder onboarded'."""
    rep = _load_json(artifact_path, "G4 bus-factor report")
    for k in ("recovery_plan", "external_reproducible_build",
              "second_key_custodian", "cofounder_pipeline"):
        if not str(rep.get(k, "")).strip():
            raise EvidenceError(f"G4: missing '{k}'")
    _require_list(rep, "external_reviewers", 1, "G4")
    return "G4 OK — recovery, reproducible build, key custodian, external reviewer, pipeline"


# task/gate id -> semantic validator
VALIDATORS = {
    "T1": validate_competitive,
    "T3": validate_G1_desktop,
    "T2A": validate_assessor_outcome,
    "T2B": validate_assessor_boundary,
    "T6": validate_boundary_witness,
    "T4A": validate_verifier_conformance,
    "T4B": validate_adapter,
    "T5": validate_ksee,
    "G0": validate_funding,
    "G3": validate_market,
    "G4": validate_busfactor,
}


def validate(target_id, manifest, artifact_path, here):
    fn = VALIDATORS.get(target_id)
    if fn is None:
        raise EvidenceError(
            f"no semantic validator registered for '{target_id}'; "
            f"refusing to accept a human attestation without one (fail-closed)"
        )
    return fn(manifest, artifact_path, here)


def verify_history_chain(history):
    """Recompute every event hash from prev_hash + canonical body. Returns
    (ok, message). Any break means the ledger was altered."""
    prev = "genesis"
    for i, ev in enumerate(history or []):
        if ev.get("prev_hash") != prev:
            return False, f"event #{i} prev_hash mismatch (chain broken)"
        body = {k: v for k, v in ev.items() if k != "hash"}
        expect = hashlib.sha256(
            (prev + json.dumps(body, sort_keys=True)).encode()
        ).hexdigest()
        if ev.get("hash") != expect:
            return False, f"event #{i} hash mismatch (event body was altered)"
        prev = ev["hash"]
    return True, f"history chain intact ({len(history or [])} events)"
