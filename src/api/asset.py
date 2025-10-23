from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.core.security import AuthenticatedClient, require_scopes
from src.db.session import get_db
from src.services.asset_service import AssetService
from src.schemas.asset import AssetStateResponse, AssetResponse, AssetControlModeRequest, AssetControlModeResponse
from src.schemas.command import ScheduleResponse

router = APIRouter(prefix="/v1/{project_code}/asset", tags=["asset"])


@router.get("/state", response_model=AssetStateResponse)
async def get_asset_state(
    asset_external_id: str = Query(..., description="External ID of the asset"),
    client: AuthenticatedClient = Depends(require_scopes("asset:read")),
    db: Session = Depends(get_db)
):
    """
    Get current state of an asset including dimming level and active schedule.
    
    This is a validation endpoint for checking asset state.
    """

    # Find the asset
    asset = AssetService.get_asset_by_external_id(
        external_id=asset_external_id,
        project_id=client.project.project_id,
        db=db
    )

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_external_id} not found"
        )

    # Get asset state using service
    asset_state = AssetService.get_asset_state(asset=asset, db=db)
    return asset_state


@router.get("/schedule", response_model=ScheduleResponse)
async def get_asset_schedule(
    asset_external_id: str = Query(..., description="External ID of the asset"),
    client: AuthenticatedClient = Depends(require_scopes("asset:read")),
    db: Session = Depends(get_db)
):
    """
    Get current active schedule for an asset.
    """

    # Find the asset
    asset = AssetService.get_asset_by_external_id(
        external_id=asset_external_id,
        project_id=client.project.project_id,
        db=db
    )

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_external_id} not found"
        )

    # Get schedule using service
    schedule_response = AssetService.get_asset_schedule(asset=asset, db=db)

    if not schedule_response:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active schedule found for asset {asset_external_id}"
        )

    return schedule_response


@router.get("/{external_id}", response_model=AssetResponse)
async def get_asset(
    external_id: str,
    client: AuthenticatedClient = Depends(require_scopes("metadata:read")),
    db: Session = Depends(get_db)
):
    """Get asset details by external ID"""

    asset = AssetService.get_asset_by_external_id(
        external_id=external_id,
        project_id=client.project.project_id,
        db=db
    )

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {external_id} not found"
        )

    # Get asset details using service
    asset_response = AssetService.get_asset_details(asset=asset)
    return asset_response


@router.put("/{external_id}/mode", response_model=AssetControlModeResponse)
async def update_asset_control_mode(
    external_id: str,
    request: AssetControlModeRequest,
    client: AuthenticatedClient = Depends(require_scopes("config:write")),
    db: Session = Depends(get_db)
):
    """
    Change asset control mode between 'optimise' and 'passthrough'.
    
    This is an operations endpoint with immediate effect on subsequent commands.
    """

    # Find the asset
    asset = AssetService.get_asset_by_external_id(
        external_id=external_id,
        project_id=client.project.project_id,
        db=db
    )

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {external_id} not found"
        )

    # Update control mode using service
    updated_asset = AssetService.update_control_mode(
        asset=asset,
        new_mode=request.control_mode,
        api_client_name=client.api_client.name,
        project_id=client.project.project_id,
        db=db
    )

    return AssetControlModeResponse(
        asset_external_id=external_id,
        control_mode=updated_asset.control_mode,
        changed_at=datetime.now(timezone.utc),
        changed_by=client.api_client.name
    )
