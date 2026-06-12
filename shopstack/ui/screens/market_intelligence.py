from __future__ import annotations

from html import escape
from typing import Any

from shopstack.app_context import db, tools, current_user_id
from shopstack.services.market_intelligence import MarketCluster, build_market_intelligence_graph
from shopstack.ui.components.cards import badge_html, card as ui_card, render_action_grid, render_unified_decision_card
from shopstack.ui.components.primitives import stat_card
from shopstack.ui.screens._utils import safe_render

_LANE_LABELS = {
    "buy": "Buy Now",
    "use_soon": "Use Soon First",
    "compare": "Compare",
    "substitute": "Substitute",
    "wait": "Wait",
    "skip": "Skip",
    "optional": "Optional",
    "confirm": "Confirm",
    "watch": "Watch",
}

_LANE_VARIANTS = {
    "buy": "success",
    "use_soon": "warning",
    "compare": "blue",
    "substitute": "danger",
    "wait": "gray",
    "skip": "gray",
    "optional": "blue",
    "confirm": "green",
    "watch": "gray",
}


@safe_render
def market_intelligence_view(search: str = "", lane_filter: str = "") -> str:
    graph = build_market_intelligence_graph(db, tools.inventory, user_id=current_user_id())
    clusters = _filter_clusters(graph.clusters, search=search, lane_filter=lane_filter)
    trust_counts = _trust_counts(clusters)

    if not clusters and not graph.clusters:
        return (
            "<div class='home-card' style='text-align:left;'>"
            "<h3>Market Intelligence Graph</h3>"
            "<div style='color:var(--text-dim);'>No market snapshots are available yet. Load Swiggy or another source to build the graph.</div>"
            "</div>"
        )

    freshness_badge = badge_html(
        graph.snapshot_freshness_label or graph.snapshot_freshness or "unknown",
        "red" if graph.snapshot_freshness == "stale" else "blue",
    )
    source_line = ", ".join(graph.source_names) if graph.source_names else "no sources"
    freshness_line = (
        f"<div style='font-size:12px;color:var(--text-dim);margin-top:6px;'>"
        f"{escape(source_line)} · Market data is point-in-time and trust-scored before being shown."
        f"</div>"
    )

    summary_cards = (
        stat_card(str(graph.summary.get("items_scored", 0)), "Items Scored", icon="🧠")
        + stat_card(str(graph.summary.get("buy", 0)), "Buy", variant="success", icon="🛒")
        + stat_card(str(graph.summary.get("skip", 0)), "Skip", variant="default", icon="⏭")
        + stat_card(str(graph.summary.get("use_soon", 0)), "Use Soon", variant="warning", icon="🥬")
        + stat_card(str(graph.summary.get("compare", 0)), "Compare", variant="default", icon="⚖️")
        + stat_card(str(graph.summary.get("substitute", 0)), "Substitute", variant="danger", icon="🔁")
        + stat_card(str(graph.summary.get("stale", 0)), "Stale", variant="danger", icon="⏳")
        + stat_card(str(graph.summary.get("sponsored", 0)), "Sponsored", variant="warning", icon="📣")
    )
    truth_cards = (
        stat_card(str(trust_counts["reliable"]), "Reliable", variant="success", icon="✅")
        + stat_card(str(trust_counts["reference"]), "Reference", variant="default", icon="🗂️")
        + stat_card(str(trust_counts["low confidence"]), "Low confidence", variant="warning", icon="⚠️")
        + stat_card(str(trust_counts["stale"]), "Stale", variant="danger", icon="⏳")
    )

    actions = render_action_grid([
        {
            "label": "Shopping",
            "subtitle": "Turn buy signals into a list",
            "tab_id": "basket",
            "tone": "primary",
        },
        {
            "label": "Pantry",
            "subtitle": "Check what is already at home",
            "tab_id": "reconcile",
            "tone": "default",
        },
        {
            "label": "Price Memory",
            "subtitle": "Inspect your historical price baseline",
            "tab_id": "memory",
            "tone": "default",
        },
        {
            "label": "Scan & Compare",
            "subtitle": "Capture a shelf item and verify it live",
            "tab_id": "market",
            "tone": "default",
        },
    ])

    legend = _legend_html(graph, trust_counts)
    lane_sections = []
    for lane in ("buy", "use_soon", "compare", "substitute", "wait", "skip"):
        lane_clusters = [c for c in clusters if c.graph_lane == lane]
        if not lane_clusters:
            continue
        lane_sections.append(_render_lane_section(lane, lane_clusters))

    graph_details = _render_graph_details(graph)

    if not lane_sections:
        return (
            f"<div class='home-card' style='text-align:left;'>"
            f"<h3>Market Intelligence Graph</h3>"
            f"{freshness_badge}{freshness_line}"
            "<div style='margin-top:10px;color:var(--text-dim);'>No items matched your current filters.</div>"
            "</div>"
        )

    return (
        "<div class='home-card' style='text-align:left;'>"
        "<h3>Market Intelligence Graph</h3>"
        f"<div style='display:flex;gap:8px;align-items:center;flex-wrap:wrap;'>{freshness_badge}</div>"
        f"{freshness_line}"
        f"<div style='margin-top:12px;display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;'>{summary_cards}</div>"
        f"<div style='margin-top:10px;display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;'>{truth_cards}</div>"
        f"<div style='margin-top:12px;'>{actions}</div>"
        f"{legend}"
        "</div>"
        + "".join(lane_sections)
        + graph_details
    )


