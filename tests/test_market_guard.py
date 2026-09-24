"""
Falling Knife (price): core/market_guard.py and its wiring into the trade check and the order path.

The rule and its thresholds come from a study on real daily history (docs/FALLING_KNIFE.md). The
real-bar fixture pins the shipped code to actual market episodes, including ones it must not
block.
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import market_bars as mb
import pytest

import app.tools.trading as trading
from app.core.config import safety_switch_on, settings
from app.core.container import global_container
from core import market_guard as mg

REAL = json.loads((Path(__file__).parent / "fixtures" / "market_guard_real_bars.json").read_text())["cases"]
SYMBOL = "WAL"


def use_bars(monkeypatch, bars):
    monkeypatch.setattr(trading, "_fetch_daily_bars", lambda symbol: bars)


def fail_fetch(monkeypatch, exc=RuntimeError("provider down")):
    def boom(symbol):
        raise exc

    monkeypatch.setattr(trading, "_fetch_daily_bars", boom)


@pytest.fixture(autouse=True)
def steady_paper_metrics(monkeypatch):
    engine = global_container.paper_engine
    if engine is not None:
        monkeypatch.setattr(
            type(engine),
            "get_risk_metrics",
            lambda self, account: {"daily_pnl_pct": 0.0, "drawdown_pct": 0.0},
        )
        monkeypatch.setattr(type(engine), "get_portfolio_value_usd", lambda self, account: 100000.0)


@pytest.fixture
def quiet_ledger(monkeypatch):
    monkeypatch.setattr(trading.global_compliance_ledger, "record_event", MagicMock())
    return trading


# ---------------------------------------------------------------- the rule on real history


@pytest.mark.parametrize("case", REAL, ids=[f"{c['symbol']}-{c['date']}" for c in REAL])
def test_real_episodes_score_as_recorded(case):
    reading = mg.assess(case["bars"], now_ms=case["bars"][-1][0])
    assert reading.status == mg.STATUS_OK
    assert reading.falling_knife is case["expect_falling_knife"], case["note"]
    assert reading.drop_pct == pytest.approx(case["expect_drop_pct"], abs=1e-4)


def test_the_real_fixture_covers_both_outcomes():
    """A fixture of only positives or only negatives would pass a broken rule."""
    outcomes = {c["expect_falling_knife"] for c in REAL}
    assert outcomes == {True, False}


def test_svb_weekend_is_blocked_and_the_bounce_is_not():
    by_date = {c["date"]: c for c in REAL if c["symbol"] == "WAL"}
    assert mg.assess(by_date["2023-03-10"]["bars"], now_ms=by_date["2023-03-10"]["bars"][-1][0]).falling_knife
    after = mg.assess(by_date["2023-03-14"]["bars"], now_ms=by_date["2023-03-14"]["bars"][-1][0])
    assert after.drop_pct > mg.KNIFE_MIN_DROP and after.still_falling is False and not after.falling_knife


# ---------------------------------------------------------------- the rule on synthetic bars


def test_a_calm_tape_is_not_a_falling_knife():
    reading = mg.assess(mb.calm())
    assert reading.status == mg.STATUS_OK and not reading.falling_knife


def test_a_collapse_that_is_still_falling_is_a_falling_knife():
    reading = mg.assess(mb.collapse(drop=0.30))
    assert reading.falling_knife and reading.still_falling
    assert reading.drop_pct >= 0.30


def test_a_drop_just_under_the_floor_is_not_a_falling_knife():
    bars = mb.collapse(drop=0.13)
    reading = mg.assess(bars)
    assert reading.drop_pct < mg.KNIFE_MIN_DROP and not reading.falling_knife


def test_a_bad_high_print_is_not_read_as_a_collapse():
    """Only closes count: a phantom spike high (a bad provider print) must not look like a drop."""
    bars = mb.calm()
    spike = bars[-2]
    bars[-2] = [spike[0], spike[1], spike[2] * 1.5, spike[3], spike[4], spike[5]]
    reading = mg.assess(bars)
    assert reading.drop_pct < 0.01 and not reading.falling_knife


def test_the_shipped_thresholds_are_the_frozen_ones():
    """docs/FALLING_KNIFE.md: 15% from the highest close of today and the three prior sessions."""
    assert (mg.KNIFE_WINDOW, mg.KNIFE_MIN_DROP) == (3, 0.15)


def test_a_collapse_that_has_bounced_is_not_a_falling_knife():
    """Still down more than the floor, but closing above the previous close: it has stopped falling."""
    bars = mb.collapse(drop=0.35)
    last, prev = bars[-1], bars[-2]
    bounced = prev[4] * 1.01
    bars[-1] = [last[0], last[1], max(last[2], bounced), last[3], bounced, last[5]]
    reading = mg.assess(bars)
    assert reading.drop_pct > mg.KNIFE_MIN_DROP and not reading.still_falling and not reading.falling_knife


def test_a_small_bounce_that_stays_below_the_prior_close_is_still_falling():
    """A 10% bounce off the low that stays under yesterday's close is not a recovery."""
    bars = mb.collapse(drop=0.35)
    last = bars[-1]
    bounced = last[4] * 1.10
    bars[-1] = [last[0], last[1], max(last[2], bounced), last[3], bounced, last[5]]
    assert bounced < bars[-2][4]
    assert mg.assess(bars).falling_knife


