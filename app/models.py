from pydantic import BaseModel, Field
from typing import Optional, List

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    token: str
    role: str
    ref: str
    display: str

class HospitalCapacityUpdate(BaseModel):
    available_beds: int = Field(..., ge=0)
    icu_available: int = Field(..., ge=0)

class SimHospitalFullRequest(BaseModel):
    hospital_id: str = "H1"

class SimRoadBlockRequest(BaseModel):
    road_id: str = "R3"
    blocked: Optional[int] = 1

class SimRiskIncreaseRequest(BaseModel):
    multiplier: float = 2.0

class SimNewIncidentRequest(BaseModel):
    area: str = "N3"
    critical: int = 1
    serious: int = 2
    moderate: int = 1
    notes: str = "Simulated Secondary Incident (Building Collapse at West Junction)"

class IncidentReportForm(BaseModel):
    critical: int = 0
    serious: int = 0
    moderate: int = 0
    notes: Optional[str] = ""
    area: Optional[str] = "N1"
    lat: Optional[float] = None
    lng: Optional[float] = None
