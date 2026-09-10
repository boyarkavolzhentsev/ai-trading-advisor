"""``app/api/*`` module-hygiene tests: no direct import of any closed
execution primitive, exact route table, and the SERVICE_UNAVAILABLE 503
response stays declared with the full ``AdvisoryResponse`` schema in
OpenAPI - never silently replaced by ``ErrorResponse``."""

from __future__ import annotations

import ast
import importlib
import inspect

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from tests.api_support import FakeApplicationAdvisoryService, build_advisory_response

_FORBIDDEN_IMPORTS = {
    "ProductionAdvisoryComposer",
    "ProductionAdvisoryConfig",
    "MT5Client",
    "MT5Credentials",
    "BinanceRestClient",
    "OpenAIExplanationClient",
    "OpenAIExplanationClientConfig",
    "run_runtime_cycle",
    "Judge",
    "RiskGate",
    "PortfolioSupervisor",
    "SessionGate",
    "SetupConstruction",
}

_API_MODULES = ["app.api.main", "app.api.models", "app.api.dependencies", "app.api.exception_handlers"]


@pytest.mark.parametrize("module_name", _API_MODULES)
def test_api_modules_never_import_closed_execution_primitives(module_name: str) -> None:
    module = importlib.import_module(module_name)
    tree = ast.parse(inspect.getsource(module))
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.update(alias.asname or alias.name for alias in node.names)
        if isinstance(node, ast.Import):
            imported_names.update(alias.asname or alias.name for alias in node.names)
    hit = imported_names & _FORBIDDEN_IMPORTS
    assert not hit, f"{module_name} imports forbidden execution primitives: {hit}"


def test_only_build_production_advisory_service_crosses_the_composition_root_boundary() -> None:
    """``app.api.main`` may import exactly one name from
    ``app.bootstrap.production`` - the factory function itself, never a
    config/execution class."""
    import app.api.main as main_module

    tree = ast.parse(inspect.getsource(main_module))
    bootstrap_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.bootstrap.production":
            bootstrap_imports.update(alias.asname or alias.name for alias in node.names)
    assert bootstrap_imports == {"build_production_advisory_service"}


def test_route_table_contains_only_approved_business_routes() -> None:
    app = create_app(service=FakeApplicationAdvisoryService(result=build_advisory_response()))
    business_paths = {
        route.path
        for route in app.routes
        if getattr(route, "path", None) not in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
    }
    assert business_paths == {"/health", "/v1/advisory"}


def test_no_execution_endpoint_exists() -> None:
    app = create_app(service=FakeApplicationAdvisoryService(result=build_advisory_response()))
    paths = {route.path for route in app.routes}
    forbidden_substrings = ("order", "execute", "cancel", "position", "trade/", "place")
    for path in paths:
        lowered = path.lower()
        assert not any(token in lowered for token in forbidden_substrings), f"unexpected execution-shaped route: {path}"


def test_openapi_documents_both_200_and_503_advisory_responses() -> None:
    app = create_app(service=FakeApplicationAdvisoryService(result=build_advisory_response()))
    with TestClient(app) as client:
        openapi = client.get("/openapi.json").json()

    advisory_responses = openapi["paths"]["/v1/advisory"]["post"]["responses"]
    assert "200" in advisory_responses
    assert "503" in advisory_responses

    schema_200 = advisory_responses["200"]["content"]["application/json"]["schema"]
    schema_503 = advisory_responses["503"]["content"]["application/json"]["schema"]
    # both reference the same AdvisoryResponse schema - the 503 body was
    # never replaced by an ErrorResponse envelope in the documented contract.
    assert schema_200 == schema_503
    ref = schema_200.get("$ref", "")
    assert "AdvisoryResponse" in ref
