from fastapi import APIRouter

from app.models import FUEL_TYPES
from app.schemas import FUEL_LABELS, FuelInfo

router = APIRouter()


@router.get("/api/fuels", response_model=list[FuelInfo])
async def list_fuels() -> list[FuelInfo]:
    return [FuelInfo(code=f, label=FUEL_LABELS[f]) for f in FUEL_TYPES]
