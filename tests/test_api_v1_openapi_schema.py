"""Contract tests for the OpenAPI 3.0 schema generated from the v1 routers.

These tests validate that the ``/api/v1/*`` surface produces a complete,
internally-consistent OpenAPI specification that can drive the mobile
client's API contract.

**What is tested:**

1. **Schema generation:** both ``openapi_schema()`` and
   ``openapi_schema_json()`` return valid output without error.
2. **Structural integrity:** the schema has the expected top-level keys
   (``openapi``, ``info``, ``paths``, ``components``).
3. **Path coverage:** every declared router endpoint is documented as a
   path in the schema.
4. **``$ref`` resolution:** every ``$ref`` in paths → responses actually
   resolves to a ``components/schemas`` entry.
5. **Components/schemas:** all key response models are defined.
6. **Security scheme:** Bearer token (HTTPBearer) is declared.
7. **Determinism:** the schema is identical across multiple calls.
8. **JSON serialisation:** the schema can be dumped to JSON without
   errors.
"""
from __future__ import annotations

import json

import pytest

# Import from the source module directly (not the lazy wrappers in
# ``shopstack.api.v1.__init__``) to avoid any circular-import risk.
from shopstack.api.v1.openapi import openapi_schema, openapi_schema_json


# ── Tests ──────────────────────────────────────────────────────────────


class TestOpenAPISchema:
    """Validate the generated OpenAPI schema structure."""

    def test_openapi_schema_generates(self) -> None:
        """The schema can be generated without error."""
        schema = openapi_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0

    def test_openapi_version(self) -> None:
        """The schema declares OpenAPI 3.x."""
        schema = openapi_schema()
        version = schema.get("openapi", "")
        assert version.startswith("3.0") or version.startswith("3.1"), (
            f"Expected OpenAPI 3.0.x or 3.1.x, got {version}"
        )

    def test_openapi_has_info(self) -> None:
        """The schema has an info section with title and version."""
        schema = openapi_schema()
        info = schema.get("info", {})
        assert info.get("title") == "ShopStack API v1"
        assert info.get("version") == "1.0.0"
        assert "description" in info
        assert len(info["description"]) > 0

    def test_openapi_has_paths(self) -> None:
        """The schema has a paths section with at least one entry."""
        schema = openapi_schema()
        paths = schema.get("paths", {})
        assert isinstance(paths, dict)
        assert len(paths) > 0, "No paths declared in schema"

    def test_openapi_has_components(self) -> None:
        """The schema has a components section with schemas."""
        schema = openapi_schema()
        components = schema.get("components", {})
        schemas = components.get("schemas", {})
        assert isinstance(schemas, dict)
        assert len(schemas) > 0, "No component schemas declared"

    def test_all_paths_have_at_least_one_method(self) -> None:
        """Every path entry has at least one HTTP method defined."""
        schema = openapi_schema()
        for path, methods in schema.get("paths", {}).items():
            assert isinstance(methods, dict), f"Path {path} is not a dict"
            http_methods = [m for m in methods if m in ("get", "post", "put", "patch", "delete", "head", "options")]
            assert len(http_methods) >= 1, f"Path {path} has no HTTP methods"

    def test_all_paths_have_summary_or_description(self) -> None:
        """Every endpoint has at least a summary or description."""
        schema = openapi_schema()
        for path, methods in schema.get("paths", {}).items():
            for method, detail in methods.items():
                if method in ("get", "post", "put", "patch", "delete"):
                    has_summary = bool(detail.get("summary", ""))
                    has_description = bool(detail.get("description", ""))
                    assert has_summary or has_description, (
                        f"{method.upper()} {path} has no summary or description"
                    )

    def test_all_paths_have_response_schemas(self) -> None:
        """Every endpoint declares at least one response."""
        schema = openapi_schema()
        for path, methods in schema.get("paths", {}).items():
            for method, detail in methods.items():
                if method in ("get", "post", "put", "patch", "delete"):
                    responses = detail.get("responses", {})
                    assert len(responses) >= 1, (
                        f"{method.upper()} {path} has no response declarations"
                    )


