from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException as FastAPIHTTPException

def install_problem_details(app: FastAPI):
    """
    Install RFC 7807 Problem Details for HTTP APIs error handling.
    
    This configures FastAPI to return standardized error responses in the
    'application/problem+json' format, which includes structured error
    information with type, title, status, detail, and instance fields.
    
    Args:
        app: The FastAPI application instance to configure
    """
    @app.exception_handler(FastAPIHTTPException)
    async def http_exc_handler(request: Request, exc: FastAPIHTTPException):
        body = {
            "type": "about:blank",
            "title": "HTTP Error",
            "status": exc.status_code,
            "detail": exc.detail,
            "instance": str(request.url),
        }
        return JSONResponse(body, status_code=exc.status_code, media_type="application/problem+json")
