"""Render an analysis markdown report to a print-ready PDF.

The markdown may contain inline <svg> charts (from matplotlib) and GFM tables.
We convert md → HTML with python-markdown (tables, fenced-code), then hand
the HTML to WeasyPrint with a tight print-friendly stylesheet.

Heavy imports (weasyprint) are deferred so the module loads cheaply — a
worker process that never renders PDFs shouldn't pay the Pango init cost.
"""

from __future__ import annotations

import html as _html
import logging
from typing import Any

log = logging.getLogger(__name__)

# Print stylesheet — minimalist, mirrors the on-screen .prose-report look but
# tuned for A4 paper. Tables can overflow horizontally inside .table-scroll;
# we don't have scroll on paper, so we shrink table font and let it break.
_PRINT_CSS = """
@page {
  size: A4;
  margin: 18mm 16mm 18mm 16mm;
  @bottom-center {
    content: "Chapter One · page " counter(page) " of " counter(pages);
    font-size: 9pt;
    color: #888;
  }
}

html, body { margin: 0; padding: 0; }
body {
  font-family: "Liberation Sans", "DejaVu Sans", sans-serif;
  font-size: 10.5pt;
  line-height: 1.5;
  color: #111;
}

header.cover {
  margin-bottom: 18pt;
  padding-bottom: 12pt;
  border-bottom: 1px solid #ddd;
}
header.cover .badge {
  display: inline-block;
  padding: 2pt 8pt;
  border-radius: 999pt;
  font-size: 9pt;
  font-weight: 600;
  color: #fff;
  background: #111;
  margin-right: 6pt;
}
header.cover .verdict.strong { background: #15803d; }
header.cover .verdict.conditional { background: #1d4ed8; }
header.cover .verdict.watch { background: #a16207; color: #fff; }
header.cover .verdict.pass { background: #b91c1c; }
header.cover h1 { font-size: 18pt; font-weight: 800; margin: 6pt 0; letter-spacing: -0.01em; }
header.cover .meta { font-size: 9pt; color: #666; }

h1 { font-size: 16pt; margin-top: 18pt; margin-bottom: 8pt; font-weight: 800; letter-spacing: -0.01em; page-break-after: avoid; }
h2 { font-size: 13pt; margin-top: 14pt; margin-bottom: 6pt; font-weight: 700; page-break-after: avoid; }
h3 { font-size: 11pt; margin-top: 10pt; margin-bottom: 4pt; font-weight: 600; page-break-after: avoid; }
p  { margin: 4pt 0; }
ul, ol { margin: 4pt 0 4pt 18pt; }
li { margin: 2pt 0; }

a  { color: #1d4ed8; text-decoration: none; word-wrap: break-word; }
a[href]::after { content: ""; }  /* no URL printing suffix; it clutters */

blockquote {
  margin: 6pt 0;
  padding: 2pt 10pt;
  border-left: 3pt solid #ccc;
  color: #444;
  font-style: italic;
}

code {
  font-family: "DejaVu Sans Mono", monospace;
  font-size: 9.5pt;
  background: #f4f4f5;
  padding: 1pt 3pt;
  border-radius: 3pt;
}
pre {
  background: #f4f4f5;
  padding: 8pt;
  border-radius: 4pt;
  font-size: 9pt;
  overflow: hidden;
  white-space: pre-wrap;
  word-wrap: break-word;
}
pre code { background: transparent; padding: 0; font-size: 9pt; }

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 9pt;
  margin: 6pt 0;
  page-break-inside: avoid;
}
th, td {
  border: 1px solid #d4d4d8;
  padding: 3pt 5pt;
  text-align: left;
  vertical-align: top;
  word-break: break-word;
}
th { background: #f4f4f5; font-weight: 600; }

img, svg { max-width: 100%; height: auto; }
svg { page-break-inside: avoid; }

hr { border: 0; border-top: 1px solid #ddd; margin: 12pt 0; }
"""


_VERDICT_CLASS = {
    "STRONG INVEST": "strong",
    "CONDITIONAL": "conditional",
    "WATCH": "watch",
    "PASS": "pass",
    "HARD PASS": "pass",
}


def render_pdf(
    markdown_text: str,
    *,
    title: str | None = None,
    verdict: str | None = None,
    score: int | None = None,
    author: str | None = None,
    generated_at: str | None = None,
) -> bytes:
    """Convert a markdown report to a PDF and return the raw bytes."""
    # Deferred imports — weasyprint pulls in pango; only pay for it when invoked.
    import markdown as md_lib  # type: ignore
    from weasyprint import CSS, HTML  # type: ignore

    body_html = md_lib.markdown(
        markdown_text,
        extensions=[
            "tables",
            "fenced_code",
            "codehilite",
            "sane_lists",
            "toc",
        ],
        extension_configs={
            "codehilite": {"guess_lang": False, "noclasses": True},
        },
        output_format="html5",
    )

    verdict_class = _VERDICT_CLASS.get((verdict or "").upper(), "")
    cover_bits: list[str] = []
    if verdict:
        cover_bits.append(
            f'<span class="badge verdict {verdict_class}">{_html.escape(verdict)}</span>'
        )
    if score is not None:
        cover_bits.append(
            f'<span class="badge" style="background:#f4f4f5;color:#111;">{score}/100</span>'
        )

    meta_bits: list[str] = []
    if author:
        meta_bits.append(f"by {_html.escape(author)}")
    if generated_at:
        meta_bits.append(_html.escape(generated_at))

    header_html = f"""
    <header class="cover">
      <div>{''.join(cover_bits) if cover_bits else ''}</div>
      <h1>{_html.escape(title or 'Analysis report')}</h1>
      <div class="meta">{' · '.join(meta_bits) if meta_bits else 'Chapter One'}</div>
    </header>
    """

    full_html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{_html.escape(title or 'Analysis report')}</title></head>
<body>
{header_html}
<article>
{body_html}
</article>
</body></html>"""

    pdf_bytes = HTML(string=full_html).write_pdf(stylesheets=[CSS(string=_PRINT_CSS)])
    if pdf_bytes is None:
        raise RuntimeError("weasyprint returned empty PDF")
    return pdf_bytes


def safe_filename(title: str | None, fallback: str) -> str:
    if not title:
        return fallback
    cleaned = "".join(c if c.isalnum() or c in (" ", "-", "_") else "" for c in title)
    cleaned = "-".join(cleaned.split()).strip("-") or fallback
    return cleaned[:80]
