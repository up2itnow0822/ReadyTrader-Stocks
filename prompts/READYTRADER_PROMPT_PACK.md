## ReadyTrader-Stocks Prompt Pack

These are copy/paste prompts you can drop into Agent Zero, Claude, or any MCP-capable agent.
Every tool they name is in `docs/TOOLS.md`.

---

## Prompt 1 — 10-minute paper-mode evaluation

You have access to the ReadyTrader-Stocks MCP server. We are in PAPER_MODE=true.

Goals:
- Validate you can use the tools safely
- Produce a short “operator report” that proves the system works

Steps:
1) Call `get_stock_price("AAPL")` and report the latest price.
2) Call `deposit_paper_funds("USD", 100000)`.
3) Call `validate_trade_risk("buy", "AAPL", 2000, 100000)` and explain the verdict, including the
   `market` (Falling Knife) reading.
4) Place a paper market order: `place_market_order("AAPL", "buy", 5)`. It fills at the latest price.
5) Place a paper limit order below the market: `place_limit_order("AAPL", "buy", 5, <10% below the
   price>)`. Explain the `limit_not_marketable` answer (resting orders are not simulated).
6) Try an oversized order: `place_market_order("AAPL", "buy", 1000)` and report the `risk_blocked`
   reason.
7) Produce a final summary with:
   - the orders that filled and at what price
   - every refusal, with its `code` and `message`

Constraints:
- Do not attempt live trading.
- Every failed call returns `{"ok": false, "error": {"code", "message"}}`: quote both.

---

## Prompt 2 — Synthetic Stress Lab (deterministic)

We are in PAPER_MODE=true. I will provide strategy code. You will:
- run `run_synthetic_stress_test(strategy_code, config_json)`
- summarize tail risk and regime failures
- output recommended settings

Use this config as a baseline:
```json
{
  "master_seed": 1337,
  "scenarios": 200,
  "length": 500,
  "timeframe": "1h",
  "initial_capital": 10000,
  "start_price": 100,
  "base_vol": 0.015,
  "black_swan_prob": 0.03,
  "parabolic_prob": 0.03
}
```

Output requirements:
- Show max drawdown stats (p95 + max) and return tail (p05).
- List the worst-case seed(s) and their event metadata.
- Provide parameter recommendations (and explain what failure mode they address).

---

## Prompt 3 — Live trading preflight (DO NOT EXECUTE TRADES)

We are preparing for live mode, but you must not place any orders.

Tasks:
1) For each ticker I plan to trade, call `get_stock_price` and
   `validate_trade_risk("buy", <ticker>, <typical order in USD>, <account equity>)`; report any
   refusal and the Falling Knife reading.
2) Call `get_market_regime(<ticker>)` and say whether my strategy suits the regime.
3) Output a “go/no-go” checklist for the operator to confirm before enabling live trading:
   - `PAPER_MODE=false` and `LIVE_TRADING_ENABLED=true`, and `TRADING_HALTED` unset
   - `EXECUTION_APPROVAL_MODE=approve_each` for the first live week
   - `MAX_ORDER_AMOUNT`, `ALLOW_TICKERS` and `ALLOW_BROKERAGES` set to the smallest workable values
   - the brokerage on its paper account or sandbox first (`ALPACA_PAPER` / `TRADIER_SANDBOX`)
   - the approval API running with the same `EXECUTION_SESSION_ID` (see `RUNBOOK.md`)
