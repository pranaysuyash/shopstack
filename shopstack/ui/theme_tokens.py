"""CSS variable name constants for Python-side color references.

Import from here instead of hardcoding hex colors in Python strings.
Use as: f'color:var({CSS_VAR["red"]})' → 'color:var(--red)'

These names must stay in sync with shopstack/ui/theme.py :root block.
"""

from __future__ import annotations

# ── Semantic colors ────────────────────────────────────────────────
CSS_VAR: dict[str, str] = {
    # Backgrounds
    "bg": "--bg",
    "bg-card": "--bg-card",
    "bg-card-strong": "--bg-card-strong",
    "bg-warm": "--bg-warm",
    "bg-input": "--bg-input",
    # Borders
    "border": "--border",
    "border-strong": "--border-strong",
    # Text
    "text": "--text",
    "text-muted": "--text-muted",
    "text-dim": "--text-dim",
    "text-faint": "--text-faint",
    # Brand
    "accent": "--accent",
    "accent-hover": "--accent-hover",
    "accent-soft": "--accent-soft",
    # Status
    "green": "--green",
    "red": "--red",
    "amber": "--amber",
    "blue": "--blue",
    "focus": "--focus",
    # Decision
    "decision-buy": "--decision-buy",
    "decision-skip": "--decision-skip",
    "decision-use-soon": "--decision-use-soon",
    "decision-optional": "--decision-optional",
    "decision-compare": "--decision-compare",
    "decision-confirm": "--decision-confirm",
    "decision-watch": "--decision-watch",
    # Status mapping (convenience)
    "success": "--green",
    "danger": "--red",
    "warning": "--amber",
    "info": "--blue",
}

# ── Decision color → CSS variable (mirrors DECISION_COLORS in decisions/types.py) ──
DECISION_COLOR_VARS: dict[str, str] = {
    "buy": "--decision-buy",
    "skip": "--decision-skip",
    "use_soon": "--decision-use-soon",
    "optional": "--decision-optional",
    "compare": "--decision-compare",
    "confirm": "--decision-confirm",
    "watch": "--decision-watch",
}

# ── Waste risk → CSS variable ──
WASTE_RISK_COLORS: dict[str, str] = {
    "high": "--red",
    "medium": "--amber",
    "low": "--green",
}

# ── Shopping status → CSS variable ──
SHOPPING_STATUS_COLORS: dict[str, str] = {
    "Must buy": "--decision-buy",
    "Optional": "--decision-optional",
    "Use Soon": "--decision-use-soon",
    "Skip": "--decision-skip",
}


def cssvar(name: str) -> str:
    """Return a `var(--name)` CSS reference string."""
    return f"var({name})"


def csscolor(token: str) -> str:
    """Resolve a CSS_VAR key or direct CSS variable name to a `var()` reference."""
    if token in CSS_VAR:
        return f"var({CSS_VAR[token]})"
    if token.startswith("--"):
        return f"var({token})"
    # Fallback: treat as literal
    return token
