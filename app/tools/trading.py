import json
import math
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from app.core.compliance import global_compliance_ledger
from app.core.config import settings
from app.core.container import global_container
from app.tools.params import Number
from core import market_guard
from core.paper import CASH_ASSETS
from core.policy import PolicyError
from execution.base import MarketClosed
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


def _invalid_order(side: Any, **amounts: Any) -> Optional[str]:
    """Why a trade request is malformed, or None. An unknown side used to pass as a SELL."""
    if str(side).strip().lower() not in ("buy", "sell"):
        return f"side must be 'buy' or 'sell', got {side!r}"
    for name, value in amounts.items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            return f"{name} must be a number, got {value!r}"
        if not math.isfinite(number) or number <= 0:
            return f"{name} must be a positive number, got {value!r}"
    return None


def _invalid_sentiment(sentiment_score: Any) -> Optional[str]:
    """None is allowed (unset). A NaN or infinite score used to read as +1.0, the most bullish."""
    if sentiment_score is None:
        return None
    try:
        number = float(sentiment_score)
    except (TypeError, ValueError):
        return f"sentiment_score must be a number on [-1, +1], got {sentiment_score!r}"
    if not math.isfinite(number):
        return f"sentiment_score must be a finite number on [-1, +1], got {sentiment_score!r}"
    return None


def _invalid_symbol(symbol: Any) -> Optional[str]:
    """Why a ticker cannot be traded here, or None. The paper ledger keys cash by USD and splits
    symbols on '/', so a ticker spelled like a cash asset (the ETF 'USD') or with a slash ('BRK/B')
    would trade against the cash balance or a phantom pair."""
    s = str(symbol or "").strip().upper()
    if not s:
        return "symbol must be a ticker such as AAPL"
    if "/" in s:
        return f"{symbol!r} is not a stock ticker; class shares use a dot (BRK.B)"
    if settings.PAPER_MODE and s in CASH_ASSETS:
        return f"{s} is the paper ledger's cash asset and cannot be paper traded as a ticker"
    return None


def _mark_paper_prices() -> None:
    """Mark the paper account's holdings to the latest price, so its value, the size rule and the
    loss limits read today's prices rather than the last fill (a held position that fell 20% since
    used to read as flat)."""
    engine = global_container.paper_engine
    for asset in engine.get_balances("agent_zero"):
        last = None if asset.upper() in CASH_ASSETS else _latest_quote(asset)
        if last is not None:
            engine.mark_price_usd(asset, last)
    engine.mark_day_open("agent_zero")


def _latest_quote(symbol: str) -> Optional[float]:
    """The latest quote's last price, or None when it cannot be read (never invented)."""
    try:
        last = float(global_container.exchange_provider.fetch_ticker(symbol).get("last") or 0.0)
    except Exception:
        return None
    return last if math.isfinite(last) and last > 0 else None


def _invalid_order_type(order_type: Any, price: Any) -> Optional[str]:
    """Why an order type / limit price pair is malformed, or None. An unknown type or a limit with
    no price used to fill at the market price on paper."""
    ot = str(order_type).strip().lower()
    if ot not in ("market", "limit"):
        return f"order_type must be 'market' or 'limit', got {order_type!r}"
    if ot == "limit" and _invalid_order("buy", price=price):
        return f"a limit order needs a positive price, got {price!r}"
    return None


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
            session = market_guard.Session(tz=settings.MARKET_TIMEZONE, open_hhmm=settings.MARKET_HOURS_START)
            reading = market_guard.assess(_fetch_daily_bars(symbol), session=session)
        except Exception as e:
            reading = market_guard.MarketReading(
                status=market_guard.STATUS_UNAVAILABLE, detail=f"{type(e).__name__}: {str(e)[:160]}"
            )
    policy = _market_guard_policy()
    return {**reading.to_dict(), "rule": rule, "on_data_error": policy, "required": policy == "block"}


def place_market_order(
    symbol: str, side: str, amount: Number, rationale: str = "", sentiment_score: Number | None = None
) -> str:
    """
    Place a market order for a stock.

    `sentiment_score` is your own reading on [-1, +1] (see validate_trade_risk); below -0.5 the
    sentiment rule blocks a BUY. Left unset, sentiment is neutral. Independently, every BUY is
    checked against recent daily closes (Falling Knife, price) - see validate_trade_risk.
    Live Alpaca orders are sent only while the market is open and fill now or not
    at all (IOC; a fractional market order goes out DAY, a fractional limit is refused); the answer
    reports what filled (`filled_qty`).
    """
    return place_stock_order(
        symbol, side, amount, order_type="market", rationale=rationale, sentiment_score=sentiment_score
    )


