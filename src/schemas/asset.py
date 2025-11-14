from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

# Asset state schemas
class AssetStateResponse(BaseModel):
    """Current state of an asset"""
    exedra_id: str
    current_dim_percent: Optional[int] = Field(None, ge=0, le=100)
    current_schedule_id: Optional[str] = None
    updated_at: datetime

class AssetResponse(BaseModel):
    """Asset details response"""
    exedra_id: str
    name: Optional[str] = None
    control_mode: str  # "optimise" | "passthrough"
    road_class: Optional[str] = None
    metadata: Dict[str, Any]

class AssetControlModeRequest(BaseModel):
    """Request to change asset control mode"""
    control_mode: str = Field(pattern=r"^(optimise|passthrough)$")

class AssetControlModeResponse(BaseModel):
    """Response for control mode change"""
    exedra_id: str
    control_mode: str
    changed_at: datetime
    changed_by: str

class AssetCreateRequest(BaseModel):
    """Request to create a new asset"""
    exedra_id: str = Field(..., description="EXEDRA device ID (external_id)")
    exedra_name: str = Field(..., description="EXEDRA device name")
    exedra_control_program_id: str = Field(..., description="EXEDRA control program ID")
    exedra_calendar_id: str = Field(..., description="EXEDRA calendar ID")
    control_mode: str = Field(pattern=r"^(optimise|passthrough)$", description="Control mode for the asset")
    road_class: Optional[str] = Field(None, description="Road classification for the asset")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata for the asset")

class AssetCreateResponse(BaseModel):
    """Response for asset creation"""
    asset_id: str
    exedra_id: str
    control_mode: str
    exedra_name: str
    exedra_control_program_id: str
    exedra_calendar_id: str
    road_class: Optional[str]
    metadata: Optional[Dict[str, Any]]
    created_at: datetime

class AssetUpdateRequest(BaseModel):
    """Request to update an asset (excludes external_id which is immutable and control_mode which is a separate endpoint)"""
    exedra_name: Optional[str] = Field(None, description="EXEDRA device name")
    exedra_control_program_id: Optional[str] = Field(None, description="EXEDRA control program ID")
    exedra_calendar_id: Optional[str] = Field(None, description="EXEDRA calendar ID")
    road_class: Optional[str] = Field(None, description="Road classification for the asset")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional asset metadata")

class AssetUpdateResponse(BaseModel):
    """Response for asset update"""
    asset_id: str
    exedra_id: str
    exedra_name: str
    exedra_control_program_id: str
    exedra_calendar_id: str
    road_class: Optional[str]
    metadata: Dict[str, Any]
    updated_at: datetime