def test_too_few_bars_is_insufficient_not_a_verdict():
    reading = mg.assess(mb.calm(n=mg.KNIFE_WINDOW))
    assert reading.status == mg.STATUS_INSUFFICIENT and not reading.falling_knife


def test_stale_bars_are_not_read_as_now():
    old_end = mb.calm()[-1][0] - 10 * mb.DAY_MS
    reading = mg.assess(mb.collapse(end_ms=old_end))
    assert reading.status == mg.STATUS_STALE and not reading.falling_knife


def test_a_long_weekend_is_not_stale():
    end = mb.calm()[-1][0]
    reading = mg.assess(mb.calm(end_ms=end - 4 * mb.DAY_MS), now_ms=end)
    assert reading.status == mg.STATUS_OK


@pytest.mark.parametrize(
    "bad_row",
    [[None, 1, 1, 1, 1, 0], [0, "x", 1, 1, 1, 0], [0, 1, float("nan"), 1, 1, 0], [0, 1, 1, 1, -5, 0], [0, 1, 0.5, 2, 1, 0], [1]],
)
def test_malformed_rows_are_dropped_not_trusted(bad_row):
    bars = mb.calm()
    reading = mg.assess(bars[:-1] + [bad_row] + bars[-1:])
    assert reading.status == mg.STATUS_OK and reading.bars == len(bars)


def test_rows_are_sorted_and_deduplicated():
    bars = mb.collapse(drop=0.30)
    shuffled = list(reversed(bars)) + bars[-3:]
    assert mg.assess(shuffled).falling_knife == mg.assess(bars).falling_knife
    assert mg.assess(shuffled).bars == len(bars)


def test_empty_or_none_input_is_insufficient():
    assert mg.assess([]).status == mg.STATUS_INSUFFICIENT
    assert mg.assess(None).status == mg.STATUS_INSUFFICIENT


# ---------------------------------------------------------------- the trade check


def test_a_buy_into_a_collapse_is_blocked(monkeypatch):
    use_bars(monkeypatch, mb.collapse(drop=0.30))
    payload = json.loads(trading.validate_trade_risk("buy", SYMBOL, 1000.0, 100000.0))
    assert payload["data"]["result"]["allowed"] is False
    assert "Falling Knife protection, price" in payload["data"]["result"]["reason"]
    assert payload["data"]["market"]["falling_knife"] is True


def test_a_sell_during_a_collapse_is_not_blocked_and_does_not_fetch(monkeypatch):
    fail_fetch(monkeypatch)  # would raise if the sell touched market data
    payload = json.loads(trading.validate_trade_risk("sell", SYMBOL, 1000.0, 100000.0))
    assert payload["data"]["result"]["allowed"] is True
    assert payload["data"]["market"]["status"] == "not_checked"


def test_a_buy_on_a_calm_tape_is_allowed_and_reports_the_reading():
    payload = json.loads(trading.validate_trade_risk("buy", SYMBOL, 1000.0, 100000.0))
    assert payload["data"]["result"]["allowed"] is True
    market = payload["data"]["market"]
    assert market["status"] == "ok" and market["falling_knife"] is False
    assert market["rule"] == {"window_bars": mg.KNIFE_WINDOW + 1, "min_drop": mg.KNIFE_MIN_DROP}


