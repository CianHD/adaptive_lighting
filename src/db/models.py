from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy import Integer, BigInteger, String, Text, DateTime, text, ForeignKey, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


# ---------- Core ----------
class Project(Base):
    __tablename__ = "project"
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), server_default=text('now()'))

    api_clients: Mapped[list["ApiClient"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    assets: Mapped[list["Asset"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    sensors: Mapped[list["Sensor"]] = relationship(back_populates="project", cascade="all, delete-orphan")

class ApiClient(Base):
    __tablename__ = "api_client"
    api_client_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    project_id: Mapped[str] = mapped_column(ForeignKey("project.project_id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="active", nullable=False)

    project: Mapped[Project] = relationship(back_populates="api_clients")
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="api_client", cascade="all, delete-orphan")
    credentials: Mapped[list["ClientCredential"]] = relationship(back_populates="api_client", cascade="all, delete-orphan")

class ApiKey(Base):
    __tablename__ = "api_key"
    api_key_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    api_client_id: Mapped[str] = mapped_column(ForeignKey("api_client.api_client_id", ondelete="CASCADE"), nullable=False, index=True)
    hash: Mapped[bytes] = mapped_column()
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    last_used_at: Mapped["datetime | None"] = mapped_column(DateTime(timezone=True))

    api_client: Mapped[ApiClient] = relationship(back_populates="api_keys")

    __table_args__ = (
        Index("api_key_hash_prefix", "hash", postgresql_using="hash"),
    )

class ClientCredential(Base):
    __tablename__ = "client_credential"
    credential_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    api_client_id: Mapped[str] = mapped_column(ForeignKey("api_client.api_client_id", ondelete="CASCADE"), nullable=False, index=True)
    service_name: Mapped[str] = mapped_column(String(50), nullable=False)
    credential_type: Mapped[str] = mapped_column(String(20), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    environment: Mapped[str | None] = mapped_column(String(10))  # 'prod', 'test', 'staging'
    created_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), server_default=text('now()'))
    expires_at: Mapped["datetime | None"] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    api_client: Mapped[ApiClient] = relationship(back_populates="credentials")

    __table_args__ = (
        UniqueConstraint('api_client_id', 'service_name', 'environment', name="client_credential_api_client_service_env_key"),
        Index('client_credential_active', 'api_client_id', 'service_name', 'is_active'),
        Index('client_credential_service', 'service_name', 'environment', postgresql_where=text('is_active = true')),
        CheckConstraint("credential_type in ('api_token','oauth_token','certificate','other','base_url')", name="client_credential_credential_type_check"),
    )


# ---------- Catalogues ----------
class ScopeCatalogue(Base):
    __tablename__ = "scope_catalogue"
    scope_code: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)  # e.g., 'asset', 'sensor', 'admin'

class SensorCapabilityCatalogue(Base):
    __tablename__ = "sensor_capability_catalogue"
    capability_code: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)


# ---------- Models/Sensors/Assets ----------
class SensorType(Base):
    __tablename__ = "sensor_type"
    sensor_type_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    manufacturer: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    firmware_ver: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)

    __table_args__ = (
        UniqueConstraint("manufacturer", "model", name="sensor_type_manufacturer_model_key"),
        Index("sensor_type_capabilities_gin", "capabilities", postgresql_using="gin"),  # GIN for array searches
    )

class Asset(Base):
    __tablename__ = "asset"
    asset_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    project_id: Mapped[str] = mapped_column(ForeignKey("project.project_id", ondelete="CASCADE"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String, nullable=False) # EXEDRA ID (not name)
    name: Mapped[str | None] = mapped_column(String)
    road_class: Mapped[str | None] = mapped_column(String)
    control_mode: Mapped[str] = mapped_column(String, nullable=False)  # 'optimise'|'passthrough'
    asset_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), server_default=text('now()'))
    updated_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), server_default=text('now()'))

    project: Mapped[Project] = relationship(back_populates="assets")
    links: Mapped[list["SensorAssetLink"]] = relationship(back_populates="asset", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("project_id", "external_id", name="asset_project_id_external_id_key"),
        CheckConstraint("control_mode in ('optimise','passthrough')", name="asset_control_mode_check"),
        Index("asset_project_id", "project_id"),
    )

