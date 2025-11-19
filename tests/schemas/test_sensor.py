"""Tests for sensor and command schema validation."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.schemas.sensor import (
    SensorAssetLinkInfo,
    SensorCreateRequest,
    SensorCreateResponse,
    SensorIngestRequest,
    SensorIngestResponse,
    SensorResponse,
    SensorTypeCreateRequest,
    SensorTypeResponse,
    SensorUpdateRequest,
)
from src.schemas.command import (
    RealtimeCommandRequest,
    RealtimeCommandResponse,
    ScheduleStep,
    ScheduleRequest,
)


class TestSensorIngestRequest:
    """Test sensor data ingestion request schema."""

    def test_sensor_ingest_with_all_fields(self):
        """Test sensor ingest with all measurement types."""
        now = datetime.now(timezone.utc)
        request = SensorIngestRequest(
            sensor_external_id="sensor-123",
            observed_at=now,
            section="northbound",
            vehicle_count=25,
            pedestrian_count=10,
            avg_vehicle_speed_kmh=45.5
        )
        assert request.sensor_external_id == "sensor-123"
        assert request.vehicle_count == 25
        assert request.pedestrian_count == 10
        assert request.section == "northbound"

    def test_sensor_ingest_minimal(self):
        """Test sensor ingest with only required fields."""
        now = datetime.now(timezone.utc)
        request = SensorIngestRequest(
            sensor_external_id="sensor-123",
            observed_at=now
        )
        assert request.vehicle_count is None
        assert request.pedestrian_count is None
        assert request.avg_vehicle_speed_kmh is None
        assert request.section is None

    def test_sensor_ingest_negative_counts_rejected(self):
        """Test that negative counts are rejected."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError) as exc_info:
            SensorIngestRequest(
                sensor_external_id="sensor-123",
                observed_at=now,
                vehicle_count=-5
            )
        assert "greater than or equal to 0" in str(exc_info.value).lower()

    def test_sensor_ingest_negative_speed_rejected(self):
        """Test that negative speeds are rejected."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError) as exc_info:
            SensorIngestRequest(
                sensor_external_id="sensor-123",
                observed_at=now,
                avg_vehicle_speed_kmh=-10.5
            )
        assert "greater than or equal to 0" in str(exc_info.value).lower()

    def test_sensor_ingest_zero_values_accepted(self):
        """Test that zero values are accepted."""
        now = datetime.now(timezone.utc)
        request = SensorIngestRequest(
            sensor_external_id="sensor-123",
            observed_at=now,
            vehicle_count=0,
            avg_vehicle_speed_kmh=0.0
        )
        assert request.vehicle_count == 0
        assert request.avg_vehicle_speed_kmh == 0.0


class TestSensorIngestResponse:
    """Test sensor ingest response schema."""

    def test_sensor_ingest_response(self):
        """Test sensor ingest response."""
        now = datetime.now(timezone.utc)
        response = SensorIngestResponse(
            reading_ids={"vehicle_count": "read-123", "speed": "read-124"},
            dedup=False,
            timestamp=now
        )
        assert len(response.reading_ids) == 2
        assert response.dedup is False


class TestSensorResponse:
    """Test sensor response schema."""

    def test_sensor_response_complete(self):
        """Test sensor response with all fields."""
        sensor = SensorResponse(
            external_id="sensor-123",
            sensor_type="traffic_counter",
            linked_assets=[
                SensorAssetLinkInfo(asset_exedra_id="asset-1", section="north"),
                SensorAssetLinkInfo(asset_exedra_id="asset-2", section=None)
            ],
            vendor="ACME Corp",
            name="Main St Sensor",
            capabilities=["vehicle_count", "speed"],
            metadata={"location": "Main St", "install_date": "2024-01-01"}
        )
        assert sensor.external_id == "sensor-123"
        assert len(sensor.linked_assets) == 2
        assert sensor.linked_assets[0].section == "north"
        assert "vehicle_count" in sensor.capabilities


class TestSensorTypeResponse:
    """Test sensor type response schema."""

    def test_sensor_type_response(self):
        """Test sensor type response."""
        sensor_type = SensorTypeResponse(
            sensor_type_id="sens-type-001",
            manufacturer="ACME",
            model="TC-2000",
            capabilities=["vehicle_count", "speed", "classification"],
            firmware_ver="2.1.0"
        )
        assert sensor_type.manufacturer == "ACME"
        assert len(sensor_type.capabilities) == 3


class TestSensorCreateRequest:
    """Test sensor creation request schema."""

    def test_sensor_create_with_metadata(self):
        """Test sensor creation with metadata."""
        request = SensorCreateRequest(
            external_id="sensor-123",
            sensor_type_id="type-456",
            asset_links=[
                SensorAssetLinkInfo(asset_exedra_id="asset-1", section="east"),
                SensorAssetLinkInfo(asset_exedra_id="asset-2", section=None)
            ],
            metadata={"location": "Main St"}
        )
        assert request.external_id == "sensor-123"
        assert len(request.asset_links) == 2
        assert request.asset_links[0].section == "east"
        assert request.metadata["location"] == "Main St"

    def test_sensor_create_without_metadata(self):
        """Test sensor creation without metadata uses default."""
        request = SensorCreateRequest(
            external_id="sensor-123",
            sensor_type_id="type-456",
            asset_links=[SensorAssetLinkInfo(asset_exedra_id="asset-1", section=None)]
        )
        assert request.metadata == {}

    def test_sensor_create_missing_required_fields(self):
        """Test sensor creation with missing required fields."""
        with pytest.raises(ValidationError) as exc_info:
            SensorCreateRequest(external_id="sensor-123")
        assert "sensor_type_id" in str(exc_info.value)
        assert "asset_links" in str(exc_info.value)


class TestSensorCreateResponse:
    """Test sensor creation response schema."""

    def test_sensor_create_response(self):
        """Test sensor creation response."""
        now = datetime.now(timezone.utc)
        response = SensorCreateResponse(
            sensor_id="sen-123",
            external_id="sensor-123",
            sensor_type_id="type-456",
            linked_assets=[
                SensorAssetLinkInfo(asset_exedra_id="asset-1", section="west"),
                SensorAssetLinkInfo(asset_exedra_id="asset-2", section=None)
            ],
            metadata={"location": "Main St"},
            created_at=now
        )
        assert response.sensor_id == "sen-123"
        assert len(response.linked_assets) == 2


class TestSensorUpdateRequest:
    """Test sensor update request schema."""

    def test_sensor_update_all_fields(self):
        """Test sensor update with all fields."""
        request = SensorUpdateRequest(
            sensor_type_id="new-type-789",
            asset_links=[
                SensorAssetLinkInfo(asset_exedra_id="asset-3", section="north"),
                SensorAssetLinkInfo(asset_exedra_id="asset-4", section=None),
                SensorAssetLinkInfo(asset_exedra_id="asset-5", section="south")
            ],
            metadata={"updated": True}
        )
        assert request.sensor_type_id == "new-type-789"
        assert len(request.asset_links) == 3

    def test_sensor_update_partial(self):
        """Test sensor update with partial fields."""
        request = SensorUpdateRequest(metadata={"note": "Relocated"})
        assert request.sensor_type_id is None
        assert request.asset_links is None
        assert request.metadata["note"] == "Relocated"


class TestSensorTypeCreateRequest:
    """Test sensor type creation request schema."""

    def test_sensor_type_create_complete(self):
        """Test sensor type creation with all fields."""
        request = SensorTypeCreateRequest(
            manufacturer="ACME",
            model="TC-2000",
            capabilities=["vehicle_count", "speed"],
            firmware_ver="2.1.0",
            notes="Advanced traffic counter"
        )
        assert request.manufacturer == "ACME"
        assert len(request.capabilities) == 2
        assert request.firmware_ver == "2.1.0"

    def test_sensor_type_create_minimal(self):
        """Test sensor type creation with minimal fields."""
        request = SensorTypeCreateRequest(
            manufacturer="ACME",
            model="TC-2000",
            capabilities=["vehicle_count"]
        )
        assert request.firmware_ver is None
        assert request.notes is None


class TestRealtimeCommandRequest:
    """Test realtime command request schema."""

    def test_realtime_command_request_with_duration(self):
        """Test realtime command with duration."""
        request = RealtimeCommandRequest(
            dim_percent=75,
            duration_minutes=30,
            note="Testing dimming"
        )
        assert request.dim_percent == 75
        assert request.duration_minutes == 30
        assert request.note == "Testing dimming"

    def test_realtime_command_request_requires_duration(self):
        """Missing duration should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RealtimeCommandRequest(dim_percent=50)
        assert "duration_minutes" in str(exc_info.value)

    def test_realtime_command_dim_percent_validation_low(self):
        """Test dim percent below 0 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RealtimeCommandRequest(dim_percent=-1, duration_minutes=10)
        assert "greater than or equal to 0" in str(exc_info.value).lower()

    def test_realtime_command_dim_percent_validation_high(self):
        """Test dim percent above 100 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RealtimeCommandRequest(dim_percent=101, duration_minutes=10)
        assert "less than or equal to 100" in str(exc_info.value).lower()

    def test_realtime_command_duration_validation_bounds(self):
        """Ensure duration must be within allowed limits."""
        with pytest.raises(ValidationError):
            RealtimeCommandRequest(dim_percent=50, duration_minutes=0)
        with pytest.raises(ValidationError):
            RealtimeCommandRequest(dim_percent=50, duration_minutes=2000)

