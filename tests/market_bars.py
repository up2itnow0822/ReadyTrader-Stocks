"""Synthetic daily bars for Falling Knife tests. Rows are [ts_ms, open, high, low, close, volume]."""

import time

DAY_MS = 86_400_000


def series(closes, *, end_ms=None, spread=0.005):
    """Daily bars ending at `end_ms` (default: now) whose closes follow `closes`."""
    end = int(time.time() * 1000) if end_ms is None else end_ms
    start = end - (len(closes) - 1) * DAY_MS
    rows, prev = [], closes[0]
    for i, c in enumerate(closes):
        o = prev
        rows.append([start + i * DAY_MS, o, max(o, c) * (1 + spread), min(o, c) * (1 - spread), c, 1_000_000.0])
        prev = c
    return rows


def calm(n=40, price=100.0, **kw):
    """A quiet tape: small alternating moves around `price`."""
    return series([price * (1 + (0.004 if i % 2 else -0.004)) for i in range(n)], **kw)


def collapse(n=40, price=100.0, drop=0.30, days=3, **kw):
    """Calm, then a steady fall of `drop` over the last `days` bars, closing on the low."""
    head = [price] * (n - days)
    tail = [price * (1 - drop * (i + 1) / days) for i in range(days)]
    return series(head + tail, **kw)
