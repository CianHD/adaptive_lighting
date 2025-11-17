"""Tests for Asset API endpoints."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from src.api.asset import (
    commission_asset,
    create_asset,
    delete_asset,
    get_asset,
    get_asset_schedule,
    get_asset_state,
    process_pending_commissions,
    realtime_command,
    update_asset,
    update_asset_control_mode,
    update_asset_schedule,
)
from src.schemas.asset import (
    AssetControlModeRequest,
    AssetCreateRequest,
    AssetResponse,
    AssetStateResponse,
    AssetUpdateRequest,
)
from src.schemas.command import RealtimeCommandRequest, ScheduleRequest, ScheduleStep


@pytest.fixture
def mock_authenticated_client():
    """Mock authenticated client with project and API client."""
    client = Mock()
    client.project.project_id = "proj-123"
    client.project.code = "TEST"
    client.api_client.api_client_id = "client-123"
    client.api_client.name = "test-client"
    client.scopes = ["asset:read", "asset:create", "asset:update", "asset:delete", "asset:command", "asset:metadata", "command:override"]
    client.has_scope = lambda scope: scope in client.scopes
    return client


@pytest.fixture
def mock_db():
    """Mock database session."""
    return Mock()


@pytest.fixture
def mock_asset():
    """Mock asset object."""
    asset = Mock()
    asset.asset_id = "asset-123"
    asset.external_id = "exedra-device-1"
    asset.name = "Test Device"
    asset.control_mode = "optimise"
    asset.road_class = "A-road"
    asset.asset_metadata = {
        "exedra_control_program_id": "prog-1",
        "exedra_calendar_id": "cal-1",
        "road_class": "A-road"
    }
    asset.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    asset.updated_at = datetime(2024, 1, 2, tzinfo=timezone.utc)
    return asset


@patch('src.api.asset.AssetService.get_asset_by_external_id')
@patch('src.api.asset.AssetService.get_asset_details')
async def test_get_asset_success(
    mock_get_details,
    mock_get_by_id,
    mock_authenticated_client,
    mock_db,
    mock_asset,
):
    """Test successful asset retrieval."""
    mock_get_by_id.return_value = mock_asset
    mock_get_details.return_value = AssetResponse(
        exedra_id="exedra-device-1",
        name="Test Device",
        control_mode="optimise",
        road_class="A-road",
        metadata={"exedra_control_program_id": "prog-1", "exedra_calendar_id": "cal-1"}
    )

    result = await get_asset(
        exedra_id="exedra-device-1",
        client=mock_authenticated_client,
        db=mock_db
    )

    assert result.exedra_id == "exedra-device-1"
    assert result.control_mode == "optimise"
    mock_get_by_id.assert_called_once_with(
        external_id="exedra-device-1",
        project_id="proj-123",
        db=mock_db
    )


@patch('src.api.asset.AssetService.get_asset_by_external_id')
async def test_get_asset_not_found(mock_get_by_id, mock_authenticated_client, mock_db):
    """Test asset not found."""
    mock_get_by_id.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await get_asset(
            exedra_id="nonexistent",
            client=mock_authenticated_client,
            db=mock_db
        )

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


class TestCreateAsset:
    """Tests for POST /asset/"""

    @patch('src.api.asset.AssetService.create_asset')
    async def test_create_asset_success(self, mock_create,
                                        mock_authenticated_client, mock_db, mock_asset):
        """Test successful asset creation."""
        mock_create.return_value = mock_asset

        request = AssetCreateRequest(
            exedra_id="exedra-device-1",
            control_mode="optimise",
            exedra_name="Test Device",
            exedra_control_program_id="prog-1",
            exedra_calendar_id="cal-1",
            road_class="A-road"
        )

        result = await create_asset(
            request=request,
            client=mock_authenticated_client,
            db=mock_db
        )

        assert result.asset_id == "asset-123"
        assert result.exedra_id == "exedra-device-1"
        assert result.control_mode == "optimise"
        mock_create.assert_called_once()

    @patch('src.api.asset.AssetService.create_asset')
    async def test_create_asset_value_error(self, mock_create,
                                            mock_authenticated_client, mock_db):
        """Test asset creation with validation error."""
        mock_create.side_effect = ValueError("Invalid external_id format")

        request = AssetCreateRequest(
            exedra_id="invalid",
            control_mode="optimise",
            exedra_name="Test",
            exedra_control_program_id="prog-1",
            exedra_calendar_id="cal-1"
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_asset(request=request, client=mock_authenticated_client, db=mock_db)

        assert exc_info.value.status_code == 400

    @patch('src.api.asset.AssetService.create_asset')
    async def test_create_asset_runtime_error(self, mock_create,
                                              mock_authenticated_client, mock_db):
        """Test asset creation with runtime error."""
        mock_create.side_effect = RuntimeError("Database error")

        request = AssetCreateRequest(
            exedra_id="exedra-1",
            control_mode="optimise",
            exedra_name="Test",
            exedra_control_program_id="prog-1",
            exedra_calendar_id="cal-1"
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_asset(request=request, client=mock_authenticated_client, db=mock_db)

        assert exc_info.value.status_code == 500


class TestUpdateAsset:
    """Tests for PUT /asset/{exedra_id}"""

    @patch('src.api.asset.AssetService.update_asset')
    async def test_update_asset_success(self, mock_update,
                                        mock_authenticated_client, mock_db, mock_asset):
        """Test successful asset update."""
        mock_update.return_value = mock_asset

        request = AssetUpdateRequest(
            exedra_name="Updated Device",
            exedra_control_program_id="prog-2",
            exedra_calendar_id="cal-2",
            road_class="B-road"
        )

        result = await update_asset(
            exedra_id="exedra-device-1",
            request=request,
            client=mock_authenticated_client,
            db=mock_db
        )

        assert result.asset_id == "asset-123"
        assert result.exedra_id == "exedra-device-1"
        mock_update.assert_called_once()

    @patch('src.api.asset.AssetService.update_asset')
    async def test_update_asset_not_found(self, mock_update,
                                          mock_authenticated_client, mock_db):
        """Test updating non-existent asset."""
        mock_update.side_effect = ValueError("Asset not found")
        request = AssetUpdateRequest(exedra_name="Updated")

        with pytest.raises(HTTPException) as exc_info:
            await update_asset(
                exedra_id="nonexistent",
                request=request,
                client=mock_authenticated_client,
                db=mock_db
            )

        assert exc_info.value.status_code == 400


class TestDeleteAsset:
    """Tests for DELETE /asset/{exedra_id}"""

    @patch('src.api.asset.AssetService.delete_asset')
    async def test_delete_asset_success(self, mock_delete,
                                        mock_authenticated_client, mock_db):
        """Test successful asset deletion."""
        mock_delete.return_value = None
        result = await delete_asset(
            exedra_id="exedra-device-1",
            client=mock_authenticated_client,
            db=mock_db
        )

        assert "deleted successfully" in result["message"]
        mock_delete.assert_called_once_with(
            external_id="exedra-device-1",
            project_id="proj-123",
            actor="test-client",
            db=mock_db
        )

    @patch('src.api.asset.AssetService.delete_asset')
    async def test_delete_asset_not_found(self, mock_delete,
                                          mock_authenticated_client, mock_db):
        """Test deleting non-existent asset."""
        mock_delete.side_effect = ValueError("Asset not found")
        with pytest.raises(HTTPException) as exc_info:
            await delete_asset(
                exedra_id="nonexistent",
                client=mock_authenticated_client,
                db=mock_db
            )

        assert exc_info.value.status_code == 404


class TestGetAssetSchedule:
    """Tests for GET /asset/schedule/{exedra_id}"""

    @patch('src.api.asset.AssetService.get_asset_by_external_id')
    @patch('src.api.asset.AssetService.get_asset_exedra_schedule')
    async def test_get_schedule_success(self, mock_get_schedule, mock_get_by_id,
                                        mock_authenticated_client, mock_db, mock_asset):
        """Test successful schedule retrieval."""
        mock_get_by_id.return_value = mock_asset
        mock_get_schedule.return_value = {
            "schedule_id": "sched-123",
            "steps": [
                {"time": "08:00", "dim": 50},
                {"time": "18:00", "dim": 100}
            ],
            "provider": "exedra",
            "status": "active",
            "updated_at": datetime.now(timezone.utc)
        }

        result = await get_asset_schedule(
            exedra_id="exedra-device-1",
            client=mock_authenticated_client,
            db=mock_db
        )

        assert result.schedule_id == "sched-123"
        assert len(result.steps) == 2
        assert result.provider == "exedra"

    @patch('src.api.asset.AssetService.get_asset_by_external_id')
    async def test_get_schedule_asset_not_found(self, mock_get_by_id,
                                                mock_authenticated_client, mock_db):
        """Test schedule retrieval for non-existent asset."""
        mock_get_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_asset_schedule(
                exedra_id="nonexistent",
                client=mock_authenticated_client,
                db=mock_db
            )

        assert exc_info.value.status_code == 404


class TestUpdateAssetSchedule:
    """Tests for PUT /asset/schedule/{exedra_id}"""

    @patch('src.api.asset.AssetService.get_asset_by_external_id')
    @patch('src.api.asset.AssetService.update_asset_schedule_in_exedra')
    async def test_update_schedule_success(self, mock_update_schedule, mock_get_by_id,
                                           mock_authenticated_client, mock_db, mock_asset):
        """Test successful schedule update."""
        mock_get_by_id.return_value = mock_asset
        mock_update_schedule.return_value = "sched-123"

        request = ScheduleRequest(
            steps=[
                ScheduleStep(time="08:00", dim=50),
                ScheduleStep(time="18:00", dim=100)
            ]
        )

        result = await update_asset_schedule(
            exedra_id="exedra-device-1",
            request=request,
            idempotency_key="key-123",
            client=mock_authenticated_client,
            db=mock_db
        )

        assert result.schedule_id == "sched-123"
        assert len(result.steps) == 2
        assert result.provider == "exedra"

    @patch('src.api.asset.AssetService.get_asset_by_external_id')
    @patch('src.api.asset.AssetService.update_asset_schedule_in_exedra')
    async def test_update_schedule_value_error(self, mock_update_schedule, mock_get_by_id,
                                               mock_authenticated_client, mock_db, mock_asset):
        """Test schedule update with validation error."""
        mock_get_by_id.return_value = mock_asset
        mock_update_schedule.side_effect = ValueError("Invalid schedule format")

        request = ScheduleRequest(steps=[ScheduleStep(time="invalid", dim=50)])

        with pytest.raises(HTTPException) as exc_info:
            await update_asset_schedule(
                exedra_id="exedra-device-1",
                request=request,
                client=mock_authenticated_client,
                db=mock_db
            )

        assert exc_info.value.status_code == 400


class TestGetAssetState:
    """Tests for GET /asset/state/{exedra_id}"""

    @patch('src.api.asset.AssetService.get_asset_by_external_id')
    @patch('src.api.asset.AssetService.get_asset_state')
    async def test_get_state_success(self, mock_get_state, mock_get_by_id,
                                     mock_authenticated_client, mock_db, mock_asset):
        """Test successful asset state retrieval."""
        mock_get_by_id.return_value = mock_asset
        mock_get_state.return_value = AssetStateResponse(
            exedra_id="exedra-device-1",
            current_dim_percent=75,
            current_schedule_id="sched-123",
            updated_at=datetime.now(timezone.utc)
        )

        result = await get_asset_state(
            exedra_id="exedra-device-1",
            client=mock_authenticated_client,
            db=mock_db
        )

        assert result.exedra_id == "exedra-device-1"
        assert result.current_dim_percent == 75

    @patch('src.api.asset.AssetService.get_asset_by_external_id')
    async def test_get_state_asset_not_found(self, mock_get_by_id,
                                             mock_authenticated_client, mock_db):
        """Test state retrieval for non-existent asset."""
        mock_get_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_asset_state(
                exedra_id="nonexistent",
                client=mock_authenticated_client,
                db=mock_db
            )

        assert exc_info.value.status_code == 404


class TestRealtimeCommand:
    """Tests for POST /asset/realtime/{exedra_id}"""

    @patch('src.api.asset.AssetService.get_asset_by_external_id')
    @patch('src.api.asset.AssetService.validate_basic_guardrails')
    @patch('src.api.asset.AssetService.validate_policy_guardrails')
    @patch('src.api.asset.AssetService.create_realtime_command')
    async def test_realtime_command_optimise_mode(self, mock_create_cmd, mock_validate_policy,
                                                   mock_validate_basic, mock_get_by_id,
                                                   mock_authenticated_client, mock_db, mock_asset):
        """Test realtime command in optimise mode."""
        mock_asset.control_mode = "optimise"
        mock_get_by_id.return_value = mock_asset
        mock_validate_basic.return_value = (True, None)
        mock_validate_policy.return_value = (True, None)
        mock_create_cmd.return_value = "cmd-123"

        request = RealtimeCommandRequest(dim_percent=75)

        result = await realtime_command(
            exedra_id="exedra-device-1",
            request=request,
            idempotency_key="key-123",
            client=mock_authenticated_client,
            db=mock_db
        )

        assert result.command_id == "cmd-123"
        assert result.status == "accepted_with_policy"
        mock_validate_policy.assert_called_once()

    @patch('src.api.asset.AssetService.get_asset_by_external_id')
    @patch('src.api.asset.AssetService.validate_basic_guardrails')
    @patch('src.api.asset.AssetService.create_realtime_command')
    async def test_realtime_command_passthrough_mode(self, mock_create_cmd, mock_validate_basic,
                                                     mock_get_by_id, mock_authenticated_client,
                                                     mock_db, mock_asset):
        """Test realtime command in passthrough mode."""
        mock_asset.control_mode = "passthrough"
        mock_get_by_id.return_value = mock_asset
        mock_validate_basic.return_value = (True, None)
        mock_create_cmd.return_value = "cmd-123"

        request = RealtimeCommandRequest(dim_percent=75)

        result = await realtime_command(
            exedra_id="exedra-device-1",
            request=request,
            client=mock_authenticated_client,
            db=mock_db
        )

        assert result.command_id == "cmd-123"
        assert result.status == "accepted"

    @patch('src.api.asset.AssetService.get_asset_by_external_id')
    @patch('src.api.asset.AssetService.validate_basic_guardrails')
    async def test_realtime_command_guardrail_failure(self, mock_validate_basic, mock_get_by_id,
                                                      mock_authenticated_client, mock_db, mock_asset):
        """Test realtime command failing basic guardrails."""
        mock_get_by_id.return_value = mock_asset
        mock_validate_basic.return_value = (False, "Dim level out of range")

        request = RealtimeCommandRequest(dim_percent=100)  # Valid value, but will be rejected by mock guardrails

        with pytest.raises(HTTPException) as exc_info:
            await realtime_command(
                exedra_id="exedra-device-1",
                request=request,
                client=mock_authenticated_client,
                db=mock_db
            )

        assert exc_info.value.status_code == 400

    @patch('src.api.asset.AssetService.get_asset_by_external_id')
    @patch('src.api.asset.AssetService.validate_basic_guardrails')
    async def test_realtime_command_missing_override_scope(self, mock_validate_basic, mock_get_by_id,
                                                           mock_authenticated_client, mock_db, mock_asset):
        """Test realtime command in optimise mode without override scope."""
        mock_asset.control_mode = "optimise"
        mock_get_by_id.return_value = mock_asset
        mock_validate_basic.return_value = (True, None)
        mock_authenticated_client.scopes = ["asset:command"]  # Remove command:override
        mock_authenticated_client.has_scope = lambda scope: scope in mock_authenticated_client.scopes

        request = RealtimeCommandRequest(dim_percent=75)

        with pytest.raises(HTTPException) as exc_info:
            await realtime_command(
                exedra_id="exedra-device-1",
                request=request,
                client=mock_authenticated_client,
                db=mock_db
            )

        assert exc_info.value.status_code == 403


class TestUpdateAssetControlMode:
    """Tests for PUT /asset/mode/{exedra_id}"""

    @patch('src.api.asset.AssetService.get_asset_by_external_id')
    @patch('src.api.asset.AssetService.update_control_mode')
    async def test_update_control_mode_success(self, mock_update_mode, mock_get_by_id,
                                               mock_authenticated_client, mock_db, mock_asset):
        """Test successful control mode update."""
        mock_get_by_id.return_value = mock_asset
        mock_asset.control_mode = "passthrough"
        mock_update_mode.return_value = mock_asset

        request = AssetControlModeRequest(control_mode="passthrough")

        result = await update_asset_control_mode(
            exedra_id="exedra-device-1",
            request=request,
            client=mock_authenticated_client,
            db=mock_db
        )

        assert result.control_mode == "passthrough"
        assert result.exedra_id == "exedra-device-1"
        mock_update_mode.assert_called_once()

    @patch('src.api.asset.AssetService.get_asset_by_external_id')
    async def test_update_control_mode_asset_not_found(self, mock_get_by_id,
                                                       mock_authenticated_client, mock_db):
        """Test control mode update for non-existent asset."""
        mock_get_by_id.return_value = None

        request = AssetControlModeRequest(control_mode="passthrough")

        with pytest.raises(HTTPException) as exc_info:
            await update_asset_control_mode(
                exedra_id="nonexistent",
                request=request,
                client=mock_authenticated_client,
                db=mock_db
            )

        assert exc_info.value.status_code == 404


class TestCommissionAsset:
    """Tests for POST /asset/commission/{exedra_id}"""

    @patch('src.api.asset.AssetService.get_asset_by_external_id')
    @patch('src.api.asset.AssetService.commission_asset')
    async def test_commission_asset_success(self, mock_commission, mock_get_by_id,
                                           mock_authenticated_client, mock_db, mock_asset):
        """Test successful asset commissioning."""
        mock_get_by_id.return_value = mock_asset
        mock_commission.return_value = True

        result = await commission_asset(
            exedra_id="exedra-device-1",
            client=mock_authenticated_client,
            db=mock_db
        )

        assert result["status"] == "success"
        assert "commissioned successfully" in result["message"]

    @patch('src.api.asset.AssetService.get_asset_by_external_id')
    @patch('src.api.asset.AssetService.commission_asset')
    async def test_commission_asset_failed(self, mock_commission, mock_get_by_id,
                                          mock_authenticated_client, mock_db, mock_asset):
        """Test failed asset commissioning."""
        mock_get_by_id.return_value = mock_asset
        mock_commission.return_value = False

        result = await commission_asset(
            exedra_id="exedra-device-1",
            client=mock_authenticated_client,
            db=mock_db
        )

        assert result["status"] == "failed"


class TestProcessPendingCommissions:
    """Tests for POST /asset/process-pending-commissions"""

    @patch('src.api.asset.AssetService.process_pending_commissions')
    async def test_process_pending_commissions_success(self, mock_process,
                                                       mock_authenticated_client, mock_db):
        """Test successful pending commissions processing."""
        mock_process.return_value = None

        result = await process_pending_commissions(
            _client=mock_authenticated_client,
            db=mock_db
        )

        assert result["status"] == "success"
        assert "processing started" in result["message"]
        mock_process.assert_called_once_with(db=mock_db, max_concurrent=10)
