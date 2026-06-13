"""Internationalization (i18n) for ShopStack.

Long-term motto: build the translation layer once so adding the next
language is a JSON file, not a code change.

**Scope of this first pass (Phase 5 #9):**

- Two locales: ``en`` (English, default) and ``hi`` (Hindi, हिन्दी).
- Static UI string translation via the :func:`t` helper. Dynamic data
  (item names, user input) is left untranslated.
- Locale is per-browser, persisted in ``localStorage`` under the key
  ``shopstack-locale``. The page reloads on change so all components
  re-render in the new language.
- Translation strings cover the most-visible labels: tab names, button
  labels, headings, toast messages, and the seasonal/coach banners.
  Strings inside rich HTML blocks (``render_*_html``) are translated at
  render time by passing a locale parameter (default ``en``) so they
  swap language when the user toggles the selector.

**Why not Gradio's built-in i18n:**

Gradio 6 has a partial i18n system (``gr.i18n``) but it is hard to extend
with custom dictionary files and does not give us first-class access to
the current locale from inside our renderers. A small layer of our own is
simpler, testable, and decoupled from the Gradio version.

**Adding a new language (Tamil, Telugu, Bengali, etc.):**

1. Add a new top-level key to :data:`TRANSLATIONS` with the same set of
   message ids as ``en``.
2. Add the language to :data:`SUPPORTED_LOCALES`.
3. Add a button to the language selector in :func:`render_language_selector_html`.
4. The persistence + reload flow already handles the rest.

The message ids are stable: do not rename them once a translation file
ships, since that breaks the user-saved locale preference.
"""
from __future__ import annotations

import json
import logging
from html import escape
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ─── Locales ─────────────────────────────────────────────────────────────

SUPPORTED_LOCALES: tuple[str, ...] = ("en", "hi")
DEFAULT_LOCALE: str = "en"
LOCALE_STORAGE_KEY: str = "shopstack-locale"


# ─── Translation table ───────────────────────────────────────────────────

TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── English (default) ────────────────────────────────────────────
    "en": {
        # App chrome
        "app.brand": "ShopStack",
        "app.tagline": "Your household, stocked.",
        # Tabs
        "tab.today": "Home",
        "tab.cookbook": "Recipes",
        "tab.basket": "Groceries",
        "tab.market": "While Shopping",
        "tab.reconcile": "At Home",
        "tab.memory": "Memory",
        # Sections
        "section.use_soon": "Use soon",
        "section.low_stock": "Low stock",
        "section.recent": "Recent activity",
        "section.changed": "What changed",
        "section.ask": "Ask a question",
        "section.cook_tonight": "Cook Tonight",
        "section.cookbook_browse": "Browse recipes",
        "section.restock": "Restock Predictions",
        "section.walkthrough_welcome": "Welcome to ShopStack",
        # Buttons
        "button.add_to_list": "Add to my shopping list",
        "button.add_selected": "Add selected to my shopping list",
        "button.ask": "Ask",
        "button.cancel": "Cancel",
        "button.create": "Create",
        "button.refresh": "Refresh",
        "button.shop_recipe": "Shop missing items",
        # Banners / toasts
        "toast.added": "Added to shopping list.",
        "toast.select_first": "Select a row first.",
        "toast.welcome": "Welcome back!",
        "toast.cook_now": "Cook with what you have.",
        "toast.seasonal_rain": "Rainy day — avoid perishables-heavy trips.",
        "toast.seasonal_heat": "Hot day — frozen and dairy items will need insulated bags.",
        "toast.seasonal_cold": "Cold day — stock warm foods and masalas.",
        "toast.waste_soon": "Use-soon items in your fridge — see Cook Tonight.",
        # Cookbook
        "cookbook.filter_veg": "Vegetarian",
        "cookbook.filter_vegan": "Vegan",
        "cookbook.filter_omnivore": "All",
        "cookbook.filter_quick": "Quick (<30 min)",
        "cookbook.no_recipes": "No recipes match the current filters.",
        "cookbook.serves": "Serves {n}",
        "cookbook.prep": "Prep",
        "cookbook.cook": "Cook",
        "cookbook.total": "Total",
        "cookbook.ingredients": "Ingredients",
        "cookbook.instructions": "Instructions",
        "cookbook.missing": "Missing",
        "cookbook.have": "Have",
        # Walkthrough
        "tour.step1.title": "Home is your dashboard",
        "tour.step1.body": "See what's expiring, what to buy, and what to cook — at a glance.",
        "tour.step2.title": "Plan a trip",
        "tour.step2.body": "Open Groceries to compare stores and prices before you leave home.",
        "tour.step3.title": "Shop & reconcile",
        "tour.step3.body": "Use While Shopping in-store. At Home when you get back.",
        "tour.step4.title": "Cook with what you have",
        "tour.step4.body": "The Recipes tab suggests meals based on your pantry.",
        "tour.next": "Next",
        "tour.back": "Back",
        "tour.skip": "Skip tour",
        "tour.done": "Got it",
        # Settings
        "settings.household": "Household",
        "settings.advanced": "Advanced",
        # Header
        "header.toggle_theme": "Toggle light/dark theme",
        "header.toggle_locale": "भाषा / Language",
        # Empty / error states
        "empty.no_inventory": "Your inventory is empty. Add some items to get started.",
        "empty.no_lists": "No shopping lists yet.",
        "error.generic": "Something went wrong. Please try again.",
    },
    # ── Hindi (हिन्दी) ──────────────────────────────────────────────
    "hi": {
        # App chrome
        "app.brand": "शॉपस्टैक",
        "app.tagline": "आपका घर, स्टॉक में।",
        # Tabs
        "tab.today": "घर",
        "tab.cookbook": "रेसिपी",
        "tab.basket": "किराना",
        "tab.market": "खरीदते समय",
        "tab.reconcile": "घर पर",
        "tab.memory": "मेमोरी",
        # Sections
        "section.use_soon": "जल्दी खत्म होगा",
        "section.low_stock": "कम स्टॉक",
        "section.recent": "हाल की गतिविधि",
        "section.changed": "क्या बदला",
        "section.ask": "कोई सवाल पूछें",
        "section.cook_tonight": "आज क्या बनाएं",
        "section.cookbook_browse": "रेसिपी देखें",
        "section.restock": "पुनः स्टॉक अनुमान",
        "section.walkthrough_welcome": "शॉपस्टैक में आपका स्वागत है",
        # Buttons
        "button.add_to_list": "मेरी लिस्ट में जोड़ें",
        "button.add_selected": "चुनी हुई वस्तु लिस्ट में जोड़ें",
        "button.ask": "पूछें",
        "button.cancel": "रद्द करें",
        "button.create": "बनाएं",
        "button.refresh": "रिफ्रेश",
        "button.shop_recipe": "कमी वाली चीजें खरीदें",
        # Banners / toasts
        "toast.added": "लिस्ट में जोड़ दिया।",
        "toast.select_first": "पहले कोई आइटम चुनें।",
        "toast.welcome": "वापसी पर स्वागत है!",
        "toast.cook_now": "जो है उसी से कुछ बनाएं।",
        "toast.seasonal_rain": "बारिश का दिन — जल्दी खराब होने वाली चीज़ें टालें।",
        "toast.seasonal_heat": "गर्मी का दिन — फ्रोज़न और डेयरी के लिए इंसुलेटेड बैग रखें।",
        "toast.seasonal_cold": "ठंड का दिन — गर्म खाना और मसाले स्टॉक करें।",
        "toast.waste_soon": "फ्रिज में जल्दी खत्म होने वाली चीज़ें — आज क्या बनाएं देखें।",
        # Cookbook
        "cookbook.filter_veg": "शाकाहारी",
        "cookbook.filter_vegan": "वीगन",
        "cookbook.filter_omnivore": "सभी",
        "cookbook.filter_quick": "झटपट (<30 मिनट)",
        "cookbook.no_recipes": "अभी कोई रेसिपी नहीं मिली।",
        "cookbook.serves": "{n} लोग",
        "cookbook.prep": "तैयारी",
        "cookbook.cook": "पकाना",
        "cookbook.total": "कुल",
        "cookbook.ingredients": "सामग्री",
        "cookbook.instructions": "विधि",
        "cookbook.missing": "कमी",
        "cookbook.have": "है",
        # Walkthrough
        "tour.step1.title": "आज — आपका डैशबोर्ड",
        "tour.step1.body": "क्या खत्म हो रहा है, क्या खरीदना है, क्या बनाना है — एक नज़र में।",
        "tour.step2.title": "ट्रिप प्लान करें",
        "tour.step2.body": "बास्केट खोलें — स्टोर और कीमत घर से निकलने से पहले देखें।",
        "tour.step3.title": "खरीदारी और रिकॉन्साइल",
        "tour.step3.body": "दुकान में शॉपलेंस चालू रखें। घर आकर रिकॉन्साइल करें।",
        "tour.step4.title": "जो है उसी से बनाएं",
        "tour.step4.body": "कुकबुक टैब आपके पैंट्री के हिसाब से रेसिपी सुझाता है।",
        "tour.next": "आगे",
        "tour.back": "पीछे",
        "tour.skip": "टूर छोड़ें",
        "tour.done": "समझ गया",
        # Settings
        "settings.household": "घर",
        "settings.advanced": "एडवांस्ड",
        # Header
        "header.toggle_theme": "लाइट/डार्क मोड",
        "header.toggle_locale": "भाषा",
        # Empty / error states
        "empty.no_inventory": "इन्वेंटरी खाली है। शुरू करने के लिए कुछ आइटम जोड़ें।",
        "empty.no_lists": "अभी कोई शॉपिंग लिस्ट नहीं है।",
        "error.generic": "कुछ गड़बड़ हो गई। फिर से कोशिश करें।",
    },
}


