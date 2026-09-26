"""
The Falling Knife gate: what the Risk Guardian actually receives, and from where.

Two defects motivated these tests.

1. `analyze_social_sentiment` added a flat +0.2 for each configured source, so a panicking feed
   and a euphoric one both scored +0.4, the only reachable values were {0.0, 0.2, 0.4}, and the
   rule - which blocks below -0.5 - could never fire.
2. `place_stock_order` passed a hardcoded 0.0 for sentiment and passed neither daily loss nor
   drawdown, so three risk rules were inert on every real order.

This server now measures no sentiment at all (see `analyze_social_sentiment`), so these tests
pin the honest contract instead: nothing fabricates a score, a neutral 0.0 is always reported as
unmeasured, an agent may supply its own reading, and every risk rule reaches the order path.
"""

import json
from unittest.mock import MagicMock

import pytest

import intelligence.core as core
from app.core.container import global_container
from app.tools.trading import _sentiment_context, validate_trade_risk

GATE = -0.5  # RiskGuardian blocks a BUY below this
SYMBOL = "NVRA"

POSTS = [
    "$NVRA plunges 19% after the auditor resigns mid-quarter",
    "NVRA is crashing and I am down 60% on this position",
    "Guidance pulled entirely. Disaster for shareholders.",
    "$NVRA -19.4% | $13.88 | Vol 44.1M",
    "no bid under 14",
]


@pytest.fixture(autouse=True)
def clean_cache():
    core._sentiment_cache.cache.clear()
    yield
    core._sentiment_cache.cache.clear()


@pytest.fixture(autouse=True)
def steady_paper_metrics(monkeypatch):
    """Isolate these tests from whatever data/paper.db happens to hold."""
    engine = global_container.paper_engine
    if engine is not None:
        monkeypatch.setattr(
            type(engine),
            "get_risk_metrics",
            lambda self, account: {"equity": 100000.0, "daily_pnl_pct": 0.0, "drawdown_pct": 0.0},
        )


def _sources(monkeypatch, tweets, titles, tweet_state="ok", title_state="ok"):
    monkeypatch.setattr(core, "_recent_tweets", lambda s: (tweets, "Twitter (Real): stub", tweet_state))
    monkeypatch.setattr(core, "_recent_reddit_titles", lambda s: (titles, "Reddit (Real): stub", title_state))


# ---------------------------------------------------------------- nothing fabricates a score


def test_no_score_is_invented_from_the_number_of_configured_sources(monkeypatch):
    """The original defect: +0.2 per source, so configuring sources moved the 'sentiment'."""
    _sources(monkeypatch, POSTS, [])
    core.analyze_social_sentiment(SYMBOL)
    one_source = core.get_cached_sentiment_score(SYMBOL)

    _sources(monkeypatch, POSTS, POSTS)
    core.analyze_social_sentiment(SYMBOL)
    two_sources = core.get_cached_sentiment_score(SYMBOL)

    assert one_source == two_sources == 0.0


def test_the_cached_score_is_always_neutral(monkeypatch):
    for tweets, titles in ((POSTS, []), ([], POSTS), (POSTS, POSTS), ([], [])):
        _sources(monkeypatch, tweets, titles)
        core.analyze_social_sentiment(SYMBOL)
        assert core.get_cached_sentiment_score(SYMBOL) == 0.0


def test_the_posts_are_returned_for_the_agent_to_read(monkeypatch):
    _sources(monkeypatch, POSTS, [])
    report = core.analyze_social_sentiment(SYMBOL)
    for post in POSTS:
        assert post in report
    assert "does not score this text" in report


def test_the_report_says_how_to_act_on_what_the_agent_reads(monkeypatch):
    _sources(monkeypatch, POSTS, [])
    report = core.analyze_social_sentiment(SYMBOL)
    assert "sentiment_score" in report
    assert "untrusted" in report


def test_repeated_posts_are_listed_once(monkeypatch):
    _sources(monkeypatch, POSTS, list(POSTS))
    core.analyze_social_sentiment(SYMBOL)
    assert core.get_cached_sentiment(SYMBOL)["texts"] == len(POSTS)


def test_blank_and_junk_posts_are_dropped(monkeypatch):
    _sources(monkeypatch, ["", "   ", None, 42] + POSTS[:2], [])
    core.analyze_social_sentiment(SYMBOL)
    assert core.get_cached_sentiment(SYMBOL)["texts"] == 2


def test_unconfigured_sources_say_so_and_do_not_claim_a_reading(monkeypatch):
    _sources(monkeypatch, [], [], tweet_state="not_configured", title_state="not_configured")
    report = core.analyze_social_sentiment(SYMBOL)
    assert "No sentiment APIs configured" in report
    assert core.get_cached_sentiment(SYMBOL)["configured"] is False


