# Third-Party Notices

Kairo Phantom integrates the following open-source libraries and projects. We are grateful to every maintainer listed here.

All licenses listed are compatible with the MIT license under which Kairo Phantom is distributed.

---

## Core Runtime

| Component | Version | License | Upstream |
|:---|:---|:---|:---|
| **Tokio** | 1.44 | MIT | https://github.com/tokio-rs/tokio |
| **Serde** | 1.x | MIT / Apache-2.0 | https://github.com/serde-rs/serde |
| **serde_json** | 1.x | MIT / Apache-2.0 | https://github.com/serde-rs/json |
| **anyhow** | 1.x | MIT / Apache-2.0 | https://github.com/dtolnay/anyhow |
| **tracing** | 0.1 | MIT | https://github.com/tokio-rs/tracing |
| **tracing-subscriber** | 0.3 | MIT | https://github.com/tokio-rs/tracing |

## AI & Inference

| Component | Version | License | Upstream |
|:---|:---|:---|:---|
| **ollama-rs** | 0.2 | MIT | https://github.com/pepperoni21/ollama-rs |
| **reqwest** | 0.12 | MIT / Apache-2.0 | https://github.com/seanmonstar/reqwest |
| **futures** | 0.3 | MIT / Apache-2.0 | https://github.com/rust-lang/futures-rs |

## OS Integration & Input

| Component | Version | License | Upstream |
|:---|:---|:---|:---|
| **uiautomation** | 0.25 | MIT | https://github.com/leexgone/uiautomation-rs |
| **enigo** | 0.2 | MIT | https://github.com/enigo-rs/enigo |
| **global-hotkey** | 0.6 | MIT / Apache-2.0 | https://github.com/tauri-apps/global-hotkey |
| **rdev** | 0.5 | MIT | https://github.com/Narsil/rdev |
| **windows** | 0.58 | MIT / Apache-2.0 | https://github.com/microsoft/windows-rs |

## Domain 8: Multimodal Input

| Component | Version | License | Upstream |
|:---|:---|:---|:---|
| **whisper.cpp** | latest | MIT | https://github.com/ggerganov/whisper.cpp |
| **farscry** | latest | Apache-2.0 | https://github.com/AbanteAI/farscry |
| **cpal** | 0.15 | Apache-2.0 | https://github.com/RustAudio/cpal |
| **hound** | 3.5 | Apache-2.0 | https://github.com/ruuda/hound |
| **sherpa-onnx** | latest | Apache-2.0 | https://github.com/k2-fsa/sherpa-onnx |
| **rustpotter** | 0.11 | Apache-2.0 | https://github.com/GiviMAD/rustpotter |

## Memory & Storage

| Component | Version | License | Upstream |
|:---|:---|:---|:---|
| **rusqlite** | 0.31 | MIT | https://github.com/rusqlite/rusqlite |
| **dirs** | 5.x | MIT / Apache-2.0 | https://github.com/dirs-dev/dirs-rs |
| **tempfile** | 3.x | MIT / Apache-2.0 | https://github.com/Stebalien/tempfile |
| **petgraph** | 0.6.5 | MIT / Apache-2.0 | https://github.com/petgraph/petgraph |

## CRDT & Collaboration

| Component | Version | License | Upstream |
|:---|:---|:---|:---|
| **yrs** (Yjs Rust port) | 0.21 | MIT | https://github.com/y-crdt/y-crdt |

## WASM Sandbox

| Component | Version | License | Upstream |
|:---|:---|:---|:---|
| **wasmtime** | 25.x | Apache-2.0 | https://github.com/bytecodealliance/wasmtime |
| **ed25519-dalek** | 2.x | MIT / Apache-2.0 | https://github.com/dalek-cryptography/curve25519-dalek |
| **sha2** | 0.10 | MIT / Apache-2.0 | https://github.com/RustCrypto/hashes |

## UI & Overlay

| Component | Version | License | Upstream |
|:---|:---|:---|:---|
| **Tauri** | 2.x | MIT / Apache-2.0 | https://github.com/tauri-apps/tauri |
| **wgpu** | 0.20 | MIT / Apache-2.0 | https://github.com/gfx-rs/wgpu |

## Data Formats & Parsing

| Component | Version | License | Upstream |
|:---|:---|:---|:---|
| **zip** | 2.x | MIT | https://github.com/zip-rs/zip2 |
| **toml** | 0.8 | MIT / Apache-2.0 | https://github.com/toml-rs/toml |
| **hex** | 0.4 | MIT / Apache-2.0 | https://github.com/KokaKiwi/rust-hex |

