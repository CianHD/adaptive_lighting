"""
Tests for AssetService - asset operations, schedule management, commissioning,
and external EXEDRA API integration.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from src.services.asset_service import AssetService
from src.db.models import Asset, Schedule, AuditLog, Policy, RealtimeCommand, Project, ApiClient
from src.schemas.asset import AssetResponse, AssetStateResponse
from src.schemas.command import RealtimeCommandRequest


class TestGetAssetByExternalId:
    """Tests for getting asset by external ID"""

    def test_get_asset_by_external_id_found(self):
        """Test getting asset when it exists"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_asset = Mock(spec=Asset)
        mock_asset.external_id = "EXT-123"
        mock_asset.project_id = "proj-123"

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_asset

        result = AssetService.get_asset_by_external_id("EXT-123", "proj-123", mock_db)

        assert result == mock_asset
        mock_db.query.assert_called_once_with(Asset)

    def test_get_asset_by_external_id_not_found(self):
        """Test getting asset when it doesn't exist"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        result = AssetService.get_asset_by_external_id("EXT-999", "proj-123", mock_db)

        assert result is None


class TestGetAssetState:
    """Tests for getting asset state"""

    def test_get_asset_state_success(self):
        """Test successful asset state retrieval"""
        mock_db = Mock(spec=Session)

        mock_project = Mock(spec=Project)
        mock_api_client = Mock(spec=ApiClient)
        mock_project.api_clients = [mock_api_client]

        mock_asset = Mock(spec=Asset)
        mock_asset.external_id = "EXT-123"
        mock_asset.project = mock_project
        mock_asset.updated_at = datetime.now(timezone.utc)

        # Mock schedule retrieval
        with patch.object(AssetService, 'get_asset_exedra_schedule') as mock_schedule:
            mock_schedule.return_value = {"schedule_id": "sched-123"}

            # Mock credential service
            with patch('src.services.asset_service.CredentialService.get_exedra_config') as mock_creds:
                mock_creds.return_value = {
                    "token": "test-token",
                    "base_url": "https://api.exedra.com"
                }

                # Mock ExedraService dimming call
                with patch('src.services.asset_service.ExedraService.get_device_dimming_level') as mock_dim:
                    mock_dim.return_value = {"level": 75}

                    result = AssetService.get_asset_state(mock_asset, mock_db)

                    assert isinstance(result, AssetStateResponse)
                    assert result.exedra_id == "EXT-123"
                    assert result.current_dim_percent == 75
                    assert result.current_schedule_id == "sched-123"

    def test_get_asset_state_fallback_on_exedra_error(self):
        """Test asset state falls back to local DB on EXEDRA error"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_project = Mock(spec=Project)
        mock_project.api_clients = []

        mock_asset = Mock(spec=Asset)
        mock_asset.external_id = "EXT-123"
        mock_asset.project = mock_project
        mock_asset.asset_id = "asset-123"
        mock_asset.updated_at = datetime.now(timezone.utc)

        mock_schedule = Mock(spec=Schedule)
        mock_schedule.schedule_id = "local-sched-123"

        # Mock schedule query for fallback
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_schedule

        # Mock get_asset_exedra_schedule to raise error
        with patch.object(AssetService, 'get_asset_exedra_schedule') as mock_get_schedule:
            mock_get_schedule.side_effect = RuntimeError("EXEDRA unavailable")

            result = AssetService.get_asset_state(mock_asset, mock_db)

            assert isinstance(result, AssetStateResponse)
            assert result.current_schedule_id == "local-sched-123"
            assert result.current_dim_percent is None  # No dimming data available

    def test_get_asset_state_simulation_skips_exedra(self):
        """Simulation mode should not call EXEDRA for dimming."""
        mock_db = Mock(spec=Session)

        mock_project = Mock(spec=Project)
        mock_project.api_clients = []
        mock_project.mode = "simulation"

        mock_asset = Mock(spec=Asset)
        mock_asset.external_id = "EXT-123"
        mock_asset.project = mock_project
        mock_asset.updated_at = datetime.now(timezone.utc)

        with patch.object(AssetService, 'get_asset_exedra_schedule') as mock_schedule, \
             patch('src.services.asset_service.ExedraService.get_device_dimming_level') as mock_dim:

            mock_schedule.return_value = {"schedule_id": "sched-123"}

            result = AssetService.get_asset_state(mock_asset, mock_db)

            assert isinstance(result, AssetStateResponse)
            assert result.current_schedule_id == "sched-123"
            mock_dim.assert_not_called()


