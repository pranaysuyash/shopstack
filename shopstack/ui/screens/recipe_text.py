"""Screen function: paste recipe ingredients → shopping list.

The Phase 3 #8 build (photo-of-recipe → shopping list) takes the form
of a *text input* in v1 — the user pastes the ingredients section
of a recipe, the parser (in ``shopstack.services.recipe_text_parser``)
turns it into structured rows, and the screen diffs against the
household's inventory to surface what's missing.

This module provides THREE Gradio-friendly entry points:

  * :func:`recipe_text_to_shopping_list` — read-only diff view
    (the original v1; renders a "have / need" table for the user
    to read).
  * :func:`recipe_text_add_missing_to_list` — one-click action
    that pushes the missing ingredients into the active shopping
    list and returns a status toast (added 2026-06-13; closes the
    loop the v1 left open).
  * :func:`recipe_image_to_text` — v2: takes a photo of a recipe
    (or a .txt file), runs it through the OCR pipeline
    (``shopstack.services.ocr_pipeline``), and returns the extracted
    text so the user can review and then click the v1 buttons to
    parse/diff/add. Closes the "OCR image upload is future work"
    note from the v1 docstring.

The three functions are intentionally composed: the v1 text view
takes whatever the v2 OCR step produces, so the user can snap a
photo, see the OCR result, edit if needed, then click "Parse &
Diff" / "Add missing to my list" without re-pasting.
"""

from __future__ import annotations

import logging
import os
from html import escape
from typing import Any

from shopstack.app_context import db, tools, providers
from shopstack.repos.inventory import InventoryRepo
from shopstack.services.ocr_pipeline import run_ocr_pipeline
from shopstack.services.recipe_text_parser import parse_recipe_text, text_to_shopping_items
from shopstack.services.recipes import missing_to_shopping_items
from shopstack.ui.components.primitives import toast
from shopstack.persistence.database import Database as _Database
from shopstack.schemas.models import ShoppingListItem

logger = logging.getLogger(__name__)


def recipe_text_to_shopping_list(raw_text: str) -> str:
    """Parse pasted recipe text and return a shopping-list-ready HTML view.

    Output shows the parsed rows plus a "missing" subset (against current
    inventory). To actually create the list, the user can paste the
    missing list into the shopping-list form, or future work can wire a
    one-click "Add missing to list" button.
    """
    if not raw_text or not raw_text.strip():
        return (
            "home_card(body='"
            "Paste a recipe's ingredients section. Example:<br>"
            "<code style='font-size: 0.75rem;'>"
            "- 2 cups rice<br>- 1 cup chickpea<br>- 1 tsp turmeric"
            "</code>', style='text-align:center;padding:16px;color:var(--text-dim);')"
        )

    parsed = parse_recipe_text(raw_text)
    if not parsed:
        return toast("Couldn't parse any ingredients from that text.", kind="warning")

    # Build a lookup of what the household has on hand
    inventory_repo = InventoryRepo(db)
    lots = db.get_inventory(user_id=_active_household_id())
    have_map: dict[str, float] = {}
    for lot in lots:
        cname = (lot.canonical_name or "").strip().lower()
        if not cname:
            continue
        have_map[cname] = have_map.get(cname, 0.0) + float(lot.quantity or 0)

    # Build the rows
    rows: list[str] = []
    missing_count = 0
    have_count = 0
    for p in parsed:
        name = escape(p.canonical_name.replace("_", " ").title())
        have = have_map.get(p.canonical_name, 0.0)
        status = "have" if have > 0 else "missing"
        if have > 0:
            have_count += 1
        else:
            missing_count += 1
        status_color = "var(--green)" if status == "have" else "var(--red)"
        status_label = "✓ have" if status == "have" else "✗ need"
        rows.append(
            f"<tr><td style='padding:4px 8px;border-bottom:1px solid var(--border);'>{name}</td>"
            f"<td style='padding:4px 8px;border-bottom:1px solid var(--border);text-align:right;'>{p.quantity:g} {escape(p.unit)}</td><td style='padding:4px 8px;border-bottom:1px solid var(--border);text-align:right;color:{status_color};'>{status_label}</td>"
            f"</tr>"
        )

    return (
        f"home_card(body='<h3 style='margin:0 0 8px 0;'>📋 Recipe → Shopping List</h3>"
            f"<div style='font-size: 0.6875rem;color:var(--text-dim);margin-bottom:6px;'>Parsed {len(parsed)} ingredient(s). {have_count} at home, "
            f"<strong style='color:var(--red);'>{missing_count} to buy</strong>.')"
        f"<table style='width:100%;font-size: 0.75rem;border-collapse:collapse;'><thead><tr style='border-bottom:2px solid var(--border);'>"
        f"<th style='text-align:left;padding:4px 8px;'>Item</th><th style='text-align:right;padding:4px 8px;'>Qty</th>"
        f"<th style='text-align:right;padding:4px 8px;'>Status</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        f"</div>"
    )


