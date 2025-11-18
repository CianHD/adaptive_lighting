"""
Tests for SensorService and SensorTypeService - sensor CRUD operations,
data ingestion, deduplication, and sensor type management.
"""
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import IntegrityError, DatabaseError
from sqlalchemy.orm import Session

from src.services.sensor_service import SensorService, SensorTypeService
from src.db.models import (
    Sensor, Asset, SensorType, VehicleReading, PedReading,
    SpeedReading, SensorAssetLink, AuditLog
)
from src.schemas.sensor import SensorIngestRequest, SensorResponse


class TestCreateReadingHash:
    """Tests for reading hash creation"""

    def test_create_reading_hash_consistent(self):
        """Test that hash is consistent for same inputs"""
        sensor_id = "sensor-123"
        timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        data = {"vehicle_count": 10, "avg_speed": 50}

        hash1 = SensorService.create_reading_hash(sensor_id, timestamp, data)
        hash2 = SensorService.create_reading_hash(sensor_id, timestamp, data)

        assert hash1 == hash2
        assert isinstance(hash1, bytes)

    def test_create_reading_hash_different_data(self):
        """Test that different data produces different hash"""
        sensor_id = "sensor-123"
        timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        hash1 = SensorService.create_reading_hash(sensor_id, timestamp, {"count": 10})
        hash2 = SensorService.create_reading_hash(sensor_id, timestamp, {"count": 20})

        assert hash1 != hash2


class TestIngestSensorData:
    """Tests for sensor data ingestion"""

    def test_ingest_sensor_data_vehicle_count(self):
        """Test ingesting vehicle count data"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_sensor = Mock(spec=Sensor)
        mock_sensor.sensor_id = "sensor-123"

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_sensor

        request = SensorIngestRequest(
            sensor_external_id="EXT-SENSOR-1",
            observed_at=datetime.now(timezone.utc),
            vehicle_count=15,
            section="northbound"
        )

        added_objects = []
        def capture_add(obj):
            if isinstance(obj, VehicleReading):
                obj.vehicle_reading_id = "vehicle-reading-123"
            added_objects.append(obj)

        mock_db.add.side_effect = capture_add
        mock_db.flush.return_value = None

        reading_ids, dedup = SensorService.ingest_sensor_data(
            request=request,
            project_id="proj-123",
            api_client_name="test-client",
            idempotency_key="idem-123",
            db=mock_db
        )

        assert "vehicle" in reading_ids
        assert dedup is False
        assert any(isinstance(obj, VehicleReading) for obj in added_objects)
        vehicle_reading = next(obj for obj in added_objects if isinstance(obj, VehicleReading))
        assert vehicle_reading.section == "northbound"
        audit_entries = [obj for obj in added_objects if isinstance(obj, AuditLog)]
        assert audit_entries
        assert audit_entries[0].details["section"] == "northbound"
        mock_db.commit.assert_called_once()

    def test_ingest_sensor_data_all_types(self):
        """Test ingesting all sensor data types"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_sensor = Mock(spec=Sensor)
        mock_sensor.sensor_id = "sensor-123"

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_sensor

        request = SensorIngestRequest(
            sensor_external_id="EXT-SENSOR-1",
            observed_at=datetime.now(timezone.utc),
            vehicle_count=15,
            pedestrian_count=5,
            avg_vehicle_speed_kmh=45,
            section="northbound"
        )

        added_objects = []
        def capture_add(obj):
            if isinstance(obj, VehicleReading):
                obj.vehicle_reading_id = "vehicle-reading-123"
            elif isinstance(obj, PedReading):
                obj.ped_reading_id = "ped-reading-123"
            elif isinstance(obj, SpeedReading):
                obj.speed_reading_id = "speed-reading-123"
            added_objects.append(obj)

        mock_db.add.side_effect = capture_add
        mock_db.flush.return_value = None

        reading_ids, dedup = SensorService.ingest_sensor_data(
            request=request,
            project_id="proj-123",
            api_client_name="test-client",
            idempotency_key=None,
            db=mock_db
        )

        assert "vehicle" in reading_ids
        assert "pedestrian" in reading_ids
        assert "speed" in reading_ids
        assert dedup is False
        vehicle_reading = next(obj for obj in added_objects if isinstance(obj, VehicleReading))
        ped_reading = next(obj for obj in added_objects if isinstance(obj, PedReading))
        speed_reading = next(obj for obj in added_objects if isinstance(obj, SpeedReading))
        assert vehicle_reading.section == "northbound"
        assert ped_reading.section == "northbound"
        assert speed_reading.section == "northbound"
        mock_db.commit.assert_called_once()

    def test_ingest_sensor_data_sensor_not_found(self):
        """Test ingesting data when sensor doesn't exist"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        request = SensorIngestRequest(
            sensor_external_id="EXT-SENSOR-999",
            observed_at=datetime.now(timezone.utc),
            vehicle_count=15
        )

        with pytest.raises(ValueError, match="Sensor EXT-SENSOR-999 not found"):
            SensorService.ingest_sensor_data(
                request=request,
                project_id="proj-123",
                api_client_name="test-client",
                idempotency_key=None,
                db=mock_db
            )

    def test_ingest_sensor_data_duplicate_detection(self):
        """Test duplicate reading detection"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_sensor = Mock(spec=Sensor)
        mock_sensor.sensor_id = "sensor-123"

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_sensor

        request = SensorIngestRequest(
            sensor_external_id="EXT-SENSOR-1",
            observed_at=datetime.now(timezone.utc),
            vehicle_count=15
        )

        # Simulate IntegrityError for duplicate - exception needs specific structure
        mock_orig = Mock()
        mock_orig.__str__ = Mock(return_value="uq_vehicle_reading_sensor_ts")

        # Track add call and raise exception after flush
        add_count = [0]
        def add_side_effect(obj):
            add_count[0] += 1

        mock_db.add.side_effect = add_side_effect
        mock_db.flush.side_effect = IntegrityError("", "", mock_orig)

        reading_ids, dedup = SensorService.ingest_sensor_data(
            request=request,
            project_id="proj-123",
            api_client_name="test-client",
            idempotency_key=None,
            db=mock_db
        )

        assert dedup is True
        assert not reading_ids
        mock_db.rollback.assert_called_once()


