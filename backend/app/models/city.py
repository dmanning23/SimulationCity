from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CollaboratorRole(str, Enum):
    ADMIN = "admin"
    BUILDER = "builder"
    VIEWER = "viewer"


class Collaborator(BaseModel):
    user_id: PydanticObjectId
    role: CollaboratorRole


class CitySettings(BaseModel):
    simulation_speed: str = "normal"
    starting_funds: int = 10000
    difficulty: str = "medium"
    design_style: Optional[str] = None  # Premium: SD style palette


class GlobalStats(BaseModel):
    population: int = 0
    happiness: int = 50
    treasury: float = 10000.0


class City(Document):
    name: str
    owner_id: PydanticObjectId
    collaborators: list[Collaborator] = []
    created_at: datetime = Field(default_factory=_utcnow)
    last_updated: datetime = Field(default_factory=_utcnow)
    size: dict = Field(default_factory=lambda: {"width": 64, "height": 64})  # in chunks
    settings: CitySettings = Field(default_factory=CitySettings)
    global_stats: GlobalStats = Field(default_factory=GlobalStats)

    class Settings:
        name = "cities"