def _active_household_id() -> str:
    from shopstack.app_context import current_user_id
    return current_user_id()


def recipe_text_add_missing_to_list(raw_text: str) -> str:
    """Parse ``raw_text``, add missing ingredients to the active shopping list.

    Closes the loop that the original v1 left open: the user pastes
    a recipe, taps this button, and the missing items show up in
    their shopping list with a status toast confirming the count.

    Flow:
      1. Parse the text via :func:`text_to_shopping_items` (the
         same canonical-name-aware parser the diff view uses).
      2. Compute the household's current pantry to filter out
         items the user already has.
      3. Resolve the active shopping list (auto-create if none
         exists, mirroring :func:`cookbook.shop_missing`).
      4. Insert each missing item via ``db.add_list_item``.
      5. Return a toast with the count and a one-line summary.

    Best-effort: any DB error returns an error toast so the UI
    never crashes. The original v1 doc's "user can paste the
    missing list into the shopping-list form" is now unnecessary
    — the action does it in one click.

    Args:
        raw_text: Free-form recipe ingredients (the same input
            the diff view parses).

    Returns:
        HTML status string for the Gradio HTML output component.
    """
    if not raw_text or not raw_text.strip():
        return toast("Paste a recipe first.", kind="warning")

    # Step 1: parse to canonical shopping items
    try:
        items = text_to_shopping_items(raw_text)
    except Exception as exc:
        logger.warning("recipe_text_add_missing_to_list: parse failed: %s", exc)
        return toast(f"Couldn't parse that recipe: {exc}", kind="error")
    if not items:
        return toast(
            "No ingredients detected in that text. Try a list with lines like "
            "'- 2 cups rice' or '- 1 onion'.",
            kind="warning",
        )

    # Step 2: figure out what the household already has, so we only add missing
    try:
        uid = _active_household_id()
        have_map: dict[str, float] = {}
        for lot in db.get_inventory(user_id=uid):
            cname = (lot.canonical_name or "").strip().lower()
            if not cname:
                continue
            have_map[cname] = have_map.get(cname, 0.0) + float(lot.quantity or 0)
        # Reuse the cookbook matcher to get the structured miss/have split.
        from shopstack.services.recipes import Recipe as _Recipe
        from shopstack.services.recipes import RecipeIngredient as _Ing
        # Build a synthetic single-recipe Recipe to feed the cookbook matcher.
        # This gives us a "consistent missing-only" computation.
        synthetic = _Recipe(
            id="__recipe_text__",
            name="Recipe Text",
            cuisine="",
            dietary=[],
            prep_minutes=0,
            cook_minutes=0,
            serves=1,
            tags=[],
            ingredients=[
                _Ing(canonical_name=str(it.get("canonical_name", "")).strip().lower(),
                     quantity=float(it.get("requested_quantity") or 1),
                     unit=str(it.get("unit") or "unit"))
                for it in items
            ],
            instructions=[],
        )
        # Translate the household's have_map into synthetic InventoryLot-like
        # objects so the matcher's lookup works.
        from dataclasses import dataclass
        @dataclass
        class _Lot:
            canonical_name: str
            quantity: float
        synthetic_inv = [_Lot(canonical_name=k, quantity=v) for k, v in have_map.items()]
        from shopstack.services.recipes import match_recipe as _match_recipe
        match = _match_recipe(synthetic, synthetic_inv, None)
        missing_items = [
            {
                "canonical_name": ing.canonical_name,
                "requested_quantity": ing.quantity,
                "unit": ing.unit,
            }
            for ing in match.missing
        ]
    except Exception as exc:
        logger.warning("recipe_text_add_missing_to_list: diff failed: %s", exc)
        # If the diff fails, fall back to adding ALL parsed items
        # (the user can de-dup manually).
        missing_items = items

    if not missing_items:
        return toast(
            "✓ You already have every ingredient for that recipe. Nothing to add.",
            kind="success",
        )

    # Step 3: resolve the active shopping list (auto-create if needed)
    try:
        active = db.get_active_shopping_list(user_id=uid)
        list_id = active.list_id if active else None
        if not list_id:
            new_list = db.create_shopping_list(
                name="Shopping List",
                goal=f"Auto-created from recipe text",
                user_id=uid,
            )
            list_id = new_list.list_id
    except Exception as exc:
        logger.warning("recipe_text_add_missing_to_list: list resolve failed: %s", exc)
        return toast(
            f"Could not resolve a shopping list: {exc}",
            kind="error",
        )

    # Step 4: insert each missing item (idempotent — skip if already on list)
    existing_names = _existing_list_canonical_names(db, list_id)
    added = 0
    skipped = 0
    for it in missing_items:
        cname = (it.get("canonical_name") or "").strip()
        if not cname:
            continue
        if cname.lower() in existing_names:
            skipped += 1
            continue
        try:
            db.add_list_item(
                list_id=list_id,
                item=ShoppingListItem(
                    canonical_name=cname,
                    requested_quantity=float(it.get("requested_quantity") or 1),
                    unit=it.get("unit") or "unit",
                ),
            )
            added += 1
            existing_names.add(cname.lower())
        except Exception as exc:
            logger.debug("add_list_item failed for %s: %s", cname, exc)

    if added == 0 and skipped == 0:
        return toast(
            "⚠ Nothing new to add (some ingredients may already be on the list).",
            kind="warning",
        )
    if added == 0:
        return toast(
            f"✓ All {skipped} ingredient{'s' if skipped != 1 else ''} already on your list — nothing new to add.",
            kind="success",
        )
    sample = ", ".join(
        (it.get("canonical_name") or "").replace("_", " ").title()
        for it in missing_items[:3]
    )
    more = "" if len(missing_items) <= 3 else f" (+{len(missing_items) - 3} more)"
    skip_note = f" ({skipped} already on list)" if skipped else ""
    return toast(
        f"✓ Added {added} missing item{'s' if added != 1 else ''} to your shopping list: {sample}{more}{skip_note}.",
        kind="success",
    )


