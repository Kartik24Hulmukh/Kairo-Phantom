import os
import subprocess
import tempfile
import shutil
import logging
from pathlib import Path

logger = logging.getLogger("kairo.quarkdown")


def compile_quarkdown(content: str, output_format: str, output_path: str) -> bool:
    """
    Compiles Quarkdown/Markdown content to either 'pdf' or 'revealjs' presentation.
    Tries to use a bundled quarkdown.jar JVM binary if available,
    otherwise gracefully falls back to native Python-based high-fidelity HTML/CSS layout templates.
    """
    try:
        # Prepare input and output paths
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Generate Quarkdown-compatible Markup
        qd_markup = generate_quarkdown_markup(content, output_format)

        # 2. Try JVM-based Quarkdown Compiler if bundled/available
        jar_path = Path(__file__).parent.parent.parent / "bin" / "quarkdown.jar"
        if jar_path.exists() and shutil.which("java"):
            logger.info("Found bundled quarkdown.jar and JVM, running compilation...")
            return run_jvm_quarkdown(qd_markup, jar_path, output_format, output_path)

        # 3. Fallback: Programmatic, high-fidelity layout compilation (100% reliable)
        logger.info(
            "Quarkdown JVM compiler unavailable. Running high-fidelity local programmatic compiler..."
        )
        return run_fallback_compiler(qd_markup, content, output_format, output_path)

    except Exception as e:
        logger.error(f"Failed to compile Quarkdown document: {e}", exc_info=True)
        return False


def generate_quarkdown_markup(content: str, output_format: str) -> str:
    """
    Translates raw content or Markdown into rich Quarkdown-flavored markup.
    """
    if output_format == "revealjs":
        # Formulate presentation slides
        sections = []
        current_section = []
        for line in content.splitlines():
            if line.startswith("# ") or line.startswith("## "):
                if current_section:
                    sections.append("\n".join(current_section))
                current_section = [line]
            else:
                current_section.append(line)
        if current_section:
            sections.append("\n".join(current_section))

        qd_slides = []
        for section in sections:
            qd_slides.append(f".slide\n{section}\n")
        return "\n".join(qd_slides)
    else:
        # Standard document
        return f".document\n{content}\n"