def _filter_clusters(clusters: list[MarketCluster], search: str = "", lane_filter: str = "") -> list[MarketCluster]:
    needle = (search or "").strip().lower()
    lane = (lane_filter or "").strip().lower()
    filtered = list(clusters)
    if lane and lane != "all":
        filtered = [c for c in filtered if c.graph_lane == lane]
    if needle:
        filtered = [
            c for c in filtered
            if needle in c.canonical_name.lower()
            or needle in c.display_name.lower()
            or needle in c.lane.lower()
            or any(needle in reason.lower() for reason in c.reasons)
            or any(needle in warning.lower() for warning in c.warnings)
            or any(needle in sub.get("substitute_display", "").lower() for sub in c.substitutions)
            or any(needle in component.lower() for component in c.combo_components)
        ]
    return filtered


def _render_lane_section(lane: str, clusters: list[MarketCluster]) -> str:
    title = _LANE_LABELS.get(lane, lane.title())
    variant = _LANE_VARIANTS.get(lane, "default")
    lane_note = {
        "buy": "Missing at home and worth adding.",
        "use_soon": "Use existing stock first.",
        "compare": "Overlap, substitutions, or better unit-price options.",
        "substitute": "Sold out or better replaced by another item.",
        "wait": "Market signal is weak or the item is not urgent.",
        "skip": "Already covered at home or not worth buying.",
    }.get(lane, "Household decision lane.")
    lanes_html = "".join(_render_cluster_card(cluster) for cluster in clusters[:6])
    return (
        f"<div class='home-card' style='text-align:left;margin-top:12px;border-left:3px solid { _lane_color(lane) };'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;'>"
        f"<h3 style='margin:0;'>{escape(title)}</h3>"
        f"{badge_html(str(len(clusters)), variant)}"
        f"</div>"
        f"<div style='margin-top:6px;font-size:12px;color:var(--text-dim);'>{escape(lane_note)}</div>"
        f"<div style='margin-top:10px;display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px;'>{lanes_html}</div>"
        f"</div>"
    )