def test_the_check_can_be_disabled(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_GUARD_ENABLED", False)
    use_bars(monkeypatch, mb.collapse(drop=0.40))
    payload = json.loads(trading.validate_trade_risk("buy", SYMBOL, 1000.0, 100000.0))
    assert payload["data"]["result"]["allowed"] is True
    assert payload["data"]["market"]["status"] == "disabled"


# ---------------------------------------------------------------- when the data cannot be read


def test_unreadable_data_blocks_a_live_buy(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_MODE", False)
    monkeypatch.setattr(settings, "MARKET_GUARD_ON_DATA_ERROR", "")
    fail_fetch(monkeypatch)
    payload = json.loads(trading.validate_trade_risk("buy", SYMBOL, 1000.0, 100000.0))
    assert payload["data"]["result"]["allowed"] is False
    assert "could not run" in payload["data"]["result"]["reason"]
    assert payload["data"]["market"]["status"] == "unavailable"


def test_unreadable_data_allows_a_paper_buy_but_says_so(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_GUARD_ON_DATA_ERROR", "")
    fail_fetch(monkeypatch)
    payload = json.loads(trading.validate_trade_risk("buy", SYMBOL, 1000.0, 100000.0))
    assert payload["data"]["result"]["allowed"] is True
    assert payload["data"]["market"]["status"] == "unavailable"
    assert payload["data"]["market"]["on_data_error"] == "allow"


@pytest.mark.parametrize("value,paper,blocks", [("block", True, True), ("allow", False, False), ("bogus", True, True)])
def test_the_data_error_policy_can_be_set_and_fails_closed(monkeypatch, value, paper, blocks):
    monkeypatch.setattr(settings, "PAPER_MODE", paper)
    monkeypatch.setattr(settings, "MARKET_GUARD_ON_DATA_ERROR", value)
    fail_fetch(monkeypatch)
    payload = json.loads(trading.validate_trade_risk("buy", SYMBOL, 1000.0, 100000.0))
    assert payload["data"]["result"]["allowed"] is (not blocks)


def test_stale_data_counts_as_unreadable_in_live_mode(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_MODE", False)
    monkeypatch.setattr(settings, "MARKET_GUARD_ON_DATA_ERROR", "")
    use_bars(monkeypatch, mb.calm(end_ms=mb.calm()[-1][0] - 10 * mb.DAY_MS))
    payload = json.loads(trading.validate_trade_risk("buy", SYMBOL, 1000.0, 100000.0))
    assert payload["data"]["result"]["allowed"] is False
    assert payload["data"]["market"]["status"] == "stale"


def test_an_error_message_is_truncated(monkeypatch):
    fail_fetch(monkeypatch, RuntimeError("x" * 5000))
    payload = json.loads(trading.validate_trade_risk("buy", SYMBOL, 1000.0, 100000.0))
    assert len(payload["data"]["market"]["detail"]) < 200


# ---------------------------------------------------------------- the order path


def test_the_order_path_blocks_a_buy_into_a_collapse(monkeypatch, quiet_ledger):
    use_bars(monkeypatch, mb.collapse(drop=0.30))
    payload = json.loads(trading.place_stock_order(SYMBOL, "buy", 10.0, price=25.0))
    assert payload["ok"] is False
    assert payload["error"]["code"] == "risk_blocked"
    assert payload["error"]["data"]["market"]["falling_knife"] is True


@pytest.mark.parametrize(
    "call",
    [
        lambda: trading.place_market_order(SYMBOL, "buy", 10.0),
        lambda: trading.place_limit_order(SYMBOL, "buy", 10.0, 25.0),
    ],
    ids=["market", "limit"],
)
def test_every_order_entry_point_applies_the_rule(monkeypatch, quiet_ledger, call):
    use_bars(monkeypatch, mb.collapse(drop=0.30))
    assert json.loads(call())["error"]["code"] == "risk_blocked"


def test_the_order_path_lets_a_sell_through_during_a_collapse(monkeypatch, quiet_ledger):
    use_bars(monkeypatch, mb.collapse(drop=0.30))
    payload = json.loads(trading.place_stock_order(SYMBOL, "sell", 10.0, price=25.0))
    assert payload.get("error", {}).get("code") != "risk_blocked"


def test_the_order_path_blocks_a_live_buy_when_data_is_unreadable(monkeypatch, quiet_ledger):
    class Broker:  # configured, with a readable account, so only the market guard can refuse
        def is_available(self):
            return True

        def get_account_balance(self):
            return {"equity": 1_000_000.0}

        def list_positions(self):
            return []

    monkeypatch.setitem(global_container.brokerages, "alpaca", Broker())
    monkeypatch.setattr(settings, "PAPER_MODE", False)
    monkeypatch.setattr(settings, "MARKET_GUARD_ON_DATA_ERROR", "")
    fail_fetch(monkeypatch)
    payload = json.loads(trading.place_stock_order(SYMBOL, "buy", 10.0, price=25.0))
    assert payload["error"]["code"] == "risk_blocked"
    assert "could not run" in payload["error"]["message"]


# ---------------------------------------------------------------- the network seam


def test_the_fetch_asks_the_provider_for_daily_bars(monkeypatch):
    """Undo the conftest stub for one call and check what the real seam requests."""
    monkeypatch.undo()
    calls = []

    class FakeProvider:
        def fetch_ohlcv(self, symbol, timeframe, limit):
            calls.append((symbol, timeframe, limit))
            return mb.calm()

    monkeypatch.setattr(global_container, "exchange_provider", FakeProvider())
    bars = trading._fetch_daily_bars("WAL")
    assert calls == [("WAL", "1d", mg.BARS_REQUESTED)]
    assert mg.assess(bars).status == mg.STATUS_OK


# ---------------------------------------------------------------- today's session must have a bar

NEW_YORK = mg.Session(tz="America/New_York", open_hhmm="09:30")


def ny_ms(year, month, day, hour=0, minute=0):
    return int(datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("America/New_York")).timestamp() * 1000)


def bars_through(year, month, day, **kw):
    """Daily bars stamped at New York midnight, as yfinance stamps them, the last on that date."""
    return mb.calm(end_ms=ny_ms(year, month, day), **kw)


def at(monkeypatch, now_ms):
    monkeypatch.setattr(mg, "_now_ms", lambda: now_ms)


def test_once_the_session_opens_yesterdays_bar_is_stale():
    # Thursday 2026-09-24, 10:00 New York: the provider still ends at Wednesday.
    reading = mg.assess(bars_through(2026, 9, 23), now_ms=ny_ms(2026, 9, 24, 10), session=NEW_YORK)
    assert reading.status == mg.STATUS_STALE and not reading.falling_knife
    assert "no daily bar yet for today's session (2026-09-24" in reading.detail


def test_a_collapse_today_is_not_hidden_by_yesterdays_calm_bars():
    # The case the check exists for: without today's bar the rule would read yesterday's calm tape.
    calm_until_yesterday = bars_through(2026, 9, 23)
    assert mg.assess(calm_until_yesterday, now_ms=ny_ms(2026, 9, 24, 10)).status == mg.STATUS_OK
    assert mg.assess(calm_until_yesterday, now_ms=ny_ms(2026, 9, 24, 10), session=NEW_YORK).status == mg.STATUS_STALE


def test_todays_partial_bar_is_current():
    reading = mg.assess(bars_through(2026, 9, 24), now_ms=ny_ms(2026, 9, 24, 10), session=NEW_YORK)
    assert reading.status == mg.STATUS_OK


@pytest.mark.parametrize(
    "now,last_bar",
    [
        (ny_ms(2026, 9, 24, 9, 29), (2026, 9, 23)),  # Thursday before the open
        (ny_ms(2026, 9, 26, 12), (2026, 9, 25)),  # Saturday
        (ny_ms(2026, 9, 28, 9, 0), (2026, 9, 25)),  # Monday before the open
        (ny_ms(2026, 12, 3, 15), (2026, 12, 3)),  # a winter (EST) session day
    ],
    ids=["before-open", "saturday", "monday-pre-open", "winter"],
)
def test_outside_the_session_the_last_bar_is_current(now, last_bar):
    assert mg.assess(bars_through(*last_bar), now_ms=now, session=NEW_YORK).status == mg.STATUS_OK


def test_an_exchange_holiday_reads_as_stale_after_the_open():
    # Labor Day 2026-09-07: no session, so no bar. Stale is the safe answer - a BUY would fill at
    # the next open, on a price the check has not seen.
    reading = mg.assess(bars_through(2026, 9, 4), now_ms=ny_ms(2026, 9, 7, 11), session=NEW_YORK)
    assert reading.status == mg.STATUS_STALE


def test_a_live_buy_with_no_bar_for_todays_session_is_blocked(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_MODE", False)
    monkeypatch.setattr(settings, "MARKET_GUARD_ON_DATA_ERROR", "")
    monkeypatch.setattr(settings, "MARKET_TIMEZONE", "US/Eastern")
    monkeypatch.setattr(settings, "MARKET_HOURS_START", "09:30")
    at(monkeypatch, ny_ms(2026, 9, 24, 10))
    use_bars(monkeypatch, bars_through(2026, 9, 23))
    payload = json.loads(trading.validate_trade_risk("buy", SYMBOL, 1000.0, 100000.0))
    assert payload["data"]["result"]["allowed"] is False
    assert payload["data"]["market"]["status"] == "stale"
    assert "today's session" in payload["data"]["market"]["detail"]


def test_the_session_follows_the_market_hours_setting(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_MODE", False)
    monkeypatch.setattr(settings, "MARKET_GUARD_ON_DATA_ERROR", "")
    monkeypatch.setattr(settings, "MARKET_HOURS_START", "11:00")
    at(monkeypatch, ny_ms(2026, 9, 24, 10))
    use_bars(monkeypatch, bars_through(2026, 9, 23))
    payload = json.loads(trading.validate_trade_risk("buy", SYMBOL, 1000.0, 100000.0))
    assert payload["data"]["market"]["status"] == "ok"


def test_a_bad_market_timezone_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_MODE", False)
    monkeypatch.setattr(settings, "MARKET_GUARD_ON_DATA_ERROR", "")
    monkeypatch.setattr(settings, "MARKET_TIMEZONE", "Mars/Olympus_Mons")
    payload = json.loads(trading.validate_trade_risk("buy", SYMBOL, 1000.0, 100000.0))
    assert payload["data"]["result"]["allowed"] is False
    assert payload["data"]["market"]["status"] == "unavailable"


# ---------------------------------------------------------------- the on/off switch


@pytest.mark.parametrize(
    "raw,on",
    [("true", True), ("", True), (None, True), ("treu", True), ("1", True), ("yes", True),
     ("false", False), (" FALSE ", False), ("0", False), ("no", False), ("off", False)],
)
def test_only_an_explicit_off_value_disables_the_check(raw, on):
    assert safety_switch_on(raw) is on


# ---------------------------------------------------------------- approval-time recheck


@pytest.fixture
def approvals(monkeypatch, quiet_ledger):
    from fastapi.testclient import TestClient

    import app.api_server as api

    monkeypatch.setattr(settings, "PAPER_MODE", True)
    monkeypatch.setattr(settings, "EXECUTION_APPROVAL_MODE", "approve_each")
    executed = []
    monkeypatch.setattr(
        type(global_container.paper_engine),
        "execute_trade",
        lambda self, **kw: executed.append(kw) or "filled",
    )
    return TestClient(api.app), executed


def propose(side):
    payload = json.loads(trading.place_stock_order(SYMBOL, side, 10.0))  # a market order
    assert payload["data"]["status"] == "pending_approval", payload
    return payload["data"]


def approve(client, proposal):
    return client.post(
        "/api/approve-trade",
        json={"request_id": proposal["request_id"], "confirm_token": proposal["confirm_token"], "approve": True},
    )


def test_an_approved_buy_is_rechecked_against_fresh_bars(monkeypatch, approvals):
    client, executed = approvals
    proposal = propose("buy")  # calm tape: proposed
    use_bars(monkeypatch, mb.collapse(drop=0.30))  # the stock collapses while it waits
    response = approve(client, proposal)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "risk_blocked"
    assert response.json()["detail"]["market"]["falling_knife"] is True
    assert executed == []


def test_an_approved_buy_on_a_calm_tape_executes(approvals):
    client, executed = approvals
    response = approve(client, propose("buy"))
    assert response.status_code == 200 and response.json()["ok"] is True
    assert len(executed) == 1 and executed[0]["side"] == "buy"


def test_an_approved_sell_executes_during_a_collapse(monkeypatch, approvals):
    client, executed = approvals
    proposal = propose("sell")
    use_bars(monkeypatch, mb.collapse(drop=0.30))
    assert approve(client, proposal).status_code == 200
    assert len(executed) == 1 and executed[0]["side"] == "sell"


def test_the_recheck_uses_the_proposals_sentiment_reading(monkeypatch, approvals):
    client, executed = approvals
    guardian = global_container.risk_guardian
    seen = []
    real = guardian.validate_trade

    def spy(*args, **kwargs):
        seen.append(kwargs.get("sentiment_score"))
        return real(*args, **kwargs)

    monkeypatch.setattr(guardian, "validate_trade", spy)
    payload = json.loads(trading.place_stock_order(SYMBOL, "buy", 10.0, sentiment_score=-0.4))
    assert approve(client, payload["data"]).status_code == 200
    assert seen == [-0.4, -0.4]  # at proposal and again at approval
