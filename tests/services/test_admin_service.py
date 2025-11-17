"""
Tests for AdminService - administrative operations including policies, kill switch,
API keys, audit logs, and EXEDRA configuration.
"""
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from src.services.admin_service import AdminService
from src.db.models import Policy, AuditLog, ApiClient, ApiKey, Project
from src.schemas.admin import PolicyRequest


class TestValidatePolicyBody:
    """Tests for policy body validation"""

    def test_validate_policy_body_valid(self):
        """Test validation with valid policy body"""
        policy_body = {
            "min_dim": 10,
            "max_dim": 90,
            "max_changes_per_hr": 5
        }
        is_valid, error = AdminService.validate_policy_body(policy_body)
        assert is_valid is True
        assert error is None

    def test_validate_policy_body_missing_field(self):
        """Test validation with missing required field"""
        policy_body = {
            "min_dim": 10,
            "max_dim": 90
            # missing max_changes_per_hr
        }
        is_valid, error = AdminService.validate_policy_body(policy_body)
        assert is_valid is False
        assert "Missing required policy field: max_changes_per_hr" in error

    def test_validate_policy_body_invalid_min_dim(self):
        """Test validation with min_dim < 0"""
        policy_body = {
            "min_dim": -5,
            "max_dim": 90,
            "max_changes_per_hr": 5
        }
        is_valid, error = AdminService.validate_policy_body(policy_body)
        assert is_valid is False
        assert "between 0 and 100" in error

    def test_validate_policy_body_invalid_max_dim(self):
        """Test validation with max_dim > 100"""
        policy_body = {
            "min_dim": 10,
            "max_dim": 150,
            "max_changes_per_hr": 5
        }
        is_valid, error = AdminService.validate_policy_body(policy_body)
        assert is_valid is False
        assert "between 0 and 100" in error

    def test_validate_policy_body_min_greater_than_max(self):
        """Test validation where min_dim >= max_dim"""
        policy_body = {
            "min_dim": 90,
            "max_dim": 50,
            "max_changes_per_hr": 5
        }
        is_valid, error = AdminService.validate_policy_body(policy_body)
        assert is_valid is False
        assert "min_dim must be less than max_dim" in error

    def test_validate_policy_body_min_equals_max(self):
        """Test validation where min_dim == max_dim"""
        policy_body = {
            "min_dim": 50,
            "max_dim": 50,
            "max_changes_per_hr": 5
        }
        is_valid, error = AdminService.validate_policy_body(policy_body)
        assert is_valid is False
        assert "min_dim must be less than max_dim" in error

    def test_validate_policy_body_zero_max_changes(self):
        """Test validation with max_changes_per_hr <= 0"""
        policy_body = {
            "min_dim": 10,
            "max_dim": 90,
            "max_changes_per_hr": 0
        }
        is_valid, error = AdminService.validate_policy_body(policy_body)
        assert is_valid is False
        assert "must be positive" in error


class TestCreatePolicy:
    """Tests for policy creation"""

    def test_create_policy_success(self):
        """Test successful policy creation"""
        mock_db = Mock(spec=Session)

        request = PolicyRequest(
            version="v1.2",
            body={"min_dim": 20, "max_dim": 80, "max_changes_per_hr": 10}
        )

        # Mock the policy object
        mock_policy = Mock(spec=Policy)
        mock_policy.policy_id = "test-policy-id"

        # Capture added objects
        added_objects = []
        mock_db.add.side_effect = added_objects.append
        mock_db.flush.return_value = None
        mock_db.commit.return_value = None

        AdminService.create_policy(
            request=request,
            project_id="proj-123",
            api_client_name="test-client",
            db=mock_db
        )

        # Verify policy was created
        assert mock_db.add.call_count == 2  # Policy + AuditLog
        assert mock_db.flush.called
        assert mock_db.commit.called

        # Verify policy object
        policy_obj = added_objects[0]
        assert isinstance(policy_obj, Policy)
        assert policy_obj.project_id == "proj-123"
        assert policy_obj.version == "v1.2"
        assert policy_obj.body == request.body

        # Verify audit log
        audit_obj = added_objects[1]
        assert isinstance(audit_obj, AuditLog)
        assert audit_obj.action == "policy_update"
        assert audit_obj.entity == "policy"
        assert audit_obj.project_id == "proj-123"


class TestGetCurrentPolicy:
    """Tests for retrieving current policy"""

    def test_get_current_policy_exists(self):
        """Test getting current policy when it exists"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_policy = Mock(spec=Policy)
        mock_policy.project_id = "proj-123"
        mock_policy.version = "v1.0"

        # Setup query chain
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_policy

        result = AdminService.get_current_policy("proj-123", mock_db)

        assert result == mock_policy
        mock_db.query.assert_called_once_with(Policy)

    def test_get_current_policy_not_exists(self):
        """Test getting current policy when none exists"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        # Setup query to return None
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None

        result = AdminService.get_current_policy("proj-123", mock_db)

        assert result is None


