from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.city import CitySettings, GlobalStats


class CreateCityRequest(BaseModel):
    name: str
    settings: Optional[CitySettings] = None


class UpdateCityRequest(BaseModel):
    name: Optional[str] = None
    settings: Optional[CitySettings] = None


class CityResponse(BaseModel):
    id: str
    name: str
    owner_id: str
    created_at: datetime
    last_updated: datetime
    size: dict
    settings: CitySettings
    global_stats: GlobalStats
    collaborator_count: int = 0
