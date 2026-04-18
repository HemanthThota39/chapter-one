"""Mermaid block sanitizer.

Runs over generated markdown, finds ```mermaid fenced blocks, and applies
defensive fixes for the most common model-produced syntax errors we've observed:

  1. Em-dashes (—) and en-dashes (–) in quadrant labels break the lexer.
  2. Smart quotes ("" '') confuse the parser.
  3. xychart-beta `horizontal` combined with string y-axis labels fails on
     Mermaid 11.x. We rewrite `horizontal` out.
  4. Numeric values accidentally wrapped in quotes inside bar/line arrays.

Emits a `chart.sanitizer_applied` observability event for each fix applied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.observability import get_logger


MERMAID_BLOCK_RE = re.compile(
    r"```mermaid\s*\n(.*?)\n```",
    re.DOTALL,
)

# Unicode dash and smart-quote replacements
UNICODE_REPLACEMENTS = {
    "\u2014": "-",  # em-dash —
    "\u2013": "-",  # en-dash –
    "\u2212": "-",  # minus sign
    "\u201c": '"',  # left double quote
    "\u201d": '"',  # right double quote
    "\u2018": "'",  # left single quote
    "\u2019": "'",  # right single quote
    "\u2026": "...",  # ellipsis
    "\u00a0": " ",  # non-breaking space
}


@dataclass
class SanitizeResult:
    output: str
    fixes: list[dict[str, Any]] = field(default_factory=list)


def sanitize_markdown(md: str) -> SanitizeResult:
    """Sanitize every ```mermaid block in the markdown string."""
    result = SanitizeResult(output=md)

    def _replace(match: re.Match[str]) -> str:
        block_idx = len([f for f in result.fixes if f.get("chart_index") is not None])
        original = match.group(1)
        cleaned, fixes_here = _sanitize_block(original, chart_index=block_idx)
        if fixes_here:
            result.fixes.extend(fixes_here)
        return f"```mermaid\n{cleaned}\n```"

    result.output = MERMAID_BLOCK_RE.sub(_replace, md)

    # Emit telemetry
    logger = get_logger()
    if logger and result.fixes:
        logger.event(
            "chart.sanitizer_applied",
            total_fixes=len(result.fixes),
            fixes=result.fixes[:50],
        )
    return result


def _sanitize_block(
    block: str, chart_index: int
) -> tuple[str, list[dict[str, Any]]]:
    fixes: list[dict[str, Any]] = []
    original = block

    # 1. Unicode dashes + smart quotes
    for char, replacement in UNICODE_REPLACEMENTS.items():
        if char in block:
            block = block.replace(char, replacement)
            fixes.append(
                {
                    "chart_index": chart_index,
                    "fix": "unicode_replace",
                    "char": repr(char),
                    "replacement": replacement,
                }
            )

    # 2. `xychart-beta horizontal` + string y-axis → convert to vertical
    if re.search(r"^xychart-beta\s+horizontal\s*$", block, flags=re.MULTILINE):
        if re.search(r"^\s*y-axis\s*\[", block, flags=re.MULTILINE):
            block = _rotate_horizontal_xychart(block)
            fixes.append(
                {
                    "chart_index": chart_index,
                    "fix": "xychart_horizontal_rotated",
                    "reason": "horizontal variant rejects categorical y-axis",
                }
            )

    # 3. Quoted numeric inside bar/line arrays — e.g. bar ["5", "6"] → bar [5, 6]
    def _unquote_numeric_arrays(m: re.Match[str]) -> str:
        prefix = m.group(1)
        body = m.group(2)
        new_body = re.sub(r'"\s*(-?\d+(?:\.\d+)?)\s*"', r"\1", body)
        if new_body != body:
            fixes.append(
                {
                    "chart_index": chart_index,
                    "fix": "unquote_numeric_array",
                    "array": prefix,
                }
            )
        return f"{prefix} [{new_body}]"

    block = re.sub(r"^(\s*(?:bar|line))\s*\[(.*?)\]", _unquote_numeric_arrays, block, flags=re.MULTILINE)

    # 4. Trim trailing whitespace on each line — Mermaid lexer is fussy
    block = "\n".join(line.rstrip() for line in block.splitlines())

    if block == original:
        return block, []
    return block, fixes


def _rotate_horizontal_xychart(block: str) -> str:
    """Swap axes: `xychart-beta horizontal` with categorical y-axis + numeric x-axis
    becomes `xychart-beta` with categorical x-axis + numeric y-axis."""
    lines = block.splitlines()
    out: list[str] = []
    x_axis_line: str | None = None
    y_axis_line: str | None = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("xychart-beta"):
            out.append("xychart-beta")
            continue
        if stripped.startswith("x-axis"):
            x_axis_line = line
            continue
        if stripped.startswith("y-axis"):
            y_axis_line = line
            continue
        out.append(line)

    # Find where to insert rebuilt axes (after title if present, else at top)
    insert_at = 1
    for i, line in enumerate(out):
        if line.strip().startswith("title"):
            insert_at = i + 1
            break

    # Rebuild: the old y-axis (categorical) becomes new x-axis;
    # the old x-axis (numeric range) becomes new y-axis.
    if y_axis_line and "[" in y_axis_line:
        cats_indent = len(y_axis_line) - len(y_axis_line.lstrip())
        indent = " " * cats_indent
        # Extract the bracketed category list
        m = re.search(r"\[.*\]", y_axis_line)
        cats = m.group(0) if m else "[]"
        new_x = f"{indent}x-axis {cats}"
        out.insert(insert_at, new_x)
        insert_at += 1

    if x_axis_line and "-->" in x_axis_line:
        # old x-axis was like `x-axis 0 --> 10` → new y-axis `y-axis "Score" 0 --> 10`
        indent = " " * (len(x_axis_line) - len(x_axis_line.lstrip()))
        range_match = re.search(r"(-?\d+(?:\.\d+)?)\s*-->\s*(-?\d+(?:\.\d+)?)", x_axis_line)
        if range_match:
            lo, hi = range_match.group(1), range_match.group(2)
            new_y = f'{indent}y-axis "Score" {lo} --> {hi}'
            out.insert(insert_at, new_y)

    # Reverse the bar/line array order so categories still line up (since we rotated).
    reversed_arrays: list[str] = []
    for line in out:
        m = re.match(r"^(\s*(?:bar|line))\s*\[(.*?)\]\s*$", line)
        if m:
            prefix = m.group(1)
            items = [s.strip() for s in m.group(2).split(",") if s.strip()]
            reversed_arrays.append(f"{prefix} [{', '.join(reversed(items))}]")
        else:
            reversed_arrays.append(line)
    return "\n".join(reversed_arrays)