class TestGetSensorDetails:
    """Tests for getting sensor details"""

    def test_get_sensor_details_success(self):
        """Test successful sensor details retrieval"""
        mock_db = Mock(spec=Session)

        mock_sensor_type = Mock(spec=SensorType)
        mock_sensor_type.manufacturer = "ACME"
        mock_sensor_type.model = "Counter-3000"
        mock_sensor_type.capabilities = ["vehicle_count", "pedestrian_count"]

        mock_sensor = Mock(spec=Sensor)
        mock_sensor.sensor_id = "sensor-123"
        mock_sensor.external_id = "EXT-SENSOR-1"
        mock_sensor.sensor_type = mock_sensor_type
        mock_sensor.sensor_metadata = {"vendor": "VendorX", "name": "Main Street Sensor"}

        mock_asset = Mock(spec=Asset)
        mock_asset.asset_id = "asset-123"
        mock_asset.external_id = "EXT-ASSET-1"

        mock_link = Mock(spec=SensorAssetLink)
        mock_link.sensor_id = "sensor-123"
        mock_link.asset_id = "asset-123"
        mock_link.section = "north"

        # Setup query: first returns sensor, second returns joined (link, asset) tuples
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.first.return_value = mock_sensor
        mock_query.all.return_value = [(mock_link, mock_asset)]

        mock_db.query.return_value = mock_query

        result = SensorService.get_sensor_details("EXT-SENSOR-1", "proj-123", mock_db)

        assert isinstance(result, SensorResponse)
        assert result.external_id == "EXT-SENSOR-1"
        assert result.sensor_type == "ACME Counter-3000"
        assert len(result.linked_assets) == 1
        assert result.linked_assets[0].asset_exedra_id == "EXT-ASSET-1"
        assert result.linked_assets[0].section == "north"
        assert result.vendor == "VendorX"

    def test_get_sensor_details_not_found(self):
        """Test getting details when sensor doesn't exist"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(ValueError, match="Sensor EXT-SENSOR-999 not found"):
            SensorService.get_sensor_details("EXT-SENSOR-999", "proj-123", mock_db)


class TestCreateSensor:
    """Tests for sensor creation"""

    def test_create_sensor_success(self):
        """Test successful sensor creation with sections"""
        mock_db = Mock(spec=Session)

        mock_sensor_type = Mock(spec=SensorType)
        mock_sensor_type.sensor_type_id = "type-123"

        mock_asset = Mock(spec=Asset)
        mock_asset.asset_id = "asset-123"
        mock_asset.external_id = "EXT-ASSET-1"

        # Setup query chains
        query_count = [0]
        def query_side_effect(model):
            mock_query = Mock()
            mock_query.filter.return_value = mock_query
            mock_query.all.return_value = []

            query_count[0] += 1
            if query_count[0] == 1:
                # Check existing sensor
                mock_query.first.return_value = None
            elif query_count[0] == 2:
                # Get sensor type
                mock_query.first.return_value = mock_sensor_type
            elif query_count[0] == 3:
                # Get assets
                mock_query.in_.return_value = mock_query
                mock_query.all.return_value = [mock_asset]

            return mock_query

        mock_db.query.side_effect = query_side_effect

        added_objects = []
        def capture_add(obj):
            if isinstance(obj, Sensor):
                obj.sensor_id = "new-sensor-123"
            added_objects.append(obj)

        mock_db.add.side_effect = capture_add
        mock_db.flush.return_value = None

        result = SensorService.create_sensor(
            external_id="EXT-SENSOR-NEW",
            project_id="proj-123",
            sensor_type_id="type-123",
            asset_links=[{"asset_exedra_id": "EXT-ASSET-1", "section": "north"}],
            metadata={"vendor": "VendorX"},
            actor="test-actor",
            db=mock_db
        )

        assert isinstance(result, Sensor)
        assert result.sensor_id == "new-sensor-123"

        # Verify sensor asset link created with section
        link_created = any(isinstance(obj, SensorAssetLink) for obj in added_objects)
        assert link_created

        # Check that section was set
        links = [obj for obj in added_objects if isinstance(obj, SensorAssetLink)]
        assert len(links) == 1
        assert links[0].section == "north"

        mock_db.commit.assert_called_once()

    def test_create_sensor_already_exists(self):
        """Test sensor creation when sensor already exists"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        existing_sensor = Mock(spec=Sensor)

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_sensor

        with pytest.raises(ValueError, match="already exists"):
            SensorService.create_sensor(
                external_id="EXT-SENSOR-1",
                project_id="proj-123",
                sensor_type_id="type-123",
                asset_links=[{"asset_exedra_id": "EXT-ASSET-1", "section": None}],
                metadata={},
                db=mock_db
            )

    def test_create_sensor_type_not_found(self):
        """Test sensor creation when sensor type doesn't exist"""
        mock_db = Mock(spec=Session)

        query_count = [0]
        def query_side_effect(model):
            mock_query = Mock()
            mock_query.filter.return_value = mock_query

            query_count[0] += 1
            if query_count[0] == 1:
                # Check existing sensor - not found
                mock_query.first.return_value = None
            elif query_count[0] == 2:
                # Get sensor type - not found
                mock_query.first.return_value = None

            return mock_query

        mock_db.query.side_effect = query_side_effect

        with pytest.raises(ValueError, match="Sensor type with ID 'type-999' not found"):
            SensorService.create_sensor(
                external_id="EXT-SENSOR-NEW",
                project_id="proj-123",
                sensor_type_id="type-999",
                asset_links=[{"asset_exedra_id": "EXT-ASSET-1", "section": None}],
                metadata={},
                db=mock_db
            )

    def test_create_sensor_asset_not_found(self):
        """Test sensor creation when asset doesn't exist"""
        mock_db = Mock(spec=Session)

        mock_sensor_type = Mock(spec=SensorType)

        query_count = [0]
        def query_side_effect(model):
            mock_query = Mock()
            mock_query.filter.return_value = mock_query
            mock_query.all.return_value = []

            query_count[0] += 1
            if query_count[0] == 1:
                # Check existing sensor
                mock_query.first.return_value = None
            elif query_count[0] == 2:
                # Get sensor type
                mock_query.first.return_value = mock_sensor_type
            elif query_count[0] == 3:
                # Get assets - not found
                mock_query.in_.return_value = mock_query
                mock_query.all.return_value = []

            return mock_query

        mock_db.query.side_effect = query_side_effect

        with pytest.raises(ValueError, match="Assets not found in this project"):
            SensorService.create_sensor(
                external_id="EXT-SENSOR-NEW",
                project_id="proj-123",
                sensor_type_id="type-123",
                asset_links=[{"asset_exedra_id": "EXT-ASSET-999", "section": None}],
                metadata={},
                db=mock_db
            )


    def test_create_sensor_database_error(self):
        """Test create sensor handles generic database errors"""
        mock_db = Mock(spec=Session)

        mock_sensor_type = Mock(spec=SensorType)
        mock_sensor_type.sensor_type_id = "type-123"

        mock_asset = Mock(spec=Asset)
        mock_asset.asset_id = "asset-123"
        mock_asset.external_id = "EXT-ASSET-1"  # Add external_id for asset validation

        query_count = [0]
        def query_side_effect(model):
            mock_query_inner = Mock()
            mock_query_inner.filter.return_value = mock_query_inner
            query_count[0] += 1
            if query_count[0] == 1:
                # Check existing sensor - not found (so we proceed)
                mock_query_inner.first.return_value = None
            elif query_count[0] == 2:
                # Get sensor type - found
                mock_query_inner.first.return_value = mock_sensor_type
            elif query_count[0] == 3:
                # Get assets - found
                mock_query_inner.in_.return_value = mock_query_inner
                mock_query_inner.all.return_value = [mock_asset]
            return mock_query_inner

        mock_db.query.side_effect = query_side_effect
        # Make commit raise a DatabaseError (not IntegrityError to avoid duplicate check)
        mock_db.commit.side_effect = DatabaseError("statement", {}, Exception("Generic DB error"))

        with pytest.raises(RuntimeError, match="Database error during sensor creation"):
            SensorService.create_sensor(
                external_id="EXT-SENSOR-NEW",
                project_id="proj-123",
                sensor_type_id="type-123",
                asset_links=[{"asset_exedra_id": "EXT-ASSET-1", "section": None}],
                metadata={},
                db=mock_db
            )

        mock_db.rollback.assert_called_once()


