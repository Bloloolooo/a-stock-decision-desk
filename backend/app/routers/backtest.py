from fastapi import APIRouter, HTTPException

from app.schemas import BacktestRequest, BacktestResult
from app.services.backtest import backtest_service

router = APIRouter()


@router.post("/run", response_model=BacktestResult)
def run_backtest(payload: BacktestRequest) -> BacktestResult:
    try:
        return backtest_service.run(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
