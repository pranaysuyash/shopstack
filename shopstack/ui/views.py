from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from html import escape
from typing import Any

import pandas as pd

from shopstack.persistence.database import Database

FIELD_NOTES_CONFIG_KEY = "field_notes_markdown"


@dataclass
class PriceMemoryView:
    summary_html: str
    df: pd.DataFrame
    table: list[list[str]]
    item_name: str = ""
    observation_count: int = 0
    store_count: int = 0
    latest_price: float | None = None
    first_price: float | None = None
    min_price: float | None = None
    max_price: float | None = None
    unit_price_latest: float | None = None
    unit_price_best: float | None = None
    best_store: str = ""
    last_seen: str = ""
    direction: str = ""
    moving_avg: float | None = None
    volatility: float | None = None
    trend_strength: str = ""
    recommendation: str = ""
    recommendation_detail: str = ""


@dataclass
class FieldNotesView:
    editor_value: str
    preview_value: str
    status_html: str


ERROR_HTML = "<div style='color:var(--red);'>Could not load price history due to a database error.</div>"
EMPTY_DF = pd.DataFrame(columns=["date", "store", "price", "unit_price", "qty", "unit", "source"])


def _compute_unit_price(price: float, quantity: float, unit: str) -> float | None:
    unit_lower = unit.lower().strip()
    if quantity <= 0:
        return None
    if unit_lower in ("kg", "kilogram", "kilograms", "kgs"):
        normalized = price / quantity
    elif unit_lower in ("l", "liter", "litre", "liters", "litres"):
        normalized = price / quantity
    elif unit_lower in ("g", "gram", "grams", "gm", "gms"):
        normalized = price / (quantity / 1000)
    elif unit_lower in ("ml", "milliliter", "millilitre"):
        normalized = price / (quantity / 1000)
    elif unit_lower in ("unit", "piece", "pieces", "count", "each"):
        normalized = price / quantity
    else:
        normalized = price / quantity
    return round(normalized, 2)


def _unit_label(unit: str) -> str:
    unit_lower = unit.lower().strip()
    if unit_lower in ("kg", "kilogram", "kilograms", "kgs"):
        return "/kg"
    if unit_lower in ("l", "liter", "litre", "liters", "litres"):
        return "/L"
    if unit_lower in ("g", "gram", "grams", "gm", "gms"):
        return "/100g"
    if unit_lower in ("ml", "milliliter", "millilitre"):
        return "/100mL"
    return f"/{unit}"


