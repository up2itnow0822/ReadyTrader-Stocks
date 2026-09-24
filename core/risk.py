from typing import Any, Dict, Optional


class RiskGuardian:
    def __init__(self):
        pass

    def validate_trade(self, 
                      side: str, 
                      symbol: str, 
                      amount_usd: float, 
                      portfolio_value: float, 
                      sentiment_score: float = 0.0,
                      daily_loss_pct: float = 0.0,
                      current_drawdown_pct: float = 0.0,
                      force_approval: bool = False,
                      price: Optional[float] = None,
                      last_close_price: Optional[float] = None,
                      day_trades_count: int = 0,
                      market: Optional[Dict[str, Any]] = None,
                      increases_exposure: Optional[bool] = None) -> Dict[str, Any]:
        """
        Validate a trade against safety rules.

        `increases_exposure` says whether the order opens or adds to a position. The order path works
        it out from the current position and passes it (selling out of a long is an exit; selling more
        than is held opens a short), and `amount_usd` is then the value of the part that adds exposure.
        The drawdown, daily-loss, sentiment and Falling Knife rules refuse only orders that add
        exposure. Without it (validate_trade_risk) a BUY is taken to add exposure and a SELL not.
        """
        adds_exposure = (side.lower() == 'buy') if increases_exposure is None else bool(increases_exposure)
        # Rule 0: System State Checks
        # Max Drawdown Check (10%)
        # If drawdown is 10%, we only allow reducing risk (SELLs), not BUYs?
        # Or we block everything? Usually block BUYs.
        if current_drawdown_pct >= 0.10 and adds_exposure:
             return {
                "allowed": False,
                "reason": (
                    f"Max Drawdown Limit Hit ({current_drawdown_pct:.1%}). Orders that add exposure are halted; "
                    "orders that reduce or close a position are allowed."
                ),
             }
             
        # Daily Loss Limit (5%)
        # If we lost 5% today, stop trading.
        # daily_loss_pct is usually negative (e.g. -0.05)
        if daily_loss_pct <= -0.05 and adds_exposure:
             return {
                "allowed": False,
                "reason": (
                    f"Daily Loss Limit Hit ({daily_loss_pct:.1%}). Orders that add exposure are halted; "
                    "orders that reduce or close a position are allowed."
                ),
             }

        # Rule 1: Position Sizing
        # Max 5% of portfolio per trade
        max_alloc_pct = 0.05
        if portfolio_value > 0:
            trade_pct = amount_usd / portfolio_value
            if trade_pct > max_alloc_pct:
                return {
                    "allowed": False,
                    "reason": f"Position size too large ({trade_pct:.1%}). Max allowed is {max_alloc_pct:.0%}."
                }

        # Rule 2: "Don't Catch Falling Knives"
        # If sentiment is very bearish (< -0.5) and trying to Buy
        if side.lower() == 'buy' and adds_exposure and sentiment_score < -0.5:
             return {
                "allowed": False,
                "reason": "Guardian blocked BUY due to Extreme Bearish sentiment (Falling Knife protection)."
            }
            
        # Rule 2b: Falling Knife (price). `market` is a core/market_guard.py reading prepared by the
        # tools layer. A BUY is blocked while the stock is still falling after a large drop, and -
        # when the operator requires the check - while the check cannot run.
        # A BUY that only covers a short is an exit, like a SELL, and is not refused.
        if side.lower() == 'buy' and adds_exposure and market:
            if market.get("falling_knife"):
                return {"allowed": False, "reason": _knife_reason(symbol, market)}
            if market.get("required") and market.get("status") not in ("ok", "disabled"):
                return {
                    "allowed": False,
                    "reason": (
                        f"Falling Knife check could not run for {symbol} "
                        f"({market.get('detail') or market.get('status')}); BUYs are blocked until it can. "
                        "Set MARKET_GUARD_ON_DATA_ERROR=allow to override."
                    ),
                }

        # Rule 3: Price Collar (Fat-finger protection - SEC Rule 15c3-5)
        if last_close_price and price:
            deviation = abs(price - last_close_price) / last_close_price
            if deviation > 0.05: # 5% collar
                return {
                    "allowed": False,
                    "reason": f"Price collar violation: {deviation:.2%} deviation from last close exceeds 5% limit."
                }

        # Rule 4: PDT (Pattern Day Trader) Check
        if day_trades_count >= 3 and portfolio_value < 25000:
             return {
                 "allowed": False,
                 "reason": "Pattern Day Trader protection: >3 day trades in account under $25k."
             }
            
        # Rule 5: Large trade flag. Advisory: a trade over $5,000 is flagged; nothing holds it for a
        # human unless EXECUTION_APPROVAL_MODE=approve_each.
        needs_confirmation = False
        if amount_usd > 5000.0:
            needs_confirmation = True

        return {
            "allowed": True,
            "needs_confirmation": needs_confirmation,
            "reason": (
                "Trade looks safe. It is over $5,000: consider EXECUTION_APPROVAL_MODE=approve_each to approve such trades."
                if needs_confirmation
                else "Trade looks safe."
            ),
        }


def _knife_reason(symbol: str, market: Dict[str, Any]) -> str:
    drop = market.get("drop_pct") or 0.0
    peak = market.get("peak_close")
    last = market.get("last_close")
    window = (market.get("rule") or {}).get("window_bars", 4)
    return (
        f"Guardian blocked BUY: {symbol} is down {drop:.1%} from its highest close of the last "
        f"{window} sessions ({peak:.2f} -> {last:.2f}) and is still at the lowest close of that "
        "window (Falling Knife protection, price)."
    )
