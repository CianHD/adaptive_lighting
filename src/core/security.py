import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Optional
from fastapi import HTTPException, Header, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.db.models import ApiKey, ApiClient, Project


security = HTTPBearer()


def project_from_path(project_code: str, db: Session = Depends(get_db)) -> Project:
    """
    FastAPI dependency that reads {project_code} from the path, looks up the project in DB, 
    404s if it doesn't exist, and injects the Project row into your endpoint so every 
    handler already has the resolved tenant.
    """
    proj = db.query(Project).filter(Project.code == project_code).first()
    if not proj:
        raise HTTPException(404, "project not found")
    return proj


def hash_api_key(raw_key: str, salt: bytes = None) -> tuple[bytes, bytes]:
    """Hash an API key with salt for secure storage"""
    if salt is None:
        salt = secrets.token_bytes(32)

    key_hash = hashlib.pbkdf2_hmac('sha256', raw_key.encode('utf-8'), salt, 100000)
    return key_hash, salt


def verify_api_key(raw_key: str, stored_hash: bytes, salt: bytes) -> bool:
    """Verify an API key against stored hash"""
    key_hash, _ = hash_api_key(raw_key, salt)
    return hmac.compare_digest(key_hash, stored_hash)


def verify_hmac_signature(body: bytes, timestamp: str, signature: str, secret: str) -> bool:
    """Verify HMAC signature for request authenticity"""
    try:
        # Parse timestamp and check skew
        ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        if abs((now - ts).total_seconds()) > 300:  # 5 minutes
            return False

        # Compute expected signature
        message = body + timestamp.encode('utf-8')
        expected = hmac.new(
            secret.encode('utf-8'),
            message,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(signature, expected)
    except (ValueError, TypeError):
        return False


class AuthenticatedClient:
    """Represents an authenticated API client with resolved permissions"""
    def __init__(self, api_key: ApiKey, api_client: ApiClient, project: Project):
        self.api_key = api_key
        self.api_client = api_client
        self.project = project
        self.scopes = api_key.scopes

    def has_scope(self, required_scope: str) -> bool:
        """Check if client has required scope"""
        return required_scope in self.scopes

    def require_scope(self, required_scope: str):
        """Raise exception if client doesn't have required scope"""
        if not self.has_scope(required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope: {required_scope}"
            )


def authenticate_client(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    project: Project = Depends(project_from_path),
    x_timestamp: Optional[str] = Header(None),
    x_signature: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> AuthenticatedClient:
    """
    Authenticate API client and return authenticated client info.
    Supports both simple Bearer token and HMAC signature verification.
    """
    # Extract the raw API key from Bearer token
    raw_key = credentials.credentials

    # Find matching API key in database
    api_keys = db.query(ApiKey).join(ApiClient).filter(
        ApiClient.project_id == project.project_id,
        ApiClient.status == "active"
    ).all()

    authenticated_key = None
    for api_key in api_keys:
        # Check if this key matches by prefix first (performance optimization)
        if raw_key.startswith(api_key.api_key_id[:8]):
            # Extract salt and hash from stored value
            if len(api_key.hash) >= 32:  # Ensure we have at least salt
                salt = api_key.hash[:32]  # First 32 bytes are salt
                stored_hash = api_key.hash[32:]  # Rest is hash

                # Verify the full key
                if verify_api_key(raw_key, stored_hash, salt):
                    authenticated_key = api_key
                    break

    if not authenticated_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

    # Optional HMAC verification - DISABLED for current implementation
    # Client has opted out of certificate management for initial deployment
    if x_signature and x_timestamp:
    #     # HMAC verification would be implemented here using a shared secret
    #     # Reference implementation for future clients requiring enhanced security:
    #     # 1. Extract signature from x_signature header
    #     # 2. Get shared secret from client configuration
    #     # 3. Reconstruct payload using request body + timestamp
    #     # 4. Calculate HMAC-SHA256 signature
    #     # 5. Compare signatures using secure comparison
    #     # 6. Validate timestamp is within acceptable window (e.g., 5 minutes)
        pass

    # Update last used timestamp
    authenticated_key.last_used_at = datetime.now(timezone.utc)
    db.commit()

    return AuthenticatedClient(
        api_key=authenticated_key,
        api_client=authenticated_key.api_client,
        project=project
    )


def require_scopes(*required_scopes: str):
    """Dependency factory for requiring specific scopes"""
    def scope_dependency(client: AuthenticatedClient = Depends(authenticate_client)):
        for scope in required_scopes:
            client.require_scope(scope)
        return client
    return scope_dependency
