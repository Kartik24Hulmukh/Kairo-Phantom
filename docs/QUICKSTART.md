# Quickstart Guide — Kairo Phantom

Get from zero to your first AI ghost-write in under 60 seconds.

---

## 1. Install

### Windows (Recommended — One-Click)
```
Download: https://github.com/KairoPhantom/Kairo-Phantom/releases/latest/KairoSetup.exe
```
Run `KairoSetup.exe` — it installs Ollama, pulls the default model, and starts the daemon automatically.

### All Platforms (Rust Toolchain)
```bash
cargo install kairo-phantom
```

> **Prerequisites:** Rust 1.77+, Ollama installed and running (`ollama serve`)

---

## 2. Pull the Default Model (first time only)

```bash
ollama pull qwen2.5-coder:14b
```

The model is ~9 GB. After the first pull, Kairo works fully offline.

---

## 3. Start the Daemon

```bash
kairo start
```

You should see:
```
✓ Kairo Phantom v0.3.0 running
✓ Hotkey: Alt+Ctrl+M registered
✓ Backend: Ollama (offline)
✓ Memory: ~/.kairo-phantom/memory.db
```

---

## 4. Your First Ghost-Write

1. Open **Microsoft Word** (or Notepad, or any text editor)
2. Type a few sentences, then on a **new line** type:
   ```
   // rewrite this in formal business English
   ```
3. Press **Alt+Ctrl+M**
4. Watch the ghost-text appear
5. Press **Tab** to accept, **Esc** to reject

---

## Command Syntax

| Prefix | Mode | Effect |
|---|---|---|
| `//` | Ghost-Write | Rewrites or creates text |
| `//!` | Urgent | Immediate override (use sparingly) |
| `//?` | Query | Answers a question, doesn't modify document |
| `///` | Verbose | Ghost-write with longer context window |

---

## Supported Apps

| App | Platform | Injection Method |
|---|---|---|
| Microsoft Word | Windows | Adeu MCP bridge (Track Changes) |
| Microsoft Excel | Windows | Formula injection |
| Microsoft PowerPoint | Windows | Slide content injection |
| Pages / Keynote | macOS | Native Accessibility |
| LibreOffice Writer | Linux | AT-SPI2 bridge |
| Notepad / any text field | All | Keyboard simulation |

---

## Configuration

Config lives at `~/.kairo-phantom/config.toml`:

```toml
[ai]
backend = "ollama"          # or "openai", "anthropic", "nvidia-nim"
model   = "qwen2.5-coder:14b"

[hotkey]
trigger = "alt+ctrl+m"      # customize if alt+ctrl+m conflicts

[memory]
enabled = true              # set false to disable learning
```

---

## Useful Commands

```bash
kairo status          # check daemon health
kairo skill list      # list available Waza agents
kairo skill new myagent  # scaffold a new custom agent
kairo memory wipe     # clear all learned style data
kairo --help          # full command reference
```

---

## Troubleshooting

**"Alt+Ctrl+M not responding"**
- Run `kairo status` — is the daemon running?
- On macOS: grant Accessibility permission in System Preferences → Privacy & Security → Accessibility
- On Linux: ensure `AT-SPI2` is enabled (`gsettings set org.gnome.desktop.interface toolkit-accessibility true`)

**"Ollama not found"**
- Install from https://ollama.com/download
- Then run `ollama serve` in a terminal

**"Text not injected into Word"**
- Ensure the Adeu sidecar is running: `kairo sidecar status`
- Fallback: Kairo will use clipboard injection if Adeu is unavailable

---

## Next Steps

- [Memory System Deep Dive](memory/MEMORY_SYSTEM_DEEP_DIVE.md) — how Kairo learns your style
- [Waza Agent Builder](launch/WAZA_TUTORIAL.md) — build custom AI agents
- [Enterprise Guide](enterprise/SOC2_READINESS.md) — SSO, audit logs, compliance (ASPIRATIONAL — not certified)
- [KMB-1 Benchmark](benchmark/KMB1_BLOG_POST.md) — verify memory quality

---

**Need help?** Open an issue on [GitHub](https://github.com/KairoPhantom/Kairo-Phantom/issues) — we respond within 24 hours.
