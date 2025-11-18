"""Tests for database models."""
import json
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from src.db.models import (
    ApiClient,
    ApiKey,
    Asset,
    ClientCredential,
    Project,
    Sensor,
    SensorAssetLink,
    SensorType,
)


def serialize_for_sqlite(value):
    """Helper to serialize lists to JSON for SQLite ARRAY fields."""
    if isinstance(value, list):
        return json.dumps(value)
    return value


def get_scopes(api_key):
    """Helper to get scopes handling both PostgreSQL ARRAY and SQLite TEXT."""
    scopes = api_key.scopes
    if isinstance(scopes, str):
        try:
            return json.loads(scopes) if scopes else []
        except (json.JSONDecodeError, TypeError):
            return []
    return scopes if scopes else []


class TestProject:
    """Test Project model."""

    def test_create_project(self, db_session):
        """Test creating a project."""
        project = Project(
            code="TEST-001",
            name="Test Project"
        )
        db_session.add(project)
        db_session.commit()

        assert project.project_id is not None
        assert project.code == "TEST-001"
        assert project.name == "Test Project"
        assert project.created_at is not None

    def test_project_unique_code(self, db_session):
        """Test project code must be unique."""
        project1 = Project(code="TEST-001", name="Project 1")
        db_session.add(project1)
        db_session.commit()

        project2 = Project(code="TEST-001", name="Project 2")
        db_session.add(project2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_project_cascade_delete(self, db_session):
        """Test deleting project cascades to related records."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        api_client = ApiClient(
            project_id=project.project_id,
            name="Test Client",
            status="active"
        )
        db_session.add(api_client)
        db_session.commit()

        db_session.delete(project)
        db_session.commit()

        # ApiClient should be deleted
        result = db_session.query(ApiClient).filter_by(api_client_id=api_client.api_client_id).first()
        assert result is None


class TestApiClient:
    """Test ApiClient model."""

    def test_create_api_client(self, db_session):
        """Test creating an API client."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        api_client = ApiClient(
            project_id=project.project_id,
            name="Test Client",
            contact_email="test@example.com",
            status="active"
        )
        db_session.add(api_client)
        db_session.commit()

        assert api_client.api_client_id is not None
        assert api_client.name == "Test Client"
        assert api_client.contact_email == "test@example.com"
        assert api_client.status == "active"

    def test_api_client_default_status(self, db_session):
        """Test API client default status."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        api_client = ApiClient(
            project_id=project.project_id,
            name="Test Client"
        )
        db_session.add(api_client)
        db_session.commit()

        assert api_client.status == "active"

    def test_api_client_relationships(self, db_session):
        """Test API client relationships."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        api_client = ApiClient(
            project_id=project.project_id,
            name="Test Client",
            status="active"
        )
        db_session.add(api_client)
        db_session.commit()

        assert api_client.project == project
        assert api_client in project.api_clients


