"""Tests for Admin API endpoints covering policy, kill switch, scopes, and keys."""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from src.api.admin import (
    create_policy,
    delete_api_key,
    generate_api_key,
    get_audit_logs,
    get_current_api_key,
    get_current_policy,
    get_kill_switch_status,
    list_available_scopes,
    store_exedra_config,
    sync_scope_catalogue,
    toggle_kill_switch,
    update_api_key,
    update_policy,
)
from src.core.security import AuthenticatedClient
from src.db.models import ApiClient, Project
from src.schemas.admin import (
    ApiKeyRequest,
    ApiKeyUpdateRequest,
    ExedraConfigRequest,
    KillSwitchRequest,
    PolicyRequest,
)


@pytest.fixture
def mock_authenticated_client():
    """Create a mock authenticated client with project and API client"""
    project = Mock(spec=Project)
    project.project_id = "proj-123"
    project.code = "TEST"

    api_client = Mock(spec=ApiClient)
    api_client.api_client_id = "client-123"
    api_client.name = "test-client"

    client = Mock(spec=AuthenticatedClient)
    client.project = project
    client.api_client = api_client
    client.scopes = ["admin:policy:create", "admin:policy:read"]

    return client


@pytest.fixture
def mock_db_session():
    """Create a mock database session"""
    return Mock()


class TestCreatePolicy:
    """Test POST /v1/{project_code}/admin/policy endpoint"""

    @patch('src.api.admin.AdminService.create_policy')
    async def test_create_policy_success(self, mock_create, mock_authenticated_client, mock_db_session):
        """Should create policy successfully"""
        # Arrange
        request = PolicyRequest(
            version="1.0",
            body={"min_dim": 20, "max_dim": 80},
            active_from=datetime(2025, 1, 1, 0, 0, 0)
        )

        mock_policy = Mock()
        mock_policy.policy_id = "policy-123"
        mock_policy.version = "1"
        mock_policy.body = {"min_dim": 20, "max_dim": 80}
        mock_policy.active_from = datetime(2025, 1, 1, 0, 0, 0)
        mock_create.return_value = mock_policy

        # Act
        result = await create_policy(request, mock_authenticated_client, mock_db_session)

        # Assert
        assert result.policy_id == "policy-123"
        assert result.version == "1"
        mock_create.assert_called_once_with(
            request=request,
            project_id="proj-123",
            api_client_name="test-client",
            db=mock_db_session
        )

    @patch('src.api.admin.AdminService.create_policy')
    async def test_create_policy_value_error(self, mock_create, mock_authenticated_client, mock_db_session):
        """Should raise 400 on ValueError"""
        request = PolicyRequest(version="1.0", body={}, active_from=datetime.now())
        mock_create.side_effect = ValueError("Invalid policy body")

        with pytest.raises(HTTPException) as exc_info:
            await create_policy(request, mock_authenticated_client, mock_db_session)

        assert exc_info.value.status_code == 400
        assert "Invalid policy body" in exc_info.value.detail

    @patch('src.api.admin.AdminService.create_policy')
    async def test_create_policy_generic_error(self, mock_create, mock_authenticated_client, mock_db_session):
        """Should raise 500 on generic exception"""
        request = PolicyRequest(version="1.0", body={}, active_from=datetime.now())
        mock_create.side_effect = Exception("Database error")

        with pytest.raises(HTTPException) as exc_info:
            await create_policy(request, mock_authenticated_client, mock_db_session)

        assert exc_info.value.status_code == 500
        assert "Failed to create policy" in exc_info.value.detail


class TestUpdatePolicy:
    """Test PUT /v1/{project_code}/admin/policy/{policy_id} endpoint"""

    @patch('src.api.admin.AdminService.update_policy')
    async def test_update_policy_success(self, mock_update, mock_authenticated_client, mock_db_session):
        """Should update policy successfully"""
        policy_id = "policy-123"
        request = PolicyRequest(
            version="2.0",
            body={"min_dim": 30, "max_dim": 90},
            active_from=datetime(2025, 2, 1, 0, 0, 0)
        )

        mock_policy = Mock()
        mock_policy.policy_id = policy_id
        mock_policy.version = "2"
        mock_policy.body = {"min_dim": 30, "max_dim": 90}
        mock_policy.active_from = datetime(2025, 2, 1, 0, 0, 0)
        mock_update.return_value = mock_policy

        result = await update_policy(policy_id, request, mock_authenticated_client, mock_db_session)

        assert result.policy_id == policy_id
        assert result.version == "2"
        mock_update.assert_called_once_with(
            policy_id=policy_id,
            request=request,
            project_id="proj-123",
            api_client_name="test-client",
            db=mock_db_session
        )

    @patch('src.api.admin.AdminService.update_policy')
    async def test_update_policy_not_found(self, mock_update, mock_authenticated_client, mock_db_session):
        """Should raise 400 when policy not found"""
        policy_id = "nonexistent-policy"
        request = PolicyRequest(
            version="2.0",
            body={"min_dim": 30, "max_dim": 90},
            active_from=datetime(2025, 2, 1, 0, 0, 0)
        )
        mock_update.side_effect = ValueError("Policy nonexistent-policy not found for project")

        with pytest.raises(HTTPException) as exc_info:
            await update_policy(policy_id, request, mock_authenticated_client, mock_db_session)

        assert exc_info.value.status_code == 400


