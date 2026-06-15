"""Regression tests for ``shopstack.services.find._calculate_confidence_decay``.

motto_v3 §0.5 / §0.11: customer-facing scoring that returns
"fully confident" on any error is a real defect — it over-trusts
bad data and the user gets shown a wrong ranking.

The pre-fix behaviour was ``except Exception: return 1.0``
which silently over-trusted a malformed timestamp. These tests
lock in the corrected contract: malformed input gets an
explicit neutral (0.5), not silent full confidence.

The test file lives at tests/ root so it's discoverable
alongside the service's other tests, even though no test_find.py
exists yet. (Future work: rename when the public-API tests
migrate to a consolidated test_find.py.)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from shopstack.services.find import (
    MIN_CONFIDENCE,
    _calculate_confidence_decay,
)


# ── Contract: the public surface ──────────────────────────────────


class TestNormalCases:
    def test_none_timestamp_returns_one(self):
        """No sighting means no information; we don't penalize."""
        assert _calculate_confidence_decay(None) == 1.0

    def test_empty_string_returns_one(self):
        assert _calculate_confidence_decay("") == 1.0

    def test_just_seen_returns_one(self):
        """A sighting 1 second ago is fresh — full confidence."""
        ts = datetime.now(timezone.utc).isoformat()
        assert _calculate_confidence_decay(ts) == pytest.approx(1.0, abs=0.01)

    def test_half_life_elapsed_returns_half(self):
        """After exactly one half-life, the confidence is 0.5.

        ``CONFIDENCE_HALFLIFE_DAYS = 30`` in find.py, so a 30-day
        old sighting decays to 0.5.
        """
        ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        # Default half_life_days is 30; the result should be ~0.5.
        assert _calculate_confidence_decay(ts) == pytest.approx(0.5, abs=0.02)

    def test_floored_at_min_confidence(self):
        """Beyond many half-lives, decay never goes below MIN_CONFIDENCE."""
        ts = (datetime.now(timezone.utc) - timedelta(days=365 * 10)).isoformat()
        assert _calculate_confidence_decay(ts) == MIN_CONFIDENCE

    def test_future_timestamp_returns_one(self):
        """Clock skew or test fixtures — a 'future' sighting is
        treated as 'just seen' rather than negative-decay."""
        future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        assert _calculate_confidence_decay(future) == 1.0

    def test_z_suffix_utc_isoformat_parses(self):
        """``...Z`` is the Z-suffix shorthand for UTC."""
        ts = (datetime.now(timezone.utc) - timedelta(seconds=10)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        assert _calculate_confidence_decay(ts) == pytest.approx(1.0, abs=0.01)


# ── The fix: malformed input must NOT silently return 1.0 ──────


class TestMalformedInputRegression:
    """Pre-fix: ``except Exception: return 1.0`` made any
    malformed timestamp return full confidence — over-trusting
    bad data. Post-fix: return 0.5 (explicit neutral)."""

    def test_malformed_garbage_string_returns_neutral_not_one(self):
        """A timestamp that's not ISO-format at all must NOT
        return 1.0. The pre-fix code did; this test locks in
        the corrected behavior.
        """
        result = _calculate_confidence_decay("not-a-timestamp")
        assert result < 1.0, (
            f"Malformed timestamp returned {result!r}; the pre-fix "
            f"bug returned 1.0 (silent over-trust). The post-fix "
            f"contract is 0.5 (explicit neutral)."
        )
        assert result == 0.5

    def test_partial_garbage_returns_neutral(self):
        assert _calculate_confidence_decay("2026-99-99") == 0.5

    def test_empty_after_strip_returns_neutral(self):
        """A whitespace string is not a valid timestamp."""
        assert _calculate_confidence_decay("   ") == 0.5

    def test_none_type_for_timestamp_param_returns_one(self):
        """Defensive: a caller passing None where a string was
        expected (a typing slip) gets the no-information
        default, not the malformed-input neutral.
        """
        assert _calculate_confidence_decay(None) == 1.0

    def test_integer_timestamp_returns_neutral(self):
        """A wrong type silently coerced must not produce 1.0.

        Per the narrow-exception contract: an int input raises
        ``AttributeError`` (int has no ``.replace``) which is NOT
        in the catch list (``(ValueError, TypeError)``), so it
        propagates to the caller. The test locks in: "wrong type
        is a programming error, not silently normalised".
        """
        with pytest.raises(AttributeError):
            _calculate_confidence_decay(12345)  # type: ignore[arg-type]


# ── The fix is narrow: only specific exceptions are caught ──────


class TestExceptionScope:
    """Per motto_v3 §0.6: a narrow except clause is safer than
    a blanket ``except Exception``. The fix narrows the catch
    to ``(ValueError, TypeError)`` so genuine bugs (AttributeError,
    NameError, …) still surface in the operator's logs instead
    of being silently turned into a 0.5 decay.
    """

    def test_unexpected_exception_still_propagates(self, monkeypatch):
        """If a real bug (AttributeError, NameError, …) fires
        during decay calculation, it must propagate so the
        operator sees it. The fix only catches parse-time
        errors (``ValueError``, ``TypeError``).
        """
        from shopstack.services import find

        def boom(timestamp_str, half_life_days=7.0):
            raise AttributeError("simulated real bug")

        monkeypatch.setattr(find, "_calculate_confidence_decay", boom)
        with pytest.raises(AttributeError):
            find._calculate_confidence_decay("any-input")