class Sensor(Base):
    __tablename__ = "sensor"
    sensor_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    project_id: Mapped[str] = mapped_column(ForeignKey("project.project_id", ondelete="CASCADE"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    sensor_type_id: Mapped[str] = mapped_column(ForeignKey("sensor_type.sensor_type_id"), nullable=False)
    sensor_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), server_default=text('now()'))
    updated_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), server_default=text('now()'))

    project: Mapped[Project] = relationship(back_populates="sensors")
    sensor_type: Mapped[SensorType] = relationship()
    links: Mapped[list["SensorAssetLink"]] = relationship(back_populates="sensor", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("project_id", "external_id", name="sensor_project_id_external_id_key"),
        Index("sensor_project_id", "project_id"),
    )

class SensorAssetLink(Base):
    __tablename__ = "sensor_asset_link"
    sensor_asset_link_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensor.sensor_id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("asset.asset_id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), server_default=text('now()'))

    sensor: Mapped[Sensor] = relationship(back_populates="links")
    asset: Mapped[Asset] = relationship(back_populates="links")

    __table_args__ = (
        UniqueConstraint("sensor_id", "asset_id", name="sensor_asset_link_sensor_id_asset_id_key"),
        Index("sensor_asset_link_sensor_asset", "sensor_id", "asset_id"),
    )


# ---------- Sensor Readings ----------
class VehicleReading(Base):
    __tablename__ = "vehicle_reading"
    vehicle_reading_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensor.sensor_id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp: Mapped["datetime"] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    veh_count: Mapped[int] = mapped_column(Integer, nullable=False)
    hash_unique: Mapped[bytes] = mapped_column(nullable=False)
    source: Mapped[str | None] = mapped_column(String)

    __table_args__ = (
        UniqueConstraint("sensor_id", "timestamp", name="vehicle_reading_sensor_id_timestamp_key"),
        Index("vehicle_reading_sensor_ts", "sensor_id", "timestamp", postgresql_using=None),
    )

class PedReading(Base):
    __tablename__ = "ped_reading"
    ped_reading_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensor.sensor_id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp: Mapped["datetime"] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ped_count: Mapped[int] = mapped_column(Integer, nullable=False)
    hash_unique: Mapped[bytes] = mapped_column(nullable=False)
    source: Mapped[str | None] = mapped_column(String)

    __table_args__ = (
        UniqueConstraint("sensor_id", "timestamp", name="ped_reading_sensor_id_timestamp_key"),
        Index("ped_reading_sensor_ts", "sensor_id", "timestamp"),
    )

class SpeedReading(Base):
    __tablename__ = "speed_reading"
    speed_reading_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensor.sensor_id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp: Mapped["datetime"] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    avg_speed_kmh: Mapped[float] = mapped_column()
    p85_speed_kmh: Mapped[float | None] = mapped_column()
    hash_unique: Mapped[bytes] = mapped_column(nullable=False)
    source: Mapped[str | None] = mapped_column(String)

    __table_args__ = (
        UniqueConstraint("sensor_id", "timestamp", name="speed_reading_sensor_id_timestamp_key"),
        Index("speed_reading_sensor_ts", "sensor_id", "timestamp"),
    )


# ---------- Commands & Ops ----------
class RealtimeCommand(Base):
    __tablename__ = "realtime_command"
    realtime_command_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    asset_id: Mapped[str] = mapped_column(ForeignKey("asset.asset_id", ondelete="CASCADE"), nullable=False, index=True)
    requested_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    dim_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    source_mode: Mapped[str] = mapped_column(String, nullable=False)  # optimise|passthrough
    vendor: Mapped[str | None] = mapped_column(String)
    algo_version: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False)  # simulated|sent|failed
    response: Mapped[dict | None] = mapped_column(JSONB)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    requested_by_api_client: Mapped[str | None] = mapped_column(ForeignKey("api_client.api_client_id"))
    idempotency_key: Mapped[str | None] = mapped_column(String)  # For proper idempotency support

    __table_args__ = (
        CheckConstraint("dim_percent BETWEEN 0 AND 100", name="realtime_command_dim_percent_check"),
        Index("realtime_cmd_asset_ts", "asset_id", "requested_at"),
        UniqueConstraint("requested_by_api_client", "idempotency_key", name="realtime_command_client_idempotency_key"),
    )

