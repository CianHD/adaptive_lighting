from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# Realtime command schemas
class RealtimeCommandRequest(BaseModel):
    """Request to set immediate dimming level"""
    dim_percent: int = Field(ge=0, le=100)
    duration_minutes: int = Field(ge=1, le=1440)
    note: Optional[str] = None

class RealtimeCommandResponse(BaseModel):
    """Response for realtime command"""
    command_id: str
    status: str  # "accepted", "rejected", "simulated"
    duration_minutes: int
    message: Optional[str] = None
    timestamp: datetime

# Schedule schemas
class ScheduleStep(BaseModel):
    """Individual step in a lighting schedule"""
    time: str  # HH:MM format
    dim: int = Field(ge=0, le=100)

class ScheduleRequest(BaseModel):
    """Request to set a lighting schedule"""
    steps: List[ScheduleStep]
    note: Optional[str] = None

class ScheduleResponse(BaseModel):
    """Current schedule for an asset"""
    schedule_id: str
    steps: List[ScheduleStep]
    provider: str  # "ours" | "vendor"
    status: str  # "active" | "superseded" | "failed"
    updated_at: datetime