class TestGetAssetDetails:
    """Tests for getting asset details"""

    def test_get_asset_details(self):
        """Test getting asset details"""
        mock_asset = Mock(spec=Asset)
        mock_asset.external_id = "EXT-123"
        mock_asset.name = "Test Asset"
        mock_asset.control_mode = "optimise"
        mock_asset.road_class = "A"
        mock_asset.asset_metadata = {"key": "value"}

        result = AssetService.get_asset_details(mock_asset)

        assert isinstance(result, AssetResponse)
        assert result.exedra_id == "EXT-123"
        assert result.name == "Test Asset"
        assert result.control_mode == "optimise"
        assert result.road_class == "A"
        assert result.metadata == {"key": "value"}


class TestUpdateControlMode:
    """Tests for updating control mode"""

    def test_update_control_mode(self):
        """Test successful control mode update"""
        mock_db = Mock(spec=Session)

        mock_asset = Mock(spec=Asset)
        mock_asset.asset_id = "asset-123"
        mock_asset.external_id = "EXT-123"
        mock_asset.control_mode = "passthrough"

        added_objects = []
        mock_db.add.side_effect = added_objects.append

        result = AssetService.update_control_mode(
            asset=mock_asset,
            new_mode="optimise",
            api_client_name="test-client",
            project_id="proj-123",
            db=mock_db
        )

        assert result == mock_asset
        assert mock_asset.control_mode == "optimise"

        # Verify audit log
        assert len(added_objects) == 1
        audit_log = added_objects[0]
        assert isinstance(audit_log, AuditLog)
        assert audit_log.action == "control_mode_change"
        assert audit_log.details["old_mode"] == "passthrough"
        assert audit_log.details["new_mode"] == "optimise"

        mock_db.commit.assert_called_once()