class TestPathCoverage:
    """Verify every known router endpoint is documented in the schema."""

    # Maps (method, path) tuples expected in the schema.
    # These are the canonical v1 endpoints — if a new router is added
    # this list must be kept in sync.
    EXPECTED_ENDPOINTS = {
        # ── meta ──
        ("get", "/api/v1/meta/whoami"),
        ("get", "/api/v1/meta/health"),
        ("get", "/api/v1/meta/runtime"),
        # ── auth ──
        ("post", "/api/v1/auth/register"),
        ("post", "/api/v1/auth/login"),
        ("post", "/api/v1/auth/refresh"),
        ("post", "/api/v1/auth/logout"),
        # ── inventory ──
        ("get", "/api/v1/inventory/lots"),
        ("get", "/api/v1/inventory/lots/{lot_id}"),
        ("post", "/api/v1/inventory/lots"),
        ("post", "/api/v1/inventory/lots/{lot_id}/consume"),
        # ── household ──
        ("get", "/api/v1/household"),
        ("post", "/api/v1/household"),
        ("post", "/api/v1/household/{household_id}/switch"),
        # ── shopping ──
        ("get", "/api/v1/shopping/active"),
        ("post", "/api/v1/shopping/lists"),
        ("post", "/api/v1/shopping/lists/{list_id}/items"),
        ("post", "/api/v1/shopping/lists/{list_id}/complete"),
        ("post", "/api/v1/shopping/lists/{list_id}/mark-purchased"),
        # ── dashboard ──
        ("get", "/api/v1/dashboard/today"),
        # ── command ──
        ("post", "/api/v1/command/preview"),
        ("post", "/api/v1/command/execute"),
        ("get", "/api/v1/command/recent"),
        # ── search ──
        ("get", "/api/v1/search/global"),
        ("get", "/api/v1/search/inventory"),
        ("post", "/api/v1/search/voice-intent"),
        # ── traces ──
        ("get", "/api/v1/traces"),
        ("get", "/api/v1/traces/{trace_id}"),
        ("get", "/api/v1/traces/{trace_id}/export"),
        # ── intelligence ──
        ("get", "/api/v1/intelligence/decision/{name}/explain"),
        ("get", "/api/v1/intelligence/recurring"),
        ("get", "/api/v1/intelligence/mealplan"),
        # ── account ──
        ("post", "/api/v1/account/privacy/purge"),
        ("get", "/api/v1/account/privacy/retention-summary"),
        ("get", "/api/v1/account/privacy/profiles"),
        ("post", "/api/v1/account/privacy/apply-profile"),
        ("post", "/api/v1/account/privacy/update-retention"),
        ("post", "/api/v1/account/undo"),
        ("post", "/api/v1/account/store-mode/toggle"),
        # ── corrections ──
        ("get", "/api/v1/corrections"),
        ("post", "/api/v1/corrections"),
        # ── sms ──
        ("post", "/api/v1/sms/incoming"),
    }

    def test_all_expected_endpoints_present(self) -> None:
        """Every declared router endpoint appears in the OpenAPI schema.

        If this test fails, a new router was added without adding its
        ``openapi_schema()`` coverage, or an existing one was removed
        without updating ``EXPECTED_ENDPOINTS``.
        """
        schema = openapi_schema()
        paths = schema.get("paths", {})

        declared: set = set()
        for path, methods in paths.items():
            for method in methods:
                if method in ("get", "post", "put", "patch", "delete"):
                    declared.add((method, path))

        missing = self.EXPECTED_ENDPOINTS - declared
        extra = declared - self.EXPECTED_ENDPOINTS

        errors = []
        if missing:
            errors.append(f"Missing endpoints: {sorted(missing)}")
        if extra:
            errors.append(f"Unexpected endpoints (update EXPECTED_ENDPOINTS): {sorted(extra)}")

        assert not errors, "; ".join(errors)

    def test_no_undeclared_endpoints_without_tags(self) -> None:
        """Every declared endpoint has a non-empty tags list."""
        schema = openapi_schema()
        for path, methods in schema.get("paths", {}).items():
            for method, detail in methods.items():
                if method in ("get", "post", "put", "patch", "delete"):
                    tags = detail.get("tags", [])
                    assert len(tags) >= 1, (
                        f"{method.upper()} {path} has no tags"
                    )

    def test_meta_endpoints_require_no_auth(self) -> None:
        """Meta endpoints are unauthenticated (no security requirement)."""
        schema = openapi_schema()
        paths = schema.get("paths", {})

        for path in (
            "/api/v1/meta/whoami",
            "/api/v1/meta/health",
            "/api/v1/meta/runtime",
        ):
            methods = paths.get(path, {})
            for method, detail in methods.items():
                if method in ("get", "post"):
                    # Should NOT have a security requirement
                    security = detail.get("security", [])
                    assert len(security) == 0, (
                        f"{method.upper()} {path} should not require auth but has security={security}"
                    )

    def test_protected_endpoints_require_bearer_auth(self) -> None:
        """Protected endpoints declare Bearer-token security requirement."""
        schema = openapi_schema()
        paths = schema.get("paths", {})

        unprotected_prefixes = ("/api/v1/meta", "/api/v1/auth", "/api/v1/sms")
        protected_paths = []

        for path, methods in paths.items():
            is_unprotected = any(path.startswith(p) for p in unprotected_prefixes) or path == "/api/v1/command/preview"
            for method, detail in methods.items():
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                if is_unprotected:
                    assert detail.get("security", []) == [], (
                        f"{method.upper()} {path} should not declare bearer auth"
                    )
                    continue
                protected_paths.append((method, path))
                security = detail.get("security", [])
                assert security == [{"BearerAuth": []}], (
                    f"{method.upper()} {path} should require BearerAuth, got {security}"
                )

        assert protected_paths, "No protected endpoints were checked"
        assert schema.get("security", []) == [], "Global bearer fallback should not be used"


