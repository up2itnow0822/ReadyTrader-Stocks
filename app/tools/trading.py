import json
from typing import Any, Dict, List

from fastmcp import FastMCP

from app.core.compliance import global_compliance_ledger
from app.core.config import settings
from app.core.container import global_container
from core import market_guard
from intelligence import get_cached_sentiment


def _json_ok(data: Dict[str, Any] | None = None) -> str:
    payload = {"ok": True, "data": data or {}}
    return json.dumps(payload, indent=2, sort_keys=True)


def _json_err(code: str, message: str, data: Dict[str, Any] | None = None) -> str:
    payload = {"ok": False, "error": {"code": code, "message": message, "data": data or {}}}
    return json.dumps(payload, indent=2, sort_keys=True)


NOT_MEASURED_HINT = (
    "This server does not score sentiment. Call get_social_sentiment(symbol) to read the posts, "
    "and pass your own reading as sentiment_score on [-1, +1] if you want the sentiment side of the "
    "Falling Knife rule to act. Left unset it is neutral (0.0) and that side cannot fire; the price "
    "side reads daily closes on every BUY regardless."
)
NO_SOURCE_HINT = (
    "No X or Reddit credentials are set, so there are no posts to read either. "
    "Set TWITTER_BEARER_TOKEN and/or REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET."
)


def _sentiment_context(symbol: str, supplied: float | None) -> Dict[str, Any]:
    """
    What the Falling Knife rule is working from, so a neutral 0.0 is never mistaken for a
    measured calm market. `source` is the whole point: this server measures nothing, so a
    non-zero score is always the caller's own judgement and is recorded as such.
    """
    entry = get_cached_sentiment(symbol)
    context: Dict[str, Any] = {
        "score": 0.0,
        "source": "unmeasured",
        "status": "not_measured",
        "posts_available": entry["texts"] if entry else 0,
        "posts_age_seconds": entry["age_seconds"] if entry else None,
        "hint": NOT_MEASURED_HINT,
    }
    if entry is not None and not entry["configured"]:
        context["status"] = "no_source_configured"
        context["hint"] = NO_SOURCE_HINT
    if supplied is not None:
        score = max(-1.0, min(1.0, float(supplied)))
        context["score"] = score
        context["source"] = "agent_supplied"
        context["status"] = "agent_supplied"
        context.pop("hint", None)
    return context


def _fetch_daily_bars(symbol: str) -> List[Any]:
    """The Falling Knife check's only network call. Tests replace this function."""
    return global_container.exchange_provider.fetch_ohlcv(
        symbol, market_guard.TIMEFRAME, limit=market_guard.BARS_REQUESTED
    )


def _market_guard_policy() -> str:
    """What a BUY does when the daily bars cannot be read: "block" or "allow"."""
    raw = (settings.MARKET_GUARD_ON_DATA_ERROR or "").strip().lower()
    if raw in ("block", "allow"):
        return raw
    if raw:
        return "block"  # an unrecognised value fails closed
    return "allow" if settings.PAPER_MODE else "block"


def _market_context(symbol: str, side: str) -> Dict[str, Any]:
    """
    The price-based Falling Knife reading for a trade (core/market_guard.py), plus the policy the
    Risk Guardian applies to it. Only BUYs are checked: a SELL is never blocked by this rule, so it
    never waits on market data either.
    """
    rule = {"window_bars": market_guard.KNIFE_WINDOW + 1, "min_drop": market_guard.KNIFE_MIN_DROP}
    if side.lower() != "buy":
        reading = market_guard.MarketReading(status="not_checked", detail="SELLs are never blocked by this rule")
    elif not settings.MARKET_GUARD_ENABLED:
        reading = market_guard.MarketReading(status=market_guard.STATUS_DISABLED, detail="MARKET_GUARD_ENABLED=false")
    else:
        try:
            reading = market_guard.assess(_fetch_daily_bars(symbol))
        except Exception as e:
            reading = market_guard.MarketReading(
                status=market_guard.STATUS_UNAVAILABLE, detail=f"{type(e).__name__}: {str(e)[:160]}"
            )
    policy = _market_guard_policy()
    return {**reading.to_dict(), "rule": rule, "on_data_error": policy, "required": policy == "block"}


