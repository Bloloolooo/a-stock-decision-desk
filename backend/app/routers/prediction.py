from fastapi import APIRouter, HTTPException

from app.schemas import PredictionResult, PredictionSettingsUpdate, PredictionStatus
from app.services.prediction import prediction_service

router = APIRouter()


@router.get("/status", response_model=PredictionStatus)
def get_status() -> PredictionStatus:
    return prediction_service.status()


@router.put("/settings", response_model=PredictionStatus)
def update_settings(payload: PredictionSettingsUpdate) -> PredictionStatus:
    return prediction_service.update_settings(enabled=payload.enabled, model_name=payload.model_name)


@router.post("/install", response_model=PredictionStatus)
def install() -> PredictionStatus:
    return prediction_service.install_async()


@router.get("/{symbol}", response_model=PredictionResult)
def predict(symbol: str, horizon: int = 20) -> PredictionResult:
    try:
        return prediction_service.predict(symbol=symbol, horizon=horizon)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
