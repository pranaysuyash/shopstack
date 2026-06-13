# Tools

Reusable scripts that are meant to be run from the repo root.

## `sync-readme-stats`

Updates `README.md` with live test and benchmark totals from the current repo.

Usage:

```bash
./tools/sync-readme-stats
```

## `model_lab_frontier.py`

Runs the ShopStack frontier planner sweep against current Hugging Face models and writes:

- a JSONL results file
- a markdown summary report

Default models:

- `qwen3.5-9b` -> `Qwen/Qwen3.5-9B`
- `qwen3.6-35b-a3b` -> `Qwen/Qwen3.6-35B-A3B`

Usage:

```bash
uv run python tools/model_lab_frontier.py
```

Override the output directory:

```bash
SHOPSTACK_MODEL_LAB_OUTPUT_DIR=benchmarks/model_lab/results uv run python tools/model_lab_frontier.py
```

Override the models:

```bash
uv run python tools/model_lab_frontier.py --model qwen3.5-9b --model qwen3.6-35b-a3b
```
