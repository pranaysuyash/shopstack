"""CLI launch entry point for ShopStack.

Extracted from ``app.py`` so the composition layer (``app.build_app``)
stays under the 300-line per-file budget enforced by
``tests/test_app_composition.py::test_app_py_under_300_lines``.

The ``__main__`` block in ``app.py`` is the only consumer. The
behaviour is identical to the inlined version that was here
before; this module just gives it a home.

Per motto_v3 §11 (hide, not delete): the inlined version
inside ``app.py`` is replaced by a thin import + delegation
line so the composition file stays focused on wiring.
"""
from __future__ import annotations

import argparse

import gradio as gr

from app import build_app
from shopstack.ui.header import pwa_head_html
from shopstack.ui.theme import CSS


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "ShopStack — local-first shopping intelligence platform. "
            "Runs the Gradio Blocks app on the configured port."
        ),
    )
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    app = build_app()
    app.launch(
        server_port=args.port,
        share=args.share,
        theme=gr.themes.Base(),
        head=pwa_head_html(),
        css=CSS,
        prevent_thread_lock=True,
    )
    app.block_thread()


if __name__ == "__main__":
    main()