class Schedule(Base):
    __tablename__ = "schedule"
    schedule_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    asset_id: Mapped[str] = mapped_column(ForeignKey("asset.asset_id", ondelete="CASCADE"), nullable=False, index=True)
    exedra_control_program_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # EXEDRA system control program ID
    exedra_calendar_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # EXEDRA system calendar ID
    schedule: Mapped[dict] = mapped_column(JSONB, nullable=False)  # TALQ/CMS-shaped
    provider: Mapped[str] = mapped_column(String, nullable=False)  # ours|vendor
    created_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), server_default=text('now()'))
    status: Mapped[str] = mapped_column(String, nullable=False)  # active|superseded|failed|pending_commission
    commission_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # Number of commission attempts
    last_commission_attempt: Mapped["datetime | None"] = mapped_column(DateTime(timezone=True), nullable=True)  # Last attempt timestamp, updated by service
    commission_error: Mapped[str | None] = mapped_column(Text, nullable=True)  # Last commission error message
    idempotency_key: Mapped[str | None] = mapped_column(String)  # For schedule update idempotency

    __table_args__ = (
        Index("schedule_asset_created", "asset_id", "created_at"),
        Index("schedule_exedra_program_id", "exedra_control_program_id"),
        Index("schedule_exedra_calendar_id", "exedra_calendar_id"),
        Index("schedule_asset_id", "asset_id"),
        Index("schedule_commission_retry", "status", "last_commission_attempt"),  # For retry processing
        Index("schedule_commission_retry_pending", "status", "last_commission_attempt", postgresql_where=text("status = 'pending_commission'")),  # Pending commissions
        Index("schedule_commission_attempts", "commission_attempts", postgresql_where=text("commission_attempts > 0")),  # Monitor attempts
        Index("schedule_commission_status_attempts", "status", "commission_attempts", "last_commission_attempt"),  # Composite for processing
        Index("schedule_commission_failed", "asset_id", "status", "commission_attempts", postgresql_where=text("status = 'failed' AND commission_attempts >= 3")),  # Failed commissions
        UniqueConstraint("asset_id", "idempotency_key", name="schedule_asset_idempotency_key"),
        CheckConstraint("provider in ('ours','vendor','exedra')", name="schedule_provider_check"),
        CheckConstraint("status in ('active','superseded','failed','pending_commission')", name="schedule_status_check"),
    )

class Policy(Base):
    __tablename__ = "policy"
    policy_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    project_id: Mapped[str] = mapped_column(ForeignKey("project.project_id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    active_from: Mapped["datetime"] = mapped_column(DateTime(timezone=True), server_default=text('now()'))

class AuditLog(Base):
    __tablename__ = "audit_log"
    audit_log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped["datetime"] = mapped_column(DateTime(timezone=True), server_default=text('now()'))
    actor: Mapped[str] = mapped_column(String, nullable=False)  # api|system|operator
    project_id: Mapped[str | None] = mapped_column(ForeignKey("project.project_id"))
    action: Mapped[str] = mapped_column(String, nullable=False)
    entity: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        Index("audit_project_ts", "project_id", "timestamp"),
        Index("audit_log_entity_action", "entity", "action"),
        Index("audit_log_timestamp_desc", "timestamp"),
    )
