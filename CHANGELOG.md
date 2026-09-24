## Changelog

This project follows a lightweight changelog format.

### Unreleased

#### Release UAT (every item was found by running the product, fixed, and retested; see `uat/`)
- **The server starts**: it could not start at all. Tools were registered with an API FastMCP no longer has, `mcp` 2.x (which dropped a module FastMCP imports) was installed by default, and `python app/main.py` failed on imports. The `mcp` SDK is pinned below 2 and both servers run as files, the way the README and MCP clients launch them.
- **CI runs the tests**: the workflow only installed frontend packages. It now runs ruff, pytest and bandit on Python 3.12, and builds the dashboard.
- **Live orders obey the switches**: `LIVE_TRADING_ENABLED` and the `TRADING_HALTED` kill switch were documented but never read. Every live order, and every approval of one, now checks both; the kill switch halts on any value other than empty/false/0/no/off, and `PAPER_MODE` stays on unless explicitly off.
- **The live policy applies on every path**: `ALLOW_TICKERS`, `ALLOW_BROKERAGES` and `MAX_ORDER_AMOUNT` were skipped for `approve_each` proposals and their approvals. They are checked when a live order is proposed and again when it executes; a refusal names its rule; an unreadable `MAX_ORDER_AMOUNT` refuses live orders instead of meaning "no limit".
- **`EXECUTION_APPROVAL_MODE` fails closed**: a misspelling, or the `env.example` line as `docker --env-file` reads it (with its inline comment), executed orders with no approval. Any value other than `auto` now requires approval, and `env.example` has no inline comments or placeholder keys.
- **Brokerage sandboxes by default**: Alpaca orders go to the Alpaca paper account unless `ALPACA_PAPER=false` (the connector used to key off `PAPER_MODE`, which is always false when it is used); `TRADIER_SANDBOX=1`/`yes` and `ETRADE_SANDBOX=1`/`yes`/`TRUE` no longer reach production.
- **Orders are sized against the real account**: the size rule used a hardcoded $100,000 account and valued a share at $1. It now uses the paper ledger's equity (or the brokerage's in live mode) and the latest price, and a BUY it cannot size is refused.
- **Paper trading tells the truth**: market orders fill at the latest price, a limit fills only when marketable (`limit_not_marketable`), `insufficient_funds` is an error, deposits must be positive, drawdown no longer spikes between the legs of a trade, and an unknown order type is refused instead of filling at the market.
- **Approvals work across processes**: the MCP server and the API server now share proposals through `EXECUTION_DB_PATH` + `EXECUTION_SESSION_ID`; a cancel needs the proposal's `confirm_token`, and the API answers only the dashboard's origin (`API_CORS_ORIGINS`) instead of any web page.
- **No fake successes**: news and sentiment tools whose source cannot answer return `not_configured` / `source_unavailable` instead of the error text as news; a failed backtest is `backtest_error`; `start_brokerage_private_ws` says `not_implemented` instead of "connected".
- **The dashboard shows the real account**: it displayed hardcoded balances and a fabricated chart. It now reads `/api/portfolio` and `/api/health`, and approving asks for the proposal's `confirm_token`.
- **Files stay with the install**: the paper ledger and stores were written under whatever folder the MCP client started the server in; they now live in `<repo>/data/` (`READYTRADER_DATA_DIR` moves them).
- **Docs match the product**: README, RUNBOOK, ERRORS, EXCHANGES, MARKETDATA, THREAT_MODEL, POSITIONING and the prompt pack were rewritten against the running server (they described tools, streams and risk rules that do not exist); `docker build` no longer copies `.venv`, `.git`, `node_modules` or the local ledger into the image.
- **Registry manifest and leftovers**: `smithery.yaml` did not parse and described a crypto/DeFi server; it is rewritten in Smithery's stdio format and starts this server. A transaction-signer left over from ReadyTrader-Crypto (`sentinel/`, `docker-compose.sentinel.yml`), which could not start, moved to `_deprecated/`.

