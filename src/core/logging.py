import logging
import sys
import time
import json
from typing import Optional, Callable
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.exc import IntegrityError, DatabaseError, SQLAlchemyError
from sqlalchemy.orm import Session
from pydantic import ValidationError

from src.db.session import get_db
from src.db.models import AuditLog, Project

# Basic logging setup
LOG_LEVEL = logging.INFO
logging.basicConfig(stream=sys.stdout, level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("adaptive")


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """
    Single middleware that handles both stdout logging AND database audit trails.
    """

    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()

        # Extract project context
        project_code = self._extract_project_code(request.url.path)

        # Store exception details for audit logging
        exception_details = None

        try:
            # Process request
            response = await call_next(request)
        except Exception as e:
            # Capture the original exception details
            exception_details = f"{type(e).__name__}: {str(e)}"
            # Log the exception and re-raise to let FastAPI handle it
            logger.error(
                "Unhandled exception in %s %s: %s",
                request.method,
                request.url.path,
                exception_details,
                exc_info=True
            )
            raise

        # Calculate duration
        duration = time.time() - start_time

        # Log to stdout based on success/error
        if response.status_code >= 400:
            # Log errors with details from response
            error_details = await self._extract_error_details(response)
            logger.error(
                "Error %d on %s %s (%.3fs) [%s]: %s",
                response.status_code,
                request.method,
                request.url.path,
                duration,
                project_code,
                error_details or "No details"
            )
        else:
            # Log successful requests
            logger.info(
                "%s %s -> %d (%.3fs) [%s]",
                request.method,
                request.url.path,
                response.status_code,
                duration,
                project_code
            )

        # Log to database audit table (compliance)
        await self._log_to_audit_table(request, response, project_code, duration, exception_details)

        return response

    def _extract_project_code(self, path: str) -> str:
        """Extract project code from URL path (e.g., /v1/scs-dev/admin)"""
        try:
            path_parts = path.split('/')
            if len(path_parts) >= 3 and path_parts[1] == 'v1':
                return path_parts[2]
        except (IndexError, AttributeError):
            # Handle cases where path parsing fails - just use fallback
            pass
        return "unknown"

    async def _extract_error_details(self, response: Response) -> Optional[str]:
        """Extract error details from response body"""
        try:
            if hasattr(response, 'body') and response.body:
                body_text = response.body.decode('utf-8')
                try:
                    body_json = json.loads(body_text)
                    return body_json.get('detail', body_text[:200])
                except json.JSONDecodeError:
                    return body_text[:200]

            # For streaming responses, try to get the content differently
            if hasattr(response, 'content'):
                content = response.content
                if isinstance(content, bytes):
                    body_text = content.decode('utf-8')
                    try:
                        body_json = json.loads(body_text)
                        return body_json.get('detail', body_text[:200])
                    except json.JSONDecodeError:
                        return body_text[:200]

        except (UnicodeDecodeError, AttributeError):
            # Handle cases where response body can't be decoded or accessed - just return None
            pass
        return None

    async def _log_to_audit_table(self, request: Request, response: Response, project_code: str, duration: float, exception_details: Optional[str] = None):
        """Log request to database audit table for compliance"""
        try:
            db: Session = next(get_db())

            # Prepare audit data
            success = response.status_code < 400

            # For audit purposes, we want the technical error details
            audit_error_details = None
            if not success:
                if exception_details:
                    # Use the original exception details (best for debugging)
                    audit_error_details = exception_details
                else:
                    # Fall back to response body extraction
                    audit_error_details = await self._extract_error_details(response)

            # Extract better actor information
            actor = 'anonymous'
            api_client_name = None

            # Check if this is an authenticated request
            auth_header = request.headers.get('authorization', '')
            if auth_header.startswith('Bearer '):
                actor = 'api_client'
                # Try to extract client info from request state (if available)
                if hasattr(request.state, 'client'):
                    client = request.state.client
                    if hasattr(client, 'api_client') and hasattr(client.api_client, 'name'):
                        api_client_name = client.api_client.name
                        actor = f"api_client:{api_client_name}"

            # Build comprehensive actor string
            user_agent = request.headers.get('user-agent', 'unknown')
            remote_addr = request.client.host if request.client else 'unknown'

            if api_client_name:
                actor_detail = f"{api_client_name} ({user_agent[:50]} from {remote_addr})"
            else:
                actor_detail = f"{actor} ({user_agent[:50]} from {remote_addr})"

            # Look up project_id from project_code
            project_id = None
            if project_code and project_code != "unknown":
                try:
                    project = db.query(Project).filter(Project.code == project_code).first()
                    if project:
                        project_id = project.project_id
                except (SQLAlchemyError, AttributeError):
                    # Don't let project lookup break audit logging
                    pass

            audit_entry = AuditLog(
                actor=actor_detail,
                project_id=project_id,
                action='api_request',
                entity='endpoint',
                entity_id=f"{request.method} {request.url.path}",
                details={
                    'method': request.method,
                    'path': request.url.path,
                    'status_code': response.status_code,
                    'project_code': project_code,
                    'api_client_name': api_client_name,
                    'duration_seconds': round(duration, 3),
                    'success': success,
                    'error_details': audit_error_details,
                    'user_response_error': await self._extract_error_details(response) if not success else None,
                    'user_agent': request.headers.get('user-agent'),
                    'remote_addr': request.client.host if request.client else None
                }
            )

            db.add(audit_entry)
            db.commit()
            db.close()

        except SQLAlchemyError as e:
            # Handle database-specific errors
            logger.warning("Failed to log to audit table (database error): %s", str(e))
        except ImportError as e:
            # Handle cases where database modules aren't available
            logger.warning("Failed to log to audit table (import error): %s", str(e))
        except Exception as e:
            # Last resort - but log the specific error type for debugging
            logger.warning("Failed to log to audit table (unexpected error %s): %s", type(e).__name__, str(e))


def install_error_handlers(app: FastAPI):
    """
    Install RFC 7807 Problem Details error handlers.
    
    These handlers convert exceptions into user-friendly JSON responses.
    Audit logging is handled by AuditLoggingMiddleware.
    
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

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, _exc: ValidationError):
        body = {
            "type": "about:blank",
            "title": "Validation Error",
            "status": 422,
            "detail": "The request data failed validation. Please check your input.",
            "instance": str(request.url),
        }
        return JSONResponse(body, status_code=422, media_type="application/problem+json")

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        # Generic user-friendly error messages based on common constraint patterns
        error_detail = "Database constraint violation. Please check your input."
        error_str = str(exc).lower()

        if "chk_credential_type" in error_str:
            error_detail = "Invalid credential type. Supported types: api_token, base_url, oauth_token, certificate, other"
        elif "unique" in error_str or "duplicate" in error_str:
            error_detail = "A record with these values already exists."
        elif "foreign key" in error_str:
            error_detail = "Referenced record does not exist."
        elif "not null" in error_str:
            error_detail = "Required field is missing."
        elif "check constraint" in error_str:
            error_detail = "Data does not meet validation requirements."

        body = {
            "type": "about:blank",
            "title": "Database Constraint Error",
            "status": 400,
            "detail": error_detail,
            "instance": str(request.url),
        }
        return JSONResponse(body, status_code=400, media_type="application/problem+json")

    @app.exception_handler(DatabaseError)
    async def database_error_handler(request: Request, _exc: DatabaseError):
        body = {
            "type": "about:blank",
            "title": "Database Error", 
            "status": 503,
            "detail": "Database service temporarily unavailable. Please try again.",
            "instance": str(request.url),
        }
        return JSONResponse(body, status_code=503, media_type="application/problem+json")

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, _exc: SQLAlchemyError):
        body = {
            "type": "about:blank",
            "title": "Database Error",
            "status": 500, 
            "detail": "A database error occurred. Please try again or contact support.",
            "instance": str(request.url),
        }
        return JSONResponse(body, status_code=500, media_type="application/problem+json")

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, _exc: Exception):
        body = {
            "type": "about:blank", 
            "title": "Internal Server Error",
            "status": 500,
            "detail": "An unexpected error occurred. Please try again or contact support.",
            "instance": str(request.url),
        }
        return JSONResponse(body, status_code=500, media_type="application/problem+json")