def _existing_list_canonical_names(db: Any, list_id: str) -> set[str]:
    """Return the set of lowercase canonical_names already on the shopping list.

    Used by :func:`recipe_text_add_missing_to_list` (and any future
    "add to list" action) for idempotency. Calling the action twice
    with the same recipe no longer duplicates items.

    Defensive:
      * Returns an empty set on any DB error (caller proceeds, may
        duplicate — better than failing the user-visible action).
      * Strips + lowercases the canonical names so "Chickpea" and
        "chickpea" are treated as the same item.

    Args:
        db: The Database (or a fake with the same interface).
        list_id: The shopping list to scan.

    Returns:
        A set of lowercase canonical_names already in the list.
    """
    try:
        conn = getattr(db, "conn", None)
        if conn is None:
            return set()
        rows = conn.execute(
            "SELECT canonical_name FROM shopping_list_items WHERE list_id = ?",
            (list_id,),
        ).fetchall()
        return {(row[0] or "").strip().lower() for row in rows if row and row[0]}
    except Exception:
        return set()


# ── v2: image upload + OCR (added 2026-06-13) ──────────────────────────


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif")


def _resolve_file_path(file_input: Any) -> str:
    """Resolve a Gradio file input to a local filesystem path.

    Gradio's ``gr.File`` returns a tempfile.NamedTemporaryFile object
    on Python 3.7+; we accept either the file object (use ``.name``),
    a string (treat as path), or ``None`` (no upload).
    """
    if not file_input:
        return ""
    if isinstance(file_input, str):
        return file_input
    if hasattr(file_input, "name"):
        return str(file_input.name)
    return str(file_input)


