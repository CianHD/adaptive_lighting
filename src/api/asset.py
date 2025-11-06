from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, DatabaseError, SQLAlchemyError

from src.core.security import AuthenticatedClient, require_scopes
from src.db.session import get_db
from src.services.asset_service import AssetService
from src.schemas.asset import AssetStateResponse, AssetResponse, AssetControlModeRequest, AssetControlModeResponse, AssetCreateRequest, AssetCreateResponse, AssetUpdateRequest, AssetUpdateResponse
from src.schemas.command import ScheduleResponse, ScheduleStep, ScheduleRequest, RealtimeCommandRequest, RealtimeCommandResponse

router = APIRouter(prefix="/v1/{project_code}/asset", tags=["asset"])


@router.get("/{exedra_id}", response_model=AssetResponse)
async def get_asset(
    exedra_id: str,
    client: AuthenticatedClient = Depends(require_scopes("asset:metadata")),
    db: Session = Depends(get_db)
):
    """Get asset details by EXEDRA device ID"""

    asset = AssetService.get_asset_by_external_id(
        external_id=exedra_id,
        project_id=client.project.project_id,
        db=db
    )

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {exedra_id} not found"
        )

    # Get asset details using service
    asset_response = AssetService.get_asset_details(asset=asset)
    return asset_response


@router.post("/", response_model=AssetCreateResponse)
async def create_asset(
    request: AssetCreateRequest,
    client: AuthenticatedClient = Depends(require_scopes("asset:create")),
    db: Session = Depends(get_db)
):
    """
    Create a new asset with EXEDRA integration.
    
    Creates an asset record with the provided EXEDRA ID as the external_id,
    stores the EXEDRA device name in the name column, and initializes a 
    schedule record with the provided control program and calendar IDs.
    """
    try:
        asset = AssetService.create_asset(
            project_id=client.project.project_id,
            external_id=request.exedra_id,
            control_mode=request.control_mode,
            exedra_name=request.exedra_name,
            exedra_control_program_id=request.exedra_control_program_id,
            exedra_calendar_id=request.exedra_calendar_id,
            actor=client.api_client.name,
            db=db
        )

        return AssetCreateResponse(
            asset_id=asset.asset_id,
            exedra_id=asset.external_id,
            control_mode=asset.control_mode,
            exedra_name=asset.name,
            exedra_control_program_id=asset.asset_metadata["exedra_control_program_id"],
            exedra_calendar_id=asset.asset_metadata["exedra_calendar_id"],
            created_at=asset.created_at
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
    except RuntimeError as e:
        # Service layer database errors - don't expose technical details
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create asset due to a system error"
        ) from e
    except (IntegrityError, DatabaseError, SQLAlchemyError):
        # Let the error handlers deal with database errors
        # Don't wrap them in HTTPException to avoid exposing technical details
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create asset due to an unexpected error"
        ) from e


@router.put("/{exedra_id}", response_model=AssetUpdateResponse)
async def update_asset(
    exedra_id: str,
    request: AssetUpdateRequest,
    client: AuthenticatedClient = Depends(require_scopes("asset:update")),
    db: Session = Depends(get_db)
):
    """
    Update an asset's details.
    
    Updates EXEDRA device information and metadata. The exedra_id (EXEDRA device ID)
    cannot be changed as it's the immutable identifier for the device.
    """
    try:
        asset = AssetService.update_asset(
            external_id=exedra_id,
            project_id=client.project.project_id,
            exedra_name=request.exedra_name,
            exedra_control_program_id=request.exedra_control_program_id,
            exedra_calendar_id=request.exedra_calendar_id,
            metadata=request.metadata,
            actor=client.api_client.name,
            db=db
        )

        return AssetUpdateResponse(
            asset_id=asset.asset_id,
            exedra_id=asset.external_id,
            exedra_name=asset.name,
            exedra_control_program_id=asset.asset_metadata.get("exedra_control_program_id"),
            exedra_calendar_id=asset.asset_metadata.get("exedra_calendar_id"),
            metadata=asset.asset_metadata,
            updated_at=asset.updated_at
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
    except RuntimeError as e:
        # Service layer database errors - don't expose technical details
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update asset due to a system error"
        ) from e
    except (IntegrityError, DatabaseError, SQLAlchemyError):
        # Let the error handlers deal with database errors
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update asset due to an unexpected error"
        ) from e