def test_a_source_error_does_not_raise(monkeypatch):
    _sources(monkeypatch, [], [], tweet_state="error")
    assert core.analyze_social_sentiment(SYMBOL)


def test_blank_symbol_does_not_reach_the_sources():
    assert "no symbol given" in core.analyze_social_sentiment("")


# ---------------------------------------------------------------- ticker normalisation


@pytest.mark.parametrize(
    "given,expected",
    [
        ("AAPL", "AAPL"),
        ("aapl", "AAPL"),
        ("$AAPL", "AAPL"),
        (" $aapl ", "AAPL"),
        ("NASDAQ:AAPL", "AAPL"),
        ("nyse:brk.b", "BRK.B"),
    ],
)
def test_ticker_normalisation(given, expected):
    assert core.ticker(given) == expected


def test_share_classes_stay_distinct():
    assert core.ticker("BRK.A") != core.ticker("BRK.B")


@pytest.mark.parametrize("given", [None, 123, ["AAPL"], {"s": 1}, "   ", ""])
def test_a_symbol_that_is_not_a_ticker_is_empty_not_garbage(given):
    assert core.ticker(given) == ""


# ---------------------------------------------------------------- cache


def test_cache_is_keyed_by_normalised_ticker():
    """The original second defect: stored under one spelling, read under another."""
    core._sentiment_cache.set("$aapl", 12)
    assert core.get_cached_sentiment("NASDAQ:AAPL")["texts"] == 12
    assert core.get_cached_sentiment("AAPL")["texts"] == 12


def test_missing_symbol_reads_as_nothing_fetched():
    assert core.get_cached_sentiment("ZZZZ") is None
    assert core.get_cached_sentiment_score("ZZZZ") == 0.0


def test_stale_entry_expires(monkeypatch):
    core._sentiment_cache.set("AAPL", 12)
    real = core.time.monotonic
    monkeypatch.setattr(core.time, "monotonic", lambda: real() + core._sentiment_cache.ttl + 1)
    assert core.get_cached_sentiment("AAPL") is None


def test_expired_entries_are_evicted_on_write(monkeypatch):
    core._sentiment_cache.set("AAA", 12)
    real = core.time.monotonic
    monkeypatch.setattr(core.time, "monotonic", lambda: real() + core._sentiment_cache.ttl + 1)
    core._sentiment_cache.set("BBB", 3)
    assert "AAA" not in core._sentiment_cache.cache


def test_cache_entry_carries_the_count_and_age():
    core._sentiment_cache.set("AAPL", 9)
    entry = core.get_cached_sentiment("aapl")
    assert entry["texts"] == 9
    assert entry["age_seconds"] >= 0
    assert entry["configured"] is True


# ---------------------------------------------------------------- what the rule reports


def test_a_neutral_score_is_reported_as_unmeasured_not_as_calm():
    context = _sentiment_context(SYMBOL, None)
    assert context["score"] == 0.0
    assert context["source"] == "unmeasured"
    assert context["status"] == "not_measured"
    assert "does not score sentiment" in context["hint"]


def test_missing_credentials_are_reported_distinctly():
    core._sentiment_cache.set(SYMBOL, 0, configured=False)
    context = _sentiment_context(SYMBOL, None)
    assert context["status"] == "no_source_configured"
    assert "TWITTER_BEARER_TOKEN" in context["hint"]


def test_the_number_of_posts_available_is_reported():
    core._sentiment_cache.set(SYMBOL, 11)
    context = _sentiment_context(SYMBOL, None)
    assert context["posts_available"] == 11
    assert context["posts_age_seconds"] >= 0


def test_an_agent_supplied_score_is_labelled_as_such():
    context = _sentiment_context(SYMBOL, -0.9)
    assert context["score"] == -0.9
    assert context["source"] == "agent_supplied"
    assert context["status"] == "agent_supplied"
    assert "hint" not in context


@pytest.mark.parametrize("given,expected", [(-4.0, -1.0), (4.0, 1.0), (-0.5, -0.5), (0, 0.0)])
def test_an_agent_supplied_score_is_clamped_to_the_documented_range(given, expected):
    assert _sentiment_context(SYMBOL, given)["score"] == expected


def test_context_always_carries_every_key():
    keys = {"score", "source", "status", "posts_available", "posts_age_seconds"}
    assert keys <= set(_sentiment_context(SYMBOL, None))
    assert keys <= set(_sentiment_context(SYMBOL, -0.9))


# ---------------------------------------------------------------- the trade check


