# UAT Log

> Rendered by `uat_log.py render` from `uat/runs/<run-id>/findings.json`. Do not hand-edit;
> update the ledger and re-render. Latest run is expanded; earlier runs are summarized.

## Run 2026-09-24-01 — ReadyTrader-Stocks

- Branch: `uat/2026-09-24-stocks`  |  Base: `main@e389057`
- Started: 2026-09-24T07:08:16+00:00  |  Updated: 2026-09-24T08:47:12+00:00
- Scope: Stacked on PR #3 (feat/market-falling-knife). In: MCP server (stdio) tools, paper trading, risk guardian, api_server approvals, docs/README/configs, CI, frontend build. Out: live brokerage orders (no credentials; live trading is a hard gate), Docker (no daemon in sandbox)
- Verdict: **CLEAN with BLOCKED items**
- Totals: 72 checks · 20 pass · 50 fail (50 verified fixed, 0 open, 0 fixed-unverified, 0 regressed, 0 wontfix) · 2 blocked

### User journeys exercised

- As an agent developer, I install ReadyTrader-Stocks from the README and connect it to my MCP client (Claude Desktop or Agent Zero) so that my agent can list and call its tools
- As a trading agent, I research a stock with get_stock_price, fetch_ohlcv and get_market_regime so that I can decide on a trade
- As a trading agent in paper mode, I fund the paper account and place a market order that passes the Risk Guardian so that I can practise with no real money
- As an operator, I rely on validate_trade_risk and the order path to refuse an unsafe BUY (oversized, or into a collapse) so that my agent cannot make an unrecoverable trade
- As an operator using approve_each, I review a pending trade and approve it through the API so that only trades I confirm execute
- As a strategy builder, I run a backtest and a synthetic stress test so that I can evaluate a strategy before trading it

### Section summary

| Section | Pass | Fail | Verified fixed | Blocked |
|---|---|---|---|---|
| preflight | 2 | 8 | 8 | 0 |
| backend | 8 | 18 | 18 | 0 |
| data | 1 | 2 | 2 | 0 |
| memory | 1 | 1 | 1 | 0 |
| frontend | 2 | 4 | 4 | 0 |
| integrations | 2 | 2 | 2 | 1 |
| cli | 1 | 2 | 2 | 0 |
| config | 1 | 7 | 7 | 0 |
| docs | 0 | 6 | 6 | 1 |
| regression | 2 | 0 | 0 | 0 |

### Findings (52)

#### PRE-03 — Fresh install can import the MCP server (python app/main.py)  [FAIL · critical · **VERIFIED**]

- Section: `preflight`  |  Journey: install and connect
- Steps: fresh python3.12 venv; pip install -r requirements-dev.txt; python app/main.py
- Expected: server starts on stdio
- Observed: ModuleNotFoundError: pydantic_settings. requirements.txt leaves mcp unpinned; mcp 2.x (released 2026-07-28) is resolved and dropped pydantic-settings, which fastmcp 2.14.1 imports. Every fresh install and Docker build since then fails at import
- Evidence: [PRE-03-start-documented.txt](evidence/2026-09-24-01/PRE-03-start-documented.txt)
- Fix: Pin mcp>=1.24.0,<2 in requirements.txt
  - Root cause: mcp unpinned; fastmcp 2.14.1 declares mcp>=1.24.0 with no upper bound and imports pydantic_settings, which mcp 2.x stopped depending on
  - Files: `requirements.txt`
  - Commit: `845e972`
  - Regression test: tests/test_server_startup.py::test_requirements_keep_the_mcp_sdk_on_1x
- Retest 1 (2026-09-24T07:17:32+00:00): **PASS** — fresh install: python app/main.py starts the stdio MCP server · evidence: [PRE-03-retest-start-documented.txt](evidence/2026-09-24-01/PRE-03-retest-start-documented.txt)

#### PRE-04 — MCP server registers its tools (python -m app.main, env with mcp 1.x)  [FAIL · critical · **VERIFIED**]

- Section: `preflight`  |  Journey: install and connect
- Steps: python -m app.main with the lock-file versions (fastmcp 2.14.1, mcp 1.25)
- Expected: server starts on stdio
- Observed: AttributeError: 'function' object has no attribute 'key' - every register_*_tools calls mcp.add_tool(<function>); fastmcp 2.14.1 add_tool takes a Tool object. The server has never been able to start with the pinned fastmcp; unit tests call the functions directly so they never noticed
- Evidence: [PRE-04-start-module.txt](evidence/2026-09-24-01/PRE-04-start-module.txt)
- Fix: Register every tool with mcp.tool(fn); register place_stock_order
  - Root cause: fastmcp 2.14.1 FastMCP.add_tool expects a Tool object; a bare function has no .key
  - Files: `app/tools/intelligence.py`, `app/tools/market.py`, `app/tools/research.py`, `app/tools/trading.py`
  - Commit: `845e972`
  - Regression test: tests/test_server_startup.py::test_the_documented_start_command_serves_mcp_over_stdio
- Retest 1 (2026-09-24T07:17:32+00:00): **PASS** — fresh install: 5/5 startup tests incl. a real stdio MCP session (initialize, list_tools, call validate_trade_risk) · evidence: [PRE-04-retest-start-module.txt](evidence/2026-09-24-01/PRE-04-retest-start-module.txt)

#### BE-01 — get_stock_price returns a price (MCP, stdio)  [FAIL · high · **VERIFIED**]

- Section: `backend`  |  Journey: research a stock
- Steps: call get_stock_price AAPL
- Expected: last price
- Observed: market_data_error: 'MarketDataBus' object has no attribute 'get_ticker' (get_multiple_prices likewise)
- Evidence: [BE-01-mcp-research-and-paper-order.txt](evidence/2026-09-24-01/BE-01-mcp-research-and-paper-order.txt)
- Fix: get_stock_price/get_multiple_prices use exchange_provider.fetch_ticker
  - Root cause: market tools called a non-existent MarketDataBus.get_ticker
  - Files: `app/tools/market.py`
  - Commit: `3f41a5a`
  - Regression test: tests/test_order_path.py::test_get_stock_price_returns_the_latest_quote
- Retest 1 (2026-09-24T07:30:27+00:00): **PASS** — get_stock_price AAPL last 337.02; get_multiple_prices AAPL+MSFT · evidence: [BE-01-retest-mcp-research-and-paper-order.txt](evidence/2026-09-24-01/BE-01-retest-mcp-research-and-paper-order.txt)

#### BE-02 — Live orders require LIVE_TRADING_ENABLED and respect TRADING_HALTED (README)  [FAIL · high · **VERIFIED**]

- Section: `backend`  |  Journey: refuse an unsafe BUY
- Steps: PAPER_MODE=false, LIVE_TRADING_ENABLED=false, TRADING_HALTED=true; place_stock_order to a fake brokerage
- Expected: refused before any brokerage call
- Observed: neither switch is read anywhere; the order went on to the policy check, which then failed with a TypeError (missing order_type) - so no live order has ever worked, and once that is fixed nothing would stop one
- Evidence: [BE-02-live-gates.txt](evidence/2026-09-24-01/BE-02-live-gates.txt)
- Fix: LIVE_TRADING_ENABLED and TRADING_HALTED enforced on the live order path and the approval API; policy call fixed; unconfigured brokerage refused
  - Root cause: documented switches never read; policy call missing a required keyword
  - Files: `app/tools/trading.py`, `app/api_server.py`
  - Commit: `3f41a5a`
  - Regression test: tests/test_order_path.py::test_a_live_order_needs_live_trading_enabled
- Retest 1 (2026-09-24T07:30:28+00:00): **PASS** — LIVE_TRADING_ENABLED=false -> live_trading_disabled; TRADING_HALTED=true -> trading_halted; both OK -> reaches the (fake) brokerage with order_type and price · evidence: [BE-02-retest-live-gates.txt](evidence/2026-09-24-01/BE-02-retest-live-gates.txt)

#### BE-04 — Paper market order executes (README: place_market_order('AAPL','buy',10))  [FAIL · high · **VERIFIED**]

- Section: `backend`  |  Journey: paper order
- Steps: deposit 100000 USD; place_market_order AAPL buy
- Expected: paper fill at the market price
- Observed: tool raises: 'Price for AAPL is unknown and pulse price was not provided' - the paper engine has no price source and the order path passed price=0; the error escapes as an MCP exception, not a JSON error
- Evidence: [BE-01-mcp-research-and-paper-order.txt](evidence/2026-09-24-01/BE-01-mcp-research-and-paper-order.txt)
- Fix: paper market orders fill at the reference price; execution errors are JSON
  - Root cause: order path passed price 0 and the paper engine has no price feed
  - Files: `app/tools/trading.py`
  - Commit: `3f41a5a`
  - Regression test: tests/test_order_path.py::test_a_paper_market_order_fills_at_the_reference_price
