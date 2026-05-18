from fastapi import APIRouter

from app.schemas import RiskAdvice
from app.services.risk import risk_service

router = APIRouter()


@router.get("/advice/{symbol}", response_model=RiskAdvice)
def get_risk_advice(symbol: str) -> RiskAdvice:
    return risk_service.advice(symbol)
