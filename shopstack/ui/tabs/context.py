"""Tab builder context — shared dependencies passed to each top-level tab.

A TabContext holds the shared singletons (db, tools, planner, providers,
model_registry) and shared header values (APP_NAME, APP_DESCRIPTION). Tab
builders receive a TabContext and the parent gr.Blocks, add their UI
elements inside a `gr.Tab` block, and return a TabHandles dataclass exposing
any components that other parts of the app need to reference (e.g. the
household-switch wiring in app.py reads back the Today tab's output
components).

Why a plain class (not a frozen dataclass):
- The shared singletons include mutable structures (e.g. `model_registry`
  is a list of model entries). A frozen dataclass would require those
  fields to be hashable, which they are not.
- The "frozen" guarantee is a convention here, not a hard invariant. Tab
  builders are expected to treat TabContext as read-only; the type system
  does not enforce it.
- If/when we need true immutability, we can add `__setattr__` overrides
  here or switch to a Pydantic model.
"""
from __future__ import annotations

import gradio as gr  # noqa: F401  (re-exported for type hints in tab builders)

from shopstack.app_context import (
    APP_DESCRIPTION,
    APP_NAME,
    db,
    model_registry,
    planner,
    providers,
    tools,
)
from shopstack.config import settings


class TabContext:
    """Shared dependencies for tab builders.

    Treat as read-only. Tab builders receive one and use it to access the
    long-lived singletons; they should not mutate the attributes.
    """

    __slots__ = (
        "app_name",
        "app_description",
        "db",
        "providers",
        "tools",
        "planner",
        "model_registry",
        "settings",
        "home_flow_state",
    )

    def __init__(self) -> None:
        self.app_name: str = APP_NAME
        self.app_description: str = APP_DESCRIPTION
        self.db = db
        self.providers = providers
        self.tools = tools
        self.planner = planner
        self.model_registry = model_registry
        self.settings = settings
        # Home-flow state (Group G, 2026-06-15). Set by app.build_app()
        # after the household context is established. Tabs that
        # care about onboarding state read this field; tabs that
        # don't (the default) ignore it. None means "not yet
        # computed" — callers should fall back to detect-on-demand.
        self.home_flow_state: object | None = None

