"""Storage sinks for the o/p eval record (EVAL-OP-1).

Two sinks, one schema, never diverge:

* :class:`JsonlSink` — append-only JSONL, one record per line, lives
  in the repo root as ``.model_call_records.jsonl`` (gitignored).
  Use for offline replay, deep dives, and dataset curation.
* :class:`SqliteSink` — flat SQLite table in the existing
  ``shopstack.db`` (or a test override). Indexed for fast per-route
  and per-model queries; powers the UI dashboard.

Both sinks are write-only during capture. Reads live in
:mod:`shopstack.eval.aggregator`.

Sinks are best-effort: every method swallows its own exception and
logs. The recorder is the last line of defense; sinks must never
break a model call.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from shopstack.eval.recorder import ModelCallRecord

logger = logging.getLogger(__name__)


# Repo-root path. The JSONL sits next to .bench_results.jsonl.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_JSONL_PATH = _REPO_ROOT / ".model_call_records.jsonl"


# DDL — the canonical table shape. Bump the suffix in
# ``eval_records_schema_version`` whenever columns change.
EVAL_RECORDS_SCHEMA_VERSION = 2
EVAL_RECORDS_DDL = """
CREATE TABLE IF NOT EXISTS model_call_records (
    record_id          TEXT PRIMARY KEY,
    trace_id           TEXT DEFAULT '',
    user_id            TEXT DEFAULT '',
    household_id       TEXT DEFAULT '',
    started_at         TEXT NOT NULL,
    domain_route       TEXT NOT NULL,
    code_route         TEXT DEFAULT '',
    capability         TEXT DEFAULT '',
    capability_shape   TEXT DEFAULT 'raw',
    model              TEXT DEFAULT '',
    backend            TEXT DEFAULT '',
    provider_name      TEXT DEFAULT '',
    prompt             TEXT DEFAULT '',
    output             TEXT DEFAULT '',
    prompt_length      INTEGER DEFAULT 0,
    output_length      INTEGER DEFAULT 0,
    latency_ms         REAL DEFAULT 0.0,
    input_tokens       INTEGER DEFAULT 0,
    output_tokens      INTEGER DEFAULT 0,
    cost_usd           REAL DEFAULT 0.0,
    outcome            TEXT NOT NULL DEFAULT 'success',
    error              TEXT DEFAULT '',
    execution_meta     TEXT DEFAULT '{}',
    eval_passed        INTEGER NOT NULL DEFAULT 1,
    eval_score         REAL DEFAULT 1.0,
    eval_check_results TEXT DEFAULT '[]',
    schema_version     INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_mcr_domain_started
    ON model_call_records (domain_route, started_at);
CREATE INDEX IF NOT EXISTS idx_mcr_capability_model
    ON model_call_records (capability, model);
CREATE INDEX IF NOT EXISTS idx_mcr_household_started
    ON model_call_records (household_id, started_at);
CREATE INDEX IF NOT EXISTS idx_mcr_outcome_started
    ON model_call_records (outcome, started_at);
"""


def _row_to_columns(record: ModelCallRecord) -> tuple:
    """Map a ModelCallRecord to a positional tuple matching EVAL_RECORDS_DDL."""
    return (
        record.record_id,
        record.trace_id,
        record.user_id,
        record.household_id,
        record.started_at,
        record.domain_route,
        record.code_route,
        record.capability,
        record.capability_expected_shape,
        record.model,
        record.backend,
        record.provider_name,
        record.prompt,
        record.output,
        record.prompt_length,
        record.output_length,
        record.latency_ms,
        record.input_tokens,
        record.output_tokens,
        record.cost_usd,
        record.outcome,
        record.error,
        json.dumps(record.execution, default=str, ensure_ascii=False),
        1 if record.eval_passed else 0,
        record.eval_score,
        json.dumps([c.to_dict() for c in record.eval_check_results]),
        EVAL_RECORDS_SCHEMA_VERSION,
    )


_INSERT_SQL = """
INSERT OR REPLACE INTO model_call_records (
    record_id, trace_id, user_id, household_id, started_at,
    domain_route, code_route, capability, capability_shape,
    model, backend, provider_name,
    prompt, output, prompt_length, output_length,
    latency_ms, input_tokens, output_tokens, cost_usd,
    outcome, error, execution_meta, eval_passed, eval_score, eval_check_results,
    schema_version
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class JsonlSink:
    """Append-only JSONL sink. Thread-safe via a single lock."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_JSONL_PATH
        self._lock = threading.Lock()

    def write(self, record: ModelCallRecord) -> None:
        line = json.dumps(record.to_dict(), default=str, ensure_ascii=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def read_all(self) -> Iterable[dict[str, Any]]:
        """Yield every record as a dict. Used by tests and offline replay."""
        if not self.path.exists():
            return
        with open(self.path, encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if raw:
                    try:
                        yield json.loads(raw)
                    except json.JSONDecodeError:
                        continue

    def clear(self) -> None:
        """Remove the file entirely. Tests use this between cases."""
        with self._lock:
            if self.path.exists():
                self.path.unlink()


class SqliteSink:
    """SQLite sink writing into the existing ``shopstack.db``.

    The connection is per-thread (same convention as the main
    ``Database`` class — see ``persistence/database.py``) and lazily
    created so importing this module never opens the database.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path: str | None = (
            str(db_path) if db_path is not None else None
        )
        self._local = threading.local()
        self._init_lock = threading.Lock()
        self._schema_ready = False

    def _resolve_db_path(self) -> str:
        if self._db_path is not None:
            return self._db_path
        # Lazy import — config import is not free and not every
        # caller has settings available at construction.
        from shopstack.config import settings
        return settings.db_path

    @property
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            path = self._resolve_db_path()
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            c = sqlite3.connect(path, check_same_thread=True)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            self._local.conn = c
        if not self._schema_ready:
            self._ensure_schema(c)
            self._schema_ready = True
        return c

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        with self._init_lock:
            conn.executescript(EVAL_RECORDS_DDL)
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(model_call_records)").fetchall()
            }
            if "execution_meta" not in columns:
                conn.execute(
                    "ALTER TABLE model_call_records ADD COLUMN execution_meta TEXT DEFAULT '{}'"
                )
            conn.commit()

    def write(self, record: ModelCallRecord) -> None:
        try:
            self.conn.execute(_INSERT_SQL, _row_to_columns(record))
            self.conn.commit()
        except sqlite3.Error:
            logger.warning("sqlite sink write failed", exc_info=True)

    def write_many(self, records: Iterable[ModelCallRecord]) -> None:
        rows = [_row_to_columns(r) for r in records]
        if not rows:
            return
        try:
            self.conn.executemany(_INSERT_SQL, rows)
            self.conn.commit()
        except sqlite3.Error:
            logger.warning("sqlite sink write_many failed", exc_info=True)

    # ----- read helpers (used by aggregator + UI) -----

    def query(
        self,
        domain_route: str | None = None,
        capability: str | None = None,
        model: str | None = None,
        since_iso: str | None = None,
        limit: int = 1000,
        trace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM model_call_records WHERE 1=1"
        params: list[Any] = []
        if domain_route:
            sql += " AND domain_route = ?"
            params.append(domain_route)
        if capability:
            sql += " AND capability = ?"
            params.append(capability)
        if model:
            sql += " AND model = ?"
            params.append(model)
        if trace_id:
            sql += " AND trace_id = ?"
            params.append(trace_id)
        if since_iso:
            sql += " AND started_at >= ?"
            params.append(since_iso)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(int(limit))
        cur = self.conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    def count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) AS n FROM model_call_records")
        return int(cur.fetchone()["n"])

    def delete_older_than(self, ttl_days: int) -> int:
        """Prune records older than ``ttl_days``. Returns rows deleted."""
        cur = self.conn.execute(
            "DELETE FROM model_call_records "
            "WHERE datetime(started_at) < datetime('now', ?)",
            (f"-{int(ttl_days)} days",),
        )
        self.conn.commit()
        return int(cur.rowcount or 0)


__all__ = [
    "DEFAULT_JSONL_PATH",
    "EVAL_RECORDS_DDL",
    "EVAL_RECORDS_SCHEMA_VERSION",
    "JsonlSink",
    "SqliteSink",
]
