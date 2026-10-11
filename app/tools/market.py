import json
from typing import Any, Dict, List

from fastmcp import FastMCP

from app.core.container import global_container
from app.tools.params import Integer


def _json_ok(data: Dict[str, Any] | None = None) -> str:
    payload = {"ok": True, "data": data or {}}
    return json.dumps(payload, indent=2, sort_keys=True)


def _json_err(code: str, message: str, data: Dict[str, Any] | None = None) -> str:
    payload = {"ok": False, "error": {"code": code, "message": message, "data": data or {}}}
    return json.dumps(payload, indent=2, sort_keys=True)


def get_stock_price(symbol: str) -> str:
    """Fetch the latest stock price (`last`, with the day's open/high/low/volume) from yfinance."""
    try:
        data = global_container.exchange_provider.fetch_ticker(symbol)
        return _json_ok(data)
    except Exception as e:
        return _json_err("market_data_error", str(e), {"symbol": symbol})


def get_multiple_prices(symbols: List[str]) -> str:
    """Fetch the latest prices for several stock tickers."""
    results = {}
    for sym in symbols:
        try:
            results[sym] = global_container.exchange_provider.fetch_ticker(sym)
        except Exception as e:
            results[sym] = {"error": f"could not fetch price: {str(e)[:160]}"}
    return _json_ok({"prices": results})


def _iso(ts: Any) -> str:
    """Bar time as ISO-8601 UTC (the backtest engine's timestamps are naive UTC)."""
    if hasattr(ts, "isoformat"):
        text = ts.isoformat()
        return text if getattr(ts, "tzinfo", None) else f"{text}Z"
    return str(ts)


def fetch_ohlcv(symbol: str, timeframe: str = '1d', limit: Integer = 100) -> str:
    """Fetch historical OHLCV candlestick data for technical analysis."""
    try:
        df = global_container.backtest_engine.fetch_ohlcv(symbol, timeframe, limit)
        data = df.to_dict(orient="records")
        for d in data:
            d['timestamp'] = _iso(d.get('timestamp'))
        return _json_ok({"symbol": symbol, "timeframe": timeframe, "history": data})
    except Exception as e:
        return _json_err("history_error", str(e), {"symbol": symbol})


def register_market_tools(mcp: FastMCP):
    mcp.tool(get_stock_price)
    mcp.tool(get_multiple_prices)
    mcp.tool(fetch_ohlcv)
