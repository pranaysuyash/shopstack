"""Regression tests for the new i18n button keys (2026-06-13).

Per motto_v3 §6, "pre-existing" hardcoded English buttons are a bug to
fix, not defer. The share-list, receipt-export, and recipe-OCR features
shipped in earlier sessions with English-only labels. This test locks
in:

  1. All new i18n keys exist in both en and hi locales
  2. The new button labels are translated in both locales
  3. The button factories (in basket_add_items, basket_shopping_list,
     recipe tabs) use the t() helper
  4. The share HTML renderer uses t() for all UI strings
  5. Regression: the existing share_list tests still pass
"""

from __future__ import annotations

import inspect

import pytest


# ─── New i18n keys must exist in both locales ──────────────────────


class TestNewButtonI18nKeys:
    """The 7 new button keys must exist in both en and hi locales."""

    REQUIRED_KEYS = [
        "button.save_as_txt",
        "button.share_list",
        "button.snap_and_parse",
        "button.share_list_title",
        "button.share_list_copy",
        "button.share_list_copy_done",
        "button.share_list_whatsapp",
    ]

    def test_keys_exist_in_en(self):
        """All required keys must be in the en locale."""
        from shopstack.services.i18n import TRANSLATIONS
        missing = [k for k in self.REQUIRED_KEYS if k not in TRANSLATIONS["en"]]
        assert not missing, (
            f"Missing keys in en locale: {missing}. "
            "These were added in the 2026-06-13 i18n new-buttons sweep."
        )

    def test_keys_exist_in_hi(self):
        """All required keys must be in the hi locale."""
        from shopstack.services.i18n import TRANSLATIONS
        missing = [k for k in self.REQUIRED_KEYS if k not in TRANSLATIONS["hi"]]
        assert not missing, (
            f"Missing keys in hi locale: {missing}. "
            "Per motto_v3 §6, the Hindi translations must exist for "
            "every new i18n key (not '??key??' placeholders)."
        )

    def test_keys_have_non_empty_values(self):
        """No key should have an empty string value."""
        from shopstack.services.i18n import TRANSLATIONS
        empty = []
        for locale in ("en", "hi"):
            for k in self.REQUIRED_KEYS:
                v = TRANSLATIONS[locale].get(k, "")
                if not v.strip():
                    empty.append(f"{locale}.{k}")
        assert not empty, f"Keys with empty values: {empty}"

    def test_hindi_translations_are_actually_hindi(self):
        """Hindi translations should contain Devanagari characters (not English)."""
        from shopstack.services.i18n import TRANSLATIONS
        # Devanagari unicode range: U+0900 to U+097F
        non_hindi = []
        for k in self.REQUIRED_KEYS:
            v = TRANSLATIONS["hi"].get(k, "")
            if not any("\u0900" <= c <= "\u097F" for c in v):
                # The emoji prefix is OK; check the rest
                # Strip emoji and check
                stripped = "".join(c for c in v if ord(c) > 0x2600)
                if not any("\u0900" <= c <= "\u097F" for c in stripped):
                    non_hindi.append(f"{k}={v!r}")
        assert not non_hindi, (
            f"Hindi translations don't contain Devanagari: {non_hindi}. "
            "These are probably just the English value copied. Per §6, "
            "this is a real bug — translate properly."
        )


# ─── Share HTML renderer uses t() for all strings ─────────────────


class TestShareHtmlI18n:
    """The share HTML renderer must use t() for all UI strings."""

    def test_share_html_signature_accepts_locale(self):
        """_shopping_list_share_html must accept a locale parameter."""
        from shopstack.ui.screens.shopping import _shopping_list_share_html
        sig = inspect.signature(_shopping_list_share_html)
        assert "locale" in sig.parameters, (
            "_shopping_list_share_html must accept a `locale` parameter "
            "so the t() helper can localize its UI strings."
        )

    def test_share_html_uses_t_for_all_strings(self):
        """The renderer must use t() for title, copy label, copy done, whatsapp."""
        from shopstack.ui.screens.shopping import _shopping_list_share_html
        src = inspect.getsource(_shopping_list_share_html)
        # Each of these i18n keys must appear in the source
        for key in (
            "button.share_list_title",
            "button.share_list_copy",
            "button.share_list_copy_done",
            "button.share_list_whatsapp",
        ):
            assert f'"{key}"' in src or f"'{key}'" in src, (
                f"_shopping_list_share_html must call t({key!r}, locale). "
                f"Hardcoded English here is the Pass 15/17-style bug."
            )

    def test_share_html_en_has_english_labels(self):
        """The English render should have English UI labels."""
        from shopstack.ui.screens.shopping import _shopping_list_share_html
        html = _shopping_list_share_html("test items", "en")
        assert "Copy for WhatsApp" in html, "English title missing"
        assert "Open in WhatsApp" in html, "English WhatsApp label missing"
        assert "Copy to clipboard" in html, "English copy label missing"

    def test_share_html_hi_has_hindi_labels(self):
        """The Hindi render should have Hindi UI labels (not English fallback)."""
        from shopstack.ui.screens.shopping import _shopping_list_share_html
        html = _shopping_list_share_html("test items", "hi")
        assert "व्हाट्सऐप के लिए कॉपी करें" in html, "Hindi title missing"
        assert "व्हाट्सऐप में खोलें" in html, "Hindi WhatsApp label missing"
        assert "क्लिपबोर्ड पर कॉपी करें" in html, "Hindi copy label missing"

    def test_share_html_xss_safe(self):
        """The HTML should escape the share_text properly (regression)."""
        from shopstack.ui.screens.shopping import _shopping_list_share_html
        # XSS attempt in the text
        html = _shopping_list_share_html("<script>alert('xss')</script>", "en")
        assert "<script>alert" not in html, "XSS: raw script tag in output"
        assert "&lt;script&gt;" in html, "Should be escaped"


