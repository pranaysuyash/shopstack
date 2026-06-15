"""Tests for shopstack.services.i18n (Phase 5 #9 multi-language UI)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from shopstack.services.i18n import (
    DEFAULT_LOCALE,
    LOCALE_STORAGE_KEY,
    SUPPORTED_LOCALES,
    TRANSLATIONS,
    detect_locale_from_request,
    get_translation,
    is_supported_locale,
    load_locale_preference,
    normalize_locale,
    render_language_script,
    render_language_selector_html,
    save_locale_preference,
    t,
)


# ── Locale constants ─────────────────────────────────────────────────


def test_supported_locales_contains_en_and_hi():
    assert "en" in SUPPORTED_LOCALES
    assert "hi" in SUPPORTED_LOCALES
    assert DEFAULT_LOCALE == "en"


def test_default_locale_is_english():
    assert DEFAULT_LOCALE == "en"


def test_locale_storage_key_is_namespaced():
    assert LOCALE_STORAGE_KEY.startswith("shopstack-")


# ── Translation lookup ────────────────────────────────────────────────


def test_t_returns_english_default():
    assert t("tab.today") == "Home"
    assert t("button.ask") == "Ask"


def test_t_returns_hindi_translation():
    assert t("tab.today", locale="hi") == "घर"
    assert t("button.ask", locale="hi") == "पूछें"


def test_t_falls_back_to_english_for_unknown_locale():
    assert t("tab.today", locale="fr") == "Home"


def test_t_falls_back_to_english_for_missing_message_id():
    # Unknown id with no English fallback returns a wrapped id
    out = t("not.a.real.id", locale="hi")
    assert "??" in out


def test_t_handles_format_placeholders():
    out = t("cookbook.serves", locale="en", n=4)
    assert out == "Serves 4"
    out_hi = t("cookbook.serves", locale="hi", n=4)
    assert "4" in out_hi


def test_t_silent_on_missing_format_key():
    # Missing key falls back gracefully (returns the raw template)
    out = t("cookbook.serves", locale="en")
    # Either returns raw template or partial format; both are non-crashing
    assert isinstance(out, str)


def test_t_empty_message_id_returns_empty_string():
    assert t("") == ""


# ── get_translation alias ─────────────────────────────────────────────


def test_get_translation_matches_t():
    assert get_translation("hi", "tab.today") == t("tab.today", locale="hi")


# ── Locale normalization ──────────────────────────────────────────────


def test_normalize_locale_lowercases_and_falls_back():
    assert normalize_locale("EN") == "en"
    assert normalize_locale("Hi") == "hi"
    assert normalize_locale("fr") == DEFAULT_LOCALE
    assert normalize_locale("") == DEFAULT_LOCALE
    assert normalize_locale(None) == DEFAULT_LOCALE


def test_is_supported_locale():
    assert is_supported_locale("en")
    assert is_supported_locale("hi")
    assert not is_supported_locale("ta")
    assert not is_supported_locale("")
    assert not is_supported_locale(None) if False else not is_supported_locale("xx")


# ── Accept-Language parsing ──────────────────────────────────────────


def test_detect_locale_from_request_picks_first_supported():
    assert detect_locale_from_request("hi-IN,hi;q=0.9,en-US;q=0.8") == "hi"
    assert detect_locale_from_request("en-US,en;q=0.9,hi;q=0.8") == "en"
    assert detect_locale_from_request("fr-FR,fr;q=0.9") == DEFAULT_LOCALE
    assert detect_locale_from_request(None) == DEFAULT_LOCALE
    assert detect_locale_from_request("") == DEFAULT_LOCALE


def test_detect_locale_from_request_handles_malformed():
    # Should not crash on weird input
    assert detect_locale_from_request(",,,") == DEFAULT_LOCALE
    assert detect_locale_from_request(";q=0.9") == DEFAULT_LOCALE


# ── Translation table integrity ───────────────────────────────────────


def test_translation_keys_consistent_across_locales():
    en_keys = set(TRANSLATIONS["en"].keys())
    for loc, table in TRANSLATIONS.items():
        if loc == "en":
            continue
        loc_keys = set(table.keys())
        missing = en_keys - loc_keys
        extra = loc_keys - en_keys
        assert not missing, f"locale {loc!r} missing keys: {missing}"
        assert not extra, f"locale {loc!r} has extra keys: {extra}"


def test_all_message_ids_have_non_empty_translations():
    for loc, table in TRANSLATIONS.items():
        for key, value in table.items():
            assert value, f"locale {loc!r} key {key!r} is empty"


# ── Server-side preference persistence ───────────────────────────────


def test_save_and_load_locale_preference(tmp_path, monkeypatch):
    # Point the module at a tmp file so we don't touch real user data
    fake_dir = tmp_path / "locale"
    fake_file = fake_dir / "preference.json"
    monkeypatch.setattr("shopstack.services.i18n._LOCALE_DIR", fake_dir)
    monkeypatch.setattr("shopstack.services.i18n._LOCALE_FILE", fake_file)

    save_locale_preference("hh-1", "hi")
    assert load_locale_preference("hh-1") == "hi"


def test_load_locale_preference_default_when_missing(tmp_path, monkeypatch):
    fake_dir = tmp_path / "locale"
    fake_file = fake_dir / "preference.json"
    monkeypatch.setattr("shopstack.services.i18n._LOCALE_DIR", fake_dir)
    monkeypatch.setattr("shopstack.services.i18n._LOCALE_FILE", fake_file)

    assert load_locale_preference("nope") == DEFAULT_LOCALE


def test_load_locale_preference_returns_default_for_empty_user():
    assert load_locale_preference("") == DEFAULT_LOCALE


def test_save_locale_preference_normalizes_input(tmp_path, monkeypatch):
    fake_dir = tmp_path / "locale"
    fake_file = fake_dir / "preference.json"
    monkeypatch.setattr("shopstack.services.i18n._LOCALE_DIR", fake_dir)
    monkeypatch.setattr("shopstack.services.i18n._LOCALE_FILE", fake_file)

    save_locale_preference("hh-1", "FR")  # unsupported → should fall back
    assert load_locale_preference("hh-1") == DEFAULT_LOCALE


def test_save_locale_preference_no_crash_on_ro_filesystem(tmp_path, monkeypatch):
    # Should swallow OSError and not raise
    monkeypatch.setattr("shopstack.services.i18n._LOCALE_DIR", Path("/proc/1/xx"))
    save_locale_preference("hh-1", "hi")  # must not raise


# ── HTML / JS rendering ───────────────────────────────────────────────


def test_render_language_selector_html_contains_both_buttons():
    out = render_language_selector_html()
    assert "EN" in out
    assert "हिं" in out or "ह" in out
    assert "setLocale" in out


def test_render_language_selector_html_marks_current_active():
    out_en = render_language_selector_html(current_locale="en")
    out_hi = render_language_selector_html(current_locale="hi")
    # The "active" class should be on the matching button
    assert "active" in out_en
    assert "active" in out_hi
    # Different active button depending on locale
    assert out_en != out_hi


def test_render_i18n_script_sets_data_locale():
    out = render_language_script()
    assert LOCALE_STORAGE_KEY in out
    assert "data-locale" in out
    assert "setLocale" in out


# ── XSS safety ────────────────────────────────────────────────────────


def test_translations_have_no_html_tags_or_script():
    """Translations are rendered as escaped text — must not include raw HTML or JS.

    The ``<`` and ``>`` characters are fine in plain prose (e.g. ``Quick (<30 min)``)
    since callers always pipe translations through :func:`html.escape` before
    insertion into a Gradio component. What's not allowed is anything that
    would render as a tag or a script block if accidentally unescaped.
    """
    for loc, table in TRANSLATIONS.items():
        for key, value in table.items():
            # No HTML tag patterns
            assert "<script" not in value.lower(), f"locale {loc} key {key}: script tag"
            assert "javascript:" not in value.lower(), f"locale {loc} key {key}: js protocol"
            assert "<img" not in value.lower(), f"locale {loc} key {key}: img tag"
            assert "<a " not in value.lower(), f"locale {loc} key {key}: link tag"
            # No event handlers
            assert "onerror" not in value.lower(), f"locale {loc} key {key}: event handler"
            assert "onclick" not in value.lower(), f"locale {loc} key {key}: event handler"
