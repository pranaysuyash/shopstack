from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from shopstack.decisions import classify_all
from shopstack.market.sources import compare_across_sources
from shopstack.market.sources.swiggy import snapshot_freshness
from shopstack.persistence.database import Database
from shopstack.schemas.models import DecisionResult, DecisionSet
from shopstack.services.freshness import classify_snapshot_freshness
from shopstack.services.price_memory import PriceMemoryService
from shopstack.services.substitution import find_substitutions
from shopstack.services.market_sources import load_market_registry

_LANE_ORDER = {
    "buy": 0,
    "use_soon": 1,
    "compare": 2,
    "substitute": 3,
    "wait": 4,
    "skip": 5,
    "optional": 6,
    "confirm": 7,
    "watch": 8,
}

_DECISION_PRIORITY = {
    "substitute": 0,
    "compare": 1,
    "use_soon": 2,
    "skip": 3,
    "buy": 4,
    "wait": 5,
    "optional": 6,
    "confirm": 7,
    "watch": 8,
}


@dataclass
class MarketTruthScore:
    freshness_score: float = 0.0
    availability_score: float = 0.0
    size_confidence: float = 0.0
    price_confidence: float = 0.0
    memory_confidence: float = 0.0
    sponsorship_penalty: float = 0.0
    combo_penalty: float = 0.0
    waste_penalty: float = 0.0
    score: float = 0.0
    label: str = "unknown"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "freshness_score": self.freshness_score,
            "availability_score": self.availability_score,
            "size_confidence": self.size_confidence,
            "price_confidence": self.price_confidence,
            "memory_confidence": self.memory_confidence,
            "sponsorship_penalty": self.sponsorship_penalty,
            "combo_penalty": self.combo_penalty,
            "waste_penalty": self.waste_penalty,
            "score": self.score,
            "label": self.label,
            "warnings": list(self.warnings),
        }


@dataclass
class MarketCluster:
    canonical_name: str
    display_name: str
    lane: str
    decision: DecisionResult | None
    home_quantity: float
    home_unit: str
    home_lot_count: int
    market_records: list[dict[str, Any]] = field(default_factory=list)
    market_source_count: int = 0
    market_price: float | None = None
    market_price_per_kg: float | None = None
    market_available: bool = False
    market_raw_size: str = ""
    market_freshness: str = "unknown"
    market_freshness_label: str = ""
    market_source: str = ""
    market_source_best: str = ""
    market_source_best_price: float | None = None
    price_memory_last: float | None = None
    price_memory_median: float | None = None
    price_memory_observations: int = 0
    price_memory_trend: str = "unknown"
    deal_score: str = "unknown"
    truth_score: MarketTruthScore = field(default_factory=MarketTruthScore)
    combo_components: list[str] = field(default_factory=list)
    combo_overlap: list[str] = field(default_factory=list)
    combo_missing: list[str] = field(default_factory=list)
    substitutions: list[dict[str, Any]] = field(default_factory=list)
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    graph_lane: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "display_name": self.display_name,
            "lane": self.lane,
            "graph_lane": self.graph_lane,
            "decision": self.decision.to_dict() if self.decision else None,
            "home_quantity": self.home_quantity,
            "home_unit": self.home_unit,
            "home_lot_count": self.home_lot_count,
            "market_records": list(self.market_records),
            "market_source_count": self.market_source_count,
            "market_price": self.market_price,
            "market_price_per_kg": self.market_price_per_kg,
            "market_available": self.market_available,
            "market_raw_size": self.market_raw_size,
            "market_freshness": self.market_freshness,
            "market_freshness_label": self.market_freshness_label,
            "market_source": self.market_source,
            "market_source_best": self.market_source_best,
            "market_source_best_price": self.market_source_best_price,
            "price_memory_last": self.price_memory_last,
            "price_memory_median": self.price_memory_median,
            "price_memory_observations": self.price_memory_observations,
            "price_memory_trend": self.price_memory_trend,
            "deal_score": self.deal_score,
            "truth_score": self.truth_score.to_dict(),
            "combo_components": list(self.combo_components),
            "combo_overlap": list(self.combo_overlap),
            "combo_missing": list(self.combo_missing),
            "substitutions": list(self.substitutions),
            "nodes": list(self.nodes),
            "edges": list(self.edges),
            "warnings": list(self.warnings),
            "reasons": list(self.reasons),
        }


