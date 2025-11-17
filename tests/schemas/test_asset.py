"""Tests for asset schema validation."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.schemas.asset import (
    AssetStateResponse,
    AssetResponse,
    AssetControlModeRequest,
    AssetControlModeResponse,
    AssetCreateRequest,
    AssetCreateResponse,
    AssetUpdateRequest,
)


class TestAssetStateResponse:
    """Test asset state response schema."""

    def test_asset_state_with_all_fields(self):
        """Test asset state with all fields populated."""
        now = datetime.now(timezone.utc)
        state = AssetStateResponse(
            exedra_id="device-123",
            current_dim_percent=75,
            current_schedule_id="schedule-456",
            updated_at=now
        )
        assert state.exedra_id == "device-123"
        assert state.current_dim_percent == 75
        assert state.current_schedule_id == "schedule-456"

    def test_asset_state_with_none_optionals(self):
        """Test asset state with None optional fields."""
        now = datetime.now(timezone.utc)
        state = AssetStateResponse(
            exedra_id="device-123",
            updated_at=now
        )
        assert state.current_dim_percent is None
        assert state.current_schedule_id is None

    def test_asset_state_dim_percent_validation_low(self):
        """Test dim percent validation - below minimum."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError) as exc_info:
            AssetStateResponse(
                exedra_id="device-123",
                current_dim_percent=-1,
                updated_at=now
            )
        assert "greater than or equal to 0" in str(exc_info.value)

    def test_asset_state_dim_percent_validation_high(self):
        """Test dim percent validation - above maximum."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError) as exc_info:
            AssetStateResponse(
                exedra_id="device-123",
                current_dim_percent=101,
                updated_at=now
            )
        assert "less than or equal to 100" in str(exc_info.value)

    def test_asset_state_dim_percent_boundary_values(self):
        """Test dim percent at boundary values 0 and 100."""
        now = datetime.now(timezone.utc)
        state_min = AssetStateResponse(
            exedra_id="device-123",
            current_dim_percent=0,
            updated_at=now
        )
        state_max = AssetStateResponse(
            exedra_id="device-123",
            current_dim_percent=100,
            updated_at=now
        )
        assert state_min.current_dim_percent == 0
        assert state_max.current_dim_percent == 100


class TestAssetResponse:
    """Test asset response schema."""

    def test_asset_response_complete(self):
        """Test asset response with all fields."""
        asset = AssetResponse(
            exedra_id="device-123",
            name="Street Light A1",
            control_mode="optimise",
            road_class="A-road",
            metadata={"location": "Main St", "install_date": "2024-01-01"}
        )
        assert asset.exedra_id == "device-123"
        assert asset.control_mode == "optimise"
        assert asset.metadata["location"] == "Main St"

    def test_asset_response_minimal(self):
        """Test asset response with only required fields."""
        asset = AssetResponse(
            exedra_id="device-123",
            control_mode="passthrough",
            metadata={}
        )
        assert asset.name is None
        assert asset.road_class is None
        assert asset.metadata == {}


class TestAssetControlModeRequest:
    """Test asset control mode request schema."""

    def test_control_mode_optimise(self):
        """Test valid control mode - optimise."""
        request = AssetControlModeRequest(control_mode="optimise")
        assert request.control_mode == "optimise"

    def test_control_mode_passthrough(self):
        """Test valid control mode - passthrough."""
        request = AssetControlModeRequest(control_mode="passthrough")
        assert request.control_mode == "passthrough"

    def test_control_mode_invalid(self):
        """Test invalid control mode."""
        with pytest.raises(ValidationError) as exc_info:
            AssetControlModeRequest(control_mode="invalid")
        assert "String should match pattern" in str(exc_info.value)


class TestAssetControlModeResponse:
    """Test asset control mode response schema."""

    def test_control_mode_response(self):
        """Test control mode response."""
        now = datetime.now(timezone.utc)
        response = AssetControlModeResponse(
            exedra_id="device-123",
            control_mode="optimise",
            changed_at=now,
            changed_by="admin@example.com"
        )
        assert response.exedra_id == "device-123"
        assert response.control_mode == "optimise"
        assert response.changed_by == "admin@example.com"


class TestAssetCreateRequest:
    """Test asset creation request schema."""

    def test_asset_create_with_all_fields(self):
        """Test asset creation with all fields."""
        request = AssetCreateRequest(
            exedra_id="device-123",
            exedra_name="Street Light A1",
            exedra_control_program_id="prog-456",
            exedra_calendar_id="cal-789",
            control_mode="optimise",
            road_class="A-road",
            metadata={"location": "Main St"}
        )
        assert request.exedra_id == "device-123"
        assert request.exedra_name == "Street Light A1"
        assert request.control_mode == "optimise"
        assert request.road_class == "A-road"

    def test_asset_create_minimal(self):
        """Test asset creation with minimal required fields."""
        request = AssetCreateRequest(
            exedra_id="device-123",
            exedra_name="Light 1",
            exedra_control_program_id="prog-456",
            exedra_calendar_id="cal-789",
            control_mode="passthrough"
        )
        assert request.road_class is None
        assert request.metadata is None

    def test_asset_create_invalid_control_mode(self):
        """Test asset creation with invalid control mode."""
        with pytest.raises(ValidationError) as exc_info:
            AssetCreateRequest(
                exedra_id="device-123",
                exedra_name="Light 1",
                exedra_control_program_id="prog-456",
                exedra_calendar_id="cal-789",
                control_mode="automatic"
            )
        assert "String should match pattern" in str(exc_info.value)

    def test_asset_create_missing_required_fields(self):
        """Test asset creation with missing required fields."""
        with pytest.raises(ValidationError) as exc_info:
            AssetCreateRequest(
                exedra_id="device-123",
                exedra_name="Light 1",
                control_mode="optimise"
            )
        assert "exedra_control_program_id" in str(exc_info.value)
        assert "exedra_calendar_id" in str(exc_info.value)


class TestAssetCreateResponse:
    """Test asset creation response schema."""

    def test_asset_create_response_complete(self):
        """Test asset creation response with all fields."""
        now = datetime.now(timezone.utc)
        response = AssetCreateResponse(
            asset_id="asset-123",
            exedra_id="device-123",
            control_mode="optimise",
            exedra_name="Street Light A1",
            exedra_control_program_id="prog-456",
            exedra_calendar_id="cal-789",
            road_class="A-road",
            metadata={"location": "Main St"},
            created_at=now
        )
        assert response.asset_id == "asset-123"
        assert response.exedra_id == "device-123"
        assert response.road_class == "A-road"


class TestAssetUpdateRequest:
    """Test asset update request schema."""

    def test_asset_update_all_fields(self):
        """Test asset update with all fields."""
        request = AssetUpdateRequest(
            exedra_name="Updated Name",
            exedra_control_program_id="new-prog-456",
            exedra_calendar_id="new-cal-789",
            road_class="B-road",
            metadata={"updated": True}
        )
        assert request.exedra_name == "Updated Name"
        assert request.road_class == "B-road"

    def test_asset_update_partial(self):
        """Test asset update with only some fields."""
        request = AssetUpdateRequest(
            exedra_name="Updated Name",
            road_class="B-road"
        )
        assert request.exedra_name == "Updated Name"
        assert request.exedra_control_program_id is None
        assert request.exedra_calendar_id is None

    def test_asset_update_empty(self):
        """Test asset update with no fields (all None)."""
        request = AssetUpdateRequest()
        assert request.exedra_name is None
        assert request.road_class is None
        assert request.metadata is None
