# Falling Knife (price)

Every BUY — through `validate_trade_risk` or any order tool — reads the stock's recent daily bars and
is blocked while the stock is still falling after a sharp drop. SELLs are never blocked by this
rule, so an exit is never trapped.

## The rule

Take today's close and the three closes before it (during the session "today's close" is the
current price, from today's partial daily bar).

```
drop = (highest of those four closes - today's close) / highest of those four closes

blocked  when  drop >= 15%  AND  today's close is at or below each of the three earlier closes
```

The second condition is what "still falling" means: a stock that is down 30% but closed above
yesterday has stopped falling, and the rule lets the buy through.

Only closes are used. Intraday highs and lows are where bad provider prints live, and a phantom
spike high would otherwise look like a collapse.

## How it runs

- **Data**: `global_container.exchange_provider.fetch_ohlcv(symbol, "1d", limit=40)` — the same
  yfinance-backed provider as the `fetch_ohlcv` tool, cached for `OHLCV_CACHE_TTL_SEC` (60 s by
  default, never past the next daily boundary). One network call per symbol per minute at most; a
  SELL makes none.
- **Code**: `core/market_guard.py` is pure (bars in, reading out). `app/tools/trading.py`
  (`_market_context`) fetches the bars and applies the policy below; `core/risk.py` (Rule 2b) turns
  the reading into a verdict.
- **Response**: `validate_trade_risk` returns a `market` block — `status`, `falling_knife`,
  `drop_pct`, `peak_close`, `last_close`, `still_falling`, `bars`, `as_of`, `detail`, the `rule`
  thresholds and the data-error policy. A blocked order returns the same block in its error data.
- **Approvals**: with `EXECUTION_APPROVAL_MODE=approve_each`, an order is checked when it is
  proposed and checked again, with fresh bars, when `/api/approve-trade` approves it: a proposal
  can wait until it expires while the market moves. An approval the check refuses answers
  `409` with `{"code": "risk_blocked", "reason", "market"}` and nothing executes.

### When the bars cannot be read

`status` is `ok`, `insufficient_data` (fewer than 4 usable bars), `stale`, `unavailable` (the
provider raised), `disabled`, or `not_checked` (a SELL).

`stale` means either the latest bar is more than 5 days old, or today's session has opened and
the provider has no bar for it yet. The session is read from `MARKET_TIMEZONE` and
`MARKET_HOURS_START` (US/Eastern, 09:30), Monday to Friday; without today's bar the rule would be
reading yesterday's closes while missing a collapse happening now. On an exchange holiday that
reads as stale all day, which is the safe answer: the market is closed (a paper order would fill at
a price this check has not seen; a live Alpaca order is refused as `market_closed`). Bars are matched to dates in `MARKET_TIMEZONE`, so a
listing on an exchange in another time zone can read as stale during US hours.

| `MARKET_GUARD_ON_DATA_ERROR` | A BUY whose check could not run |
| :--- | :--- |
| unset, live mode | **blocked** — a missed buy is recoverable, a buy into a collapse may not be |
| unset, paper mode | allowed, with the `market` block saying why the check did not run |
| `block` | blocked |
| `allow` | allowed, with the `market` block saying why |
| anything else | blocked (an unrecognised value fails closed) |

A SELL is never blocked for missing data.

### Settings

| Variable | Default | Effect |
| :--- | :--- | :--- |
| `MARKET_GUARD_ENABLED` | `true` | `false` (or `0`, `no`, `off`) turns the price check off; the `market` block then reports `disabled`. Any other value, including a typo, leaves it on |
| `MARKET_GUARD_ON_DATA_ERROR` | unset | see the table above |
| `OHLCV_CACHE_TTL_SEC` | `60` | cache lifetime for the daily bars |
| `MARKET_TIMEZONE`, `MARKET_HOURS_START` | `US/Eastern`, `09:30` | when today's session opens, for the stale check above |

`CIRCUIT_BREAKER_PCT` is not read by any check; it predates this rule and is kept only so existing
configurations still load.

## Why these numbers

The thresholds were chosen on daily history and then tested on data the choice never saw. The full
protocol, the scripts and their raw output are in [`research/falling_knife/`](../research/falling_knife/);
this is the summary.

