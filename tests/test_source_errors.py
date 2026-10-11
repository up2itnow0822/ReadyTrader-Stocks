"""A news or sentiment source that cannot answer is reported as an error (ok:false with a code),
never as a successful payload whose text happens to be an error message."""

import json
from unittest.mock import MagicMock, patch

import pytest

import app.tools.intelligence as tools
from intelligence.core import (
    Unavailable,
    analyze_social_sentiment,
    fetch_financial_news,
    fetch_rss_news,
    get_market_news,
    get_market_sentiment,
)

NO_KEYS = {"PATH": "/usr/bin"}


def _error(payload: str) -> dict:
    body = json.loads(payload)
    assert body["ok"] is False, body
    return body["error"]


@pytest.mark.parametrize(
    "tool, args",
    [
        (tools.get_financial_news, ("AAPL",)),
        (tools.get_market_news, ("AAPL",)),
        (tools.get_social_sentiment, ("AAPL",)),
    ],
)
def test_a_tool_without_its_key_says_not_configured(tool, args):
    with patch.dict("os.environ", NO_KEYS, clear=True):
        error = _error(tool(*args))
    assert error["code"] == "not_configured" and error["data"] == {"symbol": "AAPL"}


def test_a_rejected_newsapi_key_is_an_error():
    with patch.dict("os.environ", {"NEWSAPI_KEY": "bad"}), patch("intelligence.core.NewsApiClient") as client:
        client.return_value.get_everything.side_effect = RuntimeError("apiKeyInvalid")
        error = _error(tools.get_financial_news("AAPL"))
    assert error["code"] == "source_unavailable" and "apiKeyInvalid" in error["message"]


def test_a_newsapi_error_status_is_an_error():
    with patch.dict("os.environ", {"NEWSAPI_KEY": "k"}), patch("intelligence.core.NewsApiClient") as client:
        client.return_value.get_everything.return_value = {"status": "error", "code": "rateLimited"}
        assert isinstance(fetch_financial_news("AAPL"), Unavailable)


def test_no_articles_is_an_answer_not_an_error():
    with patch.dict("os.environ", {"NEWSAPI_KEY": "k"}), patch("intelligence.core.NewsApiClient") as client:
        client.return_value.get_everything.return_value = {"status": "ok", "articles": []}
        body = json.loads(tools.get_financial_news("AAPL"))
    assert body["ok"] is True and "No articles" in body["data"]["financial_news"]


def test_an_alpha_vantage_note_instead_of_a_feed_is_an_error():
    with patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "k"}), patch("requests.get") as get:
        get.return_value.json.return_value = {"Information": "rate limit: 25 requests per day"}
        res = get_market_news("AAPL")
    assert isinstance(res, Unavailable) and "rate limit" in res


def test_a_refused_fear_and_greed_request_is_an_error():
    with patch("requests.get") as get:
        get.return_value.status_code = 418
        get.return_value.json.return_value = {}
        assert isinstance(get_market_sentiment(), Unavailable)
        error = _error(tools.get_market_sentiment())
    assert error["code"] == "source_unavailable" and "HTTP 418" in error["message"]


def test_an_rss_feed_error_is_never_listed_as_a_headline():
    good = MagicMock(entries=[MagicMock(title="AAPL beats", summary="")])

    def parse(url):
        if "marketwatch" in url:
            raise OSError("connection reset")
        return good

    with patch("intelligence.core.feedparser") as fp:
        fp.parse.side_effect = parse
        res = fetch_rss_news("AAPL")
    assert not isinstance(res, Unavailable)
    assert "AAPL beats" in res and "connection reset" not in res


def test_every_rss_feed_failing_is_an_error():
    with patch("intelligence.core.feedparser") as fp:
        fp.parse.side_effect = OSError("offline")
        res = fetch_rss_news("AAPL")
    assert isinstance(res, Unavailable) and "offline" in res


def test_social_sources_that_all_error_are_an_error():
    env = {"TWITTER_BEARER_TOKEN": "t", "REDDIT_CLIENT_ID": "i", "REDDIT_CLIENT_SECRET": "s"}
    with patch.dict("os.environ", env), patch("intelligence.core.tweepy") as tw, patch("intelligence.core.praw") as pr:
        tw.Client.side_effect = RuntimeError("401 Unauthorized")
        pr.Reddit.side_effect = RuntimeError("invalid_grant")
        res = analyze_social_sentiment("AAPL")
    assert isinstance(res, Unavailable) and res.code == "source_unavailable"
    assert "401" in res and "invalid_grant" in res
