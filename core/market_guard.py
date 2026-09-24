"""
Price-based Falling Knife check, computed from daily bars. Pure: no network, no clock unless given.

A BUY is a falling knife when, over the latest daily close and the KNIFE_WINDOW closes before it:

    drop = (highest close in the window - latest close) / highest close  >=  KNIFE_MIN_DROP
    and the latest close is at or below every earlier close in the window (still falling)

Only closes are used. Intraday highs and lows are where bad provider prints live, and a phantom
spike high would otherwise look like a collapse. During the session the latest bar is today's
partial candle, so "latest close" is the current price: the question asked is "would buying now
be buying into a collapse that has not stopped?".

For equities KNIFE_WINDOW = 3 (today plus the three prior sessions) and KNIFE_MIN_DROP = 15%. They
were chosen on 2000-2019 daily history of 45 US stocks, frozen, and then scored once on 64 stocks
that had never been downloaded (docs/FALLING_KNIFE.md). On those, over 2000-2026, the rule fired
on 0.48% of stock-days; a buy on those days fell a further 10% within ten sessions 49.2% of the
time, against 13.1% on all days, and its worst-decile drawdown was -30.1% against -11.5%. Its
median outcome was not worse (+2.5% against +0.5%): this is tail protection, not a forecast.

Why not normalise by volatility? For stocks it made the rule worse on the development years - the
raw size of the drop is what predicted further losses - and market-wide sell-offs did the
opposite of single-name collapses (buying after a sharp S&P drop had better-than-average forward
returns), so the rule looks only at the instrument itself.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence

KNIFE_WINDOW = 3
KNIFE_MIN_DROP = 0.15

# How many daily bars to request. The window needs KNIFE_WINDOW + 1; the rest is headroom for
# holidays and for bars a provider drops.
BARS_REQUESTED = 40
TIMEFRAME = "1d"

# A latest bar older than this is not "now": Friday's bar on a Monday-holiday Tuesday is 4 days old.
MAX_STALENESS_DAYS = 5

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_data"
STATUS_STALE = "stale"
STATUS_UNAVAILABLE = "unavailable"
STATUS_DISABLED = "disabled"


@dataclass(frozen=True)
class MarketReading:
    status: str
    falling_knife: bool = False
    drop_pct: Optional[float] = None
    peak_close: Optional[float] = None
    last_close: Optional[float] = None
    still_falling: Optional[bool] = None
    bars: int = 0
    as_of: Optional[str] = None
    detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _clean(ohlcv: Sequence[Sequence[Any]]) -> List[List[float]]:
    """Keep rows with a timestamp and finite, positive, consistent OHLC; sort and de-duplicate by time."""
    rows: Dict[int, List[float]] = {}
    for row in ohlcv or []:
        try:
            ts, o, h, low, c = int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4])
        except (TypeError, ValueError, IndexError):
            continue
        values = (o, h, low, c)
        if not all(math.isfinite(v) and v > 0 for v in values) or h < low:
            continue
        rows[ts] = [ts, o, h, low, c]
    return [rows[k] for k in sorted(rows)]


def _iso(ts_ms: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts_ms / 1000))


def assess(
    ohlcv: Sequence[Sequence[Any]],
    *,
    min_drop: float = KNIFE_MIN_DROP,
    window: int = KNIFE_WINDOW,
    now_ms: Optional[int] = None,
    max_staleness_days: float = MAX_STALENESS_DAYS,
) -> MarketReading:
    """Evaluate the latest bar of `ohlcv` ([[ts_ms, open, high, low, close, volume], ...])."""
    bars = _clean(ohlcv)
    if len(bars) < window + 1:
        return MarketReading(
            status=STATUS_INSUFFICIENT,
            bars=len(bars),
            detail=f"need {window + 1} daily bars, got {len(bars)}",
        )

    last_ts = int(bars[-1][0])
    now = int(time.time() * 1000) if now_ms is None else int(now_ms)
    age_days = (now - last_ts) / 86_400_000
    if age_days > max_staleness_days:
        return MarketReading(
            status=STATUS_STALE,
            bars=len(bars),
            as_of=_iso(last_ts),
            detail=f"latest daily bar is {age_days:.1f} days old",
        )

    closes = [b[4] for b in bars[-(window + 1):]]
    peak_close = max(closes)
    last_close = closes[-1]
    drop = (peak_close - last_close) / peak_close
    still_falling = last_close <= min(closes[:-1])
    return MarketReading(
        status=STATUS_OK,
        falling_knife=bool(drop >= min_drop and still_falling),
        drop_pct=round(drop, 6),
        peak_close=peak_close,
        last_close=last_close,
        still_falling=bool(still_falling),
        bars=len(bars),
        as_of=_iso(last_ts),
    )
