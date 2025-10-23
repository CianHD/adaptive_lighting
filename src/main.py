from fastapi import FastAPI
from src.core.logging import logger
from src.api import asset, sensor, command, admin
from src.core.errors import install_problem_details

app = FastAPI(
    title="Adaptive Lighting API",
    description="API for adaptive lighting integrations with EXEDRA",
    version="1.0.0"
)

# Include routers
app.include_router(asset.router)
app.include_router(sensor.router)
app.include_router(command.router)
app.include_router(admin.router)

# Install problem details for RFC7807 error responses
install_problem_details(app)

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