class TestGetCurrentPolicy:
    """Test GET /v1/{project_code}/admin/policy endpoint"""

    @patch('src.api.admin.AdminService.get_current_policy')
    async def test_get_current_policy_success(self, mock_get, mock_authenticated_client, mock_db_session):
        """Should retrieve current policy successfully"""
        mock_policy = Mock()
        mock_policy.policy_id = "policy-123"
        mock_policy.version = "1"
        mock_policy.body = {"min_dim": 20, "max_dim": 80}
        mock_policy.active_from = datetime(2025, 1, 1, 0, 0, 0)
        mock_get.return_value = mock_policy

        result = await get_current_policy(mock_authenticated_client, mock_db_session)

        assert result.policy_id == "policy-123"
        assert result.version == "1"

    @patch('src.api.admin.AdminService.get_current_policy')
    async def test_get_current_policy_not_found(self, mock_get, mock_authenticated_client, mock_db_session):
        """Should raise 404 when no policy found"""
        mock_get.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_current_policy(mock_authenticated_client, mock_db_session)

        assert exc_info.value.status_code == 404
        assert "No active policy found" in exc_info.value.detail


class TestToggleKillSwitch:
    """Test POST /v1/{project_code}/admin/kill-switch endpoint"""

    @patch('src.api.admin.AdminService.toggle_kill_switch')
    async def test_toggle_kill_switch_enable(self, mock_toggle, mock_authenticated_client, mock_db_session):
        """Should enable kill switch successfully"""
        request = KillSwitchRequest(
            enabled=True,
            reason="Emergency maintenance"
        )

        mock_audit = Mock()
        mock_audit.timestamp = datetime(2025, 1, 1, 12, 0, 0)
        mock_audit.actor = "test-client"
        mock_toggle.return_value = mock_audit

        result = await toggle_kill_switch(request, mock_authenticated_client, mock_db_session)

        assert result.enabled is True
        assert result.reason == "Emergency maintenance"
        assert result.changed_by == "test-client"

    @patch('src.api.admin.AdminService.toggle_kill_switch')
    async def test_toggle_kill_switch_error(self, mock_toggle, mock_authenticated_client, mock_db_session):
        """Should raise 500 on error"""
        request = KillSwitchRequest(enabled=True, reason="Test")
        mock_toggle.side_effect = Exception("Database error")

        with pytest.raises(HTTPException) as exc_info:
            await toggle_kill_switch(request, mock_authenticated_client, mock_db_session)

        assert exc_info.value.status_code == 500


@patch('src.api.admin.AdminService.get_kill_switch_status')
async def test_get_kill_switch_status_enabled(mock_get, mock_authenticated_client, mock_db_session):
    """Test GET /v1/{project_code}/admin/kill-switch endpoint"""
    mock_get.return_value = (
        True,
        "Maintenance mode",
        datetime(2025, 1, 1, 10, 0, 0),
        "admin-user"
    )

    result = await get_kill_switch_status(mock_authenticated_client, mock_db_session)

    assert result.enabled is True
    assert result.reason == "Maintenance mode"
    assert result.changed_by == "admin-user"