class TestGetAssetExedraSchedule:
    """Tests for getting EXEDRA schedule"""

    def test_get_asset_exedra_schedule_success(self):
        """Test successful EXEDRA schedule retrieval"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_api_client = Mock(spec=ApiClient)
        mock_api_client.name = "test-client"

        mock_project = Mock(spec=Project)
        mock_project.api_clients = [mock_api_client]

        mock_asset = Mock(spec=Asset)
        mock_asset.external_id = "EXT-123"
        mock_asset.project = mock_project
        mock_asset.asset_id = "asset-123"

        mock_schedule = Mock(spec=Schedule)
        mock_schedule.exedra_control_program_id = "prog-123"
        mock_schedule.updated_at = datetime.now(timezone.utc)

        # Setup query chain
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_schedule

        # Mock CredentialService
        with patch('src.services.asset_service.CredentialService.get_exedra_config') as mock_creds:
            mock_creds.return_value = {
                "token": "test-token",
                "base_url": "https://api.exedra.com"
            }

            # Mock ExedraService
            with patch('src.services.asset_service.ExedraService.get_control_program') as mock_get_prog:
                mock_get_prog.return_value = {
                    "commands": [
                        {"base": "midnight", "offset": 0, "level": 50},
                        {"base": "midnight", "offset": 720, "level": 100}  # 12 hours
                    ]
                }

                result = AssetService.get_asset_exedra_schedule(mock_asset, mock_db)

                assert result["schedule_id"] == "prog-123"
                assert result["provider"] == "exedra"
                assert result["status"] == "active"
                assert len(result["steps"]) == 2
                assert result["steps"][0]["time"] == "00:00"
                assert result["steps"][0]["dim"] == 50
                assert result["updated_at"] == mock_schedule.updated_at

    def test_get_asset_exedra_schedule_no_active_schedule(self):
        """Test EXEDRA schedule retrieval when no active schedule"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_asset = Mock(spec=Asset)
        mock_asset.external_id = "EXT-123"

        # Return None for schedule query
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(ValueError, match="has no active schedule"):
            AssetService.get_asset_exedra_schedule(mock_asset, mock_db)

    def test_get_asset_exedra_schedule_no_api_client(self):
        """Test EXEDRA schedule retrieval when no API client"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_project = Mock(spec=Project)
        mock_project.api_clients = []

        mock_asset = Mock(spec=Asset)
        mock_asset.external_id = "EXT-123"
        mock_asset.project = mock_project

        mock_schedule = Mock(spec=Schedule)
        mock_schedule.exedra_control_program_id = "prog-123"

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_schedule

        with pytest.raises(ValueError, match="No API client found"):
            AssetService.get_asset_exedra_schedule(mock_asset, mock_db)

    def test_get_asset_exedra_schedule_simulation(self):
        """Simulation mode returns local schedule without EXEDRA call."""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_project = Mock(spec=Project)
        mock_project.mode = "simulation"

        mock_asset = Mock(spec=Asset)
        mock_asset.external_id = "EXT-123"
        mock_asset.project = mock_project
        mock_asset.asset_id = "asset-123"

        mock_schedule = Mock(spec=Schedule)
        mock_schedule.schedule_id = "sched-123"
        mock_schedule.schedule = {"steps": [{"time": "00:00", "dim": 50}]}
        mock_schedule.status = "active"
        mock_schedule.updated_at = datetime.now(timezone.utc)

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_schedule

        with patch('src.services.asset_service.ExedraService.get_control_program') as mock_get_prog:
            result = AssetService.get_asset_exedra_schedule(mock_asset, mock_db)

        assert result["provider"] == "simulation"
        assert result["status"] == "active"
        assert result["steps"] == mock_schedule.schedule["steps"]
        mock_get_prog.assert_not_called()


class TestUpdateAssetScheduleInExedra:
    """Tests for updating asset schedule in EXEDRA"""

    def test_update_asset_schedule_success(self):  # pylint: disable=too-many-locals
        """Test successful schedule update"""
        mock_db = Mock(spec=Session)

        mock_api_client = Mock(spec=ApiClient)
        mock_api_client.name = "test-client"

        mock_project = Mock(spec=Project)
        mock_project.api_clients = [mock_api_client]

        mock_asset = Mock(spec=Asset)
        mock_asset.external_id = "EXT-123"
        mock_asset.project = mock_project
        mock_asset.asset_id = "asset-123"
        mock_asset.name = "Test Asset"

        mock_schedule = Mock(spec=Schedule)
        mock_schedule.exedra_control_program_id = "prog-123"

        # Setup query chain - need separate mock for each query call
        query_count = [0]
        def query_side_effect(model):
            mock_query = Mock()
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.update.return_value = None

            query_count[0] += 1
            if query_count[0] == 1:
                # First query: check idempotency
                mock_query.first.return_value = None
            elif query_count[0] == 2:
                # Second query: get active schedule
                mock_query.first.return_value = mock_schedule
            else:
                # Third query: update existing schedules
                mock_query.first.return_value = None

            return mock_query

        mock_db.query.side_effect = query_side_effect

        schedule_steps = [
            {"time": "00:00", "dim": 50},
            {"time": "12:00", "dim": 100}
        ]

        # Mock all external dependencies
        with patch('src.services.asset_service.CredentialService.get_exedra_config') as mock_creds, \
             patch('src.services.asset_service.ExedraService.create_schedule_from_steps') as mock_create, \
             patch('src.services.asset_service.ExedraService.validate_commands') as mock_validate, \
             patch('src.services.asset_service.ExedraService.update_control_program') as mock_update, \
             patch('src.services.asset_service.asyncio.create_task') as mock_create_task:

            mock_creds.return_value = {
                "token": "test-token",
                "base_url": "https://api.exedra.com"
            }
            mock_create.return_value = [{"base": "midnight", "offset": 0, "level": 50}]
            mock_validate.return_value = None
            mock_update.return_value = True

            def run_background_task(coro):
                """Execute the coroutine immediately so pytest sees no pending tasks."""
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    asyncio.run(coro)
                    return None
                return loop.create_task(coro)

            mock_create_task.side_effect = run_background_task

            added_objects = []
            def capture_add(obj):
                if isinstance(obj, Schedule):
                    obj.schedule_id = "new-sched-123"
                added_objects.append(obj)

            mock_db.add.side_effect = capture_add
            mock_db.flush.return_value = None

            result = AssetService.update_asset_schedule_in_exedra(
                asset=mock_asset,
                schedule_steps=schedule_steps,
                actor="test-actor",
                idempotency_key="idem-123",
                db=mock_db
            )

            assert result.schedule_id == "new-sched-123"
            mock_db.commit.assert_called()
            mock_create_task.assert_called()

    def test_update_asset_schedule_idempotency(self):
        """Test idempotency key prevents duplicate schedule creation"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_asset = Mock(spec=Asset)
        mock_asset.asset_id = "asset-123"

        existing_schedule = Mock(spec=Schedule)
        existing_schedule.schedule_id = "existing-sched-123"

        # First query returns existing schedule (idempotency check)
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = existing_schedule

        result = AssetService.update_asset_schedule_in_exedra(
            asset=mock_asset,
            schedule_steps=[{"time": "00:00", "dim": 50}],
            actor="test-actor",
            idempotency_key="idem-123",
            db=mock_db
        )

        assert result == existing_schedule
        assert result.schedule_id == "existing-sched-123"
        # Should not commit new schedule
        assert not mock_db.commit.called

    def test_update_asset_schedule_simulation_mode(self):
        """Simulation mode stores schedules locally without EXEDRA."""
        mock_db = Mock(spec=Session)

        mock_project = Mock(spec=Project)
        mock_project.mode = "simulation"

        mock_asset = Mock(spec=Asset)
        mock_asset.asset_id = "asset-123"
        mock_asset.external_id = "EXT-123"
        mock_asset.project = mock_project

        mock_active_schedule = Mock(spec=Schedule)
        mock_active_schedule.exedra_control_program_id = None
        mock_active_schedule.exedra_calendar_id = None

        idempotency_query = Mock()
        idempotency_query.filter.return_value = idempotency_query
        idempotency_query.first.return_value = None

        active_query = Mock()
        active_query.filter.return_value = active_query
        active_query.order_by.return_value = active_query
        active_query.first.return_value = mock_active_schedule

        supersede_query = Mock()
        supersede_query.filter.return_value = supersede_query
        supersede_query.update.return_value = None

        mock_db.query.side_effect = [idempotency_query, active_query, supersede_query]

        schedule_steps = [{"time": "00:00", "dim": 50}]

        added_objects = []

        def capture_add(obj):
            if isinstance(obj, Schedule):
                obj.schedule_id = "sim-sched-123"
            added_objects.append(obj)

        mock_db.add.side_effect = capture_add

        with patch('src.services.asset_service.ExedraService.update_control_program') as mock_update:
            result = AssetService.update_asset_schedule_in_exedra(
                asset=mock_asset,
                schedule_steps=schedule_steps,
                actor="tester",
                idempotency_key=None,
                db=mock_db
            )

        assert result.schedule_id == "sim-sched-123"
        assert result.provider == "simulation"
        assert result.is_simulated is True
        mock_update.assert_not_called()


