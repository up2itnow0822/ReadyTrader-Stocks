$ bash -c 'python3 /tmp/claude-0/-home-claude/55237518-b0f0-557c-b340-66cb8731d4ad/scratchpad/probes/doccheck.py . "README.md,RUNBOOK.md,docs/README.md,docs/ERRORS.md,docs/EXCHANGES.md,docs/MARKETDATA.md,docs/TOOLS.md" "$(cat /tmp/claude-0/-home-claude/55237518-b0f0-557c-b340-66cb8731d4ad/scratchpad/probes/stocks_tools.json)"; echo ---; grep -n -E "MAX_TRADE_AMOUNT|request Interactive|ALLOW_CHAINS|MARKETDATA_EXCHANGES|CCXT Tuning|Mobile Guard|Multi-Agent Insights|Glassmorphic" README.md; grep -n -E "keystore|remote signer|SIGNER_TYPE|ccxt" RUNBOOK.md'
# at 2026-09-24T07:50:15+00:00 in /tmp/claude-0/-home-claude/55237518-b0f0-557c-b340-66cb8731d4ad/scratchpad/repos/ReadyTrader-Stocks

README.md: anchor #-optional-web-ui not found
README.md: path not found -> RELEASE_READINESS_CHECKLIST.md
README.md: path not found -> agent.yaml
README.md: path not found -> api_server.py
README.md: path not found -> mcp-server-config.json
README.md: tool not registered -> check_orders
README.md: tool not registered -> get_marketdata_capabilities
README.md: tool not registered -> get_portfolio_balance
README.md: tool not registered -> get_sentiment
RUNBOOK.md: tool not registered -> get_brokerage_capabilities
RUNBOOK.md: tool not registered -> get_health
RUNBOOK.md: tool not registered -> get_marketdata_status
RUNBOOK.md: tool not registered -> get_metrics_prometheus
RUNBOOK.md: tool not registered -> get_metrics_snapshot
RUNBOOK.md: tool not registered -> get_ticker
RUNBOOK.md: tool not registered -> start_marketdata_ws
docs/EXCHANGES.md: tool not registered -> get_order
docs/EXCHANGES.md: tool not registered -> get_portfolio_balance
docs/EXCHANGES.md: tool not registered -> start_marketdata_ws
docs/MARKETDATA.md: tool not registered -> start_marketdata_ws
docs/README.md: path not found -> ../RELEASE_READINESS_CHECKLIST.md
docs/TOOLS.md: anchor #deposit-paper-funds not found
docs/TOOLS.md: anchor #fetch-ohlcv not found
docs/TOOLS.md: anchor #fetch-rss-news not found
docs/TOOLS.md: anchor #get-financial-news not found
docs/TOOLS.md: anchor #get-latest-insights not found
docs/TOOLS.md: anchor #get-market-news not found
docs/TOOLS.md: anchor #get-market-regime not found
docs/TOOLS.md: anchor #get-market-sentiment not found
docs/TOOLS.md: anchor #get-multiple-prices not found
docs/TOOLS.md: anchor #get-social-sentiment not found
docs/TOOLS.md: anchor #get-stock-price not found
docs/TOOLS.md: anchor #place-limit-order not found
docs/TOOLS.md: anchor #place-market-order not found
docs/TOOLS.md: anchor #place-stock-order not found
docs/TOOLS.md: anchor #post-market-insight not found
docs/TOOLS.md: anchor #reset-paper-wallet not found
docs/TOOLS.md: anchor #run-backtest-simulation not found
docs/TOOLS.md: anchor #run-synthetic-stress-test not found
docs/TOOLS.md: anchor #start-brokerage-private-ws not found
docs/TOOLS.md: anchor #validate-trade-risk not found
-- 41 problem(s) in 7 doc(s)
---
33:*   **You keep your funds**: Your capital remains in your own brokerage account (e.g., Alpaca, Tradier, request Interactive Brokers).
43:3.  **Governance:** The MCP server checks its rules. Is $1000 within your `MAX_TRADE_AMOUNT`? If yes, it creates a **Pending Execution**.
60:-   **Multi-Agent Insights**: Shared "Market Insights" for collaborative research.
61:-   **Mobile Guard**: Push notifications for trades requiring manual approval.
62:-   **Glassmorphic UI**: High-performance charting and portfolio visualization.
142:<summary><b>📈 Market Data & CCXT Tuning</b></summary>
146:| `MARKETDATA_EXCHANGES` | `alpaca` | Comma-separated list of brokerages to use for data. |
158:| `ALLOW_CHAINS` | `ethereum...` | Allowlists for EVM networks. |
20:- Prefer keystore or remote signer in live environments.
66:  - If unreliable, fall back to `ccxt_rest` and/or ingest your own feed.
70:  - CCXT calls failing (`ccxt_exchange_unavailable`, `ccxt_network_error`)
80:#### 4) Signer unreachable (remote signer / keystore issues)
85:  - Confirm signer configuration (`SIGNER_TYPE`, keystore path/password, remote signer URL)


exit=0
