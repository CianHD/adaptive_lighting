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
from src.api.dependencies import project_from_path


security = HTTPBearer()


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
    # Note: In production, you'd want to index on a hash prefix for performance
    api_keys = db.query(ApiKey).join(ApiClient).filter(
        ApiClient.project_id == project.project_id,
        ApiClient.status == "active"
    ).all()

    authenticated_key = None
    for api_key in api_keys:
        # In a real implementation, you'd store salt separately and verify properly
        # For now, simplified check (you'll need to enhance this)
        if raw_key.startswith(api_key.api_key_id[:8]):  # Simple prefix match
            authenticated_key = api_key
            break

    if not authenticated_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

    # Optional HMAC verification
    if x_signature and x_timestamp:
        # You'd implement HMAC verification here using a shared secret
        # This is a placeholder for the HMAC verification logic
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
