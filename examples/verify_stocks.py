"""
ReadyTrader-Stocks: a quick check that market data and paper execution work in this install.

Reads a live AAPL quote from Yahoo Finance, then buys 10 shares in a throwaway paper account (a
temporary database, so your own paper balances are untouched).
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.container import global_container  # noqa: E402
from core.paper import PaperTradingEngine  # noqa: E402


def main() -> int:
    print("--- Verifying ReadyTrader-Stocks ---")
    try:
        ticker = global_container.exchange_provider.fetch_ticker("AAPL")
        price = float(ticker["last"])
        print(f"Market data: AAPL last = {price:.2f}")
    except Exception as e:
        print(f"FAILED market data: {e}")
        return 1

    with tempfile.TemporaryDirectory() as td:
        engine = PaperTradingEngine(db_path=os.path.join(td, "verify.db"))
        engine.deposit("verify", "USD", 10_000.0)
        print(engine.execute_trade("verify", "buy", "AAPL", 10, price, "verify_stocks"))
        shares = engine.get_balance("verify", "AAPL")
        if shares != 10:
            print(f"FAILED paper execution: expected 10 AAPL, have {shares}")
            return 1
    print("SUCCESS: market data and paper execution work.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