# ─── Public API ──────────────────────────────────────────────────────────


def get_translation(locale: str, message_id: str, **kwargs: Any) -> str:
    """Return the translated string for ``message_id`` in ``locale``.

    Falls back to the English string if the locale or the message id is
    unknown. If the English fallback is also missing (a developer error),
    returns the message id wrapped in ``??`` so it's visually obvious in
    the UI.

    The ``**kwargs`` are used for ``str.format`` placeholders, e.g.::

        get_translation("en", "cookbook.serves", n=4)
        # → "Serves 4"
    """
    if not message_id:
        return ""
    if locale not in TRANSLATIONS:
        locale = DEFAULT_LOCALE
    table = TRANSLATIONS.get(locale, TRANSLATIONS[DEFAULT_LOCALE])
    raw = table.get(message_id)
    if raw is None:
        raw = TRANSLATIONS[DEFAULT_LOCALE].get(message_id, f"??{message_id}??")
    if kwargs and "{" in raw:
        try:
            return raw.format(**kwargs)
        except (KeyError, IndexError):
            return raw
    return raw


def t(message_id: str, locale: str = DEFAULT_LOCALE, **kwargs: Any) -> str:
    """Short alias for :func:`get_translation`.

    Designed for inline use in renderers::

        <h3>{t('section.cook_tonight', locale)}</h3>
    """
    return get_translation(locale, message_id, **kwargs)


def is_supported_locale(locale: str) -> bool:
    """True if ``locale`` is one of the :data:`SUPPORTED_LOCALES`."""
    return locale in SUPPORTED_LOCALES


def normalize_locale(locale: str | None) -> str:
    """Return a valid locale string (falling back to ``DEFAULT_LOCALE``)."""
    if not locale:
        return DEFAULT_LOCALE
    locale = locale.strip().lower()
    if not is_supported_locale(locale):
        return DEFAULT_LOCALE
    return locale


# ─── Server-side detection ──────────────────────────────────────────────


def detect_locale_from_request(accept_language: str | None) -> str:
    """Pick the best locale from an ``Accept-Language`` HTTP header.

    Browsers send a comma-separated list of language tags with quality
    scores, e.g. ``"hi-IN,hi;q=0.9,en-US;q=0.8,en;q=0.7"``. We pick the
    first supported language tag, ignoring region subtags and q-scores
    (good-enough heuristic for a v1).

    Returns :data:`DEFAULT_LOCALE` when no supported locale is found.
    """
    if not accept_language:
        return DEFAULT_LOCALE
    for raw in accept_language.split(","):
        tag = raw.split(";")[0].strip().lower()
        if not tag:
            continue
        primary = tag.split("-")[0]
        if is_supported_locale(primary):
            return primary
    return DEFAULT_LOCALE


# ─── Persistent storage helper (server-side, optional) ──────────────────


