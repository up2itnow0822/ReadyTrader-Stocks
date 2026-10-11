"""A paper limit order that fills, as the README's paper demo walks through it."""

import runpy
from pathlib import Path

from core.paper import PaperTradingEngine

ROOT = Path(__file__).resolve().parents[1]


def test_a_limit_fill_does_not_lock_the_database(tmp_path):
    engine = PaperTradingEngine(db_path=str(tmp_path / "paper.db"))
    engine.deposit("u", "USD", 10_000.0)
    engine.place_limit_order("u", "buy", "AAPL", amount=10.0, price=150.0)
    messages = engine.check_open_orders("AAPL", current_price=149.0)
    assert messages and "FILLED" in messages[0]
    assert engine.get_balance("u", "AAPL") == 10.0


def test_the_documented_paper_demo_runs():
    demo = runpy.run_path(str(ROOT / "examples" / "paper_quick_demo.py"), run_name="demo")
    assert demo["main"]() == 0