@router.delete("/{exedra_id}")
async def delete_asset(
    exedra_id: str,
    client: AuthenticatedClient = Depends(require_scopes("asset:delete")),
    db: Session = Depends(get_db)
):
    """
    Delete an asset and its associated data.
    
    Removes the asset from the system along with all related records.
    This action cannot be undone.
    """
    try:
        AssetService.delete_asset(
            external_id=exedra_id,
            project_id=client.project.project_id,
            actor=client.api_client.name,
            db=db
        )

        return {"message": f"Asset {exedra_id} deleted successfully"}

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        ) from e
    except RuntimeError as e:
        # Service layer database errors - don't expose technical details
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete asset due to a system error"
        ) from e
    except (IntegrityError, DatabaseError, SQLAlchemyError):
        # Let the error handlers deal with database errors
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete asset due to an unexpected error"
        ) from e


# Asset Schedule Endpoints
@router.get("/schedule/{exedra_id}", response_model=ScheduleResponse)
async def get_asset_schedule(
    exedra_id: str,
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
        external_id=exedra_id,
        project_id=client.project.project_id,
        db=db
    )

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {exedra_id} not found"
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


@router.put("/schedule/{exedra_id}", response_model=ScheduleResponse)
async def update_asset_schedule(
    exedra_id: str,
    request: ScheduleRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    client: AuthenticatedClient = Depends(require_scopes("asset:command")),
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
        external_id=exedra_id,
        project_id=client.project.project_id,
        db=db
    )

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {exedra_id} not found"
        )

    try:
        # Convert ScheduleStep objects to dictionaries
        schedule_steps = [{"time": step.time, "dim": step.dim} for step in request.steps]

        # Update schedule in EXEDRA
        schedule_id = AssetService.update_asset_schedule_in_exedra(
            asset=asset,
            schedule_steps=schedule_steps,
            actor=client.api_client.name,
            idempotency_key=idempotency_key,
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


# Asset State Endpoints
@router.get("/state/{exedra_id}", response_model=AssetStateResponse)
async def get_asset_state(
    exedra_id: str,
    client: AuthenticatedClient = Depends(require_scopes("asset:read")),
    db: Session = Depends(get_db)
):
    """
    Get current state of an asset including dimming level and active schedule.
    
    This is a validation endpoint for checking asset state by EXEDRA device ID.
    """

    # Find the asset
    asset = AssetService.get_asset_by_external_id(
        external_id=exedra_id,
        project_id=client.project.project_id,
        db=db
    )

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {exedra_id} not found"
        )

    # Get asset state using service
    asset_state = AssetService.get_asset_state(asset=asset, db=db)
    return asset_state


@router.post("/realtime/{exedra_id}", response_model=RealtimeCommandResponse)
async def realtime_command(
    exedra_id: str,
    request: RealtimeCommandRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    client: AuthenticatedClient = Depends(require_scopes("asset:command")),
    db: Session = Depends(get_db)
):
    """
    Submit a real-time dimming command for an asset.
    
    Behavior depends on asset control mode:
    - optimise: Requires command:override scope, applies policy guardrails
    - passthrough: Accepts and relays with basic validation only
    """

    # Find the asset
    asset = AssetService.get_asset_by_external_id(
        external_id=exedra_id,
        project_id=client.project.project_id,
        db=db
    )

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {exedra_id} not found"
        )

    # Basic API hygiene validation
    is_valid, error_msg = AssetService.validate_basic_guardrails(asset, request.dim_percent)
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
        is_valid, error_msg = AssetService.validate_policy_guardrails(asset, request.dim_percent, db)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Policy violation: {error_msg}"
            )

    # Create command using service
    command_id = AssetService.create_realtime_command(
        request=request,
        asset=asset,
        api_client_id=client.api_client.api_client_id,
        api_client_name=client.api_client.name,
        idempotency_key=idempotency_key,
        db=db
    )

    status_msg = "accepted" if asset.control_mode == "passthrough" else "accepted_with_policy"

    return RealtimeCommandResponse(
        command_id=command_id,
        status=status_msg,
        message=f"Command queued for {asset.control_mode} mode relay",
        timestamp=datetime.now(timezone.utc)
    )


# Asset Control Endpoints
@router.put("/mode/{exedra_id}", response_model=AssetControlModeResponse)
async def update_asset_control_mode(
    exedra_id: str,
    request: AssetControlModeRequest,
    client: AuthenticatedClient = Depends(require_scopes("asset:update")),
    db: Session = Depends(get_db)
):
    """
    Change asset control mode between 'optimise' and 'passthrough'.
    
    This is an operations endpoint with immediate effect on subsequent commands.
    """

    # Find the asset
    asset = AssetService.get_asset_by_external_id(
        external_id=exedra_id,
        project_id=client.project.project_id,
        db=db
    )

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {exedra_id} not found"
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
        exedra_id=exedra_id,
        control_mode=updated_asset.control_mode,
        changed_at=datetime.now(timezone.utc),
        changed_by=client.api_client.name
    )
