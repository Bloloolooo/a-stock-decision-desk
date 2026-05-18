from datetime import datetime

from app.schemas import PortfolioSummary, Position, PositionCreate
from app.services.market_data import sample_market_data


class PortfolioService:
    def __init__(self) -> None:
        self.cash = 92_180.0
        self._positions: dict[str, PositionCreate] = {
            "300308": PositionCreate(symbol="300308", name="中际旭创", quantity=600, average_cost=151.55),
            "300750": PositionCreate(symbol="300750", name="宁德时代", quantity=300, average_cost=205.44),
        }

    def set_cash(self, cash: float) -> None:
        self.cash = cash

    def upsert_position(self, payload: PositionCreate) -> Position:
        self._positions[payload.symbol] = payload
        return self._position_view(payload)

    def positions(self) -> list[Position]:
        return [self._position_view(position) for position in self._positions.values()]

    def summary(self) -> PortfolioSummary:
        positions = self.positions()
        market_value = sum(position.market_value for position in positions)
        floating_pnl = sum(position.floating_pnl for position in positions)
        return PortfolioSummary(
            total_assets=round(self.cash + market_value, 2),
            cash=round(self.cash, 2),
            position_market_value=round(market_value, 2),
            floating_pnl=round(floating_pnl, 2),
            today_pnl=-1280.0,
            updated_at=datetime.now(),
        )

    def _position_view(self, payload: PositionCreate) -> Position:
        last_price = sample_market_data.latest_price(payload.symbol)
        market_value = last_price * payload.quantity
        cost_value = payload.average_cost * payload.quantity
        floating_pnl = market_value - cost_value
        floating_pnl_pct = floating_pnl / cost_value if cost_value else 0
        return Position(
            **payload.model_dump(),
            last_price=round(last_price, 2),
            market_value=round(market_value, 2),
            floating_pnl=round(floating_pnl, 2),
            floating_pnl_pct=round(floating_pnl_pct, 4),
            updated_at=datetime.now(),
        )


portfolio_service = PortfolioService()