@dataclass
class MarketIntelligenceGraph:
    snapshot_source: str = ""
    snapshot_captured_at: str = ""
    snapshot_freshness: str = "unknown"
    snapshot_freshness_label: str = ""
    source_count: int = 0
    source_names: list[str] = field(default_factory=list)
    load_errors: dict[str, str] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    decision_set: DecisionSet = field(default_factory=DecisionSet)
    clusters: list[MarketCluster] = field(default_factory=list)
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)

    @property
    def buy(self) -> list[MarketCluster]:
        return [c for c in self.clusters if c.graph_lane == "buy"]

    @property
    def skip(self) -> list[MarketCluster]:
        return [c for c in self.clusters if c.graph_lane == "skip"]

    @property
    def use_soon(self) -> list[MarketCluster]:
        return [c for c in self.clusters if c.graph_lane == "use_soon"]

    @property
    def compare(self) -> list[MarketCluster]:
        return [c for c in self.clusters if c.graph_lane == "compare"]

    @property
    def substitute(self) -> list[MarketCluster]:
        return [c for c in self.clusters if c.graph_lane == "substitute"]

    @property
    def wait(self) -> list[MarketCluster]:
        return [c for c in self.clusters if c.graph_lane == "wait"]

    @property
    def confirm(self) -> list[MarketCluster]:
        return [c for c in self.clusters if c.graph_lane == "confirm"]

    @property
    def optional(self) -> list[MarketCluster]:
        return [c for c in self.clusters if c.graph_lane == "optional"]

    @property
    def watch(self) -> list[MarketCluster]:
        return [c for c in self.clusters if c.graph_lane == "watch"]

    def clusters_for_lane(self, lane: str) -> list[MarketCluster]:
        return [c for c in self.clusters if c.graph_lane == lane]

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_source": self.snapshot_source,
            "snapshot_captured_at": self.snapshot_captured_at,
            "snapshot_freshness": self.snapshot_freshness,
            "snapshot_freshness_label": self.snapshot_freshness_label,
            "source_count": self.source_count,
            "source_names": list(self.source_names),
            "load_errors": dict(self.load_errors),
            "summary": dict(self.summary),
            "decision_set": {
                "buy": len(self.buy),
                "skip": len(self.skip),
                "use_soon": len(self.use_soon),
                "compare": len(self.compare),
                "substitute": len(self.substitute),
                "wait": len(self.wait),
            },
            "clusters": [cluster.to_dict() for cluster in self.clusters],
            "nodes": list(self.nodes),
            "edges": list(self.edges),
        }


