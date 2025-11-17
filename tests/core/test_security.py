"""Tests for core.security module."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
import uuid
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from src.core.security import (
    AuthenticatedClient,
    authenticate_client,
    hash_api_key,
    project_from_path,
    require_scopes,
    verify_api_key,
    verify_hmac_signature,
)
from src.db.models import ApiKey, Project
from tests.utils.factories import create_project_with_client


class TestAPIKeyHashing:
    """Test API key hashing and verification."""

    def test_hash_api_key_generates_salt(self):
        """Test hashing generates random salt."""
        raw_key = "test-api-key-123"
        key_hash, salt = hash_api_key(raw_key)

        assert salt is not None
        assert len(salt) == 32
        assert len(key_hash) > 0

    def test_hash_api_key_with_provided_salt(self):
        """Test hashing with provided salt."""
        raw_key = "test-api-key-123"
        custom_salt = secrets.token_bytes(32)

        key_hash, returned_salt = hash_api_key(raw_key, custom_salt)

        assert returned_salt == custom_salt
        assert len(key_hash) > 0

    def test_same_key_different_salts_different_hashes(self):
        """Test same key with different salts produces different hashes."""
        raw_key = "test-api-key-123"

        hash1, salt1 = hash_api_key(raw_key)
        hash2, salt2 = hash_api_key(raw_key)

        assert salt1 != salt2
        assert hash1 != hash2

    def test_verify_correct_api_key(self):
        """Test verifying correct API key returns True."""
        raw_key = "test-api-key-123"
        key_hash, salt = hash_api_key(raw_key)

        assert verify_api_key(raw_key, key_hash, salt) is True

    def test_verify_incorrect_api_key(self):
        """Test verifying incorrect API key returns False."""
        raw_key = "test-api-key-123"
        wrong_key = "wrong-api-key"
        key_hash, salt = hash_api_key(raw_key)

        assert verify_api_key(wrong_key, key_hash, salt) is False

    def test_verify_with_wrong_salt(self):
        """Test verifying with wrong salt returns False."""
        raw_key = "test-api-key-123"
        key_hash, _ = hash_api_key(raw_key)
        wrong_salt = secrets.token_bytes(32)

        assert verify_api_key(raw_key, key_hash, wrong_salt) is False


class TestHMACSignature:
    """Test HMAC signature verification."""

    def test_verify_valid_signature(self):
        """Test verifying valid HMAC signature."""
        body = b"test request body"
        secret = "shared-secret"
        timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

        # Generate valid signature
        message = body + timestamp.encode('utf-8')
        signature = hmac.new(
            secret.encode('utf-8'),
            message,
            hashlib.sha256
        ).hexdigest()

        assert verify_hmac_signature(body, timestamp, signature, secret) is True

    def test_verify_invalid_signature(self):
        """Test verifying invalid HMAC signature returns False."""
        body = b"test request body"
        secret = "shared-secret"
        timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        invalid_signature = "invalid_signature_string"

        assert verify_hmac_signature(body, timestamp, invalid_signature, secret) is False

    def test_verify_expired_timestamp(self):
        """Test verifying with expired timestamp returns False."""
        body = b"test request body"
        secret = "shared-secret"
        # Timestamp from 10 minutes ago (outside 5 minute window)
        old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        timestamp = old_time.isoformat().replace('+00:00', 'Z')

        message = body + timestamp.encode('utf-8')
        signature = hmac.new(
            secret.encode('utf-8'),
            message,
            hashlib.sha256
        ).hexdigest()

        assert verify_hmac_signature(body, timestamp, signature, secret) is False

    def test_verify_future_timestamp(self):
        """Test verifying with future timestamp returns False."""
        body = b"test request body"
        secret = "shared-secret"
        # Timestamp from future (outside 5 minute window)
        future_time = datetime.now(timezone.utc) + timedelta(minutes=10)
        timestamp = future_time.isoformat().replace('+00:00', 'Z')

        message = body + timestamp.encode('utf-8')
        signature = hmac.new(
            secret.encode('utf-8'),
            message,
            hashlib.sha256
        ).hexdigest()

        assert verify_hmac_signature(body, timestamp, signature, secret) is False

    def test_verify_invalid_timestamp_format(self):
        """Test verifying with invalid timestamp format returns False."""
        body = b"test request body"
        secret = "shared-secret"
        invalid_timestamp = "not-a-timestamp"
        signature = "some_signature"

        assert verify_hmac_signature(body, invalid_timestamp, signature, secret) is False

    def test_verify_wrong_secret(self):
        """Test verifying with wrong secret returns False."""
        body = b"test request body"
        correct_secret = "shared-secret"
        wrong_secret = "wrong-secret"
        timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

        # Generate signature with correct secret
        message = body + timestamp.encode('utf-8')
        signature = hmac.new(
            correct_secret.encode('utf-8'),
            message,
            hashlib.sha256
        ).hexdigest()

        # Verify with wrong secret
        assert verify_hmac_signature(body, timestamp, signature, wrong_secret) is False


class TestProjectFromPath:
    """Test project_from_path dependency."""

    def test_project_from_path_found(self, db_session):
        """Test project_from_path returns project when found."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        result = project_from_path("TEST-001", db_session)
        assert result.code == "TEST-001"
        assert result.name == "Test Project"

    def test_project_from_path_not_found(self, db_session):
        """Test project_from_path raises 404 when project not found."""
        with pytest.raises(HTTPException) as exc_info:
            project_from_path("NONEXISTENT", db_session)
        assert exc_info.value.status_code == 404
        assert "project not found" in str(exc_info.value.detail)