- Retest 1 (2026-09-24T07:30:28+00:00): **PASS** — place_market_order AAPL buy 10 -> Paper Trade Executed @ 337.02 · evidence: [BE-04-retest-mcp-research-and-paper-order.txt](evidence/2026-09-24-01/BE-04-retest-mcp-research-and-paper-order.txt)

#### BE-05 — Risk Guardian's 5%-of-portfolio size rule applies to market orders  [FAIL · high · **VERIFIED**]

- Section: `backend`  |  Journey: refuse an unsafe BUY
- Steps: place_market_order AAPL buy 60 shares (~20k) on a 100k paper account
- Expected: risk_blocked: position size too large
- Observed: passed the Risk Guardian and reached execution: a market order was valued at 1.0 per share (60 dollars), so any share count passed the size rule
- Evidence: [BE-01-mcp-research-and-paper-order.txt](evidence/2026-09-24-01/BE-01-mcp-research-and-paper-order.txt)
- Fix: orders valued at limit price / last close / quote for the size rule; unpriceable BUY fails closed
  - Root cause: est_px defaulted to 1.0 for market orders
  - Files: `app/tools/trading.py`
  - Commit: `3f41a5a`
  - Regression test: tests/test_order_path.py::test_a_market_order_is_valued_at_its_price_for_the_size_rule
- Retest 1 (2026-09-24T07:30:28+00:00): **PASS** — 60 shares on 100k: risk_blocked 'Position size too large (20.2%). Max allowed is 5%.' · evidence: [BE-05-retest-mcp-research-and-paper-order.txt](evidence/2026-09-24-01/BE-05-retest-mcp-research-and-paper-order.txt)

#### BE-11 — run_synthetic_stress_test tool (README section 'Synthetic Stress Testing')  [FAIL · high · **VERIFIED**]

- Section: `backend`  |  Journey: backtest and stress test
- Steps: call with an RSI strategy, scenarios=3
- Expected: summary + artifacts
- Observed: stress_test_error: run_synthetic_stress_test() takes 0 positional arguments but 2 were given - the tool calls a keyword-only core function positionally, so it fails on every call
- Evidence: [BE-07-mcp-risk-input-research.txt](evidence/2026-09-24-01/BE-07-mcp-risk-input-research.txt)
- Fix: call the keyword-only core with keywords
  - Root cause: positional call to a keyword-only function
  - Files: `app/tools/research.py`
  - Commit: `3f41a5a`
  - Regression test: tests/test_order_path.py::test_the_stress_test_tool_runs
- Retest 1 (2026-09-24T07:30:28+00:00): **PASS** — run_synthetic_stress_test returns artifacts and a summary for 3 scenarios · evidence: [BE-11-retest-mcp-risk-input-research.txt](evidence/2026-09-24-01/BE-11-retest-mcp-risk-input-research.txt)

#### BE-14 — GET /api/portfolio (the dashboard's portfolio panel)  [FAIL · high · **VERIFIED**]

- Section: `backend`  |  Journey: approve through the API
- Steps: GET /api/portfolio in paper mode
- Expected: 200 with balances and metrics
- Observed: 500 Internal Server Error: it calls paper_engine.get_balances(), which does not exist
- Evidence: [BE-14-portfolio.json](evidence/2026-09-24-01/BE-14-portfolio.json)
- Fix: PaperTradingEngine.get_balances; portfolio metrics include equity
  - Root cause: endpoint called a method that did not exist
  - Files: `core/paper.py`, `app/api_server.py`
  - Commit: `3f41a5a`
  - Regression test: tests/test_api_server.py::test_the_portfolio_view_returns_balances_and_equity
- Retest 1 (2026-09-24T07:30:28+00:00): **PASS** — 200 with balances and metrics.equity · evidence: [BE-14-retest-portfolio.json](evidence/2026-09-24-01/BE-14-retest-portfolio.json)

#### BE-19 — approve_each: a proposal made by the MCP server can be approved through the API  [FAIL · high · **VERIFIED**]

- Section: `backend`  |  Journey: approve through the API
- Steps: MCP server (approve_each, EXECUTION_DB_PATH=X) proposes a BUY; API server (same DB) lists and approves it
- Expected: listed and approvable
- Observed: the proposal is persisted (1 row) but the API lists nothing and answers 'Unknown request_id': each process scopes proposals to a random session id
- Evidence: [BE-19-cross-process-approval.txt](evidence/2026-09-24-01/BE-19-cross-process-approval.txt)
- Fix: EXECUTION_SESSION_ID shares the proposal namespace across processes (opt-in)
  - Root cause: per-process random session id scoped every persisted proposal
  - Files: `execution/store.py`
  - Commit: `3f41a5a`
  - Regression test: tests/test_api_server.py::test_a_shared_session_id_lets_the_api_see_and_confirm_the_servers_proposals
- Retest 1 (2026-09-24T07:30:28+00:00): **PASS** — with EXECUTION_SESSION_ID shared: the API lists the MCP server's proposal, refuses a wrong token, executes with the right one after the recheck, refuses a replay · evidence: [BE-19-retest-cross-process-approval.txt](evidence/2026-09-24-01/BE-19-retest-cross-process-approval.txt)

#### BE-21 — The order path sizes trades against the real account  [FAIL · high · **VERIFIED**]

- Section: `backend`  |  Journey: refuse an unsafe BUY
- Steps: paper account with 1,000 USD; BUY 1 AAPL at 330 (33% of the account)
- Expected: risk_blocked: position size too large
- Observed: executed: the order path read portfolio value from get_risk_metrics()['equity'], a key that does not exist, so every account (paper, and live, where it was never read) was sized as 100,000
- Evidence: [BE-20-fake-success.txt](evidence/2026-09-24-01/BE-20-fake-success.txt)
- Fix: portfolio value from the paper engine / brokerage account; BUY fails closed without it
  - Root cause: read a non-existent 'equity' key with a 100,000 default
  - Files: `app/tools/trading.py`
  - Commit: `880bfc4`
  - Regression test: tests/test_order_path.py::test_a_paper_order_is_sized_against_the_paper_account
- Retest 1 (2026-09-24T07:49:34+00:00): **PASS** — on the 1,000 USD account the 330 BUY (33%) is risk_blocked; after funding to 100,000 the same size passes the size rule · evidence: [BE-21-retest-fake-success.txt](evidence/2026-09-24-01/BE-21-retest-fake-success.txt)

#### BE-23 — approve_each + live: an approved proposal still passes the live policy (ALLOW_TICKERS, MAX_ORDER_AMOUNT)  [FAIL · high · **VERIFIED**]

- Section: `backend`
- Steps: API + MCP sharing EXECUTION_SESSION_ID/DB; PAPER_MODE=false LIVE_TRADING_ENABLED=true approve_each ALLOW_TICKERS=AAPL MAX_ORDER_AMOUNT=10, no keys; propose sell MSFT 1 and sell AAPL 500; approve via /api/approve-trade
- Expected: the proposal (or at the latest the approval) is refused with ticker_not_allowed / order_amount_too_large
- Observed: both are proposed and the approval goes straight past the policy to the brokerage step (400 'not configured with API keys'); with keys both would have been sent
- Evidence: [BE-23.txt](evidence/2026-09-24-01/BE-23.txt)
- Fix: live_order_refusal (switches + ALLOW_*/MAX_ORDER_AMOUNT policy) runs when a live order is proposed and again at execution, including /api/approve-trade
  - Root cause: the policy call lived only in the direct live execution branch; the proposal and approval paths skipped it
  - Files: `app/tools/trading.py`, `app/api_server.py`
  - Commit: `0beffae`
  - Regression test: tests/test_order_path.py
- Retest 1 (2026-09-24T08:07:19+00:00): **PASS** — proposals that break the policy are refused when proposed (ticker_not_allowed, order_amount_too_large); proposals created while the policy was unset are refused at approval with 409 and the rule's code · evidence: [BE-23-retest-2.txt](evidence/2026-09-24-01/BE-23-retest-2.txt)

#### CF-03 — TRADING_HALTED kill switch halts live orders for any 'on' value  [FAIL · high · **VERIFIED**]

- Section: `config`
- Steps: PAPER_MODE=false LIVE_TRADING_ENABLED=true TRADING_HALTED in {true,TRUE,1,yes,on}; call live_execution_refusal()
- Expected: every value refuses with trading_halted
- Observed: only true/TRUE halt; 1, yes and on leave live trading running (settings.TRADING_HALTED=False, refusal=None)
- Evidence: [CF-03.txt](evidence/2026-09-24-01/CF-03.txt)
- Fix: TRADING_HALTED halts on any value except empty/false/0/no/off (common/switches.kill_switch_on); PAPER_MODE stays on unless explicitly off, read the same way by config, the Alpaca client and the ws stream
  - Root cause: config compared the raw value to the exact word 'true'
  - Files: `common/switches.py`, `app/core/config.py`, `execution/alpaca_service.py`, `marketdata/ws_streams.py`, `tools/setup_wizard.py`
  - Commit: `1f542bc`
  - Regression test: tests/test_switches.py