class TestToggleKillSwitch:
    """Tests for kill switch operations"""

    def test_toggle_kill_switch_enable(self):
        """Test enabling kill switch"""
        mock_db = Mock(spec=Session)
        added_objects = []
        mock_db.add.side_effect = added_objects.append

        AdminService.toggle_kill_switch(
            enabled=True,
            reason="Emergency shutdown",
            project_id="proj-123",
            api_client_name="admin-client",
            db=mock_db
        )

        # Verify audit log creation
        assert len(added_objects) == 1
        audit_log = added_objects[0]
        assert isinstance(audit_log, AuditLog)
        assert audit_log.action == "kill_switch_toggle"
        assert audit_log.entity == "system"
        assert audit_log.project_id == "proj-123"
        assert audit_log.details["enabled"] is True
        assert audit_log.details["reason"] == "Emergency shutdown"

        mock_db.commit.assert_called_once()

    def test_toggle_kill_switch_disable(self):
        """Test disabling kill switch"""
        mock_db = Mock(spec=Session)
        added_objects = []
        mock_db.add.side_effect = added_objects.append

        AdminService.toggle_kill_switch(
            enabled=False,
            reason=None,
            project_id="proj-123",
            api_client_name="admin-client",
            db=mock_db
        )

        audit_log = added_objects[0]
        assert audit_log.details["enabled"] is False
        assert audit_log.details["reason"] is None


class TestGetKillSwitchStatus:
    """Tests for getting kill switch status"""

    def test_get_kill_switch_status_exists(self):
        """Test getting kill switch status when toggle exists"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_audit = Mock(spec=AuditLog)
        mock_audit.timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_audit.details = {
            "enabled": True,
            "reason": "Maintenance",
            "api_client": "admin-client"
        }

        # Setup query chain
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_audit

        enabled, reason, changed_at, changed_by = AdminService.get_kill_switch_status(
            "proj-123", mock_db
        )

        assert enabled is True
        assert reason == "Maintenance"
        assert changed_at == mock_audit.timestamp
        assert changed_by == "admin-client"

    def test_get_kill_switch_status_not_exists(self):
        """Test getting kill switch status when no toggle exists (default)"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        # Setup query to return None
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None

        enabled, reason, changed_at, changed_by = AdminService.get_kill_switch_status(
            "proj-123", mock_db
        )

        assert enabled is False
        assert reason is None
        assert isinstance(changed_at, datetime)
        assert changed_by == "system"


