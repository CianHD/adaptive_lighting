"""Root conftest.py for shared test fixtures and configuration."""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Generator
from unittest.mock import MagicMock, Mock

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import JSON, Text, TypeDecorator, create_engine, event, text as sql_text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.elements import TextClause

from src.core.security import hash_api_key
from src.db import models  # pylint: disable=unused-import
from src.db.base import Base
from src.db.models import ApiClient, ApiKey, Asset, Project, Sensor, SensorType
from src.db.session import get_db

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["CREDENTIAL_ENCRYPTION_KEY"] = "test-encryption-key-for-testing-only-32b="
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["EXEDRA_VERIFY_SSL"] = "False"

# Generate proper encryption key
os.environ["CREDENTIAL_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

# Patch TextClause to allow boolean evaluation (workaround for SQLite testing)
# This is needed because SQLAlchemy tries to do `not col.server_default` which fails for TextClause

def _text_clause_bool(self):
    """Allow TextClause to be evaluated as True in boolean context."""
    return True  # TextClause with content is always truthy

TextClause.__bool__ = _text_clause_bool

class ListAsJSON(TypeDecorator):  # pylint: disable=too-many-ancestors
    """Converts Python lists to JSON strings for SQLite."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, list):
            return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError):
                return value
        return value

    def process_literal_param(self, value, dialect):
        return self.process_bind_param(value, dialect)

    @property
    def python_type(self):
        return list

# Fix all PostgreSQL-specific types and defaults for SQLite
for table in Base.metadata.tables.values():
    # Remove unique constraint from client_credential table for SQLite testing
    # (PostgreSQL supports partial unique indexes, SQLite doesn't)
    if table.name == "client_credential":
        # Remove the unique constraint on (api_client_id, service_name, credential_type, environment)
        table.constraints = {c for c in table.constraints if not (
            hasattr(c, 'name') and c.name == 'client_credential_api_client_service_type_env_key'
        )}

    for column in table.columns:
        # Replace ARRAY with custom ListAsJSON type
        if isinstance(column.type, ARRAY):
            column.type = ListAsJSON()
        # Replace JSONB with JSON
        elif isinstance(column.type, JSONB):
            column.type = JSON()

        # Clear UUID server_defaults (tests will provide UUIDs explicitly)
        if column.server_default is not None and isinstance(column.server_default.arg, TextClause):
            DEFAULT_CLAUSE = str(column.server_default.arg)
            if 'gen_random_uuid()' in DEFAULT_CLAUSE.lower():
                column.server_default = None
            elif 'now()' in DEFAULT_CLAUSE.lower():
                # Use CURRENT_TIMESTAMP instead of function call for RETURNING compatibility
                column.server_default = sql_text("CURRENT_TIMESTAMP")

# Now import app (which will use the patched models)
from src.main import app  # pylint: disable=wrong-import-position


# SQLite doesn't support ARRAY, JSONB, or gen_random_uuid()
# Applied type workarounds at module level before mapper configuration
# Tests must provide UUID values explicitly when creating objects


@pytest.fixture(scope="function")
def db_engine():
    """Create a test database engine."""

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Enable foreign key support for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Auto-populate created_at/updated_at timestamps and UUID primary keys for SQLite
    # (server_default doesn't work with RETURNING for timestamps, and we removed UUID generation)
    @event.listens_for(Base, "before_insert", propagate=True)
    def set_defaults(mapper, connection, target):
        # Auto-set UUID primary keys
        for key, column in mapper.columns.items():
            if column.primary_key and str(column.type).startswith('UUID'):
                value = getattr(target, key, None)
                if value is None:
                    setattr(target, key, str(uuid.uuid4()))
        # Auto-set created_at and updated_at timestamps
        now = datetime.now(timezone.utc)
        if hasattr(target, 'created_at') and target.created_at is None:
            target.created_at = now
        if hasattr(target, 'updated_at') and target.updated_at is None:
            target.updated_at = now

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """Create a test database session."""
    testing_session_factory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = testing_session_factory()

    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def client(db_session) -> Generator[TestClient, None, None]:
    """Create a test client with database session override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(test_api_client) -> Dict[str, str]:
    """Generate valid authentication headers for testing."""
    # For testing, we'll just use the API key directly
    return {
        "Authorization": f"Bearer {test_api_client.api_client_id}_test_key"
    }


@pytest.fixture
def test_api_client(db_session):
    """Create a test API client."""
    project_id = str(uuid.uuid4())
    api_client_id = str(uuid.uuid4())

    project = Project(
        project_id=project_id,
        code="test-project",
        name="Test Project"
    )
    api_client = ApiClient(
        api_client_id=api_client_id,
        project_id=project_id,
        name="Test Client",
        contact_email="test@example.com",
        status="active"
    )
    db_session.add_all([project, api_client])
    db_session.commit()

    # Create API key
    raw_key = f"{api_client.api_client_id}_test_key"
    key_hash, salt = hash_api_key(raw_key)

    # For SQLite, serialize scopes as JSON string
    scopes = ["asset:read", "asset:write", "sensor:read", "sensor:write"]
    if db_session.bind.dialect.name == "sqlite":
        scopes = json.dumps(scopes)

    api_key = ApiKey(
        api_client_id=api_client.api_client_id,
        hash=salt + key_hash,  # Store salt + hash
        scopes=scopes
    )
    db_session.add(api_key)
    db_session.commit()

    db_session.refresh(api_client)
    return api_client


@pytest.fixture
def test_asset(db_session, test_api_client):
    """Create a test asset."""
    asset = Asset(
        project_id=test_api_client.project.project_id,
        external_id="test-exedra-id",
        name="Test Asset",
        road_class="A",
        control_mode="optimise",
        asset_metadata={}
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


@pytest.fixture
def test_sensor(db_session, test_asset):
    """Create a test sensor."""
    # For SQLite, serialize capabilities as JSON string
    capabilities = ["lux"]
    if db_session.bind.dialect.name == "sqlite":
        capabilities = json.dumps(capabilities)

    sensor_type = SensorType(
        manufacturer="Test Manufacturer",
        model="Test Model",
        capabilities=capabilities
    )
    sensor = Sensor(
        project_id=test_asset.project_id,
        external_id="test-sensor-external-id",
        sensor_type_id=sensor_type.sensor_type_id,
        sensor_metadata={}
    )
    db_session.add_all([sensor_type, sensor])
    db_session.commit()
    db_session.refresh(sensor)
    return sensor


@pytest.fixture
def mock_exedra_service(monkeypatch):
    """Mock EXEDRA service for testing."""
    mock_service = MagicMock()
    mock_service.get_control_program.return_value = {
        "id": "test-control-program-id",
        "name": "Test Program",
        "commands": []
    }
    mock_service.update_control_program.return_value = True

    monkeypatch.setattr("src.services.exedra_service.ExedraService", mock_service)
    return mock_service


@pytest.fixture
def mock_requests(monkeypatch):
    """Mock requests library for external API calls."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True}
    mock_response.raise_for_status.return_value = None

    mock_get = Mock(return_value=mock_response)
    mock_post = Mock(return_value=mock_response)
    mock_put = Mock(return_value=mock_response)
    mock_delete = Mock(return_value=mock_response)

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.put", mock_put)
    monkeypatch.setattr("requests.delete", mock_delete)

    return {
        "get": mock_get,
        "post": mock_post,
        "put": mock_put,
        "delete": mock_delete,
        "response": mock_response
    }


@pytest.fixture
def sample_command_data():
    """Sample command data for testing."""
    return {
        "time": "18:00:00",
        "intensity": 80,
        "command_type": "dim"
    }


@pytest.fixture
def sample_sensor_data():
    """Sample sensor data for testing."""
    return {
        "sensor_id": "test-sensor-id",
        "sensor_type": "lux",
        "value": 500.0,
        "timestamp": "2025-11-12T10:00:00Z"
    }
