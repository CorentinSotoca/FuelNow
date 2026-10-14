from fastapi import APIRouter

from app.schemas import FUEL_LABELS, FuelInfo
from app import services

router = APIRouter()


@router.get("/api/fuels", response_model=list[FuelInfo])
async def list_fuels() -> list[FuelInfo]:
    return [FuelInfo(**f) for f in services.list_fuels()]
