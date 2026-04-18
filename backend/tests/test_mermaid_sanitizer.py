from app.core.mermaid_sanitizer import sanitize_markdown


def test_strips_em_dash_from_quadrant_label():
    md = """# Report
```mermaid
quadrantChart
  title Risk
  x-axis "Low" --> "High"
  y-axis "Low" --> "High"
  quadrant-1 Critical — act now
  quadrant-2 Monitor
  quadrant-3 Low
  quadrant-4 Plan
```
"""
    out = sanitize_markdown(md)
    assert "—" not in out.output
    assert "Critical - act now" in out.output
    assert any(f["fix"] == "unicode_replace" for f in out.fixes)


def test_strips_smart_quotes():
    md = """```mermaid
quadrantChart
  title Risk
  x-axis \u201cLow\u201d --> \u201cHigh\u201d
  quadrant-1 a
  quadrant-2 b
  quadrant-3 c
  quadrant-4 d
```"""
    out = sanitize_markdown(md)
    assert "\u201c" not in out.output
    assert "\u201d" not in out.output
    assert '"Low"' in out.output


def test_rotates_horizontal_xychart():
    md = """```mermaid
xychart-beta horizontal
  title "CVF"
  x-axis 0 --> 10
  y-axis ["Risk", "Traction", "Team"]
  bar [4, 7, 6]
```"""
    out = sanitize_markdown(md).output
    assert "xychart-beta horizontal" not in out
    assert "xychart-beta" in out
    assert 'x-axis ["Risk", "Traction", "Team"]' in out
    assert 'y-axis "Score" 0 --> 10' in out
    # Values should be reversed (horizontal→vertical rotation flips the order)
    assert "bar [6, 7, 4]" in out


def test_unquotes_numeric_in_bar_array():
    md = '```mermaid\nxychart-beta\n  bar ["5", "6", "7"]\n```'
    out = sanitize_markdown(md).output
    assert 'bar [5, 6, 7]' in out


def test_multiple_blocks_indexed():
    md = """```mermaid
quadrantChart
  title a
  x-axis "a" --> "b"
  quadrant-1 Critical — x
  quadrant-2 y
  quadrant-3 z
  quadrant-4 w
```
```mermaid
quadrantChart
  title b
  x-axis "a" --> "b"
  quadrant-1 Another — issue
  quadrant-2 y
  quadrant-3 z
  quadrant-4 w
```"""
    result = sanitize_markdown(md)
    # Both blocks get their em-dashes stripped
    assert result.output.count("—") == 0
    # Fixes from both blocks are recorded with distinct chart_index values
    idxs = {f.get("chart_index") for f in result.fixes}
    assert len(idxs) >= 2


def test_no_mermaid_block_is_noop():
    md = "# hi\nno mermaid here"
    out = sanitize_markdown(md)
    assert out.output == md
    assert out.fixes == []