class TestAuthenticatedClient:
    """Test AuthenticatedClient class."""

    def test_authenticated_client_initialization(self):
        """Test AuthenticatedClient initialization."""
        # Create mock objects
        mock_api_key = Mock()
        mock_api_key.scopes = ["asset:read", "asset:write"]
        mock_api_client = Mock()
        mock_project = Mock()

        client = AuthenticatedClient(mock_api_key, mock_api_client, mock_project)

        assert client.api_key == mock_api_key
        assert client.api_client == mock_api_client
        assert client.project == mock_project
        assert client.scopes == ["asset:read", "asset:write"]

    def test_has_scope_returns_true_when_scope_present(self):
        """Test has_scope returns True when client has the scope."""
        mock_api_key = Mock()
        mock_api_key.scopes = ["asset:read", "asset:write", "sensor:read"]

        client = AuthenticatedClient(mock_api_key, Mock(), Mock())

        assert client.has_scope("asset:read") is True
        assert client.has_scope("asset:write") is True
        assert client.has_scope("sensor:read") is True

    def test_has_scope_returns_false_when_scope_absent(self):
        """Test has_scope returns False when client doesn't have the scope."""
        mock_api_key = Mock()
        mock_api_key.scopes = ["asset:read"]

        client = AuthenticatedClient(mock_api_key, Mock(), Mock())

        assert client.has_scope("asset:write") is False
        assert client.has_scope("admin:read") is False

    def test_require_scope_succeeds_when_scope_present(self):
        """Test require_scope doesn't raise when client has the scope."""
        mock_api_key = Mock()
        mock_api_key.scopes = ["asset:read", "asset:write"]

        client = AuthenticatedClient(mock_api_key, Mock(), Mock())

        # Should not raise
        client.require_scope("asset:read")
        client.require_scope("asset:write")

    def test_require_scope_raises_when_scope_absent(self):
        """Test require_scope raises 403 when client doesn't have the scope."""
        mock_api_key = Mock()
        mock_api_key.scopes = ["asset:read"]

        client = AuthenticatedClient(mock_api_key, Mock(), Mock())

        with pytest.raises(HTTPException) as exc_info:
            client.require_scope("asset:write")
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Missing required scope: asset:write" in str(exc_info.value.detail)

    def test_require_scope_specific_error_message(self):
        """Test require_scope error message contains the missing scope."""
        mock_api_key = Mock()
        mock_api_key.scopes = []

        client = AuthenticatedClient(mock_api_key, Mock(), Mock())

        with pytest.raises(HTTPException) as exc_info:
            client.require_scope("admin:delete")
        assert "admin:delete" in str(exc_info.value.detail)


