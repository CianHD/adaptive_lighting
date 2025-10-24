from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Header, status
from sqlalchemy.orm import Session

from src.core.security import AuthenticatedClient, require_scopes
from src.db.session import get_db
from src.services.asset_service import AssetService
from src.services.command_service import CommandService
from src.schemas.asset import AssetStateResponse, AssetResponse, AssetControlModeRequest, AssetControlModeResponse
from src.schemas.command import ScheduleResponse, ScheduleStep, ScheduleCommandRequest, RealtimeCommandRequest, RealtimeCommandResponse

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


@router.put("/mode/{external_id}", response_model=AssetControlModeResponse)
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


@router.get("/schedule", response_model=ScheduleResponse)
async def get_asset_schedule(
    asset_external_id: str = Query(..., description="External ID of the asset"),
    client: AuthenticatedClient = Depends(require_scopes("asset:read")),
    db: Session = Depends(get_db)
):
    """
    Get the current schedule for an asset.
    
    This endpoint fetches the live schedule directly from the EXEDRA system
    for compliance validation, ensuring the schedule data reflects what is
    actually active in the lighting control system.
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

    try:
        # Get schedule from EXEDRA and sync to local DB for audit
        schedule_data = AssetService.get_asset_exedra_schedule(asset=asset, db=db)

        return ScheduleResponse(
            schedule_id=schedule_data["schedule_id"],
            steps=[ScheduleStep(**step) for step in schedule_data["steps"]],
            provider=schedule_data["provider"],
            status=schedule_data["status"]
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"EXEDRA service error: {str(e)}"
        ) from e


@router.put("/schedule", response_model=ScheduleResponse)
async def update_asset_schedule(
    request: ScheduleCommandRequest,
    asset_external_id: str = Query(..., description="External ID of the asset"),
    client: AuthenticatedClient = Depends(require_scopes("asset:write")),
    db: Session = Depends(get_db)
):
    """
    Update an asset's schedule.
    
    This endpoint updates the lighting schedule directly in the EXEDRA system.
    All schedule operations go through EXEDRA for compliance validation.
    Schedules are pre-created and associated with assets - this endpoint
    updates the existing schedule rather than creating a new one.
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

    # Validate that the request asset_external_id matches the query parameter
    if request.asset_external_id != asset_external_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Asset external ID in request body must match query parameter"
        )

    try:
        # Convert ScheduleStep objects to dictionaries
        schedule_steps = [{"time": step.time, "dim": step.dim} for step in request.steps]

        # Update schedule in EXEDRA
        schedule_id = AssetService.update_asset_schedule_in_exedra(
            asset=asset,
            schedule_steps=schedule_steps,
            actor=client.api_client.name,
            db=db
        )

        return ScheduleResponse(
            schedule_id=schedule_id,
            steps=request.steps,
            provider="exedra",
            status="active"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"EXEDRA service error: {str(e)}"
        ) from e


@router.post("/realtime", response_model=RealtimeCommandResponse)
async def realtime_command(
    request: RealtimeCommandRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    client: AuthenticatedClient = Depends(require_scopes("command:realtime.write")),
    db: Session = Depends(get_db)
):
    """
    Submit a real-time dimming command for an asset.
    
    Behavior depends on asset control mode:
    - optimise: Requires command:override scope, applies policy guardrails
    - passthrough: Accepts and relays with basic validation only
    """

    # Find the asset
    asset = CommandService.get_asset_by_external_id(
        external_id=request.asset_external_id,
        project_id=client.project.project_id,
        db=db
    )

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {request.asset_external_id} not found"
        )

    # Basic API hygiene validation
    is_valid, error_msg = CommandService.validate_basic_guardrails(asset, request.dim_percent)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    # Mode-specific handling
    if asset.control_mode == "optimise":
        # Require override scope for optimize mode
        if not client.has_scope("command:override"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Optimize mode assets require command:override scope"
            )

        # Apply policy guardrails
        is_valid, error_msg = CommandService.validate_policy_guardrails(asset, request.dim_percent, db)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Policy violation: {error_msg}"
            )

    # Create command using service
    command = CommandService.create_realtime_command(
        request=request,
        asset=asset,
        api_client_id=client.api_client.api_client_id,
        api_client_name=client.api_client.name,
        project_id=client.project.project_id,
        idempotency_key=idempotency_key,
        db=db
    )

    status_msg = "accepted" if asset.control_mode == "passthrough" else "accepted_with_policy"

    return RealtimeCommandResponse(
        command_id=command.realtime_command_id,
        status=status_msg,
        message=f"Command queued for {asset.control_mode} mode relay",
        timestamp=datetime.now(timezone.utc)
    )
