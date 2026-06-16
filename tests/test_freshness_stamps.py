"""Regression tests for the freshness-stamp rollout (2026-06-15).

Per motto_v3 §0.10 Observability Is Delivery, every recommendation
card must carry a "Last updated" stamp so the user can trust the
data. The primitive ``last_updated_stamp`` exists, but before
this pass only a few cards used it (dashboard market, price
memory, intelligence cards). The decision_cards renderers
(restock, price-deals, price-drops) had NO stamps.

These tests pin the contract:

* The 3 decision_cards renderers emit a "Last updated" stamp.
* The stamp degrades gracefully when no timestamp is provided
  (the primitive renders "Last updated: unknown" rather than
  crashing).
* A timestamp passed via ``generated_at`` on the first item is
  what the renderer picks up (so the rest of the rows don't
  need to repeat it).

Evidence tier: T1 (static inspection) + T2 (this test passes).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from shopstack.ui.renderers.decision_cards import (
    render_price_deals,
    render_price_drops,
    render_restock_predictions,
)


def _sample_restock(when: datetime | None = None) -> list[dict]:
    item = {
        "canonical_name": "milk",
        "urgency": "due_soon",
        "reason": "Likely needed in 2 days",
        "typical_qty": 1.0,
        "typical_unit": "L",
        "quantity_at_home": 0,
    }
    if when is not None:
        item["generated_at"] = when
    return [item]


def _sample_deals(when: datetime | None = None) -> list[dict]:
    item = {
        "product": "rice",
        "score": "great",
        "reason": "Below historical median",
    }
    if when is not None:
        item["generated_at"] = when
    return [item]


def _sample_drops(when: datetime | None = None) -> list[dict]:
    item = {
        "canonical_name": "oil",
        "display_name": "Cooking oil",
        "source": "swiggy",
        "current_price": 180,
        "median_price": 220,
        "drop_pct": 18,
        "drop_amount": 40,
    }
    if when is not None:
        item["generated_at"] = when
    return [item]


# ── Happy path: timestamp provided ─────────────────────────────────


def test_restock_predictions_render_freshness_stamp() -> None:
    when = datetime.now(timezone.utc)
    html = render_restock_predictions(_sample_restock(when))
    assert "Last updated" in html
    # The HTML <time> tag should carry the isoformat
    assert when.isoformat()[:10] in html


def test_price_deals_render_freshness_stamp() -> None:
    when = datetime.now(timezone.utc)
    html = render_price_deals(_sample_deals(when))
    assert "Last updated" in html
    assert when.isoformat()[:10] in html


def test_price_drops_render_freshness_stamp() -> None:
    when = datetime.now(timezone.utc)
    html = render_price_drops(_sample_drops(when))
    assert "Last updated" in html
    assert when.isoformat()[:10] in html


# ── Graceful degradation: no timestamp ──────────────────────────────


def test_restock_predictions_handles_missing_timestamp() -> None:
    """When ``generated_at`` is absent, the stamp degrades to
    "Last updated: unknown" (per the primitive's contract).
    The card still renders, the user just can't trust the
    timestamp until data is loaded.
    """
    html = render_restock_predictions(_sample_restock(when=None))
    assert "Last updated" in html
    assert "unknown" in html or "ago" in html  # either is acceptable


def test_price_deals_handles_missing_timestamp() -> None:
    html = render_price_deals(_sample_deals(when=None))
    assert "Last updated" in html


def test_price_drops_handles_missing_timestamp() -> None:
    html = render_price_drops(_sample_drops(when=None))
    assert "Last updated" in html


# ── Empty list path: render returns "" ─────────────────────────────


def test_empty_restock_returns_empty_string() -> None:
    """No predictions → no card. The freshness stamp is irrelevant
    here (and so is the card body). The renderer returns "".
    """
    assert render_restock_predictions([]) == ""


def test_empty_deals_returns_empty_string() -> None:
    assert render_price_deals([]) == ""


def test_empty_drops_returns_empty_string() -> None:
    assert render_price_drops([]) == ""


# ── Card content preservation ───────────────────────────────────────


def test_freshness_stamp_does_not_overwrite_row_content() -> None:
    """Additive per motto_v3 §11: the new stamp is APPENDED,
    not inserted into the row content. The existing row
    content (item name, reason, qty) must still be present.
    Note: the renderer does ``name.replace('_', ' ').title()``
    so the canonical "milk" becomes "Milk" in the rendered HTML.
    """
    when = datetime.now(timezone.utc)
    html = render_restock_predictions(_sample_restock(when))
    # Row content preserved (canonical name is title-cased)
    assert "Milk" in html
    assert "Likely needed" in html
    # AND the stamp is present
    assert "Last updated" in html


@pytest.mark.parametrize("renderer,sample", [
    (render_restock_predictions, _sample_restock),
    (render_price_deals, _sample_deals),
    (render_price_drops, _sample_drops),
])
def test_freshness_stamp_appears_in_all_three_renderers(
    renderer, sample,
) -> None:
    """Sweep test: every one of the 3 decision_cards renderers
    carries a freshness stamp when given a non-empty input with
    a timestamp. This is the contract that the 2026-06-15
    rollout established.
    """
    when = datetime.now(timezone.utc)
    html = renderer(sample(when))
    assert "Last updated" in html, (
        f"{renderer.__name__} missing freshness stamp — "
        f"this is the regression the audit flagged"
    )
    assert when.isoformat()[:10] in html
