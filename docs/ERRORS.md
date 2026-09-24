# Error Catalog & Troubleshooting

Every tool answers `{"ok": true, "data": ...}` or `{"ok": false, "error": {"code", "message", "data"}}`.
The `code` is stable; the `message` says what happened in words; `data` carries the numbers
(limits, prices, the Falling Knife `market` reading). The approval API (`/api/approve-trade`)
answers a refusal with HTTP `409` (or `400` for a brokerage problem) and the same `code` in
`detail`; an unknown, expired, cancelled or already-approved proposal, or a wrong `confirm_token`,
answers `400` with the reason as text.

| Issue | Potential Fix |
| :--- | :--- |
| **Missing .env** | Run `python tools/setup_wizard.py`; it offers to copy `env.example` to `.env`. Paper mode needs no keys. |
| **Missing news/social keys** | See `docs/SENTIMENT.md` for which tool needs which key; `fetch_rss_news` needs none. |
| **Blocked trade** | Read the error `code` below. `risk_blocked` gives the Risk Guardian's reason. |
| **Dependency error** | Use Python 3.12+ and `pip install -r requirements.txt`. |

---

## Error codes

### Risk
- `risk_blocked`: the Risk Guardian refused the trade. The message is the reason: position size over
  5% of equity, the 5% daily-loss or 10% drawdown limit (BUYs only), the Falling Knife price rule
  (`docs/FALLING_KNIFE.md`; `data.market` has the reading), your own `sentiment_score` below -0.5,
  or an account/price the check could not read (a BUY then fails closed).
- `risk_validation_error`: the risk check itself raised; the message has the exception.

### Requests
- `invalid_request`: a malformed request, e.g. a side other than buy/sell, a non-positive or
  non-numeric amount, an order type other than market/limit, a limit with no positive price, or an
  insight outside the documented fields.
- `invalid_mode`: `deposit_paper_funds` / `reset_paper_wallet` called in live mode.

### Live trading switches and policy
- `live_trading_disabled`: `PAPER_MODE=false` but `LIVE_TRADING_ENABLED` is not `true`.
- `trading_halted`: the kill switch `TRADING_HALTED` is set.
- `ticker_not_allowed`, `brokerage_not_allowed`: outside `ALLOW_TICKERS` / `ALLOW_BROKERAGES`.
- `order_amount_too_large`: more shares than `MAX_ORDER_AMOUNT`.
- `invalid_policy_config`: `MAX_ORDER_AMOUNT` is not a number; every live order is refused until it
  is fixed or unset.

These are checked when a live order is placed or proposed, and again when a proposal is approved.

### Execution
- `brokerage_not_supported`: an `exchange` other than alpaca, tradier, ibkr, schwab, etrade or
  robinhood.
- `brokerage_not_configured`: that brokerage's keys are not set.
- `execution_error`: the paper engine or the brokerage raised; the message has its reason.
- `limit_not_marketable`: (paper) a limit BUY below / SELL above the market; resting orders are
  not simulated.
- `insufficient_funds`: (paper) not enough cash or shares.

### Market data and research
- `market_data_error`: the latest price could not be read (yfinance).
- `history_error`: candles could not be read.
- `backtest_error`: the strategy did not compile, had no `on_candle`, or raised.
- `stress_test_error`, `market_regime_error`: those tools failed; the message says why.

### Not available
- `not_implemented`: `start_brokerage_private_ws` (private order streams are not implemented; poll
  the brokerage instead).
- `paper_mode_not_supported`: the same tool in paper mode.
