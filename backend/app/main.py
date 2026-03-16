from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import close_db, init_db
from app.routers import auth, cities
from app.socket_handlers import sio


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="SimulationCity API",
    version="0.1.0",
    lifespan=lifespan,
)

_DEV_ORIGINS = ["http://localhost:3000", "http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEV_ORIGINS if settings.environment == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(cities.router)


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok", "environment": settings.environment}


# Wrap FastAPI with Socket.IO ASGI — run uvicorn against `socket_app`
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)
