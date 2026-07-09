# Kairo Phantom — Scripted Demo (60–90 seconds)

**Title:** "Redline a contract. Get a receipt. Verify it yourself."
**Format:** screen recording with voiceover — terminal + document viewer. Runs entirely offline.
**Runtime target:** 75 seconds.

## Claim discipline (read before recording)

- Every on-screen action must be a REAL command from the repository, recorded live. No mock UI, no post-edited output.
- No user counts, revenue, logos, or invented benchmark numbers.
- Test counts may be shown ONLY as terminal output actually produced during the recording.
- Kairo v1 is READ + SUGGEST ONLY — it does not drive or write to source applications. Do not
  depict ghost-typing into Word or any live app control. The demo is the CLI redline pipeline.
- If a take fails, re-record — do not splice a fake success.

---

## Script + storyboard

### Shot 1 — Cold open: the problem (0:00–0:10)

**Visual:** Desktop with `fixtures/demo/sample_nda.docx` open in a document viewer. A visible
airplane-mode/offline indicator shows the machine is OFFLINE.

**VO:**
> "This is a contract that can't leave this machine. And this machine is offline.
> Watch an AI agent redline it anyway — and prove every edit it makes."

**On-screen text:** `OFFLINE · NO CLOUD · NO NETWORK`

---

### Shot 2 — Run the redline (0:10–0:30)

**Visual:** Terminal. Operator runs the repository's real redline command, no cuts:

```bash
python -m kairo.cli redline fixtures/demo/sample_nda.docx fixtures/demo/nda_playbook.json --out demo_output
```

**VO:**
> "One command. Kairo reads the NDA, applies the playbook, and produces real OOXML
> tracked changes — the same w-ins and w-del markup Word shows as redlines."

**On-screen text:** `Real tracked changes (w:ins / w:del) · Local, offline`

---

### Shot 3 — The tracked changes (0:30–0:45)

**Visual:** Open the output .docx from `demo_output/` in the viewer — tracked-changes markup
clearly visible on the indemnification clause.

**VO:**
> "These are real tracked changes in a real document. A human reviews and accepts them —
> Kairo never applies anything on its own."

---

### Shot 4 — The receipt appears (0:45–0:55)

**Visual:** Terminal shows the signed audit log (`demo_output/audit_log.json`). A receipt is
visible with its real fields: `action`, `prev_hash`, `self_hash`, `signature`.

**VO:**
> "Every action just produced this: an Ed25519-signed receipt, hash-chained to the one before it.
> Not a log you trust — a signature you check."

**On-screen text:** `Ed25519 signed · hash-chained`

---

### Shot 5 — Verify independently, then seal (0:55–1:10)

**Visual:** Terminal. Operator runs the repo's external verifier live:

```bash
python tools/verify_receipts_external.py demo_output/audit_log.json
```

Output shows the chain verifying. Then re-run the redline with `--sealed` to show the
air-gap report:

```bash
python -m kairo.cli redline fixtures/demo/sample_nda.docx fixtures/demo/nda_playbook.json --sealed --out demo_sealed
```

**VO:**
> "An independent verifier checks every signature and every hash link — without trusting Kairo.
> And sealed mode blocks all outbound connections while it works."

---

### Shot 6 — Close (1:10–1:15)

**Visual:** The landing page hero, then the GitHub repo URL.

**VO:**
> "Kairo Phantom. Offline. Verifiable. Open source. Don't take our word for it — run the tests."

**On-screen text:** `github.com/Kartik24Hulmukh/Kairo-Phantom · MIT`

---

## Recording checklist

- [ ] Machine offline (airplane mode), indicator visible in Shot 1.
- [ ] Fresh clone; `pip install -r requirements-test.txt` completed BEFORE recording.
- [ ] `python -m kairo.cli redline fixtures/demo/sample_nda.docx fixtures/demo/nda_playbook.json --out demo_output` succeeds BEFORE recording.
- [ ] `python tools/verify_receipts_external.py demo_output/audit_log.json` passes BEFORE recording.
- [ ] Single continuous take for Shot 2 — no cuts, no speed-up beyond 2x (label if sped up).
- [ ] Final pass: confirm zero unverifiable claims appear in VO or on-screen text, and nothing
      depicts Kairo driving a live application.

## Runnable stand-in

Until the desktop recording exists, `site/demo.html` provides a runnable in-browser
demonstration of the same trust model: it generates a real Ed25519 keypair via WebCrypto,
emits hash-chained receipts for a simulated redline session, signs them, and lets the viewer
tamper and watch verification fail. It is clearly labeled as a simulation of the receipt scheme,
not a recording of the agent.
