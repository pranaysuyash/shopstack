"""Read-only Agent Quality panel for the existing Model Stack area."""
from __future__ import annotations

from collections import Counter
from html import escape
from typing import Any

from shopstack.ui.components.cards import card as ui_card, render_metric
from shopstack.ui.screens._utils import rows_to_html


def _latest() -> tuple[dict[str, Any] | None, list[Any]]:
    try:
        from shopstack.eval.agent.storage import AgentEvalStorage
        storage = AgentEvalStorage()
        try:
            runs = storage.runs(limit=1)
            if not runs:
                return None, []
            run = runs[0]
            return run, storage.results(run_id=run["run_id"])
        finally:
            storage.close()
    except Exception:
        return None, []


def agent_eval_view() -> str:
    run, results = _latest()
    if not run:
        return ui_card(
            "Agent Quality",
            "<div style='color:var(--text-dim);'>No scenario evaluation runs recorded yet. Run <code>python -m shopstack.eval.agent.cli run</code> to populate this read-only panel.</div>",
        )
    by_model: dict[str, list[Any]] = {}
    for result in results:
        by_model.setdefault(result.model_key, []).append(result)
    model_rows = []
    failures = Counter(code for result in results for code in result.failure_codes)
    for model, rows in sorted(by_model.items()):
        known_costs = [row.cost_usd for row in rows if row.cost_usd is not None]
        known_latency = [row.latency_ms for row in rows if row.latency_ms is not None]
        model_rows.append({
            "Model": model,
            "Cases": len(rows),
            "Success": f"{sum(row.task_success for row in rows) / len(rows):.1%}",
            "Composite": f"{sum(row.composite_score for row in rows) / len(rows):.3f}",
            "Latency": f"{sum(known_latency) / len(known_latency):.0f} ms" if known_latency else "Unknown",
            "Cost": f"${sum(known_costs):.4f}" if known_costs else "Unknown",
        })
    failure_rows = [{"Failure": code, "Count": count} for code, count in failures.most_common()]
    total = len(results)
    successes = sum(result.task_success for result in results)
    status = "PASS" if total and successes == total else "FAILURES PRESENT"
    summary = (
        "<div style='font-size:0.75rem;color:var(--text-dim);margin-bottom:8px;'>"
        f"Latest run <code>{escape(str(run['run_id'])[:12])}</code>, {total} persisted case results, decision data is advisory only."
        "</div>"
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;'>"
        f"{render_metric('Run status', status)}{render_metric('Cases', str(total))}"
        f"{render_metric('Task success', f'{successes / total:.1%}' if total else 'Unknown')}"
        f"{render_metric('Failure types', str(len(failures)))}"
        "</div>"
    )
    table = rows_to_html(model_rows, ["Model", "Cases", "Success", "Composite", "Latency", "Cost"])
    failure_table = rows_to_html(failure_rows, ["Failure", "Count"]) if failure_rows else "<div style='color:var(--text-dim);'>No failures recorded.</div>"
    return (
        summary
        + ui_card("Model comparison", table)
        + ui_card("Failure explorer", failure_table)
        + "<div style='font-size:0.6875rem;color:var(--text-dim);margin-top:8px;'>"
        "Requested model, actual provider/model, tool trace, and nullable usage remain persisted per case. This panel never starts runs or changes routing."
        "</div>"
    )
