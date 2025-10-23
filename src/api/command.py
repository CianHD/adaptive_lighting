from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from src.core.security import AuthenticatedClient, require_scopes
from src.db.session import get_db
from src.services.command_service import CommandService
from src.schemas.command import RealtimeCommandRequest, RealtimeCommandResponse, ScheduleCommandRequest, ScheduleCommandResponse

router = APIRouter(prefix="/v1/{project_code}/command", tags=["command"])


@router.post("/realtime", response_model=RealtimeCommandResponse)
async def realtime_command(
    request: RealtimeCommandRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    client: AuthenticatedClient = Depends(require_scopes("command:realtime.write")),
    db: Session = Depends(get_db)
):
    """
    Submit a real-time dimming command.
    
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


@router.post("/schedule", response_model=ScheduleCommandResponse)
async def schedule_command(
    request: ScheduleCommandRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    client: AuthenticatedClient = Depends(require_scopes("command:schedule.write")),
    db: Session = Depends(get_db)
):
    """
    Submit a lighting schedule.
    
    Behavior depends on asset control mode:
    - optimise: Requires command:override scope, applies policy validation
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

    # Validate schedule steps
    is_valid, error_msg = CommandService.validate_schedule_steps(request.steps)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    # Mode-specific handling
    if asset.control_mode == "optimise":
        if not client.has_scope("command:override"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Optimize mode assets require command:override scope"
            )
        # Additional policy validation could go here

    # Create schedule using service
    schedule = CommandService.create_schedule_command(
        request=request,
        asset=asset,
        api_client_name=client.api_client.name,
        project_id=client.project.project_id,
        idempotency_key=idempotency_key,
        db=db
    )

    return ScheduleCommandResponse(
        schedule_id=schedule.schedule_id,
        status="accepted",
        message=f"Schedule created for {asset.control_mode} mode relay",
        timestamp=datetime.now(timezone.utc)
    )
