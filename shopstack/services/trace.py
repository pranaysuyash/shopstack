"""Trace service — wraps trace CRUD, export, and redaction operations.

Follows the service boundary pattern established by shopstack.services.shopping,
shopstack.services.dashboard, etc. Encapsulates all trace lifecycle operations
that were previously exposed as standalone functions in shopstack.traces.export.
"""

from __future__ import annotations

import json
import logging
import tempfile
import os
from typing import Any

from shopstack.config import settings
from shopstack.persistence.database import Database
from shopstack.schemas.models import Trace
from shopstack.traces.export import (
    create_trace as _create_trace,
    export_trace_by_id as _export_trace_by_id,
    export_traces_to_jsonl as _export_traces_to_jsonl,
    trace_payload_for_export as _trace_payload_for_export,
    create_market_lens_trace as _create_market_lens_trace,
    create_shopping_list_trace as _create_shopping_list_trace,
    create_add_purchase_trace as _create_add_purchase_trace,
    find_trace_by_id as _find_trace_by_id,
    update_trace_confirmation as _update_trace_confirmation,
    redact_trace_payload as _redact_trace_payload,
    FIELD_NOTES_CONFIG_KEY,
)

logger = logging.getLogger(__name__)

__all__ = [
    "TraceService",
]


class TraceService:
    """Encapsulates trace lifecycle: creation, retrieval, export, redaction.

    Usage::

        service = TraceService(db)
        trace = service.get_trace("trace-id")
        export_path = service.export_trace_to_jsonl("trace-id")
    """

    def __init__(self, database: Database):
        self._db = database

    # ── Retrieval ──────────────────────────────────────────────────

    def get_trace(self, trace_id: str) -> Trace | None:
        """Retrieve a single trace by ID."""
        return _find_trace_by_id(self._db, trace_id)

    def list_traces(self, limit: int | None = None) -> list[Trace]:
        """List recent traces, ordered by timestamp descending."""
        return self._db.get_traces(limit=limit or max(50, settings.trace_max_rows))

    def filter_traces(
        self,
        search: str = "",
        input_type_filter: str = "",
        limit: int | None = None,
    ) -> list[Trace]:
        """List traces filtered by search text and/or input type."""
        traces = self.list_traces(limit=limit)
        needle = search.strip().lower()
        selected = input_type_filter.strip().lower()
        if selected:
            traces = [t for t in traces if (t.input_type or "").lower() == selected]
        if needle:
            traces = [
                t
                for t in traces
                if needle in (t.user_goal or "").lower()
                or needle in (t.trace_id or "").lower()
                or needle in (t.input_type or "").lower()
            ]
        return traces

    # ── Creation ───────────────────────────────────────────────────

    def create_trace(
        self,
        input_type: str = "",
        user_goal: str = "",
        redacted_user_request: str = "",
        perception: dict | None = None,
        inventory_context: dict | None = None,
        decision: dict | None = None,
        proposed_tool_calls: list | None = None,
        final_response: str = "",
        human_confirmation: str | None = None,
        user_id: str = "",
    ) -> Trace:
        """Create a new trace record."""
        return _create_trace(
            self._db,
            input_type=input_type,
            user_goal=user_goal,
            redacted_user_request=redacted_user_request,
            perception=perception,
            inventory_context=inventory_context,
            decision=decision,
            proposed_tool_calls=proposed_tool_calls,
            final_response=final_response,
            human_confirmation=human_confirmation,
            user_id=user_id,
        )

    def create_market_lens_trace(
        self,
        items_detected: list[str] | None = None,
        audio_present: bool = False,
        image_present: bool = False,
        barcode_data: str | None = None,
        analysis_text: str = "",
        analysis_result: str = "",
        decision_items: list[dict] | None = None,
        proposed_tool_calls: list | None = None,
        human_confirmation: str | None = None,
        user_id: str = "",
    ) -> Trace:
        """Create a trace specifically for Market Lens workflow."""
        return _create_market_lens_trace(
            self._db,
            items_detected=items_detected,
            audio_present=audio_present,
            image_present=image_present,
            barcode_data=barcode_data,
            analysis_text=analysis_text,
            analysis_result=analysis_result,
            decision_items=decision_items,
            proposed_tool_calls=proposed_tool_calls,
            human_confirmation=human_confirmation,
            user_id=user_id,
        )

    # ── Export ─────────────────────────────────────────────────────

    def export_trace_to_jsonl(self, trace_id: str, redact: bool = True, user_id: str = "") -> str:
        """Export a single trace as a redacted JSONL file.

        Args:
            trace_id: The trace to export.
            redact: Whether to redact PII.
            user_id: Household ID for scoping the lookup.

        Returns the path to the exported file, or empty string on failure.
        """
        _, out_path = tempfile.mkstemp(suffix=".jsonl")
        success = _export_trace_by_id(self._db, trace_id, out_path, redact=redact, user_id=user_id)
        if not success:
            try:
                os.remove(out_path)
            except OSError:
                pass
            return ""
        return out_path

    def export_all_to_jsonl(
        self, output_path: str, limit: int = 50, redact: bool = True, user_id: str = ""
    ) -> int:
        """Export recent traces as JSONL. Returns count exported.

        Args:
            output_path: Path to write the JSONL file.
            limit: Max number of traces to export.
            redact: Whether to redact PII.
            user_id: Household ID for scoping the traces.
        """
        return _export_traces_to_jsonl(self._db, output_path, limit=limit, redact=redact, user_id=user_id)

    # ── Serialization / redaction ──────────────────────────────────

    def trace_payload(self, trace: Trace, redact: bool = True) -> dict[str, Any]:
        """Get the full trace payload dict, optionally redacted."""
        return _trace_payload_for_export(trace, redact=redact, db=self._db)

    def redact_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Apply PII redaction to a trace payload dict."""
        return _redact_trace_payload(payload)

    # ── Lifecycle ──────────────────────────────────────────────────

    def update_confirmation(self, trace_id: str, confirmation: str) -> bool:
        """Update the human_confirmation field on a trace."""
        return _update_trace_confirmation(self._db, trace_id, confirmation)

    def prune(self, max_rows: int | None = None, ttl_days: int | None = None) -> int:
        """Prune old/excess traces. Returns count removed."""
        return self._db.prune_traces(max_rows=max_rows, ttl_days=ttl_days)