## PDF Domain (permissive-only stack — PyMuPDF/AGPL BANNED)

| Component | Version | License | Upstream | Attribution Notes |
|:---|:---|:---|:---|:---|
| **pdfplumber** | 0.11+ | MIT | https://github.com/jsvine/pdfplumber | Text + word/char coordinates — the read-back oracle. Built on pdfminer.six (MIT). |
| **pypdfium2** | 4.x+ | BSD-3-Clause | https://github.com/pypdfium2-team/pypdfium2 | Python binding to Google PDFium (BSD-3-Clause). Render/rasterize pages, extract images, inspect vector objects. Replaces PyMuPDF's `get_pixmap()`. |
| **pikepdf** | 9.x+ | MPL-2.0 | https://github.com/pikepdf/pikepdf | MPL-2.0 (file-level copyleft) — used as an **unmodified dependency**; not forked into our tree. Content-stream edit, TRUE redaction (bytes removed, not black boxes), AcroForm fill/flatten, encryption, repair. Wraps qpdf (Apache-2.0). |
| **pypdf** | 4.x+ | BSD-3-Clause | https://github.com/py-pdf/pypdf | Merge/split/rotate/metadata — lightweight PDF manipulation. |
| **pyHanko** | 0.20+ | MIT | https://github.com/MatthiasValvekens/pyHanko | PAdES digital signatures — sign + verify. Used for regulated legal/finance signature workflows. |
| **pdfminer.six** | latest | MIT | https://github.com/pdfminer/pdfminer.six | Low-level PDF text extraction engine (transitive dep of pdfplumber). |
| **reportlab** | 4.x+ | BSD-3-Clause | https://github.com/MrBitBucket/reportlab-mirror | PDF generation for test fixtures (not shipped in production paths). |

## Cryptography & Security

| Component | Version | License | Upstream |
|:---|:---|:---|:---|
| **jsonwebtoken** | 9.x | MIT | https://github.com/Keats/jsonwebtoken |
| **rand** | 0.8 | MIT / Apache-2.0 | https://github.com/rust-random/rand |
| **hmac** | 0.12 | MIT / Apache-2.0 | https://github.com/RustCrypto/MACs |
| **regex** | 1.x | MIT / Apache-2.0 | https://github.com/rust-lang/regex |
| **chrono** | 0.4 | MIT / Apache-2.0 | https://github.com/chronotope/chrono |

## Testing

| Component | Version | License | Upstream |
|:---|:---|:---|:---|
| **proptest** | 1.4 | MIT / Apache-2.0 | https://github.com/proptest-rs/proptest |
| **criterion** | 0.5 | MIT / Apache-2.0 | https://github.com/bheisler/criterion.rs |
| **tempfile** | 3.x | MIT / Apache-2.0 | https://github.com/Stebalien/tempfile |

---

## Domain 9: Enterprise Governance & Compliance

### Identity & Authentication

| Component | Version | License | Upstream | Attribution Notes |
|:---|:---|:---|:---|:---|
| **Logto** | latest | MIT | https://github.com/logto-io/logto | Enterprise SSO / OIDC / SAML identity provider. Kairo integrates with Logto as a JWT consumer only — Logto is deployed separately by enterprise customers. MIT license; no copyleft. |
| **jsonwebtoken** | 9.x | MIT | https://github.com/Keats/jsonwebtoken | JWT RS256/HS256 validation used by SsoGate. Already listed in Cryptography section. |

### Agent Identity (SPIFFE)

| Component | Version | License | Upstream | Attribution Notes |
|:---|:---|:---|:---|:---|
| **SPIFFE** (standard) | CNCF spec | Apache-2.0 | https://github.com/spiffe/spiffe | Kairo implements the SPIFFE URI scheme (`spiffe://<trust_domain>/agent/<name>`) and local-first Ed25519 SVIDs. The SPIFFE workload API is an optional integration for enterprises with SPIRE deployed. |
| **ed25519-dalek** | 2.x | MIT / Apache-2.0 | https://github.com/dalek-cryptography/curve25519-dalek | Ed25519 signature generation and verification for agent SPIFFE identity. Provides `SigningKey`, `VerifyingKey`. Already listed in WASM Sandbox section. |

### Audit Logging & SIEM