class TestCommissionAsset:
    """Tests for asset commissioning"""

    def test_commission_asset_success(self):
        """Test successful asset commissioning"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_api_client = Mock(spec=ApiClient)
        mock_project = Mock(spec=Project)
        mock_project.api_clients = [mock_api_client]

        mock_asset = Mock(spec=Asset)
        mock_asset.external_id = "EXT-123"
        mock_asset.project = mock_project
        mock_asset.asset_id = "asset-123"

        mock_schedule = Mock(spec=Schedule)
        mock_schedule.schedule_id = "sched-123"
        mock_schedule.commission_attempts = 0
        mock_schedule.last_commission_attempt = None

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_schedule

        with patch('src.services.asset_service.CredentialService.get_exedra_config') as mock_creds, \
             patch('src.services.asset_service.ExedraService.commission_device') as mock_commission:

            mock_creds.return_value = {
                "token": "test-token",
                "base_url": "https://api.exedra.com"
            }
            mock_commission.return_value = {"status": "commissioned"}

            result = AssetService.commission_asset(
                asset=mock_asset,
                actor="test-actor",
                db=mock_db
            )

            assert result is True
            assert mock_schedule.status == "active"
            assert mock_schedule.commission_error is None
            mock_db.commit.assert_called()

    def test_commission_asset_no_pending_schedule(self):
        """Test commissioning when no pending schedule exists"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_asset = Mock(spec=Asset)
        mock_asset.external_id = "EXT-123"

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(ValueError, match="has no pending commission schedule"):
            AssetService.commission_asset(
                asset=mock_asset,
                actor="test-actor",
                db=mock_db
            )

    def test_commission_asset_max_retries_exceeded(self):
        """Test commissioning when max retries exceeded"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_asset = Mock(spec=Asset)
        mock_asset.external_id = "EXT-123"

        mock_schedule = Mock(spec=Schedule)
        mock_schedule.commission_attempts = 3  # Max attempts

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_schedule

        with patch('src.services.asset_service.EmailService.send_commission_failure_alert') as mock_email:
            result = AssetService.commission_asset(
                asset=mock_asset,
                actor="test-actor",
                db=mock_db
            )

            assert result is False
            mock_email.assert_called_once()

    def test_commission_asset_failure_with_retry(self):
        """Test commissioning failure that will retry"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_api_client = Mock(spec=ApiClient)
        mock_project = Mock(spec=Project)
        mock_project.api_clients = [mock_api_client]

        mock_asset = Mock(spec=Asset)
        mock_asset.external_id = "EXT-123"
        mock_asset.project = mock_project
        mock_asset.asset_id = "asset-123"

        mock_schedule = Mock(spec=Schedule)
        mock_schedule.schedule_id = "sched-123"
        mock_schedule.commission_attempts = 1  # First retry
        mock_schedule.last_commission_attempt = datetime.now(timezone.utc) - timedelta(seconds=60)

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_schedule

        with patch('src.services.asset_service.CredentialService.get_exedra_config') as mock_creds, \
             patch('src.services.asset_service.ExedraService.commission_device') as mock_commission:

            mock_creds.return_value = {
                "token": "test-token",
                "base_url": "https://api.exedra.com"
            }
            mock_commission.side_effect = RuntimeError("Commission failed")

            result = AssetService.commission_asset(
                asset=mock_asset,
                actor="test-actor",
                db=mock_db
            )

            assert result is False
            assert mock_schedule.commission_error == "Commission failed"
            assert mock_schedule.commission_attempts == 2
            mock_db.commit.assert_called()

    def test_commission_asset_simulation_mode(self):
        """Simulation mode commissioning short-circuits without EXEDRA."""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_project = Mock(spec=Project)
        mock_project.mode = "simulation"

        mock_asset = Mock(spec=Asset)
        mock_asset.external_id = "EXT-123"
        mock_asset.project = mock_project
        mock_asset.asset_id = "asset-123"

        mock_schedule = Mock(spec=Schedule)
        mock_schedule.schedule_id = "sched-123"
        mock_schedule.status = "pending_commission"

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_schedule

        with patch('src.services.asset_service.ExedraService.commission_device') as mock_commission:
            result = AssetService.commission_asset(
                asset=mock_asset,
                actor="tester",
                db=mock_db
            )

        assert result is True
        assert mock_schedule.status == "active"
        assert mock_schedule.is_simulated is True
        mock_commission.assert_not_called()