def run_jvm_quarkdown(markup: str, jar_path: Path, output_format: str, output_path: str) -> bool:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".qd", delete=False, encoding="utf-8"
    ) as temp_in:
        temp_in.write(markup)
        temp_in_name = temp_in.name

    try:
        fmt_arg = "revealjs" if output_format == "revealjs" else "pdf"
        cmd = [
            "java",
            "-jar",
            str(jar_path),
            "--format",
            fmt_arg,
            "-i",
            temp_in_name,
            "-o",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            logger.info("JVM Quarkdown compile successful.")
            return True
        else:
            logger.warning(f"JVM compiler failed: {result.stderr}")
            return False
    except Exception as e:
        logger.warning(f"JVM invocation timed out or failed: {e}")
        return False
    finally:
        try:
            os.remove(temp_in_name)
        except:
            pass


def run_fallback_compiler(
    markup: str, original_content: str, output_format: str, output_path: str
) -> bool:
    """
    Renders high-fidelity reveal.js slides, EPUB 3.2 e-books, book-style HTML, or standard printable documents.
    """
    if output_format == "epub":
        return _generate_epub_fallback(original_content, output_path)
    elif output_format == "revealjs":
        return _generate_revealjs_fallback(original_content, output_path)
    elif output_format == "book":
        return _generate_book_fallback(original_content, output_path)
    else:
        return _generate_html_fallback(original_content, output_path)


def _generate_epub_fallback(content: str, output_path: str) -> bool:
    """Generate a valid EPUB 3.2 container (ZIP with XHTML + OPF metadata)."""
    import zipfile
    from xml.sax.saxutils import escape

    # Extract title from first H1
    title = "Kairo Document"
    for line in content.splitlines():
        if line.strip().startswith("# "):
            title = line.strip().lstrip("# ").strip()
            break

    # Build XHTML body from markdown
    body_lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            body_lines.append(f"<h1>{escape(stripped[2:].strip())}</h1>")
        elif stripped.startswith("## "):
            body_lines.append(f"<h2>{escape(stripped[3:].strip())}</h2>")
        elif stripped.startswith("### "):
            body_lines.append(f"<h3>{escape(stripped[4:].strip())}</h3>")
        elif stripped.startswith("- ") or stripped.startswith("* "):
            body_lines.append(
                f'<p style="margin-left:1.5em">&#x2022; {escape(stripped[2:].strip())}</p>'
            )
        elif stripped:
            body_lines.append(f"<p>{escape(stripped)}</p>")

    xhtml_body = "\n".join(body_lines)

    mimetype = "application/epub+zip"
    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

    ts = _epub_utc_timestamp()

    content_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookID">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="BookID">urn:kairo:phantom:{ts}</dc:identifier>
    <dc:title>{escape(title)}</dc:title>
    <dc:language>en</dc:language>
    <dc:creator>Kairo Phantom</dc:creator>
    <meta property="dcterms:modified">{ts}</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="content" href="content.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="content"/>
  </spine>
</package>"""

    nav_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>Navigation</title></head>
<body>
<nav epub:type="toc">
  <h1>Table of Contents</h1>
  <ol><li><a href="content.xhtml">{escape(title)}</a></li></ol>
</nav>
</body>
</html>"""

    content_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>{escape(title)}</title>
  <style>
    body {{ font-family: Georgia, serif; margin: 2em; line-height: 1.8; color: #1e293b; }}
    h1 {{ font-size: 2em; margin-bottom: 0.5em; color: #0f172a; }}
    h2 {{ font-size: 1.6em; margin-top: 1.5em; color: #1e293b; }}
    h3 {{ font-size: 1.3em; margin-top: 1em; color: #334155; }}
    p {{ margin-bottom: 0.8em; }}
  </style>
</head>
<body>
{xhtml_body}
</body>
</html>"""

    try:
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # mimetype MUST be first entry and stored uncompressed per EPUB spec
            zf.writestr("mimetype", mimetype, compress_type=zipfile.ZIP_STORED)
            zf.writestr("META-INF/container.xml", container_xml)
            zf.writestr("OEBPS/content.opf", content_opf)
            zf.writestr("OEBPS/nav.xhtml", nav_xhtml)
            zf.writestr("OEBPS/content.xhtml", content_xhtml)
        logger.info(f"✅ EPUB 3.2 generated successfully: {output_path}")
        return True
    except Exception as e:
        logger.error(f"EPUB generation failed: {e}", exc_info=True)
        return False


def _epub_utc_timestamp() -> str:
    """ISO 8601 UTC timestamp for EPUB metadata."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _generate_revealjs_fallback(original_content: str, output_path: str) -> bool:
    """High-fidelity Reveal.js slide deck."""
    slides = []
    current_slide = None

    lines = original_content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("# ") or line.startswith("## "):
            if current_slide:
                slides.append(current_slide)
            current_slide = {"title": line.lstrip("# ").lstrip("## ").strip(), "elements": []}
        elif current_slide is not None:
            if line.startswith("- ") or line.startswith("* "):
                current_slide["elements"].append({"type": "bullet", "text": line[2:].strip()})
            elif line.startswith("```"):
                code_lines = []
                lang = line[3:].strip()
                i += 1
                while i < len(lines) and not lines[i].startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                current_slide["elements"].append(
                    {"type": "code", "lang": lang, "text": "\n".join(code_lines)}
                )
            elif line.strip():
                current_slide["elements"].append({"type": "p", "text": line.strip()})
        else:
            if line.strip():
                current_slide = {
                    "title": "Introduction",
                    "elements": [{"type": "p", "text": line.strip()}],
                }
        i += 1

    if current_slide:
        slides.append(current_slide)

    slides_html = ""
    for slide in slides:
        title = slide["title"]
        elements_html = []

        in_list = False
        for elem in slide["elements"]:
            if elem["type"] == "bullet":
                if not in_list:
                    elements_html.append('<ul style="margin-top: 20px;">')
                    in_list = True
                elements_html.append(
                    f'<li class="fragment" style="margin-bottom: 10px;">{elem["text"]}</li>'
                )
            else:
                if in_list:
                    elements_html.append("</ul>")
                    in_list = False

                if elem["type"] == "code":
                    elements_html.append(
                        f'<pre><code class="language-{elem["lang"]}">{elem["text"]}</code></pre>'
                    )
                elif elem["type"] == "p":
                    elements_html.append(
                        f'<p style="margin-top: 15px; font-size: 1.1em; line-height: 1.6;">{elem["text"]}</p>'
                    )

        if in_list:
            elements_html.append("</ul>")

        body_content = "\n".join(elements_html)
        slides_html += f"""
        <section style="padding: 40px; text-align: left; box-sizing: border-box;">
            <h2 style="font-family: 'Plus Jakarta Sans', 'Segoe UI', sans-serif; font-size: 2.5em; font-weight: 800; background: linear-gradient(135deg, #38bdf8 0%, #818cf8 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; border-bottom: 2px solid rgba(255,255,255,0.1); padding-bottom: 15px; margin-bottom: 30px;">{title}</h2>
            <div class="slide-content" style="font-family: 'Inter', 'Segoe UI', sans-serif;">
                {body_content}
            </div>
        </section>
        """

    html_template = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Kairo Export - Presentation</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&family=Inter:wght@400;500&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.5.0/reveal.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.5.0/theme/dracula.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.5.0/plugin/highlight/monokai.min.css">
    <style>
        body {{
            background: linear-gradient(135deg, #0f172a 0%, #020617 100%) !important;
            color: #f8fafc;
        }}
        .reveal {{
            font-family: 'Inter', sans-serif !important;
        }}
        .reveal .slides {{
            background: rgba(30, 41, 59, 0.25);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 24px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.3);
        }}
        .reveal pre {{
            box-shadow: none !important;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
        }}
        .badge {{
            position: absolute;
            top: 20px;
            left: 20px;
            background: rgba(99, 102, 241, 0.15);
            color: #a5b4fc;
            padding: 6px 14px;
            border-radius: 99px;
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border: 1px solid rgba(99, 102, 241, 0.3);
            z-index: 10;
        }}
    </style>
</head>
<body>
    <div class="badge">Kairo Phantom presentation</div>
    <div class="reveal">
        <div class="slides">
            {slides_html}
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.5.0/reveal.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.5.0/plugin/highlight/highlight.min.js"></script>
    <script>
        Reveal.initialize({{
            hash: true,
            transition: 'slide',
            plugins: [ RevealHighlight ]
        }});
    </script>
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    return True


def _generate_book_fallback(original_content: str, output_path: str) -> bool:
    """Generate a continuous-flow HTML book with auto-generated table of contents."""
    from xml.sax.saxutils import escape

    # Extract headings for TOC
    toc_entries = []
    heading_counter = 0
    body_content = ""

    for line in original_content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            heading_counter += 1
            heading_id = f"h-{heading_counter}"
            text = stripped[2:].strip()
            toc_entries.append({"level": 1, "id": heading_id, "text": text})
            body_content += f'<h1 id="{heading_id}">{escape(text)}</h1>\n'
        elif stripped.startswith("## "):
            heading_counter += 1
            heading_id = f"h-{heading_counter}"
            text = stripped[3:].strip()
            toc_entries.append({"level": 2, "id": heading_id, "text": text})
            body_content += f'<h2 id="{heading_id}">{escape(text)}</h2>\n'
        elif stripped.startswith("### "):
            heading_counter += 1
            heading_id = f"h-{heading_counter}"
            text = stripped[4:].strip()
            toc_entries.append({"level": 3, "id": heading_id, "text": text})
            body_content += f'<h3 id="{heading_id}">{escape(text)}</h3>\n'
        elif stripped.startswith("- ") or stripped.startswith("* "):
            body_content += f"<li>{escape(stripped[2:].strip())}</li>\n"
        elif stripped:
            body_content += f"<p>{escape(stripped)}</p>\n"

    # Build TOC HTML
    toc_html = '<nav class="toc"><h2>Table of Contents</h2><ol>\n'
    for entry in toc_entries:
        indent = "  " * entry["level"]
        toc_html += f'{indent}<li style="margin-left: {(entry["level"]-1) * 20}px"><a href="#{entry["id"]}">{escape(entry["text"])}</a></li>\n'
    toc_html += "</ol></nav>\n"

    title = "Kairo Book Export"
    if toc_entries:
        title = toc_entries[0]["text"]

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{escape(title)}</title>
    <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@300;400;700&family=Inter:wght@400;500&display=swap" rel="stylesheet">
    <style>
        body {{
            font-family: 'Merriweather', Georgia, serif;
            color: #1e293b;
            background: #faf9f6;
            margin: 0;
            padding: 60px 10%;
            line-height: 1.9;
            max-width: 740px;
            margin-left: auto;
            margin-right: auto;
        }}
        .toc {{
            background: #f1f5f9;
            border-radius: 12px;
            padding: 24px 32px;
            margin-bottom: 48px;
            border: 1px solid #e2e8f0;
        }}
        .toc h2 {{
            font-family: 'Inter', sans-serif;
            font-size: 1.3rem;
            color: #475569;
            margin-bottom: 16px;
        }}
        .toc ol {{ list-style: none; padding: 0; }}
        .toc li {{ margin-bottom: 8px; }}
        .toc a {{
            color: #3b82f6;
            text-decoration: none;
            font-family: 'Inter', sans-serif;
            font-size: 0.95rem;
        }}
        .toc a:hover {{ text-decoration: underline; }}
        h1 {{
            font-size: 2.2rem;
            color: #0f172a;
            margin-top: 60px;
            margin-bottom: 24px;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 12px;
        }}
        h2 {{
            font-size: 1.7rem;
            color: #1e293b;
            margin-top: 48px;
            margin-bottom: 20px;
        }}
        h3 {{
            font-size: 1.3rem;
            color: #334155;
            margin-top: 32px;
            margin-bottom: 16px;
        }}
        p {{
            font-size: 1.05rem;
            color: #334155;
            margin-bottom: 16px;
        }}
        li {{
            font-size: 1.05rem;
            color: #334155;
            margin-bottom: 8px;
            margin-left: 24px;
        }}
    </style>
</head>
<body>
    {toc_html}
    {body_content}
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"✅ Book-style HTML exported: {output_path}")
    return True


def _generate_html_fallback(original_content: str, output_path: str) -> bool:
    """Generate a clean styled HTML document."""
    from xml.sax.saxutils import escape

    body_content = ""
    for line in original_content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            body_content += f"<h1>{escape(stripped[2:].strip())}</h1>\n"
        elif stripped.startswith("## "):
            body_content += f"<h2>{escape(stripped[3:].strip())}</h2>\n"
        elif stripped.startswith("- ") or stripped.startswith("* "):
            body_content += f"<li>{escape(stripped[2:].strip())}</li>\n"
        elif stripped:
            body_content += f"<p>{escape(stripped)}</p>\n"

    html_template = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Kairo Export - Document</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700&family=Inter:wght@400;500&display=swap" rel="stylesheet">
    <style>
        body {{
            font-family: 'Inter', sans-serif;
            color: #1e293b;
            background: #ffffff;
            margin: 0;
            padding: 80px 10%;
            line-height: 1.8;
            max-width: 800px;
            margin-left: auto;
            margin-right: auto;
        }}
        h1 {{
            font-family: 'Plus Jakarta Sans', sans-serif;
            font-weight: 700;
            font-size: 2.5rem;
            color: #0f172a;
            margin-bottom: 30px;
            border-bottom: 2px solid #f1f5f9;
            padding-bottom: 12px;
        }}
        h2 {{
            font-family: 'Plus Jakarta Sans', sans-serif;
            font-weight: 600;
            font-size: 1.8rem;
            color: #1e293b;
            margin-top: 40px;
            margin-bottom: 20px;
        }}
        p {{
            font-size: 1.1rem;
            color: #334155;
            margin-bottom: 20px;
        }}
        li {{
            font-size: 1.1rem;
            color: #334155;
            margin-bottom: 10px;
        }}
    </style>
</head>
<body>
    {body_content}
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    return True
