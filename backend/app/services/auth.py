from datetime import datetime, timezone, timedelta

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext
from beanie import PydanticObjectId

from app.config import settings
from app.models.player import Player

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(player_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": player_id, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


async def get_current_player(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Player:
    try:
        payload = decode_token(credentials.credentials)
        player_id: str | None = payload.get("sub")
        if not player_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    player = await Player.get(PydanticObjectId(player_id))
    if not player:
        raise HTTPException(status_code=401, detail="Player not found")
    return player
