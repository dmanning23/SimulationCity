from datetime import datetime, timezone
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field
from pymongo import ASCENDING, IndexModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChunkCoordinates(BaseModel):
    x: int
    y: int


class Building(BaseModel):
    id: str
    type: str            # residential, commercial, industrial, etc.
    subtype: str
    position: dict       # {x, y} within chunk
    size: dict           # {width, height} in tiles
    level: int = 1
    health: int = 100
    asset_id: Optional[str] = None  # Premium: ref to generated_assets


class ChunkBase(BaseModel):
    terrain: list = Field(
        default_factory=lambda: [[0] * 16 for _ in range(16)]
    )  # 16x16 grid; 0 = grass
    buildings: list[Building] = []
    roads: list = []


class ChunkLayers(BaseModel):
    electricity: dict = Field(default_factory=dict)
    pollution: dict = Field(default_factory=dict)
    water: dict = Field(default_factory=dict)


class Chunk(Document):
    city_id: PydanticObjectId
    coordinates: ChunkCoordinates
    last_updated: datetime = Field(default_factory=_utcnow)
    version: int = 0  # Optimistic concurrency control
    base: ChunkBase = Field(default_factory=ChunkBase)
    layers: ChunkLayers = Field(default_factory=ChunkLayers)

    class Settings:
        name = "chunks"
        indexes = [
            IndexModel(
                [
                    ("city_id", ASCENDING),
                    ("coordinates.x", ASCENDING),
                    ("coordinates.y", ASCENDING),
                ],
                unique=True,
            )
        ]
