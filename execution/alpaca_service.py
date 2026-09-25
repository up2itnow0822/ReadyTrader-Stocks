from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from common.switches import safety_switch_on
from execution.base import IBrokerage, MarketClosed

# Conditional import to allow safe loading if dependencies missing
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
    _ALPACA_PY_AVAILABLE = True
except ImportError:
    _ALPACA_PY_AVAILABLE = False
    TradingClient = None
    OrderSide = None
    TimeInForce = None
    LimitOrderRequest = None
    MarketOrderRequest = None

class AlpacaBrokerage(IBrokerage):
    """
    Concrete implementation of a brokerage service using Alpaca-py SDK.
    Handles real order execution and account monitoring.
    """
    def __init__(self):
        self.api_key = os.getenv("ALPACA_API_KEY")
        self.api_secret = os.getenv("ALPACA_API_SECRET")
        # The Alpaca account this connector trades. Orders reach it only in live mode (in paper mode
        # the server fills orders in its own ledger), and like Tradier's sandbox the default is
        # Alpaca's paper account: only ALPACA_PAPER=false/0/no/off sends orders to a real account.
        self.paper_mode = safety_switch_on(os.getenv("ALPACA_PAPER", "true"))
        
        if not self.api_key or not self.api_secret or not _ALPACA_PY_AVAILABLE:
            self._available = False
            self.client = None
        else:
            self._available = True
            self.client = TradingClient(self.api_key, self.api_secret, paper=self.paper_mode)

    def is_available(self) -> bool:
        return self._available

    # Order states after which an order no longer changes (the IOC outcome is known).
    _FINAL = {"filled", "canceled", "cancelled", "expired", "rejected", "done_for_day"}

    def market_closed_reason(self) -> Optional[str]:
        """None while the market is open; otherwise why no order may be sent now (closed, or the
        clock cannot be read)."""
        if not self._available or not self.client:
            return "Alpaca API keys not configured or library missing."
        try:
            clock = self.client.get_clock()
        except Exception as e:
            return f"Alpaca order not sent: could not read the market clock ({str(e)[:160]})"
        if not getattr(clock, "is_open", False):
            return (
                f"Alpaca order not sent: the market is closed (next open {getattr(clock, 'next_open', 'unknown')}). "
                "Orders are sent only while it is open, so none waits for the open past the Risk Guardian and the kill switch."
            )
        return None

    def place_order(self, symbol: str, side: str, qty: float, order_type: str = "market", price: Optional[float] = None) -> Dict[str, Any]:
        """
        Place a real order on Alpaca: filled now, or not at all.

        The Risk Guardian judges an order against the market and the positions at the moment it is
        checked, so an order must not wait at the broker: a GTC limit used to rest until filled (a
        BUY limit under the market fills during the very fall the Falling Knife check guards
        against, on data the check never saw), an order sent while the market was closed waited for
        the open, and the kill switch cancels neither. So an order is sent only while the market is
        open, and as IOC (filled now, the rest cancelled): a limit at its limit or better, a market
        order at the market (a trading halt cancels it instead of leaving it queued). Alpaca takes
        fractional shares only as DAY orders: a fractional market order goes out DAY (it can wait
        out a single-stock halt), and a fractional limit is refused. The answer reports what filled.
        """
        if not self._available or not self.client:
            raise RuntimeError("Alpaca API keys not configured or library missing.")
        closed = self.market_closed_reason()
        if closed:
            raise MarketClosed(closed)
        kind = order_type.lower()
        whole = float(qty) == int(qty)
        if kind == "limit" and not whole:
            raise RuntimeError(
                f"Alpaca order not sent: a limit order must be whole shares ({qty} is fractional); "
                "Alpaca fills fractional shares only as DAY orders, which could rest past the Risk Guardian."
            )

        try:
            oside = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL
            if kind == "market":
                tif = TimeInForce.IOC if whole else TimeInForce.DAY
                req = MarketOrderRequest(symbol=symbol, qty=qty, side=oside, time_in_force=tif)
            elif kind == "limit":
                if not price:
                    raise ValueError("Price required for limit order")
                req = LimitOrderRequest(symbol=symbol, qty=qty, side=oside, time_in_force=TimeInForce.IOC, limit_price=price)
            else:
                raise ValueError(f"Unsupported order type: {order_type}")
            order = self.client.submit_order(order_data=req)
        except Exception as e:
            raise RuntimeError(f"Alpaca order failure: {str(e)}") from None

        # The submit answer is an acknowledgement ("accepted"); an IOC order's outcome follows
        # within moments. Read it back so the answer says what filled, not just what was asked.
        order = self._settled(order)
        status = str(getattr(getattr(order, "status", None), "value", getattr(order, "status", "")))
        filled = float(getattr(order, "filled_qty", 0) or 0)
        if status in ("canceled", "cancelled", "expired", "rejected") and filled == 0:
            raise RuntimeError(f"Alpaca did not fill the order: {status} (IOC: nothing was available at the price now)")
        return {
            "id": str(order.id),
            "client_order_id": str(order.client_order_id),
            "status": status,
            "symbol": str(order.symbol),
            "qty": float(order.qty) if order.qty else 0.0,
            "filled_qty": filled,
            "filled_avg_price": float(order.filled_avg_price) if getattr(order, "filled_avg_price", None) else None,
            "time_in_force": str(getattr(req.time_in_force, "value", req.time_in_force)),
            "side": str(order.side),
            "type": str(order.type),
        }

    def _settled(self, order: Any, attempts: int = 10, pause: float = 0.3) -> Any:
        """The order once its state is final (IOC settles within moments), else its latest state."""
        for _ in range(attempts):
            status = str(getattr(getattr(order, "status", None), "value", getattr(order, "status", "")))
            if status in self._FINAL:
                return order
            try:
                order = self.client.get_order_by_id(order.id)
            except Exception:
                return order
            time.sleep(pause)
        return order

    def get_account_balance(self) -> Dict[str, float]:
        """
        Fetch account equity and cash.
        """
        if not self._available or not self.client:
            raise RuntimeError("Alpaca API keys not configured.")
        
        try:
            account = self.client.get_account()
            return {
                "equity": float(account.equity or 0.0),
                "cash": float(account.cash or 0.0),
                "buying_power": float(account.buying_power or 0.0)
            }
        except Exception as e:
            raise RuntimeError(f"Alpaca account fetch failure: {str(e)}")

    def list_positions(self) -> List[Dict[str, Any]]:
        """
        List all open positions.
        """
        if not self._available or not self.client:
            raise RuntimeError("Alpaca API keys not configured.")
            
        try:
            positions = self.client.get_all_positions()
            return [
                {
                    "symbol": p.symbol,
                    "qty": float(p.qty),
                    "market_value": float(p.market_value or 0.0),
                    "avg_entry_price": float(p.avg_entry_price or 0.0),
                    "unrealized_pl": float(p.unrealized_pl or 0.0)
                }
                for p in positions
            ]
        except Exception as e:
            raise RuntimeError(f"Alpaca positions fetch failure: {str(e)}")