def _render_cluster_card(cluster: MarketCluster) -> str:
    decision = cluster.decision
    truth = cluster.truth_score
    home_qty = f"{cluster.home_quantity:g} {cluster.home_unit}".strip() if cluster.home_quantity else "none"
    market_price = f"₹{cluster.market_price:.0f}" if cluster.market_price is not None else "price unknown"
    ppk = f" /kg ₹{cluster.market_price_per_kg:.0f}" if cluster.market_price_per_kg else ""
    memory = "No price memory yet"
    if cluster.price_memory_observations:
        memory = f"Last paid ₹{cluster.price_memory_last:.0f}" if cluster.price_memory_last else "Historical price memory available"
        if cluster.price_memory_median:
            memory += f", median ₹{cluster.price_memory_median:.0f}"
        if cluster.price_memory_trend and cluster.price_memory_trend != "insufficient_data":
            memory += f", trend {cluster.price_memory_trend}"

    combo_line = ""
    if cluster.combo_components:
        combo_line = "<div style='font-size:12px;margin-top:8px;'><strong>Combo:</strong> " + ", ".join(
            f"{escape(name)}{' ✓' if name in cluster.combo_overlap else ' ✗'}"
            for name in cluster.combo_components
        ) + "</div>"
    substitute_line = ""
    if cluster.substitutions:
        first = cluster.substitutions[0]
        substitute_line = (
            "<div style='font-size:12px;margin-top:8px;'>"
            f"<strong>Substitute:</strong> {escape(first.get('substitute_display', 'Alternative'))} "
            f"({escape(first.get('substitution_type', 'alternative'))})"
            "</div>"
        )

    nodes = ", ".join(f"{node.get('type', 'node')}: {node.get('label', '')}" for node in cluster.nodes[:4])
    edges = ", ".join(f"{edge.get('relation', 'edge')}: {edge.get('label', '')}" for edge in cluster.edges[:4])
    truth_badge = badge_html(f"{truth.label.title()} {truth.score:.0%}", _truth_variant(truth.label))
    decision_badge = badge_html(
        f"Decision {((decision.action if decision else 'watch').replace('_', ' ').title())}",
        _lane_variant(decision.action if decision else "watch"),
    )
    graph_badge = badge_html(
        f"Graph {cluster.graph_lane.replace('_', ' ').title()}",
        "blue" if cluster.graph_lane in {"compare", "watch"} else _lane_variant(cluster.graph_lane),
    )
    truth_warning_line = ""
    if truth.warnings:
        truth_warning_line = (
            "<div style='font-size:11px;color:var(--text-dim);margin-top:6px;'>"
            f"Truth signals: {escape('; '.join(truth.warnings[:3]))}"
            "</div>"
        )
    muted_style = ""
    if truth.label == "stale" or truth.sponsorship_penalty > 0:
        muted_style = "opacity:0.78;filter:saturate(0.82);"
    why_signal = _render_why_signal(cluster)

    edge_summary = ""
    if nodes or edges:
        edge_summary = (
            "<div style='font-size:11px;color:var(--text-dim);margin-top:10px;'>"
            f"Nodes: {escape(nodes)}<br/>"
            f"Edges: {escape(edges)}"
            "</div>"
        )

    return (
        f"<div class='home-card' style='text-align:left;border:1px solid var(--border);{muted_style}'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;gap:8px;'>"
        f"<strong>{escape(cluster.display_name)}</strong>"
        f"{badge_html(cluster.graph_lane.replace('_', ' ').title(), 'blue' if cluster.graph_lane in {'compare', 'watch'} else _lane_variant(cluster.graph_lane))}"
        f"</div>"
        f"<div style='display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;'>{truth_badge}{decision_badge}{graph_badge}</div>"
        f"<div style='font-size:12px;margin-top:6px;color:var(--text-dim);'>"
        f"Home: {escape(home_qty)} · Market: {escape(market_price + ppk)} · Memory: {escape(memory)}"
        f"</div>"
        f"<div style='font-size:12px;margin-top:6px;'>"
        f"Truth: <strong>{escape(truth.label)}</strong> ({truth.score:.0%}) · Freshness: {escape(cluster.market_freshness_label or cluster.market_freshness)}"
        f"</div>"
        f"<div style='font-size:12px;margin-top:6px;color:var(--text-dim);'>"
        f"{escape('; '.join(cluster.warnings[:3]) or 'No major warnings')}"
        f"</div>"
        f"{truth_warning_line}"
        f"{why_signal}"
        f"{render_unified_decision_card(cluster.decision) if cluster.decision else ''}"
        f"{combo_line}"
        f"{substitute_line}"
        f"{edge_summary}"
        "</div>"
    )


def _legend_html(graph, truth_counts: dict[str, int]) -> str:
    return (
        "<div style='margin-top:12px;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;'>"
        f"{ui_card('Truth Legend', '<div style=\"font-size:12px;line-height:1.45;\">Reliable = fresh, available, exact sizing, and some price memory.<br/>Reference = useful but needs a sanity check.<br/>Low confidence = combo, sponsored, estimated, or thin history.<br/>Stale = snapshot age is too old to trust like live truth.</div>')}"
        f"{ui_card('Trust Mix', '<div style=\"font-size:12px;line-height:1.45;\">Reliable: {0}<br/>Reference: {1}<br/>Low confidence: {2}<br/>Stale: {3}</div>'.format(truth_counts['reliable'], truth_counts['reference'], truth_counts['low confidence'], truth_counts['stale']))}"
        f"{ui_card('Graph Notes', '<div style=\"font-size:12px;line-height:1.45;\">Home nodes show what is already at home. Market nodes show current market signals. Memory nodes show your price baseline. Substitute nodes appear when an item is sold out or better replaced.</div>')}"
        "</div>"
    )


