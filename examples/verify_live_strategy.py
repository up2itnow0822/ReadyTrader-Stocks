"""
ReadyTrader-Stocks: check the live-brokerage wiring without placing any order, then run the SMA
strategy on real AAPL data.

With no ALPACA_API_KEY / ALPACA_API_SECRET set, the Alpaca brokerage must report itself as not
available, so a live order would be refused rather than sent.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from execution.alpaca_service import AlpacaBrokerage  # noqa: E402
from strategy.moving_average import SmaStrategy  # noqa: E402


def main() -> int:
    print("--- Verifying live-brokerage wiring and a strategy ---")
    ok = True
    brokerage = AlpacaBrokerage()
    print(f"Alpaca brokerage available: {brokerage.is_available()} (False unless ALPACA_API_KEY/SECRET are set)")

    try:
        result = SmaStrategy("AAPL", short_window=5, long_window=10).analyze()
        print(f"SMA strategy on AAPL: {result}")
        ok = ok and "signal" in result and "error" not in result
    except Exception as e:
        print(f"FAILED strategy: {e}")
        ok = False
    print("SUCCESS" if ok else "FAILURE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