- Retest 1 (2026-09-24T07:59:46+00:00): **PASS** — true, TRUE, 1, yes and on all halt: refusal code trading_halted · evidence: [CF-03-retest.txt](evidence/2026-09-24-01/CF-03-retest.txt)

#### CF-04 — EXECUTION_APPROVAL_MODE fails closed: a misspelt or commented value still requires approval  [FAIL · high · **VERIFIED**]

- Section: `config`
- Steps: paper mode; EXECUTION_APPROVAL_MODE in {approve_each, 'approve_each  # comment' (docker --env-file keeps inline comments), approve-each, 'APPROVE_EACH '}; place_market_order AAPL 1
- Expected: every variant returns a pending proposal
- Observed: 'approve_each  # auto or approve_each' (the env.example line as docker --env-file reads it) and 'approve-each' executed the order immediately with no approval
- Evidence: [CF-04.txt](evidence/2026-09-24-01/CF-04.txt)
- Fix: EXECUTION_APPROVAL_MODE: any value other than auto requires approval (common/switches.approval_mode); env.example has no inline comments (docker --env-file keeps them)
  - Root cause: raw string compared to 'approve_each'; env.example line carried an inline comment
  - Files: `common/switches.py`, `app/core/config.py`, `env.example`
  - Commit: `1f542bc`
  - Regression test: tests/test_switches.py
- Retest 1 (2026-09-24T07:59:46+00:00): **PASS** — all four variants, including the commented and misspelt ones, return a pending proposal with confirm_token; nothing executed · evidence: [CF-04-retest.txt](evidence/2026-09-24-01/CF-04-retest.txt)

#### CF-05 — An unparseable MAX_ORDER_AMOUNT fails closed  [FAIL · high · **VERIFIED**]

- Section: `config`
- Steps: live mode, no keys; MAX_ORDER_AMOUNT in {10, '1,000', '$500', '1O'}; sell AAPL 5000
- Expected: 10 refuses; the unparseable values refuse too (a limit the operator set must never silently vanish)
- Observed: '1,000', '$500' and '1O' are read as no limit: the 5000-share order passes policy and only stops at brokerage_not_configured (with keys it would have been sent)
- Evidence: [CF-05.txt](evidence/2026-09-24-01/CF-05.txt)
- Fix: MAX_ORDER_AMOUNT that is not a finite number raises invalid_policy_config; empty or unset means no limit
  - Root cause: _env_float returned the default (None = no limit) on a parse error
  - Files: `core/policy.py`
  - Commit: `0beffae`
  - Regression test: tests/test_order_path.py
- Retest 1 (2026-09-24T08:07:20+00:00): **PASS** — 10 refuses with order_amount_too_large; '1,000', '$500' and '1O' refuse with invalid_policy_config · evidence: [CF-05-retest.txt](evidence/2026-09-24-01/CF-05-retest.txt)

#### CF-06 — Brokerage sandbox switches read '1', 'yes' and 'TRUE' as sandbox  [FAIL · high · **VERIFIED**]

- Section: `config`
- Steps: TRADIER_SANDBOX / ETRADE_SANDBOX in {true, 1, yes, TRUE}; construct the brokerage clients; print base_url
- Expected: sandbox endpoint for every value
- Observed: TRADIER_SANDBOX=1/yes and ETRADE_SANDBOX=1/yes/TRUE point at the production APIs (api.tradier.com, api.etrade.com): an operator asking for the sandbox gets real orders
- Evidence: [CF-06.txt](evidence/2026-09-24-01/CF-06.txt)
- Fix: TRADIER_SANDBOX read with safety_switch_on (sandbox unless explicitly off); ETRADE_SANDBOX read with opt_in_switch_on and one api_host used for markets, orders and balances
  - Root cause: exact-string comparison to lowercase 'true'; E*TRADE balance URL hard-coded to production
  - Files: `common/switches.py`, `execution/tradier_service.py`, `execution/retail_services.py`, `env.example`
  - Commit: `060e2be`
  - Regression test: tests/test_switches.py
- Retest 1 (2026-09-24T08:12:08+00:00): **PASS** — true, 1, yes and TRUE all point Tradier and E*TRADE at their sandboxes · evidence: [CF-06-retest.txt](evidence/2026-09-24-01/CF-06-retest.txt)

#### DA-01 — Paper drawdown reflects real losses only  [FAIL · high · **VERIFIED**]

- Section: `data`  |  Journey: paper order
- Steps: deposit 100k; six 5% BUYs; sell the whole position at cost
- Expected: drawdown 0 (no loss)
- Observed: drawdown_pct 0.299 with equity unchanged at 100k: equity is snapshotted between the two legs of a trade, and the historical maximum is reported as the current drawdown - the Risk Guardian then blocks every BUY (>=10%) for good
- Evidence: [DA-01-paper-drawdown.txt](evidence/2026-09-24-01/DA-01-paper-drawdown.txt)
- Fix: one equity snapshot per trade; drawdown_pct is current, max_drawdown_pct historical
  - Root cause: deposit() snapshotted equity after each leg; get_risk_metrics returned the historical max as current
  - Files: `core/paper.py`
  - Commit: `c978713`
  - Regression test: tests/test_paper_metrics.py::test_selling_a_position_at_cost_is_not_a_drawdown
- Retest 1 (2026-09-24T07:34:26+00:00): **PASS** — drawdown ~0 (float noise 3e-16) after the buys and after selling at cost; equity 100k · evidence: [DA-01-retest-paper-drawdown.txt](evidence/2026-09-24-01/DA-01-retest-paper-drawdown.txt)

#### DOC-04 — smithery.yaml (the registry manifest) parses, describes this server and starts it  [FAIL · high · **VERIFIED**]

- Section: `docs`
- Steps: parse smithery.yaml with PyYAML (duplicate-key aware); compare with the Smithery stdio format (startCommand.type/configSchema/commandFunction)
- Expected: valid YAML in the registry's format, a stocks description and the up2itnow0822 URL
- Observed: the file does not parse (line 31: a quoted scalar followed by text), has a duplicate description key, describes a crypto/DeFi (Aave, Uniswap) server, points at github.com/up2itnow/ (wrong owner) and uses a top-level layout Smithery does not read (no commandFunction)
- Evidence: [DOC-04.txt](evidence/2026-09-24-01/DOC-04.txt)
- Fix: smithery.yaml rewritten in Smithery's stdio format: configSchema of real settings, commandFunction passing them as env to python app/main.py, exampleConfig
  - Root cause: copied from ReadyTrader-Crypto, hand-edited into invalid YAML
  - Files: `smithery.yaml`
  - Commit: `9e066f4`
- Retest 1 (2026-09-24T08:34:15+00:00): **PASS** — parses with no duplicate keys; every config key is in env.example; commandFunction(exampleConfig) -> python app/main.py with PAPER_MODE/EXECUTION_APPROVAL_MODE env, which starts the server with 20 tools · evidence: [DOC-04-retest.txt](evidence/2026-09-24-01/DOC-04-retest.txt)

#### FE-02 — Dashboard builds (npm run build)  [FAIL · high · **VERIFIED**]

- Section: `frontend`  |  Journey: approve through the API
- Steps: cd frontend && npm run build
- Expected: production build
- Observed: Type error: Cannot find name 'setPortfolio' (src/app/page.tsx:30) - the page cannot be built
- Evidence: [FE-02-build.txt](evidence/2026-09-24-01/FE-02-build.txt)
- Fix: portfolio state declared and rendered; build passes
  - Root cause: setPortfolio never declared
  - Files: `frontend/src/app/page.tsx`
  - Commit: `352bd67`
- Retest 1 (2026-09-24T07:37:21+00:00): **PASS** — next build compiles and prerenders / · evidence: [FE-02-retest-build.txt](evidence/2026-09-24-01/FE-02-retest-build.txt)

#### FE-03 — Dashboard shows the operator's real portfolio, not made-up figures  [FAIL · high · **VERIFIED**]

- Section: `frontend`  |  Journey: approve through the API
- Steps: read what page.tsx renders
- Expected: values from /api/portfolio
- Observed: hard-coded '$48,500.00', '+7.4% Today', a dummy equity chart and two invented strategies (+2.1%, -1.4%) are rendered as if real; the fetched portfolio is thrown away
- Evidence: [FE-03-fabricated-figures.txt](evidence/2026-09-24-01/FE-03-fabricated-figures.txt)
- Fix: render /api/portfolio; remove fabricated figures, dummy chart and invented strategies
  - Root cause: placeholder UI shipped as if real
  - Files: `frontend/src/app/page.tsx`
  - Commit: `352bd67`
- Retest 1 (2026-09-24T07:37:21+00:00): **PASS** — rendered page shows the API's $25,000.00 equity and AAPL balance; no 48,500 / +7.4% / invented strategies in page or source (screenshot FE-03-retest-dashboard.png) · evidence: [FE-03-retest-no-fabricated-figures.txt](evidence/2026-09-24-01/FE-03-retest-no-fabricated-figures.txt)