@patch('src.api.admin.AdminService.get_audit_logs')
async def test_get_audit_logs_success(mock_get, mock_authenticated_client, mock_db_session):
    """Test GET /v1/{project_code}/admin/audit-logs endpoint"""
    mock_log1 = Mock()
    mock_log1.audit_log_id = 1
    mock_log1.timestamp = datetime(2025, 1, 1, 10, 0, 0)
    mock_log1.actor = "user-1"
    mock_log1.action = "CREATE"
    mock_log1.entity = "policy"
    mock_log1.entity_id = "policy-1"
    mock_log1.details = {"version": 1}

    mock_log2 = Mock()
    mock_log2.audit_log_id = 2
    mock_log2.timestamp = datetime(2025, 1, 1, 11, 0, 0)
    mock_log2.actor = "user-2"
    mock_log2.action = "UPDATE"
    mock_log2.entity = "kill_switch"
    mock_log2.entity_id = "system-1"  # Must be a string, not None
    mock_log2.details = {"enabled": True}

    mock_get.return_value = [mock_log1, mock_log2]

    result = await get_audit_logs(100, 0, mock_authenticated_client, mock_db_session)

    assert len(result) == 2
    assert result[0].audit_log_id == 1
    assert result[1].audit_log_id == 2
    mock_get.assert_called_once_with(
        project_id="proj-123",
        limit=100,
        offset=0,
        entity_filter=None,
        action_filter=None,
        db=mock_db_session
    )


class TestStoreExedraConfig:
    """Test POST /v1/{project_code}/admin/exedra-config endpoint"""

    @patch('src.api.admin.AdminService.store_exedra_config')
    async def test_store_exedra_config_success(self, mock_store, mock_authenticated_client, mock_db_session):
        """Should store EXEDRA config successfully"""
        request = ExedraConfigRequest(
            api_client_id="client-123",
            api_token="test-token",
            base_url="https://exedra.test",
            environment="production"
        )

        created_at = datetime(2025, 1, 1, 10, 0, 0)
        mock_store.return_value = ("token-cred-123", "url-cred-123", created_at)

        result = await store_exedra_config(request, mock_authenticated_client, mock_db_session)

        assert result.token_credential_id == "token-cred-123"
        assert result.url_credential_id == "url-cred-123"
        assert result.api_client_id == "client-123"
        assert result.environment == "production"

    @patch('src.api.admin.AdminService.store_exedra_config')
    async def test_store_exedra_config_value_error(self, mock_store, mock_authenticated_client, mock_db_session):
        """Should raise 400 on ValueError"""
        request = ExedraConfigRequest(
            api_client_id="client-123",
            api_token="",
            base_url="https://exedra.test",
            environment="production"
        )
        mock_store.side_effect = ValueError("Invalid token")

        with pytest.raises(HTTPException) as exc_info:
            await store_exedra_config(request, mock_authenticated_client, mock_db_session)

        assert exc_info.value.status_code == 400


async def test_get_current_api_key_success(mock_authenticated_client, mock_db_session):
    """Test GET /v1/{project_code}/admin/api-key endpoint"""
    result = await get_current_api_key(mock_authenticated_client, mock_db_session)

    assert result.api_client_name == "test-client"
    assert result.scopes == ["admin:policy:create", "admin:policy:read"]


class TestGenerateApiKey:
    """Test POST /v1/{project_code}/admin/api-key endpoint"""

    @patch('src.api.admin.AdminService.get_api_client_by_name')
    @patch('src.api.admin.AdminService.generate_api_key')
    async def test_generate_api_key_success(
        self,
        mock_generate,
        mock_get_client,
        mock_authenticated_client,
        mock_db_session,
    ):
        """Should generate API key successfully"""
        request = ApiKeyRequest(
            api_client_name="target-client",
            scopes=["asset:read", "asset:write"]
        )

        mock_client = Mock()
        mock_client.api_client_id = "target-client-123"
        mock_client.name = "target-client"
        mock_get_client.return_value = mock_client

        mock_generate.return_value = ("key-123", "raw-api-key-456")

        result = await generate_api_key(request, mock_authenticated_client, mock_db_session)

        assert result.api_key_id == "key-123"
        assert result.api_key == "raw-api-key-456"
        assert result.api_client_id == "target-client-123"
        assert result.scopes == ["asset:read", "asset:write"]

    @patch('src.api.admin.AdminService.get_api_client_by_name')
    @patch('src.api.admin.AdminService.generate_api_key')
    async def test_generate_api_key_generic_error(
        self,
        mock_generate,
        mock_get_client,
        mock_authenticated_client,
        mock_db_session,
    ):
        """Should raise 500 on generic exception"""
        request = ApiKeyRequest(
            api_client_name="test-client",
            scopes=["asset:read"]
        )

        mock_client = Mock()
        mock_client.api_client_id = "client-123"
        mock_client.name = "test-client"
        mock_get_client.return_value = mock_client
        mock_generate.side_effect = Exception("Database error")

        with pytest.raises(HTTPException) as exc_info:
            await generate_api_key(request, mock_authenticated_client, mock_db_session)

        assert exc_info.value.status_code == 500

    @patch('src.api.admin.AdminService.get_api_client_by_name')
    @patch('src.api.admin.AdminService.generate_api_key')
    async def test_generate_api_key_value_error(
        self,
        mock_generate,
        mock_get_client,
        mock_authenticated_client,
        mock_db_session,
    ):
        """Should raise 400 on ValueError"""
        request = ApiKeyRequest(
            api_client_name="target-client",
            scopes=["invalid:scope"]
        )

        mock_client = Mock()
        mock_client.api_client_id = "client-123"
        mock_client.name = "target-client"
        mock_get_client.return_value = mock_client

        mock_generate.side_effect = ValueError("Invalid scope")

        with pytest.raises(HTTPException) as exc_info:
            await generate_api_key(request, mock_authenticated_client, mock_db_session)

        assert exc_info.value.status_code == 400


