from fastapi import APIRouter

from app.schemas import ScreenerResult
from app.services.screener import screener_service

router = APIRouter()


@router.get("/results", response_model=list[ScreenerResult])
def get_results(type: str = "trend") -> list[ScreenerResult]:
    return screener_service.results(type)
