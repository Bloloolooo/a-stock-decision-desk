from fastapi import APIRouter

from app.schemas import DecisionCenter
from app.services.decision import decision_service

router = APIRouter()


@router.get("/{symbol}", response_model=DecisionCenter)
def get_decision(symbol: str) -> DecisionCenter:
    return decision_service.decision(symbol=symbol)
