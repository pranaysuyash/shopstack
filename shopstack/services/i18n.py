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
        "toast.undo_done": "Undone.",
        "toast.undo_action": "Undo",
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
        "empty.fallback": "Nothing here yet.",
        # Empty-state presets (used by shopstack.services.empty_states)
        "empty.dashboard.title": "Welcome home",
        "empty.dashboard.body": "Your dashboard is empty. Add your first 5 pantry staples or import a Swiggy receipt to get started.",
        "empty.inventory.title": "Your pantry is empty",
        "empty.inventory.body": "Add items manually or scan a receipt to fill it. We suggest starting with the 5 staples you buy every week.",
        "empty.basket.title": "Plan your first trip",
        "empty.basket.body": "A shopping list helps ShopStack track prices, suggest swaps, and remind you what to buy next.",
        "empty.basket.no_active.title": "No active list",
        "empty.basket.no_active.body": "Create a new list to start comparing prices across stores.",
        "empty.memory.title": "Memory will fill in as you go",
        "empty.memory.body": "Add items, scan a receipt, or record a purchase to start building your household memory.",
        "empty.memory.no_changes.title": "All caught up",
        "empty.memory.no_changes.body": "Nothing changed since the last time you checked. New events will show up here.",
        "empty.find_trail.title": "Find trails build with use",
        "empty.find_trail.body": "After a few uses, ShopStack will remember where you keep things so you can ask 'where's the AA battery charger?' in one tap.",
        "empty.manual_add.title": "Tap the + to add what you bought",
        "empty.manual_add.body": "Use this view while you're at the store to mark items as you pick them up.",
        "empty.reconcile.title": "Reconcile when you get back",
        "empty.reconcile.body": "Scan a receipt, confirm substitutions, and update your pantry in one pass.",
        "empty.fridge.title": "Fridge is empty",
        "empty.fridge.body": "Add what you just bought, or pick from a recent shopping list.",
        "empty.cookbook.title": "Recipes will appear here",
        "empty.cookbook.body": "We suggest meals based on what's expiring and what you buy most often. Add a few staples to your pantry to see suggestions.",
        "empty.search.title": "No results",
        "empty.search.body": "Try a different word, or scan a receipt to add the item to your pantry first.",
        # Empty-state CTAs
        "empty.cta.add_items": "Add your first items",
        "empty.cta.add_first_items": "Add your first 5 staples",
        "empty.cta.import_receipt": "Import a receipt",
        "empty.cta.scan_receipt": "Scan a receipt",
        "empty.cta.create_list": "Create a shopping list",
        # Inline help / tooltips (used by shopstack.services.tooltips)
        "help.lot_id.title": "Lot ID",
        "help.lot_id.body": "A unique tag for each batch of an item you buy. Multiple lots of the same item (e.g. two milk batches) each have their own expiry.",
        "help.batch_syntax.title": "Batch syntax",
        "help.batch_syntax.body": "One line per item, with optional quantity. Separate lot IDs with a colon, e.g. inv-001: 3.",
        "help.expiry_date.title": "Expiry date",
        "help.expiry_date.body": "The best-before date on the package. ShopStack uses this to suggest recipes before items go off.",
        "help.storage_location.title": "Storage location",
        "help.storage_location.body": "Where in the house this lives (fridge, freezer, pantry shelf 2). Pick the most-specific location so the Find Item screen can locate it later.",
        "help.scene_type.title": "Scene type",
        "help.scene_type.body": "What the camera was pointed at. 'Shelf' means a top-down pantry shelf; 'receipt' means a printed receipt; 'basket' means the inside of a shopping basket.",
        "help.receipt_confidence.title": "Receipt confidence",
        "help.receipt_confidence.body": "How sure the OCR model is. 0.9+ is usually right; below 0.7 you may want to double-check the parsed items.",
        "help.community_optin.title": "Community price sharing",
        "help.community_optin.body": "When enabled, the prices you record are anonymously included in a local pool. We strip the user ID and rotate the daily ID so no individual is identifiable.",
        "help.federation_share.title": "Federation bundle",
        "help.federation_share.body": "An export of your anonymised community prices that you can share with another household. Use it to seed a friend's price pool without waiting weeks.",
        "help.sms_phone_registry.title": "SMS phone registry",
        "help.sms_phone_registry.body": "ShopStack will only respond to SMS messages from the numbers you register. Adding a number here is required before you can use the quick-add webhook.",
        "help.voice_memo_retention.title": "Voice memo retention",
        "help.voice_memo_retention.body": "How long voice memos are kept before automatic deletion. We default to 7 days — long enough to act on a reminder, short enough to protect your privacy.",
        "help.backup_format.title": "Backup format",
        "help.backup_format.body": "We export to JSON Lines (one record per line) for portability. The file contains your full household state, including inventory, lists, recipes, and preferences.",
        "help.backup_restore.title": "Backup restore",
        "help.backup_restore.body": "Restore overwrites your current household state. We strongly recommend exporting a fresh backup first so you can roll back.",
        "help.trace_retention.title": "Trace retention",
        "help.trace_retention.body": "How long we keep the audit log of actions (add, consume, move, scan, parse). Default 30 days. Shorter is more private; longer helps diagnostics.",
        "help.household_role.title": "Household role",
        "help.household_role.body": "Owner: full control including adding members. Editor: can add, consume, and move items. Viewer: read-only. There must always be at least one owner.",
        "help.actor_id.title": "Actor ID",
        "help.actor_id.body": "Which household member did this action. Used for per-member analytics ('who added the most items?') and for the activity log.",
        "help.cook_tonight.title": "Cook Tonight",
        "help.cook_tonight.body": "Recipes that use what you already have and is about to expire. Ranked by how many of your use-soon items they consume.",
        "help.global_search.title": "Global search",
        "help.global_search.body": "Search inventory, lists, recipes, and traces from one box. Press Enter to jump to the first result.",
        "help.search_syntax.title": "Search syntax",
        "help.search_syntax.body": "By default, plain text searches everything. Use prefixes to scope: prefix:milk, type:recipe, household:guest.",
        # Global search palette (used by shopstack.services.global_search)
        "search.placeholder": "Search items, lists, recipes, or run a command",
        "search.status_idle": "Type to search",
        # Privacy / data retention panel
        "privacy.title": "Your data",
        "privacy.subtitle": "How long we keep each piece of your data, and how to delete it.",
        "privacy.trace_ttl": "Action history",
        "privacy.community_retention": "Community price pool",
        "privacy.voice_memo_retention": "Voice memos",
        "privacy.sms_retention": "SMS phone registry",
        "privacy.backup_retention": "Backups on disk",
        "privacy.locale_persistence": "Remember my language",
        "privacy.community_optin": "Share prices with the community",
        "privacy.delete_data": "Delete my data",
        "privacy.delete_warning": "This deletes traces, community pool, voice memos, SMS registry, and backups. Your inventory and lists are kept.",
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
        "toast.undo_done": "पूर्ववत किया गया।",
        "toast.undo_action": "पूर्ववत करें",
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
        "empty.fallback": "अभी यहाँ कुछ नहीं है।",
        # Empty-state presets (used by shopstack.services.empty_states)
        "empty.dashboard.title": "घर पर स्वागत है",
        "empty.dashboard.body": "आपका डैशबोर्ड खाली है। पहले 5 स्टेपल जोड़ें या स्विगी रसीद इम्पोर्ट करें।",
        "empty.inventory.title": "आपका पैंट्री खाली है",
        "empty.inventory.body": "सामान मैन्युअली जोड़ें या रसीद स्कैन करें। हफ्ते में 5 स्टेपल से शुरू करें।",
        "empty.basket.title": "पहली यात्रा प्लान करें",
        "empty.basket.body": "शॉपिंग लिस्ट से कीमत ट्रैक होती है, स्वैप सुझाव मिलते हैं, अगली खरीद याद रहती है।",
        "empty.basket.no_active.title": "कोई सक्रिय लिस्ट नहीं",
        "empty.basket.no_active.body": "नई लिस्ट बनाकर शुरू करें।",
        "empty.memory.title": "मेमोरी धीरे-धीरे भरेगी",
        "empty.memory.body": "आइटम जोड़ें, रसीद स्कैन करें, खरीद रिकॉर्ड करें।",
        "empty.memory.no_changes.title": "सब अप-टू-डेट",
        "empty.memory.no_changes.body": "पिछली बार से कुछ नहीं बदला। नए इवेंट यहाँ दिखेंगे।",
        "empty.find_trail.title": "खोज इतिहास बनता रहेगा",
        "empty.find_trail.body": "कुछ बार इस्तेमाल के बाद, ShopStack को याद रहेगा कि चीज़ें कहाँ रखी हैं।",
        "empty.manual_add.title": "जो खरीदा वो + से जोड़ें",
        "empty.manual_add.body": "दुकान में रहते हुए यहाँ जोड़ें।",
        "empty.reconcile.title": "घर आकर रिकॉन्साइल करें",
        "empty.reconcile.body": "रसीद स्कैन करें, स्वैप कन्फर्म करें, पैंट्री अपडेट करें।",
        "empty.fridge.title": "फ्रिज खाली है",
        "empty.fridge.body": "अभी जो खरीदा वो जोड़ें या पिछली लिस्ट से चुनें।",
        "empty.cookbook.title": "रेसिपी यहाँ दिखेंगी",
        "empty.cookbook.body": "हम सुझाव देते हैं — क्या खत्म हो रहा है, क्या अक्सर खरीदते हैं।",
        "empty.search.title": "कुछ नहीं मिला",
        "empty.search.body": "कोई दूसरा शब्द आज़माएँ या पहले रसीद स्कैन करें।",
        # Empty-state CTAs
        "empty.cta.add_items": "पहले आइटम जोड़ें",
        "empty.cta.add_first_items": "पहले 5 स्टेपल जोड़ें",
        "empty.cta.import_receipt": "रसीद इम्पोर्ट करें",
        "empty.cta.scan_receipt": "रसीद स्कैन करें",
        "empty.cta.create_list": "शॉपिंग लिस्ट बनाएँ",
        # Inline help / tooltips (used by shopstack.services.tooltips)
        "help.lot_id.title": "लॉट आईडी",
        "help.lot_id.body": "हर खरीदी गई बैच के लिए एक यूनिक टैग। एक ही आइटम के कई लॉट (जैसे दूध के दो पैकेट) के अपने-अपने एक्सपायरी होते हैं।",
        "help.batch_syntax.title": "बैच सिंटैक्स",
        "help.batch_syntax.body": "हर आइटम एक लाइन में। लॉट आईडी के साथ मात्रा: inv-001: 3।",
        "help.expiry_date.title": "एक्सपायरी डेट",
        "help.expiry_date.body": "पैकेट पर बेस्ट-बिफोर डेट। इससे रेसिपी सुझाव मिलते हैं।",
        "help.storage_location.title": "स्टोरेज लोकेशन",
        "help.storage_location.body": "घर में कहाँ रखा है (फ्रिज, फ्रीजर, पैंट्री शेल्फ 2)।",
        "help.scene_type.title": "सीन टाइप",
        "help.scene_type.body": "कैमरा किस चीज़ पर था। 'शेल्फ' = पैंट्री, 'रसीद' = प्रिंटेड रसीद, 'बास्केट' = शॉपिंग बास्केट।",
        "help.receipt_confidence.title": "रसीद कॉन्फिडेंस",
        "help.receipt_confidence.body": "OCR मॉडल कितना कॉन्फिडेंट है। 0.9+ आमतौर पर सही; 0.7 से नीचे दोबारा जाँचें।",
        "help.community_optin.title": "कम्युनिटी प्राइस शेयरिंग",
        "help.community_optin.body": "चालू होने पर, आपकी कीमतें स्थानीय पूल में जुड़ती हैं। यूज़र आईडी हटा दी जाती है।",
        "help.federation_share.title": "फेडरेशन बंडल",
        "help.federation_share.body": "अनॉनिमाइज़्ड प्राइसेस का एक्सपोर्ट। दूसरे घर के पूल को सीड करने के लिए उपयोगी।",
        "help.sms_phone_registry.title": "SMS फ़ोन रजिस्ट्री",
        "help.sms_phone_registry.body": "ShopStack सिर्फ रजिस्टर्ड नंबरों से मैसेज स्वीकार करेगा।",
        "help.voice_memo_retention.title": "वॉइस मेमो रिटेंशन",
        "help.voice_memo_retention.body": "वॉइस मेमो कितने दिन रखी जाए। डिफ़ॉल्ट 7 दिन।",
        "help.backup_format.title": "बैकअप फ़ॉर्मेट",
        "help.backup_format.body": "हम JSON Lines में एक्सपोर्ट करते हैं — हर रिकॉर्ड एक लाइन।",
        "help.backup_restore.title": "बैकअप रिस्टोर",
        "help.backup_restore.body": "रिस्टोर वर्तमान स्थिति को बदल देता है। पहले एक ताज़ा बैकअप लें।",
        "help.trace_retention.title": "ट्रेस रिटेंशन",
        "help.trace_retention.body": "ऑडिट लॉग कितने दिन रखा जाए। डिफ़ॉल्ट 30 दिन।",
        "help.household_role.title": "घर की भूमिका",
        "help.household_role.body": "ओनर: पूरा अधिकार। एडिटर: जोड़/उपयोग/स्थानांतरण। व्यूअर: केवल देखें। कम से कम एक ओनर ज़रूरी।",
        "help.actor_id.title": "एक्टर आईडी",
        "help.actor_id.body": "किस सदस्य ने यह क्रिया की। पर-मेंबर एनालिटिक्स के लिए।",
        "help.cook_tonight.title": "आज क्या बनाएं",
        "help.cook_tonight.body": "वे रेसिपी जो आपके पास हैं और जल्दी खत्म हो रहा है।",
        "help.global_search.title": "ग्लोबल सर्च",
        "help.global_search.body": "इन्वेंटरी, लिस्ट, रेसिपी, ट्रेस — एक बॉक्स से।",
        "help.search_syntax.title": "सर्च सिंटैक्स",
        "help.search_syntax.body": "डिफ़ॉल्ट से सब सर्च होता है। स्कोप: prefix:milk, type:recipe।",
        # Global search palette
        "search.placeholder": "आइटम, लिस्ट, रेसिपी सर्च करें या कमांड चलाएँ",
        "search.status_idle": "सर्च के लिए टाइप करें",
        # Privacy / data retention panel
        "privacy.title": "आपका डेटा",
        "privacy.subtitle": "हम आपका डेटा कब तक रखते हैं, और कैसे हटाएँ।",
        "privacy.trace_ttl": "एक्शन हिस्ट्री",
        "privacy.community_retention": "कम्युनिटी प्राइस पूल",
        "privacy.voice_memo_retention": "वॉइस मेमो",
        "privacy.sms_retention": "SMS फ़ोन रजिस्ट्री",
        "privacy.backup_retention": "डिस्क पर बैकअप",
        "privacy.locale_persistence": "मेरी भाषा याद रखें",
        "privacy.community_optin": "कम्युनिटी के साथ कीमतें साझा करें",
        "privacy.delete_data": "मेरा डेटा हटाएँ",
        "privacy.delete_warning": "यह ट्रेस, कम्युनिटी पूल, वॉइस मेमो, SMS रजिस्ट्री, बैकअप हटा देगा। इन्वेंटरी और लिस्ट रहेंगी।",
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
            f"<button class='locale-btn{active}' onclick=\"setLocale('{loc}')\" "
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
<script data-ss-exec="true">
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
