"""Provider-neutral capability policy catalog.

This module connects product tasks to the evidence and safety policy required
before a provider implementation can be considered for a route. It is not a
model registry, provider resolver, router, or tool executor.

The catalog is intentionally pure data. Importing it must not load a model,
read a credential, call a provider, open the application database, or mutate
production configuration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


CapabilityStatus = Literal[
    "existing",
    "evaluation_ready",
    "candidate",
    "research",
    "deferred",
]

AuthorityClass = Literal[
    "observation",
    "retrieval",
    "recommendation",
    "proposal",
    "deterministic",
    "artifact",
]

REVIEWABLE_STATUSES: frozenset[str] = frozenset({"existing", "evaluation_ready"})


@dataclass(frozen=True)
class CapabilityDecision:
    """Policy for one product task, independent of its implementation."""

    key: str
    task: str
    owner: str
    authority: AuthorityClass
    status: CapabilityStatus
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    fallback: tuple[str, ...]
    required_evidence: tuple[str, ...]
    confirmation_policy: str
    external_data: bool = False

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible policy data for reports and UI tooling."""
        return asdict(self)

    @property
    def route_reviewable(self) -> bool:
        """Whether the task has enough maturity for a separate route review."""
        return self.status in REVIEWABLE_STATUSES


CAPABILITY_DECISIONS: tuple[CapabilityDecision, ...] = (
    CapabilityDecision(
        key="planner_tool_calling",
        task="Convert user intent into validated tool proposals",
        owner="shopstack.planner + shopstack.tools",
        authority="proposal",
        status="evaluation_ready",
        inputs=("text", "household_context", "tool_schema"),
        outputs=("tool_proposal", "clarification", "abstention"),
        fallback=("deterministic_parser", "human_review", "no_mutation"),
        required_evidence=(
            "repeated_scenario_matrix",
            "state_assertions",
            "clarification_cases",
            "duplicate_and_partial_failure_tests",
        ),
        confirmation_policy="execute only after tool validation and the action-specific confirmation policy",
    ),
    CapabilityDecision(
        key="vision_product_recognition",
        task="Recognize household products from images",
        owner="shopstack.services.market_lens",
        authority="observation",
        status="evaluation_ready",
        inputs=("image", "optional_prompt"),
        outputs=("candidate_product", "attributes", "confidence", "review_item"),
        fallback=("barcode", "ocr", "manual_entry", "review_item"),
        required_evidence=(
            "labeled_real_photo_identity",
            "brand_and_quantity_accuracy",
            "unknown_item_abstention",
            "hard_neighbor_cases",
        ),
        confirmation_policy="never mutate inventory from recognition alone",
    ),
    CapabilityDecision(
        key="ocr_receipt",
        task="Extract receipt text and structured purchase fields",
        owner="shopstack.services.ocr_pipeline + shopstack.services.receipt",
        authority="observation",
        status="evaluation_ready",
        inputs=("receipt_image", "receipt_text"),
        outputs=("receipt_text", "merchant", "date", "lines", "total", "review_item"),
        fallback=("tesseract", "manual_entry", "unreconciled_receipt"),
        required_evidence=(
            "labeled_receipt_images",
            "line_item_accuracy",
            "total_consistency_checks",
            "blur_skew_and_missing_line_cases",
        ),
        confirmation_policy="create purchase events only after reconciliation and user review when uncertain",
    ),
    CapabilityDecision(
        key="embeddings_semantic",
        task="Retrieve relevant household or catalog candidates",
        owner="shopstack.services.find + shopstack.catalog",
        authority="retrieval",
        status="evaluation_ready",
        inputs=("query_text", "indexed_records", "structured_filters"),
        outputs=("ranked_candidates", "match_type", "abstention"),
        fallback=("exact_search", "prefix_search", "no_match"),
        required_evidence=(
            "positive_retrieval_cases",
            "multilingual_cases",
            "hard_negative_cases",
            "no_match_abstention",
        ),
        confirmation_policy="retrieval may suggest candidates but cannot assert identity or mutate state",
    ),
    CapabilityDecision(
        key="stt_voice_command",
        task="Convert speech into a command candidate",
        owner="shopstack.providers + shopstack.ui.screens.ask",
        authority="observation",
        status="candidate",
        inputs=("audio", "language", "conversation_context"),
        outputs=("transcript", "language", "confidence", "command_candidate"),
        fallback=("text_input", "push_to_talk_retry", "manual_entry"),
        required_evidence=(
            "word_error_rate",
            "slot_retention",
            "hinglish_and_code_switching",
            "noise_silence_and_interruption",
        ),
        confirmation_policy="transcript and parsed command remain reviewable until action confirmation",
    ),
    CapabilityDecision(
        key="tts_household_response",
        task="Speak a validated response, summary, or instruction",
        owner="shopstack.providers + experience_surfaces",
        authority="artifact",
        status="candidate",
        inputs=("validated_text", "language", "voice_preferences"),
        outputs=("audio_artifact", "duration", "playback_metadata"),
        fallback=("on_screen_text", "system_tts", "silent_mode"),
        required_evidence=(
            "intelligibility",
            "latency",
            "interruption_behavior",
            "language_and_accessibility_review",
        ),
        confirmation_policy="speak only validated content and label safety-sensitive uncertainty",
    ),
    CapabilityDecision(
        key="grounding_visual_location",
        task="Locate a named item or region in an image",
        owner="shopstack.providers + shopstack.services.photo_search",
        authority="observation",
        status="evaluation_ready",
        inputs=("image", "text_query"),
        outputs=("regions", "confidence", "unknown_or_not_found"),
        fallback=("whole_image_review", "manual_region_selection", "not_found"),
        required_evidence=(
            "grounding_success",
            "box_or_region_quality",
            "occlusion_cases",
            "unknown_item_abstention",
        ),
        confirmation_policy="regions guide review and must not become identity or quantity without reconciliation",
    ),
    CapabilityDecision(
        key="segmentation_item_isolation",
        task="Isolate an item or region for review or presentation",
        owner="shopstack.providers + shopstack.ui",
        authority="artifact",
        status="evaluation_ready",
        inputs=("image", "optional_region_prompt"),
        outputs=("mask_or_crop", "source_reference", "quality_metadata"),
        fallback=("original_image", "manual_crop", "no_artifact"),
        required_evidence=(
            "mask_quality",
            "identity_preservation",
            "source_provenance",
            "failure_case_review",
        ),
        confirmation_policy="derived visuals never replace the original evidence artifact",
    ),
    CapabilityDecision(
        key="image_card_generation",
        task="Create a derived visual card or annotation",
        owner="shopstack.providers + shopstack.ui",
        authority="artifact",
        status="candidate",
        inputs=("source_image_or_product_data", "validated_attributes", "style_request"),
        outputs=("derived_image", "provenance", "generation_metadata"),
        fallback=("template_card", "text_only", "original_image"),
        required_evidence=(
            "identity_preservation",
            "annotation_correctness",
            "no_invented_product_facts",
            "source_provenance",
        ),
        confirmation_policy="generation may present validated facts but cannot author new household facts",
    ),
    CapabilityDecision(
        key="market_price_normalization",
        task="Normalize and compare external price observations",
        owner="shopstack.market + shopstack.services.market_intelligence",
        authority="deterministic",
        status="existing",
        inputs=("market_records", "catalog_identity", "unit_rules", "source_metadata"),
        outputs=("normalized_price", "unit_price", "comparison", "freshness_warning"),
        fallback=("source_specific_display", "stale_data_warning", "no_comparison"),
        required_evidence=(
            "unit_and_currency_cases",
            "pack_equivalence_cases",
            "stale_source_cases",
            "conflicting_observation_cases",
        ),
        confirmation_policy="external observations inform decisions but do not overwrite household purchase truth",
        external_data=True,
    ),
    CapabilityDecision(
        key="proactive_household_routine",
        task="Prepare or schedule a recurring household recommendation",
        owner="shopstack.services + scheduler",
        authority="recommendation",
        status="candidate",
        inputs=("household_events", "preferences", "schedule", "quiet_hours"),
        outputs=("recommendation", "reason", "schedule_proposal", "suppression_state"),
        fallback=("manual_dashboard", "disabled", "no_notification"),
        required_evidence=(
            "relevance",
            "duplicate_suppression",
            "quiet_hours",
            "pause_explanation_and_undo",
        ),
        confirmation_policy="activation requires user-owned schedule and explicit pause or opt-out controls",
    ),
    CapabilityDecision(
        key="external_purchase_execution",
        task="Hand off or execute an external purchase",
        owner="future commerce integration",
        authority="proposal",
        status="research",
        inputs=("confirmed_basket", "retailer_account", "payment_authority"),
        outputs=("purchase_proposal", "external_receipt", "handoff_status"),
        fallback=("export_basket", "copy_list", "manual_checkout"),
        required_evidence=(
            "partner_contract",
            "authentication_and_payment",
            "explicit_confirmation",
            "rollback_and_audit",
        ),
        confirmation_policy="never execute without explicit confirmation for the exact retailer basket and amount",
        external_data=True,
    ),
)


