from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, DatabaseError, SQLAlchemyError

from src.core.security import AuthenticatedClient, require_scopes
from src.db.session import get_db
from src.services.admin_service import AdminService
from src.services.scope_service import ScopeService
from src.schemas.admin import PolicyRequest, PolicyResponse, KillSwitchRequest, KillSwitchResponse, AuditLogResponse, ExedraConfigRequest, ExedraConfigResponse, ApiKeyRequest, ApiKeyResponse, CurrentApiKeyResponse, ScopeListResponse, ScopeInfo

router = APIRouter(prefix="/v1/{project_code}/admin", tags=["admin"])


@router.post("/policy", response_model=PolicyResponse)
async def create_policy(
    request: PolicyRequest,
    client: AuthenticatedClient = Depends(require_scopes("admin:policy:create")),
    db: Session = Depends(get_db)
):
    """
    Create a new system policy configuration.
    
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
            detail="Failed to create policy"
        ) from e


@router.put("/policy/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: str,
    request: PolicyRequest,
    client: AuthenticatedClient = Depends(require_scopes("admin:policy:update")),
    db: Session = Depends(get_db)
):
    """
    Update an existing system policy configuration.
    
    Updates the specified policy while maintaining version history.
    """

    try:
        policy = AdminService.update_policy(
            policy_id=policy_id,
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
    client: AuthenticatedClient = Depends(require_scopes("admin:policy:read")),
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
    client: AuthenticatedClient = Depends(require_scopes("admin:killswitch")),
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
    client: AuthenticatedClient = Depends(require_scopes("admin:killswitch")),
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
    client: AuthenticatedClient = Depends(require_scopes("admin:audit")),
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


@router.post("/exedra-config", response_model=ExedraConfigResponse)
async def store_exedra_config(
    request: ExedraConfigRequest,
    client: AuthenticatedClient = Depends(require_scopes("admin:credentials")),
    db: Session = Depends(get_db)
):
    """
    Store complete EXEDRA configuration (API token + base URL) for a client.
    
    This endpoint allows administrators to securely store both EXEDRA API tokens
    and base URLs for clients, enabling them to access their specific EXEDRA tenant's
    lighting control programs.
    """
    try:
        # Store EXEDRA configuration using AdminService
        token_credential_id, url_credential_id, created_at = AdminService.store_exedra_config(
            api_client_id=request.api_client_id,
            api_token=request.api_token,
            base_url=request.base_url,
            project_id=client.project.project_id,
            environment=request.environment,
            db=db
        )

        return ExedraConfigResponse(
            token_credential_id=token_credential_id,
            url_credential_id=url_credential_id,
            api_client_id=request.api_client_id,
            environment=request.environment,
            created_at=created_at
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
    except (IntegrityError, DatabaseError, SQLAlchemyError):
        # Let database errors flow through to global error handlers for proper status codes
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store EXEDRA configuration"
        ) from e


@router.get("/api-key", response_model=CurrentApiKeyResponse)
async def get_current_api_key(
    client: AuthenticatedClient = Depends(require_scopes("admin:apikey:read")),
    _db: Session = Depends(get_db)
):
    """
    Get current API key information and permissions.
    
    Returns the client name and scopes for the API key being used to make this request.
    """
    try:
        return CurrentApiKeyResponse(
            api_client_name=client.api_client.name,
            scopes=client.scopes
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve API key information"
        ) from e


@router.post("/api-key", response_model=ApiKeyResponse)
async def generate_api_key(
    request: ApiKeyRequest,
    client: AuthenticatedClient = Depends(require_scopes("admin:apikey:create")),
    db: Session = Depends(get_db)
):
    """
    Generate a new API key for a client.
    
    This endpoint allows administrators to create API keys for clients within their project.
    The generated API key will be returned only once - store it securely!
    """
    try:
        # Get the API client by name
        api_client = AdminService.get_api_client_by_name(
            project_code=client.project.code,
            client_name=request.api_client_name,
            db=db
        )

        if not api_client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API client '{request.api_client_name}' not found in project '{client.project.code}'"
            )

        # Generate the API key
        api_key_id, raw_api_key = AdminService.generate_api_key(
            api_client_id=api_client.api_client_id,
            project_id=client.project.project_id,
            scopes=request.scopes,
            db=db
        )

        return ApiKeyResponse(
            api_key_id=api_key_id,
            api_key=raw_api_key,
            api_client_id=api_client.api_client_id,
            api_client_name=api_client.name,
            scopes=request.scopes,
            created_at=datetime.now()
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate API key"
        ) from e


@router.put("/api-key/{api_key_id}", response_model=ApiKeyResponse)
async def update_api_key(
    api_key_id: str,
    request: ApiKeyRequest,
    client: AuthenticatedClient = Depends(require_scopes("admin:apikey:update")),
    db: Session = Depends(get_db)
):
    """
    Update an existing API key's scopes and details.
    
    This endpoint allows administrators to modify API key permissions.
    The original API key value remains unchanged.
    """
    try:
        # Update the API key
        updated_key = AdminService.update_api_key(
            api_key_id=api_key_id,
            scopes=request.scopes,
            project_id=client.project.project_id,
            api_client_name=client.api_client.name,
            db=db
        )

        return ApiKeyResponse(
            api_key_id=updated_key.api_key_id,
            api_key="[HIDDEN]",  # Don't return the actual key value
            api_client_id=updated_key.api_client_id,
            api_client_name=updated_key.api_client.name,
            scopes=updated_key.scopes,
            created_at=updated_key.created_at
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update API key"
        ) from e


@router.delete("/api-key/{api_key_id}")
async def delete_api_key(
    api_key_id: str,
    client: AuthenticatedClient = Depends(require_scopes("admin:apikey:delete")),
    db: Session = Depends(get_db)
):
    """
    Revoke and delete an API key.
    
    This endpoint permanently removes an API key, making it invalid for further use.
    This action cannot be undone.
    """
    try:
        AdminService.delete_api_key(
            api_key_id=api_key_id,
            project_id=client.project.project_id,
            api_client_name=client.api_client.name,
            db=db
        )

        return {"message": f"API key {api_key_id} deleted successfully"}

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete API key"
        ) from e


@router.get("/scopes", response_model=ScopeListResponse)
async def list_available_scopes(
    _client: AuthenticatedClient = Depends(require_scopes("admin:apikey:read")),
    db: Session = Depends(get_db)
):
    """
    List all available API scopes and recommended combinations.
    
    This endpoint provides the complete catalogue of available scopes
    for API key generation, along with recommended scope combinations
    for common use cases.
    """
    try:
        # Get scopes from database (single source of truth)
        all_scopes = ScopeService.get_all_scopes(db=db)
        recommended = ScopeService.get_recommended_scopes()

        scope_list = [
            ScopeInfo(
                scope_code=scope_code,
                description=details["description"],
                category=details["category"]
            )
            for scope_code, details in all_scopes.items()
        ]

        return ScopeListResponse(
            scopes=scope_list,
            recommended_combinations=recommended
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve scope catalogue"
        ) from e


@router.post("/scopes/sync")
async def sync_scope_catalogue(
    client: AuthenticatedClient = Depends(require_scopes("admin:apikey:update")),
    db: Session = Depends(get_db)
):
    """
    Sync the scope catalogue to the database.
    
    This endpoint updates the database scope_catalogue table with the latest
    scope definitions from the codebase.
    """
    try:
        count = AdminService.sync_scope_catalogue_with_audit(
            project_id=client.project.project_id,
            api_client_name=client.api_client.name,
            db=db
        )

        return {
            "message": "Scope catalogue synced successfully",
            "scopes_updated": count
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to sync scope catalogue"
        ) from e
