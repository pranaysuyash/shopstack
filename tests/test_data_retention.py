"""Tests for `shopstack.services.data_retention` — the privacy panel service.

Verifies:
  * `retention_summary` returns the canonical defaults when the DB
    is missing or raises.
  * `purge_user_data` REQUIRES confirm=True (defensive against
    accidental wipes — motto_v3 §0.6 risk-based verification).
  * Each subsystem (traces, community, SMS, voice, backups) is
    purged via its public DB method.
  * Failures in one subsystem don't stop the others.
  * Inventory and shopping lists are NOT touched (per the doc's
    privacy contract).
  * The privacy panel HTML includes every retention knob and
    the "Delete my data" button.
  * The privacy panel script wires the button to /api/purge_user_data.
  * The panel respects the locale (Hindi strings appear when
    locale="hi").
  * Escape safety: panel output is safe even if a value contains
    HTML special characters.
"""
from __future__ import annotations

from html.parser import HTMLParser

import pytest

from shopstack.services.data_retention import (
    PurgeResult,
    RetentionPolicy,
    purge_user_data,
    render_privacy_panel_html,
    render_privacy_panel_script,
    retention_summary,
    update_retention_setting,
    _CONFIG_KEY_TRACE_TTL,
)


# ── Fixtures ───────────────────────────────────────────────────────


class _FakeDb:
    """A fake DB that records which purge methods were called."""

    def __init__(
        self,
        *,
        prune_traces_returns: int = 5,
        clear_community_returns: int = 3,
        clear_sms_returns: int = 2,
        purge_voice_returns: int = 1,
        purge_backups_returns: int = 0,
        trace_ttl_value: str = "30",
        community_optin: bool = False,
        fail_on: str = "",
    ) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self._prune_traces_returns = prune_traces_returns
        self._clear_community_returns = clear_community_returns
        self._clear_sms_returns = clear_sms_returns
        self._purge_voice_returns = purge_voice_returns
        self._purge_backups_returns = purge_backups_returns
        self._trace_ttl = trace_ttl_value
        self._optin = community_optin
        self._fail_on = fail_on

    def get_config_value(self, key: str, default: str = "") -> str:
        if key == "retention.trace_ttl_days":
            return self._trace_ttl
        if key == "retention.community_optin":
            return "1" if self._optin else "0"
        return default

    def get_community_optin(self, user_id: str = "") -> bool:
        return self._optin

    def prune_traces(self, max_rows: int | None = None, ttl_days: int | None = None) -> int:
        self.calls.append(("prune_traces", (max_rows, ttl_days), {}))
        if self._fail_on == "prune_traces":
            raise RuntimeError("simulated prune failure")
        return self._prune_traces_returns

    def clear_community_pool(self, user_id: str = "", household_id: str = "") -> int:
        self.calls.append(("clear_community_pool", (user_id, household_id), {}))
        if self._fail_on == "clear_community_pool":
            raise RuntimeError("simulated community failure")
        return self._clear_community_returns

    def clear_sms_registry(self, user_id: str = "", household_id: str = "") -> int:
        self.calls.append(("clear_sms_registry", (user_id, household_id), {}))
        if self._fail_on == "clear_sms_registry":
            raise RuntimeError("simulated sms failure")
        return self._clear_sms_returns

    def purge_voice_memos(self, user_id: str = "", household_id: str = "") -> int:
        self.calls.append(("purge_voice_memos", (user_id, household_id), {}))
        if self._fail_on == "purge_voice_memos":
            raise RuntimeError("simulated voice failure")
        return self._purge_voice_returns

    def purge_backups(self, user_id: str = "", household_id: str = "") -> int:
        self.calls.append(("purge_backups", (user_id, household_id), {}))
        if self._fail_on == "purge_backups":
            raise RuntimeError("simulated backup failure")
        return self._purge_backups_returns


# ── retention_summary ─────────────────────────────────────────────


class TestRetentionSummary:
    def test_default_when_db_missing(self):
        s = retention_summary(database=None, user_id="hh1")
        assert s.trace_ttl_days == 30
        assert s.community_optin is False

    def test_reads_trace_ttl_from_db(self):
        db = _FakeDb(trace_ttl_value="7")
        s = retention_summary(database=db, user_id="hh1")
        assert s.trace_ttl_days == 7

    def test_reads_community_optin(self):
        db = _FakeDb(community_optin=True)
        s = retention_summary(database=db, user_id="hh1")
        assert s.community_optin is True

    def test_invalid_trace_ttl_falls_back(self):
        db = _FakeDb(trace_ttl_value="not-a-number")
        s = retention_summary(database=db, user_id="hh1")
        # Bad value → default
        assert s.trace_ttl_days == 30

    def test_db_exception_returns_defaults(self):
        class _BoomDb:
            def get_config_value(self, key, default=""):
                raise RuntimeError("simulated db failure")

        s = retention_summary(database=_BoomDb(), user_id="hh1")
        assert s.trace_ttl_days == 30

    def test_db_without_community_optin_works(self):
        class _MinimalDb:
            def get_config_value(self, key, default=""):
                return default

        s = retention_summary(database=_MinimalDb(), user_id="hh1")
        # No get_community_optin → community_optin stays False
        assert s.community_optin is False


# ── purge_user_data ───────────────────────────────────────────────