def build_market_intelligence_graph(
    db: Database,
    inventory: Any,
    user_id: str = "",
) -> MarketIntelligenceGraph:
    registry, load_errors = load_market_registry(db=db, force=False)
    snapshots = registry.all_snapshots() if registry is not None else {}
    latest_snapshot = None
    if snapshots:
        latest_snapshot = max(snapshots.values(), key=lambda snap: snap.captured_at)

    decision_set = classify_all(
        db,
        inventory,
        market_snapshot=latest_snapshot,
        source_registry=registry,
        user_id=user_id,
    )

    price_memory = PriceMemoryService(db)
    inventory_rows = db.get_inventory(user_id=user_id)
    inventory_map = _inventory_map(inventory_rows)
    lot_counts = _inventory_lot_counts(inventory_rows)

    market_names = {
        record.canonical_name
        for snapshot in snapshots.values()
        for record in getattr(snapshot, "normalized_records", [])
        if getattr(record, "canonical_name", "")
    }
    focus_names = sorted(
        set(inventory_map.keys())
        | market_names
        | {d.canonical_name for d in decision_set.decisions if d.canonical_name}
    )

    clusters: list[MarketCluster] = []
    graph_nodes: list[dict[str, Any]] = []
    graph_edges: list[dict[str, Any]] = []

    for canonical in focus_names:
        decision = _choose_decision(decision_set, canonical)
        records = _collect_records(snapshots, canonical)
        best_record = _best_record(records)
        freshness = _freshness_for_snapshot(best_record or latest_snapshot)
        summary = price_memory.get_summary(canonical)
        history = price_memory.get_history(canonical) if summary.observations >= 3 else None
        deal = None
        if summary.last_price is not None:
            deal = price_memory.score_deal(
                canonical,
                current_price=summary.last_price,
                per_kg=summary.normalized_per_kg,
            )

        combo_components = list(best_record.component_names) if best_record and best_record.component_names else []
        combo_overlap = [name for name in combo_components if inventory_map.get(name, 0.0) > 0]
        combo_missing = [name for name in combo_components if name not in combo_overlap]

        substitutions: list[dict[str, Any]] = []
        if latest_snapshot is not None:
            sub_result = find_substitutions(canonical, latest_snapshot, include_available=True)
            substitutions = [
                {
                    "original_canonical": suggestion.original_canonical,
                    "substitute_canonical": suggestion.substitute_canonical,
                    "substitute_display": suggestion.substitute_display,
                    "substitution_type": suggestion.substitution_type,
                    "reason": suggestion.reason,
                    "confidence": suggestion.confidence,
                    "is_available": suggestion.is_available,
                    "price_inr": suggestion.price_inr,
                    "price_per_kg": suggestion.price_per_kg,
                }
                for suggestion in sub_result.suggestions[:3]
            ]

        truth = _build_truth_score(best_record, freshness, summary, decision, combo_components)
        lane = _graph_lane(decision, best_record, combo_components, combo_overlap, substitutions)

        market_source_count = len({record.source for record in records})
        source_best = ""
        source_best_price = None
        if registry is not None:
            cross_source = compare_across_sources(registry, canonical)
            if cross_source is not None:
                source_best = cross_source.best_source
                source_best_price = cross_source.prices.get(cross_source.best_source)

        cluster_nodes, cluster_edges = _build_cluster_graph(
            canonical=canonical,
            display_name=(decision.display_name if decision else _display_name(canonical)),
            decision=decision,
            home_quantity=inventory_map.get(canonical, 0.0),
            home_unit=_inventory_unit(inventory_rows, canonical),
            home_lot_count=lot_counts.get(canonical, 0),
            best_record=best_record,
            freshness=freshness,
            summary=summary,
            history=history,
            deal=deal.score if deal else "unknown",
            combo_components=combo_components,
            combo_overlap=combo_overlap,
            combo_missing=combo_missing,
            substitutions=substitutions,
            source_best=source_best,
            source_best_price=source_best_price,
        )

        cluster = MarketCluster(
            canonical_name=canonical,
            display_name=decision.display_name if decision else _display_name(canonical),
            lane=decision.action if decision else "watch",
            graph_lane=lane,
            decision=decision,
            home_quantity=inventory_map.get(canonical, 0.0),
            home_unit=_inventory_unit(inventory_rows, canonical),
            home_lot_count=lot_counts.get(canonical, 0),
            market_records=[
                {
                    "source": record.source,
                    "price_inr": record.price_inr,
                    "price_per_kg": record.price_per_kg,
                    "availability": record.availability,
                    "is_available": record.is_available,
                    "is_combo": record.is_combo,
                    "is_ad": record.is_ad,
                    "is_upgrade": record.is_upgrade,
                    "raw_name": record.raw_name,
                    "raw_size": record.raw_size,
                    "component_names": list(record.component_names),
                }
                for record in records[:6]
            ],
            market_source_count=market_source_count,
            market_price=best_record.price_inr if best_record else (decision.market_price if decision else None),
            market_price_per_kg=best_record.price_per_kg if best_record else (decision.market_price_per_kg if decision else None),
            market_available=best_record.is_available if best_record else bool(decision.market_available if decision else False),
            market_raw_size=best_record.raw_size if best_record else (decision.market_raw_size if decision else ""),
            market_freshness=freshness.status,
            market_freshness_label=freshness.label,
            market_source=best_record.source if best_record else (decision.source_trace if decision else ""),
            market_source_best=source_best,
            market_source_best_price=source_best_price,
            price_memory_last=summary.last_price,
            price_memory_median=summary.median_price,
            price_memory_observations=summary.observations,
            price_memory_trend=history.trend if history else "insufficient_data",
            deal_score=deal.score if deal else "unknown",
            truth_score=truth,
            combo_components=combo_components,
            combo_overlap=combo_overlap,
            combo_missing=combo_missing,
            substitutions=substitutions,
            nodes=cluster_nodes,
            edges=cluster_edges,
            warnings=_cluster_warnings(best_record, freshness, summary, decision, combo_components, substitutions, combo_overlap),
            reasons=list(decision.reasons if decision else []),
        )

        clusters.append(cluster)
        graph_nodes.extend(cluster_nodes)
        graph_edges.extend(cluster_edges)

    clusters.sort(key=lambda c: (_LANE_ORDER.get(c.graph_lane, 99), -(c.truth_score.score or 0.0), -(c.decision.confidence if c.decision else 0.0), c.display_name.lower()))

    summary = {
        "items_scored": len(clusters),
        "home_items": len(inventory_map),
        "buy": len([c for c in clusters if c.graph_lane == "buy"]),
        "skip": len([c for c in clusters if c.graph_lane == "skip"]),
        "use_soon": len([c for c in clusters if c.graph_lane == "use_soon"]),
        "compare": len([c for c in clusters if c.graph_lane == "compare"]),
        "substitute": len([c for c in clusters if c.graph_lane == "substitute"]),
        "wait": len([c for c in clusters if c.graph_lane == "wait"]),
        "stale": len([c for c in clusters if c.market_freshness == "stale"]),
        "sponsored": len([
            c for c in clusters
            if any(rec.get("is_ad") or rec.get("is_upgrade") for rec in c.market_records)
        ]),
    }

    freshness = _freshness_for_snapshot(latest_snapshot)
    return MarketIntelligenceGraph(
        snapshot_source=latest_snapshot.source if latest_snapshot else "",
        snapshot_captured_at=latest_snapshot.captured_at if latest_snapshot else "",
        snapshot_freshness=freshness.status,
        snapshot_freshness_label=freshness.label,
        source_count=len(snapshots),
        source_names=sorted(snapshots.keys()),
        load_errors=load_errors,
        summary=summary,
        decision_set=decision_set,
        clusters=clusters,
        nodes=graph_nodes,
        edges=graph_edges,
    )


