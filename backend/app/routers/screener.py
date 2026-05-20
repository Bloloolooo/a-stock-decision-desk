from fastapi import APIRouter

from app.schemas import ScreenerConfig, ScreenerConfigUpdate, ScreenerResult, ScreenerStatus
from app.services.screener import screener_service

router = APIRouter()


@router.get("/results", response_model=list[ScreenerResult])
def get_results(type: str = "trend") -> list[ScreenerResult]:
    return screener_service.results(type)


@router.get("/config", response_model=ScreenerConfig)
def get_config() -> ScreenerConfig:
    return screener_service.config()


@router.put("/config", response_model=ScreenerConfig)
def update_config(payload: ScreenerConfigUpdate) -> ScreenerConfig:
    return screener_service.update_config(payload.symbols)


@router.get("/status", response_model=ScreenerStatus)
def get_status() -> ScreenerStatus:
    return screener_service.status()


@router.post("/refresh", response_model=ScreenerStatus)
def refresh() -> ScreenerStatus:
    return screener_service.refresh()
