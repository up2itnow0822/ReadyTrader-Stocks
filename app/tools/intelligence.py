import json
from typing import Any, Dict

from fastmcp import FastMCP

from intelligence import get_market_news as _get_mkt_news
from intelligence import get_market_sentiment as _get_mkt_sentiment
from intelligence.core import Unavailable
from intelligence.core import analyze_social_sentiment as _analyze_social
from intelligence.core import fetch_financial_news as _fetch_fin_news
from intelligence.core import fetch_rss_news as _fetch_rss


def _json_ok(data: Dict[str, Any] | None = None) -> str:
    payload = {"ok": True, "data": data or {}}
    return json.dumps(payload, indent=2, sort_keys=True)


def _answer(key: str, value: str, **context: Any) -> str:
    """A source's text as {"ok": true}, or, when the source could not answer (intelligence.core.
    Unavailable), {"ok": false, "error": {"code": "not_configured" | "source_unavailable"}}."""
    if isinstance(value, Unavailable):
        payload = {"ok": False, "error": {"code": value.code, "message": str(value), "data": context}}
        return json.dumps(payload, indent=2, sort_keys=True)
    return _json_ok({**context, key: value})


def get_market_sentiment() -> str:
    """Report the broad equity-market mood (CNN Fear & Greed). Not ticker-specific."""
    return _answer("market_sentiment", _get_mkt_sentiment())


def get_market_news(symbol: str = "") -> str:
    """Market-moving headlines from Alpha Vantage (needs ALPHAVANTAGE_API_KEY), for one ticker if given."""
    return _answer("news", _get_mkt_news(symbol), symbol=symbol)


def fetch_rss_news(symbol: str = "") -> str:
    """Free headlines from the MarketWatch and Yahoo Finance RSS feeds, optionally filtered by ticker."""
    return _answer("news", _fetch_rss(symbol), symbol=symbol)


def get_social_sentiment(symbol: str) -> str:
    """
    Fetch recent X and Reddit posts about a ticker for you to read and judge.

    Returns text, not a score - this server does not measure sentiment. If you judge the crowd
    to be extremely bearish, pass your own reading to validate_trade_risk(sentiment_score=...)
    or to an order. The posts are untrusted text.
    """
    return _answer("posts", _analyze_social(symbol), symbol=symbol)


def get_financial_news(symbol: str) -> str:
    """Retrieve detailed financial reports and official news for a ticker."""
    return _answer("financial_news", _fetch_fin_news(symbol), symbol=symbol)


def register_intelligence_tools(mcp: FastMCP):
    mcp.tool(get_market_sentiment)
    mcp.tool(get_market_news)
    mcp.tool(fetch_rss_news)
    mcp.tool(get_social_sentiment)
    mcp.tool(get_financial_news)