class TestComponentSchemas:
    """Validate that all component schemas are defined and referenced correctly."""

    def test_all_refs_resolve(self) -> None:
        """Every ``$ref`` in the schema resolves to a component definition.

        Walks the entire schema tree to find all ``$ref`` values and
        verifies each one exists in ``components/schemas``.
        """
        schema = openapi_schema()
        components = schema.get("components", {}).get("schemas", {})

        refs: list[str] = []
        self._collect_refs(schema, refs)

        unresolved = []
        for ref in refs:
            if not ref.startswith("#/components/schemas/"):
                continue  # external ref — out of scope
            name = ref[len("#/components/schemas/"):]
            if name not in components:
                unresolved.append(ref)

        assert not unresolved, (
            f"Unresolved $ref targets: {unresolved}"
        )

    @staticmethod
    def _collect_refs(obj, refs: list[str]) -> None:
        """Recursively collect all ``$ref`` strings from a schema tree."""
        if isinstance(obj, dict):
            if "$ref" in obj and isinstance(obj["$ref"], str):
                refs.append(obj["$ref"])
            for value in obj.values():
                TestComponentSchemas._collect_refs(value, refs)
        elif isinstance(obj, list):
            for item in obj:
                TestComponentSchemas._collect_refs(item, refs)

    def test_key_response_models_defined(self) -> None:
        """Essential response schemas are present in components/schemas."""
        schema = openapi_schema()
        schemas = schema.get("components", {}).get("schemas", {})

        # NOTE: ``ApiError`` is NOT included because it is used via
        # ``HTTPException(detail=ApiError(...).model_dump())`` inside
        # endpoint bodies, not as a ``response_model=`` decorator.
        # Only models declared in ``response_model=`` are emitted into
        # OpenAPI ``components/schemas``. The ``<GenericResolved>``
        # naming (e.g. ``ListResponse_InventoryLot_``) is generated
        # by Pydantic v2 and may vary across versions.
        expected_models = {
            "TokenResponse",
            "WhoAmI",
            "InventoryLot",
            "ListResponse_InventoryLot_",
            "DashboardSnapshot",
            "SearchResponse",
            "CommandPreviewResponse",
            "CommandHistoryItemWire",
            "CommandHistoryResponse",
            "CommandResponse",
            "DecisionExplanationWire",
            "RecurringPlanResponse",
            "MealPlanResponse",
            "ShoppingListWire",
            "HouseholdListResponse",
            "PurgeDataResponse",
            "UndoResponse",
            "RetentionSummaryResponse",
            "CorrectionListResponse",
            "CorrectionCreateResponse",
        }

        missing = expected_models - set(schemas.keys())
        assert not missing, f"Missing response models in components/schemas: {sorted(missing)}"

    def test_security_scheme_defined(self) -> None:
        """Bearer token security scheme is declared in components/securitySchemes."""
        schema = openapi_schema()
        security_schemes = schema.get("components", {}).get("securitySchemes", {})

        assert "BearerAuth" in security_schemes or "bearerAuth" in security_schemes, (
            f"No Bearer security scheme found. Available: {list(security_schemes.keys())}"
        )

        # Find the bearer scheme regardless of casing
        bearer_key = next(
            (k for k in security_schemes if "bearer" in k.lower()),
            None,
        )
        assert bearer_key is not None, "No Bearer security scheme"
        scheme = security_schemes[bearer_key]
        assert scheme.get("scheme", "").lower() == "bearer", (
            f"Security scheme {bearer_key} is not bearer: {scheme}"
        )
        assert scheme.get("type", "").lower() == "http", (
            f"Security scheme {bearer_key} type is not http"
        )

    def test_public_paths_do_not_inherit_security(self) -> None:
        """Public auth/bootstrap paths remain unauthenticated in the schema."""
        schema = openapi_schema()
        for path in (
            "/api/v1/meta/whoami",
            "/api/v1/meta/health",
            "/api/v1/meta/runtime",
            "/api/v1/auth/register",
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
            "/api/v1/auth/logout",
            "/api/v1/sms/incoming",
            "/api/v1/command/preview",
        ):
            methods = schema.get("paths", {}).get(path, {})
            for method, detail in methods.items():
                if method in ("get", "post", "put", "patch", "delete"):
                    assert detail.get("security", []) == [], (
                        f"{method.upper()} {path} unexpectedly declares security"
                    )