#### Earlier in this release
- **Falling Knife now reads prices (security-relevant)**: every BUY - through `validate_trade_risk` and every order tool - reads the stock's last 40 daily bars (cached, one fetch per symbol per minute) and is refused while the stock is down 15%+ from its highest close of the last four sessions and still at its lowest close. SELLs are never blocked by it. On 64 stocks the rule had never seen (2000-2026) a buy on the days it fires fell a further 10% within ten sessions 49% of the time, against 13% on all days. Method, results and caveats: `docs/FALLING_KNIFE.md`; reproduction scripts: `research/falling_knife/`.
- **Missing market data is explicit**: if the bars cannot be read, a BUY is blocked in live mode and allowed-but-flagged in paper mode (`MARKET_GUARD_ON_DATA_ERROR=block|allow` overrides; an unknown value blocks). `MARKET_GUARD_ENABLED=false` turns the check off. The `market` block in every verdict says what was read and why.
- **A missing bar for today's session counts as stale**: once today's session has opened (`MARKET_TIMEZONE`, `MARKET_HOURS_START`, Monday to Friday) the provider must have today's bar, or the rule would read yesterday's closes and miss a collapse happening now. On an exchange holiday that reads as stale, the safe answer: a BUY would fill at the next open.
- **Approvals are rechecked**: with `EXECUTION_APPROVAL_MODE=approve_each`, `/api/approve-trade` re-runs the Risk Guardian with fresh bars before it executes, because a proposal can wait until it expires while the market moves. A refused approval answers `409 risk_blocked` and executes nothing.
- **`MARKET_GUARD_ENABLED` fails closed**: only `false`, `0`, `no` or `off` turns the check off; a typo such as `treu` used to disable it silently.
- **`CIRCUIT_BREAKER_PCT` is documented as unused**: no check ever read it.
- **Share classes resolve**: market data for `BRK.B`-style symbols (the broker form) failed because Yahoo writes `BRK-B`; a dotted symbol with no data is now retried in Yahoo's form. Without this, a live BUY of a share class would have been blocked by the new check's missing-data policy.
- **`docs/TOOLS.md` regenerated**: it still showed the old signatures (no `sentiment_score`) and descriptions.
- **Tests**: 74 new tests, including real-bar fixtures (SVB, COVID, 2025 tariff shock, and days the rule must allow) whose expectations come from the independent research code.
- **Falling Knife gate repaired (security-relevant)**: `analyze_social_sentiment` added a flat `+0.2` for each configured source, so the "sentiment score" measured how many API keys were set rather than what anyone was saying. A panicking feed and a euphoric feed both scored `+0.4`, and the only reachable values were `0.0`, `0.2` and `0.4`. The rule blocks below `-0.5`, so it could never fire.
- **The order path was a bypass**: every order entry point passed a hardcoded `sentiment_score = 0.0` to the Risk Guardian, and passed neither daily loss nor drawdown. Three risk rules were therefore inert on every real order even though `validate_trade_risk` applied them. They now apply.
- **Nothing fabricates a sentiment number any more**: `get_social_sentiment(symbol)` returns the posts themselves, for the calling agent to read and judge. A deterministic text scorer was built and measured first; `docs/SENTIMENT.md` records what it scored and why it was rejected. On three corpora written blind to its vocabulary it caught about one crash in eight, and blocked buys on ordinary days — a sector peer crashing, a broad market down day, an earnings beat quoting business metrics.
- **The agent can supply its own reading**: `validate_trade_risk(..., sentiment_score=...)` and every order entry point accept a score on `[-1, +1]`, clamped, and the response records `source` as `agent_supplied` rather than as a measurement.
- **The absence of a measurement is visible**: every verdict carries a `sentiment` block (`score`, `source`, `status`, `posts_available`, `posts_age_seconds`) with a `hint`, so a neutral `0.0` is never mistaken for a measured calm market.
- **Cache keyed by normalised symbol**: `$AAPL`, `aapl` and `NASDAQ:AAPL` reach one entry, while `BRK.A` and `BRK.B` stay distinct. Expiry uses the monotonic clock, so a wall-clock step cannot pin or expire an entry, and expired entries are evicted rather than accumulating.
- **`get_market_sentiment` tool fixed**: the MCP wrapper called the underlying function with a `symbol` argument it does not accept, raising `TypeError` on every call. It is market-wide and now takes no argument.
- **48 new tests** covering the contract above. No new dependency.
- **Stock Focus Transition**: Completed full refactor from crypto-focused connections to stock brokerage architecture.
- **WebSocket Streams**: Replaced crypto streams (Binance/Coinbase/Kraken) with Alpaca stock streaming.
- **Execution Routing**: Updated router terminology to focus on stock brokerages and retail execution.
- **Tool Catalog**: Cleaned up MCP tools to remove crypto-specific actions (`swap_tokens`, `get_crypto_price`, etc.).
- **Documentation**: Fully rebranded all docs from ReadyTrader-Crypto to ReadyTrader-Stocks.

### 0.1.0 (2025-12-29)
- **Initial Release (Crypto Focus)**: Agent-first MCP server for crypto trading workflows.
- **Safety governance**: risk disclosure, kill switch, approve-each execution.
- **Execution**: CEX via CCXT + DEX swaps.
- **Stress lab**: deterministic synthetic stress testing.
