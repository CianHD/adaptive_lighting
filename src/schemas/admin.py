from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

# Policy management
class PolicyRequest(BaseModel):
    """Request to update policy"""
    version: str
    body: Dict[str, Any]  # Contains min_dim, max_dim, max_changes_per_hr, etc.

class PolicyResponse(BaseModel):
    """Policy details response"""
    policy_id: str
    version: str
    body: Dict[str, Any]
    active_from: datetime

# Kill switch
class KillSwitchRequest(BaseModel):
    """Request to enable/disable kill switch"""
    enabled: bool
    reason: Optional[str] = None

class KillSwitchResponse(BaseModel):
    """Kill switch status response"""
    enabled: bool
    reason: Optional[str] = None
    changed_at: datetime
    changed_by: str

# EXEDRA configuration management
class ExedraConfigRequest(BaseModel):
    """Request to store EXEDRA configuration (token + base URL) for a client"""
    api_client_id: str
    api_token: str
    base_url: str
    environment: str = "prod"

class ExedraConfigResponse(BaseModel):
    """Response for EXEDRA configuration operation"""
    token_credential_id: str
    url_credential_id: str
    api_client_id: str
    environment: str
    created_at: datetime

# Audit log
class AuditLogResponse(BaseModel):
    """Audit log entry"""
    audit_log_id: int
    timestamp: datetime
    actor: str
    action: str
    entity: str
    entity_id: str
    details: Dict[str, Any]

# API Key management
class ApiKeyRequest(BaseModel):
    """Request to generate a new API key"""
    api_client_name: str
    scopes: List[str] = ["asset:read"]  # Default to asset read scope

class ApiKeyResponse(BaseModel):
    """Response for API key generation"""
    api_key_id: str
    api_key: str  # The actual key - only returned once!
    api_client_id: str
    api_client_name: str
    scopes: List[str]
    created_at: datetime

# Scope management
class ScopeInfo(BaseModel):
    """Information about a scope"""
    scope_code: str
    description: str
    category: str

class ScopeListResponse(BaseModel):
    """Response for scope catalogue listing"""
    scopes: List[ScopeInfo]
    recommended_combinations: Dict[str, List[str]]
    current_key_scopes: List[str]  # Scopes active for the current API key
