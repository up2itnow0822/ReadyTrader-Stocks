## ReadyTrader-Stocks Runbook

Two processes make up a deployment:

- **The MCP server** (`python app/main.py`, stdio): the tools your agent calls. An MCP client
  launches it; it has no port.
- **The API server** (`python app/api_server.py`, `127.0.0.1:8000` by default): health, the paper
  portfolio, pending approvals and the approval endpoint the dashboard uses. Only needed for
  `approve_each` and the dashboard.

Every setting is read when a process starts, so **restart both processes after changing `.env`**.

### Common operations

#### Check that it is up
- MCP server: in your client, list the tools (20 are registered; see `docs/TOOLS.md`), or call
  `get_stock_price("AAPL")`.
- API server: `curl -s 127.0.0.1:8000/api/health` returns `{"status": "ok", "mode": "paper"}`
  (or `"live"`).
- Environment: `python tools/setup_wizard.py` checks the Python version, dependencies, data
  sources and the keys it finds.

#### Kill switch (live trading)
- Set `TRADING_HALTED=true` (any value other than empty, `false`, `0`, `no` or `off` halts) and
  restart both processes. Every live order, and every approval of one, is then refused with
  `trading_halted`. Paper trading is unaffected.
- To stop live trading entirely, set `PAPER_MODE=true` or `LIVE_TRADING_ENABLED=false` and restart.

#### Approve trades (`EXECUTION_APPROVAL_MODE=approve_each`)
- Start both processes with the same `EXECUTION_DB_PATH` and `EXECUTION_SESSION_ID`; without them
  the API cannot see the MCP server's proposals.
- `curl -s 127.0.0.1:8000/api/pending-approvals` lists proposals (they expire after 120 s).
- Approve: `POST /api/approve-trade` with `{"request_id", "confirm_token", "approve": true}`; the
  agent received the `confirm_token` with the proposal. The Risk Guardian, the kill switch and the
  live policy are checked again before anything executes; a refusal answers `409` with its `code`.
- Cancel: the same call with `"approve": false` (the `confirm_token` is required here too).
- The dashboard (`frontend/`) does the same from a browser at `http://localhost:3000`. Other
  browser origins are refused unless listed in `API_CORS_ORIGINS`.

#### Rotate brokerage credentials
- Update `ALPACA_*`, `TRADIER_*` (or the other brokerage variables in `env.example`), then restart.
  Keys live only in the environment; nothing is written to disk.

#### Debug a refused or failed order
- Every tool answers `{"ok": false, "error": {"code", "message", "data"}}` on failure; the codes
  are listed in `docs/ERRORS.md`. `risk_blocked` carries the Risk Guardian's reason and the
  Falling Knife `market` reading.
- The API server writes one JSON log line per event to stdout (`api_server_started`,
  `api_approval_risk_blocked`, ...); set `LOG_LEVEL=DEBUG` for more. The MCP server keeps stdout
  for the protocol and does not log there.

---

### Incident playbooks

#### 1) BUYs refused with `risk_blocked`
- **Read the reason** in the error. Common ones:
  - `Position size too large`: the order is more than 5% of the account's equity (paper equity, or
    the brokerage's reported equity in live mode). Reduce the size.
  - `Daily Loss Limit Hit` / `Max Drawdown`: the account lost 5% today or is 10% below its peak;
    BUYs resume when the condition clears. SELLs are always allowed.
  - Falling Knife: the stock fell 15%+ over four closes and is still falling; see
    `docs/FALLING_KNIFE.md`.
  - `account's equity` / cannot be priced: the check could not read the account or the price, so
    it refused (fail closed). Check the brokerage keys and network.

#### 2) Market data unavailable (yfinance)
- **Symptoms**: `market_data_error` / `history_error`, or a Falling Knife `market.status` of
  `unavailable` or `stale`.
- **Behaviour**: in live mode a BUY is refused while the daily bars cannot be read (unless
  `MARKET_GUARD_ON_DATA_ERROR=allow`); SELLs are not affected.
- **Mitigation**: wait for the provider to recover. Yahoo rate-limits bursts; the bars are cached
  for `OHLCV_CACHE_TTL_SEC` (60 s) and prices for `TICKER_CACHE_TTL_SEC` (5 s).

#### 3) Brokerage outage or rejected order
- **Symptoms**: `execution_error` with the brokerage's message, or `brokerage_not_configured`.
- **Mitigation**: set `TRADING_HALTED=true` and restart while the brokerage recovers; check the
  order and positions with the brokerage directly. This server does not cancel or list brokerage
  orders.

#### 4) Live policy refusals
- **Symptoms**: `ticker_not_allowed`, `brokerage_not_allowed`, `order_amount_too_large` or
  `invalid_policy_config`.
- **Triage**: the error data names the rule and its limit. `invalid_policy_config` means
  `MAX_ORDER_AMOUNT` is not a number; every live order is refused until it is fixed or unset.
- **Mitigation**: adjust `ALLOW_TICKERS`, `ALLOW_BROKERAGES` or `MAX_ORDER_AMOUNT` and restart.
  Keep `EXECUTION_APPROVAL_MODE=approve_each` while validating a new configuration.

### Backup/restore (paper mode)
- The paper ledger is `data/paper.db` (`PAPER_DB_PATH`; ignored by git). Back it up by copying the
  file while the processes are stopped. `reset_paper_wallet()` clears it.