# TODO: Why is this here instead of being in a test_command file?
class TestRealtimeCommandResponse:
    """Test realtime command response schema."""

    def test_realtime_command_response(self):
        """Test realtime command response."""
        now = datetime.now(timezone.utc)
        response = RealtimeCommandResponse(
            command_id="cmd-123",
            status="accepted",
            duration_minutes=30,
            message="Command sent successfully",
            timestamp=now
        )
        assert response.command_id == "cmd-123"
        assert response.status == "accepted"
        assert response.duration_minutes == 30


class TestScheduleSchemas:
    """Test schedule-related schemas."""

    def test_schedule_step(self):
        """Test schedule step."""
        step = ScheduleStep(time="18:00", dim=80)
        assert step.time == "18:00"
        assert step.dim == 80

    def test_schedule_step_dim_validation(self):
        """Test schedule step dim validation."""
        with pytest.raises(ValidationError) as exc_info:
            ScheduleStep(time="18:00", dim=150)
        assert "less than or equal to 100" in str(exc_info.value).lower()

    def test_schedule_request(self):
        """Test schedule request."""
        steps = [
            ScheduleStep(time="06:00", dim=20),
            ScheduleStep(time="18:00", dim=80),
            ScheduleStep(time="22:00", dim=40),
        ]
        request = ScheduleRequest(steps=steps, note="Evening schedule")
        assert len(request.steps) == 3
        assert request.note == "Evening schedule"