class TestValidateGuardrails:
    """Tests for guardrail validation"""

    def test_validate_basic_guardrails_valid(self):
        """Test basic guardrails with valid dim percent"""
        mock_asset = Mock(spec=Asset)

        is_valid, error = AssetService.validate_basic_guardrails(mock_asset, 50)

        assert is_valid is True
        assert error is None

    def test_validate_basic_guardrails_too_low(self):
        """Test basic guardrails with dim percent < 0"""
        mock_asset = Mock(spec=Asset)

        is_valid, error = AssetService.validate_basic_guardrails(mock_asset, -5)

        assert is_valid is False
        assert "between 0 and 100" in error

    def test_validate_basic_guardrails_too_high(self):
        """Test basic guardrails with dim percent > 100"""
        mock_asset = Mock(spec=Asset)

        is_valid, error = AssetService.validate_basic_guardrails(mock_asset, 150)

        assert is_valid is False
        assert "between 0 and 100" in error

    def test_validate_policy_guardrails_passthrough_mode(self):
        """Test policy guardrails in passthrough mode (always valid)"""
        mock_db = Mock(spec=Session)

        mock_asset = Mock(spec=Asset)
        mock_asset.control_mode = "passthrough"

        is_valid, error = AssetService.validate_policy_guardrails(mock_asset, 50, mock_db)

        assert is_valid is True
        assert error is None

    def test_validate_policy_guardrails_optimise_mode_valid(self):
        """Test policy guardrails in optimise mode with valid dim"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_asset = Mock(spec=Asset)
        mock_asset.control_mode = "optimise"
        mock_asset.project_id = "proj-123"

        mock_policy = Mock(spec=Policy)
        mock_policy.body = {
            "min_dim": 20,
            "max_dim": 80
        }

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_policy

        is_valid, error = AssetService.validate_policy_guardrails(mock_asset, 50, mock_db)

        assert is_valid is True
        assert error is None

    def test_validate_policy_guardrails_below_minimum(self):
        """Test policy guardrails with dim below minimum"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_asset = Mock(spec=Asset)
        mock_asset.control_mode = "optimise"
        mock_asset.project_id = "proj-123"

        mock_policy = Mock(spec=Policy)
        mock_policy.body = {
            "min_dim": 20,
            "max_dim": 80
        }

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_policy

        is_valid, error = AssetService.validate_policy_guardrails(mock_asset, 10, mock_db)

        assert is_valid is False
        assert "below policy minimum" in error

    def test_validate_policy_guardrails_above_maximum(self):
        """Test policy guardrails with dim above maximum"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_asset = Mock(spec=Asset)
        mock_asset.control_mode = "optimise"
        mock_asset.project_id = "proj-123"

        mock_policy = Mock(spec=Policy)
        mock_policy.body = {
            "min_dim": 20,
            "max_dim": 80
        }

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_policy

        is_valid, error = AssetService.validate_policy_guardrails(mock_asset, 90, mock_db)

        assert is_valid is False
        assert "above policy maximum" in error


class TestCreateRealtimeCommand:
    """Tests for creating realtime commands"""

    def test_create_realtime_command_success(self):
        """Test successful realtime command creation"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_api_client = Mock(spec=ApiClient)
        mock_api_client.name = "test-client"

        mock_project = Mock(spec=Project)
        mock_project.api_clients = [mock_api_client]

        mock_asset = Mock(spec=Asset)
        mock_asset.external_id = "EXT-123"
        mock_asset.project = mock_project
        mock_asset.asset_id = "asset-123"
        mock_asset.project_id = "proj-123"
        mock_asset.control_mode = "optimise"

        request = RealtimeCommandRequest(dim_percent=75, note="Test command")

        # Setup query to return None for idempotency check (no existing command)
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        created_command = None
        def capture_add(obj):
            nonlocal created_command
            if isinstance(obj, RealtimeCommand):
                obj.realtime_command_id = "cmd-123"
                created_command = obj

        mock_db.add.side_effect = capture_add
        mock_db.flush.return_value = None

        with patch('src.services.asset_service.CredentialService.get_exedra_config') as mock_creds, \
             patch('src.services.asset_service.ExedraService.send_device_command') as mock_send:

            mock_creds.return_value = {
                "token": "test-token",
                "base_url": "https://api.exedra.com"
            }
            mock_send.return_value = {"status": "sent"}

            result = AssetService.create_realtime_command(
                request=request,
                asset=mock_asset,
                api_client_id="client-123",
                api_client_name="test-client",
                idempotency_key="idem-123",
                db=mock_db
            )

            assert result == "cmd-123"
            assert created_command.status == "sent"
            assert mock_db.commit.call_count >= 1

    def test_create_realtime_command_idempotency(self):
        """Test realtime command idempotency"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_asset = Mock(spec=Asset)

        existing_command = Mock(spec=RealtimeCommand)
        existing_command.realtime_command_id = "existing-cmd-123"

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_command

        request = RealtimeCommandRequest(dim_percent=75)

        result = AssetService.create_realtime_command(
            request=request,
            asset=mock_asset,
            api_client_id="client-123",
            api_client_name="test-client",
            idempotency_key="idem-123",
            db=mock_db
        )

        assert result == "existing-cmd-123"

    def test_create_realtime_command_failure(self):
        """Test realtime command failure handling"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_asset = Mock(spec=Asset)
        mock_asset.external_id = "EXT-123"
        mock_asset.asset_id = "asset-123"
        mock_asset.project_id = "proj-123"
        mock_asset.control_mode = "optimise"

        mock_project = Mock(spec=Project)
        mock_project.api_clients = []
        mock_asset.project = mock_project

        # No existing command
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        request = RealtimeCommandRequest(dim_percent=75)

        created_command = None
        def capture_add(obj):
            nonlocal created_command
            if isinstance(obj, RealtimeCommand):
                obj.realtime_command_id = "cmd-123"
                created_command = obj

        mock_db.add.side_effect = capture_add
        mock_db.flush.return_value = None

        result = AssetService.create_realtime_command(
            request=request,
            asset=mock_asset,
            api_client_id="client-123",
            api_client_name="test-client",
            idempotency_key=None,
            db=mock_db
        )

        assert result == "cmd-123"
        assert created_command.status == "failed"
        assert "error" in created_command.response

    def test_create_realtime_command_simulation_mode(self):
        """Realtime commands should be marked simulated when project is in simulation mode."""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_project = Mock(spec=Project)
        mock_project.api_clients = []
        mock_project.mode = "simulation"

        mock_asset = Mock(spec=Asset)
        mock_asset.external_id = "EXT-123"
        mock_asset.asset_id = "asset-123"
        mock_asset.project_id = "proj-123"
        mock_asset.control_mode = "optimise"
        mock_asset.project = mock_project

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        created_command = None

        def capture_add(obj):
            nonlocal created_command
            if isinstance(obj, RealtimeCommand):
                obj.realtime_command_id = "sim-cmd-123"
                created_command = obj

        mock_db.add.side_effect = capture_add
        mock_db.flush.return_value = None

        with patch('src.services.asset_service.ExedraService.send_device_command') as mock_send:
            result = AssetService.create_realtime_command(
                request=RealtimeCommandRequest(dim_percent=80, note="demo"),
                asset=mock_asset,
                api_client_id="client-123",
                api_client_name="test-client",
                idempotency_key=None,
                db=mock_db
            )

        assert result == "sim-cmd-123"
        assert created_command.status == "simulated"
        assert created_command.is_simulated is True
        mock_send.assert_not_called()


