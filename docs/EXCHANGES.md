## ReadyTrader-Stocks — Brokerage Capabilities

A truthful capability matrix. "Supported" means the order path is covered by tests (against a fake
brokerage) and documented; "Experimental" means the connector exists but has not been exercised
against that brokerage in this project's tests. None has been exercised against a live account
by this project; start with a sandbox or paper account and `EXECUTION_APPROVAL_MODE=approve_each`.

Live orders go only through `place_stock_order` (and `place_market_order` / `place_limit_order`,
which use Alpaca) with `PAPER_MODE=false` and `LIVE_TRADING_ENABLED=true`. Every live order passes
the Risk Guardian (sized against the brokerage's reported equity), the kill switch and the live
policy (`ALLOW_TICKERS`, `ALLOW_BROKERAGES`, `MAX_ORDER_AMOUNT`) first. Paper mode never contacts a
brokerage: orders fill in the local paper ledger.

### Market data
All price and candle tools (`get_stock_price`, `get_multiple_prices`, `fetch_ohlcv`) and the
Falling Knife check read **yfinance** (Yahoo). No brokerage key is needed for market data, and no
streaming feed is exposed as a tool in this release.

---

## Capability matrix

| `exchange` | Market / limit orders | Account equity (for sizing) | Keys (env) | Status |
|-----------|--------------|--------------|----------------|-------|
| `alpaca` | Yes (only while the market is open; `IOC`, fractional market orders `DAY`) | Yes | `ALPACA_API_KEY`, `ALPACA_API_SECRET` (paper account unless `ALPACA_PAPER=false`) | Supported |
| `tradier` | Yes | Yes | `TRADIER_ACCESS_TOKEN`, `TRADIER_ACCOUNT_ID` (sandbox unless `TRADIER_SANDBOX=false`) | Experimental |
| `ibkr` | Yes | Yes | `IBKR_ENABLED=true`, `IBKR_HOST`, `IBKR_PORT`, `IBKR_CLIENT_ID`; needs a running TWS / Gateway and `ib_insync` | Experimental |
| `schwab` | Yes | Yes | `SCHWAB_ACCESS_TOKEN`, `SCHWAB_ACCOUNT_HASH` | Experimental |
| `etrade` | Yes | Yes | `ETRADE_CONSUMER_KEY`, `ETRADE_CONSUMER_SECRET`, `ETRADE_RESOURCE_OWNER_KEY`, `ETRADE_RESOURCE_OWNER_SECRET`, `ETRADE_ACCOUNT_ID_KEY` (`ETRADE_SANDBOX=true` for the sandbox) | Experimental |
| `robinhood` | Yes | Cash only (holdings not counted, so sizing is stricter) | `ROBINHOOD_USER`, `ROBINHOOD_PASS`, `ROBINHOOD_TOTP`; needs `robin_stocks` | Experimental |

**Alpaca orders fill now or not at all.** The Risk Guardian judges an order against the market and
the positions at the moment it is placed, so nothing is left waiting at Alpaca. An order is sent only
while the market is open (Alpaca's clock): otherwise the tool answers `market_closed` and nothing is
proposed or sent. It goes out `IOC`: filled now (a limit at its limit or better), the rest cancelled;
a trading halt cancels it rather than leaving it queued. Alpaca takes fractional shares only as `DAY`
orders, so a fractional market order goes out `DAY` (it can wait out a single-stock halt) and a
fractional limit is refused. The answer reads the order back: `status`, `filled_qty`,
`filled_avg_price`; an order Alpaca cancelled unfilled is an `execution_error`. A resting order could
fill later, past every check and the kill switch.

**Test the live path without real money:** with `PAPER_MODE=false` and `LIVE_TRADING_ENABLED=true`,
Alpaca orders go to your Alpaca paper account (`ALPACA_PAPER` defaults to `true`) and Tradier
orders to its sandbox (`TRADIER_SANDBOX` defaults to `true`). Only an explicit `false` reaches a
real account.

---

## What the server does not do

- Cancel, amend or list brokerage orders, or list positions: manage those with the brokerage.
- Count open orders. At the brokerages other than Alpaca a limit order can rest (Tradier `day`, and
  the others' defaults); the Risk Guardian sizes each order against the positions at the time it
  is checked, not against open orders, and the kill switch does not cancel them.
- Close positions while `TRADING_HALTED` is set: the kill switch refuses closing orders too;
  flatten at the brokerage.
- Stream private order updates: `start_brokerage_private_ws` answers `not_implemented`.
- Fetch a live portfolio view in the API (`/api/portfolio` is paper-only).