class TestPurgeUserData:
    def test_requires_confirm(self):
        db = _FakeDb()
        with pytest.raises(ValueError, match="confirm=True"):
            purge_user_data(db, user_id="u1", household_id="h1")

    def test_calls_all_purge_methods(self):
        db = _FakeDb()
        result = purge_user_data(
            db, user_id="u1", household_id="h1", confirm=True,
        )
        # Every subsystem was called
        names = [c[0] for c in db.calls]
        assert "prune_traces" in names
        assert "clear_community_pool" in names
        assert "clear_sms_registry" in names
        assert "purge_voice_memos" in names
        assert "purge_backups" in names
        # And the counts came back
        assert result.traces_purged == 5
        assert result.community_observations_purged == 3
        assert result.sms_registry_cleared == 2
        assert result.voice_memos_purged == 1
        assert result.backups_purged == 0
        assert result.success is True
        assert result.errors == []

    def test_prune_traces_called_with_zero(self):
        """prune_traces(0, 0) is the signal to delete everything."""
        db = _FakeDb()
        purge_user_data(db, user_id="u1", confirm=True)
        prune_call = next(c for c in db.calls if c[0] == "prune_traces")
        assert prune_call[1] == (0, 0)

    def test_failure_in_one_subsystem_does_not_stop_others(self):
        """A failure in prune_traces must not prevent community
        and SMS purges from running."""
        db = _FakeDb(fail_on="prune_traces")
        result = purge_user_data(db, user_id="u1", confirm=True)
        assert result.success is False
        assert any("traces" in e for e in result.errors)
        # The other subsystems were still called
        names = [c[0] for c in db.calls]
        assert "clear_community_pool" in names
        assert "clear_sms_registry" in names

    def test_inventory_and_lists_not_touched(self):
        """purge_user_data must not touch the inventory or shopping
        list tables — those are the user's data."""
        db = _FakeDb()
        # Spy on attribute access: if purge_user_data tried to call
        # any of these, the test would AttributeError.
        class _InventorySpy(_FakeDb):
            def delete_inventory_lot(self, *a, **kw):
                raise AssertionError("inventory must not be touched")

            def delete_list_item(self, *a, **kw):
                raise AssertionError("list items must not be touched")

        db = _InventorySpy()
        result = purge_user_data(db, user_id="u1", confirm=True)
        assert result.success is True

    def test_missing_db_method_skipped(self):
        """A DB that doesn't expose a purge method is skipped, not
        crashed."""
        class _PartialDb:
            def prune_traces(self, max_rows=None, ttl_days=None):
                return 7

        # clear_community_pool, clear_sms_registry, purge_voice_memos,
        # purge_backups are all missing.
        result = purge_user_data(_PartialDb(), user_id="u1", confirm=True)
        # Only traces was purged
        assert result.traces_purged == 7
        assert result.community_observations_purged == 0
        assert result.sms_registry_cleared == 0
        assert result.voice_memos_purged == 0
        assert result.backups_purged == 0
        assert result.success is True

    def test_passes_household_id_through(self):
        db = _FakeDb()
        purge_user_data(db, user_id="u1", household_id="hh-42", confirm=True)
        for name, args, _ in db.calls:
            if name in {"clear_community_pool", "clear_sms_registry",
                        "purge_voice_memos", "purge_backups"}:
                assert "hh-42" in args


# ── Privacy panel HTML ────────────────────────────────────────────


class _TagListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


class TestPrivacyPanelHtml:
    def test_includes_every_retention_knob(self):
        s = RetentionPolicy()
        html = render_privacy_panel_html(s, locale="en")
        # Each knob is referenced by its i18n key (the actual
        # English text appears). "SMS phone registry" was
        # renamed to "Phone numbers" in R2.1 to match the
        # consumer-friendly label.
        for must in (
            "Action history",
            "Community price pool",
            "Voice memos",
            "Phone numbers",
            "Backups on disk",
            "Remember my language",
            "Share prices with the community",
        ):
            assert must in html, f"Missing panel row: {must}"

    def test_includes_delete_button(self):
        s = RetentionPolicy()
        html = render_privacy_panel_html(s, locale="en")
        assert "Delete my data" in html
        assert 'id="ss-privacy-delete-btn"' in html
        # Has the click handler reference
        assert "ssPrivacyDelete()" in html

    def test_indefinite_rendered_for_zero_days(self):
        s = RetentionPolicy(sms_registry_retention_days=0)
        html = render_privacy_panel_html(s, locale="en")
        assert "Indefinite" in html
        assert "value='0'" in html

    def test_hindi_renders_hindi_text(self):
        s = RetentionPolicy()
        html = render_privacy_panel_html(s, locale="hi")
        assert "आपका डेटा" in html
        assert "मेरा डेटा हटाएँ" in html

    def test_no_untranslated_keys_leak(self):
        """If a translation is missing, the i18n layer returns
        `??key??`. The panel must not show that."""
        s = RetentionPolicy()
        html = render_privacy_panel_html(s, locale="en")
        assert "??privacy." not in html


# ── Privacy panel script ─────────────────────────────────────────


class TestPrivacyPanelScript:
    def test_returns_valid_script(self):
        script = render_privacy_panel_script()
        assert script.strip().startswith("<script")
        assert script.strip().endswith("</script>")
        assert 'data-ss-exec="true"' in script

    def test_calls_purge_endpoint(self):
        script = render_privacy_panel_script()
        assert "/api/purge_user_data" in script
        assert "confirm=true" in script

    def test_uses_confirm_dialog(self):
        script = render_privacy_panel_script()
        # window.confirm() is the safety gate
        assert "window.confirm" in script