class TestAuthenticateClient:
    """Test authenticate_client dependency."""

    def test_authenticate_client_success(self, db_session):
        """Test successful authentication with valid API key."""
        # Create test data
        project, api_client = create_project_with_client(db_session)

        # Generate a real API key with hash
        # The key needs to start with api_key_id prefix for the optimization to work
        api_key_id = str(uuid.uuid4()).replace('-', '')
        raw_key = f"{api_key_id}-full-test-key"
        key_hash, salt = hash_api_key(raw_key)
        combined_hash = salt + key_hash

        api_key = ApiKey(
            api_key_id=api_key_id,
            api_client_id=api_client.api_client_id,
            hash=combined_hash,
            scopes=["asset:read"]
        )
        db_session.add(api_key)
        db_session.commit()

        # Mock credentials
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=raw_key)

        # Call authenticate_client
        result = authenticate_client(
            credentials=credentials,
            project=project,
            x_timestamp=None,
            x_signature=None,
            db=db_session
        )

        assert result.project == project
        assert result.api_client == api_client
        assert "asset:read" in result.scopes

    def test_authenticate_client_invalid_key(self, db_session):
        """Test authentication fails with invalid API key."""
        # Create test data
        project, api_client = create_project_with_client(db_session)

        # Generate a real API key with hash
        raw_key = f"{str(uuid.uuid4())[:8]}-test-key"
        key_hash, salt = hash_api_key(raw_key)
        combined_hash = salt + key_hash

        api_key = ApiKey(
            api_client_id=api_client.api_client_id,
            hash=combined_hash,
            scopes=["asset:read"]
        )
        db_session.add(api_key)
        db_session.commit()

        # Try with wrong key
        wrong_key = "wrong-invalid-key-12345"
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=wrong_key)

        with pytest.raises(HTTPException) as exc_info:
            authenticate_client(
                credentials=credentials,
                project=project,
                x_timestamp=None,
                x_signature=None,
                db=db_session
            )
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid API key" in str(exc_info.value.detail)

    def test_authenticate_client_inactive_client(self, db_session):
        """Test authentication fails with inactive API client."""
        # Create test data with inactive client
        project, api_client = create_project_with_client(
            db_session,
            api_client_kwargs={"status": "inactive"}
        )

        # Generate API key
        raw_key = f"{str(uuid.uuid4())[:8]}-test-key"
        key_hash, salt = hash_api_key(raw_key)
        combined_hash = salt + key_hash

        api_key = ApiKey(
            api_client_id=api_client.api_client_id,
            hash=combined_hash,
            scopes=["asset:read"]
        )
        db_session.add(api_key)
        db_session.commit()

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=raw_key)

        with pytest.raises(HTTPException) as exc_info:
            authenticate_client(
                credentials=credentials,
                project=project,
                x_timestamp=None,
                x_signature=None,
                db=db_session
            )
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    def test_authenticate_client_with_hmac_headers(self, db_session):
        """Test authentication with HMAC headers (currently disabled but path should be covered)."""
        # Create test data
        project, api_client = create_project_with_client(db_session)

        # Generate API key
        api_key_id = str(uuid.uuid4()).replace('-', '')
        raw_key = f"{api_key_id}-test-key"
        key_hash, salt = hash_api_key(raw_key)
        combined_hash = salt + key_hash

        api_key = ApiKey(
            api_key_id=api_key_id,
            api_client_id=api_client.api_client_id,
            hash=combined_hash,
            scopes=["asset:read"]
        )
        db_session.add(api_key)
        db_session.commit()

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=raw_key)

        # Call with HMAC headers (though HMAC verification is disabled via pass statement)
        result = authenticate_client(
            credentials=credentials,
            project=project,
            x_timestamp="2024-01-01T12:00:00Z",
            x_signature="some_signature",
            db=db_session
        )

        # Should still succeed since HMAC is disabled
        assert result.project == project
        assert result.api_client == api_client


class TestRequireScopes:
    """Test require_scopes dependency factory."""

    def test_require_scopes_single_scope(self):
        """Test require_scopes dependency factory with single scope."""
        # Create mock client with required scope
        mock_api_key = Mock()
        mock_api_key.scopes = ["asset:read", "asset:write"]
        mock_client = AuthenticatedClient(mock_api_key, Mock(), Mock())

        # Get the dependency function
        scope_dependency = require_scopes("asset:read")

        # Should return the client without raising
        result = scope_dependency(client=mock_client)
        assert result == mock_client

    def test_require_scopes_multiple_scopes(self):
        """Test require_scopes with multiple required scopes."""
        # Create mock client with all required scopes
        mock_api_key = Mock()
        mock_api_key.scopes = ["asset:read", "asset:write", "sensor:read"]
        mock_client = AuthenticatedClient(mock_api_key, Mock(), Mock())

        # Get the dependency function requiring multiple scopes
        scope_dependency = require_scopes("asset:read", "asset:write")

        # Should return the client without raising
        result = scope_dependency(client=mock_client)
        assert result == mock_client

    def test_require_scopes_missing_scope_raises(self):
        """Test require_scopes raises when client missing required scope."""
        # Create mock client missing required scope
        mock_api_key = Mock()
        mock_api_key.scopes = ["asset:read"]
        mock_client = AuthenticatedClient(mock_api_key, Mock(), Mock())

        # Get the dependency function
        scope_dependency = require_scopes("asset:write")

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            scope_dependency(client=mock_client)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "asset:write" in str(exc_info.value.detail)