class TestUpdateSensor:
    """Tests for sensor updates"""

    def test_update_sensor_success(self):
        """Test successful sensor update"""
        mock_db = Mock(spec=Session)

        mock_sensor = Mock(spec=Sensor)
        mock_sensor.sensor_id = "sensor-123"
        mock_sensor.sensor_metadata = {"old": "value"}

        mock_sensor_type = Mock(spec=SensorType)
        mock_sensor_type.sensor_type_id = "type-456"

        mock_asset = Mock(spec=Asset)
        mock_asset.asset_id = "asset-123"
        mock_asset.external_id = "EXT-ASSET-1"

        query_count = [0]
        def query_side_effect(model):
            mock_query = Mock()
            mock_query.filter.return_value = mock_query
            mock_query.delete.return_value = None

            query_count[0] += 1
            if query_count[0] == 1:
                # Get sensor
                mock_query.first.return_value = mock_sensor
            elif query_count[0] == 2:
                # Get sensor type
                mock_query.first.return_value = mock_sensor_type
            elif query_count[0] == 3:
                # Get assets
                mock_query.in_.return_value = mock_query
                mock_query.all.return_value = [mock_asset]
            elif query_count[0] == 4:
                # Delete existing links
                pass

            return mock_query

        mock_db.query.side_effect = query_side_effect

        result = SensorService.update_sensor(
            external_id="EXT-SENSOR-1",
            project_id="proj-123",
            sensor_type_id="type-456",
            asset_links=[{"asset_exedra_id": "EXT-ASSET-1", "section": "south"}],
            metadata={"new": "data"},
            actor="test-actor",
            db=mock_db
        )

        assert result == mock_sensor
        assert mock_sensor.sensor_type_id == "type-456"
        assert mock_sensor.sensor_metadata["new"] == "data"

        # Verify section was set on the link
        links = [obj for obj in mock_db.add.call_args_list if isinstance(obj[0][0], SensorAssetLink)]
        assert len(links) == 1
        assert links[0][0][0].section == "south"

        mock_db.commit.assert_called_once()

    def test_update_sensor_not_found(self):
        """Test updating sensor when it doesn't exist"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            SensorService.update_sensor(
                external_id="EXT-SENSOR-999",
                project_id="proj-123",
                metadata={"test": "data"},
                db=mock_db
            )

    def test_update_sensor_no_updates(self):
        """Test updating sensor with no fields provided"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_sensor = Mock(spec=Sensor)

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_sensor

        with pytest.raises(ValueError, match="At least one field must be provided"):
            SensorService.update_sensor(
                external_id="EXT-SENSOR-1",
                project_id="proj-123",
                db=mock_db
            )

    def test_update_sensor_database_error(self):
        """Test update sensor handles database errors"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_sensor = Mock(spec=Sensor)
        mock_sensor.sensor_id = "sensor-123"
        mock_sensor.sensor_metadata = {}

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_sensor
        mock_db.commit.side_effect = DatabaseError("statement", {}, Exception("DB error"))

        with pytest.raises(RuntimeError, match="Database error during sensor update"):
            SensorService.update_sensor(
                external_id="EXT-SENSOR-1",
                project_id="proj-123",
                metadata={"new": "data"},
                db=mock_db
            )

        mock_db.rollback.assert_called_once()


class TestDeleteSensor:
    """Tests for sensor deletion"""

    def test_delete_sensor_success(self):
        """Test successful sensor deletion"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_sensor_type = Mock(spec=SensorType)
        mock_sensor_type.manufacturer = "ACME"
        mock_sensor_type.model = "Counter-3000"

        mock_sensor = Mock(spec=Sensor)
        mock_sensor.sensor_id = "sensor-123"
        mock_sensor.external_id = "EXT-SENSOR-1"
        mock_sensor.sensor_type = mock_sensor_type

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_sensor

        result = SensorService.delete_sensor(
            external_id="EXT-SENSOR-1",
            project_id="proj-123",
            actor="test-actor",
            db=mock_db
        )

        assert result is True
        mock_db.delete.assert_called_once_with(mock_sensor)
        mock_db.commit.assert_called_once()

    def test_delete_sensor_not_found(self):
        """Test deleting sensor when it doesn't exist"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            SensorService.delete_sensor(
                external_id="EXT-SENSOR-999",
                project_id="proj-123",
                db=mock_db
            )

    def test_delete_sensor_database_error(self):
        """Test delete sensor handles database errors"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_sensor = Mock(spec=Sensor)
        mock_sensor.sensor_id = "sensor-123"

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_sensor
        mock_db.commit.side_effect = DatabaseError("statement", {}, Exception("DB error"))

        with pytest.raises(RuntimeError, match="Database error during sensor deletion"):
            SensorService.delete_sensor(
                external_id="EXT-SENSOR-1",
                project_id="proj-123",
                db=mock_db
            )

        mock_db.rollback.assert_called_once()


