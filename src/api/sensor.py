from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, DatabaseError, SQLAlchemyError

from src.core.security import AuthenticatedClient, require_scopes
from src.db.session import get_db
from src.services.sensor_service import SensorService
from src.schemas.sensor import SensorIngestRequest, SensorIngestResponse, SensorResponse, SensorCreateRequest, SensorCreateResponse, SensorUpdateRequest, SensorUpdateResponse,SensorTypeCreateRequest, SensorTypeCreateResponse, SensorTypeUpdateRequest, SensorTypeUpdateResponse, SensorTypeResponse

router = APIRouter(prefix="/v1/{project_code}/sensor", tags=["sensor"])

# Sensor Data Endpoint
@router.post("/ingest", response_model=SensorIngestResponse)
async def ingest_sensor_data(
    request: SensorIngestRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    client: AuthenticatedClient = Depends(require_scopes("sensor:ingest")),
    db: Session = Depends(get_db)
):
    """
    Ingest sensor data from external sources.
    
    Accepts vehicle counts, pedestrian counts, and speed data.
    Data is stored in separate tables for performance and clarity.
    Deduplication is handled via unique constraints on sensor_id + timestamp.
    """

    try:
        reading_ids, dedup = SensorService.ingest_sensor_data(
            request=request,
            project_id=client.project.project_id,
            api_client_name=client.api_client.name,
            idempotency_key=idempotency_key,
            db=db
        )

        return SensorIngestResponse(
            reading_ids=reading_ids,
            dedup=dedup,
            timestamp=datetime.now(timezone.utc)
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Data integrity error: {e}"
        ) from e


# Sensor Endpoints
@router.get("/{external_id}", response_model=SensorResponse)
async def get_sensor(
    external_id: str,
    client: AuthenticatedClient = Depends(require_scopes("sensor:metadata")),
    db: Session = Depends(get_db)
):
    """Get sensor details by external ID"""

    try:
        sensor_response = SensorService.get_sensor_details(
            external_id=external_id,
            project_id=client.project.project_id,
            db=db
        )
        return sensor_response

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        ) from e


@router.post("/", response_model=SensorCreateResponse)
async def create_sensor(
    request: SensorCreateRequest,
    client: AuthenticatedClient = Depends(require_scopes("sensor:create")),
    db: Session = Depends(get_db)
):
    """
    Create a new sensor with asset links.
    
    Creates a sensor record and links it to the specified assets.
    """
    try:
        sensor = SensorService.create_sensor(
            external_id=request.external_id,
            project_id=client.project.project_id,
            sensor_type_id=request.sensor_type_id,
            asset_external_ids=request.asset_exedra_ids,
            metadata=request.metadata,
            actor=client.api_client.name,
            db=db
        )

        return SensorCreateResponse(
            sensor_id=sensor.sensor_id,
            external_id=sensor.external_id,
            sensor_type_id=sensor.sensor_type_id,
            linked_assets=request.asset_exedra_ids,
            metadata=sensor.sensor_metadata,
            created_at=sensor.created_at
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
    except RuntimeError as exc:
        # Service layer database errors - don't expose technical details
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create sensor due to a system error"
        ) from exc
    except (IntegrityError, DatabaseError, SQLAlchemyError):
        # Let the error handlers deal with database errors
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create sensor due to an unexpected error"
        ) from e


@router.put("/{external_id}", response_model=SensorUpdateResponse)
async def update_sensor(
    external_id: str,
    request: SensorUpdateRequest,
    client: AuthenticatedClient = Depends(require_scopes("sensor:update")),
    db: Session = Depends(get_db)
):
    """
    Update a sensor's details and asset links.
    
    Updates sensor type, asset links, and metadata.
    """
    try:
        sensor = SensorService.update_sensor(
            external_id=external_id,
            project_id=client.project.project_id,
            sensor_type_id=request.sensor_type_id,
            asset_external_ids=request.asset_exedra_ids,
            metadata=request.metadata,
            actor=client.api_client.name,
            db=db
        )

        # Get current asset links
        linked_assets = []
        if sensor.links:
            for link in sensor.links:
                if link.asset:
                    linked_assets.append(link.asset.external_id)

        return SensorUpdateResponse(
            sensor_id=sensor.sensor_id,
            external_id=sensor.external_id,
            sensor_type_id=sensor.sensor_type_id,
            linked_assets=linked_assets,
            metadata=sensor.sensor_metadata,
            updated_at=sensor.updated_at
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
    except RuntimeError as exc:
        # Service layer database errors - don't expose technical details
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update sensor due to a system error"
        ) from exc
    except (IntegrityError, DatabaseError, SQLAlchemyError):
        # Let the error handlers deal with database errors
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update sensor due to an unexpected error"
        ) from e


@router.delete("/{external_id}")
async def delete_sensor(
    external_id: str,
    client: AuthenticatedClient = Depends(require_scopes("sensor:delete")),
    db: Session = Depends(get_db)
):
    """
    Delete a sensor and its associated data.
    
    Removes the sensor from the system along with all related records.
    This action cannot be undone.
    """
    try:
        SensorService.delete_sensor(
            external_id=external_id,
            project_id=client.project.project_id,
            actor=client.api_client.name,
            db=db
        )

        return {"message": f"Sensor {external_id} deleted successfully"}

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        ) from e
    except RuntimeError as exc:
        # Service layer database errors - don't expose technical details
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete sensor due to a system error"
        ) from exc
    except (IntegrityError, DatabaseError, SQLAlchemyError):
        # Let the error handlers deal with database errors
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete sensor due to an unexpected error"
        ) from e


