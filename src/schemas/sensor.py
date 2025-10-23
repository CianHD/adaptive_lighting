from pydantic import BaseModel, Field, NonNegativeInt
from typing import Optional, List, Dict, Any
from datetime import datetime

# Sensor data ingestion
class SensorIngestRequest(BaseModel):
    """Unified sensor data ingestion payload"""
    sensor_external_id: str
    observed_at: datetime
    vehicle_count: Optional[NonNegativeInt] = None
    pedestrian_count: Optional[NonNegativeInt] = None
    avg_vehicle_speed_kmh: Optional[float] = Field(None, ge=0)
    p85_vehicle_speed_kmh: Optional[float] = Field(None, ge=0)

class SensorIngestResponse(BaseModel):
    """Response for sensor data ingestion"""
    reading_ids: Dict[str, str]  # reading_type -> reading_id
    dedup: bool
    timestamp: datetime

# Sensor metadata
class SensorResponse(BaseModel):
    """Sensor details response"""
    external_id: str
    sensor_type: str
    asset_external_ids: List[str]
    vendor: Optional[str] = None
    name: Optional[str] = None
    capabilities: List[str]
    metadata: Dict[str, Any]

class SensorTypeResponse(BaseModel):
    """Sensor type details"""
    manufacturer: str
    model: str
    capabilities: List[str]
    firmware_ver: Optional[str] = None