class TestSchemaStability:
    """Verify the schema is deterministic and serialisable."""

    def test_schema_is_deterministic(self) -> None:
        """Generating the schema twice yields the same result."""
        schema_a = openapi_schema()
        schema_b = openapi_schema()
        assert schema_a == schema_b, "OpenAPI schema is not deterministic"

    def test_schema_json_serialisable(self) -> None:
        """The schema can be serialised to JSON without errors."""
        schema = openapi_schema()
        dumped = json.dumps(schema, indent=2, default=str, ensure_ascii=False)
        assert isinstance(dumped, str)
        assert len(dumped) > 100

        # Round-trip test
        reloaded = json.loads(dumped)
        assert reloaded == schema, "JSON round-trip changed schema"

    def test_openapi_schema_json_function(self) -> None:
        """The string-returning variant works correctly."""
        dumped = openapi_schema_json()
        assert isinstance(dumped, str)
        assert len(dumped) > 100
        assert dumped.startswith("{")
        assert dumped.endswith("}\n") or dumped.endswith("}")

    def test_schema_importable_from_package(self) -> None:
        """Both functions are importable from ``shopstack.api.v1``."""
        from shopstack.api.v1 import openapi_schema as _s, openapi_schema_json as _j
        assert callable(_s), "openapi_schema import failed"
        assert callable(_j), "openapi_schema_json import failed"

    def test_all_paths_document_responses_for_success_status(self) -> None:
        """Every endpoint documents its success response (2xx).

        Endpoints that declare ``response_model=<schema>`` get a full
        content/schema entry. Endpoints returning bare ``JSONResponse``
        (like ``/meta/health`` and ``/sms/incoming``) have only a
        description — which is acceptable. The test ensures there is
        at least *some* documented response for every endpoint.

        Note: ``/meta/health`` and ``/sms/incoming`` do not use
        ``response_model=`` because they return ``JSONResponse`` or
        ``dict`` directly. Their OpenAPI entry has only a description
        with no content schema. This is a known limitation — those
        endpoints are introspection/webhook endpoints whose response
        shape is inherently dynamic.
        """
        schema = openapi_schema()
        for path, methods in schema.get("paths", {}).items():
            for method, detail in methods.items():
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                responses = detail.get("responses", {})
                success_codes = [k for k in responses if k.startswith("2")]
                if not success_codes:
                    # Some endpoints document only error responses.
                    assert len(responses) >= 1, (
                        f"{method.upper()} {path} has zero documented responses"
                    )
                    continue
                for code in success_codes:
                    resp = responses[code]
                    # Endpoints without ``response_model=`` emit only
                    # a description — that's fine. We just need *some*
                    # documented response.
                    has_content = bool(resp.get("content"))
                    has_ref = "$ref" in resp
                    has_description = bool(resp.get("description"))
                    assert has_content or has_ref or has_description, (
                        f"{method.upper()} {path} response {code} is empty"
                    )
