# PDF DOMAIN STACK — full PyMuPDF feature parity, permissive-only

> You were right: text extraction is only part of what PyMuPDF (AGPL) does. This maps EVERY
> PyMuPDF capability to a permissive replacement, so the PDF domain is complete AND legally
> clean. All libs below are MIT / BSD / Apache / MPL (MPL used as unmodified dep).

## Full capability map (PyMuPDF feature → permissive replacement)
| PyMuPDF capability | Permissive replacement | License | Notes |
|---|---|---|---|
| Text + coordinates | pdfplumber | MIT ✓ | deterministic word/char boxes → the read-back **oracle** |
| Layout, tables, reading order, headings, formulas | **Docling** (IBM) | MIT ✓ | ML doc-understanding, LLM-ready structured JSON/Markdown |
| **Extract embedded images** | **pypdfium2** (`extract-images`) or pikepdf | BSD/Apache · MPL | pypdfium2 = Google PDFium engine |
| **Render/rasterize page → image** | **pypdfium2** (`render`) | BSD-3-Clause ✓ | replaces `page.get_pixmap()`; supports scale, annotations, forms, grayscale. **Do NOT use pdf2image/poppler (GPL).** |
| **Vector/drawing objects** (paths, shapes) | pypdfium2 `pageobjects` (filter=path/shading) | BSD | inspect/extract vector content |
| **Annotations** (read/draw) | pypdfium2 (draw) + pikepdf (edit) | BSD · MPL | highlight, comment, stamp |
| **AcroForm form fields** (read/fill) | pikepdf + pypdfium2 (`--draw-forms`) | MPL · BSD | fill + flatten forms |
| **Redaction** (true content removal) | pikepdf (content-stream edit) + pypdfium2 (verify by re-render) | MPL · BSD | remove bytes, not just black boxes; verify with render-diff oracle |
| **Encryption / decryption / permissions** | pikepdf (qpdf) | MPL | password, AES, permission flags |
| Merge / split / rotate / metadata | pypdf | BSD-3-Clause | lightweight manipulation |
| Linearize / repair / optimize | pikepdf (qpdf) | MPL | fix broken PDFs |
| **OCR (scanned pages)** | olmocr (primary) + Tesseract (fallback) | Apache-2.0 | text on image-only pages |
| **Digital signatures / PAdES** | **pyHanko** | MIT | sign + verify; regulated legal/finance need this |
| Attachments / embedded files | pikepdf | MPL | extract/add attachments |

## Recommended architecture (`kairo.domains.pdf`)
```
 PDF in
   ├─ classify: born-digital vs scanned (pypdfium2 render + heuristics)
   ├─ born-digital → Docling (structure) + pdfplumber (coords oracle)
   ├─ scanned      → pypdfium2 render → olmocr OCR → Docling structure
   ├─ images/vectors → pypdfium2 extract-images / pageobjects
   ├─ forms/annots  → pikepdf (edit) / pypdfium2 (render-verify)
   ├─ redaction     → pikepdf content edit → pypdfium2 re-render diff (proves bytes gone)
   ├─ sign/verify   → pyHanko (PAdES)
   └─ manipulate    → pypdf / pikepdf (merge/split/encrypt)
```

## Oracles (deterministic, kill-proof)
- `pdf_text_roundtrip`: pdfplumber coords stable within tolerance; kill-proof = shift a word box → fail.
- `pdf_render_diff`: pypdfium2 render before/after; redaction removes target region in pixels AND in extracted text; kill-proof = leave text under a black box → fail.
- `pdf_form_readback`: fill field → re-read value via pikepdf; kill-proof = write wrong value → fail.
- `pdf_signature_verify`: pyHanko verifies a signed doc; kill-proof = tamper one byte → verification fails.

## Licensing note (belt-and-suspenders)
- pypdfium2 wraps **PDFium** (BSD-3-Clause, Google) — permissive, safe to ship.
- pikepdf is **MPL-2.0** (file-level copyleft): ship as an **unmodified dependency**; don't fork its files into your tree. `license_gate` allows MPL for shipped deps.
- **Reject** pymupdf4llm / pdfmux (AGPL passthrough) and marker (GPL) — see TECH_MANIFEST.
