"""Paper-account equity and drawdown, which the Risk Guardian's drawdown rule is fed."""

import pytest

from core.paper import PaperTradingEngine


@pytest.fixture
def engine(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "paper.db"))
    e.deposit("u", "USD", 100_000.0)
    return e


def test_selling_a_position_at_cost_is_not_a_drawdown(engine):
    for _ in range(6):
        engine.execute_trade("u", "buy", "AAPL", amount=14.8, price=337.0)
    engine.execute_trade("u", "sell", "AAPL", amount=88.8, price=337.0)
    metrics = engine.get_risk_metrics("u")
    assert metrics["drawdown_pct"] == pytest.approx(0.0, abs=1e-9)
    assert metrics["max_drawdown_pct"] == pytest.approx(0.0, abs=1e-9)


def test_a_recovered_loss_is_no_longer_a_current_drawdown(engine):
    engine.execute_trade("u", "buy", "AAPL", amount=100.0, price=100.0)
    engine.execute_trade("u", "sell", "AAPL", amount=100.0, price=80.0)  # a real 2,000 loss
    assert engine.get_risk_metrics("u")["drawdown_pct"] == pytest.approx(0.02, abs=1e-6)
    engine.deposit("u", "USD", 2_000.0)  # capital added is not a recovery (UAT XR-03)
    assert engine.get_risk_metrics("u")["drawdown_pct"] == pytest.approx(0.02, abs=1e-6)
    engine.execute_trade("u", "buy", "AAPL", amount=100.0, price=80.0)
    engine.execute_trade("u", "sell", "AAPL", amount=100.0, price=101.0)  # a trading gain recovers it
    metrics = engine.get_risk_metrics("u")
    assert metrics["drawdown_pct"] == pytest.approx(0.0, abs=1e-9)
    assert metrics["max_drawdown_pct"] == pytest.approx(0.02, abs=1e-6)


def test_a_resting_limit_order_keeps_its_reserved_funds_in_equity(engine):
    engine.place_limit_order("u", "buy", "MSFT", amount=10.0, price=400.0)
    assert engine.get_portfolio_value_usd("u") == pytest.approx(100_000.0)
    engine.check_open_orders("MSFT", current_price=399.0)
    assert engine.get_portfolio_value_usd("u") == pytest.approx(100_000.0)
    assert engine.get_risk_metrics("u")["drawdown_pct"] == pytest.approx(0.0, abs=1e-9)


def test_balances_survive_a_restart(engine):
    engine.execute_trade("u", "buy", "AAPL", amount=10.0, price=100.0)
    restarted = PaperTradingEngine(db_path=engine.db_path)
    assert restarted.get_balance("u", "AAPL") == 10.0
    assert restarted.get_balance("u", "USD") == pytest.approx(99_000.0)


def test_a_trade_or_deposit_without_a_real_number_never_touches_the_ledger(engine):
    """UAT BE-34: a NaN price passed `price <= 0`, the balance check and the debit, and was stored as a
    NULL balance; every later deposit then crashed. Now the engine refuses before it writes anything."""
    nan = float("nan")
    with pytest.raises(ValueError, match="unknown"):
        engine.execute_trade("u", "buy", "AAPL", amount=1.0, price=nan)
    with pytest.raises(ValueError, match="positive"):
        engine.execute_trade("u", "buy", "AAPL", amount=nan, price=100.0)
    with pytest.raises(ValueError, match="finite"):
        engine.deposit("u", "USD", nan)
    assert engine.get_balances("u") == {"USD": 100_000.0}
    assert engine.deposit("u", "USD", 1.0) == "Deposited 1.0 USD. New Balance: 100001.0"


def test_a_trade_without_a_price_uses_the_last_known_one(engine):
    engine.execute_trade("u", "buy", "AAPL", amount=1.0, price=337.0)
    engine.execute_trade("u", "buy", "AAPL", amount=1.0, price=float("nan"))
    assert engine.get_balances("u") == {"AAPL": 2.0, "USD": 100_000.0 - 2 * 337.0}