class TestListAssetGroups:
    """Tests for SensorService.list_asset_groups"""

    class _Row:
        def __init__(self, sensor_id, sensor_external_id, section, asset_external_id):
            self.sensor_id = sensor_id
            self.sensor_external_id = sensor_external_id
            self.section = section
            self.asset_external_id = asset_external_id

    def test_list_asset_groups_returns_grouped_results(self):
        """Test listing asset groups returns correctly grouped results"""

        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [
            self._Row("sensor-1", "S-1", "north", "asset-1"),
            self._Row("sensor-1", "S-1", "north", "asset-2"),
            self._Row("sensor-1", "S-1", "south", "asset-3"),
            self._Row("sensor-2", "S-2", None, "asset-4"),
        ]

        results = SensorService.list_asset_groups("proj-123", mock_db)

        assert len(results) == 3
        assert results[0].sensor_external_id == "S-1"
        assert results[0].asset_exedra_ids == ["asset-1", "asset-2"]
        assert results[0].asset_count == 2
        assert any(group.section is None for group in results)

    def test_list_asset_groups_returns_empty_when_no_rows(self):
        """Test listing asset groups when no data exists"""

        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        results = SensorService.list_asset_groups("proj-123", mock_db)

        assert results == []


class TestCreateSensorType:
    """Tests for sensor type creation"""

    def test_create_sensor_type_success(self):
        """Test successful sensor type creation"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        # No existing sensor type
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        added_objects = []
        def capture_add(obj):
            if isinstance(obj, SensorType):
                obj.sensor_type_id = "new-type-123"
            added_objects.append(obj)

        mock_db.add.side_effect = capture_add
        mock_db.flush.return_value = None

        result = SensorTypeService.create_sensor_type(
            manufacturer="ACME",
            model="Counter-3000",
            capabilities=["vehicle_count", "speed"],
            firmware_ver="v1.2.3",
            notes="Test sensor type",
            actor="test-actor",
            db=mock_db
        )

        assert isinstance(result, SensorType)
        assert result.sensor_type_id == "new-type-123"
        mock_db.commit.assert_called_once()

    def test_create_sensor_type_already_exists(self):
        """Test sensor type creation when it already exists"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        existing_type = Mock(spec=SensorType)

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_type

        with pytest.raises(ValueError, match="already exists"):
            SensorTypeService.create_sensor_type(
                manufacturer="ACME",
                model="Counter-3000",
                capabilities=["vehicle_count"],
                db=mock_db
            )


