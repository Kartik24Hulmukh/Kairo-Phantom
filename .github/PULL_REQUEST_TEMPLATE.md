## Summary

<!-- A one-paragraph description of WHAT this PR does and WHY. -->

## Type of Change

- [ ] 🐛 Bug fix (non-breaking)
- [ ] ✨ New feature (non-breaking)
- [ ] 💥 Breaking change (requires migration steps)
- [ ] 📝 Documentation only
- [ ] ♻️  Refactor (no functional change)
- [ ] 🔒 Security fix
- [ ] ⚡ Performance improvement

## Testing

- [ ] `cargo test` passes locally (all 762+ tests green)
- [ ] New tests added for the change
- [ ] Tested manually on: Windows / macOS / Linux

## No-Bluff Checklist

- [ ] CI is green on the latest commit (both required gates: `CI Pass (aggregate)` and `Release Gate / Release Gate (aggregated)`)
- [ ] Every quantitative claim cites a reproducible command — no invented numbers
- [ ] No fabricated users, revenue, ARR, customers, stars, or downloads
- [ ] Real vs Experimental labels are correct (Experimental is never asserted as Real)
- [ ] No secrets, API keys, or credentials committed
- [ ] Branch auto-deletes after merge (enable in repo settings if not already on)

## Code Quality Checklist

- [ ] Code follows the project's Rust conventions (`cargo fmt`, `cargo clippy`)
- [ ] No new `unwrap()` calls without a comment explaining why it's safe
- [ ] No hardcoded API keys, credentials, or internal URLs
- [ ] Commit messages follow Conventional Commits: `fix:`, `feat:`, `docs:`, etc.
- [ ] PR title matches: `<type>(<scope>): <short description>`

## Related Issues

Closes #<!-- issue number -->

## Screenshots / Recordings

<!-- For UI or behaviour changes, add a GIF or screenshot. -->

## Notes for Reviewers

<!-- Anything non-obvious the reviewer should know. -->
