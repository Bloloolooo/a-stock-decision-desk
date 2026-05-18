from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from app.routers import market, portfolio, risk, screener

app = FastAPI(title="A Stock Decision Desk", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(market.router, prefix="/api/market", tags=["market"])
app.include_router(risk.router, prefix="/api/risk", tags=["risk"])
app.include_router(screener.router, prefix="/api/screener", tags=["screener"])


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
