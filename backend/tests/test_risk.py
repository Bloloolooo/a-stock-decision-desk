from app.services.risk import fixed_risk_position_amount, fractional_kelly


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
