from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from app.routers import backtest, decision, market, portfolio, prediction, risk, screener

app = FastAPI(title="A Stock Decision Desk", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(market.router, prefix="/api/market", tags=["market"])
app.include_router(decision.router, prefix="/api/decision", tags=["decision"])
app.include_router(risk.router, prefix="/api/risk", tags=["risk"])
app.include_router(screener.router, prefix="/api/screener", tags=["screener"])
app.include_router(prediction.router, prefix="/api/prediction", tags=["prediction"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["backtest"])


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