#### PRE-05 — Documented start command python app/main.py resolves the app package  [FAIL · high · **VERIFIED**]

- Section: `preflight`  |  Journey: install and connect
- Steps: python app/main.py from the repo root (README, Dockerfile CMD)
- Expected: imports app.*
- Observed: ModuleNotFoundError: No module named 'app' - running a file inside the package puts app/ on sys.path, not the repo root
- Evidence: [PRE-05-start-path.txt](evidence/2026-09-24-01/PRE-05-start-path.txt)
- Fix: app/main.py inserts the repo root on sys.path when run as a file
  - Root cause: python app/main.py puts app/ (not the repo root) first on sys.path
  - Files: `app/main.py`
  - Commit: `845e972`
  - Regression test: tests/test_server_startup.py::test_the_package_resolves_when_main_is_run_as_a_file
- Retest 1 (2026-09-24T07:17:32+00:00): **PASS** — no 'No module named' error; server starts · evidence: [PRE-05-retest-start-path.txt](evidence/2026-09-24-01/PRE-05-retest-start-path.txt)

#### PRE-07 — Documented demo: python examples/paper_quick_demo.py  [FAIL · high · **VERIFIED**]

- Section: `preflight`  |  Journey: paper order
- Steps: README '10-minute evaluation' step 1
- Expected: deposit, limit order, fill, balances, sell, metrics
- Observed: crashes at step 3: sqlite3.OperationalError: database is locked in PaperTradingEngine.check_open_orders -> _set_asset_price_usd
- Evidence: [PRE-07-paper-demo.txt](evidence/2026-09-24-01/PRE-07-paper-demo.txt)
- Fix: check_open_orders commits the fill before helpers open their own write connections
  - Root cause: an open write transaction on one sqlite connection while other connections try to write
  - Files: `core/paper.py`
  - Commit: `845e972`
  - Regression test: tests/test_paper_limit_fill.py
- Retest 1 (2026-09-24T07:17:33+00:00): **PASS** — demo completes all 6 steps, exit 0 · evidence: [PRE-07-retest-paper-demo.txt](evidence/2026-09-24-01/PRE-07-retest-paper-demo.txt)

#### PRE-09 — CI runs the project's tests  [FAIL · high · **VERIFIED**]

