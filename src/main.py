from fastapi import FastAPI
from src.core.logging import AuditLoggingMiddleware, install_error_handlers
from src.api import asset, sensor, admin

app = FastAPI(
    title="Adaptive Lighting API",
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
app.include_router(admin.router)

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
