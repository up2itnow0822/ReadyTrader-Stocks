import json
from typing import Any, Dict

from fastmcp import FastMCP

from app.core.container import global_container
from core.stress_test import run_synthetic_stress_test as _run_stress


def _json_ok(data: Dict[str, Any] | None = None) -> str:
    payload = {"ok": True, "data": data or {}}
    return json.dumps(payload, indent=2, sort_keys=True)


def _json_err(code: str, message: str, data: Dict[str, Any] | None = None) -> str:
    payload = {"ok": False, "error": {"code": code, "message": message, "data": data or {}}}
    return json.dumps(payload, indent=2, sort_keys=True)


SIGNALS = ("bullish", "bearish", "neutral")


def post_market_insight(symbol: str, agent_id: str, signal: str, confidence: float, reasoning: str, ttl_seconds: int = 3600) -> str:
    """Share a market insight with other agents: `signal` is bullish, bearish or neutral, `confidence` 0.0-1.0."""
    if str(signal).strip().lower() not in SIGNALS:
        return _json_err("invalid_request", f"signal must be one of {', '.join(SIGNALS)}, got {signal!r}")
    if not (isinstance(confidence, (int, float)) and 0.0 <= float(confidence) <= 1.0):
        return _json_err("invalid_request", f"confidence must be between 0.0 and 1.0, got {confidence!r}")
    if not str(symbol).strip() or int(ttl_seconds) <= 0:
        return _json_err("invalid_request", "symbol must be non-empty and ttl_seconds positive")
    insight = global_container.insight_store.post_insight(symbol, agent_id, signal, confidence, reasoning, ttl_seconds)
    return _json_ok({"insight": vars(insight)})


def get_latest_insights(symbol: str = "") -> str:
    """Retrieve recent high-confidence market insights for a specific symbol or all symbols."""
    insights = global_container.insight_store.get_latest_insights(symbol if symbol else None)
    return _json_ok({"insights": [vars(i) for i in insights]})


def run_backtest_simulation(strategy_code: str, symbol: str, timeframe: str = '1h') -> str:
    """
    Backtest Python strategy code on the symbol's last 500 candles, starting from $10,000.

    The code must define `on_candle(close, rsi, state)` returning 'buy', 'sell' or 'hold';
    imports such as os are refused. A strategy that fails to compile or raises returns ok:false
    with code backtest_error.
    """
    try:
        result = global_container.backtest_engine.run(strategy_code, symbol, timeframe)
    except Exception as e:
        return _json_err("backtest_error", str(e), {"symbol": symbol, "timeframe": timeframe})
    if isinstance(result, dict) and "error" in result:
        return _json_err("backtest_error", str(result["error"]), {"symbol": symbol, "timeframe": timeframe})
    return _json_ok({"result": result})


def get_market_regime(symbol: str, timeframe: str = '1d') -> str:
    """Detect the prevailing market regime (TRENDING, RANGING, VOLATILE) for a stock."""
    try:
        df = global_container.backtest_engine.fetch_ohlcv(symbol, timeframe, limit=100)
        result = global_container.regime_detector.detect(df)
        return _json_ok({"symbol": symbol, "timeframe": timeframe, "result": result})
    except Exception as e:
        return _json_err("market_regime_error", str(e), {"symbol": symbol, "timeframe": timeframe})


def run_synthetic_stress_test(strategy_code: str, config_json: str = "{}") -> str:
    """
    Run a synthetic black-swan stress test on a strategy.
    Deterministic simulator that injects various market regimes and crashes.
    """
    try:
        config = json.loads(config_json)
        result = _run_stress(strategy_code=strategy_code, config=config)
        return _json_ok({"result": result})
    except Exception as e:
        return _json_err("stress_test_error", str(e))


def register_research_tools(mcp: FastMCP):
    mcp.tool(post_market_insight)
    mcp.tool(get_latest_insights)
    mcp.tool(run_backtest_simulation)
    mcp.tool(get_market_regime)
    mcp.tool(run_synthetic_stress_test)