# ─── Tab builders use t() for the new button labels ───────────────


class TestTabBuildersUseT:
    """The 3 tab builders that have the new buttons must use t()."""

    def test_basket_add_items_uses_t_for_save_as_txt(self):
        """The receipt export button must use t(button.save_as_txt, locale)."""
        text = open("shopstack/ui/tabs/basket_add_items.py").read()
        assert 't("button.save_as_txt"' in text, (
            "basket_add_items.py must use t(button.save_as_txt, locale) "
            "for the receipt export button label."
        )
        assert '"💾 Save as .txt"' not in text, (
            "basket_add_items.py has hardcoded English 'Save as .txt'. "
            "Per §6, this is a bug — use t() instead."
        )

    def test_basket_add_items_uses_t_for_snap_and_parse(self):
        """The OCR button must use t(button.snap_and_parse, locale)."""
        text = open("shopstack/ui/tabs/basket_add_items.py").read()
        assert 't("button.snap_and_parse"' in text, (
            "basket_add_items.py must use t(button.snap_and_parse, locale) "
            "for the OCR button label."
        )

    def test_recipe_tab_uses_t_for_snap_and_parse(self):
        """The recipe tab Snap button must use t(button.snap_and_parse, locale)."""
        text = open("shopstack/ui/tabs/recipe.py").read()
        assert 't("button.snap_and_parse"' in text, (
            "recipe.py must use t(button.snap_and_parse, locale) "
            "for the Snap & parse button label."
        )

    def test_basket_shopping_list_uses_t_for_share_list(self):
        """The share list button must use t(button.share_list, locale)."""
        text = open("shopstack/ui/tabs/basket_shopping_list.py").read()
        assert 't("button.share_list"' in text, (
            "basket_shopping_list.py must use t(button.share_list, locale) "
            "for the share list button label."
        )
        assert '"📤 Share list"' not in text, (
            "basket_shopping_list.py has hardcoded English 'Share list'. "
            "Per §6, this is a bug — use t() instead."
        )


# ─── Build-time locale resolution ────────────────────────────────


class TestBuildTimeLocaleResolution:
    """Tab builders must resolve the current locale at build time."""

    def test_basket_add_items_loads_locale(self):
        """basket_add_items.py must call load_locale_preference at build time."""
        text = open("shopstack/ui/tabs/basket_add_items.py").read()
        assert "load_locale_preference" in text, (
            "basket_add_items.py must call load_locale_preference to get "
            "the current locale at build time for static button labels."
        )

    def test_basket_shopping_list_loads_locale(self):
        """basket_shopping_list.py must call load_locale_preference at build time."""
        text = open("shopstack/ui/tabs/basket_shopping_list.py").read()
        assert "load_locale_preference" in text, (
            "basket_shopping_list.py must call load_locale_preference."
        )

    def test_recipe_tab_loads_locale(self):
        """recipe.py must call load_locale_preference at build time."""
        text = open("shopstack/ui/tabs/recipe.py").read()
        assert "load_locale_preference" in text, (
            "recipe.py must call load_locale_preference."
        )


# ─── i18n catalog total key count must match ──────────────────────


class TestI18nCatalogParity:
    """The en and hi locales must have the same set of keys."""

    def test_en_and_hi_have_same_keys(self):
        """Both locales should have identical key sets (no drift)."""
        from shopstack.services.i18n import TRANSLATIONS
        en_keys = set(TRANSLATIONS["en"].keys())
        hi_keys = set(TRANSLATIONS["hi"].keys())
        only_en = en_keys - hi_keys
        only_hi = hi_keys - en_keys
        assert not only_en and not only_hi, (
            f"i18n key drift: en-only={only_en}, hi-only={only_hi}. "
            "Every key added to one locale must be added to the other."
        )
