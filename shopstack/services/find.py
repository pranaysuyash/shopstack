"""Find / locate inventory items across the household.

motto_v3 §0.5/§0.10: confidence scoring and silent exceptions
need explicit handling. See ``_calculate_confidence_decay`` for
the malformed-input contract and ``_semantic_find_inventory``
for the embedding-failure log path. Item #5 (PROJECT_INTELLIGENCE)
flags these as the canonical silent-swallow sites; this module
keeps the function shape intact but stops returning a silent
empty result on a real exception.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from shopstack.domain.product_matching import score_product_match
from shopstack.domain.storage_locations import is_parent_of as _is_parent_of
from shopstack.persistence.database import Database
from shopstack.schemas.models import FindFeedback, HouseholdLocation, HouseholdObject, InventoryLot


FindEntityType = Literal["inventory_lot", "household_object", "location", "not_found"]
FindIntent = Literal["item", "location", "category", "need", "unknown"]

# Decay constant for confidence over time (days half-life)
CONFIDENCE_HALFLIFE_DAYS = 30.0
# Maximum movement events to consider for recency scoring
MAX_MOVEMENT_EVENTS = 10
# Minimum confiance floor
MIN_CONFIDENCE = 0.05

logger = logging.getLogger(__name__)


ALIASES: dict[str, list[str]] = {
    "fever medicine": ["crocin", "paracetamol", "medicine"],
    "painkiller": ["crocin", "paracetamol", "medicine"],
    "tooth stuff": ["toothpaste", "toothbrush"],
    "surf": ["detergent"],
    "remote battery": ["aa battery", "aaa battery", "battery"],
    "dhaniya": ["coriander"],
    "bill": ["receipt", "warranty card", "document"],
    # Hindi / Hinglish food aliases for cross-language search
    "doodh": ["milk"],
    "dudh": ["milk"],
    "dahi": ["curd", "yogurt"],
    "anda": ["egg"],
    "chawal": ["rice"],
    "atta": ["flour"],
    "maida": ["flour", "refined flour"],
    "sooji": ["semolina"],
    "subzi": ["vegetable"],
    "sabzi": ["vegetable"],
    "aloo": ["potato"],
    "pyaaz": ["onion"],
    "pyaz": ["onion"],
    "tamatar": ["tomato"],
    "mirchi": ["chili"],
    "namak": ["salt"],
    "cheeni": ["sugar"],
    "chai": ["tea"],
    "tel": ["oil"],
    "ghee": ["ghee", "clarified butter"],
    "nimbu": ["lemon"],
    "paneer": ["paneer", "cottage cheese"],
    "dal": ["lentil"],
    "daliya": ["porridge", "oats"],
}


@dataclass(frozen=True)
class FindEvidence:
    source: str
    message: str
    confidence: float = 1.0


@dataclass(frozen=True)
class LikelyLocation:
    location_id: str
    location_name: str
    score: float
    reasons: list[str] = field(default_factory=list)
    last_seen_at: str | None = None
    confidence_decay: float = 1.0


@dataclass(frozen=True)
class NegativeMemory:
    """Places where an item has been explicitly confirmed NOT to be."""
    location_id: str
    location_name: str
    confirmed_at: str
    source: str = "user_feedback"
    confidence: float = 1.0


@dataclass(frozen=True)
class PersonAssociation:
    """Person who owns or primarily uses this item."""
    person_id: str
    person_name: str
    relationship: str = "owner"  # owner, primary_user, occasional_user
    confidence: float = 1.0


@dataclass(frozen=True)
class ContainerRelationship:
    """Container hierarchy for nested locations (e.g., folder in bag on desk)."""
    container_id: str
    container_name: str
    contained_location_id: str
    contained_location_name: str
    confidence: float = 1.0


@dataclass(frozen=True)
class FindResult:
    entity_type: FindEntityType
    title: str
    confidence: float
    location_id: str | None = None
    location_name: str | None = None
    normal_home_location_id: str | None = None
    normal_home_location_name: str | None = None
    current_believed_location_id: str | None = None
    current_believed_location_name: str | None = None
    likely_locations: list[LikelyLocation] = field(default_factory=list)
    movement_trail: list[dict[str, Any]] = field(default_factory=list)
    negative_memory: list[NegativeMemory] = field(default_factory=list)
    person_associations: list[PersonAssociation] = field(default_factory=list)
    container_relationships: list[ContainerRelationship] = field(default_factory=list)
    evidence: list[FindEvidence] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    lot: dict[str, Any] | None = None
    location: dict[str, Any] | None = None
    household_object: dict[str, Any] | None = None
    contained_items: list[dict[str, Any]] = field(default_factory=list)
    match_type: str = "none"
    match_score: float = 0.0
    search_plan: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FindResultSet:
    query: str
    intent: FindIntent
    results: list[FindResult]
    count: int
    expanded_queries: list[str] = field(default_factory=list)
    not_found_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "intent": self.intent,
            "results": [_result_to_dict(r) for r in self.results],
            "count": self.count,
            "expanded_queries": self.expanded_queries,
            "not_found_actions": self.not_found_actions,
        }


def _calculate_confidence_decay(timestamp_str: str | None, half_life_days: float = CONFIDENCE_HALFLIFE_DAYS) -> float:
    """Calculate confidence decay factor based on time since last sighting.

    Returns a value in ``[MIN_CONFIDENCE, 1.0]`` representing how
    much we still trust a "I last saw it here" claim as time
    passes since the sighting.

    Decay policy:
      * ``None`` or empty timestamp → 1.0 (no sighting to decay from —
        we have no information, so we don't penalize).
      * Malformed timestamp (cannot parse) → 0.5 (neutral; we
        can't trust the sighting, so we apply the floor's half
        confidence). The previous behaviour of "return 1.0 on
        any error" silently over-trusted bad data — see the
        regression test in
        ``tests/test_find_confidence_decay.py``.
      * Future timestamp (clock skew) → 1.0 (we just saw it).
      * Otherwise → exponential decay with the configured
        half-life, floored at ``MIN_CONFIDENCE``.

    tz handling:
      The diff is computed against ``datetime.now(timezone.utc)``,
      not ``datetime.now()``, so tz-aware timestamps (with a
      ``+00:00`` suffix or ``Z``) work alongside naive timestamps
      in the same codebase. Naive timestamps are interpreted as
      UTC (the storage format), per the existing system state.
    """
    if not timestamp_str:
        return 1.0
    try:
        last_seen = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        if last_seen.tzinfo is None:
            # Treat naive timestamps as UTC (the storage format).
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        days_elapsed = (now_utc - last_seen).total_seconds() / 86400
        if days_elapsed <= 0:
            return 1.0
        decay_factor = 0.5 ** (days_elapsed / half_life_days)
        return max(MIN_CONFIDENCE, decay_factor)
    except (ValueError, TypeError):
        # Malformed timestamp: explicit neutral, not silent 1.0.
        return 0.5


def _generate_search_plan(
    likely_locations: list[LikelyLocation],
    negative_memory: list[NegativeMemory],
    normal_home: str | None = None,
) -> list[str]:
    """Generate ordered search plan from likely locations, excluding negative memory."""
    negative_ids = {nm.location_id for nm in negative_memory}
    plan = []
    for loc in likely_locations:
        if loc.location_id in negative_ids:
            continue
        if loc.score > 0.1:
            plan.append(f"Check {loc.location_name} ({loc.score:.0%} confidence)")
    if normal_home and normal_home not in negative_ids:
        if not any(normal_home in step for step in plan):
            plan.append(f"Check normal home: {normal_home}")
    return plan[:5]


class ShopFindService:
    """Canonical household object/location retrieval service.

    This is the first ShopFind slice: one explainable service behind the
    existing `find_item` and `semantic_find_item` tools. It intentionally uses a
    transparent rule-based model before any 3D/map/photo layer so the future UI
    has a durable source of truth to visualize.
    """

    def __init__(self, db: Database, embedding_provider: Any = None):
        self.db = db
        self._embedding_provider = embedding_provider

    def find_anything(self, query: str, user_id: str = "") -> FindResultSet:
        q = query.strip()
        if not q:
            return FindResultSet(query=query, intent="unknown", results=[], count=0)
        expanded = self._expand_query(q)
        intent = self.classify_query_intent(q, expanded)
        location_results = self._find_locations(expanded, user_id)
        object_results = self._find_household_objects(expanded, user_id)
        item_results = self._find_inventory_lots(expanded, user_id)
        results = sorted(
            [*location_results, *object_results, *item_results],
            key=lambda result: result.confidence,
            reverse=True,
        )
        return FindResultSet(
            query=query,
            intent=intent,
            results=results,
            count=len(results),
            expanded_queries=expanded,
            not_found_actions=[] if results else [
                "add_placeholder",
                "scan_location",
                "add_note",
            ],
        )

    def find_inventory_compatible(self, query: str, user_id: str = "") -> dict[str, Any]:
        result_set = self.find_anything(query, user_id=user_id)
        lot_results = [r for r in result_set.results if r.entity_type == "inventory_lot"]
        return {
            "results": [_compatible_lot_result(r) for r in lot_results],
            "count": len(lot_results),
            "intent": result_set.intent,
            "expanded_queries": result_set.expanded_queries,
        }

    def semantic_find_inventory_compatible(self, query: str, user_id: str = "") -> dict[str, Any]:
        q = query.strip()
        if not q:
            return {"results": [], "count": 0, "intent": "unknown", "match_type": "none", "semantic_active": False}
        # Try semantic ranking first when an embedding provider is wired.
        # Falls back to text matching if embeddings are unavailable or
        # return no matches above threshold.
        semantic_results = self._semantic_find_inventory(q, user_id=user_id)
        if semantic_results:
            lot_ids = {r.lot["lot_id"] for r in semantic_results if r.lot}
            text_results = self.find_inventory_compatible(query, user_id=user_id)
            extra = [r for r in self._text_only_results(query, user_id) if r.lot and r.lot["lot_id"] not in lot_ids]
            combined = list(semantic_results) + extra
            return {
                "results": [_compatible_lot_result(r) for r in combined],
                "count": len(combined),
                "intent": self.classify_query_intent(q),
                "expanded_queries": self._expand_query(q),
                "match_type": semantic_results[0].match_type if semantic_results else "none",
                "semantic_active": True,
            }
        # No embedding provider or no semantic matches → text-only fallback.
        result = self.find_inventory_compatible(query, user_id=user_id)
        result["match_type"] = (
            result["results"][0].get("match_type", "none")
            if result["results"]
            else "none"
        )
        result["semantic_active"] = self._embedding_provider is not None and getattr(self._embedding_provider, "available", False)
        return result

    def record_feedback(self, feedback: FindFeedback, user_id: str = "") -> FindFeedback:
        return self.db.record_find_feedback(feedback, user_id=user_id)

    def _semantic_find_inventory(self, query: str, user_id: str) -> list[FindResult]:
        """Return inventory lots ranked by embedding similarity to ``query``.

        Returns an empty list when no embedding provider is wired, when
        the provider reports ``available=False`` (e.g. sentence-transformers
        missing), or when no lot clears the similarity threshold.
        """
        provider = self._embedding_provider
        if provider is None or not getattr(provider, "available", False):
            return []
        lots = self.db.get_inventory(user_id=user_id)
        if not lots:
            return []
        locations = {loc.location_id: loc for loc in self.db.get_locations()}
        lot_texts = [self._lot_search_text(lot, locations.get(lot.storage_location_id)) for lot in lots]
        try:
            # Nomic distinguishes query vs document prefixes; BGE-M3 has a single embed().
            query_emb = (
                provider.embed_queries([query])[0]
                if hasattr(provider, "embed_queries")
                else provider.embed([query])[0]
            )
            doc_embs = (
                provider.embed_documents(lot_texts)
                if hasattr(provider, "embed_documents")
                else provider.embed(lot_texts)
            )
        except Exception as exc:  # noqa: BLE001
            # Item #5 (motto_v3 §0.6 risk-based verification): a
            # silent return on embedding failure left the user
            # with no results AND no audit trail. We now log
            # the failure at WARNING so it shows up in operator
            # logs and the future /health/ui error surface, then
            # fall back to no-semantic (the prefix search still
            # runs via the caller).
            logger.warning(
                "find._semantic_find_inventory: embedding failed for query=%r: %s",
                query, exc,
            )
            return []
        if not query_emb or not doc_embs or len(doc_embs) != len(lots):
            return []

        # Score every lot; keep matches above 0.40 cosine similarity.
        # 0.40 is low enough to catch cross-language matches (e.g. Hindi
        # "doodh" → English "milk") while high enough to avoid noise.
        # The Nomic bench (13-Jun-2026) showed 58% top-1 at 768 dim;
        # at 0.40 we cast a wider net and rely on text fallback for
        # the final ranking.
        threshold = 0.40
        scored: list[tuple[float, InventoryLot]] = []
        for lot, doc_emb in zip(lots, doc_embs):
            if not doc_emb:
                continue
            try:
                score = provider.similarity(query_emb, doc_emb)
            except Exception:
                continue
            if score >= threshold:
                scored.append((score, lot))
        if not scored:
            return []
        scored.sort(key=lambda pair: pair[0], reverse=True)

        results: list[FindResult] = []
        for score, lot in scored[:20]:
            loc = locations.get(lot.storage_location_id)
            trail = self._movement_trail(lot.lot_id, locations)
            negative_memory = self._get_negative_memory(lot.lot_id, user_id)
            person_associations = self._get_person_associations(lot, user_id)
            container_relationships = self._get_container_relationships(lot, locations)
            likely_locations = self._likely_locations(lot, locations, trail, negative_memory)
            current_believed_id, current_believed_name = self._determine_current_believed_location(
                lot, likely_locations, trail
            )
            normal_home_id = lot.storage_location_id
            normal_home_name = loc.name if loc else None
            search_plan = _generate_search_plan(likely_locations, negative_memory, normal_home_name)
            evidence = [
                FindEvidence(
                    source="semantic",
                    message=f"Semantic similarity to '{query}': {score:.2f}.",
                    confidence=score,
                )
            ]
            if loc:
                evidence.append(FindEvidence(source="current_location", message=f"Normal home location is {loc.name}.", confidence=0.8))
            if trail:
                evidence.append(FindEvidence(source="movement", message=f"Movement history has {len(trail)} event(s).", confidence=0.7))
            confidence = min(1.0, round(score + (0.1 if loc else 0) + (0.05 if trail else 0), 4))
            results.append(FindResult(
                entity_type="inventory_lot",
                title=lot.display_name or lot.canonical_name,
                confidence=confidence,
                location_id=lot.storage_location_id or None,
                location_name=loc.name if loc else "Unknown",
                normal_home_location_id=normal_home_id,
                normal_home_location_name=normal_home_name,
                current_believed_location_id=current_believed_id,
                current_believed_location_name=current_believed_name,
                likely_locations=likely_locations,
                movement_trail=trail,
                negative_memory=negative_memory,
                person_associations=person_associations,
                container_relationships=container_relationships,
                evidence=evidence,
                actions=["mark_found", "move_item", "add_note", "add_negative_memory", "add_person_association"],
                lot=lot.model_dump(),
                match_type="semantic",
                match_score=score,
                search_plan=search_plan,
            ))
        return results

    def _text_only_results(self, query: str, user_id: str) -> list[FindResult]:
        expanded = self._expand_query(query)
        return self._find_inventory_lots(expanded, user_id)

    def classify_query_intent(self, query: str, expanded_queries: list[str] | None = None) -> FindIntent:
        q = query.lower().strip()
        terms = expanded_queries or [q]
        if q in ALIASES or any(word in q for word in ("need", "fever", "clean", "pain")):
            return "need"
        if any(word in q for word in ("medicine", "cleaning", "document", "personal care")):
            return "category"
        if any(self._text_matches_location(term) for term in terms):
            return "location"
        return "item"

    # ── Negative memory ────────────────────────────────────────────────

    def _get_negative_memory(self, lot_id: str, user_id: str) -> list[NegativeMemory]:
        """Get locations where this item has been confirmed NOT to be."""
        rows = self.db.get_negative_memory_for_lot(lot_id)
        return [
            NegativeMemory(
                location_id=r["location_id"],
                location_name=r.get("location_name", r["location_id"]),
                confirmed_at=r["confirmed_at"],
                source=r.get("source", "user_feedback"),
                confidence=r.get("confidence", 1.0),
            )
            for r in rows
        ]

    # ── Person associations ────────────────────────────────────────────

    def _get_person_associations(self, lot: InventoryLot, user_id: str) -> list[PersonAssociation]:
        """Get person associations for this item (owner, primary user, etc.)."""
        rows = self.db.get_person_associations_for_lot(lot.lot_id)
        return [
            PersonAssociation(
                person_id=r["person_id"],
                person_name=r.get("person_name", r["person_id"]),
                relationship=r.get("relationship", "owner"),
                confidence=r.get("confidence", 1.0),
            )
            for r in rows
        ]

    # ── Container relationships ────────────────────────────────────────

    def _get_container_relationships(
        self, lot: InventoryLot, locations: dict[str, HouseholdLocation]
    ) -> list[ContainerRelationship]:
        """Build container hierarchy from location tree (e.g., bag on desk holds a folder)."""
        if not lot.storage_location_id:
            return []
        parent_by_id = {loc.location_id: loc.parent_location_id for loc in locations.values()}
        current = lot.storage_location_id
        relationships: list[ContainerRelationship] = []
        while current:
            parent_id = parent_by_id.get(current)
            if not parent_id:
                break
            child_loc = locations.get(current)
            parent_loc = locations.get(parent_id)
            if child_loc and parent_loc:
                relationships.append(ContainerRelationship(
                    container_id=parent_id,
                    container_name=parent_loc.name,
                    contained_location_id=current,
                    contained_location_name=child_loc.name,
                    confidence=0.9,
                ))
            current = parent_id
        return relationships

    # ── Current believed location ──────────────────────────────────────

    def _determine_current_believed_location(
        self,
        lot: InventoryLot,
        likely_locations: list[LikelyLocation],
        movement_trail: list[dict[str, Any]],
    ) -> tuple[str | None, str | None]:
        """Determine the item's most likely current location based on evidence.

        Priority:
          1. Most recent movement target (highest confidence)
          2. Current recorded location
          3. Normal home location
        """
        # Most recent movement
        if movement_trail:
            latest = movement_trail[0]
            to_id = latest.get("to_location_id")
            to_name = latest.get("to_location_name")
            if to_id:
                return to_id, to_name or to_id
        # Current recorded location
        if lot.storage_location_id:
            for loc in likely_locations:
                if loc.location_id == lot.storage_location_id:
                    return loc.location_id, loc.location_name
            return lot.storage_location_id, lot.storage_location_id
        return None, None

    # ── Durable household objects ─────────────────────────────────────

    def _find_household_objects(self, expanded_queries: list[str], user_id: str) -> list[FindResult]:
        objects = self.db.get_household_objects(user_id=user_id)
        locations = {loc.location_id: loc for loc in self.db.get_locations()}
        results: list[FindResult] = []
        for obj in objects:
            notes = self.db.get_object_notes(obj.object_id, user_id=user_id)
            sightings = self.db.get_object_sightings(obj.object_id, user_id=user_id)
            home = locations.get(obj.home_location_id or "")
            current = locations.get(obj.current_location_id or "")
            haystack = self._object_search_text(obj, home, current, notes)
            best = self._best_text_match(expanded_queries, haystack, obj.canonical_name, obj.display_name, obj.category)
            if best is None:
                continue
            match_type, match_score, reason = best
            likely_locations = self._object_likely_locations(obj, sightings, locations)
            current_id = likely_locations[0].location_id if likely_locations else (obj.current_location_id or obj.home_location_id)
            current_name = likely_locations[0].location_name if likely_locations else ((current or home).name if (current or home) else None)
            trail = [
                {
                    "sighting_id": sighting.sighting_id,
                    "to_location_id": sighting.location_id,
                    "to_location_name": locations.get(sighting.location_id).name if locations.get(sighting.location_id) else sighting.location_id,
                    "timestamp": sighting.timestamp.isoformat(),
                    "source": sighting.source,
                    "confidence": sighting.confidence,
                    "context": sighting.context,
                    "notes": sighting.notes,
                }
                for sighting in sightings
            ]
            evidence = [FindEvidence(source="match", message=reason, confidence=match_score)]
            if home:
                evidence.append(FindEvidence(source="home", message=f"Normal home is {home.name}.", confidence=0.8))
            if current:
                evidence.append(FindEvidence(source="current_location", message=f"Current believed location is {current.name}.", confidence=0.85))
            if sightings:
                first_loc = locations.get(sightings[0].location_id)
                evidence.append(FindEvidence(source="sighting", message=f"Last seen at {first_loc.name if first_loc else sightings[0].location_id}.", confidence=sightings[0].confidence))
            if notes:
                evidence.append(FindEvidence(source="note", message=notes[0].note_text, confidence=0.7))
            search_plan = _generate_search_plan(likely_locations, [], home.name if home else None)
            results.append(FindResult(
                entity_type="household_object",
                title=obj.display_name or obj.canonical_name,
                confidence=min(1.0, round(match_score + (0.1 if current else 0) + (0.08 if sightings else 0), 4)),
                location_id=current_id,
                location_name=current_name,
                normal_home_location_id=obj.home_location_id,
                normal_home_location_name=home.name if home else None,
                current_believed_location_id=current_id,
                current_believed_location_name=current_name,
                likely_locations=likely_locations,
                movement_trail=trail,
                evidence=evidence,
                actions=["mark_found", "add_sighting", "add_note", "set_home_location"],
                household_object=obj.model_dump(),
                match_type=match_type,
                match_score=match_score,
                search_plan=search_plan,
            ))
        return results

    # ── Core search ────────────────────────────────────────────────────

    def _find_inventory_lots(self, expanded_queries: list[str], user_id: str) -> list[FindResult]:
        lots = self.db.get_inventory(user_id=user_id)
        locations = {loc.location_id: loc for loc in self.db.get_locations()}
        results: dict[str, FindResult] = {}
        for lot in lots:
            loc = locations.get(lot.storage_location_id)
            haystack = self._lot_search_text(lot, loc)
            best = self._best_text_match(expanded_queries, haystack, lot.canonical_name, lot.display_name, lot.category)
            if best is None:
                continue
            match_type, match_score, reason = best
            trail = self._movement_trail(lot.lot_id, locations)

            negative_memory = self._get_negative_memory(lot.lot_id, user_id)
            person_associations = self._get_person_associations(lot, user_id)
            container_relationships = self._get_container_relationships(lot, locations)
            likely_locations = self._likely_locations(lot, locations, trail, negative_memory)
            current_believed_id, current_believed_name = self._determine_current_believed_location(lot, likely_locations, trail)
            normal_home_id = lot.storage_location_id
            normal_home_name = loc.name if loc else None
            search_plan = _generate_search_plan(likely_locations, negative_memory, normal_home_name)

            evidence = [FindEvidence(source="match", message=reason, confidence=match_score)]
            if loc:
                evidence.append(FindEvidence(source="current_location", message=f"Normal home location is {loc.name}.", confidence=0.8))
            if trail:
                evidence.append(FindEvidence(source="movement", message=f"Movement history has {len(trail)} event(s).", confidence=0.7))
            if negative_memory:
                evidence.append(FindEvidence(source="negative_memory", message=f"Confirmed not in {len(negative_memory)} location(s).", confidence=0.9))
            confidence = min(1.0, round(match_score + (0.1 if loc else 0) + (0.05 if trail else 0), 4))
            result = FindResult(
                entity_type="inventory_lot",
                title=lot.display_name or lot.canonical_name,
                confidence=confidence,
                location_id=lot.storage_location_id or None,
                location_name=loc.name if loc else "Unknown",
                normal_home_location_id=normal_home_id,
                normal_home_location_name=normal_home_name,
                current_believed_location_id=current_believed_id,
                current_believed_location_name=current_believed_name,
                likely_locations=likely_locations,
                movement_trail=trail,
                negative_memory=negative_memory,
                person_associations=person_associations,
                container_relationships=container_relationships,
                evidence=evidence,
                actions=["mark_found", "move_item", "add_note", "add_negative_memory", "add_person_association"],
                lot=lot.model_dump(),
                match_type=match_type,
                match_score=match_score,
                search_plan=search_plan,
            )
            existing = results.get(lot.lot_id)
            if existing is None or result.confidence > existing.confidence:
                results[lot.lot_id] = result
        return list(results.values())

    def _find_locations(self, expanded_queries: list[str], user_id: str) -> list[FindResult]:
        locations = self.db.get_locations()
        inventory = self.db.get_inventory(user_id=user_id)
        results: list[FindResult] = []
        for loc in locations:
            haystack = " ".join(
                part for part in [loc.location_id, loc.name, loc.location_type, loc.notes or ""] if part
            ).lower()
            if not any(term in haystack for term in expanded_queries):
                continue
            contained = [lot for lot in inventory if self._lot_in_location_tree(lot, loc, locations)]
            results.append(FindResult(
                entity_type="location",
                title=loc.name,
                confidence=0.92,
                location_id=loc.location_id,
                location_name=loc.name,
                location=loc.model_dump(),
                contained_items=[lot.model_dump() for lot in contained],
                evidence=[FindEvidence(source="location", message=f"Query matched storage location {loc.name}.", confidence=0.92)],
                actions=["open_location", "scan_location", "move_item_here"],
                match_type="location",
                match_score=0.92,
            ))
        return results

    def _expand_query(self, query: str) -> list[str]:
        q = query.lower().strip()
        expanded = [q]
        for alias, terms in ALIASES.items():
            if q == alias or alias in q:
                expanded.extend(terms)
        return list(dict.fromkeys(term.strip().lower() for term in expanded if term.strip()))

    def _text_matches_location(self, term: str) -> bool:
        return any(term in " ".join([loc.location_id, loc.name, loc.location_type]).lower() for loc in self.db.get_locations())

    @staticmethod
    def _lot_search_text(lot: InventoryLot, location: HouseholdLocation | None) -> str:
        return " ".join(
            str(part)
            for part in [
                lot.canonical_name,
                lot.display_name,
                lot.category,
                lot.status,
                lot.unit,
                lot.source_event_id,
                location.name if location else "",
                location.location_type if location else "",
                location.notes if location else "",
            ]
            if part
        ).lower()

    @staticmethod
    def _object_search_text(
        obj: HouseholdObject,
        home: HouseholdLocation | None,
        current: HouseholdLocation | None,
        notes: list[Any],
    ) -> str:
        return " ".join(
            str(part)
            for part in [
                obj.canonical_name,
                obj.display_name,
                obj.object_type,
                obj.category,
                obj.owner_name or "",
                obj.status,
                obj.importance,
                obj.notes or "",
                home.name if home else "",
                current.name if current else "",
                " ".join(note.note_text for note in notes),
                " ".join(" ".join(note.tags) for note in notes),
            ]
            if part
        ).lower()

    @staticmethod
    def _best_text_match(
        expanded_queries: list[str],
        haystack: str,
        canonical_name: str,
        display_name: str,
        category: str,
    ) -> tuple[str, float, str] | None:
        """Score query terms against item names using domain.product_matching, then fall back to category/context.

        Returns ``(match_type, score, reason)`` where match_type is one of
        ``exact``, ``prefix``, ``alias``, ``category``, ``context``, or ``none``.
        """
        cat = category.lower()
        candidates = [canonical_name, display_name]

        # Phase 1: score_product_match on item names (domain.product_matching)
        # Covers exact match, alias match (e.g. "doodh" → "milk"),
        # substring, prefix, and word overlap.
        best_score: float = 0.0
        best_type: str = "none"
        best_reason: str = ""

        for term in expanded_queries:
            for candidate in candidates:
                ms = score_product_match(term, candidate)
                if ms.score > best_score:
                    best_score = ms.score
                    best_type = _match_factor_to_type(ms)
                    best_reason = ms.reasons[0].detail if ms.reasons else ""

        if best_score >= 0.5:
            return best_type, best_score, best_reason or f"Matched '{best_type}' with score {best_score:.2f}."

        # Phase 2: category match (not covered by domain.product_matching)
        for term in expanded_queries:
            if cat and term in cat:
                return "category", 0.78, f"Category matches '{term}'."

        # Phase 3: full-text haystack context match
        for term in expanded_queries:
            if term in haystack:
                return "context", 0.68, f"Search context contains '{term}'."

        query_tokens = [token for term in expanded_queries for token in term.split() if len(token) >= 3]
        if query_tokens:
            matched_tokens = [token for token in query_tokens if token in haystack]
            if matched_tokens and len(matched_tokens) == len(set(query_tokens)):
                return "context", 0.66, f"Search context contains all query tokens: {', '.join(sorted(set(matched_tokens)))}."
            if len(matched_tokens) >= 2:
                return "context", 0.62, f"Search context contains related query tokens: {', '.join(sorted(set(matched_tokens)))}."

        if best_score > 0:
            return best_type, best_score, best_reason or f"Weak match (score {best_score:.2f})."
        return None


    def _movement_trail(self, lot_id: str, locations: dict[str, HouseholdLocation]) -> list[dict[str, Any]]:
        trail = []
        for movement in self.db.get_movements_for_lot(lot_id):
            from_loc = locations.get(movement.from_location_id or "")
            to_loc = locations.get(movement.to_location_id)
            trail.append({
                "movement_id": movement.movement_id,
                "from_location_id": movement.from_location_id,
                "from_location_name": from_loc.name if from_loc else None,
                "to_location_id": movement.to_location_id,
                "to_location_name": to_loc.name if to_loc else movement.to_location_id,
                "timestamp": movement.timestamp.isoformat(),
                "source": movement.source,
                "confidence": movement.confidence,
            })
        return trail

    @staticmethod
    def _likely_locations(
        lot: InventoryLot,
        locations: dict[str, HouseholdLocation],
        movement_trail: list[dict[str, Any]],
        negative_memory: list[NegativeMemory] | None = None,
    ) -> list[LikelyLocation]:
        """Score likely locations with time-decay and negative memory exclusion."""
        scores: dict[str, float] = {}
        reasons: dict[str, list[str]] = {}
        last_seen: dict[str, str] = {}

        negative_ids = {nm.location_id for nm in (negative_memory or [])}

        def add(location_id: str | None, score: float, reason: str, timestamp: str | None = None) -> None:
            if not location_id or location_id in negative_ids:
                return
            decayed = score * _calculate_confidence_decay(timestamp) if timestamp else score
            scores[location_id] = scores.get(location_id, 0.0) + decayed
            reasons.setdefault(location_id, []).append(reason)
            if timestamp:
                last_seen[location_id] = timestamp

        add(lot.storage_location_id, 0.7, "Normal home location.")
        for index, movement in enumerate(movement_trail[:5]):
            recency_score = max(0.05, 0.35 - (index * 0.06))
            ts = movement.get("timestamp")
            reason = "Most recent movement target." if index == 0 else "Prior movement target."
            add(movement.get("to_location_id"), recency_score, reason, ts)

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        if not ranked:
            return []
        max_score = max(score for _, score in ranked) or 1.0
        return [
            LikelyLocation(
                location_id=location_id,
                location_name=locations.get(location_id).name if locations.get(location_id) else location_id,
                score=round(min(1.0, score / max_score), 4),
                reasons=reasons.get(location_id, []),
                last_seen_at=last_seen.get(location_id),
                confidence_decay=_calculate_confidence_decay(last_seen.get(location_id)),
            )
            for location_id, score in ranked
        ]

    @staticmethod
    def _object_likely_locations(
        obj: HouseholdObject,
        sightings: list[Any],
        locations: dict[str, HouseholdLocation],
    ) -> list[LikelyLocation]:
        scores: dict[str, float] = {}
        reasons: dict[str, list[str]] = {}
        last_seen: dict[str, str] = {}

        def add(location_id: str | None, score: float, reason: str, timestamp: str | None = None) -> None:
            if not location_id:
                return
            scores[location_id] = scores.get(location_id, 0.0) + score
            reasons.setdefault(location_id, []).append(reason)
            if timestamp:
                last_seen[location_id] = timestamp

        add(obj.home_location_id, 0.45, "Normal home location.")
        add(obj.current_location_id, 0.75, "Current believed location.")
        for index, sighting in enumerate(sightings[:MAX_MOVEMENT_EVENTS]):
            score = max(0.08, 0.4 - index * 0.07)
            add(sighting.location_id, score, "Most recent sighting." if index == 0 else "Prior sighting.", sighting.timestamp.isoformat())
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        if not ranked:
            return []
        max_score = max(score for _, score in ranked) or 1.0
        return [
            LikelyLocation(
                location_id=location_id,
                location_name=locations.get(location_id).name if locations.get(location_id) else location_id,
                score=round(min(1.0, score / max_score), 4),
                reasons=reasons.get(location_id, []),
                last_seen_at=last_seen.get(location_id),
                confidence_decay=_calculate_confidence_decay(last_seen.get(location_id)),
            )
            for location_id, score in ranked
        ]

    @staticmethod
    def _lot_in_location_tree(lot: InventoryLot, location: HouseholdLocation, locations: list[HouseholdLocation]) -> bool:
        # Check direct match first, then delegate ancestor check to domain
        if lot.storage_location_id == location.location_id:
            return True
        return _is_parent_of(location.location_id, lot.storage_location_id, locations)


def _match_factor_to_type(ms) -> str:
    """Map a domain.product_matching MatchScore to the legacy match_type string."""
    _SCORE_TO_TYPE = {
        1.0: "exact",
        0.9: "alias",
        0.7: "prefix",
        0.6: "prefix",
        0.5: "context",
        0.4: "context",
    }
    for score, mtype in sorted(_SCORE_TO_TYPE.items(), reverse=True):
        if ms.score >= score:
            return mtype
    return "none"


def _compatible_lot_result(result: FindResult) -> dict[str, Any]:
    return {
        "lot": result.lot,
        "household_object": result.household_object,
        "location_name": result.location_name,
        "location_id": result.location_id,
        "normal_home_location_id": result.normal_home_location_id,
        "normal_home_location_name": result.normal_home_location_name,
        "current_believed_location_id": result.current_believed_location_id,
        "current_believed_location_name": result.current_believed_location_name,
        "match_type": result.match_type,
        "match_score": result.match_score,
        "confidence": result.confidence,
        "evidence": [e.__dict__ for e in result.evidence],
        "likely_locations": [loc.__dict__ for loc in result.likely_locations],
        "movement_trail": result.movement_trail,
        "negative_memory": [nm.__dict__ for nm in result.negative_memory],
        "person_associations": [pa.__dict__ for pa in result.person_associations],
        "container_relationships": [cr.__dict__ for cr in result.container_relationships],
        "search_plan": result.search_plan,
        "actions": result.actions,
    }


def _result_to_dict(result: FindResult) -> dict[str, Any]:
    data = result.__dict__.copy()
    data["evidence"] = [e.__dict__ for e in result.evidence]
    data["likely_locations"] = [loc.__dict__ for loc in result.likely_locations]
    data["negative_memory"] = [nm.__dict__ for nm in result.negative_memory]
    data["person_associations"] = [pa.__dict__ for pa in result.person_associations]
    data["container_relationships"] = [cr.__dict__ for cr in result.container_relationships]
    return data
