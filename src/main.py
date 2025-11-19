from typing import Any, Dict

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi

from src.core.logging import AuditLoggingMiddleware, install_error_handlers
from src.api import asset, sensor, admin, INTERNAL_DOC_TAG

app = FastAPI(
    title="SCS Flux - Adaptive Lighting API",
    description="API for adaptive lighting integrations with EXEDRA",
    version="1.0.0"
)

# Add our unified logging & audit middleware
app.add_middleware(AuditLoggingMiddleware)

# Install RFC 7807 Problem Details error handlers
install_error_handlers(app)

# Include routers
app.include_router(asset.router)
app.include_router(sensor.router)
app.include_router(admin.router, tags=[INTERNAL_DOC_TAG])


_full_openapi_schema: Dict[str, Any] | None = None
_public_openapi_schema: Dict[str, Any] | None = None


def build_full_openapi_schema(force: bool = False) -> Dict[str, Any]:
    """Build the full OpenAPI schema including internal endpoints."""
    global _full_openapi_schema
    if force or _full_openapi_schema is None:
        app.openapi_schema = None
        _full_openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
    return _full_openapi_schema


def build_public_openapi_schema(force: bool = False) -> Dict[str, Any]:
    """Build the public OpenAPI schema excluding internal endpoints."""
    global _public_openapi_schema
    if force or _public_openapi_schema is None:
        full_schema = build_full_openapi_schema(force=force)
        filtered_paths: Dict[str, Dict[str, Any]] = {}
        for path, methods in full_schema.get("paths", {}).items():
            public_methods = {
                method: details
                for method, details in methods.items()
                if INTERNAL_DOC_TAG not in details.get("tags", [])
            }
            if public_methods:
                filtered_paths[path] = public_methods

        _public_openapi_schema = {**full_schema, "paths": filtered_paths}
    return _public_openapi_schema


def public_openapi() -> Dict[str, Any]:
    """Expose the public OpenAPI schema (excluding internal endpoints)."""
    return build_public_openapi_schema()


app.openapi = public_openapi  # type: ignore[assignment]


@app.get("/internal/openapi.json", include_in_schema=False)
def internal_openapi() -> Dict[str, Any]:
    """Expose the full OpenAPI schema (including internal endpoints)."""
    return build_full_openapi_schema()


@app.get("/internal/docs", include_in_schema=False)
def internal_docs() -> Any:
    """Serve Swagger UI for the internal schema."""
    return get_swagger_ui_html(
        openapi_url="/internal/openapi.json",
        title="Adaptive Lighting Internal API Docs",
    )

@app.get("/health")
def health():
    """Health check endpoint"""
    return {"status": "ok", "service": "adaptive-lighting-api"}

@app.get("/")
def root():
    """Root endpoint with API info"""
    return {
        "service": "Adaptive Lighting API",
        "version": "1.0.0",
        "documentation": "/docs",
        "health": "/health"
    }
