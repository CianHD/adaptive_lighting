from pydantic import BaseModel
from typing import Optional, Dict, Any
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
