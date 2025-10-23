import hashlib
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.db.models import Sensor, Asset, VehicleReading, PedReading, SpeedReading, SensorAssetLink, AuditLog
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
            asset_external_ids=asset_external_ids,
            vendor=sensor.metadata.get("vendor"),
            name=sensor.metadata.get("name"),
            capabilities=sensor.sensor_type.capabilities,
            metadata=sensor.metadata
        )
