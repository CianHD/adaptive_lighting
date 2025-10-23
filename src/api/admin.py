from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.core.security import AuthenticatedClient, require_scopes
from src.db.session import get_db
from src.services.admin_service import AdminService
from src.schemas.admin import PolicyRequest, PolicyResponse, KillSwitchRequest, KillSwitchResponse, AuditLogResponse

router = APIRouter(prefix="/v1/{project_code}/admin", tags=["admin"])


@router.post("/policy", response_model=PolicyResponse)
async def update_policy(
    request: PolicyRequest,
    client: AuthenticatedClient = Depends(require_scopes("admin")),
    db: Session = Depends(get_db)
):
    """
    Update the system policy configuration.
    
    Policy controls dimming limits, rate limits, and other operational parameters.
    Only one policy can be active at a time. Previous policies are archived.
    """

    try:
        policy = AdminService.create_policy(
            request=request,
            project_id=client.project.project_id,
            api_client_name=client.api_client.name,
            db=db
        )

        return PolicyResponse(
            policy_id=str(policy.policy_id),
            version=policy.version,
            body=policy.body,
            active_from=policy.active_from
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update policy"
        ) from e


@router.get("/policy", response_model=PolicyResponse)
async def get_current_policy(
    client: AuthenticatedClient = Depends(require_scopes("admin")),
    db: Session = Depends(get_db)
):
    """
    Get the currently active policy configuration.
    
    Returns the latest policy version with all configuration parameters.
    """

    policy = AdminService.get_current_policy(
        project_id=client.project.project_id,
        db=db
    )
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active policy found"
        )

    return PolicyResponse(
        policy_id=str(policy.policy_id),
        version=policy.version,
        body=policy.body,
        active_from=policy.active_from
    )


@router.post("/kill-switch", response_model=KillSwitchResponse)
async def toggle_kill_switch(
    request: KillSwitchRequest,
    client: AuthenticatedClient = Depends(require_scopes("admin")),
    db: Session = Depends(get_db)
):
    """
    Enable or disable the system kill switch.
    
    When enabled, all asset commands are blocked regardless of mode.
    This is an emergency feature for system-wide control suspension.
    """

    try:
        audit_entry = AdminService.toggle_kill_switch(
            enabled=request.enabled,
            reason=request.reason,
            project_id=client.project.project_id,
            api_client_name=client.api_client.name,
            db=db
        )

        return KillSwitchResponse(
            enabled=request.enabled,
            reason=request.reason,
            changed_at=audit_entry.timestamp,
            changed_by=audit_entry.actor
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to toggle kill switch"
        ) from e


@router.get("/kill-switch", response_model=KillSwitchResponse)
async def get_kill_switch_status(
    client: AuthenticatedClient = Depends(require_scopes("admin")),
    db: Session = Depends(get_db)
):
    """
    Get the current kill switch status.
    
    Returns whether the kill switch is currently enabled and when it was last changed.
    """

    enabled, reason, changed_at, changed_by = AdminService.get_kill_switch_status(
        project_id=client.project.project_id,
        db=db
    )

    return KillSwitchResponse(
        enabled=enabled,
        reason=reason,
        changed_at=changed_at,
        changed_by=changed_by
    )


@router.get("/audit-logs", response_model=List[AuditLogResponse])
async def get_audit_logs(
    limit: Optional[int] = Query(100, description="Maximum number of logs to return", ge=1, le=1000),
    offset: Optional[int] = Query(0, description="Number of logs to skip", ge=0),
    client: AuthenticatedClient = Depends(require_scopes("admin")),
    db: Session = Depends(get_db)
):
    """
    Get system audit logs with pagination.
    
    Returns administrative actions including policy changes and kill switch toggles.
    Logs are returned in descending chronological order (newest first).
    """

    logs = AdminService.get_audit_logs(
        project_id=client.project.project_id,
        limit=limit,
        offset=offset,
        entity_filter=None,
        action_filter=None,
        db=db
    )
    return [
        AuditLogResponse(
            audit_log_id=log.audit_log_id,
            timestamp=log.timestamp,
            actor=log.actor,
            action=log.action,
            entity=log.entity,
            entity_id=log.entity_id,
            details=log.details
        )
        for log in logs
    ]
