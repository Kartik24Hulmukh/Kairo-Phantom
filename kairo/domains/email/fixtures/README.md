# Email/Comms Domain — Fixture Ground Truth

This directory contains fixtures for the Email/comms domain oracle tests.

## Contents

- `attachment.txt` — a real text attachment used in attachment read-back tests
- `attachment.bin` — a binary attachment with known bytes for hash verification
- `ground_truth.json` — expected values for all gauntlet scenarios

## Ground Truth

The `ground_truth.json` file specifies the expected To, Cc, From, Subject,
Body, attachment names, and attachment SHA-256 hashes for each gauntlet
scenario. The oracles compose drafts from these specs, save to a temp Maildir,
re-open, and assert every field matches.