class TestCreateAsset:
    """Tests for asset creation"""

    def test_create_asset_success(self):
        """Test successful asset creation"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        # No existing asset
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        added_objects = []
        def capture_add(obj):
            if isinstance(obj, Asset):
                obj.asset_id = "new-asset-123"
            elif isinstance(obj, Schedule):
                obj.schedule_id = "new-sched-123"
            added_objects.append(obj)

        mock_db.add.side_effect = capture_add
        mock_db.flush.return_value = None

        result = AssetService.create_asset(
            project_id="proj-123",
            external_id="EXT-123",
            control_mode="optimise",
            exedra_name="Test Asset",
            exedra_control_program_id="prog-123",
            exedra_calendar_id="cal-123",
            actor="test-actor",
            db=mock_db,
            road_class="A",
            metadata={"custom": "value"}
        )

        assert isinstance(result, Asset)
        assert result.asset_id == "new-asset-123"
        assert result.external_id == "EXT-123"
        assert result.control_mode == "optimise"

        # Verify schedule was created
        schedule_created = any(isinstance(obj, Schedule) for obj in added_objects)
        assert schedule_created

        # Verify audit log
        audit_created = any(isinstance(obj, AuditLog) for obj in added_objects)
        assert audit_created

        mock_db.commit.assert_called_once()

    def test_create_asset_already_exists(self):
        """Test asset creation when asset already exists"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        existing_asset = Mock(spec=Asset)

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_asset

        with pytest.raises(ValueError, match="already exists"):
            AssetService.create_asset(
                project_id="proj-123",
                external_id="EXT-123",
                control_mode="optimise",
                exedra_name="Test Asset",
                exedra_control_program_id="prog-123",
                exedra_calendar_id="cal-123",
                actor="test-actor",
                db=mock_db
            )


