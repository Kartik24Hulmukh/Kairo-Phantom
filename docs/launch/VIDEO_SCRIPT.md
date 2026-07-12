# Kairo Phantom — 90-Second Demo Video Script

**Target:** Product Hunt launch video  
**Duration:** 90 seconds  
**Format:** Screen recording + voiceover  
**Hook:** "What if your AI knew your writing style?"

---

## Pre-Production Checklist

- [ ] VS Code open with a sample business email draft
- [ ] Kairo Phantom running (check with `// health`)
- [ ] OBS or QuickTime recording at 1920×1080
- [ ] Voiceover mic ready (or use TTS: ElevenLabs "Daniel" voice)
- [ ] Royalty-free background music (quiet, focus-mode)

---

## Script

### SCENE 1: The Problem (0:00–0:12)

**[SCREEN: Desktop with a half-written email in Outlook]**

**VOICEOVER:**  
*"Every day you switch between your document and ChatGPT. You copy, you paste, you re-explain your context — again. Your AI doesn't remember you. Kairo does."*

**[SCREEN: Briefly show the Copy → Paste → Context → Paste loop with a speed-cut montage]**

---

### SCENE 2: The Hook (0:12–0:22)

**[SCREEN: Kairo Phantom tray icon in the taskbar]**

**VOICEOVER:**  
*"Kairo Phantom lives in your tray. It reads your document, learns your style, and types the AI response directly into your app. No switching. No pasting. Just Alt+Ctrl+M."*

**[TEXT OVERLAY: "Alt+Ctrl+M = AI writes directly into any app"]**

---

### SCENE 3: Live Demo — First Use (0:22–0:45)

**[SCREEN: VS Code open with a marketing email draft. User types:]**
```
// rewrite this email opening to sound warmer and more personal
```

**[Pause 1 second]**

**[Alt+Ctrl+M pressed. Toast appears: "Kairo: Generating..."]**

**VOICEOVER:**  
*"I typed my instruction in the document itself — using Kairo's two-slash protocol. Pressed Alt+Ctrl+M. Watch."*

**[AI response types directly into the document — humanized keystrokes, character by character]**

**VOICEOVER:**  
*"Kairo read my draft, understood the context, and rewrote the opening. Right there. In VS Code. No copy-paste."*

**[SCREEN: Show the rewritten paragraph highlighted in the document]**

---

### SCENE 4: The Memory Difference (0:45–1:05)

**[SCREEN: User works in Word on a second document]**

**VOICEOVER:**  
*"Here's where Kairo is different. It remembers."*

**[User types in a new Word document:]**
```
// write a LinkedIn post about our Q2 results
```

**[Alt+Ctrl+M → response appears]**

**[SCREEN: Side-by-side showing the LinkedIn post matches the user's established tone — same vocabulary, same sentence length]**

**VOICEOVER:**  
*"On session 5, Kairo already knows I prefer short sentences, data-first structure, and no corporate jargon. That's MemMachine — personalized AI memory that learns from every session."*

---

### SCENE 5: Privacy & Security (1:05–1:17)

**[SCREEN: Activity monitor showing Ollama running locally. No network requests.]**

**VOICEOVER:**  
*"Everything runs locally. Ollama. No API calls. Your documents never leave your machine. Enterprise teams get Ed25519-signed audit logs and tamper-evident receipts (SPIFFE identity and SOC 2 readiness are planned, not yet implemented)."*

**[TEXT OVERLAY: "100% offline · Zero cloud · Enterprise-ready (planned)"]**

---

### SCENE 6: Call to Action (1:17–1:30)

**[SCREEN: GitHub repo page for Kairo Phantom]**

**VOICEOVER:**  
*"Kairo Phantom is open source, MIT-licensed, and available today on Windows — with macOS and Linux in beta. One command to install. One hotkey to activate. Your AI writing partner that actually knows you."*

**[TEXT OVERLAY:]**
```
cargo install kairo-phantom
Press Alt+Ctrl+M. Write // and go.
github.com/KairoPhantom/Kairo-Phantom
```

**VOICEOVER:**  
*"Star us on GitHub. Try it today. Your first session is free forever."*

**[OUTRO: Kairo Phantom logo + tagline: "The AI that haunts every app and learns how you write."]**

---

## Production Notes

### Commands to Show On-Screen

```
# Installation (show this terminal command)
cargo install kairo-phantom

# First run
kairo-phantom

# Health check  
// health

# Example prompts to use in recording
// rewrite this to sound more confident
// kami slides: 5-slide pitch for investors
// summarize this document in 3 bullets
```

### Timestamps for Editing

| Time | Scene | Cut |
|------|-------|-----|
| 0:00 | Problem montage | Fast cuts |
| 0:12 | Tray icon reveal | Zoom in |
| 0:22 | VS Code demo starts | Screen recording |
| 0:45 | Word memory demo | Smooth transition |
| 1:05 | Privacy screen | Activity monitor |
| 1:17 | GitHub CTA | Zoom to repo |
| 1:30 | Logo outro | Fade |

### Music

Suggested royalty-free tracks:
- "Midnight City Drives" (Artlist)  
- "Focus Flow" (Epidemic Sound)
- Level: -18db (ambient, not distracting)
