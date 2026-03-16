from fastapi import APIRouter, HTTPException
from pymongo.errors import DuplicateKeyError

from app.models.player import Player
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.auth import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: RegisterRequest):
    if await Player.find_one(Player.email == data.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    if await Player.find_one(Player.username == data.username):
        raise HTTPException(status_code=400, detail="Username already taken")

    player = Player(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
    )
    try:
        await player.insert()
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Email or username already taken")
    return TokenResponse(access_token=create_access_token(str(player.id)))


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest):
    player = await Player.find_one(Player.email == data.email)
    if not player or not verify_password(data.password, player.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenResponse(access_token=create_access_token(str(player.id)))
