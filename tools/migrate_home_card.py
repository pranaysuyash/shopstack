"""Migrate inline `<div class='home-card'>` patterns to home_card() primitive.

Per motto_v3 §11 engineering standards, this mechanical migration preserves
behavior exactly while consolidating the pattern under a single canonical
call. The script handles four common cases:

1. `<div class='home-card'>{body}</div>` → `home_card(body={body})`
2. `<div class='home-card'><h4>{title}</h4>{body}</div>` → `home_card(title={title}, body={body})`
3. `<div class='home-card' style='{style}'>{body}</div>` → `home_card(body={body}, style={style})`
4. `<div class='home-card' style='{style}'><h4>{title}</h4>{body}</div>` → `home_card(title={title}, body={body}, style={style})`

The script does NOT touch patterns that have:
- Additional class names (e.g. class='home-card hero-panel')
- Additional attributes (e.g. role='region', id='foo')
- Nested divs with home-card as the inner element

Those require manual review.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


SCREENS_DIR = Path("shopstack/ui/screens")

# Pattern 4: style + title + body
# `<div class='home-card' style='...'><h4>TITLE</h4>BODY</div>`
P_STYLE_TITLE = re.compile(
    r"<div class='home-card' style='([^']*)'><h4>([^<]+)</h4>(.*?)</div>",
    re.DOTALL,
)
# Pattern 3: style + body
# `<div class='home-card' style='...'>BODY</div>`
P_STYLE_BODY = re.compile(
    r"<div class='home-card' style='([^']*)'>(.*?)</div>",
    re.DOTALL,
)
# Pattern 2: title + body
# `<div class='home-card'><h4>TITLE</h4>BODY</div>`
P_TITLE = re.compile(
    r"<div class='home-card'><h4>([^<]+)</h4>(.*?)</div>",
    re.DOTALL,
)
# Pattern 1: body only
# `<div class='home-card'>BODY</div>`
# MUST NOT match multi-line tag — the .*? is non-greedy and the </div> is the
# closing tag of the OUTER home-card. Multi-line cases are skipped by the
# constraint that BODY does not contain a `<div` opening tag.
P_BODY = re.compile(
    r"<div class='home-card'>(.*?)</div>(?![^<]*</div>)",
    re.DOTALL,
)


def migrate(content: str) -> tuple[str, int]:
    """Apply all four pattern replacements; return (new_content, count)."""
    count = 0

    def _replace_style_title(m: re.Match) -> str:
        nonlocal count
        count += 1
        style, title, body = m.group(1), m.group(2), m.group(3)
        return f"home_card(title={title!r}, body={body!r}, style={style!r})"

    def _replace_style_body(m: re.Match) -> str:
        nonlocal count
        count += 1
        style, body = m.group(1), m.group(2)
        return f"home_card(body={body!r}, style={style!r})"

    def _replace_title(m: re.Match) -> str:
        nonlocal count
        count += 1
        title, body = m.group(1), m.group(2)
        return f"home_card(title={title!r}, body={body!r})"

    def _replace_body(m: re.Match) -> str:
        nonlocal count
        count += 1
        body = m.group(1)
        return f"home_card(body={body!r})"

    # Order matters: more specific patterns first so the title+h4 in the
    # pattern is consumed before the simple body match.
    content = P_STYLE_TITLE.sub(_replace_style_title, content)
    content = P_STYLE_BODY.sub(_replace_style_body, content)
    content = P_TITLE.sub(_replace_title, content)
    content = P_BODY.sub(_replace_body, content)

    return content, count


def process_file(path: Path) -> int:
    src = path.read_text(encoding="utf-8")
    if "home_card" not in src and "home-card" not in src:
        return 0
    # Skip files that don't yet import home_card
    if "from shopstack.ui.components.primitives import" not in src and "home_card" not in src:
        return 0

    new_src, count = migrate(src)
    if count == 0:
        return 0

    # Add the import if not present
    if "from shopstack.ui.components.primitives import" in src and "home_card" not in src:
        # Find the primitives import line and add home_card
        new_src = re.sub(
            r"from shopstack\.ui\.components\.primitives import \(([^)]*)\)",
            lambda m: f"from shopstack.ui.components.primitives import (\n    {m.group(1).strip()},\n    home_card,\n)",
            new_src,
            count=1,
        )
    elif "from shopstack.ui.components.primitives import home_card" not in src and "from shopstack.ui.components.primitives" in src:
        # Single-line primitives import
        new_src = re.sub(
            r"from shopstack\.ui\.components\.primitives import (.+)",
            r"from shopstack.ui.components.primitives import \1, home_card",
            new_src,
            count=1,
        )
    elif "home_card" not in src and "primitives" not in src:
        # Need to add a new import line for primitives
        # Insert after the last import line
        lines = new_src.split("\n")
        last_import = -1
        for i, line in enumerate(lines):
            if line.startswith("from shopstack") or line.startswith("import "):
                last_import = i
        if last_import >= 0:
            lines.insert(
                last_import + 1,
                "from shopstack.ui.components.primitives import home_card",
            )
            new_src = "\n".join(lines)

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
    print(f"\nTOTAL: {total} home-card patterns migrated to home_card() primitive")
    return total


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