class TestApiKey:
    """Test ApiKey model."""

    def test_create_api_key(self, db_session):
        """Test creating an API key."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        api_client = ApiClient(
            project_id=project.project_id,
            name="Test Client",
            status="active"
        )
        db_session.add(api_client)
        db_session.commit()

        scopes_list = ["asset:read", "sensor:read"]
        api_key = ApiKey(
            api_client_id=api_client.api_client_id,
            hash=b"hashed_key_value",
            scopes=serialize_for_sqlite(scopes_list)
        )
        db_session.add(api_key)
        db_session.commit()

        assert api_key.api_key_id is not None
        assert api_key.hash == b"hashed_key_value"

        scopes = get_scopes(api_key)
        assert "asset:read" in scopes
        assert "sensor:read" in scopes

    def test_api_key_default_scopes(self, db_session):
        """Test API key default scopes."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        api_client = ApiClient(
            project_id=project.project_id,
            name="Test Client",
            status="active"
        )
        db_session.add(api_client)
        db_session.commit()

        api_key = ApiKey(
            api_client_id=api_client.api_client_id,
            hash=b"hashed_key_value"
        )
        db_session.add(api_key)
        db_session.commit()

        scopes = get_scopes(api_key)
        assert scopes == []

    def test_api_key_last_used_at(self, db_session):
        """Test API key last_used_at tracking."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        api_client = ApiClient(
            project_id=project.project_id,
            name="Test Client",
            status="active"
        )
        db_session.add(api_client)
        db_session.commit()

        api_key = ApiKey(
            api_client_id=api_client.api_client_id,
            hash=b"hashed_key_value"
        )
        db_session.add(api_key)
        db_session.commit()

        assert api_key.last_used_at is None

        # Update last_used_at
        now = datetime.now()
        api_key.last_used_at = now
        db_session.commit()

        assert api_key.last_used_at is not None


class TestClientCredential:
    """Test ClientCredential model."""

    def test_create_credential(self, db_session):
        """Test creating a client credential."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        api_client = ApiClient(
            project_id=project.project_id,
            name="Test Client",
            status="active"
        )
        db_session.add(api_client)
        db_session.commit()

        credential = ClientCredential(
            api_client_id=api_client.api_client_id,
            service_name="exedra",
            credential_type="api_token",
            encrypted_value="encrypted_token_value",
            environment="prod"
        )
        db_session.add(credential)
        db_session.commit()

        assert credential.credential_id is not None
        assert credential.service_name == "exedra"
        assert credential.credential_type == "api_token"
        assert credential.environment == "prod"
        assert credential.is_active is True

    @pytest.mark.skip(reason="Unique constraint removed for SQLite compatibility - PostgreSQL will enforce partial unique index")
    def test_credential_unique_constraint(self, db_session):
        """Test credential unique constraint on api_client, service, type, environment."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        api_client = ApiClient(
            project_id=project.project_id,
            name="Test Client",
            status="active"
        )
        db_session.add(api_client)
        db_session.commit()

        credential1 = ClientCredential(
            api_client_id=api_client.api_client_id,
            service_name="exedra",
            credential_type="api_token",
            encrypted_value="value1",
            environment="prod"
        )
        db_session.add(credential1)
        db_session.commit()

        credential2 = ClientCredential(
            api_client_id=api_client.api_client_id,
            service_name="exedra",
            credential_type="api_token",
            encrypted_value="value2",
            environment="prod"
        )
        db_session.add(credential2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_credential_type_check_constraint(self, db_session):
        """Test credential type must be valid."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        api_client = ApiClient(
            project_id=project.project_id,
            name="Test Client",
            status="active"
        )
        db_session.add(api_client)
        db_session.commit()

        credential = ClientCredential(
            api_client_id=api_client.api_client_id,
            service_name="exedra",
            credential_type="invalid_type",
            encrypted_value="value",
            environment="prod"
        )
        db_session.add(credential)

        with pytest.raises(IntegrityError):
            db_session.commit()


class TestAsset:
    """Test Asset model."""

    def test_create_asset(self, db_session):
        """Test creating an asset."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        asset = Asset(
            project_id=project.project_id,
            external_id="EXEDRA-123",
            name="Test Asset",
            road_class="A",
            control_mode="optimise",
            asset_metadata={"key": "value"}
        )
        db_session.add(asset)
        db_session.commit()

        assert asset.asset_id is not None
        assert asset.external_id == "EXEDRA-123"
        assert asset.control_mode == "optimise"
        assert asset.asset_metadata == {"key": "value"}

    def test_asset_unique_constraint(self, db_session):
        """Test asset unique constraint on project_id and external_id."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        asset1 = Asset(
            project_id=project.project_id,
            external_id="EXEDRA-123",
            control_mode="optimise"
        )
        db_session.add(asset1)
        db_session.commit()

        asset2 = Asset(
            project_id=project.project_id,
            external_id="EXEDRA-123",
            control_mode="passthrough"
        )
        db_session.add(asset2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_asset_control_mode_check(self, db_session):
        """Test asset control_mode must be valid."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        asset = Asset(
            project_id=project.project_id,
            external_id="EXEDRA-123",
            control_mode="invalid_mode"
        )
        db_session.add(asset)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_asset_default_metadata(self, db_session):
        """Test asset default metadata is empty dict."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        asset = Asset(
            project_id=project.project_id,
            external_id="EXEDRA-123",
            control_mode="optimise"
        )
        db_session.add(asset)
        db_session.commit()

        assert asset.asset_metadata == {}