**Question asked of each rule:** if you had bought at the close on a day the rule fires, how often
did the stock fall a *further* 10% within the next ten sessions, compared with buying on any day?

**Selection** (2000-2019, 45 US stocks — large caps plus names with known collapses): among rules
that fire on 0.3%-1.0% of stock-days, pick the highest lift. That was 15% over four closes. It was
frozen, with its hash, before any scoring.

**Results** (close-based rule, frozen):

| Data | Fires on | Fell a further 10% within 10 sessions | Worst-decile 10-day drawdown | Median 10-day return |
| :--- | ---: | :--- | :--- | :--- |
| Development: 45 stocks, 2000-2019 | 0.59% of days | 54.9% vs 13.4% on all days (4.1x) | -35.2% vs -11.7% | +1.8% vs +0.6% |
| **Never-seen: 64 other stocks, 2000-2026** | 0.48% | **49.2% vs 13.1% (3.8x)** | -30.1% vs -11.5% | +2.5% vs +0.5% |
| Never-seen stocks, 2020-2026 only | 0.78% | 50.1% vs 17.6% (2.8x) | -28.2% vs -13.6% | +2.7% vs +0.5% |
| Development stocks, 2020-2026 (already used once, to test the first version) | 0.91% | 47.5% vs 18.6% (2.6x) | -28.5% vs -14.1% | +3.1% vs +0.6% |

The shipped `core/market_guard.py` was checked against the research implementation on all
601,534 stock-days above, using only the 40 bars it sees at runtime: 100% agreement.

**Real episodes pinned by the tests** (`tests/fixtures/market_guard_real_bars.json`):

| Stock, day | Reading | What happened next |
| :--- | :--- | :--- |
| WAL 2023-03-10 (SVB weekend) | down 31%, still falling: **blocked** | fell a further 85% intraday by 03-13 |
| ZION 2023-03-09 (SVB day one) | down 15.2%: **blocked** | fell a further 45% within ten sessions |
| BA 2020-03-09 (COVID) | down 19.8%: **blocked** | fell a further 61% |
| COIN 2022-05-06 | down 20.3%: **blocked** | fell a further 61% |
| AAPL 2025-04-04 (tariff shock) | down 15.9%: **blocked** | fell a further 10% by 04-08 |
| WAL 2023-03-14 | down 52% but closed above the prior close: allowed | — |
| TSLA 2022-11-09 | down 14.4%, under the floor: allowed | — |
| SPY 2020-03-16 | down 12.6%, under the floor: allowed | — |
| AAPL 2024-06-12 | an ordinary day: allowed | — |

## What it is not

- **Not a forecast.** On days the rule fires, the *median* ten-day return was higher than on an
  ordinary day: many collapses bounce. The rule trades those bounces away for protection against
  the tail — about half of the time the stock kept falling another 10%. That trade matches this
  project's rule that nothing should make an unrecoverable move; if you disagree for your
  strategy, set `MARKET_GUARD_ENABLED=false`.
- **Not independent evidence 1,617 times over.** Fires cluster in crises (March 2020, March 2023),
  so the effective number of independent episodes is far smaller than the day counts.
- **Only as good as the bars.** A bad close from the provider can cause a false block (the safe
  direction: a buy is refused). Delisted stocks could not be downloaded, so the samples carry
  survivorship bias. Index ETFs were excluded from scoring; the rule still applies to them, and a
  broad index rarely falls 15% in four sessions.
- **Separate from the sentiment rule.** `sentiment_score` (your own reading of the crowd, below
  -0.5) still blocks a BUY on its own; see [SENTIMENT.md](SENTIMENT.md).

## History

Before this rule the Falling Knife protection depended only on a sentiment score that this server
cannot measure (see SENTIMENT.md), so in practice it never fired. A first version of this price
rule measured the drop from the highest *intraday high*; it was replaced by the close-based rule
above before release because bad high prints in provider data made it fire on phantom spikes.
A price rule for crypto was tested the same way and failed on data it had not seen, so
ReadyTrader-Crypto does not ship one.