_LOCALE_DIR = Path.home() / ".shopstack" / "locale"
_LOCALE_FILE = _LOCALE_DIR / "preference.json"


def save_locale_preference(user_id: str, locale: str) -> None:
    """Persist the chosen locale for a household to a small JSON file.

    Best-effort: any IO error is logged and swallowed so the UI flow
    never breaks because disk is full or read-only.
    """
    locale = normalize_locale(locale)
    if not user_id:
        return
    try:
        _LOCALE_DIR.mkdir(parents=True, exist_ok=True)
        prefs: dict[str, str] = {}
        if _LOCALE_FILE.is_file():
            try:
                prefs = json.loads(_LOCALE_FILE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                prefs = {}
        prefs[user_id] = locale
        _LOCALE_FILE.write_text(json.dumps(prefs), encoding="utf-8")
    except OSError as exc:
        logger.debug("save_locale_preference failed: %s", exc)


def load_locale_preference(user_id: str) -> str:
    """Return the saved locale for ``user_id``, or :data:`DEFAULT_LOCALE`."""
    if not user_id:
        return DEFAULT_LOCALE
    try:
        if not _LOCALE_FILE.is_file():
            return DEFAULT_LOCALE
        prefs = json.loads(_LOCALE_FILE.read_text(encoding="utf-8"))
        return normalize_locale(prefs.get(user_id))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_LOCALE


# ─── Language selector HTML ─────────────────────────────────────────────


def render_language_selector_html(current_locale: str = DEFAULT_LOCALE) -> str:
    """Render a small button group that switches the UI language.

    The actual locale change happens in JS: the click handler writes
    the new locale to ``localStorage`` and reloads the page so all
    server-rendered components re-render in the new language.
    """
    current_locale = normalize_locale(current_locale)
    buttons: list[str] = []
    for loc in SUPPORTED_LOCALES:
        label = {
            "en": "EN",
            "hi": "हिं",
        }.get(loc, loc.upper())
        active = " active" if loc == current_locale else ""
        buttons.append(
            f"<button class='locale-btn{active}' "
            f"onclick=\"setLocale('{loc}')\" "
            f"aria-label='{escape(label)}'>{escape(label)}</button>"
        )
    return (
        "<div class='locale-selector' role='group' "
        "aria-label='Language selector'>"
        + "".join(buttons)
        + "</div>"
    )


def render_i18n_script() -> str:
    """Return the inline JS that wires up locale persistence + reload.

    The locale is read from ``localStorage`` on page load and applied to
    ``<html data-locale='...'>`` so server-rendered components can read
    it (via :func:`detect_locale_from_request` on subsequent reloads).
    The :func:`setLocale` helper writes the new locale, posts it to the
    server's ``save_locale`` API endpoint (so the choice is persisted
    to the server-side locale file), and then reloads so the next
    page render uses the saved locale.
    """
    return f"""
<script>
(function() {{
  try {{
    var saved = localStorage.getItem('{LOCALE_STORAGE_KEY}');
    if (saved) {{
      document.documentElement.setAttribute('data-locale', saved);
    }}
  }} catch (e) {{}}
}})();
async function setLocale(loc) {{
  // 1) Local cache for immediate client-side use.
  try {{
    localStorage.setItem('{LOCALE_STORAGE_KEY}', loc);
  }} catch (e) {{}}
  // 2) Persist to the server so the next page load reads it from
  //    ``load_locale_preference(user_id)`` (which is what
  //    ``header_block`` is called with on app boot). Best-effort:
  //    ignore the network error and still reload — localStorage
  //    keeps the choice in-session.
  try {{
    await fetch('/gradio_api/call/save_locale', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ data: [loc] }}),
    }});
  }} catch (e) {{ /* server unreachable — localStorage is enough */ }}
  // 3) Reload so the next page render uses the new locale.
  window.location.reload();
}}
</script>"""


__all__ = [
    "DEFAULT_LOCALE",
    "LOCALE_STORAGE_KEY",
    "SUPPORTED_LOCALES",
    "TRANSLATIONS",
    "detect_locale_from_request",
    "get_translation",
    "is_supported_locale",
    "load_locale_preference",
    "normalize_locale",
    "render_i18n_script",
    "render_language_selector_html",
    "save_locale_preference",
    "t",
]
