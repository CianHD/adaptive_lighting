from pydantic import BaseModel, Field, NonNegativeInt
from typing import Optional, List, Dict, Any
from datetime import datetime

# Sensor-Asset Link Info
class SensorAssetLinkInfo(BaseModel):
    """Information about a sensor-asset link with optional section identifier"""
    asset_exedra_id: str
    section: Optional[str] = None

class SensorAssetGroup(BaseModel):
    """Aggregated luminaire group for a sensor section."""
    sensor_external_id: str
    section: Optional[str] = None
    asset_exedra_ids: List[str]
    asset_count: int

# Sensor data ingestion
class SensorIngestRequest(BaseModel):
    """Unified sensor data ingestion payload"""
    sensor_external_id: str
    observed_at: datetime
    section: Optional[str] = Field(None, description="Section/direction identifier where the reading was observed")
    vehicle_count: Optional[NonNegativeInt] = None
    pedestrian_count: Optional[NonNegativeInt] = None
    avg_vehicle_speed_kmh: Optional[float] = Field(None, ge=0)

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
    linked_assets: List[SensorAssetLinkInfo]
    vendor: Optional[str] = None
    name: Optional[str] = None
    capabilities: List[str]
    metadata: Dict[str, Any]

class SensorTypeResponse(BaseModel):
    """Sensor type details"""
    sensor_type_id: str
    manufacturer: str
    model: str
    capabilities: List[str]
    firmware_ver: Optional[str] = None

# Sensor CRUD operations
class SensorCreateRequest(BaseModel):
    """Request to create a new sensor"""
    external_id: str = Field(..., description="External sensor identifier")
    sensor_type_id: str = Field(..., description="ID of the sensor type")
    asset_links: List[SensorAssetLinkInfo] = Field(..., description="List of asset links with optional sections")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional sensor metadata")

class SensorCreateResponse(BaseModel):
    """Response for sensor creation"""
    sensor_id: str
    external_id: str
    sensor_type_id: str
    linked_assets: List[SensorAssetLinkInfo]
    metadata: Dict[str, Any]
    created_at: datetime

class SensorUpdateRequest(BaseModel):
    """Request to update a sensor"""
    sensor_type_id: Optional[str] = Field(None, description="Updated sensor type ID")
    asset_links: Optional[List[SensorAssetLinkInfo]] = Field(None, description="Updated list of asset links with optional sections")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Updated sensor metadata")

class SensorUpdateResponse(BaseModel):
    """Response for sensor update"""
    sensor_id: str
    external_id: str
    sensor_type_id: str
    linked_assets: List[SensorAssetLinkInfo]
    metadata: Dict[str, Any]
    updated_at: datetime

# Sensor Type CRUD operations
class SensorTypeCreateRequest(BaseModel):
    """Request to create a new sensor type"""
    manufacturer: str = Field(..., description="Sensor manufacturer")
    model: str = Field(..., description="Sensor model")
    capabilities: List[str] = Field(..., description="List of sensor capabilities")
    firmware_ver: Optional[str] = Field(None, description="Firmware version")
    notes: Optional[str] = Field(None, description="Additional notes")

class SensorTypeCreateResponse(BaseModel):
    """Response for sensor type creation"""
    sensor_type_id: str
    manufacturer: str
    model: str
    capabilities: List[str]
    firmware_ver: Optional[str]
    notes: Optional[str]

class SensorTypeUpdateRequest(BaseModel):
    """Request to update a sensor type"""
    capabilities: Optional[List[str]] = Field(None, description="Updated list of sensor capabilities")
    firmware_ver: Optional[str] = Field(None, description="Updated firmware version")
    notes: Optional[str] = Field(None, description="Updated notes")

class SensorTypeUpdateResponse(BaseModel):
    """Response for sensor type update"""
    sensor_type_id: str
    manufacturer: str
    model: str
    capabilities: List[str]
    firmware_ver: Optional[str]
    notes: Optional[str]
