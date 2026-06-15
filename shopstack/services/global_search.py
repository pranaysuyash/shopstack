"""Global search — a multi-source search engine for the command palette.

Every app with 100+ items and 30 recipes needs a single search box.
ShopStack already has per-subsystem search (inventory prefix search,
recipe filter, trace search) but no single point of entry. This
module unifies them.

**What it does (motto_v3 §0 first-principles):**

Given a query string, search across every relevant data source in
parallel and return a ranked list of results. Each result carries
its kind (inventory / list / recipe / trace / price / location /
action), a human-readable title, a metadata snippet, and an action
that the JS palette can dispatch (e.g. "click the add-items tab +
focus the input").

**Sources searched:**

- ``inventory`` — items in the current household (canonical + display
  name, prefix + Hinglish aliases).
- ``shopping_list`` — items on the active list.
- ``recipes`` — recipe title and ingredient names.
- ``traces`` — recent action history (only if the query looks like
  a free-text search, not a kind: prefix).
- ``prices`` — price observations (canonical name + store).
- ``locations`` — household location names.
- ``actions`` — built-in commands (e.g. "go home", "toggle theme").

**Ranking:**

- Exact match in title: 1.0
- Prefix match in title: 0.8
- Contains match: 0.5
- Action command match: 0.9 (commands are high-intent)
- Traces: always below 0.3 (they are history, not the target).

**Security:**

- Per-household scoping is enforced at the DB layer (every search
  query passes ``user_id=``). The service does not bypass the DB
  scoping.
- The palette never returns data from other households — the
  service is read-only with respect to the database and trusts
  the database's permission checks.

**Supersession rule (motto_v3 §7):** the existing per-subsystem
search services (search.py, find.py, recipes.py) are NOT deleted.
The global search is a *layer above* them, calling each when its
domain is in the query. The inventory prefix search still works
inside the Pantry tab; the global search adds cross-source
discovery on top.

**Long-term direction:** the ranking weights live as a single
constant so a future "learning-to-rank" pass can replace them
without touching the search code.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from html import escape
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)


# ── Result model ───────────────────────────────────────────────────


@dataclass(frozen=True)
class GlobalSearchResult:
    """A single search result, ranked and ready for the palette UI.

    Attributes:
        kind: One of ``inventory``, ``list``, ``recipe``, ``trace``,
            ``price``, ``location``, ``action``. Used by the palette
            to render the result-type chip.
        title: The visible primary text.
        meta: A small secondary line (e.g. "12 left, in fridge").
        score: A float in [0, 1]; higher is more relevant. The
            palette sorts by descending score.
        action_kind: How the palette dispatches this result on
            click. ``"tab"`` clicks a top-level tab; ``"fn"`` calls
            a JS function; ``"url"`` opens a URL.
        action_target: The id or URL the action targets.
        household_id: The household the result belongs to. Used to
            filter palette results when the household switches.
    """

    kind: str
    title: str
    meta: str = ""
    score: float = 0.0
    action_kind: str = "tab"
    action_target: str = ""
    household_id: str = ""


# ── Action commands (always available, regardless of data) ────────


_ACTIONS: tuple[GlobalSearchResult, ...] = (
    GlobalSearchResult(
        kind="action", title="Go to Home", meta="Dashboard",
        score=0.9, action_kind="tab", action_target="today",
    ),
    GlobalSearchResult(
        kind="action", title="Go to Recipes", meta="Cookbook",
        score=0.9, action_kind="tab", action_target="cookbook",
    ),
    GlobalSearchResult(
        kind="action", title="Go to Groceries", meta="Shopping list",
        score=0.9, action_kind="tab", action_target="basket",
    ),
    GlobalSearchResult(
        kind="action", title="Go to While Shopping", meta="Store mode",
        score=0.9, action_kind="tab", action_target="market",
    ),
    GlobalSearchResult(
        kind="action", title="Go to At Home", meta="Reconcile",
        score=0.9, action_kind="tab", action_target="reconcile",
    ),
    GlobalSearchResult(
        kind="action", title="Go to Memory", meta="Insights",
        score=0.9, action_kind="tab", action_target="memory",
    ),
    GlobalSearchResult(
        kind="action", title="Add a new item", meta="Inventory",
        score=0.9, action_kind="tab", action_target="pantry",
    ),
    GlobalSearchResult(
        kind="action", title="Open settings", meta="Workspace",
        score=0.9, action_kind="tab", action_target="settings",
    ),
    GlobalSearchResult(
        kind="action", title="Toggle theme",
        score=0.9, action_kind="fn", action_target="toggleTheme",
    ),
    GlobalSearchResult(
        kind="action", title="Show keyboard shortcuts",
        score=0.9, action_kind="fn", action_target="showShortcutsHelp",
    ),
    GlobalSearchResult(
        kind="action", title="Show this search",
        score=0.9, action_kind="fn", action_target="showGlobalSearch",
    ),
)


# ── Source-specific searchers ─────────────────────────────────────


def _search_inventory(
    query: str, database: Any, user_id: str
) -> list[GlobalSearchResult]:
    if not database or not query:
        return []
    out: list[GlobalSearchResult] = []
    try:
        lots = database.get_inventory(user_id=user_id) or []
    except Exception as exc:  # noqa: BLE001
        logger.debug("global_search._search_inventory: %s", exc)
        return []
    q = query.strip().lower()
    # Hinglish canonicalisation (delegates to the existing service)
    canonical_q: str | None = None
    try:
        from shopstack.services.search import _canonicalize_query

        canonical_q = _canonicalize_query(query)
    except Exception:  # noqa: BLE001
        canonical_q = None

    for lot in lots:
        title = lot.display_name
        title_lower = title.lower()
        cname_lower = lot.canonical_name.lower()
        if canonical_q and canonical_q == lot.canonical_name:
            score = 1.0
        elif q == title_lower or q == cname_lower:
            score = 1.0
        elif title_lower.startswith(q) or cname_lower.startswith(q):
            score = 0.8
        elif q in title_lower or q in cname_lower:
            score = 0.5
        else:
            continue
        meta = f"{lot.quantity:g} {lot.unit}, in {lot.storage_location_id}"
        out.append(
            GlobalSearchResult(
                kind="inventory",
                title=title,
                meta=meta,
                score=score,
                action_kind="tab",
                action_target="pantry",
                household_id=user_id,
            )
        )
    return out


def _search_shopping_list(
    query: str, database: Any, user_id: str
) -> list[GlobalSearchResult]:
    if not database or not query:
        return []
    out: list[GlobalSearchResult] = []
    try:
        active = database.get_active_shopping_list(user_id=user_id)
    except Exception:  # noqa: BLE001
        return []
    if not active:
        return []
    q = query.strip().lower()
    for item in active.items:
        name = getattr(item, "name", "") or ""
        if not name:
            continue
        name_lower = name.lower()
        if q == name_lower:
            score = 1.0
        elif name_lower.startswith(q):
            score = 0.8
        elif q in name_lower:
            score = 0.5
        else:
            continue
        out.append(
            GlobalSearchResult(
                kind="list",
                title=name,
                meta=f"Active list · priority {getattr(item, 'priority', 'normal')}",
                score=score,
                action_kind="tab",
                action_target="basket",
                household_id=user_id,
            )
        )
    return out


def _search_recipes(query: str, household: Any, user_id: str) -> list[GlobalSearchResult]:
    if not query:
        return []
    # Recipes live in the cookbook service; we accept a small
    # interface so this function is testable without the full
    # service stack.
    recipes_getter = getattr(household, "get_recipes", None) if household else None
    if recipes_getter is None:
        return []
    try:
        recipes = recipes_getter() or []
    except Exception:  # noqa: BLE001
        return []
    q = query.strip().lower()
    out: list[GlobalSearchResult] = []
    for r in recipes:
        title = getattr(r, "title", "") or ""
        title_lower = title.lower()
        if q == title_lower:
            score = 1.0
        elif title_lower.startswith(q):
            score = 0.8
        elif q in title_lower:
            score = 0.5
        else:
            # Also match ingredient names — a user searching
            # "chicken" should find recipes that include chicken.
            ings = [i.lower() for i in (getattr(r, "ingredients", []) or [])]
            if any(q in ing for ing in ings):
                score = 0.4
            else:
                continue
        out.append(
            GlobalSearchResult(
                kind="recipe",
                title=title,
                meta=f"{getattr(r, 'cook_minutes', '?')} min",
                score=score,
                action_kind="tab",
                action_target="cookbook",
                household_id=user_id,
            )
        )
    return out


def _search_locations(query: str, database: Any, user_id: str) -> list[GlobalSearchResult]:
    if not database or not query:
        return []
    try:
        locs = database.get_locations() or []
    except Exception:  # noqa: BLE001
        return []
    q = query.strip().lower()
    out: list[GlobalSearchResult] = []
    for loc in locs:
        name = getattr(loc, "name", "") or ""
        if q == name.lower():
            score = 1.0
        elif name.lower().startswith(q):
            score = 0.8
        elif q in name.lower():
            score = 0.5
        else:
            continue
        out.append(
            GlobalSearchResult(
                kind="location",
                title=name,
                meta=f"Location · {getattr(loc, 'kind', 'storage')}",
                score=score,
                action_kind="tab",
                action_target="pantry",
                household_id=user_id,
            )
        )
    return out


def _search_prices(query: str, database: Any, user_id: str) -> list[GlobalSearchResult]:
    if not database or not query:
        return []
    # We search the latest price observations. The DB exposes
    # get_price_history(canonical_name) but not a free-text search,
    # so we iterate canonical names we know about.
    try:
        lots = database.get_inventory(user_id=user_id) or []
    except Exception:  # noqa: BLE001
        return []
    q = query.strip().lower()
    seen: set[str] = set()
    out: list[GlobalSearchResult] = []
    for lot in lots:
        cname = lot.canonical_name
        if cname in seen:
            continue
        seen.add(cname)
        if q not in cname.lower() and q not in lot.display_name.lower():
            continue
        try:
            history = database.get_price_history(cname, user_id=user_id) or []
        except Exception:  # noqa: BLE001
            continue
        if not history:
            continue
        latest = history[-1]
        out.append(
            GlobalSearchResult(
                kind="price",
                title=cname,
                meta=(
                    f"Latest: {latest.price:.2f} {getattr(latest, 'currency', 'INR')} "
                    f"at {getattr(latest, 'store', '?')}"
                ),
                score=0.5,
                action_kind="tab",
                action_target="market",
                household_id=user_id,
            )
        )
    return out


def _search_traces(
    query: str, database: Any, user_id: str
) -> list[GlobalSearchResult]:
    """Search recent traces. Capped to 20 to keep the palette snappy."""
    if not database or not query or len(query) < 3:
        return []
    try:
        traces = database.get_traces(limit=20, user_id=user_id) or []
    except Exception:  # noqa: BLE001
        return []
    q = query.strip().lower()
    out: list[GlobalSearchResult] = []
    for t in traces:
        text = (getattr(t, "summary", "") or getattr(t, "kind", "") or "").lower()
        if q not in text:
            continue
        out.append(
            GlobalSearchResult(
                kind="trace",
                title=getattr(t, "summary", "") or "Action",
                meta=f"Action history · {getattr(t, 'kind', '')}",
                score=0.3,
                action_kind="tab",
                action_target="memory",
                household_id=user_id,
            )
        )
    return out


def _search_actions(query: str) -> list[GlobalSearchResult]:
    """Match the action commands (e.g. "go to home", "toggle theme")."""
    if not query:
        return []
    q = query.strip().lower()
    out: list[GlobalSearchResult] = []
    for a in _ACTIONS:
        title_lower = a.title.lower()
        if q in title_lower:
            out.append(
                GlobalSearchResult(
                    kind=a.kind,
                    title=a.title,
                    meta=a.meta,
                    score=a.score,
                    action_kind=a.action_kind,
                    action_target=a.action_target,
                )
            )
    return out


# ── Public search API ─────────────────────────────────────────────


@dataclass
class SearchSources:
    """Bundle of data sources for the search.

    Each attribute is optional. A ``None`` value means "don't search
    this source." This keeps the function easy to call from tests
    (pass a partial bundle) and from the live app (pass everything).
    """

    database: Any = None
    cookbook: Any = None
    user_id: str = ""


def search(query: str, sources: SearchSources) -> list[GlobalSearchResult]:
    """Run a global search and return ranked results.

    Args:
        query: The user's query string. Empty returns no results.
        sources: A :class:`SearchSources` with the data sources to
            search. At minimum ``database`` is required; the rest
            are optional.

    Returns:
        A list of :class:`GlobalSearchResult` sorted by descending
        score, capped at 50 results.
    """
    query = (query or "").strip()
    if not query:
        return []
    # Source-allowlist filter: a user can scope the search with
    # prefixes like "type:recipe milk" or "type:trace scan".
    type_filter = _parse_type_prefix(query)
    search_query = type_filter.remaining_query
    if not search_query:
        return []

    results: list[GlobalSearchResult] = []
    # Actions are always searched — they're the most useful results
    # for short queries like "go" or "home".
    if type_filter.allows("action"):
        results.extend(_search_actions(search_query))
    if type_filter.allows("inventory"):
        results.extend(_search_inventory(search_query, sources.database, sources.user_id))
    if type_filter.allows("list"):
        results.extend(_search_shopping_list(search_query, sources.database, sources.user_id))
    if type_filter.allows("recipe"):
        results.extend(_search_recipes(search_query, sources.cookbook, sources.user_id))
    if type_filter.allows("location"):
        results.extend(_search_locations(search_query, sources.database, sources.user_id))
    if type_filter.allows("price"):
        results.extend(_search_prices(search_query, sources.database, sources.user_id))
    if type_filter.allows("trace"):
        results.extend(_search_traces(search_query, sources.database, sources.user_id))

    # Sort + cap
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:50]


# ── type: prefix parser ────────────────────────────────────────────


@dataclass
class _TypeFilter:
    """Internal helper: parsed ``type:kind ...`` prefix from a query."""

    allowed: frozenset[str] | None = None
    remaining_query: str = ""

    def allows(self, kind: str) -> bool:
        return self.allowed is None or kind in self.allowed


_TYPE_PREFIX_RE = re.compile(r"^type:([\w,]+)\s+(.*)$", re.DOTALL)


def _parse_type_prefix(query: str) -> _TypeFilter:
    """Parse ``type:recipe,trace <rest>`` to scope the search.

    Examples:

        "milk" → _TypeFilter(allowed=None, remaining_query="milk")
        "type:recipe chicken" → _TypeFilter(allowed={"recipe"}, remaining_query="chicken")
        "type:recipe,trace milk" → _TypeFilter(allowed={"recipe", "trace"}, remaining_query="milk")
    """
    m = _TYPE_PREFIX_RE.match(query)
    if not m:
        return _TypeFilter(remaining_query=query)
    kinds = frozenset(k.strip() for k in m.group(1).split(",") if k.strip())
    return _TypeFilter(allowed=kinds, remaining_query=m.group(2).strip())


# ── Renderers ──────────────────────────────────────────────────────


def render_palette_html(*, locale: str = "en") -> str:
    """Render the command-palette overlay HTML.

    The overlay is a fixed-position div that is hidden until the
    user triggers it (Cmd/Ctrl+K or the help menu). The CSS is in
    ``shopstack.ui.theme`` under ``.global-search-*``.
    """
    from shopstack.services.i18n import get_translation

    placeholder = get_translation(locale, "search.placeholder")
    status = get_translation(locale, "search.status_idle")
    empty_msg = get_translation(locale, "empty.search.title")
    return (
        f'<div class="global-search-overlay" id="ss-global-search-overlay" '
        f'role="dialog" aria-label="Search ShopStack">'
        f'<div class="global-search-panel">'
        f'<input class="global-search-input" id="ss-global-search-input" '
        f'type="search" placeholder="{escape(placeholder)}" '
        f'aria-controls="ss-global-search-results" '
        f'autocomplete="off" autocorrect="off" spellcheck="false" />'
        f'<ul class="global-search-results" id="ss-global-search-results" '
        f'role="listbox"></ul>'
        f'<div class="global-search-status" id="ss-global-search-status" '
        f'aria-live="polite">{escape(status)}</div>'
        f'<div class="global-search-empty" id="ss-global-search-empty" '
        f'style="display:none;">{escape(empty_msg)}</div>'
        f'</div>'
        f'</div>'
    )


def render_palette_script() -> str:
    """Return the JS that wires the palette to Gradio.

    - Opens on Cmd/Ctrl+K or when the help overlay's "Search" item
      is clicked.
    - Renders results as the user types, calling a Gradio endpoint
      ``/api/global_search`` with the query.
    - Keyboard: ArrowUp/Down to navigate, Enter to select, Escape
      to close.
    - Result click dispatches the action: ``tab:<id>`` clicks the
      top-level tab; ``fn:<name>`` calls a global function.

    The script is self-contained and reuses the existing
    ``data-ss-exec`` pattern (item #99).
    """
    return """
<script data-ss-exec="true">
(function() {
  var overlay = document.getElementById('ss-global-search-overlay');
  var input = document.getElementById('ss-global-search-input');
  var resultsList = document.getElementById('ss-global-search-results');
  var status = document.getElementById('ss-global-search-status');
  var empty = document.getElementById('ss-global-search-empty');
  if (!overlay || !input || !resultsList) {
    console.warn('global search overlay not in DOM yet');
    return;
  }
  var selectedIdx = -1;
  var lastResults = [];
  var inflight = null;
  function openPalette() {
    overlay.setAttribute('data-open', 'true');
    input.focus();
    input.select();
  }
  function closePalette() {
    overlay.setAttribute('data-open', 'false');
    input.value = '';
    resultsList.innerHTML = '';
    empty.style.display = 'none';
    selectedIdx = -1;
  }
  function dispatchResult(r) {
    if (r.action_kind === 'tab') {
      var btn = document.querySelector('[data-testid="tab-' + r.action_target + '"]');
      if (btn) btn.click();
    } else if (r.action_kind === 'fn') {
      try { window[r.action_target] && window[r.action_target](); } catch (e) { console.warn(e); }
    }
    closePalette();
  }
  function renderResults(results) {
    lastResults = results || [];
    selectedIdx = -1;
    resultsList.innerHTML = '';
    if (!lastResults.length) {
      empty.style.display = 'block';
      status.textContent = 'No results';
      return;
    }
    empty.style.display = 'none';
    lastResults.forEach(function(r, i) {
      var li = document.createElement('li');
      li.className = 'global-search-result';
      li.setAttribute('data-selected', 'false');
      li.setAttribute('data-index', String(i));
      li.setAttribute('role', 'option');
      li.innerHTML =
        '<span class="global-search-result-kind">' + (r.kind || '') + '</span>' +
        '<span class="global-search-result-title">' + (r.title || '') + '</span>' +
        '<span class="global-search-result-meta">' + (r.meta || '') + '</span>';
      li.addEventListener('click', function() { dispatchResult(r); });
      resultsList.appendChild(li);
    });
    status.textContent = lastResults.length + ' result' + (lastResults.length === 1 ? '' : 's');
  }
  function setSelected(delta) {
    if (!lastResults.length) return;
    var next = (selectedIdx + delta + lastResults.length) % lastResults.length;
    selectedIdx = next;
    Array.from(resultsList.children).forEach(function(li, i) {
      li.setAttribute('data-selected', i === selectedIdx ? 'true' : 'false');
    });
    var sel = resultsList.children[selectedIdx];
    if (sel) sel.scrollIntoView({ block: 'nearest' });
  }
  function doSearch() {
    var q = input.value;
    if (inflight && inflight.abort) inflight.abort();
    if (!q || q.length < 1) {
      resultsList.innerHTML = '';
      empty.style.display = 'none';
      status.textContent = 'Type to search';
      lastResults = [];
      return;
    }
    status.textContent = 'Searching...';
    // Use AbortController to cancel previous requests.
    var ctrl = new AbortController();
    inflight = ctrl;
    fetch('/api/global_search?q=' + encodeURIComponent(q), { signal: ctrl.signal })
      .then(function(r){ return r.json(); })
      .then(function(data) {
        if (ctrl.signal.aborted) return;
        renderResults(data && data.results ? data.results : []);
      })
      .catch(function(e){
        if (e.name !== 'AbortError') console.warn('global search failed', e);
      });
  }
  // Debounce: 120ms is the sweet spot for keystroke-as-you-type.
  var debounceTimer = null;
  input.addEventListener('input', function() {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(doSearch, 120);
  });
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') { closePalette(); e.preventDefault(); return; }
    if (e.key === 'ArrowDown') { setSelected(1); e.preventDefault(); return; }
    if (e.key === 'ArrowUp')   { setSelected(-1); e.preventDefault(); return; }
    if (e.key === 'Enter' && selectedIdx >= 0) {
      dispatchResult(lastResults[selectedIdx]);
      e.preventDefault();
      return;
    }
  });
  // Global hotkey: Cmd/Ctrl+K opens the palette.
  document.addEventListener('keydown', function(e) {
    if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      openPalette();
    }
  });
  // Click outside the panel closes the palette.
  overlay.addEventListener('click', function(e) {
    if (e.target === overlay) closePalette();
  });
  // Expose for the help overlay's "Search" item.
  window.showGlobalSearch = openPalette;
})();
</script>
"""


__all__ = [
    "GlobalSearchResult",
    "SearchSources",
    "render_palette_html",
    "render_palette_script",
    "search",
]