def place_market_order(
    symbol: str, side: str, amount: float, rationale: str = "", sentiment_score: float | None = None
) -> str:
    """
    Place a market order for a stock.

    `sentiment_score` is your own reading on [-1, +1] (see validate_trade_risk); below -0.5 the
    sentiment rule blocks a BUY. Left unset, sentiment is neutral. Independently, every BUY is
    checked against recent daily closes (Falling Knife, price) - see validate_trade_risk.
    """
    return place_stock_order(
        symbol, side, amount, order_type="market", rationale=rationale, sentiment_score=sentiment_score
    )


def place_limit_order(
    symbol: str, side: str, amount: float, price: float, rationale: str = "", sentiment_score: float | None = None
) -> str:
    """
    Place a limit order for a stock.

    `sentiment_score` is your own reading on [-1, +1] (see validate_trade_risk); below -0.5 the
    sentiment rule blocks a BUY. Left unset, sentiment is neutral. Independently, every BUY is
    checked against recent daily closes (Falling Knife, price) - see validate_trade_risk.
    """
    return place_stock_order(
        symbol, side, amount, price=price, order_type="limit", rationale=rationale, sentiment_score=sentiment_score
    )


def deposit_paper_funds(asset: str, amount: float) -> str:
    """[PAPER MODE] Deposit virtual funds into the paper trading account."""
    if not settings.PAPER_MODE:
        return _json_err("invalid_mode", "Deposits only available in paper mode.")
    res = global_container.paper_engine.deposit("agent_zero", asset.upper(), amount)
    return _json_ok({"message": res})


def reset_paper_wallet() -> str:
    """[PAPER MODE] Clear all balances and trade history for the paper account."""
    if not settings.PAPER_MODE:
        return _json_err("invalid_mode", "Wallet reset only available in paper mode.")
    res = global_container.paper_engine.reset_wallet("agent_zero")
    return _json_ok({"message": res})


def validate_trade_risk(
    side: str, symbol: str, amount_usd: float, portfolio_value: float, sentiment_score: float | None = None
) -> str:
    """
    Verify if a trade complies with risk policies and current market conditions.

    `sentiment_score` is optional and is YOUR reading of the market on [-1, +1], not a
    measurement this server makes. Below -0.5 the sentiment rule blocks a BUY. Call
    get_social_sentiment(symbol) first to read the posts and form that judgement. Left unset,
    sentiment is neutral (0.0) and that rule cannot fire.

    Returns `result` ({allowed, reason}), `sentiment` ({score, source, status,
    posts_available, posts_age_seconds}) and `market`, the price-based Falling Knife reading
    for a BUY ({status, falling_knife, drop_pct, peak_close, last_close, still_falling, as_of,
    ...}). A BUY is blocked while the stock is still falling after a 15%+ drop from its highest
    close of the last four sessions. This check reads recent daily bars (cached for up to a minute).
    `sentiment.source` is "agent_supplied" or "unmeasured" - never a measurement by this server.
    """
    try:
        sentiment = _sentiment_context(symbol, sentiment_score)
        market = _market_context(symbol, side)
        daily_loss = 0.0
        drawdown = 0.0
        
        if settings.PAPER_MODE:
             metrics = global_container.paper_engine.get_risk_metrics("agent_zero")
             daily_loss = metrics.get('daily_pnl_pct', 0.0)
             drawdown = metrics.get('drawdown_pct', 0.0)
        
        result = global_container.risk_guardian.validate_trade(
            side, symbol, amount_usd, portfolio_value, sentiment["score"], daily_loss, drawdown, market=market
        )
        return _json_ok({
            "side": side,
            "symbol": symbol,
            "amount_usd": amount_usd,
            "result": result,
            "sentiment": sentiment,
            "market": market,
        })
    except Exception as e:
        return _json_err("risk_validation_error", str(e))


