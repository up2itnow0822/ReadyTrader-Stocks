# Error Catalog & Troubleshooting

Every tool answers `{"ok": true, "data": ...}` or `{"ok": false, "error": {"code", "message", "data"}}`.
The `code` is stable; the `message` says what happened in words; `data` carries the numbers
(limits, prices, the Falling Knife `market` reading). The approval API (`/api/approve-trade`)
answers a refusal with HTTP `409` (or `400` for a brokerage problem) and the same `code` in
`detail`; an unknown proposal answers `404`, a wrong `confirm_token` `403`, and an expired,
cancelled or already-approved proposal `409`, with the reason as text.

| Issue | Potential Fix |
| :--- | :--- |
| **Missing .env** | Run `python tools/setup_wizard.py`; it offers to copy `env.example` to `.env`. Paper mode needs no keys. |
| **Missing news/social keys** | See `docs/SENTIMENT.md` for which tool needs which key; `fetch_rss_news` needs none. |
| **Blocked trade** | Read the error `code` below. `risk_blocked` gives the Risk Guardian's reason. |
| **Dependency error** | Use Python 3.12+ and `pip install -r requirements.txt`. |

---

## Error codes

### Risk
- `risk_blocked`: the Risk Guardian refused the trade. The message is the reason: new exposure over
  5% of equity, the 5% daily-loss or 10% drawdown limit (orders that add exposure), the Falling Knife
  price rule (`docs/FALLING_KNIFE.md`; `data.market` has the reading), your own `sentiment_score`
  below -0.5, or an account/market price the check could not read (an order that adds exposure then
  fails closed; it is never valued at a price the order carries). The daily-loss and drawdown rules
  read the paper account (deposits are not gains); live orders list them in `data.inactive_rules`.
  Selling out of a position is never sized as new exposure; `data` includes `position_units`,
  `exposure_added_units` and `reference_price`.
- `risk_validation_error`: the risk check itself raised; the message has the exception.

### Requests
- `invalid_request`: a malformed request, e.g. a side other than buy/sell, a non-positive or
  non-numeric amount, an order type other than market/limit, a limit with no positive price, a
  `sentiment_score` that is not a finite number, a symbol with a `/` (class shares use `BRK.B`) or,
  in paper mode, a ticker spelled like the ledger's cash (`USD`), or an insight outside the
  documented fields. A market order's `price` is ignored. Arguments of the wrong type (text that
  is not a number, or `true`/`false` for an amount, price, value or score) are refused by the MCP
  argument validation before the tool runs: the client gets a tool error naming the argument.
- `paper_price_required`: `deposit_paper_funds` of shares with no market price for the ticker (a
  deposit is valued at the market price); deposit USD or retry.
- `invalid_mode`: `deposit_paper_funds` / `reset_paper_wallet` called in live mode.
- `mode_mismatch`: (approval API) the proposal was made in paper mode and the API runs live, or the
  reverse; nothing was executed.
- `operator_token_required`: (approval API) `API_OPERATOR_TOKEN` is set and the request did not send
  `Authorization: Bearer <it>` (HTTP 401), or a live proposal was approved on an API without
  `API_OPERATOR_TOKEN` (HTTP 403).
- `internal_error`: (approval API, HTTP 500) an unexpected error; the message names the request id
  to find in the API log (`X-Request-ID`), never the exception text.

### Live trading switches and policy
- `live_trading_disabled`: `PAPER_MODE=false` but `LIVE_TRADING_ENABLED` is not `true`.
- `trading_halted`: the kill switch `TRADING_HALTED` is set.
- `ticker_not_allowed`, `brokerage_not_allowed`: outside `ALLOW_TICKERS` / `ALLOW_BROKERAGES`.
- `order_amount_too_large`: more shares than `MAX_ORDER_AMOUNT`.
- `invalid_policy_config`: `MAX_ORDER_AMOUNT` is not a number; every live order is refused until it
  is fixed or unset.

These are checked when a live order is placed or proposed, and again when a proposal is approved.
The switches (`live_trading_disabled`, `trading_halted`) answer before anything else, even an
unconfigured brokerage, and at approval before the proposal is used up.

### Execution
- `brokerage_not_supported`: an `exchange` other than alpaca, tradier, ibkr, schwab, etrade or
  robinhood.
- `brokerage_not_configured`: that brokerage's keys are not set.
- `market_closed`: (Alpaca) the market is closed, or its clock could not be read: nothing was
  proposed or sent (the approval API answers `409` before the proposal is used up).
- `execution_error`: the paper engine or the brokerage raised; the message has its reason (for
  Alpaca also a fractional limit order, which is refused, or an `IOC` order Alpaca cancelled
  unfilled: nothing traded).
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
