import math
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from common.paths import data_path, ensure_parent

# The ledger's cash asset(s): valued at 1 USD. A ticker spelled like one cannot be paper traded.
CASH_ASSETS = frozenset({"USD", "USDT", "USDC", "DAI"})


class PaperTradingEngine:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv("READYTRADER_PAPER_DB_PATH", os.getenv("PAPER_DB_PATH", data_path("paper.db")))
        ensure_parent(self.db_path)
        self._init_db()
        
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        # Create balances table
        c.execute('''CREATE TABLE IF NOT EXISTS balances
                     (user_id TEXT, asset TEXT, amount REAL, 
                      PRIMARY KEY (user_id, asset))''')
        # Create orders table
        # NOTE: Prior versions had a schema bug (duplicate column names). We create a correct schema here.
        c.execute(
            '''CREATE TABLE IF NOT EXISTS orders
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id TEXT NOT NULL,
                      timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                      side TEXT NOT NULL,
                      symbol TEXT NOT NULL,
                      amount REAL NOT NULL,
                      price REAL NOT NULL,
                      total_value REAL NOT NULL,
                      type TEXT DEFAULT 'market',
                      status TEXT DEFAULT 'filled',
                      rationale TEXT,
                      pnl_realized REAL)'''
        )

        # Equity snapshots for real drawdown/daily PnL metrics
        c.execute(
            '''CREATE TABLE IF NOT EXISTS equity_snapshots
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id TEXT NOT NULL,
                      timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                      equity_usd REAL NOT NULL)'''
        )

        # Net deposits in USD (each valued when it was made), so the loss limits measure trading
        # results: topping the account up is neither a gain nor a way out of a halt.
        c.execute("CREATE TABLE IF NOT EXISTS paper_deposits (user_id TEXT PRIMARY KEY, deposits_usd REAL NOT NULL)")

        # Asset price cache (derived from executed trades; no external price feed required)
        c.execute(
            '''CREATE TABLE IF NOT EXISTS asset_prices
                     (asset TEXT PRIMARY KEY,
                      price_usd REAL NOT NULL,
                      updated_at TEXT DEFAULT CURRENT_TIMESTAMP)'''
        )
        conn.commit()
        
        # Schema Migration: ensure required columns exist for older DBs
        cols = {row[1] for row in c.execute("PRAGMA table_info(orders)").fetchall()}
        if "rationale" not in cols:
            c.execute("ALTER TABLE orders ADD COLUMN rationale TEXT")
        if "pnl_realized" not in cols:
            c.execute("ALTER TABLE orders ADD COLUMN pnl_realized REAL")
        if "type" not in cols:
            c.execute("ALTER TABLE orders ADD COLUMN type TEXT DEFAULT 'market'")
        if "status" not in cols:
            c.execute("ALTER TABLE orders ADD COLUMN status TEXT DEFAULT 'filled'")
        snap_cols = {row[1] for row in c.execute("PRAGMA table_info(equity_snapshots)").fetchall()}
        if "deposits_usd" not in snap_cols:
            c.execute("ALTER TABLE equity_snapshots ADD COLUMN deposits_usd REAL")
        conn.commit()
            
        conn.close()

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _set_asset_price_usd(self, asset: str, price_usd: float) -> None:
        if price_usd <= 0:
            return
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO asset_prices (asset, price_usd, updated_at) VALUES (?, ?, ?)",
            (asset.upper(), float(price_usd), self._now_iso()),
        )
        conn.commit()
        conn.close()

    def mark_price_usd(self, asset: str, price_usd: float) -> None:
        """Record a market price for `asset` (USD per unit) as its mark-to-market price."""
        try:
            price = float(price_usd)
        except (TypeError, ValueError):
            return
        if math.isfinite(price) and price > 0:
            self._set_asset_price_usd(asset, price)

    def _get_asset_price_usd(self, asset: str) -> Optional[float]:
        a = asset.upper()
        if a in CASH_ASSETS:
            return 1.0
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT price_usd FROM asset_prices WHERE asset=?", (a,))
        row = c.fetchone()
        conn.close()
        return float(row[0]) if row else None

    def get_portfolio_value_usd(self, user_id: str) -> float:
        """
        Mark-to-market portfolio using last known executed prices (derived from paper trades).
        Stablecoins are valued at $1.
        Assets without a known price are excluded (conservative).
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT asset, amount FROM balances WHERE user_id=?", (user_id,))
        rows = c.fetchall()
        conn.close()

        total = 0.0
        for asset, amount in rows:
            if amount is None:
                continue
            px = self._get_asset_price_usd(asset)
            if px is None:
                continue
            total += float(amount) * float(px)
        # Funds reserved by open limit orders are still the user's: a BUY reserved its cost in the
        # quote asset, a SELL its shares.
        for side, symbol, amount, reserved in self._open_orders(user_id):
            base, quote = self._parse_symbol(symbol)
            asset, qty = (quote, reserved) if side == "buy" else (base, amount)
            px = self._get_asset_price_usd(asset)
            if px is not None and qty:
                total += float(qty) * float(px)
        return float(total)

    def _open_orders(self, user_id: str) -> List[tuple]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT side, symbol, amount, total_value FROM orders WHERE user_id=? AND status='open'", (user_id,))
        rows = c.fetchall()
        conn.close()
        return rows

    def get_net_deposits_usd(self, user_id: str) -> float:
        """USD deposited, each deposit valued at its price when it was made."""
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT deposits_usd FROM paper_deposits WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        return float(row[0]) if row and row[0] is not None else 0.0

    def _snapshot_equity(self, user_id: str) -> None:
        equity = self.get_portfolio_value_usd(user_id)
        deposits = self.get_net_deposits_usd(user_id)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "INSERT INTO equity_snapshots (user_id, timestamp, equity_usd, deposits_usd) VALUES (?, ?, ?, ?)",
            (user_id, self._now_iso(), float(equity), float(deposits)),
        )
        conn.commit()
        conn.close()

    def mark_day_open(self, user_id: str) -> None:
        """Record the account's value once per UTC day, at its first risk check: the daily-loss
        baseline when the account made no snapshot the day before."""
        today = self._now_iso()[:10]
        conn = sqlite3.connect(self.db_path)
        seen = conn.execute(
            "SELECT 1 FROM equity_snapshots WHERE user_id=? AND substr(timestamp, 1, 10)=? LIMIT 1", (user_id, today)
        ).fetchone()
        has_any = conn.execute("SELECT 1 FROM equity_snapshots WHERE user_id=? LIMIT 1", (user_id,)).fetchone()
        conn.close()
        if has_any and not seen:
            self._snapshot_equity(user_id)
        
    def get_balance(self, user_id: str, asset: str) -> float:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT amount FROM balances WHERE user_id=? AND asset=?", (user_id, asset))
        row = c.fetchone()
        conn.close()
        return row[0] if row else 0.0
        
    def get_balances(self, user_id: str) -> Dict[str, float]:
        """Every non-zero balance for the user, by asset (the API's portfolio view)."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT asset, amount FROM balances WHERE user_id=? AND amount != 0 ORDER BY asset", (user_id,))
        rows = c.fetchall()
        conn.close()
        return {str(asset): float(amount) for asset, amount in rows}

    def deposit(self, user_id: str, asset: str, amount: float, snapshot: bool = True) -> str:
        """Adjust a balance. Trades pass snapshot=False and record equity once, after both legs:
        a snapshot between the legs saw the cash leave before the shares arrived (or the reverse)
        and recorded a drawdown that never happened."""
        current = self.get_balance(user_id, asset)
        new_balance = current + amount
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO balances (user_id, asset, amount) VALUES (?, ?, ?)",
                  (user_id, asset, new_balance))
        if snapshot:
            # A deposit (not a trade leg): capital added, valued at today's price. An asset with no
            # known price counts as 0 here, so deposit_paper_funds refuses to deposit one.
            row = c.execute("SELECT deposits_usd FROM paper_deposits WHERE user_id=?", (user_id,)).fetchone()
            value = float(amount) * (self._get_asset_price_usd(asset) or 0.0)
            c.execute(
                "INSERT OR REPLACE INTO paper_deposits (user_id, deposits_usd) VALUES (?, ?)",
                (user_id, (float(row[0]) if row and row[0] is not None else 0.0) + value),
            )
        conn.commit()
        conn.close()
        if snapshot:
            self._snapshot_equity(user_id)
        return f"Deposited {amount} {asset}. New Balance: {new_balance}"

    def reset_wallet(self, user_id: str) -> str:
        """Clear all balances and trade history for a user in paper mode."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("DELETE FROM balances WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM orders WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM equity_snapshots WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM paper_deposits WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
        return f"Paper wallet and history for {user_id} have been reset."

    def _parse_symbol(self, symbol: str) -> tuple[str, str]:
        """
        Parse symbol into (base, quote).
        If no slash, assume it's a Stock ticker quoted in USD.
        e.g. "AAPL" -> ("AAPL", "USD")
        e.g. "BTC/USDT" -> ("BTC", "USDT")
        """
        s = symbol.strip().upper()
        if '/' in s:
            parts = s.split('/', 1)
            return parts[0], parts[1]
        # For stocks, base is the ticker, quote is USD
        return s, "USD"

    def place_limit_order(self, user_id: str, side: str, symbol: str, amount: float, price: float) -> str:
        """
        Place a limit order. Reserve funds immediately.
        """
        base, quote = self._parse_symbol(symbol)
        total_value = amount * price
        
        # Check simulated balance and reserve
        if side == 'buy':
            balance = self.get_balance(user_id, quote)
            if balance < total_value:
                return f"Insufficient fund. Have {balance} {quote}, need {total_value}"
            # Lock funds (deduct now)
            self.deposit(user_id, quote, -total_value, snapshot=False)
            
        elif side == 'sell':
            balance = self.get_balance(user_id, base)
            if balance < amount:
                return f"Insufficient fund. Have {balance} {base}, need {amount}"
            # Lock funds
            self.deposit(user_id, base, -amount, snapshot=False)
            
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "INSERT INTO orders (user_id, side, symbol, amount, price, total_value, type, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'limit', 'open')",
            (user_id, side, symbol, amount, price, total_value),
        )
        order_id = c.lastrowid
        conn.commit()
        conn.close()
        return f"Order Placed: {side.upper()} {amount} {symbol} @ {price}. ID: {order_id}"

    def check_open_orders(self, symbol: str, current_price: float) -> List[str]:
        """
        Check and fill open orders based on current price.
        Returns a list of messages for filled orders.
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        # Find open orders for this symbol
        c.execute(
            "SELECT id, user_id, side, amount, price, total_value "
            "FROM orders WHERE symbol=? AND status='open'",
            (symbol,),
        )
        orders = c.fetchall()
        
        filled_msgs = []
        base, quote = self._parse_symbol(symbol)
        
        for order in orders:
            oid, uid, side, amt, price, val = order
            
            fill = False
            if side == 'buy' and current_price <= price:
                fill = True
                # Give user the Base asset (Quote was deducted at placement)
                self.deposit(uid, base, amt, snapshot=False)
                
            elif side == 'sell' and current_price >= price:
                fill = True
                # Give user the Quote asset (Base was deducted at placement)
                self.deposit(uid, quote, val, snapshot=False) # val was amt * limit_price
                
            if fill:
                c.execute("UPDATE orders SET status='filled' WHERE id=?", (oid,))
                # Commit before the helpers below open their own connections to write: an open
                # write transaction here made them fail with "database is locked".
                conn.commit()
                filled_msgs.append(f"Order #{oid} FILLED: {side.upper()} {amt} {symbol} @ {price}")
                # Update derived price cache from the fill price (best available for metrics)
                self._set_asset_price_usd(quote, 1.0 if quote.upper() in {"USDT", "USDC", "DAI", "USD"} else 1.0)
                if quote.upper() in {"USDT", "USDC", "DAI", "USD"}:
                    self._set_asset_price_usd(base, float(price))
                self._snapshot_equity(uid)
                
        conn.commit()
        conn.close()
        return filled_msgs
        
    def execute_trade(
        self,
        user_id: str,
        side: str,
        symbol: str,
        amount: float,
        price: float,
        rationale: str = "",
    ) -> str:
        """
        Execute a paper trade.
        """
        base, quote = self._parse_symbol(symbol)
        
        # If price is 0, try to fetch it from cache or mock
        if price <= 0:
            cached_price = self._get_asset_price_usd(base)
            if cached_price is None:
                raise ValueError(f"Price for {base} is unknown and pulse price was not provided. Execution failed (Zero-Mock Policy).")
            price = cached_price
        
            
        total_value = amount * price
        
        # Check simulated balance
        if side == 'buy':
            # Need quote asset (USDT)
            balance = self.get_balance(user_id, quote)
            if balance < total_value:
                return f"Insufficient fund. Have {balance} {quote}, need {total_value}"
            
            # Update balances
            self.deposit(user_id, quote, -total_value, snapshot=False)
            self.deposit(user_id, base, amount, snapshot=False)
            
        elif side == 'sell':
            # Need base asset (BTC)
            balance = self.get_balance(user_id, base)
            if balance < amount:
                return f"Insufficient fund. Have {balance} {base}, need {amount}"
            
            # Update balances
            self.deposit(user_id, base, -amount, snapshot=False)
            self.deposit(user_id, quote, total_value, snapshot=False)
            
        # Log order
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "INSERT INTO orders (user_id, side, symbol, amount, price, total_value, rationale) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, side, symbol, amount, price, total_value, rationale),
        )
        conn.commit()
        conn.close()

        # Update derived price cache (if quote looks like USD stable)
        if quote.upper() in {"USDT", "USDC", "DAI", "USD"}:
            self._set_asset_price_usd(base, float(price))
            self._set_asset_price_usd(quote, 1.0)
        self._snapshot_equity(user_id)
        
        return (
            f"Paper Trade Executed: {side.upper()} {amount} {symbol} @ {price}. "
            f"Value: {total_value} {quote}. Rationale: {rationale}"
        )

    def get_risk_metrics(self, user_id: str) -> Dict[str, float]:
        """
        Risk metrics measured on trading results: deposits are neither gains nor losses, and
        neither end a halt nor start one. Returns {daily_pnl_pct, drawdown_pct, max_drawdown_pct}
        (fractions, e.g. 0.10).

        The account's results are chained into a performance index (time-weighted return): between
        two snapshots, the return is the change in value less the deposits made in between, over the
        value before. `drawdown_pct` is the index's CURRENT fall from its best level (what the Risk
        Guardian's drawdown rule reads; reporting the deepest fall as current blocked every BUY after
        one dip); `max_drawdown_pct` is the deepest fall on record. `daily_pnl_pct` is the index's
        change since the last snapshot of the previous UTC day, or since the day's first snapshot when
        the account made none the day before. The account's value now (at the latest marked prices)
        ends the series, so a price move counts before the next trade.
        """
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT timestamp, equity_usd, deposits_usd FROM equity_snapshots WHERE user_id=? ORDER BY timestamp ASC, id ASC",
            (user_id,),
        ).fetchall()
        conn.close()

        if not rows:
            return {"daily_pnl_pct": 0.0, "drawdown_pct": 0.0, "max_drawdown_pct": 0.0}

        # Snapshots from before deposits were tracked carry NULL: counted as no deposits (the old rule).
        series = [(str(ts), float(eq), float(dep or 0.0)) for ts, eq, dep in rows]
        series.append((self._now_iso(), self.get_portfolio_value_usd(user_id), self.get_net_deposits_usd(user_id)))

        index = peak = 1.0
        max_drawdown = current_drawdown = 0.0
        levels = [(series[0][0], index)]
        for (_, prev_equity, prev_deposits), (ts, equity, deposits) in zip(series, series[1:]):
            if prev_equity > 0:
                period_return = (equity - (deposits - prev_deposits)) / prev_equity - 1.0
                index *= max(0.0, 1.0 + period_return)
            peak = max(peak, index)
            current_drawdown = 1.0 - index / peak if peak > 0 else 0.0
            max_drawdown = max(max_drawdown, current_drawdown)
            levels.append((ts, index))

        today = self._now_iso()[:10]
        yesterday = (datetime.fromisoformat(today) - timedelta(days=1)).date().isoformat()
        before = [level for ts, level in levels if ts[:10] == yesterday]
        start = before[-1] if before else next((level for ts, level in levels if ts[:10] == today), levels[-1][1])
        daily_pct = index / start - 1.0 if start > 0 else 0.0

        return {
            "daily_pnl_pct": float(daily_pct),
            "drawdown_pct": float(current_drawdown),
            "max_drawdown_pct": float(max_drawdown),
        }