def start_brokerage_private_ws(brokerage: str) -> str:
    """Initiate a private websocket connection for order and portfolio updates."""
    if settings.PAPER_MODE:
        return _json_err("paper_mode_not_supported", "Private streams are not used in paper mode.")
    return _json_ok({"mode": "ws", "status": "connected", "brokerage": brokerage})


def place_stock_order(
    symbol: str, 
    side: str, 
    amount: float, 
    price: float = 0.0, 
    order_type: str = "market", 
    exchange: str = "alpaca", 
    rationale: str = "", 
    audit_context: str = "",
    sentiment_score: float | None = None
) -> str:
    # Compliance Record
    global_compliance_ledger.record_event("trade_start", {
        "symbol": symbol, "side": side, "amount": amount, "rationale": rationale, "audit_context": audit_context
    })
    
    # Risk Guardian Check
    try:
        portfolio_value = 100000.0
        daily_loss = 0.0
        drawdown = 0.0
        sentiment = _sentiment_context(symbol, sentiment_score)
        market = _market_context(symbol, side)
        if settings.PAPER_MODE:
             metrics = global_container.paper_engine.get_risk_metrics("agent_zero")
             portfolio_value = metrics.get('equity', 100000.0)
             # Previously never passed, so the daily-loss and drawdown rules were inert on
             # every real order even though validate_trade_risk applied them.
             daily_loss = metrics.get('daily_pnl_pct', 0.0)
             drawdown = metrics.get('drawdown_pct', 0.0)

        est_px = price if price > 0 else 1.0
        risk_result = global_container.risk_guardian.validate_trade(
            side=side,
            symbol=symbol,
            amount_usd=amount * est_px,
            portfolio_value=portfolio_value,
            sentiment_score=sentiment["score"],
            daily_loss_pct=daily_loss,
            current_drawdown_pct=drawdown,
            market=market,
        )

        if not risk_result.get("allowed", False):
            return _json_err(
                "risk_blocked",
                risk_result.get("reason", "Risk policy violation"),
                {"sentiment": sentiment, "market": market},
            )
            
        if settings.EXECUTION_APPROVAL_MODE == "approve_each":
            proposal = global_container.execution_store.create(
                kind="stock_order",
                payload={
                    "symbol": symbol, "side": side, "amount": amount, "price": price,
                    "order_type": order_type, "rationale": rationale, "exchange": exchange
                }
            )
            return _json_ok({
                "status": "pending_approval",
                "request_id": proposal.request_id,
                "confirm_token": proposal.confirm_token,
                "order_details": proposal.payload
            })
            
    except Exception as e:
        return _json_err("risk_validation_error", str(e))

    # Execution
    if settings.PAPER_MODE:
        res = global_container.paper_engine.execute_trade(
            user_id="agent_zero", side=side, symbol=symbol, amount=amount,
            price=price if price > 0 else 0.0, rationale=rationale or "stock_order_paper"
        )
        return _json_ok({"venue": "paper", "result": res})
    
    try:
        global_container.policy_engine.validate_brokerage_order(
            exchange_id=exchange, symbol=symbol, side=side, amount=amount, market_type="spot"
        )
        ex = exchange.lower()
        if ex not in global_container.brokerages:
            return _json_err("brokerage_not_supported", f"Brokerage {exchange} not found.")
            
        brokerage = global_container.brokerages[ex]
        res = brokerage.place_order(symbol=symbol, side=side, qty=amount, order_type=order_type, price=price if price > 0 else None)
        return _json_ok({"venue": ex, "result": res})
    except Exception as e:
        return _json_err("execution_error", str(e))


def register_trading_tools(mcp: FastMCP):
    mcp.add_tool(place_market_order)
    mcp.add_tool(place_limit_order)
    mcp.add_tool(deposit_paper_funds)
    mcp.add_tool(reset_paper_wallet)
    mcp.add_tool(validate_trade_risk)
    mcp.add_tool(start_brokerage_private_ws)
