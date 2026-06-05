# Hugging Face Space Deployment

ShopStack is designed to run on Hugging Face Spaces with zero configuration.

## Setup

1. Create a new Space at [huggingface.co/spaces](https://huggingface.co/spaces)
2. Choose **Gradio** SDK
3. Set Space hardware: **CPU basic** (sufficient for mock providers)
4. If using real models, select **CPU upgrade** or **GPU (T4 small)** depending on model size

## Files

The Space will use:
- `app.py` (entry point — already compatible)
- `requirements.txt` (already includes gradio, pydantic, pydantic-settings)
- `packages.txt` (not needed for current deps)
- `setup.py` (for editable install)

## Environment Variables

Set these in Space settings:

```
SHOPSTACK_DATABASE_PATH = /app/shopstack.db
SHOPSTACK_OFF_THE_GRID = true
```

## Limits

- With mock providers: runs on free CPU tier
- With real models (e.g., Qwen 2.5 7B): requires GPU T4 small or larger
- Database is ephemeral unless mounted to persistent storage
- For persistent DB, use a Hugging Face Dataset or HF Hub file store

## Persistent Database

Add to `app.py` startup:

```python
import os
DB_PATH = os.environ.get("SHOPSTACK_DATABASE_PATH", "shopstack.db")
```

On Spaces, files persist across restarts unless the Space is rebuilt.