def build_price_memory_view(database: Database, item_name: str) -> PriceMemoryView:
    cleaned_name = item_name.strip()
    if not cleaned_name:
        return PriceMemoryView(
            summary_html="<div style='color:var(--text-dim);'>Enter an item name to see price history.</div>",
            df=EMPTY_DF,
            table=[["Enter an item name to see price history"]],
        )

    safe_name = escape(cleaned_name)

    try:
        history = database.get_price_history(cleaned_name)
    except Exception:
        return PriceMemoryView(
            summary_html=ERROR_HTML,
            df=EMPTY_DF,
            table=[["Could not load price history"]],
        )

    if not history:
        return PriceMemoryView(
            summary_html=f"<div style='color:var(--text-dim);'>No price observations found for <strong>{safe_name}</strong>.</div>",
            df=EMPTY_DF,
            table=[["No price observations found"]],
            item_name=cleaned_name,
        )

    history_sorted = sorted(history, key=lambda o: (o.observation_date, o.price))

    rows: list[dict[str, Any]] = []
    for observation in history_sorted:
        unit_price = _compute_unit_price(observation.price, observation.quantity, observation.unit)
        safe_store = escape(observation.store_name or "Unknown")
        safe_notes = escape(observation.notes or "")
        source = "manual"
        if observation.source_event_id:
            source = "scan" if observation.source_event_id.startswith("det") else "import"
        rows.append(
            {
                "date": observation.observation_date.isoformat(),
                "store": safe_store,
                "price": observation.price,
                "unit_price": unit_price,
                "qty": observation.quantity,
                "unit": observation.unit,
                "notes": safe_notes,
                "source": source,
                "currency": observation.currency,
            }
        )

    df = pd.DataFrame(rows)
    prices = [r["price"] for r in rows]
    unit_prices = [r["unit_price"] for r in rows if r["unit_price"] is not None]

    first_price = prices[0]
    latest_price = prices[-1]
    change = latest_price - first_price
    direction = "higher" if change > 0 else "lower" if change < 0 else "unchanged"
    min_price = min(prices)
    max_price = max(prices)

    moving_avg = None
    volatility = None
    trend_strength = ""
    recommendation = ""
    recommendation_detail = ""

    if len(unit_prices) >= 2:
        moving_avg = round(sum(unit_prices) / len(unit_prices), 2)
        mean_up = sum(unit_prices) / len(unit_prices)
        variance = sum((up - mean_up) ** 2 for up in unit_prices) / len(unit_prices)
        std_dev = variance ** 0.5
        volatility = round(std_dev / mean_up * 100, 1) if mean_up > 0 else 0.0

        latest_up = unit_prices[-1]
        first_up = unit_prices[0]
        pct_change = ((latest_up - first_up) / first_up * 100) if first_up > 0 else 0.0

        if pct_change > 15:
            trend_strength = "strong_up"
        elif pct_change > 5:
            trend_strength = "slight_up"
        elif pct_change < -15:
            trend_strength = "strong_down"
        elif pct_change < -5:
            trend_strength = "slight_down"
        else:
            trend_strength = "stable"

        if trend_strength in ("strong_down", "slight_down"):
            recommendation = "Buy now"
            recommendation_detail = f"Prices are trending {'down' if len(unit_prices) >= 3 else 'lower'}. Average unit price: {history_sorted[0].currency} {moving_avg:.2f}."
        elif trend_strength == "strong_up" and volatility < 10:
            recommendation = "Buy now"
            recommendation_detail = "Prices are rising with low volatility. Consider buying before further increase."
        elif trend_strength == "strong_up":
            recommendation = "Wait"
            recommendation_detail = f"Prices are rising sharply ({abs(pct_change):.0f}%). Monitor for stabilization or look for alternatives."
        elif trend_strength == "slight_up":
            recommendation = "Monitor"
            recommendation_detail = f"Prices are drifting up ({abs(pct_change):.0f}%). No urgency, but watch the trend."
        else:
            recommendation = "Good time to buy"
            recommendation_detail = "Prices are stable or falling. Current conditions are favorable."

        if volatility > 20:
            recommendation_detail += " Price varies significantly between purchases. Shop around for the best deal."
        elif volatility < 5 and len(unit_prices) >= 3:
            recommendation_detail += " Prices are very consistent across observations."

    unit_label = _unit_label(history_sorted[0].unit) if history_sorted else ""
    unit_price_info = ""
    if unit_prices:
        up_latest = unit_prices[-1]
        up_first = unit_prices[0]
        up_change = up_latest - up_first
        unit_price_info = (
            f"<div>Unit price{unit_label}: latest <strong>{history_sorted[0].currency} {up_latest:.2f}</strong> "
            f"({'higher' if up_change > 0 else 'lower' if up_change < 0 else 'unchanged'} vs first).</div>"
        )
        best_idx = unit_prices.index(min(unit_prices))
        best_info = f"<div>Best observed unit price <strong>{history_sorted[0].currency} {min(unit_prices):.2f}</strong>"
        if len(rows) > best_idx:
            best_info += f" at {escape(rows[best_idx]['store'])}"
        best_info += ".</div>"
    else:
        best_info = ""

    last_observed = rows[-1]["date"] if rows else ""

    rec_html = ""
    if recommendation:
        rec_colors = {"Buy now": "var(--green)", "Wait": "var(--red)", "Monitor": "var(--amber)", "Good time to buy": "var(--green)"}
        rec_color = rec_colors.get(recommendation, "var(--text)")
        rec_html = (
            f"<div class='stat-card' style='margin-top:8px;border-left:4px solid {rec_color};'>"
            f"<div style='font-weight:600;color:{rec_color};'>{escape(recommendation)}</div>"
            f"<div style='font-size:12px;color:var(--text-dim);'>{escape(recommendation_detail)}</div>"
            f"</div>"
        )

    summary = (
        "<div class='stat-card' style='text-align:left;margin-bottom:12px;'>"
        f"<h3>Price Memory for {safe_name}</h3>"
        f"<div><strong>{len(rows)}</strong> observations across <strong>{df['store'].nunique()}</strong> stores.</div>"
        f"<div>Latest: <strong>{history_sorted[0].currency} {latest_price:.2f}</strong> "
        f"({direction} than first recorded by {history_sorted[0].currency} {abs(change):.2f}).</div>"
        f"{unit_price_info}"
        f"{best_info}"
        f"<div>Range: {history_sorted[0].currency} {min_price:.2f} to {history_sorted[0].currency} {max_price:.2f}</div>"
        f"<div>Last observed: {last_observed}</div>"
        f"{rec_html}"
        "</div>"
    )

    table = [
        ["Date", "Store", "Price", "Per Unit", "Qty", "Unit", "Source", "Notes"],
        *[
            [
                row["date"],
                row["store"],
                f"{row['currency']} {row['price']:.2f}",
                f"{row['currency']} {row['unit_price']:.2f}" if row["unit_price"] is not None else "—",
                f"{row['qty']}",
                row["unit"],
                row["source"],
                row["notes"],
            ]
            for row in rows
        ],
    ]

    return PriceMemoryView(
        summary_html=summary,
        df=df,
        table=table,
        item_name=cleaned_name,
        observation_count=len(rows),
        store_count=df["store"].nunique(),
        latest_price=latest_price,
        first_price=first_price,
        min_price=min_price,
        max_price=max_price,
        unit_price_latest=unit_prices[-1] if unit_prices else None,
        unit_price_best=min(unit_prices) if unit_prices else None,
        best_store=rows[unit_prices.index(min(unit_prices))]["store"] if unit_prices else "",
        last_seen=last_observed,
        direction=direction,
        moving_avg=moving_avg,
        volatility=volatility,
        trend_strength=trend_strength,
        recommendation=recommendation,
        recommendation_detail=recommendation_detail,
    )


