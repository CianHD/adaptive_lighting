import hashlib
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, DatabaseError, SQLAlchemyError

from src.db.models import Sensor, Asset, SensorType, VehicleReading, PedReading, SpeedReading, SensorAssetLink, AuditLog
from src.schemas.sensor import SensorIngestRequest, SensorResponse


class SensorService:
    """Service class for sensor-related business logic"""

    @staticmethod
    def create_reading_hash(sensor_id: str, timestamp: datetime, data: Dict[str, Any]) -> bytes:
        """Create unique hash for deduplication"""
        hash_input = f"{sensor_id}:{timestamp.isoformat()}:{str(sorted(data.items()))}"
        return hashlib.sha256(hash_input.encode()).digest()

    @staticmethod
    def ingest_sensor_data(
        request: SensorIngestRequest,
        project_id: str,
        api_client_name: str,
        idempotency_key: Optional[str],
        db: Session
    ) -> Tuple[Dict[str, str], bool]:
        """
        Ingest sensor data and return reading IDs and dedup status.

        Args:
            request: Sensor data to ingest
            project_id: Project ID for tenant isolation
            api_client_name: Name of API client for audit trail
            idempotency_key: Optional idempotency key
            db: Database session

        Returns:
            Tuple of (reading_ids_dict, dedup_flag)

        Raises:
            ValueError: If sensor not found
            IntegrityError: If database constraints violated
        """
        # Find the sensor
        sensor = db.query(Sensor).filter(
            Sensor.project_id == project_id,
            Sensor.external_id == request.sensor_external_id
        ).first()

        if not sensor:
            raise ValueError(f"Sensor {request.sensor_external_id} not found")

        reading_ids = {}
        dedup = False

        try:
            # Vehicle count data
            if request.vehicle_count is not None:
                vehicle_data = {"vehicle_count": request.vehicle_count}
                if request.p85_vehicle_speed_kmh is not None:
                    vehicle_data["p85_speed_kmh"] = request.p85_vehicle_speed_kmh

                hash_unique = SensorService.create_reading_hash(
                    sensor.sensor_id, request.observed_at, vehicle_data
                )

                vehicle_reading = VehicleReading(
                    sensor_id=sensor.sensor_id,
                    timestamp=request.observed_at,
                    veh_count=request.vehicle_count,
                    hash_unique=hash_unique,
                    source=api_client_name
                )
                db.add(vehicle_reading)
                db.flush()
                reading_ids["vehicle"] = str(vehicle_reading.vehicle_reading_id)

            # Pedestrian count data
            if request.pedestrian_count is not None:
                ped_data = {"pedestrian_count": request.pedestrian_count}
                hash_unique = SensorService.create_reading_hash(
                    sensor.sensor_id, request.observed_at, ped_data
                )

                ped_reading = PedReading(
                    sensor_id=sensor.sensor_id,
                    timestamp=request.observed_at,
                    ped_count=request.pedestrian_count,
                    hash_unique=hash_unique,
                    source=api_client_name
                )
                db.add(ped_reading)
                db.flush()
                reading_ids["pedestrian"] = str(ped_reading.ped_reading_id)

            # Speed data
            if request.avg_vehicle_speed_kmh is not None:
                speed_data = {"avg_speed_kmh": request.avg_vehicle_speed_kmh}
                if request.p85_vehicle_speed_kmh is not None:
                    speed_data["p85_speed_kmh"] = request.p85_vehicle_speed_kmh

                hash_unique = SensorService.create_reading_hash(
                    sensor.sensor_id, request.observed_at, speed_data
                )

                speed_reading = SpeedReading(
                    sensor_id=sensor.sensor_id,
                    timestamp=request.observed_at,
                    avg_speed_kmh=request.avg_vehicle_speed_kmh,
                    p85_speed_kmh=request.p85_vehicle_speed_kmh,
                    hash_unique=hash_unique,
                    source=api_client_name
                )
                db.add(speed_reading)
                db.flush()
                reading_ids["speed"] = str(speed_reading.speed_reading_id)

            # Audit log entry
            audit_entry = AuditLog(
                actor="api",
                project_id=project_id,
                action="sensor_ingest",
                entity="sensor",
                entity_id=sensor.sensor_id,
                details={
                    "sensor_external_id": request.sensor_external_id,
                    "api_client": api_client_name,
                    "reading_types": list(reading_ids.keys()),
                    "timestamp": request.observed_at.isoformat(),
                    "idempotency_key": idempotency_key
                }
            )
            db.add(audit_entry)

            db.commit()

        except IntegrityError as e:
            db.rollback()
            # Check if it's a duplicate reading
            if "uq_" in str(e.orig) and "_sensor_ts" in str(e.orig):
                dedup = True
                reading_ids = {}
            else:
                raise

        return reading_ids, dedup

    @staticmethod
    def get_sensor_details(external_id: str, project_id: str, db: Session) -> SensorResponse:
        """
        Get sensor details including linked assets.

        Args:
            external_id: External ID of the sensor
            project_id: Project ID for tenant isolation
            db: Database session

        Returns:
            SensorResponse with sensor details

        Raises:
            ValueError: If sensor not found
        """
        sensor = db.query(Sensor).filter(
            Sensor.project_id == project_id,
            Sensor.external_id == external_id
        ).first()

        if not sensor:
            raise ValueError(f"Sensor {external_id} not found")

        # Get linked assets
        asset_links = db.query(SensorAssetLink).filter(
            SensorAssetLink.sensor_id == sensor.sensor_id
        ).all()

        asset_external_ids = []
        for link in asset_links:
            asset = db.query(Asset).filter(Asset.asset_id == link.asset_id).first()
            if asset:
                asset_external_ids.append(asset.external_id)

        return SensorResponse(
            external_id=sensor.external_id,
            sensor_type=f"{sensor.sensor_type.manufacturer} {sensor.sensor_type.model}",
            asset_exedra_ids=asset_external_ids,
            vendor=sensor.sensor_metadata.get("vendor"),
            name=sensor.sensor_metadata.get("name"),
            capabilities=sensor.sensor_type.capabilities,
            metadata=sensor.sensor_metadata
        )

    @staticmethod
    def create_sensor(
        external_id: str,
        project_id: str,
        sensor_type_id: str,
        asset_external_ids: List[str],
        metadata: Dict[str, Any],
        actor: str = "unknown",
        db: Session = None
    ) -> Sensor:
        """
        Create a new sensor with asset links.

        Args:
            external_id: External sensor identifier
            project_id: Project ID for tenant isolation
            sensor_type_id: ID of the sensor type
            asset_external_ids: List of asset external IDs to link to
            metadata: Additional sensor metadata
            actor: Who is performing the creation
            db: Database session

        Returns:
            Created Sensor object

        Raises:
            ValueError: If sensor type or assets not found, or sensor already exists
        """
        # Check if sensor already exists
        existing_sensor = db.query(Sensor).filter(
            Sensor.project_id == project_id,
            Sensor.external_id == external_id
        ).first()
        if existing_sensor:
            raise ValueError(f"Sensor with external_id '{external_id}' already exists in this project")

        # Validate sensor type exists
        sensor_type = db.query(SensorType).filter(
            SensorType.sensor_type_id == sensor_type_id
        ).first()
        if not sensor_type:
            raise ValueError(f"Sensor type with ID '{sensor_type_id}' not found")

        # Validate all assets exist in the project
        assets = db.query(Asset).filter(
            Asset.project_id == project_id,
            Asset.external_id.in_(asset_external_ids)
        ).all()

        found_external_ids = {asset.external_id for asset in assets}
        missing_external_ids = set(asset_external_ids) - found_external_ids
        if missing_external_ids:
            raise ValueError(f"Assets not found in this project: {', '.join(missing_external_ids)}")

        try:
            # Create sensor
            sensor = Sensor(
                project_id=project_id,
                external_id=external_id,
                sensor_type_id=sensor_type_id,
                sensor_metadata=metadata or {}
            )
            db.add(sensor)
            db.flush()  # Get the sensor_id

            # Create asset links
            for asset in assets:
                link = SensorAssetLink(
                    sensor_id=sensor.sensor_id,
                    asset_id=asset.asset_id
                )
                db.add(link)

            # Create audit log
            audit_entry = AuditLog(
                actor=actor,
                project_id=project_id,
                action="create_sensor",
                entity="sensor",
                entity_id=sensor.sensor_id,
                details={
                    "external_id": external_id,
                    "sensor_type_id": sensor_type_id,
                    "linked_assets": asset_external_ids,
                    "metadata_fields": list(metadata.keys()) if metadata else []
                }
            )
            db.add(audit_entry)
            db.commit()
            db.refresh(sensor)

        except (IntegrityError, DatabaseError, SQLAlchemyError) as e:
            db.rollback()
            # Check for duplicate sensor
            if "uq_" in str(e.orig) and "external_id" in str(e.orig):
                raise ValueError(f"Sensor with external_id '{external_id}' already exists in this project") from e
            else:
                raise RuntimeError(f"Database error during sensor creation: {str(e)}") from e

        return sensor

    @staticmethod
    def update_sensor(
        external_id: str,
        project_id: str,
        sensor_type_id: Optional[str] = None,
        asset_external_ids: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        actor: str = "unknown",
        db: Session = None
    ) -> Sensor:
        """
        Update a sensor's details and asset links.

        Args:
            external_id: External sensor identifier
            project_id: Project ID for tenant isolation
            sensor_type_id: Updated sensor type ID
            asset_external_ids: Updated list of asset external IDs to link to
            metadata: Updated sensor metadata (merged with existing)
            actor: Who is performing the update
            db: Database session

        Returns:
            Updated Sensor object

        Raises:
            ValueError: If sensor not found or no updates provided
        """
        # Get existing sensor
        sensor = db.query(Sensor).filter(
            Sensor.project_id == project_id,
            Sensor.external_id == external_id
        ).first()

        if not sensor:
            raise ValueError(f"Sensor with external_id '{external_id}' not found in this project")

        # Check if any updates are provided
        if not any([sensor_type_id, asset_external_ids is not None, metadata]):
            raise ValueError("At least one field must be provided for update")

        try:
            # Update sensor type if provided
            if sensor_type_id:
                sensor_type = db.query(SensorType).filter(
                    SensorType.sensor_type_id == sensor_type_id
                ).first()
                if not sensor_type:
                    raise ValueError(f"Sensor type with ID '{sensor_type_id}' not found")
                sensor.sensor_type_id = sensor_type_id

            # Update metadata if provided (merge with existing)
            if metadata is not None:
                current_metadata = sensor.sensor_metadata or {}
                current_metadata.update(metadata)
                sensor.sensor_metadata = current_metadata

            # Update asset links if provided
            if asset_external_ids is not None:
                # Validate all assets exist in the project
                assets = db.query(Asset).filter(
                    Asset.project_id == project_id,
                    Asset.external_id.in_(asset_external_ids)
                ).all()

                found_external_ids = {asset.external_id for asset in assets}
                missing_external_ids = set(asset_external_ids) - found_external_ids
                if missing_external_ids:
                    raise ValueError(f"Assets not found in this project: {', '.join(missing_external_ids)}")

                # Remove existing links
                db.query(SensorAssetLink).filter(
                    SensorAssetLink.sensor_id == sensor.sensor_id
                ).delete()

                # Create new links
                for asset in assets:
                    link = SensorAssetLink(
                        sensor_id=sensor.sensor_id,
                        asset_id=asset.asset_id
                    )
                    db.add(link)

            # Create audit log
            audit_entry = AuditLog(
                actor=actor,
                project_id=project_id,
                action="update_sensor",
                entity="sensor",
                entity_id=sensor.sensor_id,
                details={
                    "external_id": external_id,
                    "updated_fields": {
                        "sensor_type_id": sensor_type_id,
                        "asset_links_updated": asset_external_ids is not None,
                        "metadata_updated": metadata is not None
                    }
                }
            )
            db.add(audit_entry)
            db.commit()
            db.refresh(sensor)

        except (IntegrityError, DatabaseError, SQLAlchemyError) as e:
            db.rollback()
            raise RuntimeError(f"Database error during sensor update: {str(e)}") from e

        return sensor

    @staticmethod
    def delete_sensor(
        external_id: str,
        project_id: str,
        actor: str = "unknown",
        db: Session = None
    ) -> bool:
        """
        Delete a sensor and its associated data.

        Args:
            external_id: External sensor identifier
            project_id: Project ID for tenant isolation
            actor: Who is performing the deletion
            db: Database session

        Returns:
            True if deletion was successful

        Raises:
            ValueError: If sensor not found
        """
        # Get existing sensor
        sensor = db.query(Sensor).filter(
            Sensor.project_id == project_id,
            Sensor.external_id == external_id
        ).first()

        if not sensor:
            raise ValueError(f"Sensor with external_id '{external_id}' not found in this project")

        sensor_id = sensor.sensor_id

        try:
            # Log the deletion before actually deleting
            audit_entry = AuditLog(
                actor=actor,
                project_id=project_id,
                action="delete_sensor",
                entity="sensor",
                entity_id=sensor_id,
                details={
                    "external_id": external_id,
                    "sensor_type": f"{sensor.sensor_type.manufacturer} {sensor.sensor_type.model}"
                }
            )
            db.add(audit_entry)

            # Delete the sensor (cascade will handle related records)
            db.delete(sensor)
            db.commit()

        except (IntegrityError, DatabaseError, SQLAlchemyError) as e:
            db.rollback()
            raise RuntimeError(f"Database error during sensor deletion: {str(e)}") from e

        return True