class TestGetAuditLogs:
    """Tests for retrieving audit logs"""

    def test_get_audit_logs_no_filters(self):
        """Test getting audit logs without filters"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_logs = [Mock(spec=AuditLog) for _ in range(3)]

        # Setup query chain
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = mock_logs

        result = AdminService.get_audit_logs(
            project_id="proj-123",
            limit=10,
            offset=0,
            entity_filter=None,
            action_filter=None,
            db=mock_db
        )

        assert result == mock_logs
        assert mock_query.offset.called
        assert mock_query.limit.called

    def test_get_audit_logs_with_entity_filter(self):
        """Test getting audit logs with entity filter"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_logs = [Mock(spec=AuditLog)]

        # Setup query chain
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = mock_logs

        result = AdminService.get_audit_logs(
            project_id="proj-123",
            limit=10,
            offset=0,
            entity_filter="policy",
            action_filter=None,
            db=mock_db
        )

        assert result == mock_logs
        # Verify filter was called multiple times (for project_id and entity)
        assert mock_query.filter.call_count >= 2

    def test_get_audit_logs_with_action_filter(self):
        """Test getting audit logs with action filter"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_logs = [Mock(spec=AuditLog)]

        # Setup query chain
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = mock_logs

        result = AdminService.get_audit_logs(
            project_id="proj-123",
            limit=10,
            offset=5,
            entity_filter=None,
            action_filter="policy_update",
            db=mock_db
        )

        assert result == mock_logs
        mock_query.offset.assert_called_with(5)
        mock_query.limit.assert_called_with(10)


class TestStoreExedraConfig:
    """Tests for storing EXEDRA configuration"""

    def test_store_exedra_config_success(self):
        """Test successful EXEDRA config storage"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_client = Mock(spec=ApiClient)
        mock_client.api_client_id = "client-123"
        mock_client.project_id = "proj-123"

        # Setup query chain
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_client

        # Mock CredentialService
        with patch('src.services.admin_service.CredentialService.store_exedra_config') as mock_store:
            mock_token_cred = Mock()
            mock_token_cred.credential_id = "token-cred-id"
            mock_token_cred.created_at = datetime.now(timezone.utc)

            mock_url_cred = Mock()
            mock_url_cred.credential_id = "url-cred-id"

            mock_store.return_value = (mock_token_cred, mock_url_cred)

            token_id, url_id, created_at = AdminService.store_exedra_config(
                api_client_id="client-123",
                api_token="test-token",
                base_url="https://api.exedra.com",
                project_id="proj-123",
                environment="prod",
                db=mock_db
            )

            assert token_id == "token-cred-id"
            assert url_id == "url-cred-id"
            assert created_at == mock_token_cred.created_at
            mock_store.assert_called_once()

    def test_store_exedra_config_client_not_found(self):
        """Test storing EXEDRA config when client not found"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        # Setup query to return None
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(ValueError, match="API client client-123 not found"):
            AdminService.store_exedra_config(
                api_client_id="client-123",
                api_token="test-token",
                base_url="https://api.exedra.com",
                project_id="proj-123",
                environment="prod",
                db=mock_db
            )


class TestGenerateApiKey:
    """Tests for API key generation"""

    def test_generate_api_key_success(self):
        """Test successful API key generation"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_client = Mock(spec=ApiClient)
        mock_client.api_client_id = "client-123"
        mock_client.project_id = "proj-123"

        # Setup query chain for client lookup
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_client

        # Mock ScopeService validation
        with patch('src.services.admin_service.ScopeService.validate_scopes') as mock_validate:
            mock_validate.return_value = (["asset", "admin"], [])

            # Mock hash_api_key
            with patch('src.services.admin_service.hash_api_key') as mock_hash:
                mock_hash.return_value = (b'hashed_key', b'salt')

                # Mock the ApiKey object created
                created_key = None
                def capture_add(obj):
                    nonlocal created_key
                    if isinstance(obj, ApiKey):
                        created_key = obj
                        # Simulate database generating UUID
                        obj.api_key_id = "12345678-1234-1234-1234-123456789abc"

                mock_db.add.side_effect = capture_add

                key_id, raw_key = AdminService.generate_api_key(
                    api_client_id="client-123",
                    project_id="proj-123",
                    scopes=["asset", "admin"],
                    db=mock_db
                )

                assert key_id == "12345678-1234-1234-1234-123456789abc"
                assert raw_key.startswith("12345678")  # First 8 chars of UUID
                assert "_" in raw_key
                assert len(raw_key) > 8  # Has suffix

                mock_db.commit.assert_called_once()
                mock_validate.assert_called_once_with(["asset", "admin"], db=mock_db)

    def test_generate_api_key_client_not_found(self):
        """Test API key generation when client not found"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        # Setup query to return None
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(ValueError, match="API client client-123 not found"):
            AdminService.generate_api_key(
                api_client_id="client-123",
                project_id="proj-123",
                scopes=["asset"],
                db=mock_db
            )

    def test_generate_api_key_invalid_scopes(self):
        """Test API key generation with invalid scopes"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_client = Mock(spec=ApiClient)
        mock_client.api_client_id = "client-123"

        # Setup query chain
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_client

        # Mock ScopeService to return no valid scopes
        with patch('src.services.admin_service.ScopeService.validate_scopes') as mock_validate:
            mock_validate.return_value = ([], ["invalid_scope"])

            with pytest.raises(ValueError, match="Invalid scopes"):
                AdminService.generate_api_key(
                    api_client_id="client-123",
                    project_id="proj-123",
                    scopes=["invalid_scope"],
                    db=mock_db
                )


class TestGetApiClientByName:
    """Tests for getting API client by name"""

    def test_get_api_client_by_name_found(self):
        """Test getting API client by name when it exists"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_client = Mock(spec=ApiClient)
        mock_client.name = "test-client"

        # Setup query chain with join
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_client

        result = AdminService.get_api_client_by_name(
            project_code="scs-dev",
            client_name="test-client",
            db=mock_db
        )

        assert result == mock_client
        mock_query.join.assert_called_once_with(Project)

    def test_get_api_client_by_name_not_found(self):
        """Test getting API client by name when it doesn't exist"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        # Setup query to return None
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        result = AdminService.get_api_client_by_name(
            project_code="scs-dev",
            client_name="nonexistent",
            db=mock_db
        )

        assert result is None


