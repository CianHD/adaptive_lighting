"""Tests for Sensor API endpoints."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from src.api.sensor import (
    create_sensor,
    create_sensor_type,
    delete_sensor,
    delete_sensor_type,
    get_sensor,
    get_sensor_type,
    ingest_sensor_data,
    list_asset_groups,
    list_sensor_types,
    update_sensor,
    update_sensor_type,
)
from src.schemas.sensor import (
    SensorAssetLinkInfo,
    SensorAssetGroup,
    SensorCreateRequest,
    SensorIngestRequest,
    SensorResponse,
    SensorTypeCreateRequest,
    SensorTypeUpdateRequest,
    SensorUpdateRequest,
)


@pytest.fixture
def mock_authenticated_client():
    """Mock authenticated client with project and API client."""
    client = Mock()
    client.project.project_id = "proj-123"
    client.project.code = "TEST"
    client.api_client.api_client_id = "client-123"
    client.api_client.name = "test-client"
    client.scopes = [
        "sensor:ingest",
        "sensor:metadata",
        "sensor:create",
        "sensor:update",
        "sensor:delete",
        "sensor:type:create",
        "sensor:type:update",
        "sensor:type:delete",
    ]
    return client


@pytest.fixture
def mock_db():
    """Mock database session."""
    return Mock()


@pytest.fixture
def mock_sensor():
    """Mock sensor object."""
    sensor = Mock()
    sensor.sensor_id = "sensor-123"
    sensor.external_id = "ext-sensor-1"
    sensor.sensor_type_id = "type-123"
    sensor.sensor_metadata = {"location": "intersection-1"}
    sensor.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    sensor.updated_at = datetime(2024, 1, 2, tzinfo=timezone.utc)
    sensor.links = []
    return sensor


@pytest.fixture
def mock_sensor_type():
    """Mock sensor type object."""
    sensor_type = Mock()
    sensor_type.sensor_type_id = "type-123"
    sensor_type.manufacturer = "Acme Corp"
    sensor_type.model = "TrafficSensor-5000"
    sensor_type.capabilities = ["vehicle_count", "speed"]
    sensor_type.firmware_ver = "1.2.3"
    sensor_type.notes = "Test sensor type"
    return sensor_type


class TestIngestSensorData:
    """Tests for POST /sensor/ingest"""

    @patch('src.api.sensor.SensorService.ingest_sensor_data')
    async def test_ingest_success(self, mock_ingest, mock_authenticated_client, mock_db):
        """Test successful sensor data ingestion."""
        mock_ingest.return_value = ({"vehicle": "reading-1", "pedestrian": "reading-2"}, False)

        request = SensorIngestRequest(
            sensor_external_id="ext-sensor-1",
            observed_at=datetime.now(timezone.utc),
            vehicle_count=10,
            pedestrian_count=5,
            avg_vehicle_speed_kmh=45.5,
            section="northbound"
        )

        result = await ingest_sensor_data(
            request=request,
            idempotency_key="key-123",
            client=mock_authenticated_client,
            db=mock_db
        )

        assert len(result.reading_ids) == 2
        assert result.dedup is False
        mock_ingest.assert_called_once()

    @patch('src.api.sensor.SensorService.ingest_sensor_data')
    async def test_ingest_sensor_not_found(self, mock_ingest, mock_authenticated_client, mock_db):
        """Test ingesting data for non-existent sensor."""
        mock_ingest.side_effect = ValueError("Sensor not found")

        request = SensorIngestRequest(
            sensor_external_id="nonexistent",
            observed_at=datetime.now(timezone.utc),
            vehicle_count=10
        )

        with pytest.raises(HTTPException) as exc_info:
            await ingest_sensor_data(
                request=request,
                idempotency_key=None,
                client=mock_authenticated_client,
                db=mock_db
            )

        assert exc_info.value.status_code == 404

    @patch('src.api.sensor.SensorService.ingest_sensor_data')
    async def test_ingest_data_integrity_error(
        self,
        mock_ingest,
        mock_authenticated_client,
        mock_db,
    ):
        """Test ingestion with data integrity error."""
        mock_ingest.side_effect = Exception("Data integrity error")

        request = SensorIngestRequest(
            sensor_external_id="ext-sensor-1",
            observed_at=datetime.now(timezone.utc),
            vehicle_count=10
        )

        with pytest.raises(HTTPException) as exc_info:
            await ingest_sensor_data(
                request=request,
                idempotency_key=None,
                client=mock_authenticated_client,
                db=mock_db
            )

        assert exc_info.value.status_code == 400


class TestListLuminaireGroups:
    """Tests for GET /sensor/groups"""

    @patch('src.api.sensor.SensorService.list_asset_groups')
    async def test_list_groups_success(self, mock_list_groups, mock_authenticated_client, mock_db):
        """"Test successful listing of luminaire groups."""

        mock_list_groups.return_value = [
            SensorAssetGroup(
                sensor_external_id="S-1",
                section="north",
                asset_exedra_ids=["asset-1", "asset-2"],
                asset_count=2
            )
        ]

        result = await list_asset_groups(
            client=mock_authenticated_client,
            db=mock_db
        )

        assert len(result) == 1
        assert result[0].asset_count == 2
        mock_list_groups.assert_called_once_with(project_id="proj-123", db=mock_db)

    @patch('src.api.sensor.SensorService.list_asset_groups')
    async def test_list_groups_unexpected_error(self, mock_list_groups, mock_authenticated_client, mock_db):
        """Test listing luminaire groups with unexpected error."""

        mock_list_groups.side_effect = Exception("boom")

        with pytest.raises(HTTPException) as exc_info:
            await list_asset_groups(
                client=mock_authenticated_client,
                db=mock_db
            )

        assert exc_info.value.status_code == 500


