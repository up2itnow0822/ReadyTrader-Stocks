# ReadyTrader-Stocks

Root AGENTS.md (DOX rail).

## Purpose
A stdio MCP server (`app/main.py`, 20 tools) that lets an AI agent research US stocks, paper trade
in a local ledger, and optionally place live brokerage orders behind a Risk Guardian, an operator
policy and a kill switch; plus an approval/dashboard API (`app/api_server.py`) and a Next.js
dashboard (`frontend/`).

## Ownership
- `app/`: MCP tool surface (`app/tools/`), settings (`app/core/config.py`), the approval API.
- `core/`: pure rules (risk, Falling Knife `market_guard`, policy, paper ledger, backtest).
- `execution/`: brokerage connectors and the approval store; `marketdata/`, `intelligence/`:
  data sources. `common/`: shared helpers (`common/switches.py`, `common/paths.py`).
- `research/falling_knife/`: the study behind `docs/FALLING_KNIFE.md`; nothing imports it.
- `_deprecated/`: history only, never shipped.

## Local Contracts
- Fail closed. Safety switches are parsed with `common/switches.py`: protections stay on unless
  explicitly `false/0/no/off`; `LIVE_TRADING_ENABLED` needs exactly `true`; the kill switch halts
  on any value but empty/off; an unknown `EXECUTION_APPROVAL_MODE` requires approval; an unreadable
  limit refuses live orders. Brokerage connectors default to paper/sandbox accounts.
- Every live order passes `pre_trade_check` and `live_order_refusal` when placed or proposed, and
  again at execution (including `/api/approve-trade`); a proposal executes only in the mode
  (paper/live) it was made in.
- Risk rules judge the exposure an order adds (from the paper ledger or the brokerage's positions):
  selling out of a position is never sized as new exposure; an order that adds exposure and cannot
  be priced or sized is refused; unknown live positions count as new exposure.
- Tools answer `{"ok": true, "data"}` or `{"ok": false, "error": {"code", "message", "data"}}`; a
  source that cannot answer is an error, never a payload. New codes go in `docs/ERRORS.md`.
- Default data files live in `<repo>/data/` via `common/paths.data_path` (never the working
  directory); `READYTRADER_DATA_DIR` and each `*_PATH` variable override.
- Every variable the code reads is in `env.example`, with no inline comments or placeholder keys.
- Docs describe only what runs: after changing a tool, run `python tools/generate_tool_docs.py`
  and update README / `docs/` in the same change.

## Work Guidance
- Python 3.12+. Regression test for every fix, failing on the old code.
- Money paths are paper or sandbox only in development and UAT.

## Verification
- `ruff check .`, `pytest`, `bandit -q -c bandit.yaml -r app core common execution intelligence marketdata observability strategy` (CI runs all three plus the dashboard build).
- Release UAT: `uat/UAT-LOG.md`.

## Child DOX Index
- `uat/AGENTS.md` — owns the UAT reporting log, ledger, and evidence for this project
