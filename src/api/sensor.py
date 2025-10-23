from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from src.core.security import AuthenticatedClient, require_scopes
from src.db.session import get_db
from src.services.sensor_service import SensorService
from src.schemas.sensor import SensorIngestRequest, SensorIngestResponse, SensorResponse

router = APIRouter(prefix="/v1/{project_code}/sensor", tags=["sensor"])


@router.post("/ingest", response_model=SensorIngestResponse)
async def ingest_sensor_data(
    request: SensorIngestRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    client: AuthenticatedClient = Depends(require_scopes("ingest:write")),
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


@router.get("/{external_id}", response_model=SensorResponse)
async def get_sensor(
    external_id: str,
    client: AuthenticatedClient = Depends(require_scopes("metadata:read")),
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