@patch('src.api.admin.AdminService.update_api_key')
async def test_update_api_key_success(mock_update, mock_authenticated_client, mock_db_session):
    """Test PUT /v1/{project_code}/admin/api-key/{api_key_id} endpoint"""
    api_key_id = "key-123"
    request = ApiKeyUpdateRequest(scopes=["asset:read", "sensor:read"])

    mock_key = Mock()
    mock_key.api_key_id = api_key_id
    mock_key.api_client_id = "client-123"
    mock_key.api_client = Mock()
    mock_key.api_client.name = "test-client"
    mock_key.scopes = ["asset:read", "sensor:read"]
    mock_key.created_at = datetime(2025, 1, 1, 10, 0, 0)
    mock_update.return_value = mock_key

    result = await update_api_key(api_key_id, request, mock_authenticated_client, mock_db_session)

    assert result.api_key_id == api_key_id
    assert result.api_key == "[HIDDEN]"
    assert result.scopes == ["asset:read", "sensor:read"]


class TestDeleteApiKey:
    """Test DELETE /v1/{project_code}/admin/api-key/{api_key_id} endpoint"""

    @patch('src.api.admin.AdminService.delete_api_key')
    async def test_delete_api_key_success(self, mock_delete, mock_authenticated_client, mock_db_session):
        """Should delete API key successfully"""
        api_key_id = "key-123"

        result = await delete_api_key(api_key_id, mock_authenticated_client, mock_db_session)

        assert "deleted successfully" in result["message"]
        mock_delete.assert_called_once_with(
            api_key_id=api_key_id,
            project_id="proj-123",
            api_client_name="test-client",
            db=mock_db_session
        )

    @patch('src.api.admin.AdminService.delete_api_key')
    async def test_delete_api_key_not_found(self, mock_delete, mock_authenticated_client, mock_db_session):
        """Should raise 404 when API key not found"""
        api_key_id = "nonexistent-key"
        mock_delete.side_effect = ValueError("API key not found")

        with pytest.raises(HTTPException) as exc_info:
            await delete_api_key(api_key_id, mock_authenticated_client, mock_db_session)

        assert exc_info.value.status_code == 404


@patch('src.api.admin.ScopeService.get_all_scopes')
@patch('src.api.admin.ScopeService.get_recommended_scopes')
async def test_list_available_scopes_success(mock_recommended, mock_all, mock_authenticated_client, mock_db_session):
    """Test GET /v1/{project_code}/admin/scopes endpoint"""
    mock_all.return_value = {
        "asset:read": {
            "description": "Read asset data",
            "category": "asset"
        },
        "asset:write": {
            "description": "Write asset data",
            "category": "asset"
        }
    }

    mock_recommended.return_value = {
        "read_only": ["asset:read", "sensor:read"],
        "full_access": ["asset:read", "asset:write", "sensor:read", "sensor:write"]
    }

    result = await list_available_scopes(mock_authenticated_client, mock_db_session)

    assert len(result.scopes) == 2
    assert result.scopes[0].scope_code == "asset:read"
    assert result.recommended_combinations["read_only"] == ["asset:read", "sensor:read"]


@patch('src.api.admin.AdminService.sync_scope_catalogue_with_audit')
async def test_sync_scope_catalogue_success(mock_sync, mock_authenticated_client, mock_db_session):
    """Test POST /v1/{project_code}/admin/scopes/sync endpoint"""
    mock_sync.return_value = 15

    result = await sync_scope_catalogue(mock_authenticated_client, mock_db_session)

    assert result["scopes_updated"] == 15
    assert "synced successfully" in result["message"]
    mock_sync.assert_called_once_with(
        project_id="proj-123",
        api_client_name="test-client",
        db=mock_db_session
    )
