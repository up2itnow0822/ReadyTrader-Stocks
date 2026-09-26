from unittest.mock import MagicMock, patch

from intelligence.core import (
    SentimentCache,
    analyze_social_sentiment,
    fetch_financial_news,
    fetch_rss_news,
    get_cached_sentiment_score,
    get_market_news,
    get_market_sentiment,
)


def test_get_market_sentiment_success():
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "fear_and_greed": {
                "rating": "greed",
                "now": 65.0
            }
        }
        mock_get.return_value = mock_response
        
        sentiment = get_market_sentiment()
        assert "CNN Fear & Greed: GREED (65.0)" in sentiment

def test_a_refused_fear_and_greed_request_is_not_reported_as_a_reading():
    """CNN answers automated clients with 418; that used to read as 'UNKNOWN (0.0)'."""
    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=418, json=MagicMock(return_value={}))
        sentiment = get_market_sentiment()
        assert "unavailable (HTTP 418)" in sentiment and "0.0" not in sentiment

def test_get_market_sentiment_failure():
    with patch("requests.get", side_effect=Exception("API Down")):
        sentiment = get_market_sentiment()
        assert "Error fetching CNN Fear & Greed" in sentiment

def test_analyze_social_sentiment_no_keys():
    # Ensure env vars are unset
    with patch.dict("os.environ", {}, clear=True):
        res = analyze_social_sentiment("AAPL")
        assert "No sentiment APIs configured" in res
        # A missing source must not be reported as a measured neutral market.
        assert "no data source" in res or "treats sentiment as neutral" in res

def test_sentiment_cache():
    cache = SentimentCache()
    cache.set("AAPL", 12)

    cached = cache.get("AAPL")
    # The cache records how much text was fetched, never a score - nothing here measures one.
    assert cached["texts"] == 12
    assert cached["configured"] is True
    assert "score" not in cached
    # Any spelling of the ticker reaches the same entry.
    assert cache.get("$aapl")["texts"] == 12

    # Expiry runs on the monotonic clock, so a wall-clock step cannot pin or expire an entry.
    import time

    real = time.monotonic
    with patch("time.monotonic", side_effect=lambda: real() + cache.ttl + 1):
        assert cache.get("AAPL") is None

def test_get_cached_sentiment_score():
    """This server measures no sentiment, so the cached score is neutral for every symbol."""
    assert get_cached_sentiment_score("AAPL") == 0.0
    assert get_cached_sentiment_score("GOOG") == 0.0

def test_get_market_news_no_key():
    with patch.dict("os.environ", {}, clear=True):
        res = get_market_news()
        assert "ALPHAVANTAGE_API_KEY missing" in res

def test_get_market_news_success():
    with patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "test"}):
        with patch("requests.get") as mock_get:
            mock_get.return_value.json.return_value = {
                "feed": [
                    {"title": "Stock Up", "source": "CNBC"}
                ]
            }
            res = get_market_news()
            assert "Stock Up" in res

def test_fetch_rss_news_no_lib():
    with patch("intelligence.core.feedparser", None):
        res = fetch_rss_news("AAPL")
        assert "feedparser library not installed" in res

def test_fetch_rss_news_success():
    # Only if feedparser is installed (it is in main env, but maybe verify)
    # Use mock
    with patch("intelligence.core.feedparser") as mock_fp:
        entry = MagicMock()
        entry.title = "AAPL releases iPhone 20"
        entry.summary = "It is great"
        
        mock_feed = MagicMock()
        mock_feed.entries = [entry]
        mock_fp.parse.return_value = mock_feed
        
        res = fetch_rss_news("AAPL")
        assert "AAPL releases iPhone 20" in res

def test_fetch_financial_news_no_key():
    with patch.dict("os.environ", {}, clear=True):
        res = fetch_financial_news("AAPL")
        assert "NEWSAPI_KEY missing" in res

def test_fetch_financial_news_success():
    with patch.dict("os.environ", {"NEWSAPI_KEY": "test"}):
        with patch("intelligence.core.NewsApiClient") as MockClient:
            client_inst = MockClient.return_value
            client_inst.get_everything.return_value = {
                "status": "ok",
                "articles": [
                    {"title": "Boom", "source": {"name": "Test"}}
                ]
            }
            res = fetch_financial_news("AAPL")
            assert "Boom" in res

def test_analyze_social_sentiment_mocked_success():
    with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "x", "REDDIT_CLIENT_ID": "r", "REDDIT_CLIENT_SECRET": "s"}):
        with patch("intelligence.core.tweepy") as mock_tweepy:
            with patch("intelligence.core.praw") as mock_praw:
                # Mock Twitter
                mock_client = MagicMock()
                mock_tweet = MagicMock()
                mock_tweet.text = "AAPL is going up #bullish"
                mock_client.search_recent_tweets.return_value = MagicMock(data=[mock_tweet])
                mock_tweepy.Client.return_value = mock_client
                
                # Mock Reddit
                mock_reddit = MagicMock()
                mock_sub = MagicMock()
                mock_post = MagicMock()
                mock_post.title = "AAPL DD"
                mock_sub.search.return_value = [mock_post]
                mock_reddit.subreddit.return_value = mock_sub
                mock_praw.Reddit.return_value = mock_reddit

                res = analyze_social_sentiment("AAPL")
                assert "Twitter (Real): 1 recent posts" in res
                assert "Reddit (Real): 1 posts" in res
                # The posts themselves are handed to the agent, not condensed into a number.
                assert "AAPL is going up #bullish" in res
                assert "AAPL DD" in res