def recipe_image_to_text(file_input: Any) -> tuple[str, str]:
    """v2: Extract recipe text from an uploaded image or text file.

    The user uploads a photo of a recipe (or a .txt file), clicks
    "Snap & parse recipe", and the result is the extracted text
    pre-populated into the existing ``recipe_input`` Textbox. The
    user can then click "Parse & Diff" or "Add missing to my list"
    (the v1 actions) to act on it.

    Returns a ``(recipe_text, status_html)`` tuple:
      * ``recipe_text`` — the extracted text (empty on failure)
      * ``status_html`` — a toast indicating success / failure

    Failure modes (all caught, never raise):
      * No file uploaded → warning toast
      * Unsupported file type → warning toast
      * File not found / unreadable → error toast
      * OCR pipeline returns ``{"error": ...}`` → error toast
      * OCR returns empty text → warning toast

    The OCR pipeline used is :func:`shopstack.services.ocr_pipeline.
    run_ocr_pipeline`, which tries GLM-OCR (primary) → preprocess
    + retry → Tesseract (fallback). On real photos the preprocessed
    fallback is the most reliable path.
    """
    file_path = _resolve_file_path(file_input)
    if not file_path:
        return "", toast(
            "Upload a recipe image (.png, .jpg, .webp) or a .txt file first.",
            kind="warning",
        )

    if not os.path.isfile(file_path):
        return "", toast(
            f"File not found: {escape(file_path)}",
            kind="error",
        )

    file_lower = file_path.lower()

    # Branch 1: .txt / .csv — just read the file directly.
    if file_lower.endswith((".txt", ".csv", ".md")):
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                raw_text = f.read()
        except Exception as exc:
            logger.warning("recipe_image_to_text: read failed: %s", exc)
            return "", toast(f"Failed to read file: {exc}", kind="error")
        if not raw_text.strip():
            return "", toast(
                "The uploaded text file is empty.",
                kind="warning",
            )
        return raw_text, toast(
            f"✓ Loaded {len(raw_text)} characters from text file. "
            "Click 'Parse & Diff' to see what's missing.",
            kind="success",
        )

    # Branch 2: image — run through the OCR pipeline.
    if not file_lower.endswith(_IMAGE_EXTS):
        return "", toast(
            f"Unsupported file type: {escape(os.path.basename(file_path))}. "
            "Use .png, .jpg, .jpeg, .webp, .bmp, or .txt.",
            kind="warning",
        )

    try:
        ocr_result = run_ocr_pipeline(
            file_path, providers, enable_preprocessing=True
        )
    except Exception as exc:
        logger.warning("recipe_image_to_text: OCR raised: %s", exc)
        return "", toast(
            f"OCR failed: {exc}. Try a clearer photo or a .txt file.",
            kind="error",
        )

    if "error" in ocr_result:
        return "", toast(
            f"OCR could not read the image: {escape(str(ocr_result['error']))}. "
            "Try a clearer photo or paste the text directly.",
            kind="error",
        )

    raw_text = ocr_result.get("text", "") or ocr_result.get("raw_text", "")
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return "", toast(
            "OCR ran successfully but found no text in the image. "
            "Try a clearer photo, better lighting, or paste the text directly.",
            kind="warning",
        )

    # Success — include OCR metadata in the toast so the user knows
    # which pipeline stage succeeded (and how long it took).
    model = ocr_result.get("model", "?")
    stage = ocr_result.get("pipeline_stage", "?")
    latency = ocr_result.get("latency_ms", 0)
    status = toast(
        f"✓ Extracted {len(raw_text)} characters via {model} ({stage}, {latency:.0f}ms). "
        "Review the text below, then click 'Parse & Diff' or 'Add missing to my list'.",
        kind="success",
    )
    return raw_text, status


__all__ = [
    "recipe_text_to_shopping_list",
    "recipe_text_add_missing_to_list",
    "recipe_image_to_text",
]