# Sensor Type Endpoints
@router.get("/type/", response_model=List[SensorTypeResponse])
async def list_sensor_types(
    _client: AuthenticatedClient = Depends(require_scopes("sensor:metadata")),
    db: Session = Depends(get_db)
):
    """
    List all sensor types.
    """
    try:
        sensor_types = SensorService.list_sensor_types(db=db)

        return [
            SensorTypeResponse(
                manufacturer=st.manufacturer,
                model=st.model,
                capabilities=st.capabilities,
                firmware_ver=st.firmware_ver
            )
            for st in sensor_types
        ]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list sensor types due to an unexpected error"
        ) from e


@router.get("/type/{sensor_type_id}", response_model=SensorTypeResponse)
async def get_sensor_type(
    sensor_type_id: str,
    _client: AuthenticatedClient = Depends(require_scopes("sensor:metadata")),
    db: Session = Depends(get_db)
):
    """
    Get a sensor type by ID.
    """
    try:
        sensor_type = SensorService.get_sensor_type(
            sensor_type_id=sensor_type_id,
            db=db
        )

        return SensorTypeResponse(
            manufacturer=sensor_type.manufacturer,
            model=sensor_type.model,
            capabilities=sensor_type.capabilities,
            firmware_ver=sensor_type.firmware_ver
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        ) from e


@router.post("/type", response_model=SensorTypeCreateResponse)
async def create_sensor_type(
    request: SensorTypeCreateRequest,
    client: AuthenticatedClient = Depends(require_scopes("sensor:type:create")),
    db: Session = Depends(get_db)
):
    """
    Create a new sensor type.
    
    Creates a new sensor type with manufacturer, model, and capabilities.
    Sensor types are global and not project-specific.
    """
    try:
        sensor_type = SensorService.create_sensor_type(
            manufacturer=request.manufacturer,
            model=request.model,
            capabilities=request.capabilities,
            firmware_ver=request.firmware_ver,
            notes=request.notes,
            actor=client.api_client.name,
            db=db
        )

        return SensorTypeCreateResponse(
            sensor_type_id=sensor_type.sensor_type_id,
            manufacturer=sensor_type.manufacturer,
            model=sensor_type.model,
            capabilities=sensor_type.capabilities,
            firmware_ver=sensor_type.firmware_ver,
            notes=sensor_type.notes
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
    except RuntimeError as exc:
        # Service layer database errors - don't expose technical details
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create sensor type due to a system error"
        ) from exc
    except (IntegrityError, DatabaseError, SQLAlchemyError):
        # Let the error handlers deal with database errors
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create sensor type due to an unexpected error"
        ) from e


@router.put("/type/{sensor_type_id}", response_model=SensorTypeUpdateResponse)
async def update_sensor_type(
    sensor_type_id: str,
    request: SensorTypeUpdateRequest,
    client: AuthenticatedClient = Depends(require_scopes("sensor:type:update")),
    db: Session = Depends(get_db)
):
    """
    Update a sensor type's details.
    
    Updates capabilities, firmware version, and notes.
    Manufacturer and model cannot be changed as they are the unique identifier.
    """
    try:
        sensor_type = SensorService.update_sensor_type(
            sensor_type_id=sensor_type_id,
            capabilities=request.capabilities,
            firmware_ver=request.firmware_ver,
            notes=request.notes,
            actor=client.api_client.name,
            db=db
        )

        return SensorTypeUpdateResponse(
            sensor_type_id=sensor_type.sensor_type_id,
            manufacturer=sensor_type.manufacturer,
            model=sensor_type.model,
            capabilities=sensor_type.capabilities,
            firmware_ver=sensor_type.firmware_ver,
            notes=sensor_type.notes
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
    except RuntimeError as exc:
        # Service layer database errors - don't expose technical details
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update sensor type due to a system error"
        ) from exc
    except (IntegrityError, DatabaseError, SQLAlchemyError):
        # Let the error handlers deal with database errors
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update sensor type due to an unexpected error"
        ) from e


@router.delete("/type/{sensor_type_id}")
async def delete_sensor_type(
    sensor_type_id: str,
    client: AuthenticatedClient = Depends(require_scopes("sensor:type:delete")),
    db: Session = Depends(get_db)
):
    """
    Delete a sensor type.
    
    Removes the sensor type from the system. This will fail if any sensors
    are still using this sensor type.
    """
    try:
        SensorService.delete_sensor_type(
            sensor_type_id=sensor_type_id,
            actor=client.api_client.name,
            db=db
        )

        return {"message": f"Sensor type {sensor_type_id} deleted successfully"}

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        ) from e
    except IntegrityError as e:
        # Handle foreign key constraint violations
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete sensor type: it is still referenced by existing sensors"
        ) from e
    except (DatabaseError, SQLAlchemyError):
        # Let the error handlers deal with other database errors
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete sensor type due to an unexpected error"
        ) from e