class TestDeleteApiKey:
    """Tests for API key deletion"""

    def test_delete_api_key_success(self):
        """Test successful API key deletion"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_client = Mock(spec=ApiClient)
        mock_client.project_id = "proj-123"
        mock_client.name = "test-client"

        mock_key = Mock(spec=ApiKey)
        mock_key.api_key_id = "key-123"
        mock_key.api_client_id = "client-123"
        mock_key.api_client = mock_client
        mock_key.scopes = ["asset"]
        mock_key.last_used_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Setup query chain with join
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_key

        added_objects = []
        mock_db.add.side_effect = added_objects.append

        AdminService.delete_api_key(
            api_key_id="key-123",
            project_id="proj-123",
            api_client_name="admin-client",
            db=mock_db
        )

        # Verify key deletion
        mock_db.delete.assert_called_once_with(mock_key)

        # Verify audit log
        assert len(added_objects) == 1
        audit_log = added_objects[0]
        assert isinstance(audit_log, AuditLog)
        assert audit_log.action == "delete_api_key"
        assert audit_log.entity == "api_key"
        assert audit_log.entity_id == "key-123"

        mock_db.commit.assert_called_once()

    def test_delete_api_key_not_found(self):
        """Test deleting API key when it doesn't exist"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        # Setup query to return None
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(ValueError, match="API key key-123 not found"):
            AdminService.delete_api_key(
                api_key_id="key-123",
                project_id="proj-123",
                api_client_name="admin-client",
                db=mock_db
            )


class TestUpdateApiKey:
    """Tests for API key updates"""

    def test_update_api_key_success(self):
        """Test successful API key scope update"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_client = Mock(spec=ApiClient)
        mock_client.project_id = "proj-123"
        mock_client.name = "test-client"

        mock_key = Mock(spec=ApiKey)
        mock_key.api_key_id = "key-123"
        mock_key.api_client_id = "client-123"
        mock_key.api_client = mock_client
        mock_key.scopes = ["asset"]

        # Setup query chain
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_key

        # Mock ScopeService validation
        with patch('src.services.admin_service.ScopeService.validate_scopes') as mock_validate:
            mock_validate.return_value = (["asset", "admin"], [])

            added_objects = []
            mock_db.add.side_effect = added_objects.append

            AdminService.update_api_key(
                api_key_id="key-123",
                scopes=["asset", "admin"],
                project_id="proj-123",
                api_client_name="admin-client",
                db=mock_db
            )

            # Verify scopes updated
            assert mock_key.scopes == ["asset", "admin"]

            # Verify audit log
            assert len(added_objects) == 1
            audit_log = added_objects[0]
            assert audit_log.action == "update_api_key"
            assert audit_log.details["old_scopes"] == ["asset"]
            assert audit_log.details["new_scopes"] == ["asset", "admin"]

            mock_db.commit.assert_called_once()
            mock_db.refresh.assert_called_once_with(mock_key)

    def test_update_api_key_not_found(self):
        """Test updating API key when it doesn't exist"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        # Setup query to return None
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(ValueError, match="API key key-123 not found"):
            AdminService.update_api_key(
                api_key_id="key-123",
                scopes=["asset"],
                project_id="proj-123",
                api_client_name="admin-client",
                db=mock_db
            )

    def test_update_api_key_invalid_scopes(self):
        """Test updating API key with invalid scopes"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_client = Mock(spec=ApiClient)
        mock_key = Mock(spec=ApiKey)
        mock_key.api_client = mock_client

        # Setup query chain
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_key

        # Mock ScopeService to return no valid scopes
        with patch('src.services.admin_service.ScopeService.validate_scopes') as mock_validate:
            mock_validate.return_value = ([], ["bad_scope"])

            with pytest.raises(ValueError, match="Invalid scopes"):
                AdminService.update_api_key(
                    api_key_id="key-123",
                    scopes=["bad_scope"],
                    project_id="proj-123",
                    api_client_name="admin-client",
                    db=mock_db
                )


class TestSyncScopeCatalogueWithAudit:
    """Tests for scope catalogue sync"""

    def test_sync_scope_catalogue_success(self):
        """Test successful scope catalogue sync"""
        mock_db = Mock(spec=Session)

        # Mock ScopeService sync
        with patch('src.services.admin_service.ScopeService.sync_catalogue_to_database') as mock_sync:
            mock_sync.return_value = 15  # 15 scopes updated

            added_objects = []
            mock_db.add.side_effect = added_objects.append

            count = AdminService.sync_scope_catalogue_with_audit(
                project_id="proj-123",
                api_client_name="admin-client",
                db=mock_db
            )

            assert count == 15

            # Verify audit log
            assert len(added_objects) == 1
            audit_log = added_objects[0]
            assert isinstance(audit_log, AuditLog)
            assert audit_log.action == "scope_catalogue_sync"
            assert audit_log.entity == "system"
            assert audit_log.details["scopes_updated"] == 15

            mock_db.commit.assert_called_once()
            mock_sync.assert_called_once_with(mock_db)
