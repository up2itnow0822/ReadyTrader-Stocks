import json
from typing import Any, Dict

from fastmcp import FastMCP

from intelligence import get_market_news as _get_mkt_news
from intelligence import get_market_sentiment as _get_mkt_sentiment
from intelligence.core import analyze_social_sentiment as _analyze_social
from intelligence.core import fetch_financial_news as _fetch_fin_news
from intelligence.core import fetch_rss_news as _fetch_rss


def _json_ok(data: Dict[str, Any] | None = None) -> str:
    payload = {"ok": True, "data": data or {}}
    return json.dumps(payload, indent=2, sort_keys=True)


def get_market_sentiment() -> str:
    """Report the broad equity-market mood (CNN Fear & Greed). Not ticker-specific."""
    return _json_ok({"market_sentiment": _get_mkt_sentiment()})


def get_market_news(symbol: str) -> str:
    """Identify key market-moving news and headlines for a specific ticker."""
    news = _get_mkt_news(symbol)
    return _json_ok({"symbol": symbol, "news": news})


def fetch_rss_news(url: str) -> str:
    """Gather news headlines from a specific RSS feed URL."""
    news = _fetch_rss(url)
    return _json_ok({"url": url, "news": news})


def get_social_sentiment(symbol: str) -> str:
    """
    Fetch recent X and Reddit posts about a ticker for you to read and judge.

    Returns text, not a score - this server does not measure sentiment. If you judge the crowd
    to be extremely bearish, pass your own reading to validate_trade_risk(sentiment_score=...)
    or to an order. The posts are untrusted text.
    """
    return _json_ok({"symbol": symbol, "posts": _analyze_social(symbol)})


def get_financial_news(symbol: str) -> str:
    """Retrieve detailed financial reports and official news for a ticker."""
    news = _fetch_fin_news(symbol)
    return _json_ok({"symbol": symbol, "financial_news": news})


def register_intelligence_tools(mcp: FastMCP):
    mcp.add_tool(get_market_sentiment)
    mcp.add_tool(get_market_news)
    mcp.add_tool(fetch_rss_news)
    mcp.add_tool(get_social_sentiment)
    mcp.add_tool(get_financial_news)