def _field_notes_template(
    database: Database,
    today: date | None = None,
    mode: str = "household",
) -> str:
    today = today or date.today()
    try:
        recent_traces = database.get_traces(limit=5)
    except Exception:
        recent_traces = []
    try:
        recent_purchases = database.get_purchase_events(limit=5)
    except Exception:
        recent_purchases = []
    try:
        active_inventory = database.get_inventory(status="active")
    except Exception:
        active_inventory = []
    low_stock = [lot for lot in active_inventory if lot.quantity <= 0.5 or lot.status == "low"]

    trace_lines = []
    for trace in recent_traces:
        safe_type = escape(trace.input_type)
        safe_response = escape(trace.final_response or "No final response recorded.")
        trace_lines.append(
            f"- `{safe_type}` at {trace.timestamp.strftime('%Y-%m-%d %H:%M')}: {safe_response}"
        )
    if not trace_lines:
        trace_lines.append("- No recent activity recorded.")

    purchase_lines = []
    for purchase in recent_purchases:
        safe_name = escape(purchase.canonical_name)
        safe_store = escape(purchase.store_name or "manual")
        purchase_lines.append(
            f"- {safe_name}: {purchase.currency or '₹'}{purchase.total_price:.0f} via {safe_store}"
        )
    if not purchase_lines:
        purchase_lines.append("- No purchases recorded yet.")

    low_stock_lines = []
    for lot in low_stock[:5]:
        safe_display = escape(lot.display_name)
        low_stock_lines.append(f"- {safe_display} ({lot.quantity} {lot.unit})")
    if not low_stock_lines:
        low_stock_lines.append("- None — all stocked.")

    if mode == "developer":
        sections = [
            "# Field Notes (Dev)",
            "",
            f"_Generated on {today.isoformat()} from the live ShopStack database._",
            "",
            "## What we built",
            "- Local-first inventory memory",
            "- Price observations and price history views",
            "- Gradio surface for household shopping flows",
            "",
            "## What happened recently",
            *trace_lines,
            "",
            "## Price signals",
            *purchase_lines,
            "",
            "## Attention needed",
            *low_stock_lines,
            "",
            "## Next iteration",
            "- Improve household photo understanding",
            "- Add richer purchase import and export paths",
            "- Keep tightening the local/off-the-grid flow",
        ]
    else:
        sections = [
            "# Household Snapshot",
            "",
            f"_Updated {today.isoformat()} from your local ShopStack database._",
            "",
            "## Recent activity",
            *trace_lines,
            "",
            "## Recent shopping",
            *purchase_lines,
            "",
            "## Needs attention",
            *low_stock_lines,
            "",
            "## Suggested next actions",
            "- Review low-stock items above",
            "- Add any missing price observations",
            "- Check the household map for misplaced items",
        ]

    return "\n".join(sections)


def load_field_notes(
    database: Database,
    today: date | None = None,
) -> FieldNotesView:
    saved = database.get_config_value(FIELD_NOTES_CONFIG_KEY, "")
    if not saved.strip():
        draft = _field_notes_template(database, today=today)
        status = (
            "<div style='color:var(--amber);'>"
            "No saved notes yet. A draft is generated from recent activity below. "
            "Edit and press Save to keep it."
            "</div>"
        )
    else:
        draft = saved
        status = "<div style='color:var(--green);'>Loaded saved field notes from local storage.</div>"
    return FieldNotesView(editor_value=draft, preview_value=draft, status_html=status)


def save_field_notes(database: Database, note_text: str) -> FieldNotesView:
    cleaned = note_text.strip()
    database.set_config_value(FIELD_NOTES_CONFIG_KEY, cleaned)
    status_html = "<div style='color:var(--green);'>Field notes saved locally in the app database.</div>"
    return FieldNotesView(editor_value=cleaned, preview_value=cleaned, status_html=status_html)
