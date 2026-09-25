## UAT run `2026-09-24-01` — ready for release review (1 item blocked on brokerage credentials)

Acting as the user, exercised every surface of ReadyTrader-Stocks end to end (MCP server over stdio,
approval API, dashboard, CLI scripts, config, docs, registry manifest), fixed every failure on this
branch, and retested each fix with fresh evidence. Money paths ran in paper mode or against
brokerage stubs only; no live order was placed.

**Stacked on #3** (`feat/market-falling-knife`, the price-based Falling Knife). Review and merge #3
first; this PR's diff is the UAT work on top of it.

**Totals:** 109 checks · 25 pass · 83 fail (83 fixed & verified) · 1 blocked · 409 tests pass, ruff and bandit clean, dashboard lints and builds.

| Section | Pass | Fail | Verified fixed | Blocked |
|---|---|---|---|---|
| preflight | 3 | 8 | 8 | 0 |
| backend | 8 | 33 | 33 | 0 |
| data | 1 | 6 | 6 | 0 |
| memory | 1 | 1 | 1 | 0 |
| frontend | 2 | 7 | 7 | 0 |
| integrations | 2 | 6 | 6 | 1 |
| cli | 1 | 3 | 3 | 0 |
| config | 1 | 11 | 11 | 0 |
| docs | 1 | 8 | 8 | 0 |
| regression | 5 | 0 | 0 | 0 |