def _collect_records(snapshots: dict[str, Any], canonical: str) -> list[Any]:
    records: list[Any] = []
    for snap in snapshots.values():
        if not snap or not getattr(snap, "normalized_records", None):
            continue
        records.extend([r for r in snap.normalized_records if r.canonical_name == canonical])
    return records


def _best_record(records: list[Any]) -> Any | None:
    available = [r for r in records if getattr(r, "is_available", False)]
    candidates = available or list(records)
    if not candidates:
        return None

    def _sort_key(record: Any) -> tuple[float, float, float]:
        if getattr(record, "price_per_kg", None):
            return (0.0, float(record.price_per_kg), float(record.price_inr))
        if getattr(record, "price_per_piece", None):
            return (0.1, float(record.price_per_piece), float(record.price_inr))
        return (1.0, float(record.price_inr or 0.0), float(record.card_index or 0))

    return min(candidates, key=_sort_key)


def _freshness_for_snapshot(snapshot: Any | None):
    if snapshot is None:
        from shopstack.services.freshness import FreshnessReport

        return FreshnessReport(
            status="unknown",
            age_days=None,
            label="No snapshot available",
            captured_at="",
            is_stale=True,
            warning="Market data unavailable.",
        )
    try:
        return classify_snapshot_freshness(snapshot)
    except Exception:
        freshness = snapshot_freshness(snapshot)
        from shopstack.services.freshness import FreshnessReport

        return FreshnessReport(
            status="stale" if freshness.get("is_stale") else "live",
            age_days=freshness.get("age_days"),
            label=freshness.get("label", ""),
            captured_at=getattr(snapshot, "captured_at", ""),
            is_stale=bool(freshness.get("is_stale")),
            warning="",
        )


