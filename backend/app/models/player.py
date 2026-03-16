from datetime import datetime, timezone
from typing import Optional

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Player(Document):
    username: str
    email: str
    hashed_password: str
    is_premium: bool = False
    premium_expires_at: Optional[datetime] = None
    generation_credits: int = 0      # Premium: SD generation credits
    credits_reset_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utcnow)

    class Settings:
        name = "players"
        indexes = [
            IndexModel([("email", ASCENDING)], unique=True),
            IndexModel([("username", ASCENDING)], unique=True),
        ]
