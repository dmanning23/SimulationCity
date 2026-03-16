from datetime import datetime, timezone

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.models.city import City, CollaboratorRole, CitySettings
from app.models.player import Player
from app.schemas.cities import CityResponse, CreateCityRequest, UpdateCityRequest
from app.services.auth import get_current_player

router = APIRouter(prefix="/api/cities", tags=["cities"])


def _to_response(city: City) -> CityResponse:
    return CityResponse(
        id=str(city.id),
        name=city.name,
        owner_id=str(city.owner_id),
        created_at=city.created_at,
        last_updated=city.last_updated,
        size=city.size,
        settings=city.settings,
        global_stats=city.global_stats,
        collaborator_count=len(city.collaborators),
    )


def _has_access(city: City, player: Player) -> bool:
    if city.owner_id == player.id:
        return True
    return any(c.user_id == player.id for c in city.collaborators)


def _is_admin(city: City, player: Player) -> bool:
    if city.owner_id == player.id:
        return True
    return any(
        c.user_id == player.id and c.role == CollaboratorRole.ADMIN
        for c in city.collaborators
    )


@router.post("", response_model=CityResponse, status_code=201)
async def create_city(
    data: CreateCityRequest,
    player: Player = Depends(get_current_player),
):
    city = City(
        name=data.name,
        owner_id=player.id,
        settings=data.settings or CitySettings(),
    )
    await city.insert()
    return _to_response(city)


@router.get("", response_model=list[CityResponse])
async def list_cities(player: Player = Depends(get_current_player)):
    owned = await City.find(City.owner_id == player.id).to_list()
    collab = await City.find({"collaborators.user_id": player.id}).to_list()

    seen = {str(c.id) for c in owned}
    all_cities = owned + [c for c in collab if str(c.id) not in seen]
    return [_to_response(c) for c in all_cities]


@router.get("/{city_id}", response_model=CityResponse)
async def get_city(
    city_id: str,
    player: Player = Depends(get_current_player),
):
    city = await City.get(PydanticObjectId(city_id))
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    if not _has_access(city, player):
        raise HTTPException(status_code=403, detail="Access denied")
    return _to_response(city)


@router.patch("/{city_id}", response_model=CityResponse)
async def update_city(
    city_id: str,
    data: UpdateCityRequest,
    player: Player = Depends(get_current_player),
):
    city = await City.get(PydanticObjectId(city_id))
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    if not _is_admin(city, player):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    if data.name is not None:
        city.name = data.name
    if data.settings is not None:
        city.settings = data.settings
    city.last_updated = datetime.now(timezone.utc)
    await city.save()
    return _to_response(city)


@router.delete("/{city_id}", status_code=204)
async def delete_city(
    city_id: str,
    player: Player = Depends(get_current_player),
):
    city = await City.get(PydanticObjectId(city_id))
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    if city.owner_id != player.id:
        raise HTTPException(status_code=403, detail="Only the owner can delete a city")
    await city.delete()