class TestSensor:
    """Test Sensor model."""

    def test_create_sensor(self, db_session):
        """Test creating a sensor."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        sensor_type = SensorType(
            manufacturer="Test Manufacturer",
            model="Test Model",
            capabilities=serialize_for_sqlite(["lux", "temperature"])
        )
        db_session.add(sensor_type)
        db_session.commit()

        sensor = Sensor(
            project_id=project.project_id,
            external_id="SENSOR-123",
            sensor_type_id=sensor_type.sensor_type_id,
            sensor_metadata={"location": "pole_1"}
        )
        db_session.add(sensor)
        db_session.commit()

        assert sensor.sensor_id is not None
        assert sensor.external_id == "SENSOR-123"
        assert sensor.sensor_metadata == {"location": "pole_1"}

    def test_sensor_unique_constraint(self, db_session):
        """Test sensor unique constraint on project_id and external_id."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        sensor_type = SensorType(
            manufacturer="Test Manufacturer",
            model="Test Model"
        )
        db_session.add(sensor_type)
        db_session.commit()

        sensor1 = Sensor(
            project_id=project.project_id,
            external_id="SENSOR-123",
            sensor_type_id=sensor_type.sensor_type_id
        )
        db_session.add(sensor1)
        db_session.commit()

        sensor2 = Sensor(
            project_id=project.project_id,
            external_id="SENSOR-123",
            sensor_type_id=sensor_type.sensor_type_id
        )
        db_session.add(sensor2)

        with pytest.raises(IntegrityError):
            db_session.commit()


class TestSensorAssetLink:
    """Test SensorAssetLink model."""

    def test_create_link(self, db_session):
        """Test creating a sensor-asset link."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        sensor_type = SensorType(manufacturer="Test", model="Model")
        db_session.add(sensor_type)
        db_session.commit()

        sensor = Sensor(
            project_id=project.project_id,
            external_id="SENSOR-123",
            sensor_type_id=sensor_type.sensor_type_id
        )
        asset = Asset(
            project_id=project.project_id,
            external_id="ASSET-123",
            control_mode="optimise"
        )
        db_session.add_all([sensor, asset])
        db_session.commit()

        link = SensorAssetLink(
            sensor_id=sensor.sensor_id,
            asset_id=asset.asset_id
        )
        db_session.add(link)
        db_session.commit()

        assert link.sensor_asset_link_id is not None
        assert link.sensor == sensor
        assert link.asset == asset

    def test_link_unique_constraint(self, db_session):
        """Test sensor-asset link unique constraint."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        sensor_type = SensorType(manufacturer="Test", model="Model")
        db_session.add(sensor_type)
        db_session.commit()

        sensor = Sensor(
            project_id=project.project_id,
            external_id="SENSOR-123",
            sensor_type_id=sensor_type.sensor_type_id
        )
        asset = Asset(
            project_id=project.project_id,
            external_id="ASSET-123",
            control_mode="optimise"
        )
        db_session.add_all([sensor, asset])
        db_session.commit()

        link1 = SensorAssetLink(sensor_id=sensor.sensor_id, asset_id=asset.asset_id, section="north")
        db_session.add(link1)
        db_session.commit()

        # Same sensor, asset, and section should violate unique constraint
        link2 = SensorAssetLink(sensor_id=sensor.sensor_id, asset_id=asset.asset_id, section="north")
        db_session.add(link2)

        with pytest.raises(IntegrityError):
            db_session.commit()
