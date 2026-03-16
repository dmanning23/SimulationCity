from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from app.config import settings
from app.models.city import City
from app.models.chunk import Chunk
from app.models.player import Player

_client: AsyncIOMotorClient | None = None


async def init_db() -> None:
    global _client
    _client = AsyncIOMotorClient(settings.mongodb_url)
    await init_beanie(
        database=_client[settings.mongodb_db_name],
        document_models=[City, Chunk, Player],
    )


async def close_db() -> None:
    if _client:
        _client.close()
