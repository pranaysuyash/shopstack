"""Persistence for scenario runs, separate from model-call records."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from shopstack.eval.agent.schema import EvalCaseResult, EvalRunMetadata


DDL = """
CREATE TABLE IF NOT EXISTS agent_eval_runs (
  run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, ended_at TEXT,
  suite_version INTEGER NOT NULL, scenario_count INTEGER NOT NULL,
  policy_version INTEGER NOT NULL, metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_eval_case_results (
  run_id TEXT NOT NULL, scenario_id TEXT NOT NULL, model_key TEXT NOT NULL,
  requested_model TEXT NOT NULL, actual_model TEXT, backend TEXT, provider TEXT,
  trace_id TEXT NOT NULL, status TEXT NOT NULL, task_success INTEGER NOT NULL,
  composite_score REAL NOT NULL, metrics_json TEXT NOT NULL,
  tool_calls_json TEXT NOT NULL, assertions_json TEXT NOT NULL,
  failure_codes_json TEXT NOT NULL, latency_ms REAL, input_tokens INTEGER,
  output_tokens INTEGER, cost_usd REAL, planner_outcome TEXT, error TEXT,
  PRIMARY KEY (run_id, scenario_id, model_key),
  FOREIGN KEY (run_id) REFERENCES agent_eval_runs(run_id)
);
CREATE INDEX IF NOT EXISTS idx_agent_eval_case_model ON agent_eval_case_results(model_key);
CREATE INDEX IF NOT EXISTS idx_agent_eval_case_scenario ON agent_eval_case_results(scenario_id);
CREATE INDEX IF NOT EXISTS idx_agent_eval_case_success ON agent_eval_case_results(task_success);
"""


class AgentEvalStorage:
    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            from shopstack.config import settings
            db_path = settings.db_path
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(DDL)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def save_run(self, metadata: EvalRunMetadata) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO agent_eval_runs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (metadata.run_id, metadata.started_at, metadata.ended_at, metadata.suite_version,
             metadata.scenario_count, metadata.policy_version, metadata.model_dump_json()),
        )
        self.conn.commit()

    def save_case(self, result: EvalCaseResult) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO agent_eval_case_results VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (result.run_id, result.scenario_id, result.model_key, result.requested_model,
             result.actual_model, result.backend, result.provider, result.trace_id,
             result.status.value, int(result.task_success), result.composite_score,
             result.metrics.model_dump_json(), json.dumps([row.model_dump() for row in result.tool_calls], default=str),
             json.dumps(result.assertions, default=str), json.dumps(result.failure_codes),
             result.latency_ms, result.input_tokens, result.output_tokens, result.cost_usd,
             result.planner_outcome, result.error),
        )
        self.conn.commit()

    def save(self, metadata: EvalRunMetadata, results: list[EvalCaseResult]) -> None:
        self.save_run(metadata)
        for result in results:
            self.save_case(result)

    def runs(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM agent_eval_runs ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def results(self, run_id: str | None = None, model_key: str | None = None, limit: int = 5000) -> list[EvalCaseResult]:
        sql = "SELECT * FROM agent_eval_case_results WHERE 1=1"
        params: list[Any] = []
        if run_id:
            sql += " AND run_id = ?"
            params.append(run_id)
        if model_key:
            sql += " AND model_key = ?"
            params.append(model_key)
        sql += " ORDER BY scenario_id LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        from shopstack.eval.agent.schema import MetricScores, ToolCallEvidence
        output: list[EvalCaseResult] = []
        for row in rows:
            data = dict(row)
            data["status"] = data["status"]
            data["task_success"] = bool(data["task_success"])
            data["metrics"] = MetricScores.model_validate(json.loads(data.pop("metrics_json")))
            data["tool_calls"] = [ToolCallEvidence.model_validate(item) for item in json.loads(data.pop("tool_calls_json"))]
            data["assertions"] = json.loads(data.pop("assertions_json"))
            data["failure_codes"] = json.loads(data.pop("failure_codes_json"))
            output.append(EvalCaseResult.model_validate(data))
        return output
