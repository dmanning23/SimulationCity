"""
Test configuration.

Requires docker-compose to be running (MongoDB + Redis):
    docker-compose up -d

Run tests from the backend directory:
    uv run pytest
"""

import os

# Override settings before any app imports so pydantic-settings picks them up.
os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("MONGODB_DB_NAME", "simulationcity_test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from app.models.city import City
from app.models.chunk import Chunk
from app.models.player import Player

_DOCUMENT_MODELS = [City, Chunk, Player]
_TEST_DB = os.environ["MONGODB_DB_NAME"]
_MONGO_URL = os.environ["MONGODB_URL"]


@pytest_asyncio.fixture()
async def db():
    """Isolated test database — dropped after each test."""
    client = AsyncIOMotorClient(_MONGO_URL)
    database = client[_TEST_DB]
    await init_beanie(database=database, document_models=_DOCUMENT_MODELS)
    yield database
    for name in await database.list_collection_names():
        await database.drop_collection(name)
    client.close()


@pytest_asyncio.fixture()
async def http_client(db):
    """ASGI test client wired to the full socket_app (FastAPI + Socket.IO)."""
    from app.main import socket_app

    async with AsyncClient(
        transport=ASGITransport(app=socket_app), base_url="http://test"
    ) as ac:
        yield ac