### What was broken and is now fixed
- **critical** PRE-03 — Fresh install can import the MCP server (python app/main.py) → Pin mcp>=1.24.0,<2 in requirements.txt (`845e972`)
- **critical** PRE-04 — MCP server registers its tools (python -m app.main, env with mcp 1.x) → Register every tool with mcp.tool(fn); register place_stock_order (`845e972`)
- **high** BE-01 — get_stock_price returns a price (MCP, stdio) → get_stock_price/get_multiple_prices use exchange_provider.fetch_ticker (`3f41a5a`)
- **high** BE-02 — Live orders require LIVE_TRADING_ENABLED and respect TRADING_HALTED (README) → LIVE_TRADING_ENABLED and TRADING_HALTED enforced on the live order path and the approval API; policy call fixed; unconfigured brokerage refused (`3f41a5a`)
- **high** BE-04 — Paper market order executes (README: place_market_order('AAPL','buy',10)) → paper market orders fill at the reference price; execution errors are JSON (`3f41a5a`)
- **high** BE-05 — Risk Guardian's 5%-of-portfolio size rule applies to market orders → orders valued at limit price / last close / quote for the size rule; unpriceable BUY fails closed (`3f41a5a`)
- **high** BE-11 — run_synthetic_stress_test tool (README section 'Synthetic Stress Testing') → call the keyword-only core with keywords (`3f41a5a`)
- **high** BE-14 — GET /api/portfolio (the dashboard's portfolio panel) → PaperTradingEngine.get_balances; portfolio metrics include equity (`3f41a5a`)
- **high** BE-19 — approve_each: a proposal made by the MCP server can be approved through the API → EXECUTION_SESSION_ID shares the proposal namespace across processes (opt-in) (`3f41a5a`)
- **high** BE-21 — The order path sizes trades against the real account → portfolio value from the paper engine / brokerage account; BUY fails closed without it (`880bfc4`)
- **high** BE-23 — approve_each + live: an approved proposal still passes the live policy (ALLOW_TICKERS, MAX_ORDER_AMOUNT) → live_order_refusal (switches + ALLOW_*/MAX_ORDER_AMOUNT policy) runs when a live order is proposed and again at execution, including /api/approve-trade (`0beffae`)
- **high** CF-03 — TRADING_HALTED kill switch halts live orders for any 'on' value → TRADING_HALTED halts on any value except empty/false/0/no/off (common/switches.kill_switch_on); PAPER_MODE stays on unless explicitly off, read the same way by config, the Alpaca client and the ws stream (`1f542bc`)
- **high** CF-04 — EXECUTION_APPROVAL_MODE fails closed: a misspelt or commented value still requires approval → EXECUTION_APPROVAL_MODE: any value other than auto requires approval (common/switches.approval_mode); env.example has no inline comments (docker --env-file keeps them) (`1f542bc`)
- **high** CF-05 — An unparseable MAX_ORDER_AMOUNT fails closed → MAX_ORDER_AMOUNT that is not a finite number raises invalid_policy_config; empty or unset means no limit (`0beffae`)
- **high** CF-06 — Brokerage sandbox switches read '1', 'yes' and 'TRUE' as sandbox → TRADIER_SANDBOX read with safety_switch_on (sandbox unless explicitly off); ETRADE_SANDBOX read with opt_in_switch_on and one api_host used for markets, orders and balances (`060e2be`)
- **high** DA-01 — Paper drawdown reflects real losses only → one equity snapshot per trade; drawdown_pct is current, max_drawdown_pct historical (`c978713`)
- **high** DOC-04 — smithery.yaml (the registry manifest) parses, describes this server and starts it → smithery.yaml rewritten in Smithery's stdio format: configSchema of real settings, commandFunction passing them as env to python app/main.py, exampleConfig (`9e066f4`)
- **high** FE-02 — Dashboard builds (npm run build) → portfolio state declared and rendered; build passes (`352bd67`)
- **high** FE-03 — Dashboard shows the operator's real portfolio, not made-up figures → render /api/portfolio; remove fabricated figures, dummy chart and invented strategies (`352bd67`)
- **high** PRE-05 — Documented start command python app/main.py resolves the app package → app/main.py inserts the repo root on sys.path when run as a file (`845e972`)
- **high** PRE-07 — Documented demo: python examples/paper_quick_demo.py → check_open_orders commits the fill before helpers open their own write connections (`845e972`)
- **high** PRE-09 — CI runs the project's tests → CI installs Python deps and runs ruff, pytest, bandit; builds and lints the dashboard (`352bd67`)
- **medium** BE-03 — fetch_ohlcv bars carry their timestamps → fetch_ohlcv keeps bar timestamps as ISO UTC (`3f41a5a`)
- **medium** BE-08 — Malformed trade requests are refused (unknown side, non-positive amount) → side must be buy/sell and amounts positive and finite (`3f41a5a`)
- **medium** BE-12 — API server starts as a file (python app/api_server.py) → api_server.py puts the repo root on sys.path when run as a file (`3f41a5a`)
- **medium** BE-20 — Failures are reported as failures (paper funds, limit fills, private streams) → paper fills at market, limits only when marketable; insufficient_funds error; private stream not_implemented (`880bfc4`)
- **medium** BE-22 — Live policy refusals (MAX_ORDER_AMOUNT, ALLOW_TICKERS, ALLOW_BROKERAGES) say which rule refused → PolicyError is caught and returned as its own code, message and data (`0beffae`)
- **medium** BE-24 — place_stock_order refuses an order type it cannot honour → place_stock_order accepts only market and limit, and a limit needs a positive price (`0beffae`)
- **medium** BE-25 — A backtest that fails reports failure (ok:false), not success → run_backtest_simulation returns ok:false code backtest_error when the engine reports an error or raises (`e3ab436`)
- **medium** BE-26 — The approval API only answers the dashboard, and a cancel needs the proposal's token → CORS origins from API_CORS_ORIGINS (default localhost:3000 / 127.0.0.1:3000, '*' ignored), GET/POST and content-type only; cancel checks the confirm_token (`583b5c2`)
- **medium** BE-28 — A news or sentiment source that cannot answer is reported as an error, not as news → intelligence.core returns Unavailable (a str with a code) when a source cannot answer; the MCP tools turn it into ok:false not_configured / source_unavailable; RSS feed errors are no longer headlines (`6f3feb3`)
- **medium** CF-07 — The Alpaca live path can target an Alpaca paper account, as Tradier's does its sandbox → AlpacaBrokerage reads ALPACA_PAPER (default true, safety_switch_on) instead of PAPER_MODE (`4fbca2c`)
- **medium** CL-02 — tools/setup_wizard.py (docs/ERRORS.md: run it to generate .env) → wizard checks Stocks deps, data/news endpoints, brokerage keys; correct next step (`615ac72`)
- **medium** DOC-01 — README, RUNBOOK and ops docs describe tools, settings and files that exist → README, RUNBOOK, docs/*.md and the prompt pack rewritten against the running server; TOOLS.md anchors use GitHub's slugs; a test fails when TOOLS.md drifts (`9e066f4`)
- **medium** DOC-03 — docker build copies only the server into the image, and the Dockerfile's API hint runs → .dockerignore excludes .venv, .git, data/, artifacts/, uat/, frontend/node_modules and .next, _deprecated/; the Dockerfile's API hint is 'python app/api_server.py' with API_HOST=0.0.0.0 (`9e066f4`)
- **medium** DOC-05 — Every shipped entry point runs: docker-compose.sentinel.yml / sentinel/ → sentinel/ and docker-compose.sentinel.yml moved (git mv) to _deprecated/ with a README; .dockerignore excludes it (`9e066f4`)
- **medium** DOC-06 — SECURITY.md tells a reporter where to send a vulnerability → SECURITY.md points at GitHub private vulnerability reporting (security/advisories/new) and states how keys and the approval API are handled (`f9938df`)
- **medium** DOC-07 — The documented Docker MCP configs keep the paper ledger between sessions → configs and README Docker examples mount readytrader-stocks-data:/app/data (`f9938df`)
- **medium** FE-05 — Mode indicator, approval control and API URL → ModePill reads /api/health; Approve prompts for the confirm_token; API_URL module; READYTRADER logo (`352bd67`)
- **medium** IN-04 — get_market_news, fetch_rss_news and get_market_sentiment → news tools call their core functions with matching arguments; refused Fear & Greed reads as unavailable (`abc58c9`)
- **medium** PRE-01 — README local install (pip install -r requirements-dev.txt) on the default python3 → README states Python 3.12+ and shows the python3.12 venv steps (`845e972`)
- **medium** PRE-08 — Documented demo: python examples/stress_test_demo.py → README and paper demo point at examples/simulation_demo.py (`845e972`)
- **medium** PRE-10 — Run as the README's 'Without Docker' config does (another working directory): the paper ledger stays with the install → common/paths.data_path anchors every default data file to <repo>/data (READYTRADER_DATA_DIR overrides); ensure_parent creates folders (`96979b4`)
- **low** BE-27 — deposit_paper_funds accepts only a positive amount → deposit_paper_funds validates amount (positive, finite) and asset (non-empty) (`70e5a3c`)
- **low** CF-01 — env.example lists the variables the code reads → env.example lists every variable read (prefixed aliases noted), grouped and commented; DEBUG removed (`0eb9304`)
- **low** CF-08 — A .env copied from env.example holds no placeholder credentials → placeholder credentials in env.example commented out (`fd75c1c`)
- **low** CL-03 — examples/verify_stocks.py and verify_live_strategy.py → verify scripts use current APIs and a temporary paper DB; SMA strategy registers pandas_ta (`615ac72`)
- **low** DA-02 — Equity counts funds reserved by open limit orders → get_portfolio_value_usd adds funds reserved by open limit orders (`c978713`)
- **low** FE-04 — Navigation links lead to pages → remove nav links without pages (`352bd67`)
- **low** ME-02 — Insight fields are validated (signal bullish/bearish/neutral, confidence 0..1) → post_market_insight validates signal, confidence and ttl (`06c41c0`)

Commit ids above are from the local UAT history recorded in the ledger; the pushed branch carries
the same changes in fewer commits (the GitHub connector used here writes whole trees).

### Follow-up: found while testing ReadyTrader-FOREX
The same probes run against ReadyTrader-FOREX, and an independent review of that run, found defects
that also existed here. Each was captured here first, then fixed and retested:
- **high** BE-30 — Selling out of a position is never sized as new exposure → orders are judged by the exposure they add (paper ledger / brokerage positions); selling out passes the size, daily-loss and drawdown rules; selling beyond a live position (a short) is sized (`5fb2edf`)
- **high** BE-32 — A proposal executes in the mode it was proposed in → proposals record paper_mode; the approval API refuses the other mode (409 `mode_mismatch`) (`5fb2edf`)
- **medium** FE-07 — The dashboard is readable at phone width (390x844) → below 900 px the sidebar becomes a top bar and the grid one column (`fb843a5`)
- **medium** FE-08 — The operator can see what a proposal is before approving it, and can reject it → the pending list carries each order (never the token); the Guard Rail shows it with Approve and Reject (`5fb2edf`)
- **low** BE-29 — Approval errors → unknown proposal 404, wrong token 403, no longer approvable 409 (`d9d65b6`)
- **low** BE-31 — The large-trade verdict no longer promises a confirmation nothing asks for (`5fb2edf`)
- **low** BE-33 — The API's WebSocket answers only the dashboard's origins (`5fb2edf`)
- **low** CF-09 — A malformed setting that nothing applies (`CIRCUIT_BREAKER_PCT`, `RATE_LIMIT_DEFAULT_PER_MIN`) no longer stops the server (`491e203`)
- **low** CL-04 — The setup wizard treats a closed stdin as no answer instead of crashing (`03bdc44`)

### Follow-up: defect classes found in ReadyTrader-Crypto (`XR-*`)
Two adversarial reviews of the Crypto run found classes of defects that could exist in all three servers; an independent probe of this repo reproduced ten of them, and one more (XR-11) came from the FOREX probe. All fixed here, each with a regression test in `tests/test_uat_review_2026_09_24.py` that fails on the code before the fix:
- **critical** XR-01 — The Risk Guardian values an order at the market price, not the caller's → Valued at the market (limit: max(limit, market)); market-order price dropped; no market price refuses exposure-adding orders; the approval re-check passes order_type (`f84a5fc`)
- **high** XR-02 — Docs say which loss limits apply to live orders → Live checks report inactive_rules [daily_loss_limit, max_drawdown]; docs say the loss rules run on the paper account (`f84a5fc`, `477c34c`)
- **high** XR-03 — A paper deposit does not end a drawdown halt → Time-weighted performance index; deposits recorded (valued when made) and excluded from returns (`f84a5fc`)
- **high** XR-04 — Paper loss limits and sizing read the account at today's prices → _mark_paper_prices marks holdings to the latest quote before every check; the current value ends the metrics series (`f84a5fc`)
- **high** XR-11 — A live approve_each order needs an approval the agent cannot give itself → API_OPERATOR_TOKEN gates /api/ (not /api/health) and is required to approve live proposals, checked before the proposal is consumed; the dashboard asks for it once per tab (`f84a5fc`, `9f0d0bf`, `477c34c`)
- **medium** XR-05 — The daily-loss rule measures today's loss → Baseline = previous UTC day's last snapshot, else the day-open mark written at the first check of the day (`f84a5fc`)
- **medium** XR-06 — A ticker never collides with the paper ledger's cash → _invalid_symbol refuses '/' and, in paper mode, a ticker spelled like the cash asset (`f84a5fc`)
- **medium** XR-07 — A market order's price and the sentiment score are validated → Market-order price dropped; non-finite sentiment refused; the pending list replaces non-finite floats (`f84a5fc`)
- **medium** XR-08 — The Docker build context keeps secrets and local state out → Every cache/secret/database pattern is **/; the image runs as readytrader (uid 10001) (`a4b0937`)
- **low** XR-09 — API responses and logs identify each request and do not leak internals → request_context middleware: X-Request-ID, per-request log id, security headers, JSON internal_error; log_event stamps ts_ms at emit time (`f84a5fc`)
- **low** XR-10 — Live orders reach the brokerage with the normalised symbol → place_stock_order normalises the symbol once and uses it everywhere (`f84a5fc`)

### Follow-up: classes from the FOREX cross-review, and an adversarial review of all fixes (`XR-12..14`, `AR-*`)
The FOREX cross-review found three more classes here, and a separate agent then tried to refute every fix above. Each finding was captured here first, fixed with a regression test that fails on the code before it, and retested (the regression sweep and CI gate re-ran afterwards: REG-05, REG-06):
- **high** AR-01 — The operator token cannot be steered past (Host header, root path) → require_operator is a dependency of the operator_api router holding every protected route. (`ecc181d`)
- **high** XR-14 — A live Alpaca order fills now or not at all → Alpaca orders are sent only while the market is open (clock checked first; failure refuses), market orders DAY, limits IOC. Docs: other brokerages' limits can rest and are not counted; the kill switch refuses closes; flatten at the broker. (`b1fa4e8`)
- **medium** AR-02 — The dashboard can read a 401 and ask for the operator token → CORS is added after request_context and wraps every answer. (`ecc181d`)
- **medium** AR-03 — The operator switches answer first, and refused orders are audited → trade_start is recorded after validation; live_execution_refusal answers first in place_stock_order; at approval the switches answer before the proposal is consumed and live_order_refusal runs before pre_trade_check. (`ecc181d`)
- **low** AR-04 — Approving while the market is closed keeps the proposal → AlpacaBrokerage.market_closed_reason(); place_stock_order answers market_closed before proposing; the approval checks it before confirming; MarketClosed maps to 409 market_closed. (`ecc181d`)
- **low** AR-05 — A fractional Alpaca limit is refused before it is sent → A fractional limit is refused before sending, with the reason. (`ecc181d`)
- **low** AR-06 — The answer says what an IOC order filled → The order is read back until its state is final (up to ~3 s): status, filled_qty, filled_avg_price, time_in_force; cancelled unfilled raises (execution_error); the tool descriptions and TOOLS.md say how live Alpaca orders fill. (`ecc181d`)
- **low** AR-07 — Every numeric tool parameter refuses true → app/tools/params.py defines Number and Integer; every numeric tool parameter uses one. (`ecc181d`)
- **low** AR-08 — A whole-share Alpaca market order cannot wait out a trading halt → Whole-share market orders go out IOC; fractional ones DAY (Alpaca's rule), documented. (`ecc181d`)
- **low** AR-09 — An existing Docker data volume keeps working after the upgrade → RUNBOOK 'Upgrading a Docker data volume' and a CHANGELOG breaking note give the one-time chown to uid 10001. (`ecc181d`)
- **low** AR-10 — The docs describe the daily-loss baseline and the closed market as the code does → RUNBOOK gives the daily baseline as computed; FALLING_KNIFE.md says a live Alpaca order is refused as market_closed. (`ecc181d`)
- **low** XR-12 — The Smithery listing offers only settings that work there → EXECUTION_APPROVAL_MODE is no longer offered; commandFunction passes only the listed settings and sets 'auto'. (`b1fa4e8`)
- **low** XR-13 — An MCP client cannot send true where a tool takes a number → Amounts, prices, values and scores on every tool are typed Number (float with a validator that refuses booleans before conversion); the JSON schema stays 'number'. (`b1fa4e8`)

### Still blocked (needs the owner)
- **IN-02** live brokerage round trip: needs Alpaca **paper-account** keys (`ALPACA_API_KEY`, `ALPACA_API_SECRET`). With `ALPACA_PAPER=true` (now the default) the whole live path can be exercised with no real money: set `PAPER_MODE=false`, `LIVE_TRADING_ENABLED=true`, `EXECUTION_APPROVAL_MODE=approve_each`.
- **Repo setting**: SECURITY.md now points reporters at GitHub private vulnerability reporting; switch it on under Settings → Code security if it is off (not visible from here).

### Review these fixes with extra care
- **Breaking, live Alpaca orders fill now or not at all** (XR-14, AR-04..AR-08): orders are sent only while the market is open (else `market_closed`, before anything is proposed, and at approval before the proposal is used up), as `IOC` (a fractional market order as `DAY`, which Alpaca requires; a fractional limit is refused); the answer reads the order back (`filled_qty`, `filled_avg_price`) and an IOC cancelled unfilled is an `execution_error`. Exercised against a fake Alpaca that follows Alpaca's documented rules; the paper-account round trip (IN-02) would confirm it against Alpaca itself.
- **Operator token** (AR-01): the check is a dependency of the `operator_api` router, not a path check in a middleware (a `Host: …#` header or a root path got past that); CORS is now outermost (AR-02).
- **Switches first** (AR-03): with no keys, a halted or disabled live order answers `trading_halted` / `live_trading_disabled` (it answered `brokerage_not_configured`); refused orders are audited.
- **Breaking, sizing** (XR-01): every order is valued at the latest market price (a limit at the higher of limit and market); a market order's `price` is ignored; with no market price an order that adds exposure is refused. Tests that sized orders at a caller's price were adjusted.
- **Breaking, approvals** (XR-11): with `API_OPERATOR_TOKEN` set, the whole `/api/` surface (not `/api/health`) needs `Authorization: Bearer`; a live proposal cannot be approved without it. The dashboard asks for it once per tab.
- **Paper loss limits** (XR-03..05): a time-weighted index replaces raw equity; holdings are marked to the latest quote before each check, which adds one quote fetch per held ticker per check.
- **Docker** (XR-08, AR-09): the image runs as uid 10001; a volume an earlier root image wrote stops the server at start-up until handed over once (RUNBOOK, "Upgrading a Docker data volume"; verified with Docker on a fresh volume).
- **Trading gates** (`app/tools/trading.py`, `app/api_server.py`, `core/policy.py`, `common/switches.py`): `live_order_refusal` now runs at proposal and at execution; `TRADING_HALTED`, `PAPER_MODE`, `EXECUTION_APPROVAL_MODE` and `MAX_ORDER_AMOUNT` parsing all fail closed (BE-02, BE-23, CF-03, CF-04, CF-05).
- **Brokerage endpoints** (`execution/alpaca_service.py`, `execution/tradier_service.py`, `execution/retail_services.py`): live-mode Alpaca orders now go to the Alpaca **paper** account unless `ALPACA_PAPER=false`, a deliberate default change (CF-07); sandbox switches parse 1/yes/TRUE (CF-06).
- **Sizing** (BE-05, BE-21): orders are valued at the latest price and sized against the paper ledger's or the brokerage's real equity; a BUY that cannot be sized is refused.
- **Approval API contract** (BE-26, BE-29, BE-32, BE-33): CORS limited to the dashboard origins (`API_CORS_ORIGINS`), the WebSocket too; cancelling needs the `confirm_token`; errors answer 404/403/409; a proposal made in the other mode is refused (`mode_mismatch`).
- **Exits** (BE-30): selling out of a position is no longer refused by the size, daily-loss or drawdown rules; an unsupported or unconfigured brokerage is refused before any check.
- **Tool response contract** (BE-25, BE-28, BE-20): failures that used to be `ok: true` are now `ok: false` with codes (`backtest_error`, `not_configured`, `source_unavailable`, `insufficient_funds`, `limit_not_marketable`, `not_implemented`). Agents that relied on the old shape will see errors.
- **Data location** (PRE-10): default data files moved from the working directory to `<repo>/data/`. An existing ledger under another working directory is not migrated; set `PAPER_DB_PATH` to keep using it.
- **Dependency pin** (PRE-03): `mcp>=1.24.0,<2` because fastmcp 2.14.1 imports a module mcp 2.x removed.

### Evidence
Full log: [`uat/UAT-LOG.md`](uat/UAT-LOG.md) (rendered from the run's ledger) · captures under `uat/evidence/2026-09-24-01/` (four dashboard screenshots and the machine-readable ledger `findings.json` stay with the local run: the push path used here takes text files under ~95 KB; their content is in the log and the `.json` captures).

### DOX pass
- Root `AGENTS.md` now also records: Alpaca fill-now-or-not-at-all, `app/tools/params.py`, switches-first and audit order, the operator-token router and CORS order.
- Root `AGENTS.md` created (the repo had none): purpose, ownership, the fail-closed and response contracts, data-path rule, docs-must-match rule, verification commands; indexes `uat/AGENTS.md`.
- `uat/AGENTS.md`: created by the UAT tooling; owns the log, ledger and evidence.
- `_deprecated/README.md`: explains the crypto signer moved out of the shipped tree.
- Root `AGENTS.md` (XR round): market-price sizing and symbol normalisation, the time-weighted paper loss limits, the operator token and API response contract, the Docker user and `.dockerignore` rule.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01JoGpymL6LG3N8Mx7Btuxp5