def test_an_agent_supplied_bearish_score_blocks_a_buy():
    payload = json.loads(validate_trade_risk("buy", SYMBOL, 1000.0, 100000.0, sentiment_score=-0.9))
    assert payload["data"]["result"]["allowed"] is False
    assert "Falling Knife" in payload["data"]["result"]["reason"]
    assert payload["data"]["sentiment"]["source"] == "agent_supplied"


def test_an_agent_supplied_bearish_score_does_not_block_a_sell():
    payload = json.loads(validate_trade_risk("sell", SYMBOL, 1000.0, 100000.0, sentiment_score=-0.9))
    assert payload["data"]["result"]["allowed"] is True


def test_without_a_supplied_score_the_rule_cannot_fire():
    payload = json.loads(validate_trade_risk("buy", SYMBOL, 1000.0, 100000.0))
    assert payload["data"]["result"]["allowed"] is True
    assert payload["data"]["sentiment"]["status"] == "not_measured"


def test_a_score_just_above_the_gate_does_not_block():
    payload = json.loads(validate_trade_risk("buy", SYMBOL, 1000.0, 100000.0, sentiment_score=GATE))
    assert payload["data"]["result"]["allowed"] is True


def test_the_trade_check_finds_the_posts_under_any_ticker_spelling():
    core._sentiment_cache.set("$nvra", 7)
    payload = json.loads(validate_trade_risk("buy", "NASDAQ:NVRA", 1000.0, 100000.0))
    assert payload["data"]["sentiment"]["posts_available"] == 7


# ---------------------------------------------------------------- the order path


@pytest.fixture
def quiet_ledger(monkeypatch):
    from app.tools import trading

    monkeypatch.setattr(trading.global_compliance_ledger, "record_event", MagicMock())
    return trading


def test_the_order_path_honours_an_agent_supplied_score(quiet_ledger):
    """The other half of the defect: place_stock_order passed a hardcoded 0.0."""
    payload = json.loads(
        quiet_ledger.place_stock_order(SYMBOL, "buy", 1.0, price=25.0, sentiment_score=-0.9)
    )
    assert payload["ok"] is False
    assert payload["error"]["code"] == "risk_blocked"
    assert "Falling Knife" in payload["error"]["message"]
    assert payload["error"]["data"]["sentiment"]["source"] == "agent_supplied"


def test_a_market_order_inherits_the_gate(quiet_ledger):
    payload = json.loads(quiet_ledger.place_market_order(SYMBOL, "buy", 10.0, sentiment_score=-0.9))
    assert payload["error"]["code"] == "risk_blocked"


def test_a_limit_order_inherits_the_gate(quiet_ledger):
    payload = json.loads(quiet_ledger.place_limit_order(SYMBOL, "buy", 10.0, 25.0, sentiment_score=-0.9))
    assert payload["error"]["code"] == "risk_blocked"


def test_the_order_path_allows_a_sell_on_a_bearish_score(quiet_ledger):
    payload = json.loads(
        quiet_ledger.place_stock_order(SYMBOL, "sell", 1.0, price=25.0, sentiment_score=-0.9)
    )
    assert payload.get("error", {}).get("code") != "risk_blocked"


def test_the_order_path_applies_the_daily_loss_rule(monkeypatch, quiet_ledger):
    """Previously never passed, so this rule was inert on every real order."""
    engine = global_container.paper_engine
    monkeypatch.setattr(
        type(engine),
        "get_risk_metrics",
        lambda self, account: {"equity": 100000.0, "daily_pnl_pct": -0.09, "drawdown_pct": 0.0},
    )
    payload = json.loads(quiet_ledger.place_stock_order(SYMBOL, "buy", 1.0, price=25.0))
    assert payload["ok"] is False
    assert payload["error"]["code"] == "risk_blocked"


def test_the_order_path_applies_the_drawdown_rule(monkeypatch, quiet_ledger):
    """Drawdown is reported as a positive fraction by the paper engine (peak-to-trough)."""
    engine = global_container.paper_engine
    monkeypatch.setattr(
        type(engine),
        "get_risk_metrics",
        lambda self, account: {"equity": 100000.0, "daily_pnl_pct": 0.0, "drawdown_pct": 0.25},
    )
    payload = json.loads(quiet_ledger.place_stock_order(SYMBOL, "buy", 1.0, price=25.0))
    assert payload["ok"] is False
    assert payload["error"]["code"] == "risk_blocked"


def test_an_ordinary_order_is_not_blocked(quiet_ledger):
    payload = json.loads(quiet_ledger.place_stock_order(SYMBOL, "buy", 1.0, price=25.0))
    assert payload.get("error", {}).get("code") != "risk_blocked"
