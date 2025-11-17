"""Tests for admin schema validation."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.schemas.admin import (
    PolicyRequest,
    PolicyResponse,
    KillSwitchRequest,
    KillSwitchResponse,
    ExedraConfigRequest,
    ExedraConfigResponse,
    AuditLogResponse,
    ApiKeyRequest,
    ApiKeyUpdateRequest,
    ApiKeyResponse,
    CurrentApiKeyResponse,
    ScopeInfo,
    ScopeListResponse,
)


class TestPolicySchemas:
    """Test policy-related schemas."""

    def test_policy_request_valid(self):
        """Test valid policy request."""
        data = {
            "version": "1.0.0",
            "body": {
                "min_dim": 0.0,
                "max_dim": 1.0,
                "max_changes_per_hr": 10
            }
        }
        policy = PolicyRequest(**data)
        assert policy.version == "1.0.0"
        assert policy.body["min_dim"] == 0.0

    def test_policy_request_missing_fields(self):
        """Test policy request with missing required fields."""
        with pytest.raises(ValidationError) as exc_info:
            PolicyRequest(version="1.0.0")
        assert "body" in str(exc_info.value)

    def test_policy_response_serialization(self):
        """Test policy response with datetime."""
        now = datetime.now(timezone.utc)
        policy = PolicyResponse(
            policy_id="pol-123",
            version="1.0.0",
            body={"min_dim": 0.0},
            active_from=now
        )
        assert policy.policy_id == "pol-123"
        assert policy.active_from == now


class TestKillSwitchSchemas:
    """Test kill switch schemas."""

    def test_kill_switch_request_enabled(self):
        """Test enabling kill switch with reason."""
        request = KillSwitchRequest(enabled=True, reason="Emergency maintenance")
        assert request.enabled is True
        assert request.reason == "Emergency maintenance"

    def test_kill_switch_request_disabled_no_reason(self):
        """Test disabling kill switch without reason."""
        request = KillSwitchRequest(enabled=False)
        assert request.enabled is False
        assert request.reason is None

    def test_kill_switch_response_complete(self):
        """Test kill switch response with all fields."""
        now = datetime.now(timezone.utc)
        response = KillSwitchResponse(
            enabled=True,
            reason="Testing",
            changed_at=now,
            changed_by="admin@example.com"
        )
        assert response.enabled is True
        assert response.changed_by == "admin@example.com"


class TestExedraConfigSchemas:
    """Test EXEDRA configuration schemas."""

    def test_exedra_config_request_valid(self):
        """Test valid EXEDRA config request."""
        request = ExedraConfigRequest(
            api_client_id="client-123",
            api_token="secret-token",
            base_url="https://api.exedra.com",
            environment="prod"
        )
        assert request.api_client_id == "client-123"
        assert request.api_token == "secret-token"
        assert request.environment == "prod"

    def test_exedra_config_request_default_environment(self):
        """Test EXEDRA config with default environment."""
        request = ExedraConfigRequest(
            api_client_id="client-123",
            api_token="token",
            base_url="https://api.exedra.com"
        )
        assert request.environment == "prod"

    def test_exedra_config_request_missing_fields(self):
        """Test EXEDRA config with missing required fields."""
        with pytest.raises(ValidationError) as exc_info:
            ExedraConfigRequest(api_client_id="client-123")
        assert "api_token" in str(exc_info.value)
        assert "base_url" in str(exc_info.value)

    def test_exedra_config_response(self):
        """Test EXEDRA config response."""
        now = datetime.now(timezone.utc)
        response = ExedraConfigResponse(
            token_credential_id="cred-123",
            url_credential_id="cred-124",
            api_client_id="client-123",
            environment="prod",
            created_at=now
        )
        assert response.token_credential_id == "cred-123"
        assert response.url_credential_id == "cred-124"


class TestAuditLogSchema:
    """Test audit log schema."""

    def test_audit_log_response_complete(self):
        """Test audit log with all fields."""
        now = datetime.now(timezone.utc)
        log = AuditLogResponse(
            audit_log_id=1,
            timestamp=now,
            actor="admin@example.com",
            action="CREATE",
            entity="ApiKey",
            entity_id="key-123",
            details={"scopes": ["asset:read"]}
        )
        assert log.audit_log_id == 1
        assert log.action == "CREATE"
        assert log.details["scopes"] == ["asset:read"]


class TestApiKeySchemas:
    """Test API key management schemas."""

    def test_api_key_request_with_default_scopes(self):
        """Test API key request with default scopes."""
        request = ApiKeyRequest(api_client_name="Test Client")
        assert request.api_client_name == "Test Client"
        assert request.scopes == ["asset:read"]

    def test_api_key_request_with_custom_scopes(self):
        """Test API key request with custom scopes."""
        request = ApiKeyRequest(
            api_client_name="Test Client",
            scopes=["asset:read", "asset:write", "sensor:read"]
        )
        assert len(request.scopes) == 3
        assert "asset:write" in request.scopes

    def test_api_key_update_request(self):
        """Test API key update request."""
        request = ApiKeyUpdateRequest(scopes=["asset:read", "sensor:read"])
        assert len(request.scopes) == 2

    def test_api_key_update_request_empty_scopes(self):
        """Test API key update with empty scopes."""
        request = ApiKeyUpdateRequest(scopes=[])
        assert request.scopes == []

    def test_api_key_response_complete(self):
        """Test API key response with all fields."""
        now = datetime.now(timezone.utc)
        response = ApiKeyResponse(
            api_key_id="key-123",
            api_key="ak_1234567890abcdef",
            api_client_id="client-123",
            api_client_name="Test Client",
            scopes=["asset:read", "asset:write"],
            created_at=now
        )
        assert response.api_key.startswith("ak_")
        assert len(response.scopes) == 2

    def test_current_api_key_response(self):
        """Test current API key response."""
        response = CurrentApiKeyResponse(
            api_client_name="Test Client",
            scopes=["asset:read"]
        )
        assert response.api_client_name == "Test Client"
        assert response.scopes == ["asset:read"]


class TestScopeSchemas:
    """Test scope management schemas."""

    def test_scope_info(self):
        """Test scope info schema."""
        scope = ScopeInfo(
            scope_code="asset:read",
            description="Read asset data",
            category="asset"
        )
        assert scope.scope_code == "asset:read"
        assert scope.category == "asset"

    def test_scope_list_response(self):
        """Test scope list response."""
        scopes = [
            ScopeInfo(scope_code="asset:read", description="Read", category="asset"),
            ScopeInfo(scope_code="sensor:read", description="Read", category="sensor"),
        ]
        recommendations = {
            "basic": ["asset:read"],
            "full": ["asset:read", "asset:write", "sensor:read"]
        }
        response = ScopeListResponse(
            scopes=scopes,
            recommended_combinations=recommendations
        )
        assert len(response.scopes) == 2
        assert "basic" in response.recommended_combinations
        assert len(response.recommended_combinations["full"]) == 3
