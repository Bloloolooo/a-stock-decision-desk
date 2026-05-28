from datetime import date, datetime, timedelta

from app.schemas import PriceBar
from app.services.risk import fixed_risk_position_amount, fractional_kelly, market_regime_from_bars


def test_fixed_risk_position_amount_uses_stop_distance() -> None:
    amount = fixed_risk_position_amount(
        total_assets=100_000,
        current_price=20,
        stop_loss_price=18,
        risk_ratio=0.01,
    )
    assert amount == 10_000


def test_fractional_kelly_disables_negative_edge() -> None:
    assert fractional_kelly(win_rate=0.4, win_loss_ratio=1.0) == 0


def test_fractional_kelly_returns_discounted_fraction() -> None:
    value = fractional_kelly(win_rate=0.55, win_loss_ratio=1.5, fraction=0.25)
    assert round(value, 4) == 0.0625


def test_market_regime_detects_trend() -> None:
    bars = []
    start = date(2026, 1, 1)
    for index in range(70):
        close = 10 + index * 0.1
        bars.append(
            PriceBar(
                symbol="000001",
                period="daily",
                trade_date=start + timedelta(days=index),
                timestamp=(start + timedelta(days=index)).isoformat(),
                open=close * 0.99,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=1_000_000,
                amount=close * 1_000_000,
                updated_at=datetime.now(),
            )
        )
    assert market_regime_from_bars(bars) == "多头趋势"