def place_limit_order(
    symbol: str, side: str, amount: Number, price: Number, rationale: str = "", sentiment_score: Number | None = None
) -> str:
    """
    Place a limit order for a stock.

    `sentiment_score` is your own reading on [-1, +1] (see validate_trade_risk); below -0.5 the
    sentiment rule blocks a BUY. Left unset, sentiment is neutral. Independently, every BUY is
    checked against recent daily closes (Falling Knife, price) - see validate_trade_risk.
    Live Alpaca orders are sent only while the market is open and fill now or not
    at all (IOC; a fractional market order goes out DAY, a fractional limit is refused); the answer
    reports what filled (`filled_qty`).
    """
    return place_stock_order(
        symbol, side, amount, price=price, order_type="limit", rationale=rationale, sentiment_score=sentiment_score
    )


def deposit_paper_funds(asset: str, amount: Number) -> str:
    """[PAPER MODE] Deposit virtual funds (USD, or shares of a ticker) into the paper trading account."""
    if not settings.PAPER_MODE:
        return _json_err("invalid_mode", "Deposits only available in paper mode.")
    problem = _invalid_order("buy", amount=amount)
    if problem or not str(asset).strip():
        return _json_err("invalid_request", problem or "asset must be non-empty (USD or a ticker)")
    asset = asset.strip().upper()
    engine = global_container.paper_engine
    if asset not in CASH_ASSETS:
        # Shares deposited are capital added, valued at today's price. Unvalued, they would read as a
        # trading gain once priced (and could end a drawdown halt), so the deposit waits for a price.
        last = _latest_quote(asset)
        if last is None:
            return _json_err(
                "paper_price_required",
                f"No market price for {asset}: a paper deposit of shares is valued at the market price. Deposit USD, or retry.",
                {"asset": asset},
            )
        engine.mark_price_usd(asset, float(last))
    res = engine.deposit("agent_zero", asset, float(amount))
    return _json_ok({"message": res})


def reset_paper_wallet() -> str:
    """[PAPER MODE] Clear all balances and trade history for the paper account."""
    if not settings.PAPER_MODE:
        return _json_err("invalid_mode", "Wallet reset only available in paper mode.")
    res = global_container.paper_engine.reset_wallet("agent_zero")
    return _json_ok({"message": res})


