"""Answerability report.

Integrity says the record was not altered. Answerability says whether the
record can answer the questions that matter. Two states only: ANSWERED or
NOT ANSWERABLE FROM THIS RECORD. Never infers: if the typing or the relation
is absent, the determination is NOT ANSWERABLE, even when the outcome is
obvious. A false NOT ANSWERABLE is intended; a false ANSWERED is a bug.
"""

QUESTIONS = {
    "D1": "Did protected data cross a boundary?",
    "D2": "Could a human have intervened before the irreversible step?",
    "D3": "Did the barrier hold, or was it merely present?",
    "D4": "Was delegated authority valid at the moment it was used?",
}

ANSWERED = "ANSWERED"
NOT_ANSWERABLE = "NOT ANSWERABLE FROM THIS RECORD"


def _ctx(r):
    c = r.get("context")
    return c if isinstance(c, dict) else {}


def _act(r):
    return str(r.get("action", "")).lower()


def answerability(receipts):
    out = []

    ev = [
        r.get("seq")
        for r in receipts
        if "data_category" in _ctx(r)
        and "document_id" in _ctx(r)
        and "chunk_id" in _ctx(r)
        and ("boundary" in _act(r) or "boundary" in _ctx(r))
    ]
    missing = [] if ev else [
        "typing: no receipt carries data_category + document/chunk lineage + boundary marking"
    ]
    out.append({"id": "D1", "question": QUESTIONS["D1"],
                "status": ANSWERED if ev else NOT_ANSWERABLE,
                "evidence": ev, "missing": missing})

    approvals = [r.get("seq") for r in receipts if "approv" in _act(r)]
    irreversibles = [
        r.get("seq")
        for r in receipts
        if "irreversible" in _act(r) or _ctx(r).get("irreversible") is True
    ]
    rel = any(a < i for a in approvals for i in irreversibles)
    missing = []
    if not approvals:
        missing.append("typing: no approval-typed event")
    if not irreversibles:
        missing.append("typing: no event typed as irreversible")
    if approvals and irreversibles and not rel:
        missing.append("relation: no approval precedes an irreversible action")
    ev = sorted(set(approvals + irreversibles)) if (approvals and irreversibles and rel) else []
    out.append({"id": "D2", "question": QUESTIONS["D2"],
                "status": ANSWERED if ev else NOT_ANSWERABLE,
                "evidence": ev, "missing": missing})

    controls = [r for r in receipts if any(k in _act(r) for k in ("control", "gate", "policy"))]
    held = [r.get("seq") for r in controls if r.get("outcome")]
    missing = []
    if not controls:
        missing.append("typing: no control-invocation event")
    elif not held:
        missing.append("typing: control events carry no outcome (present, but no record of holding)")
    out.append({"id": "D3", "question": QUESTIONS["D3"],
                "status": ANSWERED if held else NOT_ANSWERABLE,
                "evidence": held, "missing": missing})

    grants = [
        r for r in receipts
        if any(k in _act(r) for k in ("authority", "grant"))
        and (_ctx(r).get("valid_until") or _ctx(r).get("not_after"))
    ]
    ev, missing = [], []
    if not grants:
        missing.append("typing: no authority grant with a validity window")
    else:
        g = grants[0]
        until = str(_ctx(g).get("valid_until") or _ctx(g).get("not_after"))
        uses = [
            r.get("seq")
            for r in receipts
            if (r.get("seq") or 0) > (g.get("seq") or 0)
            and r.get("agent_id") == g.get("agent_id")
            and str(r.get("timestamp", "")) <= until
        ]
        if uses:
            ev = [g.get("seq")] + uses[:3]
        else:
            missing.append("relation: no later action by the grantee inside the validity window")
    out.append({"id": "D4", "question": QUESTIONS["D4"],
                "status": ANSWERED if ev else NOT_ANSWERABLE,
                "evidence": ev, "missing": missing})

    return out