- Section: `preflight`
- Steps: read .github/workflows/ci.yml; PR #3's 'build' check
- Expected: CI installs Python deps and runs pytest/ruff
- Observed: CI runs 'npm install --if-present || true' and 'npm test --if-present || echo' at the repo root, which has no package.json: the job is always green (8 s on PR #3) and no Python test has ever run in CI - which is how the start-up crash (PRE-03/04) shipped
- Evidence: [PRE-09-ci-workflow.txt](evidence/2026-09-24-01/PRE-09-ci-workflow.txt)
- Fix: CI installs Python deps and runs ruff, pytest, bandit; builds and lints the dashboard
  - Root cause: workflow copied from a Node template
  - Files: `.github/workflows/ci.yml`
  - Commit: `352bd67`
- Retest 1 (2026-09-24T07:38:24+00:00): **PASS** — the workflow's steps run locally: ruff clean, 255 passed, bandit clean, dashboard lint + build OK (GitHub Actions confirms on push) · evidence: [PRE-09-retest-ci-steps-local.txt](evidence/2026-09-24-01/PRE-09-retest-ci-steps-local.txt)

#### BE-03 — fetch_ohlcv bars carry their timestamps  [FAIL · medium · **VERIFIED**]

- Section: `backend`  |  Journey: research a stock
- Steps: call fetch_ohlcv AAPL 1d limit 2
- Expected: ISO timestamps
- Observed: timestamp is '0', '1', ...: the row index overwrote the real bar time
- Evidence: [BE-01-mcp-research-and-paper-order.txt](evidence/2026-09-24-01/BE-01-mcp-research-and-paper-order.txt)
- Fix: fetch_ohlcv keeps bar timestamps as ISO UTC
  - Root cause: reset_index() added an index column that overwrote timestamp
  - Files: `app/tools/market.py`
  - Commit: `3f41a5a`
  - Regression test: tests/test_order_path.py::test_fetch_ohlcv_keeps_each_bars_timestamp
- Retest 1 (2026-09-24T07:30:28+00:00): **PASS** — timestamps 2026-09-22T04:00:00Z, 2026-09-23T04:00:00Z · evidence: [BE-03-retest-mcp-research-and-paper-order.txt](evidence/2026-09-24-01/BE-03-retest-mcp-research-and-paper-order.txt)

#### BE-08 — Malformed trade requests are refused (unknown side, non-positive amount)  [FAIL · medium · **VERIFIED**]

- Section: `backend`  |  Journey: refuse an unsafe BUY
- Steps: validate_trade_risk side=hold; amount_usd=-5
- Expected: invalid_request errors
- Observed: side 'hold' was treated as a SELL and allowed; a negative amount_usd was allowed; place_stock_order accepted the same
- Evidence: [BE-07-mcp-risk-input-research.txt](evidence/2026-09-24-01/BE-07-mcp-risk-input-research.txt)
- Fix: side must be buy/sell and amounts positive and finite
  - Root cause: no input validation
  - Files: `app/tools/trading.py`
  - Commit: `3f41a5a`
  - Regression test: tests/test_order_path.py::test_a_malformed_risk_check_is_refused
- Retest 1 (2026-09-24T07:30:28+00:00): **PASS** — side 'hold' and amount_usd -5 -> invalid_request with the reason · evidence: [BE-08-retest-mcp-risk-input-research.txt](evidence/2026-09-24-01/BE-08-retest-mcp-risk-input-research.txt)

#### BE-12 — API server starts as a file (python app/api_server.py)  [FAIL · medium · **VERIFIED**]

- Section: `backend`  |  Journey: approve through the API
- Steps: python app/api_server.py
- Expected: uvicorn serves the API
- Observed: ModuleNotFoundError: No module named 'app' (python -m app.api_server works; the README gives no start command at all)
- Evidence: [BE-12-api-start-as-file.txt](evidence/2026-09-24-01/BE-12-api-start-as-file.txt)
- Fix: api_server.py puts the repo root on sys.path when run as a file
  - Root cause: same packaging issue as app/main.py
  - Files: `app/api_server.py`
  - Commit: `3f41a5a`
  - Regression test: tests/test_server_startup.py::test_the_api_server_resolves_when_run_as_a_file
- Retest 1 (2026-09-24T07:30:28+00:00): **PASS** — python app/api_server.py -> Uvicorn running on 127.0.0.1 · evidence: [BE-12-retest-api-start-as-file.txt](evidence/2026-09-24-01/BE-12-retest-api-start-as-file.txt)

#### BE-20 — Failures are reported as failures (paper funds, limit fills, private streams)  [FAIL · medium · **VERIFIED**]

- Section: `backend`  |  Journey: paper order
- Steps: paper: limit BUY 330 with market 337; SELL 5 AAPL holding 1; live: start_brokerage_private_ws
- Expected: a resting/unfilled limit, an insufficient_funds error, a not-implemented error
- Observed: the limit BUY filled at 330 while AAPL traded at 337 (every paper limit filled at its own price); the oversized SELL returned ok:true with 'Insufficient fund...' as its result; start_brokerage_private_ws answered status 'connected' without connecting
- Evidence: [BE-20-fake-success.txt](evidence/2026-09-24-01/BE-20-fake-success.txt)
- Fix: paper fills at market, limits only when marketable; insufficient_funds error; private stream not_implemented
  - Root cause: engine filled at the limit; string results passed through as ok; stubbed stream
  - Files: `app/tools/trading.py`, `app/api_server.py`
  - Commit: `880bfc4`
  - Regression test: tests/test_order_path.py::test_a_paper_limit_below_the_market_does_not_fill
- Retest 1 (2026-09-24T07:49:34+00:00): **PASS** — limit 330 under market 337.02 -> limit_not_marketable; limit 345 fills at the market 337.02; SELL 5 holding 1 -> insufficient_funds; private stream -> not_implemented · evidence: [BE-20-retest-fake-success.txt](evidence/2026-09-24-01/BE-20-retest-fake-success.txt)

#### BE-22 — Live policy refusals (MAX_ORDER_AMOUNT, ALLOW_TICKERS, ALLOW_BROKERAGES) say which rule refused  [FAIL · medium · **VERIFIED**]

- Section: `backend`
- Steps: PAPER_MODE=false LIVE_TRADING_ENABLED=true, no keys; MAX_ORDER_AMOUNT=1 ALLOW_TICKERS=AAPL ALLOW_BROKERAGES=alpaca; sell AAPL 5, sell MSFT 1, sell AAPL via tradier
- Expected: order_amount_too_large / ticker_not_allowed / brokerage_not_allowed with the limit in data
- Observed: all three return code execution_error with an empty message and no data: the operator cannot tell which rule refused
- Evidence: [BE-22.txt](evidence/2026-09-24-01/BE-22.txt)
- Fix: PolicyError is caught and returned as its own code, message and data
  - Root cause: a generic except turned the dataclass exception (empty str) into execution_error
  - Files: `app/tools/trading.py`
  - Commit: `0beffae`
  - Regression test: tests/test_order_path.py
- Retest 1 (2026-09-24T08:07:19+00:00): **PASS** — order_amount_too_large, ticker_not_allowed and brokerage_not_allowed, each with its message and limits · evidence: [BE-22-retest.txt](evidence/2026-09-24-01/BE-22-retest.txt)

#### BE-24 — place_stock_order refuses an order type it cannot honour  [FAIL · medium · **VERIFIED**]

- Section: `backend`
- Steps: paper mode, USD 10000; place_stock_order AAPL buy 1 with order_type=stop, order_type=limit (no price), order_type=limit price=-5
- Expected: invalid_request; nothing fills
- Observed: all three filled at the market price (337.02): a limit with no price and an unsupported stop order became market orders
- Evidence: [BE-24.txt](evidence/2026-09-24-01/BE-24.txt)
- Fix: place_stock_order accepts only market and limit, and a limit needs a positive price
  - Root cause: order_type was never validated on the paper path
  - Files: `app/tools/trading.py`
  - Commit: `0beffae`
  - Regression test: tests/test_order_path.py
- Retest 1 (2026-09-24T08:07:20+00:00): **PASS** — stop, limit without price and limit at -5 all return invalid_request; nothing fills · evidence: [BE-24-retest.txt](evidence/2026-09-24-01/BE-24-retest.txt)

#### BE-25 — A backtest that fails reports failure (ok:false), not success  [FAIL · medium · **VERIFIED**]

- Section: `backend`
- Steps: run_backtest_simulation with a forbidden import, with no on_candle, and with a strategy that raises
- Expected: ok:false with an error code and the reason
- Observed: all three return ok:true with the failure buried in data.result.error; an agent checking ok reads them as successful backtests
- Evidence: [BE-25.txt](evidence/2026-09-24-01/BE-25.txt)
- Fix: run_backtest_simulation returns ok:false code backtest_error when the engine reports an error or raises
  - Root cause: the engine's error dict was wrapped in _json_ok
  - Files: `app/tools/research.py`
  - Commit: `e3ab436`
  - Regression test: tests/test_order_path.py
- Retest 1 (2026-09-24T08:09:45+00:00): **PASS** — all three failures return ok:false, code backtest_error, with the reason · evidence: [BE-25-retest.txt](evidence/2026-09-24-01/BE-25-retest.txt)

#### BE-26 — The approval API only answers the dashboard, and a cancel needs the proposal's token  [FAIL · medium · **VERIFIED**]

- Section: `backend`
- Steps: approve_each paper; propose over MCP; from Origin https://evil.example: GET /api/pending-approvals, CORS preflight for POST /api/approve-trade, POST approve=false with a guessed token
- Expected: no CORS grant for a foreign origin; cancel without the right confirm_token refused
- Observed: Access-Control-Allow-Origin: * on every route (any web page the operator visits can read the account and the pending proposals and POST approvals); a cancel with a guessed token succeeded (ok:true) and the proposal vanished
- Evidence: [BE-26.txt](evidence/2026-09-24-01/BE-26.txt)
- Fix: CORS origins from API_CORS_ORIGINS (default localhost:3000 / 127.0.0.1:3000, '*' ignored), GET/POST and content-type only; cancel checks the confirm_token
  - Root cause: allow_origins=['*'] left from scaffolding; store.cancel took only a request_id
  - Files: `app/api_server.py`, `execution/store.py`, `env.example`
  - Commit: `583b5c2`
  - Regression test: tests/test_api_server.py
- Retest 1 (2026-09-24T08:14:01+00:00): **PASS** — no Access-Control-Allow-Origin for https://evil.example (a browser blocks the read); the preflight for approve-trade is refused (400); a cancel with a guessed token returns ok:false and the proposal stays pending · evidence: [BE-26-retest.txt](evidence/2026-09-24-01/BE-26-retest.txt)

#### BE-28 — A news or sentiment source that cannot answer is reported as an error, not as news  [FAIL · medium · **VERIFIED**]

- Section: `integrations`
- Steps: over MCP: get_financial_news with an invalid NEWSAPI_KEY; with no keys: get_financial_news, get_market_news, get_social_sentiment, get_market_sentiment
- Expected: ok:false with a code (not_configured / source_unavailable) and the reason
- Observed: every one returns ok:true with the failure text as the payload ('NewsAPI Error: apiKeyInvalid', 'ALPHAVANTAGE_API_KEY missing', 'No sentiment APIs configured', 'CNN Fear & Greed unavailable (HTTP 404)'); an agent checking ok treats the error text as headlines
- Evidence: [BE-28.txt](evidence/2026-09-24-01/BE-28.txt)
- Fix: intelligence.core returns Unavailable (a str with a code) when a source cannot answer; the MCP tools turn it into ok:false not_configured / source_unavailable; RSS feed errors are no longer headlines
  - Root cause: source functions returned failure text through the same channel as news, and the tools wrapped everything in _json_ok
  - Files: `intelligence/core.py`, `app/tools/intelligence.py`
  - Commit: `6f3feb3`
  - Regression test: tests/test_source_errors.py
- Retest 1 (2026-09-24T08:23:12+00:00): **PASS** — invalid NewsAPI key and Alpha Vantage's invalid-key note -> source_unavailable; missing keys -> not_configured; refused Fear & Greed -> source_unavailable; all ok:false with the reason · evidence: [BE-28-retest.txt](evidence/2026-09-24-01/BE-28-retest.txt)

#### CF-07 — The Alpaca live path can target an Alpaca paper account, as Tradier's does its sandbox  [FAIL · medium · **VERIFIED**]

- Section: `config`
- Steps: PAPER_MODE=false with test keys; ALPACA_PAPER unset / true / false; construct AlpacaBrokerage; read the client's base URL
- Expected: a way to send the live order path to Alpaca's paper endpoint (Tradier defaults to its sandbox), so the brokerage path can be tested without real money
- Observed: always BaseURL.TRADING_LIVE: the live path has no paper/sandbox option for Alpaca, the recommended brokerage, so the first end-to-end test of the brokerage path is with real money
- Evidence: [CF-07.txt](evidence/2026-09-24-01/CF-07.txt)
- Fix: AlpacaBrokerage reads ALPACA_PAPER (default true, safety_switch_on) instead of PAPER_MODE
  - Root cause: the connector keyed its endpoint on PAPER_MODE, which is false whenever it is used
  - Files: `execution/alpaca_service.py`, `env.example`
  - Commit: `4fbca2c`
  - Regression test: tests/test_switches.py
- Retest 1 (2026-09-24T08:34:21+00:00): **PASS** — ALPACA_PAPER unset or true -> BaseURL.TRADING_PAPER; only ALPACA_PAPER=false reaches TRADING_LIVE · evidence: [CF-07-retest.txt](evidence/2026-09-24-01/CF-07-retest.txt)

#### CL-02 — tools/setup_wizard.py (docs/ERRORS.md: run it to generate .env)  [FAIL · medium · **VERIFIED**]

- Section: `cli`  |  Journey: install and connect
- Steps: run with 'n' answers
- Expected: checks this project's dependencies, data sources and keys; correct next step
- Observed: a crypto wizard: checks ccxt/web3 (not dependencies here) and offers to install them, pings Binance and CoinDesk, and says 'configure SIGNER_TYPE' and 'run fastmcp run server.py' - there is no server.py
- Evidence: [CL-02-setup-wizard.txt](evidence/2026-09-24-01/CL-02-setup-wizard.txt)
- Fix: wizard checks Stocks deps, data/news endpoints, brokerage keys; correct next step
  - Root cause: copied from the crypto server
  - Files: `tools/setup_wizard.py`
  - Commit: `615ac72`
- Retest 1 (2026-09-24T07:42:26+00:00): **PASS** — checks fastmcp/yfinance/pandas/pandas_ta/alpaca/feedparser/requests and Yahoo/MarketWatch; next step 'python app/main.py' · evidence: [CL-02-retest-setup-wizard.txt](evidence/2026-09-24-01/CL-02-retest-setup-wizard.txt)

#### DOC-01 — README, RUNBOOK and ops docs describe tools, settings and files that exist  [FAIL · medium · **VERIFIED**]

- Section: `docs`  |  Journey: install and connect
- Steps: every tool name, path, link and env var in README/RUNBOOK/docs checked against the running server and the tree
- Expected: all resolve
- Observed: README: 4 tools that do not exist (get_sentiment, check_orders, get_portfolio_balance, get_marketdata_capabilities), MAX_TRADE_AMOUNT (the variable is MAX_ORDER_AMOUNT), unread MARKETDATA_EXCHANGES and EVM ALLOW_CHAINS, a dead #-optional-web-ui anchor, RELEASE_READINESS_CHECKLIST.md (missing), dashboard features that do not exist (Mobile Guard push, multi-agent insights, charting), no API start command; RUNBOOK/EXCHANGES/MARKETDATA: 9 non-existent tools, CCXT and crypto-signer playbooks; docs/TOOLS.md: every index link is a dead anchor
- Evidence: [DOC-01-readme-and-ops-docs.txt](evidence/2026-09-24-01/DOC-01-readme-and-ops-docs.txt)
- Fix: README, RUNBOOK, docs/*.md and the prompt pack rewritten against the running server; TOOLS.md anchors use GitHub's slugs; a test fails when TOOLS.md drifts
  - Root cause: docs carried over from ReadyTrader-Crypto and earlier plans, never executed
  - Files: `README.md`, `RUNBOOK.md`, `docs/ERRORS.md`, `docs/EXCHANGES.md`, `docs/MARKETDATA.md`, `docs/README.md`, `docs/THREAT_MODEL.md`, `docs/POSITIONING.md`, `docs/SENTIMENT.md`, `prompts/READYTRADER_PROMPT_PACK.md`, `tools/generate_tool_docs.py`, `docs/TOOLS.md`
  - Commit: `9e066f4`
  - Regression test: tests/test_server_startup.py
- Retest 1 (2026-09-24T08:34:15+00:00): **PASS** — no unregistered tool, broken anchor or missing path remains (the 5 left are expected: uat/UAT-LOG.md is rendered at closeout, CONTRIBUTING's ../../issues/new is a GitHub-relative link, and three README names are the user's own config files); TOOLS.md regenerates identically; Prompt 1 runs as written (fill, limit_not_marketable, risk_blocked); RUNBOOK curls and the README backtest/regime examples return what the docs say · evidence: [DOC-01-retest-2.txt](evidence/2026-09-24-01/DOC-01-retest-2.txt)

#### DOC-03 — docker build copies only the server into the image, and the Dockerfile's API hint runs  [FAIL · medium · **VERIFIED**]

- Section: `docs`
- Steps: apply .dockerignore to the repo as docker build would (top-level and nested patterns); read the Dockerfile's sidecar hint
- Expected: a small context; no .venv, .git, local data (paper ledger, audit log) or UAT evidence in the image; a runnable API command
- Observed: a 1.18 GB context: frontend/node_modules and .next, .venv, .git and data/ (the local paper ledger and audit log) would be copied into the image; the hint 'uvicorn api_server:app' fails (the module is app.api_server)
- Evidence: [DOC-03.txt](evidence/2026-09-24-01/DOC-03.txt)
- Fix: .dockerignore excludes .venv, .git, data/, artifacts/, uat/, frontend/node_modules and .next, _deprecated/; the Dockerfile's API hint is 'python app/api_server.py' with API_HOST=0.0.0.0
  - Root cause: .dockerignore predated the dashboard and local venvs; the hint named a module path that never existed
  - Files: `.dockerignore`, `Dockerfile`, `.gitignore`
  - Commit: `9e066f4`
- Retest 1 (2026-09-24T08:34:15+00:00): **PASS** — 0.7 MB context with no .venv, .git, data, uat or artifacts; the Dockerfile's API command serves /api/health on 0.0.0.0 · evidence: [DOC-03-retest.txt](evidence/2026-09-24-01/DOC-03-retest.txt)

#### DOC-05 — Every shipped entry point runs: docker-compose.sentinel.yml / sentinel/  [FAIL · medium · **VERIFIED**]

- Section: `docs`
- Steps: import sentinel.app as the compose file's uvicorn command does; read the compose file
- Expected: it runs, or it is not shipped
- Observed: sentinel/app.py imports a 'signing' package that does not exist in this repo (ModuleNotFoundError): a crypto transaction-signer left over from ReadyTrader-Crypto, wired in compose with SIGNER_TYPE=env_private_key and PRIVATE_KEY; a stocks server signs nothing
- Evidence: [DOC-05.txt](evidence/2026-09-24-01/DOC-05.txt)
- Fix: sentinel/ and docker-compose.sentinel.yml moved (git mv) to _deprecated/ with a README; .dockerignore excludes it
  - Root cause: crypto signer carried over from ReadyTrader-Crypto without its signing package
  - Files: `_deprecated/README.md`, `_deprecated/sentinel/app.py`, `_deprecated/docker-compose.sentinel.yml`
  - Commit: `9e066f4`
- Retest 1 (2026-09-24T08:34:15+00:00): **PASS** — sentinel/ and the compose file are only under _deprecated/, referenced nowhere else and excluded from the image · evidence: [DOC-05-retest.txt](evidence/2026-09-24-01/DOC-05-retest.txt)

#### DOC-06 — SECURITY.md tells a reporter where to send a vulnerability  [FAIL · medium · **VERIFIED**]

- Section: `docs`
- Steps: read SECURITY.md; look for the code it describes
- Expected: a private reporting channel; only true statements
- Observed: 'Please report details privately with:' lists what to include but no channel (no address, no link); it also claims a 'credential provider abstraction' the code does not have
- Evidence: [DOC-06.txt](evidence/2026-09-24-01/DOC-06.txt)
- Fix: SECURITY.md points at GitHub private vulnerability reporting (security/advisories/new) and states how keys and the approval API are handled
  - Root cause: template text without a channel; a crypto-era claim
  - Files: `SECURITY.md`
  - Commit: `f9938df`
- Retest 1 (2026-09-24T08:44:53+00:00): **PASS** — SECURITY.md names the private reporting channel (GitHub security advisories) and no longer claims a credential-provider abstraction; whether private vulnerability reporting is switched on in the repo settings could not be checked from here · evidence: [DOC-06-retest.txt](evidence/2026-09-24-01/DOC-06-retest.txt)

#### DOC-07 — The documented Docker MCP configs keep the paper ledger between sessions  [FAIL · medium · **VERIFIED**]

- Section: `docs`
- Steps: read configs/agent_zero.mcp.yaml, configs/claude_desktop.mcp-server-config.json, the README examples and the Dockerfile
- Expected: the ledger survives a client restart, as README's 'persistent balances' promises
- Observed: every config runs 'docker run -i --rm' with no volume; the ledger is /app/data/paper.db inside the container, so each session starts from an empty paper account (not run here: no Docker daemon, see DOC-02)
- Evidence: [DOC-07.txt](evidence/2026-09-24-01/DOC-07.txt)
- Fix: configs and README Docker examples mount readytrader-stocks-data:/app/data
  - Root cause: configs written without persistence in mind
  - Files: `configs/agent_zero.mcp.yaml`, `configs/claude_desktop.mcp-server-config.json`, `README.md`
  - Commit: `f9938df`
  - Regression test: tests/test_configs.py
- Retest 1 (2026-09-24T08:44:53+00:00): **PASS** — both configs and all four README examples mount readytrader-stocks-data:/app/data; the config tests pass · evidence: [DOC-07-retest.txt](evidence/2026-09-24-01/DOC-07-retest.txt)

#### FE-05 — Mode indicator, approval control and API URL  [FAIL · medium · **VERIFIED**]

- Section: `frontend`  |  Journey: approve through the API
- Steps: read layout.tsx / page.tsx
- Expected: mode read from the server; Review works; NEXT_PUBLIC_API_URL honoured
- Observed: 'Paper Mode' is hard-coded (it would show in live mode too); 'Review' has no handler; the portfolio fetch hard-codes localhost:8000; logo reads REALTRADER
- Evidence: [FE-05-mode-pill.txt](evidence/2026-09-24-01/FE-05-mode-pill.txt)
- Fix: ModePill reads /api/health; Approve prompts for the confirm_token; API_URL module; READYTRADER logo
  - Root cause: hard-coded mode, dead button, hard-coded URL
  - Files: `frontend/src/components/ModePill.tsx`, `frontend/src/app/page.tsx`, `frontend/src/lib/api.ts`, `frontend/src/app/layout.tsx`, `frontend/src/hooks/usePendingApprovals.ts`, `frontend/src/app/globals.css`
  - Commit: `352bd67`
- Retest 1 (2026-09-24T07:37:21+00:00): **PASS** — with the API stopped the pill reads 'API offline' and the portfolio card says the API is not reachable (the failed requests are those calls); with it running the pill reads 'Paper Mode' (FE-03-retest-dashboard.json) · evidence: [FE-05-retest-api-offline.json](evidence/2026-09-24-01/FE-05-retest-api-offline.json)

#### IN-04 — get_market_news, fetch_rss_news and get_market_sentiment  [FAIL · medium · **VERIFIED**]

- Section: `integrations`  |  Journey: research a stock
- Steps: get_market_news AAPL; fetch_rss_news; get_market_sentiment
- Expected: news or a clear 'unavailable'
- Observed: get_market_news raises TypeError (the tool passes a symbol the core function does not take); fetch_rss_news treats its url argument as a ticker filter over fixed feeds, so it never returns anything; CNN answers 418 and that is reported as 'UNKNOWN (0.0)'
- Evidence: [IN-04-news-tools.txt](evidence/2026-09-24-01/IN-04-news-tools.txt)
- Fix: news tools call their core functions with matching arguments; refused Fear & Greed reads as unavailable
  - Root cause: tool/core signature drift; response status ignored
  - Files: `intelligence/core.py`, `app/tools/intelligence.py`
  - Commit: `abc58c9`
  - Regression test: tests/test_order_path.py::test_get_market_news_passes_the_ticker
- Retest 1 (2026-09-24T07:40:18+00:00): **PASS** — get_market_news explains the missing key; fetch_rss_news returns Yahoo Finance headlines; Fear & Greed reports 'unavailable (HTTP 404)' instead of a made-up 0.0 · evidence: [IN-04-retest-news-tools.txt](evidence/2026-09-24-01/IN-04-retest-news-tools.txt)

#### PRE-01 — README local install (pip install -r requirements-dev.txt) on the default python3  [FAIL · medium · **VERIFIED**]

- Section: `preflight`  |  Journey: install and connect
- Steps: python3 -m venv v && v/bin/pip install -r requirements-dev.txt
- Expected: dependencies install
- Observed: Python 3.11: pandas_ta has no release for <3.12 ('No matching distribution found'). pyproject says requires-python >=3.12 but the README never states a Python version
- Evidence: [PRE-01-install.txt](evidence/2026-09-24-01/PRE-01-install.txt)
- Fix: README states Python 3.12+ and shows the python3.12 venv steps
  - Root cause: pyproject requires-python >=3.12 was never surfaced in the README
  - Files: `README.md`
  - Commit: `845e972`
- Retest 1 (2026-09-24T07:17:32+00:00): **PASS** — README states Python 3.12+; the documented python3.12 install succeeds (mcp 1.30.0, fastmcp 2.14.1, pydantic-settings present) · evidence: [PRE-01-retest-install.txt](evidence/2026-09-24-01/PRE-01-retest-install.txt)

#### PRE-08 — Documented demo: python examples/stress_test_demo.py  [FAIL · medium · **VERIFIED**]

- Section: `preflight`  |  Journey: backtest and stress test
- Steps: README '10-minute evaluation' step 2
- Expected: stress lab artifacts under artifacts/demo_stress/
- Observed: No such file: examples/stress_test_demo.py does not exist (examples/ has paper_quick_demo, simulation_demo, verify_live_strategy, verify_stocks)
- Evidence: [PRE-08-stress-demo.txt](evidence/2026-09-24-01/PRE-08-stress-demo.txt)
- Fix: README and paper demo point at examples/simulation_demo.py
  - Root cause: demo renamed without updating the README
  - Files: `README.md`, `examples/paper_quick_demo.py`
  - Commit: `845e972`
- Retest 1 (2026-09-24T07:17:33+00:00): **PASS** — README names examples/simulation_demo.py; it writes the 5 artifacts, exit 0 · evidence: [PRE-08-retest-stress-demo.txt](evidence/2026-09-24-01/PRE-08-retest-stress-demo.txt)

#### PRE-10 — Run as the README's 'Without Docker' config does (another working directory): the paper ledger stays with the install  [FAIL · medium · **VERIFIED**]

- Section: `preflight`
- Steps: cd to an empty folder; <venv>/python <repo>/app/main.py over MCP; deposit + paper order; list files written
- Expected: state lands in <repo>/data (or a configured directory), whatever folder the client starts in
- Observed: data/paper.db, compliance_audit.log, strategies.db and insights.db are created under the client's working directory: the ledger silently changes with the launch folder, and a client that starts servers in / (not writable) breaks the first order
- Evidence: [PRE-10.txt](evidence/2026-09-24-01/PRE-10.txt)
- Fix: common/paths.data_path anchors every default data file to <repo>/data (READYTRADER_DATA_DIR overrides); ensure_parent creates folders
  - Root cause: defaults were cwd-relative strings
  - Files: `common/paths.py`, `core/paper.py`, `app/core/compliance.py`, `execution/store.py`, `intelligence/insights.py`, `observability/audit.py`, `strategy/marketplace.py`, `common/idempotency.py`, `env.example`
  - Commit: `96979b4`
  - Regression test: tests/test_paths.py
- Retest 1 (2026-09-24T08:27:19+00:00): **PASS** — nothing is written under the client's working directory; the ledger, audit log and stores are in <repo>/data · evidence: [PRE-10-retest.txt](evidence/2026-09-24-01/PRE-10-retest.txt)

#### BE-27 — deposit_paper_funds accepts only a positive amount  [FAIL · low · **VERIFIED**]

- Section: `backend`
- Steps: paper mode, empty ledger: deposit 1000 USD, then -50000, then 0; then buy 1 AAPL
- Expected: the negative and zero deposits are refused with invalid_request
- Observed: -50000 is accepted as a 'deposit' and the paper cash goes to -49000; 0 is accepted; the account is left negative
- Evidence: [BE-27.txt](evidence/2026-09-24-01/BE-27.txt)
- Fix: deposit_paper_funds validates amount (positive, finite) and asset (non-empty)
  - Root cause: no input validation on the deposit tool
  - Files: `app/tools/trading.py`
  - Commit: `70e5a3c`
  - Regression test: tests/test_order_path.py
- Retest 1 (2026-09-24T08:16:33+00:00): **PASS** — -50000 and 0 refused with invalid_request; the ledger stays at 1000 USD · evidence: [BE-27-retest.txt](evidence/2026-09-24-01/BE-27-retest.txt)

#### CF-01 — env.example lists the variables the code reads  [FAIL · low · **VERIFIED**]

- Section: `config`  |  Journey: install and connect
- Steps: scan getenv/environ in the source vs env.example
- Expected: every setting discoverable
- Observed: 74 variables read, 16 in env.example: missing include TWITTER_BEARER_TOKEN, ALPHAVANTAGE_API_KEY, PAPER_DB_PATH, EXECUTION_DB_PATH, MAX_ORDER_AMOUNT, ALLOW_TICKERS, MARKET_TIMEZONE/HOURS, the IBKR/E*TRADE/Schwab/Robinhood credentials and the market-data tuning; DEBUG is listed but never read
- Evidence: [CF-01-env-vs-example.txt](evidence/2026-09-24-01/CF-01-env-vs-example.txt)
- Fix: env.example lists every variable read (prefixed aliases noted), grouped and commented; DEBUG removed
  - Root cause: settings added over time without updating the example
  - Files: `env.example`
  - Commit: `0eb9304`
- Retest 1 (2026-09-24T07:44:31+00:00): **PASS** — only the READYTRADER_-prefixed aliases (documented by a note) and the unused CIRCUIT_BREAKER_PCT (commented) are not listed; nothing listed is unread · evidence: [CF-01-retest-env-vs-example.txt](evidence/2026-09-24-01/CF-01-retest-env-vs-example.txt)

#### CF-08 — A .env copied from env.example holds no placeholder credentials  [FAIL · low · **VERIFIED**]

- Section: `config`
- Steps: cp env.example .env (README step), run tools/setup_wizard.py from the repo root, then call get_financial_news over MCP
- Expected: no keys reported; tools say the key is not set
- Observed: the wizard reports ALPACA_API_KEY, ALPACA_API_SECRET and TRADIER_ACCESS_TOKEN 'detected' (the your_* placeholders), and get_financial_news calls NewsAPI with 'your_newsapi_key' (apiKeyInvalid)
- Evidence: [CF-08.txt](evidence/2026-09-24-01/CF-08.txt)
- Fix: placeholder credentials in env.example commented out
  - Root cause: env.example set your_* values that read as configured keys
  - Files: `env.example`
  - Commit: `fd75c1c`
  - Regression test: tests/test_switches.py
- Retest 1 (2026-09-24T08:23:39+00:00): **PASS** — with .env copied from env.example the wizard reports the brokerage keys not set and get_financial_news answers not_configured · evidence: [CF-08-retest.txt](evidence/2026-09-24-01/CF-08-retest.txt)

#### CL-03 — examples/verify_stocks.py and verify_live_strategy.py  [FAIL · low · **VERIFIED**]

- Section: `cli`
- Steps: run both
- Expected: they verify the install
- Observed: verify_stocks.py calls an async method without awaiting it and reports 'FAILED market data' (it would also write to the real paper DB); verify_live_strategy.py imports execution.stock_executor, which does not exist
- Evidence: [CL-03-verify-examples.txt](evidence/2026-09-24-01/CL-03-verify-examples.txt)
- Fix: verify scripts use current APIs and a temporary paper DB; SMA strategy registers pandas_ta
  - Root cause: scripts left behind by refactors; missing pandas_ta import
  - Files: `examples/verify_stocks.py`, `examples/verify_live_strategy.py`, `strategy/moving_average.py`
  - Commit: `615ac72`
  - Regression test: tests/test_strategy_sma.py::test_the_strategy_module_registers_the_pandas_ta_accessor_itself
- Retest 1 (2026-09-24T07:42:26+00:00): **PASS** — verify_stocks: quote + paper trade in a temp DB, SUCCESS; verify_live_strategy: Alpaca unavailable without keys, SMA result without error, SUCCESS · evidence: [CL-03-retest-verify-examples.txt](evidence/2026-09-24-01/CL-03-retest-verify-examples.txt)

#### DA-02 — Equity counts funds reserved by open limit orders  [FAIL · low · **VERIFIED**]

- Section: `data`  |  Journey: paper order
- Steps: place a resting limit BUY for 4,000
- Expected: equity unchanged (100k)
- Observed: equity 96,000: the reserved cash disappears from the valuation until the order fills
- Evidence: [DA-01-paper-drawdown.txt](evidence/2026-09-24-01/DA-01-paper-drawdown.txt)
- Fix: get_portfolio_value_usd adds funds reserved by open limit orders
  - Root cause: reserved funds were deducted from balances and not counted anywhere
  - Files: `core/paper.py`
  - Commit: `c978713`
  - Regression test: tests/test_paper_metrics.py::test_a_resting_limit_order_keeps_its_reserved_funds_in_equity
- Retest 1 (2026-09-24T07:34:26+00:00): **PASS** — equity stays 100,000 with a resting 4,000 limit BUY · evidence: [DA-02-retest-paper-drawdown.txt](evidence/2026-09-24-01/DA-02-retest-paper-drawdown.txt)

#### FE-04 — Navigation links lead to pages  [FAIL · low · **VERIFIED**]

- Section: `frontend`
- Steps: layout.tsx nav vs src/app routes
- Expected: every link has a page
- Observed: /strategy, /history and /settings have no page (404); only / exists
- Evidence: [FE-04-dead-nav.txt](evidence/2026-09-24-01/FE-04-dead-nav.txt)
- Fix: remove nav links without pages
  - Root cause: planned pages never built
  - Files: `frontend/src/app/layout.tsx`
  - Commit: `352bd67`
- Retest 1 (2026-09-24T07:37:21+00:00): **PASS** — only the Dashboard link remains; it has a page · evidence: [FE-04-retest-nav.txt](evidence/2026-09-24-01/FE-04-retest-nav.txt)

#### ME-02 — Insight fields are validated (signal bullish/bearish/neutral, confidence 0..1)  [FAIL · low · **VERIFIED**]

- Section: `memory`
- Steps: post signal 'sideways-ish' with confidence 7.5
- Expected: invalid_request
- Observed: stored as-is; a 7.5 'confidence' then ranks as the most confident insight
- Evidence: [ME-01-insights-write-restart-read.txt](evidence/2026-09-24-01/ME-01-insights-write-restart-read.txt)
- Fix: post_market_insight validates signal, confidence and ttl
  - Root cause: no validation of documented field ranges
  - Files: `app/tools/research.py`
  - Commit: `06c41c0`
  - Regression test: tests/test_order_path.py::test_an_insight_outside_the_documented_fields_is_refused
- Retest 1 (2026-09-24T07:35:31+00:00): **PASS** — 'sideways-ish'/7.5 -> invalid_request; a valid insight is stored and, once its TTL passes, no longer returned · evidence: [ME-02-retest-insights-validation.txt](evidence/2026-09-24-01/ME-02-retest-insights-validation.txt)

#### DOC-02 — README Docker build and run (docker build -t readytrader-stocks .)  [BLOCKED · **BLOCKED**]

- Section: `docs`  |  Journey: install and connect
- Steps: docker build; docker run -i
- Expected: image builds, server answers on stdio
- Observed: not run: no Docker daemon in this sandbox (docker.sock absent); the build context and the Dockerfile's commands were checked without one (DOC-03, DOC-07)
- Blocked on: a machine with Docker: docker build -t readytrader-stocks . then run configs/claude_desktop.mcp-server-config.json's command and list the tools
- Evidence: [DOC-02-docker-daemon.txt](evidence/2026-09-24-01/DOC-02-docker-daemon.txt)

#### IN-02 — Alpaca / Tradier live brokerage  [BLOCKED · **BLOCKED**]

- Section: `integrations`
- Steps: live order with brokerage keys
- Expected: order accepted by the broker
- Observed: not run: no ALPACA_*/TRADIER_* credentials here, and live trading is outside this run's authority (fake-brokerage tests cover the path up to the broker call, BE-02, BE-23)
- Blocked on: Alpaca paper-account keys (ALPACA_API_KEY/ALPACA_API_SECRET) with ALPACA_PAPER=true (the default): run PAPER_MODE=false LIVE_TRADING_ENABLED=true EXECUTION_APPROVAL_MODE=approve_each and approve one small order through the API
- Evidence: [IN-02-brokerage-credentials.txt](evidence/2026-09-24-01/IN-02-brokerage-credentials.txt)

### Passed checks (20)

| ID | Section | Check | Observed |
|---|---|---|---|
| PRE-02 | preflight | README local install on Python 3.12 (the version pyproject requires) | installs; pip check clean; fastmcp 2.14.1 |
| PRE-06 | preflight | Test-suite baseline | 214 passed |
| BE-06 | backend | get_market_regime and deposit_paper_funds | VOLATILE_RANGING (ADX 19.5); Deposited 100000.0 USD |
| BE-09 | backend | Missing required arguments give a readable MCP validation error | fastmcp validation: 'Missing required argument' for both fields |
| BE-10 | backend | run_backtest_simulation runs a strategy and its sandbox refuses imports | pnl +11.91% over 2 trades; 'Importing os is forbidden' |
| BE-13 | backend | GET /api/health | 200 {status: ok, mode: paper} |
| BE-15 | backend | GET /api/pending-approvals | 200 {pending: []} |
| BE-16 | backend | POST /api/approve-trade with an empty body | 422 with missing-field details |
| BE-17 | backend | POST /api/approve-trade for an unknown request_id | 400 Unknown request_id |
| BE-18 | backend | Cancel an unknown proposal | 200 {ok: false} |
| DA-03 | data | Paper balances survive a restart | USD 96000.0, AAPL 0.0 read back after the restart |
| ME-01 | memory | Shared agent insights: write, read back, restart, case, unicode/html | stored as AAPL, returned for AAPL and aapl before and after the restart; '<b>beat</b> ... ✓ ünïcode' unchanged |
| FE-01 | frontend | Dashboard lint (npm run lint) | eslint exits 0 |
| FE-06 | frontend | Dashboard at phone width (390x844) | no console/page errors, Portfolio card present |
| IN-01 | integrations | yfinance market data (real call) | AAPL 337.02, MSFT quote, dated daily bars |
| IN-03 | integrations | Social and financial news without credentials say how to enable them | names TWITTER_BEARER_TOKEN / REDDIT_* and NEWSAPI_KEY |
| CL-01 | cli | tools/generate_tool_docs.py regenerates docs/TOOLS.md | 20 tools; TOOLS.md unchanged (and test_the_tool_catalog_matches_the_server pins it to the server) |
| CF-02 | config | No secrets in the tree or published history | 0 key-pattern matches over 18 commits; no .env/.pem tracked (tests use a dummy key 0x...01) |
| REG-01 | regression | Regression sweep: all six journeys end to end on the final code, and the dashboard on its documented port | 20 tools; prices/bars/regime; paper fill at 337.02; 20% and 337% BUYs refused (Position size too large); proposal approved via API and filled; portfolio shows 7 AAPL; 400/422 for bad approvals; dashboard ok with no failed requests or console errors under the restricted CORS; backtest + stress test run; RSS works, keyed sources say not_configured; both demos exit 0; no stray files |
| REG-02 | regression | CI's checks on the final code: ruff, pytest, bandit, dashboard lint and build | ruff clean; full pytest suite passes; bandit no issues; dashboard lint and production build succeed |

### Run notes

- 2026-09-24T08:40:27+00:00: IN-02 unblock path: with ALPACA_PAPER=true (now the default) the live order path can be exercised end to end against an Alpaca paper account; it needs ALPACA_API_KEY/ALPACA_API_SECRET for a paper account, which this environment does not have.
- 2026-09-24T08:44:53+00:00: Adversarial pass (cold start, done in-session because a second reviewer agent could not be started): re-read the rendered log; every VERIFIED retest capture from this session was opened and shows the fixed behaviour; both brokerage place_order callers are behind live_order_refusal; remaining exact-'true' parses are opt-ins (LIVE_TRADING_ENABLED, IBKR_ENABLED, the unused MARKETDATA_FAIL_CLOSED). It found two more gaps, both fixed: DOC-06 (SECURITY.md had no reporting channel) and DOC-07 (Docker configs lost the paper ledger each session).

---
