from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

# Asset state schemas
class AssetStateResponse(BaseModel):
    """Current state of an asset"""
    asset_external_id: str
    current_dim_percent: Optional[int] = Field(None, ge=0, le=100)
    current_schedule_id: Optional[str] = None
    updated_at: datetime

class AssetResponse(BaseModel):
    """Asset details response"""
    external_id: str
    name: Optional[str] = None
    control_mode: str  # "optimise" | "passthrough"
    road_class: Optional[str] = None
    metadata: Dict[str, Any]

class AssetControlModeRequest(BaseModel):
    """Request to change asset control mode"""
    control_mode: str = Field(pattern=r"^(optimise|passthrough)$")

class AssetControlModeResponse(BaseModel):
    """Response for control mode change"""
    asset_external_id: str
    control_mode: str
    changed_at: datetime
    changed_by: str