def _inventory_map(inventory_rows: list[Any]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for lot in inventory_rows:
        if getattr(lot, "status", "") != "active":
            continue
        totals[lot.canonical_name] = totals.get(lot.canonical_name, 0.0) + float(getattr(lot, "quantity", 0.0) or 0.0)
    return totals


def _inventory_lot_counts(inventory_rows: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for lot in inventory_rows:
        if getattr(lot, "status", "") != "active":
            continue
        counts[lot.canonical_name] = counts.get(lot.canonical_name, 0) + 1
    return counts


def _inventory_unit(inventory_rows: list[Any], canonical: str) -> str:
    for lot in inventory_rows:
        if getattr(lot, "status", "") != "active":
            continue
        if lot.canonical_name == canonical:
            return getattr(lot, "unit", "") or ""
    return ""


def _choose_decision(decision_set: DecisionSet, canonical: str) -> DecisionResult | None:
    candidates = [d for d in decision_set.decisions if d.canonical_name == canonical]
    if not candidates:
        return None

    def _rank(decision: DecisionResult) -> tuple[int, float]:
        return (_DECISION_PRIORITY.get(decision.action, 99), -float(decision.confidence or 0.0))

    return sorted(candidates, key=_rank)[0]


def _display_name(canonical: str) -> str:
    return canonical.replace("_", " ").title()


def _build_truth_score(
    best_record: Any | None,
    freshness: Any,
    summary: Any,
    decision: DecisionResult | None,
    combo_components: list[str],
) -> MarketTruthScore:
    warnings: list[str] = []
    freshness_score = 0.15
    if freshness.status == "live":
        freshness_score = 1.0
    elif freshness.status == "recent":
        freshness_score = 0.85
    elif freshness.status == "stale":
        freshness_score = 0.35

    availability_score = 0.2
    size_confidence = 0.25
    price_confidence = 0.2
    memory_confidence = 0.0
    sponsorship_penalty = 0.0
    combo_penalty = 0.0
    waste_penalty = 0.0

    if best_record is not None:
        availability_score = 1.0 if getattr(best_record, "is_available", False) else 0.2
        if getattr(best_record, "is_combo", False):
            combo_penalty = 0.2
            warnings.append("combo_risk")
        if getattr(best_record, "is_size_class", False):
            size_confidence = 0.65
            warnings.append("estimated size class")
        elif getattr(best_record, "is_weight_based", False) or getattr(best_record, "is_piece_based", False):
            size_confidence = 0.95
        else:
            size_confidence = 0.55

        if getattr(best_record, "price_per_kg", None) or getattr(best_record, "price_per_piece", None):
            price_confidence = 0.95
        elif getattr(best_record, "price_inr", 0):
            price_confidence = 0.75
        else:
            price_confidence = 0.4

        if getattr(best_record, "is_ad", False):
            sponsorship_penalty += 0.18
            warnings.append("sponsored listing")
        if getattr(best_record, "is_upgrade", False):
            sponsorship_penalty += 0.1
            warnings.append("upgrade variant")

    if getattr(summary, "observations", 0) >= 3:
        memory_confidence = 0.9
        if getattr(summary, "is_price_volatile", False):
            warnings.append("price volatility")
            memory_confidence = 0.7
    elif getattr(summary, "observations", 0) >= 1:
        memory_confidence = 0.6

    if decision is not None:
        if decision.waste_risk == "high":
            waste_penalty = 0.15
            warnings.append("waste risk")
        if decision.data_freshness == "stale":
            warnings.append("stale market data")

    raw_score = (
        freshness_score * 0.28
        + availability_score * 0.16
        + size_confidence * 0.14
        + price_confidence * 0.14
        + memory_confidence * 0.14
        + max(0.0, 1.0 - sponsorship_penalty) * 0.07
        + max(0.0, 1.0 - combo_penalty) * 0.04
        + max(0.0, 1.0 - waste_penalty) * 0.03
    )
    score = round(max(0.0, min(1.0, raw_score)), 2)

    if score >= 0.8:
        label = "reliable"
    elif score >= 0.6:
        label = "reference"
    elif score >= 0.4:
        label = "low confidence"
    else:
        label = "stale"

    return MarketTruthScore(
        freshness_score=round(freshness_score, 2),
        availability_score=round(availability_score, 2),
        size_confidence=round(size_confidence, 2),
        price_confidence=round(price_confidence, 2),
        memory_confidence=round(memory_confidence, 2),
        sponsorship_penalty=round(sponsorship_penalty, 2),
        combo_penalty=round(combo_penalty, 2),
        waste_penalty=round(waste_penalty, 2),
        score=score,
        label=label,
        warnings=warnings,
    )


def _cluster_warnings(
    best_record: Any | None,
    freshness: Any,
    summary: Any,
    decision: DecisionResult | None,
    combo_components: list[str],
    substitutions: list[dict[str, Any]],
    combo_overlap: list[str],
) -> list[str]:
    warnings: list[str] = []
    if freshness.is_stale:
        warnings.append(freshness.warning or freshness.label)
    if best_record is not None and getattr(best_record, "is_ad", False):
        warnings.append("Sponsored listing detected")
    if best_record is not None and getattr(best_record, "is_upgrade", False):
        warnings.append("Upgrade variant detected")
    if combo_components:
        warnings.append(f"Combo contains {len(combo_components)} components")
    if combo_overlap:
        warnings.append(f"Home overlap: {', '.join(combo_overlap)}")
    if substitutions:
        warnings.append(f"{len(substitutions)} substitution option(s)")
    if getattr(summary, "observations", 0) >= 3 and getattr(summary, "is_price_volatile", False):
        warnings.append("Price history is volatile")
    if decision is not None and decision.waste_risk == "high":
        warnings.append("High waste-risk item")
    return warnings


def _graph_lane(
    decision: DecisionResult | None,
    best_record: Any | None,
    combo_components: list[str],
    combo_overlap: list[str],
    substitutions: list[dict[str, Any]],
) -> str:
    lane = decision.action if decision is not None else "watch"
    if combo_components:
        if combo_overlap and len(combo_overlap) >= len(combo_components):
            lane = "skip"
        elif combo_overlap:
            lane = "compare"
        elif lane == "buy" and not getattr(best_record, "is_available", True) and substitutions:
            lane = "substitute"
    if lane in {"watch", "wait"} and substitutions:
        lane = "substitute"
    if lane == "buy" and best_record is not None and not getattr(best_record, "is_available", True) and substitutions:
        lane = "substitute"
    return lane


def _build_cluster_graph(
    *,
    canonical: str,
    display_name: str,
    decision: DecisionResult | None,
    home_quantity: float,
    home_unit: str,
    home_lot_count: int,
    best_record: Any | None,
    freshness: Any,
    summary: Any,
    history: Any,
    deal: str,
    combo_components: list[str],
    combo_overlap: list[str],
    combo_missing: list[str],
    substitutions: list[dict[str, Any]],
    source_best: str,
    source_best_price: float | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    canonical_id = canonical
    home_id = f"home:{canonical}"
    market_id = f"market:{canonical}"
    memory_id = f"memory:{canonical}"

    nodes.append({
        "id": canonical_id,
        "type": "item",
        "label": display_name,
        "lane": decision.action if decision else "watch",
    })

    if home_quantity > 0 or home_lot_count > 0:
        home_label = f"At home: {home_quantity:g} {home_unit}".strip()
        if not home_unit:
            home_label = f"At home: {home_quantity:g}"
        nodes.append({
            "id": home_id,
            "type": "home",
            "label": home_label,
        })
        edges.append({
            "source": home_id,
            "target": canonical_id,
            "relation": "inventory",
            "label": "already have",
        })

    if best_record is not None:
        market_label = _market_label(best_record, freshness)
        nodes.append({
            "id": market_id,
            "type": "market",
            "label": market_label,
            "source": getattr(best_record, "source", ""),
        })
        edges.append({
            "source": canonical_id,
            "target": market_id,
            "relation": "market",
            "label": "available" if getattr(best_record, "is_available", False) else "sold out",
        })
        if source_best:
            nodes.append({
                "id": f"source:{source_best}",
                "type": "source",
                "label": source_best.title(),
            })
            edges.append({
                "source": market_id,
                "target": f"source:{source_best}",
                "relation": "best_source",
                "label": f"best source {source_best}",
            })

    if summary.observations > 0:
        nodes.append({
            "id": memory_id,
            "type": "memory",
            "label": f"Price memory: {summary.observations} obs",
        })
        edges.append({
            "source": canonical_id,
            "target": memory_id,
            "relation": "memory",
            "label": f"last paid {summary.last_price:.0f}" if summary.last_price else "history",
        })

    if combo_components:
        combo_id = f"combo:{canonical}"
        nodes.append({
            "id": combo_id,
            "type": "combo",
            "label": "Combo bundle",
            "components": list(combo_components),
        })
        edges.append({
            "source": combo_id,
            "target": canonical_id,
            "relation": "bundle",
            "label": "contains components",
        })
        for component in combo_components:
            component_id = f"component:{component}"
            edges.append({
                "source": combo_id,
                "target": component_id,
                "relation": "contains",
                "label": component.replace("_", " "),
            })
    if combo_overlap:
        edges.append({
            "source": home_id,
            "target": canonical_id,
            "relation": "combo_overlap",
            "label": f"{len(combo_overlap)} component(s) already at home",
        })
    if combo_missing:
        edges.append({
            "source": canonical_id,
            "target": f"missing:{canonical}",
            "relation": "combo_gap",
            "label": f"still need {len(combo_missing)} component(s)",
        })
    if substitutions:
        sub = substitutions[0]
        nodes.append({
            "id": f"substitute:{canonical}",
            "type": "substitute",
            "label": sub.get("substitute_display", "Substitute"),
        })
        edges.append({
            "source": canonical_id,
            "target": f"substitute:{canonical}",
            "relation": "substitute",
            "label": sub.get("reason", "alternative available"),
        })

    return nodes, edges


def _market_label(record: Any, freshness: Any) -> str:
    price = f"₹{record.price_inr:.0f}" if getattr(record, "price_inr", None) is not None else "price unknown"
    size = f"{record.raw_size}" if getattr(record, "raw_size", "") else ""
    source = getattr(record, "source", "").title()
    trust = freshness.status if getattr(freshness, "status", "") else "unknown"
    parts = [part for part in [source, price, size, trust] if part]
    return " · ".join(parts)