def validate_trade_risk(
    side: str, symbol: str, amount_usd: Number, portfolio_value: Number, sentiment_score: Number | None = None
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
    problem = _invalid_order(side, amount_usd=amount_usd, portfolio_value=portfolio_value) or _invalid_sentiment(sentiment_score)
    if problem:
        return _json_err("invalid_request", problem)
    try:
        sentiment = _sentiment_context(symbol, sentiment_score)
        market = _market_context(symbol, side)
        daily_loss = 0.0
        drawdown = 0.0

        if settings.PAPER_MODE:
             _mark_paper_prices()
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
    """Private order/portfolio streams are not implemented yet; this reports that instead of connecting."""
    if settings.PAPER_MODE:
        return _json_err("paper_mode_not_supported", "Private streams are not used in paper mode.")
    # It used to answer {"status": "connected"} without opening anything.
    return _json_err("not_implemented", f"Private {brokerage} streams are not implemented; poll the brokerage instead.")


def pre_trade_check(
    symbol: str,
    side: str,
    amount: float,
    price: float = 0.0,
    sentiment_score: float | None = None,
    exchange: str = "alpaca",
    order_type: str = "market",
) -> Dict[str, Any]:
    """
    The Risk Guardian check an order must pass, with fresh market data: {allowed, reason,
    sentiment, market, reference_price, market_price, position_units, exposure_added_units,
    inactive_rules}. place_stock_order runs it before anything is proposed or executed, and the
    approval API (app/api_server.py) runs it again at execution time, because a proposal can wait
    up to its expiry while the market moves.

    The order is valued at the market price, never at a price the caller supplies alone: a market
    order at the market, a limit order at the higher of its limit and the market. Without a market
    price, an order that adds exposure is refused. The daily-loss and drawdown rules read the paper
    account; a live brokerage account has no loss history here, so live orders report those two
    in `inactive_rules`.
    """
    daily_loss = 0.0
    drawdown = 0.0
    inactive_rules: List[str] = []
    symbol = str(symbol or "").strip().upper()
    side = str(side or "").strip().lower()
    sentiment = _sentiment_context(symbol, sentiment_score)
    market = _market_context(symbol, side)
    if settings.PAPER_MODE:
        engine = global_container.paper_engine
        _mark_paper_prices()
        metrics = engine.get_risk_metrics("agent_zero")
        # The account the order is sized against. get_risk_metrics has no "equity" key, so this
        # read a flat 100,000 for every account: a 1,000 account could put 5,000 on one trade.
        portfolio_value = engine.get_portfolio_value_usd("agent_zero")
        # Previously never passed, so the daily-loss and drawdown rules were inert on
        # every real order even though validate_trade_risk applied them.
        daily_loss = metrics.get('daily_pnl_pct', 0.0)
        drawdown = metrics.get('drawdown_pct', 0.0)
    else:
        portfolio_value = _live_equity(exchange)
        inactive_rules = ["daily_loss_limit", "max_drawdown"]

    market_price = _market_price(symbol, market)
    limit = None
    if str(order_type or "market").strip().lower() == "limit":
        try:
            limit = float(price) if price and math.isfinite(float(price)) and float(price) > 0 else None
        except (TypeError, ValueError):
            limit = None
    reference_price = (max(market_price, limit) if limit else market_price) if market_price else None
    # Selling out of a long is an exit, not new exposure; only what an order adds is sized.
    position = _position_units(symbol, exchange)
    added = exposure_added(side.lower(), amount, position)
    increases_exposure = added > 0
    refusal = None
    if reference_price is None:
        refusal = f"No market price for {symbol}: orders are valued at the market for the position-size check; retry when market data is available."
    elif portfolio_value is None:
        refusal = f"Could not read the {exchange} account's equity for the position-size check."
    risk_result = global_container.risk_guardian.validate_trade(
        side=side,
        symbol=symbol,
        increases_exposure=increases_exposure,
        amount_usd=added * (reference_price or 0.0),
        portfolio_value=portfolio_value or 0.0,
        sentiment_score=sentiment["score"],
        daily_loss_pct=daily_loss,
        current_drawdown_pct=drawdown,
        market=market,
    )
    allowed = bool(risk_result.get("allowed", False))
    reason = risk_result.get("reason", "Risk policy violation")
    if allowed and refusal and increases_exposure:
        # The size rule needs both numbers; without them it could not run, so an order that opens or
        # adds to a position fails closed. One that only reduces a position goes through: an exit.
        allowed, reason = False, refusal
    return {
        "allowed": allowed,
        "reason": reason,
        "sentiment": sentiment,
        "market": market,
        "reference_price": reference_price,
        "market_price": market_price,
        "position_units": position,
        "exposure_added_units": added,
        "inactive_rules": inactive_rules,
    }


def _position_units(symbol: str, exchange: str) -> Optional[float]:
    """Shares currently held (negative if short), or None when they cannot be read. Paper: the paper
    ledger. Live: the brokerage's positions."""
    key = (symbol or "").strip().upper()
    if settings.PAPER_MODE:
        try:
            return float(global_container.paper_engine.get_balance("agent_zero", key))
        except Exception:
            return None
    brokerage = global_container.brokerages.get((exchange or "").strip().lower())
    if brokerage is None or not brokerage.is_available():
        return None
    try:
        positions = brokerage.list_positions()
    except Exception:
        return None
    return sum(float(p.get("qty") or 0.0) for p in positions or [] if str(p.get("symbol") or "").strip().upper() == key)


def exposure_added(side: str, amount: float, position: Optional[float]) -> float:
    """How many shares of the order open or add to a position. Selling out of a long, or buying back a
    short, reduces exposure; only what goes beyond flat adds it. Unknown position: all of it adds."""
    amount = abs(float(amount))
    if position is None:
        return amount
    signed = amount if side == "buy" else -amount
    if position == 0 or (position > 0) == (signed > 0):
        return amount
    return max(0.0, amount - abs(position))


def _live_equity(exchange: str) -> Optional[float]:
    """The brokerage account's equity, or None when it cannot be read."""
    brokerage = global_container.brokerages.get((exchange or "").strip().lower())
    if brokerage is None or not brokerage.is_available():
        return None
    try:
        equity = float(brokerage.get_account_balance().get("equity") or 0.0)
    except Exception:
        return None
    return equity if equity > 0 else None


def _market_price(symbol: str, market: Dict[str, Any]) -> Optional[float]:
    """
    The latest price: the close the Falling Knife check already read, else the latest quote. An
    order is valued at its limit price, else at this (`amount` is a share count; valuing a market
    order at 1.0, as before, let any number of shares through the 5%-of-portfolio rule).
    """
    if market.get("last_close"):
        return float(market["last_close"])
    try:
        last = global_container.exchange_provider.fetch_ticker(symbol).get("last")
        return float(last) if last else None
    except Exception:
        return None


def paper_fill_price(side: str, limit: float, market_price: Optional[float]):
    """
    Where a paper order fills: at the latest market price. A limit order fills only if it is
    marketable (a BUY at or above the market, a SELL at or below), and then at the market; resting
    orders are not simulated. It used to fill every limit at its own price, so a BUY limit under
    the market bought below it. Returns (price, None) or (None, {code, message}).
    """
    if not market_price:
        return None, {"code": "execution_error", "message": "No market price to fill the paper order at."}
    if limit and limit > 0:
        marketable = limit >= market_price if side == "buy" else limit <= market_price
        if not marketable:
            return None, {
                "code": "limit_not_marketable",
                "message": (
                    f"Paper mode fills marketable limit orders only: {side} limit {limit:.2f} vs market "
                    f"{market_price:.2f}. Resting orders are not simulated."
                ),
            }
    return float(market_price), None


def live_execution_refusal() -> Optional[Dict[str, str]]:
    """
    The two operator switches every live order must pass (README): LIVE_TRADING_ENABLED must be
    true, and TRADING_HALTED (the kill switch) must not be. Both were documented but never read.
    """
    if not settings.LIVE_TRADING_ENABLED:
        return {
            "code": "live_trading_disabled",
            "message": "PAPER_MODE is false but LIVE_TRADING_ENABLED is not true: no live order was sent.",
        }
    if settings.TRADING_HALTED:
        return {"code": "trading_halted", "message": "TRADING_HALTED is set: live trading is halted, no order was sent."}
    return None


def live_order_refusal(
    exchange: str, symbol: str, side: str, amount: float, order_type: str, price: float
) -> Optional[Dict[str, Any]]:
    """
    Everything a live order must pass before it may reach a brokerage: the operator switches
    (live_execution_refusal) and the live policy (ALLOW_BROKERAGES, ALLOW_TICKERS,
    MAX_ORDER_AMOUNT; core/policy.py). Checked when an order is proposed and again when it
    executes, including after an approval, so an approved proposal cannot skip it.
    Returns {"code", "message", "data"} or None.
    """
    refusal = live_execution_refusal()
    if refusal:
        return {**refusal, "data": {}}
    try:
        global_container.policy_engine.validate_brokerage_order(
            exchange_id=exchange, symbol=symbol, side=side, amount=amount, market_type="spot",
            order_type=order_type, price=price if price and price > 0 else None,
        )
    except PolicyError as e:
        return {"code": e.code, "message": e.message, "data": e.data}
    return None


def place_stock_order(
    symbol: str,
    side: str,
    amount: Number,
    price: Number = 0.0,
    order_type: str = "market",
    exchange: str = "alpaca",
    rationale: str = "",
    audit_context: str = "",
    sentiment_score: Number | None = None
) -> str:
    """
    Place a stock order through the Risk Guardian, on paper or at a brokerage (`exchange`:
    alpaca or tradier; live orders need LIVE_TRADING_ENABLED=true and brokerage keys).

    `order_type` is market or limit (`price` > 0 for a limit). `sentiment_score` is your own
    reading on [-1, +1] (see validate_trade_risk); below -0.5 the sentiment rule blocks a BUY.
    Independently, every BUY is checked against recent daily closes (Falling Knife, price). With
    EXECUTION_APPROVAL_MODE=approve_each the order is returned as a pending proposal instead.
    Live Alpaca orders are sent only while the market is open and fill now or not
    at all (IOC; a fractional market order goes out DAY, a fractional limit is refused); the answer
    reports what filled (`filled_qty`).
    """
    problem = (
        _invalid_order(side, amount=amount)
        or _invalid_order_type(order_type, price)
        or _invalid_symbol(symbol)
        or _invalid_sentiment(sentiment_score)
    )
    if problem:
        return _json_err("invalid_request", problem)
    symbol = symbol.strip().upper()
    side = side.strip().lower()
    order_type = order_type.strip().lower()
    # A market order fills at the market whatever price it carries: the price is dropped, so it can
    # neither size the order nor reach a proposal or the brokerage (a NaN there broke the API).
    price = float(price) if order_type == "limit" else 0.0
    # Compliance record: every well-formed order request, including one the switches refuse (those
    # are the attempts an operator reviews after a halt).
    global_compliance_ledger.record_event("trade_start", {
        "symbol": symbol, "side": side, "amount": amount, "rationale": rationale, "audit_context": audit_context
    })
    if not settings.PAPER_MODE:
        # The operator's switches answer first: with the kill switch set, "halted" is the answer,
        # whatever else is wrong with the order or the brokerage's configuration.
        switch = live_execution_refusal()
        if switch:
            return _json_err(switch["code"], switch["message"])
        ex = (exchange or "").strip().lower()
        if ex not in global_container.brokerages:
            return _json_err("brokerage_not_supported", f"Brokerage {exchange} not found.")
        if not global_container.brokerages[ex].is_available():
            return _json_err("brokerage_not_configured", f"{exchange} keys are missing. Cannot execute a live order.")
        # A brokerage that knows its market is closed says so before anything is proposed or sent
        # (Alpaca: an order would wait for the open, past every check).
        closed = getattr(global_container.brokerages[ex], "market_closed_reason", None)
        reason = closed() if callable(closed) else None
        if reason:
            return _json_err("market_closed", reason)

    # Risk Guardian Check
    try:
        check = pre_trade_check(symbol, side, amount, price, sentiment_score, exchange, order_type)
        if not check["allowed"]:
            return _json_err(
                "risk_blocked",
                check["reason"],
                {
                    "sentiment": check["sentiment"],
                    "market": check["market"],
                    "position_units": check["position_units"],
                    "exposure_added_units": check["exposure_added_units"],
                    "reference_price": check["reference_price"],
                    "inactive_rules": check["inactive_rules"],
                },
            )

        # A live order that the switches or the live policy would refuse is refused now, not
        # after a human has been asked to approve it.
        if not settings.PAPER_MODE:
            refusal = live_order_refusal(exchange, symbol, side, amount, order_type, price)
            if refusal:
                return _json_err(refusal["code"], refusal["message"], refusal["data"])

        if settings.EXECUTION_APPROVAL_MODE == "approve_each":
            proposal = global_container.execution_store.create(
                kind="stock_order",
                payload={
                    "symbol": symbol, "side": side, "amount": amount, "price": price,
                    "order_type": order_type, "rationale": rationale, "exchange": exchange,
                    # Kept so the approval path can re-run the same check at execution time.
                    "sentiment_score": sentiment_score,
                    # A proposal executes only in the mode it was made in (paper/live).
                    "paper_mode": settings.PAPER_MODE,
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
        fill_price, problem = paper_fill_price(side, price, check.get("market_price"))
        if problem:
            return _json_err(problem["code"], problem["message"], {"market_price": check.get("market_price")})
        try:
            res = global_container.paper_engine.execute_trade(
                user_id="agent_zero", side=side, symbol=symbol, amount=amount,
                price=fill_price, rationale=rationale or "stock_order_paper"
            )
        except Exception as e:
            return _json_err("execution_error", str(e))
        if str(res).startswith("Insufficient fund"):
            return _json_err("insufficient_funds", str(res))
        return _json_ok({"venue": "paper", "result": res})

    refusal = live_order_refusal(exchange, symbol, side, amount, order_type, price)
    if refusal:
        return _json_err(refusal["code"], refusal["message"], refusal["data"])
    try:
        ex = exchange.lower()
        if ex not in global_container.brokerages:
            return _json_err("brokerage_not_supported", f"Brokerage {exchange} not found.")

        brokerage = global_container.brokerages[ex]
        if not brokerage.is_available():
            return _json_err("brokerage_not_configured", f"{exchange} keys are missing. Cannot execute a live order.")
        res = brokerage.place_order(symbol=symbol, side=side, qty=amount, order_type=order_type, price=price if price > 0 else None)
        return _json_ok({"venue": ex, "result": res})
    except MarketClosed as e:
        return _json_err("market_closed", str(e))
    except Exception as e:
        return _json_err("execution_error", str(e))


def register_trading_tools(mcp: FastMCP):
    mcp.tool(place_market_order)
    mcp.tool(place_limit_order)
    mcp.tool(place_stock_order)
    mcp.tool(deposit_paper_funds)
    mcp.tool(reset_paper_wallet)
    mcp.tool(validate_trade_risk)
    mcp.tool(start_brokerage_private_ws)
