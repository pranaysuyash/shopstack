"""Regression test for f-string corruption (Pass 17, 2026-06-15).

**Why this exists (motto_v3 §6 pre-existing is not an excuse):**

A concurrent agent introduced widespread f-string corruption
into ``shopstack/ui/components/primitives.py`` (and possibly
other files) on 2026-06-15. The corruption took these forms:

  1. ``f'<span style='...`` — single-quoted f-string with
     single-quoted style attribute (Python parses the inner
     ``'`` as the string terminator).
  2. ``f'pan style='...`` / ``f'iv style='...`` — lost the
     leading ``<s`` / ``<d`` characters of the tag name.
  3. ``f"<tag>...`` followed by ``\'`` at the end — escaped
     single quote that should have been the closing ``"``.
  4. ``font-size`` mangled to ``ffont-size`` or ``ofont-size`` —
     lost/duplicated the leading ``f``.

The result was unparseable Python in 13+ lines, breaking the
entire ``shopstack.ui`` import chain (because ``cards.py``
imports from ``primitives.py``, and ``_comparison.py``
imports from ``cards.py``).

This test guards against future drift that re-introduces
the same corruption. The test runs fast (no I/O, no DB).

**Scope:** only checks the canonical UI primitive file. Other
files may have similar corruption that needs separate
regression tests. Per motto_v3 §6, we fix what's in the
blast radius; adding similar guards for other files is
deferred to a future pass.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRIMITIVES = ROOT / "shopstack" / "ui" / "components" / "primitives.py"

# Patterns that signal f-string corruption:
# - f'pan / f"pan (lost <s from <span) — valid f-string but wrong content
# - f'iv  / f"iv  (lost <d from <div)
# - f'<span style=' / f'<div style=' (outer ' conflicts with inner ')
# - ffont- / ofont- (lost or doubled f in font-)
# - </tag>\' at end of line (escaped quote instead of closing ")
FSTRING_CORRUPTION_PATTERNS = [
    (re.compile(r"(?<![A-Za-z0-9_'\"\\])f'pan(\s+)(?=[A-Za-z])"),
     "f'pan (lost `<s` from `<span`) — should be `f\"<span`"),
    (re.compile(r'(?<![A-Za-z0-9_\'\"\\])f"pan(\s+)(?=[A-Za-z])'),
     'f"pan (lost `<s` from `<span`) — should be `f"<span`'),
    (re.compile(r"(?<![A-Za-z0-9_'\"\\])f'iv(\s+)(?=[A-Za-z])"),
     "f'iv (lost `<d` from `<div`) — should be `f\"<div`"),
    (re.compile(r'(?<![A-Za-z0-9_\'\"\\])f"iv(\s+)(?=[A-Za-z])'),
     'f"iv (lost `<d` from `<div`) — should be `f"<div`'),
    (re.compile(r"f'<(span|div)(\s+style=')"),
     "f'<span/div style=' (outer ' conflicts with inner ') — should be `f\"<span/div style='`"),
    (re.compile(r"f'<(span|div)(\s+class=')"),
     "f'<span/div class=' (outer ' conflicts with inner ') — should be `f\"<span/div class='`"),
    (re.compile(r"f'<(span|div)(\s+aria-)"),
     "f'<span/div aria- (outer ' conflicts with inner ') — should be `f\"<span/div aria-`"),
    (re.compile(r"f'<(span|div)(\s+id=')"),
     "f'<span/div id=' (outer ' conflicts with inner ') — should be `f\"<span/div id='`"),
    (re.compile(r'ffont-'),
     'ffont- (doubled f in font-size/weight) — should be `font-`'),
    (re.compile(r"ofont-"),
     'ofont- (wrong leading char in font-) — should be `font-`'),
    (re.compile(r"</(?:span|div)>\\\\?'$"),
     "</tag>\\' at end of line (escaped single quote instead of closing \") — should be `</tag>\"`"),
]


def test_primitives_file_parses_as_python():
    """The primitives file must parse cleanly.

    This is the Tier-1 minimum: if the file doesn't parse,
    the entire ``shopstack.ui`` import chain is broken.
    """
    src = PRIMITIVES.read_text()
    try:
        ast.parse(src)
    except SyntaxError as e:
        pytest.fail(
            f"shopstack/ui/components/primitives.py does not parse: "
            f"line {e.lineno}: {e.msg}\n"
            f"  {e.text.rstrip() if e.text else ''}\n\n"
            f"Concurrent-agent f-string corruption pattern. "
            f"Re-introduces a §6 pre-existing bug."
        )


def test_primitives_file_has_no_fstring_corruption_patterns():
    """The primitives file has no known f-string corruption patterns.

    Catches the specific patterns observed in the 2026-06-15
    concurrent-agent incident:
      - f'pan / f"pan (lost <s)
      - f'iv  / f"iv  (lost <d)
      - f'<span/div style=' / class=' / aria- / id=' (outer/inner quote conflict)
      - ffont- / ofont- (font-size mangled)
      - </tag>\' at end of line (escaped quote instead of closing ")
    """
    src = PRIMITIVES.read_text()
    bad: list[tuple[int, str, str]] = []
    for line_no, line in enumerate(src.splitlines(), start=1):
        for pattern, description in FSTRING_CORRUPTION_PATTERNS:
            m = pattern.search(line)
            if m:
                bad.append((line_no, line.rstrip()[:100], description))
    assert not bad, (
        f"Found {len(bad)} f-string corruption patterns in primitives.py. "
        f"Each is a §6 pre-existing bug. Fix each line before merging.\n"
        + "\n".join(
            f"  line {ln}: {desc}\n    > {snippet}"
            for ln, snippet, desc in bad
        )
    )


# NOTE: a coarse "balanced quotes per line" test was removed — it's
# too noisy in this file (docstrings, escaped quotes inside f-strings,
# multi-line f-string continuations all legitimately have unbalanced
# quotes per line). The two tests above (parses + pattern check) are
# the right balance of strict enough to catch the corruption and
# loose enough to not generate false positives.