| Component | Version | License | Upstream | Attribution Notes |
|:---|:---|:---|:---|:---|
| **rusqlite** | 0.31 | MIT | https://github.com/rusqlite/rusqlite | Append-only enterprise audit SQLite database (`kairo_audit.db`). Already listed in Memory & Storage section. |
| **hmac** | 0.12 | MIT / Apache-2.0 | https://github.com/RustCrypto/MACs | HMAC-SHA256 for hourly audit chain sealing (`seal_hourly()`). RustCrypto MACs crate. |
| **sha2** | 0.10 | MIT / Apache-2.0 | https://github.com/RustCrypto/hashes | SHA-256 for per-record cryptographic chaining and document hashing. Already listed in WASM Sandbox section. |

### Compliance Scanning

| Component | Version | License | Upstream | Attribution Notes |
|:---|:---|:---|:---|:---|
| **regex** | 1.x | MIT / Apache-2.0 | https://github.com/rust-lang/regex | Deterministic PII/PAN/CVV pattern matching in EnterpriseComplianceScanner. No lookaheads — all patterns are bounded linear time. |

### Compliance Rule Sets (Data)

| Resource | Format | Source | Notes |
|:---|:---|:---|:---|
| **HIPAA Safe Harbor identifiers** | TOML | HHS 45 CFR §164.514(b) | 18 Safe Harbor de-identification categories. Rule text is original; PHI patterns are public regulatory definitions. |
| **GDPR Special Categories** | TOML | GDPR Article 9(1) | Special category data patterns (biometric, health, racial/ethnic, religious). Pattern text is original. |
| **PCI-DSS v4.0 PANs** | TOML | PCI Security Standards Council | Primary Account Number regex patterns. Industry-standard definitions; original implementation. |

---

## Conceptual Inspirations

The following projects influenced Kairo Phantom's architecture. Their source code is **not** included in this repository; all integration is via published crates.io dependencies or documented API bridges.

| Inspiration | Role in Kairo | Upstream |
|:---|:---|:---|
| **MemGPT / MemMachine** | Memory tiering and ground-truth storage architecture | https://github.com/cpacker/MemGPT |
| **Alaya** | Cognitive decay curves and memory lifecycle design | Research paper: Alaya Memory Model |
| **PRIME** (Preference Reasoning) | Meta-operation semantics (merge/split/generalize) | Research-inspired design |
| **Waza** | Skill-based agent architecture | Internal design, open-spec |
| **gl-transitions** | WGSL transition shader patterns | https://gl-transitions.com |
| **GraphRAG** | Cognitive entity graph memory design | https://github.com/microsoft/graphrag |
| **Hermes Agent** | Autonomous planning trace reflecting and skill creation pattern | https://github.com/airbytehq/hermes |
| **Feynman** | Output verification via self-critique and explanation | Conceptual pattern |
| **DSPy** | Offline prompt optimization and evaluation | https://github.com/stanfordnlp/dspy |

## Domain 8: Voice & Multimodal Input

### Automatic Speech Recognition

| Component | Version | License | Upstream | Attribution Notes |
|:---|:---|:---|:---|:---|
| **Moonshine Voice** (moonshine-onnx) | 1.x | MIT | https://github.com/usefulsensors/moonshine | Primary ASR engine. 26MB model, 107ms inference. No user-facing "Powered by Moonshine" required under MIT; internal attribution sufficient. |
| **whisper.cpp** | latest | MIT | https://github.com/ggerganov/whisper.cpp | Fallback ASR. Invoked via CLI subprocess. MIT requires copyright notice in binary distributions. Note: only the C++ CLI binary is used; original OpenAI Whisper model weights were released under MIT by OpenAI. |

### Text-to-Speech

| Component | Version | License | Upstream | Attribution Notes |
|:---|:---|:---|:---|:---|
| **sherpa-onnx** (offline-tts) | 1.x | Apache-2.0 | https://github.com/k2-fsa/sherpa-onnx | Primary TTS. VITS model `en_US-amy-medium` (piper-tts, MIT). Invoked via CLI subprocess; no linking required. |
| **pyttsx3** | 2.x | MPL-2.0 | https://github.com/nateshmbhat/pyttsx3 | Cross-platform TTS fallback. MPL-2.0 is compatible with MIT distribution (file-level copyleft only). |
| **Windows SAPI** | OS built-in | Proprietary (OS component) | Microsoft | Accessed via PowerShell; no license required for use on licensed Windows installations. |

### Wake Word Detection