class SensorTypeService:
    """Service class for sensor type CRUD operations"""

    @staticmethod
    def create_sensor_type(
        manufacturer: str,
        model: str,
        capabilities: List[str],
        firmware_ver: Optional[str] = None,
        notes: Optional[str] = None,
        actor: str = "unknown",
        db: Session = None
    ) -> SensorType:
        """
        Create a new sensor type.

        Args:
            manufacturer: Sensor manufacturer
            model: Sensor model
            capabilities: List of sensor capabilities
            firmware_ver: Firmware version
            notes: Additional notes
            actor: Who is performing the creation
            db: Database session

        Returns:
            Created SensorType object

        Raises:
            ValueError: If sensor type already exists
        """
        # Check if sensor type already exists
        existing_sensor_type = db.query(SensorType).filter(
            SensorType.manufacturer == manufacturer,
            SensorType.model == model
        ).first()
        if existing_sensor_type:
            raise ValueError(f"Sensor type with manufacturer '{manufacturer}' and model '{model}' already exists")

        try:
            # Create sensor type
            sensor_type = SensorType(
                manufacturer=manufacturer,
                model=model,
                capabilities=capabilities,
                firmware_ver=firmware_ver,
                notes=notes
            )
            db.add(sensor_type)
            db.flush()  # Get the sensor_type_id

            # Create audit log
            audit_entry = AuditLog(
                actor=actor,
                project_id=None,  # Sensor types are global
                action="create_sensor_type",
                entity="sensor_type",
                entity_id=sensor_type.sensor_type_id,
                details={
                    "manufacturer": manufacturer,
                    "model": model,
                    "capabilities": capabilities,
                    "firmware_ver": firmware_ver,
                    "notes": notes
                }
            )
            db.add(audit_entry)
            db.commit()
            db.refresh(sensor_type)

        except (IntegrityError, DatabaseError, SQLAlchemyError) as e:
            db.rollback()
            # Check for duplicate sensor type
            if "uq_" in str(e.orig) and ("manufacturer" in str(e.orig) or "model" in str(e.orig)):
                raise ValueError(f"Sensor type with manufacturer '{manufacturer}' and model '{model}' already exists") from e
            else:
                raise RuntimeError(f"Database error during sensor type creation: {str(e)}") from e

        return sensor_type

    @staticmethod
    def update_sensor_type(
        sensor_type_id: str,
        capabilities: Optional[List[str]] = None,
        firmware_ver: Optional[str] = None,
        notes: Optional[str] = None,
        actor: str = "unknown",
        db: Session = None
    ) -> SensorType:
        """
        Update a sensor type's details.

        Args:
            sensor_type_id: ID of the sensor type to update
            capabilities: Updated list of sensor capabilities
            firmware_ver: Updated firmware version
            notes: Updated notes
            actor: Who is performing the update
            db: Database session

        Returns:
            Updated SensorType object

        Raises:
            ValueError: If sensor type not found or no updates provided
        """
        # Get existing sensor type
        sensor_type = db.query(SensorType).filter(
            SensorType.sensor_type_id == sensor_type_id
        ).first()

        if not sensor_type:
            raise ValueError(f"Sensor type with ID '{sensor_type_id}' not found")

        # Check if any updates are provided
        if not any([capabilities is not None, firmware_ver is not None, notes is not None]):
            raise ValueError("At least one field must be provided for update")

        try:
            # Update fields
            if capabilities is not None:
                sensor_type.capabilities = capabilities
            if firmware_ver is not None:
                sensor_type.firmware_ver = firmware_ver
            if notes is not None:
                sensor_type.notes = notes

            # Create audit log
            audit_entry = AuditLog(
                actor=actor,
                project_id=None,  # Sensor types are global
                action="update_sensor_type",
                entity="sensor_type",
                entity_id=sensor_type.sensor_type_id,
                details={
                    "manufacturer": sensor_type.manufacturer,
                    "model": sensor_type.model,
                    "updated_fields": {
                        "capabilities": capabilities,
                        "firmware_ver": firmware_ver,
                        "notes": notes
                    }
                }
            )
            db.add(audit_entry)
            db.commit()
            db.refresh(sensor_type)

        except (IntegrityError, DatabaseError, SQLAlchemyError) as e:
            db.rollback()
            raise RuntimeError(f"Database error during sensor type update: {str(e)}") from e

        return sensor_type

    @staticmethod
    def delete_sensor_type(
        sensor_type_id: str,
        actor: str = "unknown",
        db: Session = None
    ) -> bool:
        """
        Delete a sensor type.

        Args:
            sensor_type_id: ID of the sensor type to delete
            actor: Who is performing the deletion
            db: Database session

        Returns:
            True if deletion was successful

        Raises:
            ValueError: If sensor type not found
            IntegrityError: If sensor type is still referenced by sensors
        """
        # Get existing sensor type
        sensor_type = db.query(SensorType).filter(
            SensorType.sensor_type_id == sensor_type_id
        ).first()

        if not sensor_type:
            raise ValueError(f"Sensor type with ID '{sensor_type_id}' not found")

        try:
            # Log the deletion before actually deleting
            audit_entry = AuditLog(
                actor=actor,
                project_id=None,  # Sensor types are global
                action="delete_sensor_type",
                entity="sensor_type",
                entity_id=sensor_type_id,
                details={
                    "manufacturer": sensor_type.manufacturer,
                    "model": sensor_type.model,
                    "capabilities": sensor_type.capabilities
                }
            )
            db.add(audit_entry)

            # Delete the sensor type
            db.delete(sensor_type)
            db.commit()

        except (IntegrityError, DatabaseError, SQLAlchemyError) as e:
            db.rollback()
            # Check if sensor type is still referenced
            if "foreign key constraint" in str(e.orig).lower():
                raise ValueError("Cannot delete sensor type: it is still referenced by existing sensors") from e
            else:
                raise RuntimeError(f"Database error during sensor type deletion: {str(e)}") from e

        return True

    @staticmethod
    def get_sensor_type(sensor_type_id: str, db: Session = None) -> SensorType:
        """
        Get a sensor type by ID.

        Args:
            sensor_type_id: ID of the sensor type
            db: Database session

        Returns:
            SensorType object

        Raises:
            ValueError: If sensor type not found
        """
        sensor_type = db.query(SensorType).filter(
            SensorType.sensor_type_id == sensor_type_id
        ).first()

        if not sensor_type:
            raise ValueError(f"Sensor type with ID '{sensor_type_id}' not found")

        return sensor_type

    @staticmethod
    def list_sensor_types(db: Session = None) -> List[SensorType]:
        """
        List all sensor types.

        Args:
            db: Database session

        Returns:
            List of SensorType objects
        """
        return db.query(SensorType).all()


# Add convenience methods to SensorService for sensor type operations
SensorService.create_sensor_type = SensorTypeService.create_sensor_type
SensorService.update_sensor_type = SensorTypeService.update_sensor_type
SensorService.delete_sensor_type = SensorTypeService.delete_sensor_type
SensorService.get_sensor_type = SensorTypeService.get_sensor_type
SensorService.list_sensor_types = SensorTypeService.list_sensor_types
