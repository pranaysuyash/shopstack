"""Module registry — single source of truth for ShopStack module metadata.

Each ShopStack module (ShopStock, ShopBasket, ShopCompare, etc.) registers its
name, slug, description, tab IDs, key service paths, and dependencies here.
Any UI surface that needs module metadata imports from this registry instead of
hardcoding strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModuleMetadata:
    """Metadata for a single ShopStack module.

    This is the canonical source for all module-level information.
    Any UI surface that needs a module name, tab label, description,
    or navigation order should read it from here — never hardcode it.

    Attributes:
        slug: Short machine-friendly identifier (e.g. \"stock\", \"basket\").
        name: Human-readable module name (e.g. \"ShopStock\").
        label: Short UI label for the module itself (e.g. \"My Stock\").
        description: One-line summary of the module's purpose.
        tab_ids: Gradio tab IDs associated with this module.
        tab_labels: Canonical display labels keyed by tab_id.
                     If a tab_id is missing here, the module's ``label`` is used.
                     Example: tab_labels={"inventory": "Find Item at Home", "purchase": "Add Purchase"}
        order: Display order in the UI navigation bar (lower = earlier).
        service_modules: Python module paths providing this module's logic.
        depends_on: Slugs of modules this module typically depends on.
        is_source: Whether this module is a retailer/source adapter.
    """
    slug: str
    name: str
    label: str
    description: str
    tab_ids: tuple[str, ...] = ()
    tab_labels: dict[str, str] = field(default_factory=dict)
    order: int = 999
    service_modules: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    is_source: bool = False

    def tab_label(self, tab_id: str) -> str:
        """Return the canonical display label for a given tab_id.

        Falls back to ``self.label`` if no per-tab label is registered.
        """
        return self.tab_labels.get(tab_id, self.label)


__all__ = [
    "ModuleMetadata",
    "SHOPSTOCK",
    "SHOPBASKET",
    "SHOPCOMPARE",
    "SHOPLENS",
    "SHOPMEMORY",
    "SHOPAGENT",
    "SOURCES",
    "RUNTIME",
    "SHOPNUTRITION",
    "SHOPTIMELINE",
    "get_all",
    "get_by_slug",
    "get_by_tab_id",
    "TAB_ORDER",
    "TAB_LABELS",
    "TAB_GROUPS",
    "GROUP_LABELS",
    "GROUP_ORDER",
    "get_tab_ids",
    "tab_order",
    "tab_label",
    "group_order",
    "group_tab_ids",
    "group_label",
    "navigation",
    "module_dependencies",
    "summary_table",
]


# ── Registry ─────────────────────────────────────────────────────────

_MODULES: dict[str, ModuleMetadata] = {}


def _register(m: ModuleMetadata) -> ModuleMetadata:
    """Register a module and index it by slug."""
    _MODULES[m.slug] = m
    return m


# ── Tab groups ──────────────────────────────────────────────────────
#
# The Gradio tab bar uses a nested structure: 5 top-level module-group tabs
# each containing their respective screen tabs as sub-tabs. This grouping
# is module-aligned and avoids single-screen groups that would add
# unnecessary clicks (motto_v3 §11, §12).
#
# Each group maps to a list of screen tab_ids that appear inside it.
# Order within each group follows TAB_ORDER.

TAB_GROUPS: dict[str, list[str]] = {
    "home":       ["today", "cookbook", "trip_advisor"],
    "groceries": ["basket", "smart_basket", "store_mode"],
    "shopping":  ["market", "scanner", "recipe", "market_intel"],
    "at_home":   ["reconcile", "timeline", "find_trail", "photo_map",
                    "repair_inbox", "consumption", "nutrition"],
    "memory":    ["memory", "community", "parser", "analytics"],
}

# Display labels for each group tab.
GROUP_LABELS: dict[str, str] = {
    "home":       "Home",
    "groceries": "Groceries",
    "shopping":  "Shopping",
    "at_home":   "At Home",
    "memory":    "Memory",
}

# Display order for each group (lower = earlier in the tab bar).
GROUP_ORDER: dict[str, int] = {
    "home":       10,
    "groceries":  20,
    "shopping":   30,
    "at_home":    40,
    "memory":     50,
}


# ── Tab order map ──────────────────────────────────────────────────

# This is the canonical ordering for the Gradio tab bar within each group.
# Every tab that appears in the UI must have an entry here.
# Order = explicit integer; lower values appear first.
#
# Adding a new tab: add it here with the position where it should appear.
# The `order` field on each ModuleMetadata auto-aligns via the module's
# lowest-order tab, but this dict is the single source of truth for the
# actual tab bar sequence.
TAB_ORDER: dict[str, int] = {
    "today":         10,
    "cookbook":      20,
    "basket":        30,
    "market_intel":  35,
    "trip_advisor":  37,
    "market":        40,
    "scanner":       44,
    "photo_map":     46,
    "reconcile":     50,
    "timeline":      55,
    "find_trail":    56,
    "store_mode":    57,
    "memory":        60,
    "nutrition":     65,
    "smart_basket":  67,
    "analytics":     68,
    "repair_inbox":  70,
    "consumption":   72,
    "recipe":        74,
    "parser":        76,
    "community":     78,
}

# ── Tab display labels ────────────────────────────────────────────
# Canonical display names for every UI tab.
# A module's `tab_labels` dict overrides these for module-specific labels.
TAB_LABELS: dict[str, str] = {
    "today":         "Today",
    "cookbook":      "Recipes",
    "basket":        "Shopping List",
    "market_intel":  "Market Intel",
    "trip_advisor":  "Trip Plans",
    "market":        "While Shopping",
    "scanner":       "Shelf Scan",
    "photo_map":     "Photo Map",
    "reconcile":     "Overview",
    "timeline":      "Timeline",
    "find_trail":    "Find",
    "store_mode":    "Store Mode",
    "memory":        "System",
    "nutrition":     "Nutrition",
    "smart_basket":  "Smart Basket",
    "analytics":     "Analytics",
    "repair_inbox":  "Repair Inbox",
    "consumption":   "Consumption",
    "recipe":        "Recipe Scan",
    "parser":        "Parser Test",
    "community":     "Community",
}


# ── Module definitions ───────────────────────────────────────────────
#
# Each module registers with:
#   - slug:          machine-friendly ID
#   - name:          canonical module name
#   - label:         short UI label for the module itself
#   - tab_labels:    per-tab display labels (override TAB_LABELS)
#   - order:         display priority (auto-derived from TAB_ORDER)
#   - tab_ids:       which Gradio tab IDs belong to this module
#   - service_modules: Python paths implementing the module
#   - depends_on:    module slugs this module depends on

SHOPSTOCK = _register(ModuleMetadata(
    slug="stock",
    name="ShopStock",
    label="At Home",
    description=(
        "Inventory, pantry, fridge, expiry, low-stock, use-soon, "
        "household storage, object trail (find), unified timeline, "
        "photo-anchored map, and condition/damage detection."
    ),
    tab_ids=("reconcile", "timeline", "photo_map", "find_trail", "repair_inbox", "consumption"),
    tab_labels={
        "reconcile": "At Home",
        "photo_map": "Photo Map",
        "find_trail": "Find",
        "repair_inbox": "Repair Inbox",
        "consumption": "Consumption",
    },
    order=TAB_ORDER.get("reconcile", 999),
    service_modules=(
        "shopstack.ui.screens.inventory",
        "shopstack.ui.screens.portability",
        "shopstack.portability",
        # Spatial memory & findability core (2026-06-14)
        "shopstack.services.find",
        "shopstack.ui.screens.find_trail",
        "shopstack.services.timeline",
        "shopstack.ui.screens.timeline",
        "shopstack.services.photo_search",
        "shopstack.ui.screens.photo_map",
        "shopstack.services.condition",
        "shopstack.ui.screens.repair_inbox",
        "shopstack.schemas.condition",
    ),
))

SHOPBASKET = _register(ModuleMetadata(
    slug="basket",
    name="ShopBasket",
    label="Groceries",
    description="Shopping list creation, decision classification (buy/skip/use-soon), cart planning, and market basket optimization.",
    tab_ids=("basket", "cookbook", "store_mode", "smart_basket", "recipe"),
    tab_labels={
        "basket": "Groceries",
        "cookbook": "Recipes",
        "store_mode": "Store Mode",
        "smart_basket": "Smart Basket",
        "recipe": "Recipe Scan",
    },
    order=TAB_ORDER.get("basket", 999),
    service_modules=(
        "shopstack.services.shopping",
        "shopstack.ui.screens.shopping",
    ),
    depends_on=("stock",),
))

SHOPCOMPARE = _register(ModuleMetadata(
    slug="compare",
    name="ShopCompare",
    label="Price Check",
    description="Retailer price comparison, unit price normalization, price-drop alerts, best-store recommendations, and community price sharing.",
    tab_ids=("basket", "community"),
    tab_labels={"basket": "Groceries", "community": "Community"},
    order=TAB_ORDER.get("basket", 999),
    service_modules=(
        "shopstack.market",
        "shopstack.market.analytics",
        "shopstack.market.normalization",
    ),
    depends_on=("sources",),
))

SHOPLENS = _register(ModuleMetadata(
    slug="lens",
    name="ShopLens",
    label="While Shopping",
    description="Scanning and import: barcode, photo, receipt, object detection, OCR, and voice input.",
    tab_ids=("market", "scanner"),
    tab_labels={"market": "While Shopping"},
    order=TAB_ORDER.get("market", 999),
    service_modules=(
        "shopstack.services.market_lens",
        "shopstack.ui.screens.market_lens",
        "shopstack.scanner",
    ),
    depends_on=("stock",),
))

SHOPMEMORY = _register(ModuleMetadata(
    slug="memory",
    name="ShopMemory",
    label="Memory",
    description="Price history, household preferences, field notes, purchase cadence, waste pattern tracking, and household analytics.",
    tab_ids=("basket", "memory", "analytics"),
    tab_labels={
        "basket": "Groceries",
        "memory": "Memory",
        "analytics": "Analytics",
    },
    order=TAB_ORDER.get("memory", 999),
    service_modules=(
        "shopstack.ui.views",
        "shopstack.ui.screens.other",
    ),
))

SHOPAGENT = _register(ModuleMetadata(
    slug="agent",
    name="ShopAgent",
    label="Ask ShopStack",
    description="Reasoning layer: AI planner with tool-calling, decision classification, intent parsing, and trace audit trail.",
    tab_ids=("today", "memory", "parser"),
    tab_labels={
        "today": "Home",
        "memory": "Memory",
        "parser": "Parser Test",
    },
    order=TAB_ORDER.get("today", 999),
    service_modules=(
        "shopstack.planner.engine",
        "shopstack.planner.prompts",
        "shopstack.planner.parser",
        "shopstack.decisions",
        "shopstack.traces.export",
    ),
    depends_on=("stock", "basket", "memory"),
))

SOURCES = _register(ModuleMetadata(
    slug="sources",
    name="Sources",
    label="Sources",
    description="Retailer dataset adapters for price intelligence and basket comparison. Includes Swiggy Instamart.",
    tab_ids=(),
    order=999,
    service_modules=(
        "shopstack.market.sources.swiggy",
    ),
    is_source=True,
))

RUNTIME = _register(ModuleMetadata(
    slug="runtime",
    name="Runtime",
    label="System",
    description="Provider/model runtime diagnostics, budget status, and candidate model catalog. Developer-facing.",
    tab_ids=("memory",),
    tab_labels={"memory": "System"},
    order=TAB_ORDER.get("memory", 999),
    service_modules=(
        "shopstack.ui.screens.model_stack",
        "shopstack.model_registry",
        "shopstack.providers.runtime",
    ),
))

SHOPNUTRITION = _register(ModuleMetadata(
    slug="nutrition",
    name="ShopNutrition",
    label="Nutrition",
    description="Nutrition lookup for common Indian household items and kitchen macro breakdown from inventory.",
    tab_ids=("memory", "nutrition"),
    tab_labels={"memory": "Memory", "nutrition": "Nutrition"},
    order=TAB_ORDER.get("nutrition", 999),
    service_modules=(
        "shopstack.services.nutrition",
        "shopstack.ui.screens.nutrition",
        "shopstack.ui.screens.nutrition_coach",
        "shopstack.services.nutrition_coach",
    ),
    depends_on=("stock",),
))

SHOPTIMELINE = _register(ModuleMetadata(
    slug="timeline",
    name="ShopTimeline",
    label="Timeline",
    description="Unified cross-source event timeline — see what happened to your household items over time.",
    tab_ids=("timeline",),
    tab_labels={"timeline": "Timeline"},
    order=TAB_ORDER.get("timeline", 999),
    service_modules=(
        "shopstack.services.timeline",
        "shopstack.ui.screens.timeline",
    ),
    depends_on=("stock",),
))

SHOPTRIPADVISOR = _register(ModuleMetadata(
    slug="trip_advisor",
    name="ShopTripAdvisor",
    label="Trip Plans",
    description="Trip planning: combine weather, expiry, and shopping needs into actionable advice before you head out.",
    tab_ids=("trip_advisor",),
    tab_labels={"trip_advisor": "Trip Plans"},
    order=TAB_ORDER.get("trip_advisor", 999),
    service_modules=(
        "shopstack.services.trip_advisor",
        "shopstack.services.trip_context",
        "shopstack.services.weather",
        "shopstack.ui.screens.trip_advisor",
    ),
    depends_on=("stock", "basket"),
))

SHOPMARKETINTEL = _register(ModuleMetadata(
    slug="market_intel",
    name="ShopMarketIntel",
    label="Market Intel",
    description="Market intelligence graph — cross-source price comparison, buy/skip/signal lanes, substitution, and reliability scoring.",
    tab_labels={"market_intel": "Market Intel"},
    tab_ids=("market_intel",),
    order=TAB_ORDER.get("market_intel", 999),
    service_modules=(
        "shopstack.services.market_intelligence",
        "shopstack.ui.screens.market_intelligence",
    ),
    depends_on=("sources", "basket"),
))


# ── Lookup helpers ───────────────────────────────────────────────────

def get_all() -> list[ModuleMetadata]:
    """Return all registered modules, ordered by definition."""
    return list(_MODULES.values())


def tab_order() -> list[tuple[str, str]]:
    """Return (tab_id, display_label) pairs in UI navigation order.

    This is the canonical source for building the Gradio tab bar in app.py.
    Every registered tab appears once, ordered by ``TAB_ORDER``.
    Unknown tab_ids (not in TAB_ORDER) are sorted last alphabetically.
    """
    known = [(TAB_ORDER[tid], tid, TAB_LABELS.get(tid, tid)) for tid in TAB_ORDER]
    known.sort(key=lambda x: x[0])
    return [(tid, label) for _, tid, label in known]


def tab_label(tab_id: str) -> str:
    """Return the canonical display label for a tab ID.

    Checks per-module tab_labels first (for module-specific overrides),
    then the global TAB_LABELS, then falls back to the raw tab_id.
    """
    # Check if any module has a per-tab override
    for m in _MODULES.values():
        if tab_id in m.tab_labels:
            return m.tab_labels[tab_id]
    return TAB_LABELS.get(tab_id, tab_id)


def group_order() -> list[tuple[str, str]]:
    """Return (group_id, display_label) pairs in UI navigation order.

    This is the canonical source for building the top-level grouped
    tab bar in app.py. Groups are sorted by ``GROUP_ORDER``.
    """
    known = [(GROUP_ORDER[gid], gid, GROUP_LABELS.get(gid, gid)) for gid in GROUP_ORDER]
    known.sort(key=lambda x: x[0])
    return [(gid, label) for _, gid, label in known]


def group_tab_ids(group_id: str) -> list[str]:
    """Return the screen tab IDs for a given group, sorted by TAB_ORDER."""
    tids = TAB_GROUPS.get(group_id, [])
    return sorted(tids, key=lambda tid: TAB_ORDER.get(tid, 999))


def group_label(group_id: str) -> str:
    """Return the display label for a group tab ID."""
    return GROUP_LABELS.get(group_id, group_id)


def get_by_slug(slug: str) -> ModuleMetadata | None:
    """Look up a module by its slug (e.g. \"stock\", \"basket\")."""
    return _MODULES.get(slug)


def get_by_tab_id(tab_id: str) -> list[ModuleMetadata]:
    """Find all modules associated with a given Gradio tab ID.

    A single tab may belong to multiple modules (e.g. \"prices\" belongs to
    both ShopMemory and ShopCompare).
    """
    return [m for m in _MODULES.values() if tab_id in m.tab_ids]


def get_tab_ids(slug: str) -> tuple[str, ...]:
    """Return all tab IDs for a given module slug."""
    m = _MODULES.get(slug)
    return m.tab_ids if m else ()


def navigation() -> list[tuple[str, str, str]]:
    """Return an ordered list of (tab_id, label, module_name) for navigation.

    This is the canonical source for building tab navigation in app.py and
    other UI surfaces. Only modules with at least one tab ID are included.
    """
    entries: list[tuple[str, str, str]] = []
    for m in _MODULES.values():
        for tid in m.tab_ids:
            entries.append((tid, m.label, m.name))
    return entries


def module_dependencies(slug: str) -> list[ModuleMetadata]:
    """Return the ModuleMetadata objects this module depends on."""
    m = _MODULES.get(slug)
    if not m:
        return []
    return [dep for dep_slug in m.depends_on if (dep := _MODULES.get(dep_slug))]


def summary_table() -> list[dict[str, str]]:
    """Return a table-friendly list of dicts for display/export."""
    return [
        {
            "Module": m.name,
            "Label": m.label,
            "Description": m.description,
            "Tabs": ", ".join(m.tab_ids) if m.tab_ids else "(none)",
        }
        for m in _MODULES.values()
    ]