def _render_graph_details(graph) -> str:
    if not graph.nodes and not graph.edges:
        return ""
    node_rows = "".join(
        f"<div style='padding:4px 0;border-bottom:1px solid var(--border);'><strong>{escape(node.get('type', 'node'))}</strong> · {escape(str(node.get('label', '')))}</div>"
        for node in graph.nodes[:8]
    )


def _render_why_signal(cluster: MarketCluster) -> str:
    truth = cluster.truth_score
    decision = cluster.decision
    reasons = list(cluster.reasons[:3])
    if decision and decision.reason and decision.reason not in reasons:
        reasons.append(decision.reason)
    if cluster.combo_components:
        overlap = ", ".join(cluster.combo_overlap) if cluster.combo_overlap else "none"
        reasons.append(f"Combo overlap at home: {overlap}")
    if cluster.substitutions:
        reasons.append(f"Substitutions available: {len(cluster.substitutions)}")
    reasons.append(f"Truth score: {truth.label} ({truth.score:.0%})")

    breakdown_lines = [
        f"Freshness {truth.freshness_score:.0%}",
        f"Availability {truth.availability_score:.0%}",
        f"Size confidence {truth.size_confidence:.0%}",
        f"Price confidence {truth.price_confidence:.0%}",
        f"Memory confidence {truth.memory_confidence:.0%}",
    ]
    if truth.sponsorship_penalty > 0:
        breakdown_lines.append(f"Sponsored penalty {truth.sponsorship_penalty:.0%}")
    if truth.combo_penalty > 0:
        breakdown_lines.append(f"Combo penalty {truth.combo_penalty:.0%}")
    if truth.waste_penalty > 0:
        breakdown_lines.append(f"Waste penalty {truth.waste_penalty:.0%}")

    return (
        "<details style='margin-top:8px;font-size:12px;'>"
        "<summary style='cursor:pointer;color:var(--text);font-weight:600;'>Why this signal?</summary>"
        "<div style='margin-top:8px;padding:8px;border:1px solid var(--border);border-radius:8px;background:var(--surface-muted);'>"
        f"<div style='color:var(--text-dim);line-height:1.45;'>{escape('; '.join(reasons))}</div>"
        f"<div style='margin-top:8px;color:var(--text-dim);line-height:1.45;'>{escape(' · '.join(breakdown_lines))}</div>"
        "</div></details>"
    )
    edge_rows = "".join(
        f"<div style='padding:4px 0;border-bottom:1px solid var(--border);'><strong>{escape(edge.get('relation', 'edge'))}</strong> · {escape(str(edge.get('label', '')))}</div>"
        for edge in graph.edges[:8]
    )
    return (
        "<div class='home-card' style='text-align:left;margin-top:12px;'>"
        "<h3>Graph Details</h3>"
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;'>"
        f"<div><div style='font-weight:600;margin-bottom:6px;'>Nodes</div>{node_rows or '<div style=\"color:var(--text-dim);\">No nodes.</div>'}</div>"
        f"<div><div style='font-weight:600;margin-bottom:6px;'>Edges</div>{edge_rows or '<div style=\"color:var(--text-dim);\">No edges.</div>'}</div>"
        "</div></div>"
    )


def _lane_color(lane: str) -> str:
    return {
        "buy": "var(--green)",
        "use_soon": "var(--amber)",
        "compare": "var(--blue)",
        "substitute": "var(--red)",
        "wait": "var(--text-dim)",
        "skip": "var(--text-dim)",
    }.get(lane, "var(--border)")


def _lane_variant(lane: str) -> str:
    return {
        "buy": "success",
        "use_soon": "warning",
        "compare": "blue",
        "substitute": "red",
        "wait": "gray",
        "skip": "gray",
        "watch": "gray",
        "optional": "blue",
        "confirm": "green",
    }.get(lane, "gray")


def _truth_variant(label: str) -> str:
    normalized = (label or "").strip().lower()
    if normalized == "reliable":
        return "success"
    if normalized == "reference":
        return "blue"
    if normalized == "low confidence":
        return "warning"
    if normalized == "stale":
        return "red"
    return "gray"


def _trust_counts(clusters: list[MarketCluster]) -> dict[str, int]:
    counts = {"reliable": 0, "reference": 0, "low confidence": 0, "stale": 0}
    for cluster in clusters:
        label = (cluster.truth_score.label or "low confidence").strip().lower()
        if label not in counts:
            label = "low confidence"
        counts[label] += 1
        if cluster.market_freshness == "stale" and cluster.truth_score.label != "stale":
            counts["stale"] += 1
    return counts
