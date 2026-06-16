"""Regression test for the Pass 18 canonical-only contract.

**Why this exists (motto_v3 §0 bold + first-principles):**

In Pass 17, the legacy decision-renderer shim
(``shopstack._legacy_decisions``) was deprecated but kept as
a backward-compat layer. The shim provided 5 functions that
took a ``Database`` and pre-fetched data internally:

  - ``render_what_changed(db)``
  - ``render_cadence_insights(db)``
  - ``render_waste_warnings(db)``
  - ``render_swiggy_soldout_warning(shopping_list_names: list[str])``
  - ``render_needs_confirmation(db)``

The canonical versions (in ``shopstack.ui.renderers.decision_cards``)
take pre-fetched data and are the only functions any new code
should use.

**The reversion problem:**

During Pass 17, a concurrent agent repeatedly reverted test
files back to the legacy-import pattern. The shim still
worked (so the reverted tests passed), but the migration was
erased each time. This test guards against that reversion
pattern by:

  1. Asserting the shim file does NOT exist (resurrection
     prevention).
  2. Asserting the legacy 5 functions CANNOT be imported via
     the ``shopstack.decisions`` package (the legacy routing
     is gone).
  3. Asserting the canonical 5 functions have the right
     signatures (catches signature drift).
  4. Asserting no production code uses the legacy call pattern
     (db-bridging function bodies).

Per ``motto_v3`` §0: "Build for the **best app**, not the
safest small change. Prefer bold, durable, first-principles
solutions over narrow patchwork." The bold fix is to delete
the shim entirely. This test pins that contract.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LEGACY_SHIM = ROOT / "shopstack" / "_legacy_decisions.py"
DECISIONS_INIT = ROOT / "shopstack" / "decisions" / "__init__.py"
CANONICAL_FILE = ROOT / "shopstack" / "ui" / "renderers" / "decision_cards.py"

LEGACY_FUNCTION_NAMES = {
    "render_what_changed",
    "render_cadence_insights",
    "render_waste_warnings",
    "render_swiggy_soldout_warning",
    "render_needs_confirmation",
}


# ── Guard 1: the shim file does NOT exist (resurrection prevention) ──


def test_legacy_shim_does_not_exist():
    """The legacy shim file must not exist.

    Per Pass 18: the shim was deleted as the durable fix for
    the concurrent-agent reversion pattern. The shim's
    existence would re-enable the bug it was created to
    solve (a parallel source of truth that the migration
    could be reverted to).
    """
    assert not LEGACY_SHIM.exists(), (
        f"The legacy shim {LEGACY_SHIM} was resurrected. "
        f"Pass 18 deleted it as the durable first-principles "
        f"fix to the concurrent-agent reversion pattern. "
        f"If you're seeing this, the shim was re-introduced "
        f"(likely by reverting Pass 18). Delete it again and "
        f"update tests/test_decisions_canonical_only.py to "
        f"reflect the new state."
    )


def test_legacy_shim_does_not_import():
    """``import shopstack._legacy_decisions`` must fail.

    Belt-and-suspenders guard: even if the file is recreated
    without a test, an import would re-enable the bug. This
    test ensures the import also fails.

    Note: a missing file means ``importlib.import_module``
    raises ``ModuleNotFoundError``. We accept both
    ModuleNotFoundError and ImportError as "module does not
    exist" signals.
    """
    result = subprocess.run(
        [sys.executable, "-c", "import shopstack._legacy_decisions"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode != 0, (
        "Importing `shopstack._legacy_decisions` succeeded. "
        "The shim should not exist. Delete it."
    )
    # The error message should mention the module.
    combined = result.stdout + result.stderr
    assert "_legacy_decisions" in combined or "ModuleNotFoundError" in combined, (
        f"Unexpected error when importing _legacy_decisions: {combined[:200]}"
    )


# ── Guard 2: legacy routing in shopstack.decisions is GONE ──


def test_decisions_init_does_not_route_legacy_functions():
    """``shopstack.decisions`` must NOT route any of the 5 legacy
    functions to anywhere (the legacy shim is gone, so any
    routing would be a dead reference).
    """
    src = DECISIONS_INIT.read_text()
    for fn_name in LEGACY_FUNCTION_NAMES:
        # The function name should not appear in the __getattr__
        # routing logic or in __all__ (legacy routing is removed).
        # We allow it in the comment block, but check that the
        # function name is not in an active import / routing.
        in_getattr = re.search(
            rf"if\s+name\s+==?\s+[\"']{re.escape(fn_name)}[\"']",
            src,
        )
        in_all = re.search(
            rf"[\"']{re.escape(fn_name)}[\"']\s*,",
            src.split("__all__")[-1] if "__all__" in src else "",
        )
        assert not in_getattr, (
            f"shopstack.decisions.__getattr__ still routes {fn_name!r} "
            f"to the legacy shim. Per Pass 18, the shim is gone — "
            f"this routing is a dead reference. Remove the routing."
        )
        assert not in_all, (
            f"shopstack.decisions.__all__ still includes {fn_name!r}. "
            f"Per Pass 18, the legacy shim is gone. The function is "
            f"importable from `shopstack.ui.renderers.decision_cards` only."
        )


def test_cannot_import_legacy_via_shopstack_decisions():
    """Importing any legacy function via ``shopstack.decisions`` must fail.

    Run as a subprocess to ensure clean import state. If the
    shim were ever re-added, this test would catch it.
    """
    for fn_name in LEGACY_FUNCTION_NAMES:
        result = subprocess.run(
            [sys.executable, "-c", f"from shopstack.decisions import {fn_name}"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert result.returncode != 0, (
            f"Importing `from shopstack.decisions import {fn_name}` "
            f"succeeded. The legacy routing is removed in Pass 18; "
            f"this import should fail. If it succeeds, the legacy "
            f"routing was re-introduced."
        )


# ── Guard 3: canonical signatures are right ──


def test_canonical_signatures_take_prefetched_data():
    """The canonical renderers take pre-fetched data, not a ``db``.

    This test catches the case where someone refactors the
    canonical signatures back to ``db``-taking forms (which
    would re-introduce the coupling the migration was meant
    to break).
    """
    src = CANONICAL_FILE.read_text()
    expected = {
        "render_what_changed": ("purchases", "traces"),
        "render_cadence_insights": ("cadence", "today"),
        "render_waste_warnings": ("signals",),
        "render_swiggy_soldout_warning": ("availability",),
        "render_needs_confirmation": ("uncertain",),
    }
    missing: list[str] = []
    wrong: list[tuple[str, tuple, tuple]] = []
    for name, want in expected.items():
        m = re.search(
            rf"^def\s+{name}\s*\((.*?)\)\s*->",
            src,
            re.MULTILINE,
        )
        if not m:
            missing.append(name)
            continue
        raw = m.group(1)
        names: list[str] = []
        for m2 in re.finditer(r"(?:^|,\s*)(\w+)\s*(?=[:,)\s])", raw):
            if m2.group(1) != "self":
                names.append(m2.group(1))
        actual = tuple(names[:len(want)])
        if actual != want:
            wrong.append((name, want, actual))
    assert not missing, (
        f"Canonical functions missing from decision_cards.py: {missing}. "
        f"Pass 18 expects these signatures."
    )
    assert not wrong, (
        "Canonical signatures changed. Per motto_v3 §7: don't refactor "
        "canonical signatures without updating all callers + this test. "
        "Wrong signatures: "
        + ", ".join(f"{n} (want={w}, got={a})" for n, w, a in wrong)
    )


# ── Guard 4: no production code uses the legacy call pattern ──


def test_no_production_code_uses_legacy_imports():
    """No production code imports the 5 legacy functions from
    ``shopstack.decisions`` or ``shopstack._legacy_decisions``.

    The shim is gone, so any import site that uses these
    patterns is broken (the test should fail). This guard
    catches concurrent-agent reverts that re-introduce the
    broken import pattern.
    """
    pattern = re.compile(
        r"from\s+shopstack\.(?:decisions|_legacy_decisions)\s+import\s+"
        r"([^#\n]+)",
        re.MULTILINE,
    )
    bad: list[tuple[str, int, str, str]] = []
    for root, dirs, files in os.walk(ROOT / "shopstack"):
        dirs[:] = [d for d in dirs if d not in ("__pycache__",)]
        for f in files:
            if not f.endswith(".py"):
                continue
            path = Path(root) / f
            # Skip the shim file (which should not exist; the
            # test_no_legacy_shim_file test catches the case
            # where it does).
            if path == LEGACY_SHIM:
                continue
            # Skip the decisions __init__ (it has a comment
            # about the legacy shim).
            rel = str(path.relative_to(ROOT))
            if rel in {
                "shopstack/decisions/__init__.py",
                "tests/test_decisions_canonical_only.py",
            }:
                continue
            try:
                src = path.read_text()
            except (FileNotFoundError, IsADirectoryError):
                continue
            for line_no, line in enumerate(src.splitlines(), start=1):
                m = pattern.search(line)
                if not m:
                    continue
                names = {n.strip() for n in m.group(1).split(",") if n.strip()}
                legacy = names & LEGACY_FUNCTION_NAMES
                if legacy:
                    mod = "shopstack.decisions" if "shopstack.decisions" in m.group(0) else "shopstack._legacy_decisions"
                    bad.append((rel, line_no, mod, ", ".join(sorted(legacy))))
    assert not bad, (
        "Found legacy import sites. The shim is deleted (Pass 18); "
        "these imports will fail at runtime. Migrate to "
        "`shopstack.ui.renderers.decision_cards` (canonical) or "
        "`shopstack.ui.renderers` (canonical re-exports). "
        f"Found {len(bad)} violations:\n"
        + "\n".join(f"  {p}:{ln}: from {m} import {names}" for p, ln, m, names in bad)
    )


def test_no_production_code_uses_legacy_db_bridging_pattern():
    """No production code has a function that takes ``db`` and
    pre-fetches data internally before calling the canonical.

    This was the legacy shim's pattern. With the shim gone,
    this pattern would re-introduce a parallel source of truth.
    """
    canonical_call = re.compile(
        r"render_(what_changed|cadence_insights|waste_warnings|"
        r"swiggy_soldout_warning|needs_confirmation)\s*\(",
    )
    db_fetch = re.compile(
        r"\bdb\.(get_purchase_events|get_traces|get_inventory|"
        r"detect_purchase_cadence|detect_waste_patterns)\b",
    )
    bad: list[tuple[str, int, str]] = []
    shopstack_root = ROOT / "shopstack"
    for path in shopstack_root.rglob("*.py"):
        rel = str(path.relative_to(ROOT))
        if rel in {
            "shopstack/ui/renderers/decision_cards.py",
            "shopstack/ui/renderers/__init__.py",
            "shopstack/decisions/__init__.py",
        }:
            continue
        try:
            src = path.read_text()
        except (FileNotFoundError, IsADirectoryError):
            continue
        # Find function defs: function whose body contains
        # both a canonical call AND a db-fetch, AND takes `db`
        # as first parameter.
        for m in re.finditer(
            r"^def\s+\w+\(([^)]*db[^)]*)\)\s*:\s*\n(.*?)(?=^\ndef\s|\Z)",
            src,
            re.MULTILINE | re.DOTALL,
        ):
            body = m.group(2)
            if not canonical_call.search(body):
                continue
            if not db_fetch.search(body):
                continue
            line_no = src[: m.start()].count("\n") + 1
            bad.append((rel, line_no, "db-bridging function"))
    assert not bad, (
        "Found new production db-to-canonical bridging functions. "
        "The shim is deleted (Pass 18); these re-introduce the "
        "parallel-source-of-truth bug. Migrate the call sites to "
        "pre-fetch and call the canonical directly. "
        f"Found {len(bad)} violations:\n"
        + "\n".join(f"  {p}:{ln}: {name}" for p, ln, name in bad)
    )