| Component | Version | License | Upstream | Attribution Notes |
|:---|:---|:---|:---|:---|
| **horchd** | latest | Apache-2.0 | https://github.com/GiviMAD/horchd | Primary wake word CLI (rustpotter-based). Subprocess invocation; no Rust linking to the main binary. |
| **rustpotter** | 3.x | Apache-2.0 | https://github.com/GiviMAD/rustpotter | Underlying wake word engine used by horchd. Apache-2.0 compatible with MIT distribution. |
| **openwakeword** | 0.6+ | Apache-2.0 | https://github.com/dscripka/openwakeword | Python wake word service (port 7440). Uses pre-trained models under Apache-2.0. |

### Audio I/O

| Component | Version | License | Upstream | Attribution Notes |
|:---|:---|:---|:---|:---|
| **sounddevice** | 0.4+ | MIT | https://github.com/spatialaudio/python-sounddevice | Microphone capture in Python wake word service. |
| **numpy** | 1.x / 2.x | BSD-3-Clause | https://numpy.org | Audio buffer manipulation. BSD-3 compatible with MIT. |
| **aiohttp** | 3.x | Apache-2.0 | https://github.com/aio-libs/aiohttp | HTTP server for Moonshine sidecar service. |

---

## Domain 11: Cross-Platform Hardening

### Cross-Platform Accessibility Layer

| Component | Version | License | Upstream | Attribution Notes |
|:---|:---|:---|:---|:---|
| **xa11y** | 0.7.1 | MIT | https://github.com/LeoTindall/xa11y | Unified Rust accessibility API design. Kairo implements the same unified `AccessibilityReader` trait pattern and CSS-like locator semantics inspired by xa11y, using each platform's native API (Windows UIAutomation, macOS AXUIElement, Linux AT-SPI2) directly rather than linking the xa11y crate. No source code copied; architecture and API design inspired by xa11y. MIT licence; attribution sufficient. |
| **macos-accessibility-client** | 0.0.2 | MIT | https://github.com/tmandry/macos-accessibility-client | macOS AXUIElement Rust bindings used for `MacOsAccessibilityReader::get_focused_text()`. Reads focused element value and title attributes via `AXUIElement`. |
| **core-graphics** | 0.23 | MIT | https://github.com/servo/core-foundation-rs | macOS CGEvent API for background keyboard injection (`CGEventPostToPid`). Enables Cmd+V injection without focus stealing. |
| **core-foundation** | 0.10 | MIT | https://github.com/servo/core-foundation-rs | macOS Core Foundation bindings used alongside core-graphics for macOS platform integration. |

### Linux Accessibility Tools (Runtime Dependencies)

The following external tools are *not* bundled with Kairo Phantom but are required on Linux for context capture and text injection. They are documented here for supply chain transparency.

| Tool | Version | License | Purpose |
|:---|:---|:---|:---|
| **xdotool** | 3.x | MIT | X11 window title/PID query and keyboard simulation. `sudo apt install xdotool` |
| **xclip** | 0.13+ | GPL-2.0 | X11 clipboard read/write for text injection fallback. `sudo apt install xclip` |
| **xsel** | 1.2+ | GPL-2.0 | Alternative X11 clipboard tool. `sudo apt install xsel` |
| **ydotool** | 1.x | GPL-3.0 | Wayland keyboard/mouse simulation. `sudo apt install ydotool` |
| **wl-clipboard** | 2.x | GPL-3.0 | Wayland clipboard (`wl-copy`/`wl-paste`). `sudo apt install wl-clipboard` |
| **at-spi2-core** | 2.x | LGPL-2.1 | Assistive Technology Service Provider Interface for GNOME accessibility bus. `sudo apt install at-spi2-core` |

> **Note:** GPL-licensed runtime tools are separate processes invoked via subprocess. Kairo Phantom (MIT) does not link to or distribute these tools. The GPL copyleft therefore does not extend to Kairo's source code.

### macOS Accessibility

| Requirement | Details |
|:---|:---|
| **NSAccessibilityUsageDescription** | Required in `Info.plist` for `.app` bundles. Included in `installer/macos/Info.plist`. |
| **Accessibility permission** | Users must grant in System Settings → Privacy & Security → Accessibility. The installer (`install.sh`) detects and guides users through this step. |

---

## cua-driver

- **Source**: https://github.com/trycua/cua/tree/main/libs/cua-driver
- **License**: MIT
- **Version**: Latest (installed via install.ps1)
- **Usage**: Fallback CUA backend for screenshot capture and mouse/keyboard input when enigo fails. Used only in Tier 3 (CUA) execution path — not compiled into default builds.
- **Note**: We use ONLY the cua-driver component, NOT the trycua VM sandbox infrastructure.

---

*If you believe a dependency or attribution has been omitted, please [open an issue](https://github.com/KairoPhantom/Kairo-Phantom/issues).*