class TestUpdateAsset:
    """Tests for asset updates"""

    def test_update_asset_success(self):
        """Test successful asset update"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_asset = Mock(spec=Asset)
        mock_asset.asset_id = "asset-123"
        mock_asset.external_id = "EXT-123"
        mock_asset.name = "Old Name"
        mock_asset.asset_metadata = {}

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_asset

        result = AssetService.update_asset(
            external_id="EXT-123",
            project_id="proj-123",
            exedra_name="New Name",
            exedra_control_program_id="prog-456",
            road_class="B",
            actor="test-actor",
            db=mock_db
        )

        assert result == mock_asset
        assert mock_asset.name == "New Name"
        assert mock_db.commit.call_count >= 1

    def test_update_asset_not_found(self):
        """Test asset update when asset doesn't exist"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            AssetService.update_asset(
                external_id="EXT-999",
                project_id="proj-123",
                exedra_name="New Name",
                db=mock_db
            )

    def test_update_asset_no_updates(self):
        """Test asset update with no fields provided"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_asset = Mock(spec=Asset)

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_asset

        with pytest.raises(ValueError, match="At least one field must be provided"):
            AssetService.update_asset(
                external_id="EXT-123",
                project_id="proj-123",
                db=mock_db
            )


class TestDeleteAsset:
    """Tests for asset deletion"""

    def test_delete_asset_success(self):
        """Test successful asset deletion"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_asset = Mock(spec=Asset)
        mock_asset.asset_id = "asset-123"
        mock_asset.external_id = "EXT-123"
        mock_asset.name = "Test Asset"
        mock_asset.control_mode = "optimise"

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_asset

        result = AssetService.delete_asset(
            external_id="EXT-123",
            project_id="proj-123",
            actor="test-actor",
            db=mock_db
        )

        assert result is True
        mock_db.delete.assert_called_once_with(mock_asset)
        mock_db.commit.assert_called()

    def test_delete_asset_not_found(self):
        """Test asset deletion when asset doesn't exist"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            AssetService.delete_asset(
                external_id="EXT-999",
                project_id="proj-123",
                actor="test-actor",
                db=mock_db
            )