class TestGetSensor:
    """Tests for GET /sensor/{external_id}"""

    @patch('src.api.sensor.SensorService.get_sensor_details')
    async def test_get_sensor_success(self, mock_get_details, mock_authenticated_client, mock_db):
        """Test successful sensor retrieval."""
        mock_get_details.return_value = SensorResponse(
            external_id="ext-sensor-1",
            sensor_type="TrafficSensor-5000",
            linked_assets=[SensorAssetLinkInfo(asset_exedra_id="asset-1", section="east")],
            manufacturer="Acme Corp",
            model="Sensor 1",
            capabilities=["vehicle_count", "speed"],
            metadata={"location": "intersection-1"}
        )

        result = await get_sensor(
            external_id="ext-sensor-1",
            client=mock_authenticated_client,
            db=mock_db
        )

        assert result.external_id == "ext-sensor-1"
        assert result.sensor_type == "TrafficSensor-5000"

    @patch('src.api.sensor.SensorService.get_sensor_details')
    async def test_get_sensor_not_found(self, mock_get_details, mock_authenticated_client, mock_db):
        """Test sensor not found."""
        mock_get_details.side_effect = ValueError("Sensor not found")

        with pytest.raises(HTTPException) as exc_info:
            await get_sensor(
                external_id="nonexistent",
                client=mock_authenticated_client,
                db=mock_db
            )

        assert exc_info.value.status_code == 404


