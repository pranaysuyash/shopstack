"""Migrate inline `<div class='stat-card'>` patterns to stat_card() primitive.

Per motto_v3 §11, this mechanical migration consolidates stat-card patterns
under the canonical primitive. Four common cases:

1. Simple stat-card with just a heading: `stat_card(value, label)`
2. Stat-card with a section heading: `stat_card("", "", body_html="<h4>...</h4>...")`
3. Stat-card with complex content (e.g. barcode info, swiggy section header)
4. Stat-card with additional attributes (role, id) - skipped for manual review
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


SCREENS_DIR = Path("shopstack/ui/screens")

# Stat-card with a heading AND body content (e.g. swiggy section header).
# The body contains `<h4>...</h4>` plus other content.
# `<div class='stat-card' style='...'><h4>TITLE</h4>BODY</div>`
P_HEADING_BODY = re.compile(
    r"<div class='stat-card'(?: style='([^']*)')?><h4>([^<]+)</h4>(.*?)</div>\s*\n?",
    re.DOTALL,
)

# Plain stat-card wrapper (just opens a stat-card section).
# `<div class='stat-card' style='...'></div>` or `<div class='stat-card'>CONTENT</div>`
P_PLAIN = re.compile(
    r"<div class='stat-card'(?: style='([^']*)')?>(.*?)</div>\s*\n?",
    re.DOTALL,
)


def migrate(content: str) -> tuple[str, int]:
    """Apply stat-card migrations. Conservative — skips ambiguous patterns."""
    count = 0

    def _replace_heading_body(m: re.Match) -> str:
        nonlocal count
        count += 1
        style, title, body = m.group(1), m.group(2), m.group(3)
        body_html = f"<h4>{title}</h4>{body}"
        if style:
            return f"stat_card(value='', label='', body_html={body_html!r}, style={style!r})\n"
        return f"stat_card(value='', label='', body_html={body_html!r})\n"

    # First pass: heading+body pattern (most specific)
    content = P_HEADING_BODY.sub(_replace_heading_body, content)

    return content, count


def process_file(path: Path) -> int:
    src = path.read_text(encoding="utf-8")
    if "stat-card" not in src:
        return 0

    new_src, count = migrate(src)
    if count == 0:
        return 0

    path.write_text(new_src, encoding="utf-8")
    return count


def main() -> int:
    total = 0
    for path in sorted(SCREENS_DIR.glob("*.py")):
        if path.name in ("__init__.py", "_utils.py", "_legacy") or path.name.startswith("_"):
            continue
        count = process_file(path)
        if count > 0:
            print(f"{path.name}: {count} migrations")
            total += count
    print(f"\nTOTAL: {total} stat-card heading+body patterns migrated to stat_card(body_html=)")
    return total


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