class TestUpdateSensorType:
    """Tests for sensor type updates"""

    def test_update_sensor_type_success(self):
        """Test successful sensor type update"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_sensor_type = Mock(spec=SensorType)
        mock_sensor_type.sensor_type_id = "type-123"
        mock_sensor_type.manufacturer = "ACME"
        mock_sensor_type.model = "Counter-3000"

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_sensor_type

        result = SensorTypeService.update_sensor_type(
            sensor_type_id="type-123",
            capabilities=["vehicle_count", "speed", "pedestrian_count"],
            firmware_ver="v2.0.0",
            actor="test-actor",
            db=mock_db
        )

        assert result == mock_sensor_type
        assert mock_sensor_type.capabilities == ["vehicle_count", "speed", "pedestrian_count"]
        assert mock_sensor_type.firmware_ver == "v2.0.0"
        mock_db.commit.assert_called_once()

    def test_update_sensor_type_not_found(self):
        """Test updating sensor type when it doesn't exist"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            SensorTypeService.update_sensor_type(
                sensor_type_id="type-999",
                capabilities=["vehicle_count"],
                db=mock_db
            )

    def test_update_sensor_type_no_updates(self):
        """Test updating sensor type with no fields provided"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_sensor_type = Mock(spec=SensorType)

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_sensor_type

        with pytest.raises(ValueError, match="At least one field must be provided"):
            SensorTypeService.update_sensor_type(
                sensor_type_id="type-123",
                db=mock_db
            )


class TestDeleteSensorType:
    """Tests for sensor type deletion"""

    def test_delete_sensor_type_success(self):
        """Test successful sensor type deletion"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_sensor_type = Mock(spec=SensorType)
        mock_sensor_type.sensor_type_id = "type-123"
        mock_sensor_type.manufacturer = "ACME"
        mock_sensor_type.model = "Counter-3000"
        mock_sensor_type.capabilities = ["vehicle_count"]

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_sensor_type

        result = SensorTypeService.delete_sensor_type(
            sensor_type_id="type-123",
            actor="test-actor",
            db=mock_db
        )

        assert result is True
        mock_db.delete.assert_called_once_with(mock_sensor_type)
        mock_db.commit.assert_called_once()

    def test_delete_sensor_type_not_found(self):
        """Test deleting sensor type when it doesn't exist"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            SensorTypeService.delete_sensor_type(
                sensor_type_id="type-999",
                db=mock_db
            )

    def test_delete_sensor_type_still_referenced(self):
        """Test deleting sensor type when it's still referenced"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_sensor_type = Mock(spec=SensorType)
        mock_sensor_type.sensor_type_id = "type-123"
        mock_sensor_type.manufacturer = "ACME"
        mock_sensor_type.model = "Counter-3000"
        mock_sensor_type.capabilities = ["vehicle_count"]

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_sensor_type

        # Simulate foreign key constraint error
        mock_orig = Mock()
        mock_orig.__str__ = Mock(return_value="FOREIGN KEY constraint failed")

        # add() succeeds, but commit() raises IntegrityError
        mock_db.commit.side_effect = IntegrityError("", "", mock_orig)

        with pytest.raises(ValueError, match="Cannot delete sensor type"):
            SensorTypeService.delete_sensor_type(
                sensor_type_id="type-123",
                db=mock_db
            )

        mock_db.rollback.assert_called_once()


class TestGetSensorType:
    """Tests for getting sensor type"""

    def test_get_sensor_type_success(self):
        """Test successful sensor type retrieval"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_sensor_type = Mock(spec=SensorType)
        mock_sensor_type.sensor_type_id = "type-123"

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_sensor_type

        result = SensorTypeService.get_sensor_type("type-123", mock_db)

        assert result == mock_sensor_type

    def test_get_sensor_type_not_found(self):
        """Test getting sensor type when it doesn't exist"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            SensorTypeService.get_sensor_type("type-999", mock_db)


class TestListSensorTypes:
    """Tests for listing sensor types"""

    def test_list_sensor_types(self):
        """Test listing all sensor types"""
        mock_db = Mock(spec=Session)
        mock_query = Mock()

        mock_types = [Mock(spec=SensorType) for _ in range(3)]

        mock_db.query.return_value = mock_query
        mock_query.all.return_value = mock_types

        result = SensorTypeService.list_sensor_types(mock_db)

        assert result == mock_types
        assert len(result) == 3