class TestCreateSensor:
    """Tests for POST /sensor/"""

    @patch('src.api.sensor.SensorService.create_sensor')
    async def test_create_sensor_success(
        self,
        mock_create,
        mock_authenticated_client,
        mock_db,
        mock_sensor,
    ):
        """Test successful sensor creation."""
        # Add mock links to sensor
        mock_link1 = Mock()
        mock_asset1 = Mock()
        mock_asset1.external_id = "asset-1"
        mock_link1.asset = mock_asset1
        mock_link1.section = "north"

        mock_link2 = Mock()
        mock_asset2 = Mock()
        mock_asset2.external_id = "asset-2"
        mock_link2.asset = mock_asset2
        mock_link2.section = None

        mock_sensor.links = [mock_link1, mock_link2]
        mock_create.return_value = mock_sensor

        request = SensorCreateRequest(
            external_id="ext-sensor-1",
            sensor_type_id="type-123",
            asset_links=[
                SensorAssetLinkInfo(asset_exedra_id="asset-1", section="north"),
                SensorAssetLinkInfo(asset_exedra_id="asset-2", section=None)
            ],
            metadata={"location": "intersection-1"}
        )

        result = await create_sensor(
            request=request,
            client=mock_authenticated_client,
            db=mock_db
        )

        assert result.sensor_id == "sensor-123"
        assert result.external_id == "ext-sensor-1"
        assert len(result.linked_assets) == 2
        assert result.linked_assets[0].asset_exedra_id == "asset-1"
        assert result.linked_assets[0].section == "north"
        assert result.linked_assets[1].asset_exedra_id == "asset-2"
        assert result.linked_assets[1].section is None

    @patch('src.api.sensor.SensorService.create_sensor')
    async def test_create_sensor_value_error(self, mock_create, mock_authenticated_client, mock_db):
        """Test sensor creation with validation error."""
        mock_create.side_effect = ValueError("Invalid sensor type")

        request = SensorCreateRequest(
            external_id="ext-sensor-1",
            sensor_type_id="invalid",
            asset_links=[]
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_sensor(request=request, client=mock_authenticated_client, db=mock_db)

        assert exc_info.value.status_code == 400

    @patch('src.api.sensor.SensorService.create_sensor')
    async def test_create_sensor_runtime_error(
        self,
        mock_create,
        mock_authenticated_client,
        mock_db,
    ):
        """Test sensor creation with runtime error."""
        mock_create.side_effect = RuntimeError("Database error")

        request = SensorCreateRequest(
            external_id="ext-sensor-1",
            sensor_type_id="type-123",
            asset_links=[]
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_sensor(request=request, client=mock_authenticated_client, db=mock_db)

        assert exc_info.value.status_code == 500


class TestUpdateSensor:
    """Tests for PUT /sensor/{external_id}"""

    @patch('src.api.sensor.SensorService.update_sensor')
    async def test_update_sensor_success(
        self,
        mock_update,
        mock_authenticated_client,
        mock_db,
        mock_sensor,
    ):
        """Test successful sensor update."""
        # Add mock links
        mock_link = Mock()
        mock_asset = Mock()
        mock_asset.external_id = "asset-1"
        mock_link.asset = mock_asset
        mock_link.section = "west"  # Set actual string value, not Mock
        mock_sensor.links = [mock_link]

        mock_update.return_value = mock_sensor

        request = SensorUpdateRequest(
            sensor_type_id="type-123",
            asset_links=[SensorAssetLinkInfo(asset_exedra_id="asset-1", section="west")],
            metadata={"location": "updated"}
        )

        result = await update_sensor(
            external_id="ext-sensor-1",
            request=request,
            client=mock_authenticated_client,
            db=mock_db
        )

        assert result.sensor_id == "sensor-123"
        assert len(result.linked_assets) == 1

    @patch('src.api.sensor.SensorService.update_sensor')
    async def test_update_sensor_not_found(self, mock_update, mock_authenticated_client, mock_db):
        """Test updating non-existent sensor."""
        mock_update.side_effect = ValueError("Sensor not found")

        request = SensorUpdateRequest(
            sensor_type_id="type-123",
            asset_links=[]
        )

        with pytest.raises(HTTPException) as exc_info:
            await update_sensor(
                external_id="nonexistent",
                request=request,
                client=mock_authenticated_client,
                db=mock_db
            )

        assert exc_info.value.status_code == 400


class TestDeleteSensor:
    """Tests for DELETE /sensor/{external_id}"""

    @patch('src.api.sensor.SensorService.delete_sensor')
    async def test_delete_sensor_success(self, mock_delete, mock_authenticated_client, mock_db):
        """Test successful sensor deletion."""
        mock_delete.return_value = None

        result = await delete_sensor(
            external_id="ext-sensor-1",
            client=mock_authenticated_client,
            db=mock_db
        )

        assert "deleted successfully" in result["message"]

    @patch('src.api.sensor.SensorService.delete_sensor')
    async def test_delete_sensor_not_found(self, mock_delete, mock_authenticated_client, mock_db):
        """Test deleting non-existent sensor."""
        mock_delete.side_effect = ValueError("Sensor not found")

        with pytest.raises(HTTPException) as exc_info:
            await delete_sensor(
                external_id="nonexistent",
                client=mock_authenticated_client,
                db=mock_db
            )

        assert exc_info.value.status_code == 404


@patch('src.api.sensor.SensorService.list_sensor_types')
async def test_list_sensor_types_success(
    mock_list,
    mock_authenticated_client,
    mock_db,
    mock_sensor_type,
):
    """Test successful sensor type listing."""
    mock_list.return_value = [mock_sensor_type]

    result = await list_sensor_types(
        _client=mock_authenticated_client,
        db=mock_db
    )

    assert len(result) == 1
    assert result[0].manufacturer == "Acme Corp"
    assert result[0].model == "TrafficSensor-5000"


class TestGetSensorType:
    """Tests for GET /sensor/type/{sensor_type_id}"""

    @patch('src.api.sensor.SensorService.get_sensor_type')
    async def test_get_sensor_type_success(
        self,
        mock_get,
        mock_authenticated_client,
        mock_db,
        mock_sensor_type,
    ):
        """Test successful sensor type retrieval."""
        mock_get.return_value = mock_sensor_type

        result = await get_sensor_type(
            sensor_type_id="type-123",
            _client=mock_authenticated_client,
            db=mock_db
        )

        assert result.manufacturer == "Acme Corp"
        assert result.model == "TrafficSensor-5000"

    @patch('src.api.sensor.SensorService.get_sensor_type')
    async def test_get_sensor_type_not_found(self, mock_get, mock_authenticated_client, mock_db):
        """Test sensor type not found."""
        mock_get.side_effect = ValueError("Sensor type not found")

        with pytest.raises(HTTPException) as exc_info:
            await get_sensor_type(
                sensor_type_id="nonexistent",
                _client=mock_authenticated_client,
                db=mock_db
            )

        assert exc_info.value.status_code == 404


class TestCreateSensorType:
    """Tests for POST /sensor/type"""

    @patch('src.api.sensor.SensorService.create_sensor_type')
    async def test_create_sensor_type_success(
        self,
        mock_create,
        mock_authenticated_client,
        mock_db,
        mock_sensor_type,
    ):
        """Test successful sensor type creation."""
        mock_create.return_value = mock_sensor_type

        request = SensorTypeCreateRequest(
            manufacturer="Acme Corp",
            model="TrafficSensor-5000",
            capabilities=["vehicle_count", "speed"],
            firmware_ver="1.2.3",
            notes="Test sensor type"
        )

        result = await create_sensor_type(
            request=request,
            client=mock_authenticated_client,
            db=mock_db
        )

        assert result.sensor_type_id == "type-123"
        assert result.manufacturer == "Acme Corp"

    @patch('src.api.sensor.SensorService.create_sensor_type')
    async def test_create_sensor_type_value_error(
        self,
        mock_create,
        mock_authenticated_client,
        mock_db,
    ):
        """Test sensor type creation with validation error."""
        mock_create.side_effect = ValueError("Duplicate sensor type")

        request = SensorTypeCreateRequest(
            manufacturer="Acme Corp",
            model="Duplicate",
            capabilities=[]
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_sensor_type(request=request, client=mock_authenticated_client, db=mock_db)

        assert exc_info.value.status_code == 400


class TestUpdateSensorType:
    """Tests for PUT /sensor/type/{sensor_type_id}"""

    @patch('src.api.sensor.SensorService.update_sensor_type')
    async def test_update_sensor_type_success(
        self,
        mock_update,
        mock_authenticated_client,
        mock_db,
        mock_sensor_type,
    ):
        """Test successful sensor type update."""
        mock_update.return_value = mock_sensor_type

        request = SensorTypeUpdateRequest(
            capabilities=["vehicle_count", "speed", "occupancy"],
            firmware_ver="1.3.0",
            notes="Updated"
        )

        result = await update_sensor_type(
            sensor_type_id="type-123",
            request=request,
            client=mock_authenticated_client,
            db=mock_db
        )

        assert result.sensor_type_id == "type-123"

    @patch('src.api.sensor.SensorService.update_sensor_type')
    async def test_update_sensor_type_not_found(
        self,
        mock_update,
        mock_authenticated_client,
        mock_db,
    ):
        """Test updating non-existent sensor type."""
        mock_update.side_effect = ValueError("Sensor type not found")

        request = SensorTypeUpdateRequest(
            capabilities=["vehicle_count"]
        )

        with pytest.raises(HTTPException) as exc_info:
            await update_sensor_type(
                sensor_type_id="nonexistent",
                request=request,
                client=mock_authenticated_client,
                db=mock_db
            )

        assert exc_info.value.status_code == 400


class TestDeleteSensorType:
    """Tests for DELETE /sensor/type/{sensor_type_id}"""

    @patch('src.api.sensor.SensorService.delete_sensor_type')
    async def test_delete_sensor_type_success(
        self,
        mock_delete,
        mock_authenticated_client,
        mock_db,
    ):
        """Test successful sensor type deletion."""
        mock_delete.return_value = None

        result = await delete_sensor_type(
            sensor_type_id="type-123",
            client=mock_authenticated_client,
            db=mock_db
        )

        assert "deleted successfully" in result["message"]

    @patch('src.api.sensor.SensorService.delete_sensor_type')
    async def test_delete_sensor_type_not_found(
        self,
        mock_delete,
        mock_authenticated_client,
        mock_db,
    ):
        """Test deleting non-existent sensor type."""
        mock_delete.side_effect = ValueError("Sensor type not found")

        with pytest.raises(HTTPException) as exc_info:
            await delete_sensor_type(
                sensor_type_id="nonexistent",
                client=mock_authenticated_client,
                db=mock_db
            )

        assert exc_info.value.status_code == 404

    @patch('src.api.sensor.SensorService.delete_sensor_type')
    async def test_delete_sensor_type_in_use(self, mock_delete, mock_authenticated_client, mock_db):
        """Test deleting sensor type that's still in use."""
        mock_delete.side_effect = IntegrityError("FK constraint", None, None)

        with pytest.raises(HTTPException) as exc_info:
            await delete_sensor_type(
                sensor_type_id="type-123",
                client=mock_authenticated_client,
                db=mock_db
            )

        assert exc_info.value.status_code == 409
        assert "still referenced" in exc_info.value.detail
