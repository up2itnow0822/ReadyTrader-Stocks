import os

from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "ReadyTrader-Stocks"
    VERSION: str = "0.1.0"
    
    # Stock Market Specifics
    MARKET_HOURS_START: str = os.getenv("MARKET_HOURS_START", "09:30")
    MARKET_HOURS_END: str = os.getenv("MARKET_HOURS_END", "16:00")
    MARKET_TIMEZONE: str = os.getenv("MARKET_TIMEZONE", "US/Eastern")
    # Not read by any check. The price-based Falling Knife rule (core/market_guard.py) is configured
    # with the MARKET_GUARD_* settings below; see docs/FALLING_KNIFE.md.
    CIRCUIT_BREAKER_PCT: float = float(os.getenv("CIRCUIT_BREAKER_PCT", "0.07"))
    
    PAPER_MODE: bool = os.getenv("PAPER_MODE", "true").lower() == "true"
    LIVE_TRADING_ENABLED: bool = os.getenv("LIVE_TRADING_ENABLED", "false").strip().lower() == "true"
    TRADING_HALTED: bool = os.getenv("TRADING_HALTED", "false").strip().lower() == "true"
    
    # Risk & execution
    EXECUTION_APPROVAL_MODE: str = os.getenv("EXECUTION_APPROVAL_MODE", "auto").strip().lower()
    EXECUTION_MODE: str = os.getenv("EXECUTION_MODE", "auto").strip().lower()
    RISK_PROFILE: str = os.getenv("RISK_PROFILE", "conservative").strip().lower()

    # Falling Knife (price) - docs/FALLING_KNIFE.md. Every BUY reads recent daily bars and is
    # blocked while the stock is still falling after a 15%+ drop from its highest recent close.
    MARKET_GUARD_ENABLED: bool = os.getenv("MARKET_GUARD_ENABLED", "true").strip().lower() == "true"
    # What a BUY does when the daily bars cannot be read: "block" or "allow". Unset means block in
    # live mode (a missed buy is recoverable, a buy into a collapse is not) and allow in paper mode.
    MARKET_GUARD_ON_DATA_ERROR: str = os.getenv("MARKET_GUARD_ON_DATA_ERROR", "").strip().lower()
    
    # Observability
    RATE_LIMIT_DEFAULT_PER_MIN: int = int(os.getenv("RATE_LIMIT_DEFAULT_PER_MIN", "120"))
    
settings = Settings()