def capability_decisions() -> tuple[CapabilityDecision, ...]:
    """Return the immutable catalog in its canonical display order."""
    return CAPABILITY_DECISIONS


def get_capability_decision(key: str) -> CapabilityDecision:
    """Look up one policy row, raising a useful error for unknown tasks."""
    for decision in CAPABILITY_DECISIONS:
        if decision.key == key:
            return decision
    raise KeyError(f"unknown ShopStack capability: {key}")


def validate_capability_matrix(
    decisions: tuple[CapabilityDecision, ...] = CAPABILITY_DECISIONS,
) -> tuple[str, ...]:
    """Return policy-catalog violations without mutating or importing runtime state."""
    errors: list[str] = []
    seen: set[str] = set()
    valid_statuses = {"existing", "evaluation_ready", "candidate", "research", "deferred"}
    valid_authorities = {
        "observation",
        "retrieval",
        "recommendation",
        "proposal",
        "deterministic",
        "artifact",
    }

    for decision in decisions:
        if not decision.key:
            errors.append("capability key must not be empty")
        if decision.key in seen:
            errors.append(f"duplicate capability key: {decision.key}")
        seen.add(decision.key)
        if decision.status not in valid_statuses:
            errors.append(f"{decision.key}: invalid status {decision.status!r}")
        if decision.authority not in valid_authorities:
            errors.append(f"{decision.key}: invalid authority {decision.authority!r}")
        if not decision.owner:
            errors.append(f"{decision.key}: owner must not be empty")
        if not decision.inputs:
            errors.append(f"{decision.key}: inputs must not be empty")
        if not decision.outputs:
            errors.append(f"{decision.key}: outputs must not be empty")
        if not decision.fallback:
            errors.append(f"{decision.key}: fallback must not be empty")
        if not decision.required_evidence:
            errors.append(f"{decision.key}: required evidence must not be empty")
        if not decision.confirmation_policy:
            errors.append(f"{decision.key}: confirmation policy must not be empty")

    return tuple(errors)


def capability_decision_rows() -> list[dict[str, object]]:
    """Return rows for read-only UI and benchmark reports."""
    return [decision.to_dict() for decision in CAPABILITY_DECISIONS]
