from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from shopstack.api.v1.deps import HouseholdContext, require_household

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portability", tags=["portability"])


class ExportResponse(BaseModel):
    schema_version: str
    exported_at: str
    export_type: str
    inventory: list[dict]
    price_observations: list[dict]
    field_notes: str


class ImportRequest(BaseModel):
    data: dict
    import_mode: str = "merge"


class ImportResponse(BaseModel):
    items_added: int
    items_updated: int
    price_observations_added: int
    errors: list[str]
    messages: list[str]


class ValidateRequest(BaseModel):
    data: dict


class ValidateResponse(BaseModel):
    items_added: int
    items_updated: int
    price_observations_added: int
    errors: list[str]
    messages: list[str]


@router.get(
    "/export",
    response_model=ExportResponse,
    summary="Export all household data as JSON",
)
def export_data(
    ctx: HouseholdContext = Depends(require_household),
) -> ExportResponse:
    from shopstack.app_context import db
    from shopstack.portability import export_backup

    try:
        export = export_backup(db)
        return ExportResponse(
            schema_version=export.get("schema_version", "1.0"),
            exported_at=export.get("exported_at", ""),
            export_type=export.get("export_type", "household_backup"),
            inventory=export.get("inventory", []),
            price_observations=export.get("price_observations", []),
            field_notes=export.get("field_notes", ""),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Export failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "export_failed", "message": str(exc)},
        )


@router.post(
    "/import",
    response_model=ImportResponse,
    status_code=status.HTTP_200_OK,
    summary="Import household data from JSON",
)
def import_data(
    body: ImportRequest,
    ctx: HouseholdContext = Depends(require_household),
) -> ImportResponse:
    from shopstack.app_context import db
    from shopstack.portability import import_json

    try:
        result = import_json(db, body.data, import_mode=body.import_mode)
        return ImportResponse(
            items_added=result.items_added,
            items_updated=result.items_updated,
            price_observations_added=result.price_observations_added,
            errors=result.errors,
            messages=result.messages,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Import failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "import_failed", "message": str(exc)},
        )


@router.post(
    "/validate",
    response_model=ValidateResponse,
    summary="Dry-run import validation (reports changes without writing)",
)
def validate_import(
    body: ValidateRequest,
    ctx: HouseholdContext = Depends(require_household),
) -> ValidateResponse:
    from shopstack.app_context import db
    from shopstack.portability import validate_import_json

    try:
        result = validate_import_json(db, body.data)
        return ValidateResponse(
            items_added=result.items_added,
            items_updated=result.items_updated,
            price_observations_added=result.price_observations_added,
            errors=result.errors,
            messages=result.messages,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Validate import failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "validate_failed", "message": str(exc)},
        )


@router.get(
    "/export/csv",
    summary="Export inventory as CSV",
)
def export_csv(
    ctx: HouseholdContext = Depends(require_household),
):
    from fastapi.responses import PlainTextResponse

    from shopstack.app_context import db
    from shopstack.portability import export_csv_inventory as export_csv

    try:
        csv_text = export_csv(db)
        return PlainTextResponse(
            content=csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=shopstack_inventory.csv"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("CSV export failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "csv_export_failed", "message": str(exc)},
        )


@router.post(
    "/import/csv",
    summary="Import inventory from CSV",
)
def import_csv_endpoint(
    body: dict,
    ctx: HouseholdContext = Depends(require_household),
) -> ImportResponse:
    from shopstack.app_context import db
    from shopstack.portability import import_csv

    csv_text = body.get("csv_text", "")
    if not csv_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "csv_text_required"},
        )

    try:
        result = import_csv(db, csv_text)
        return ImportResponse(
            items_added=result.items_added,
            items_updated=result.items_updated,
            price_observations_added=result.price_observations_added,
            errors=result.errors,
            messages=result.messages,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("CSV import failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "csv_import_failed", "message": str(exc)},
        )


__all__ = ["router"]
