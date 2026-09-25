"""
Market data tools and the order path as a client uses them: prices, bar timestamps, how an order
is valued for the size rule, how a paper market order fills, and the switches every live order
must pass. Live orders here reach a fake brokerage only.
"""

import json
from unittest.mock import MagicMock

import market_bars as mb
import pandas as pd
import pytest

import app.tools.market as market
import app.tools.trading as trading
from app.core.config import settings
from app.core.container import global_container

EQUITY = 100_000.0


OPERATOR_TOKEN = "unit-test-operator-token"
OPERATOR_HEADERS = {"Authorization": f"Bearer {OPERATOR_TOKEN}"}


@pytest.fixture(autouse=True)
def steady_paper_metrics(monkeypatch):
    monkeypatch.setattr(
        type(global_container.paper_engine),
        "get_risk_metrics",
        lambda self, account: {"daily_pnl_pct": 0.0, "drawdown_pct": 0.0},
    )
    monkeypatch.setattr(type(global_container.paper_engine), "get_portfolio_value_usd", lambda self, account: EQUITY)
    monkeypatch.setattr(trading.global_compliance_ledger, "record_event", MagicMock())


class FakeProvider:
    def __init__(self, last=None, exc=None):
        self.last, self.exc = last, exc

    def fetch_ticker(self, symbol):
        if self.exc:
            raise self.exc
        return {"symbol": symbol, "last": self.last, "close": self.last}


class FakeBroker:
    def __init__(self, available=True, equity=EQUITY):
        self.available, self.orders, self.equity = available, [], equity

    def is_available(self):
        return self.available

    def get_account_balance(self):
        return {"equity": self.equity, "cash": self.equity}

    def place_order(self, **kw):
        self.orders.append(kw)
        return {"id": "fake-1", **kw}


# ---------------------------------------------------------------- market data tools


def test_get_stock_price_returns_the_latest_quote(monkeypatch):
    monkeypatch.setattr(global_container, "exchange_provider", FakeProvider(last=187.5))
    payload = json.loads(market.get_stock_price("AAPL"))
    assert payload["ok"] is True and payload["data"]["last"] == 187.5


def test_get_multiple_prices_reports_each_symbol(monkeypatch):
    monkeypatch.setattr(global_container, "exchange_provider", FakeProvider(last=10.0))
    payload = json.loads(market.get_multiple_prices(["AAPL", "MSFT"]))
    assert {k: v["last"] for k, v in payload["data"]["prices"].items()} == {"AAPL": 10.0, "MSFT": 10.0}


def test_fetch_ohlcv_keeps_each_bars_timestamp(monkeypatch):
    frame = pd.DataFrame(
        [[1790136000000, 1, 2, 0.5, 1.5, 10], [1790222400000, 1.5, 2, 1, 1.8, 12]],
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms")
    engine = MagicMock()
    engine.fetch_ohlcv.return_value = frame
    monkeypatch.setattr(global_container, "backtest_engine", engine)
    history = json.loads(market.fetch_ohlcv("AAPL", "1d", 2))["data"]["history"]
    assert [bar["timestamp"] for bar in history] == ["2026-09-23T04:00:00Z", "2026-09-24T04:00:00Z"]


# ---------------------------------------------------------------- valuing an order


def test_a_market_order_is_valued_at_its_price_for_the_size_rule(monkeypatch):
    # 60 shares at ~100 is ~6% of a 100k portfolio: over the 5% cap. Valued at 1.0 a share (as
    # before) it was 60 dollars and passed.
    payload = json.loads(trading.place_market_order("AAPL", "buy", 60.0))
    assert payload["error"]["code"] == "risk_blocked"
    assert "Position size too large" in payload["error"]["message"]


def test_a_paper_market_order_fills_at_the_reference_price(monkeypatch):
    fills = []
    monkeypatch.setattr(
        type(global_container.paper_engine), "execute_trade", lambda self, **kw: fills.append(kw) or "filled"
    )
    payload = json.loads(trading.place_market_order("AAPL", "buy", 10.0))
    assert payload["ok"] is True
    assert fills[0]["price"] == pytest.approx(mb.calm()[-1][4])


def test_a_buy_that_cannot_be_priced_fails_closed(monkeypatch):
    def boom(symbol):
        raise RuntimeError("no bars")

    monkeypatch.setattr(trading, "_fetch_daily_bars", boom)
    monkeypatch.setattr(global_container, "exchange_provider", FakeProvider(exc=RuntimeError("no quote")))
    payload = json.loads(trading.place_market_order("AAPL", "buy", 1.0))
    assert payload["error"]["code"] == "risk_blocked"
    assert "No market price for AAPL" in payload["error"]["message"]


def test_a_paper_execution_error_is_a_json_error_not_an_exception(monkeypatch):
    def boom(self, **kw):
        raise ValueError("engine down")

    monkeypatch.setattr(type(global_container.paper_engine), "execute_trade", boom)
    payload = json.loads(trading.place_market_order("AAPL", "buy", 1.0))
    assert payload["error"]["code"] == "execution_error"


# ---------------------------------------------------------------- live orders (fake brokerage)


@pytest.fixture
def live(monkeypatch):
    broker = FakeBroker()
    # Live proposals are approved only with the operator token (UAT XR-11).
    monkeypatch.setenv("API_OPERATOR_TOKEN", OPERATOR_TOKEN)
    monkeypatch.setattr(settings, "PAPER_MODE", False)
    monkeypatch.setattr(settings, "MARKET_GUARD_ON_DATA_ERROR", "")
    monkeypatch.setattr(settings, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(settings, "TRADING_HALTED", False)
    monkeypatch.setitem(global_container.brokerages, "alpaca", broker)
    return broker


def test_a_live_order_needs_live_trading_enabled(monkeypatch, live):
    monkeypatch.setattr(settings, "LIVE_TRADING_ENABLED", False)
    payload = json.loads(trading.place_stock_order("AAPL", "buy", 1.0, price=100.0))
    assert payload["error"]["code"] == "live_trading_disabled"
    assert live.orders == []


def test_the_kill_switch_halts_live_orders(monkeypatch, live):
    monkeypatch.setattr(settings, "TRADING_HALTED", True)
    payload = json.loads(trading.place_stock_order("AAPL", "sell", 1.0, price=100.0))
    assert payload["error"]["code"] == "trading_halted"
    assert live.orders == []


def test_an_enabled_live_order_passes_policy_and_reaches_the_brokerage(live):
    payload = json.loads(trading.place_stock_order("AAPL", "buy", 1.0, price=100.0, order_type="limit"))
    assert payload["ok"] is True, payload
    assert live.orders == [{"symbol": "AAPL", "side": "buy", "qty": 1.0, "order_type": "limit", "price": 100.0}]


def test_a_live_order_without_brokerage_keys_is_refused(monkeypatch, live):
    broker = FakeBroker(available=False)
    monkeypatch.setitem(global_container.brokerages, "alpaca", broker)
    for side in ("buy", "sell"):
        payload = json.loads(trading.place_stock_order("AAPL", side, 1.0, price=100.0))
        assert payload["error"]["code"] == "brokerage_not_configured"
    assert broker.orders == []


def test_a_live_order_is_sized_against_the_brokerage_account(monkeypatch, live):
    monkeypatch.setitem(global_container.brokerages, "alpaca", FakeBroker(equity=1_000.0))
    payload = json.loads(trading.place_stock_order("AAPL", "buy", 1.0, price=100.0))  # 10% of 1,000
    assert payload["error"]["code"] == "risk_blocked" and "Position size too large" in payload["error"]["message"]


def test_a_paper_order_is_sized_against_the_paper_account(monkeypatch):
    monkeypatch.setattr(type(global_container.paper_engine), "get_portfolio_value_usd", lambda self, account: 1_000.0)
    payload = json.loads(trading.place_market_order("AAPL", "buy", 1.0))  # ~100 of 1,000
    assert payload["error"]["code"] == "risk_blocked" and "Position size too large" in payload["error"]["message"]


def test_a_paper_limit_below_the_market_does_not_fill(monkeypatch):
    fills = []
    monkeypatch.setattr(type(global_container.paper_engine), "execute_trade", lambda self, **kw: fills.append(kw) or "ok")
    payload = json.loads(trading.place_limit_order("AAPL", "buy", 1.0, 50.0))  # market ~100
    assert payload["error"]["code"] == "limit_not_marketable" and fills == []


def test_a_marketable_paper_limit_fills_at_the_market(monkeypatch):
    fills = []
    monkeypatch.setattr(type(global_container.paper_engine), "execute_trade", lambda self, **kw: fills.append(kw) or "ok")
    assert json.loads(trading.place_limit_order("AAPL", "buy", 1.0, 150.0))["ok"] is True
    assert fills[0]["price"] == pytest.approx(mb.calm()[-1][4])


def test_a_paper_order_without_the_funds_is_an_error(monkeypatch):
    monkeypatch.setattr(type(global_container.paper_engine), "execute_trade", lambda self, **kw: "Insufficient fund. Have 0 AAPL, need 5")
    payload = json.loads(trading.place_market_order("AAPL", "sell", 5.0))
    assert payload["ok"] is False and payload["error"]["code"] == "insufficient_funds"


def test_an_approval_in_live_mode_needs_live_trading_enabled(monkeypatch, live):
    from fastapi.testclient import TestClient

    import app.api_server as api

    monkeypatch.setattr(settings, "EXECUTION_APPROVAL_MODE", "approve_each")
    proposal = json.loads(trading.place_stock_order("AAPL", "buy", 1.0, price=100.0))["data"]
    monkeypatch.setattr(settings, "LIVE_TRADING_ENABLED", False)
    response = TestClient(api.app, headers=OPERATOR_HEADERS).post(
        "/api/approve-trade",
        json={"request_id": proposal["request_id"], "confirm_token": proposal["confirm_token"], "approve": True},
    )
    assert response.status_code == 409 and response.json()["detail"]["code"] == "live_trading_disabled"
    assert live.orders == []


@pytest.mark.parametrize(
    "env,order,code,data_key",
    [
        ({"MAX_ORDER_AMOUNT": "1"}, ("AAPL", "sell", 5.0), "order_amount_too_large", "max_order_amount"),
        ({"ALLOW_TICKERS": "AAPL"}, ("MSFT", "sell", 1.0), "ticker_not_allowed", "allow_tickers"),
        ({"ALLOW_BROKERAGES": "tradier"}, ("AAPL", "sell", 1.0), "brokerage_not_allowed", "allow_brokerages"),
    ],
)
def test_a_live_policy_refusal_names_the_rule(monkeypatch, live, env, order, code, data_key):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    payload = json.loads(trading.place_stock_order(*order, price=100.0))
    assert payload["error"]["code"] == code, payload
    assert data_key in payload["error"]["data"] and payload["error"]["message"]
    assert live.orders == []


@pytest.mark.parametrize("limit", ["1,000", "$500", "1O", "nan", "inf"])
def test_an_unreadable_order_limit_refuses_live_orders(monkeypatch, live, limit):
    monkeypatch.setenv("MAX_ORDER_AMOUNT", limit)
    payload = json.loads(trading.place_stock_order("AAPL", "sell", 20.0, price=100.0))
    assert payload["error"]["code"] == "invalid_policy_config", payload
    assert live.orders == []


def test_an_empty_order_limit_means_no_limit(monkeypatch, live):
    monkeypatch.setenv("MAX_ORDER_AMOUNT", "")
    assert json.loads(trading.place_stock_order("AAPL", "sell", 5.0, price=100.0))["ok"] is True


def test_a_live_proposal_that_breaks_the_policy_is_refused_before_approval(monkeypatch, live):
    monkeypatch.setattr(settings, "EXECUTION_APPROVAL_MODE", "approve_each")
    monkeypatch.setenv("ALLOW_TICKERS", "AAPL")
    before = len(global_container.execution_store.list_pending()["pending"])
    payload = json.loads(trading.place_stock_order("MSFT", "sell", 1.0, price=100.0))
    assert payload["error"]["code"] == "ticker_not_allowed"
    assert len(global_container.execution_store.list_pending()["pending"]) == before


def test_an_approved_live_proposal_still_passes_the_policy(monkeypatch, live):
    """The policy can change while a proposal waits; the approval re-checks it."""
    from fastapi.testclient import TestClient

    import app.api_server as api

    monkeypatch.setattr(settings, "EXECUTION_APPROVAL_MODE", "approve_each")
    proposal = json.loads(trading.place_stock_order("AAPL", "sell", 40.0, price=100.0))["data"]
    monkeypatch.setenv("MAX_ORDER_AMOUNT", "10")
    response = TestClient(api.app, headers=OPERATOR_HEADERS).post(
        "/api/approve-trade",
        json={"request_id": proposal["request_id"], "confirm_token": proposal["confirm_token"], "approve": True},
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "order_amount_too_large"
    assert live.orders == []


def test_an_approval_without_brokerage_keys_is_a_coded_error(monkeypatch, live):
    from fastapi.testclient import TestClient

    import app.api_server as api

    monkeypatch.setattr(settings, "EXECUTION_APPROVAL_MODE", "approve_each")
    proposal = json.loads(trading.place_stock_order("AAPL", "sell", 1.0, price=100.0))["data"]
    monkeypatch.setitem(global_container.brokerages, "alpaca", FakeBroker(available=False))
    response = TestClient(api.app, headers=OPERATOR_HEADERS).post(
        "/api/approve-trade",
        json={"request_id": proposal["request_id"], "confirm_token": proposal["confirm_token"], "approve": True},
    )
    # Without keys the account cannot be read, so the re-check refuses the order before execution.
    assert response.status_code == 409 and response.json()["detail"]["code"] == "risk_blocked"
    assert "equity" in response.json()["detail"]["reason"]


# ---------------------------------------------------------------- malformed requests


@pytest.mark.parametrize(
    "side,amount_usd,portfolio_value,fragment",
    [("hold", 100.0, 1e5, "side must be"), ("buy", -5.0, 1e5, "amount_usd"), ("buy", float("nan"), 1e5, "amount_usd"), ("sell", 100.0, 0.0, "portfolio_value")],
)
def test_a_malformed_risk_check_is_refused(side, amount_usd, portfolio_value, fragment):
    payload = json.loads(trading.validate_trade_risk(side, "AAPL", amount_usd, portfolio_value))
    assert payload["error"]["code"] == "invalid_request" and fragment in payload["error"]["message"]


@pytest.mark.parametrize("side,amount", [("short", 1.0), ("buy", 0.0), ("sell", -3.0)])
def test_a_malformed_order_is_refused_before_anything_runs(monkeypatch, side, amount):
    ledger = MagicMock()
    monkeypatch.setattr(trading.global_compliance_ledger, "record_event", ledger)
    payload = json.loads(trading.place_stock_order("AAPL", side, amount, price=10.0))
    assert payload["error"]["code"] == "invalid_request"
    ledger.assert_not_called()


@pytest.mark.parametrize(
    "order_type,price,fragment",
    [("stop", 0.0, "order_type must be"), ("limit", 0.0, "positive price"), ("limit", -5.0, "positive price")],
)
def test_an_order_type_the_server_cannot_honour_is_refused(monkeypatch, order_type, price, fragment):
    fills = []
    monkeypatch.setattr(type(global_container.paper_engine), "execute_trade", lambda self, **kw: fills.append(kw) or "ok")
    payload = json.loads(trading.place_stock_order("AAPL", "buy", 1.0, price=price, order_type=order_type))
    assert payload["error"]["code"] == "invalid_request" and fragment in payload["error"]["message"]
    assert fills == []


@pytest.mark.parametrize("amount", [-50_000.0, 0.0, float("nan"), float("inf")])
def test_a_paper_deposit_must_be_positive(monkeypatch, amount):
    deposits = []
    monkeypatch.setattr(type(global_container.paper_engine), "deposit", lambda self, *a, **k: deposits.append(a) or "ok")
    payload = json.loads(trading.deposit_paper_funds("USD", amount))
    assert payload["error"]["code"] == "invalid_request" and deposits == []


def test_an_upper_case_side_is_accepted(monkeypatch):
    fills = []
    monkeypatch.setattr(type(global_container.paper_engine), "execute_trade", lambda self, **kw: fills.append(kw) or "ok")
    assert json.loads(trading.place_market_order("AAPL", "BUY", 1.0))["ok"] is True
    assert fills[0]["side"] == "buy"


# ---------------------------------------------------------------- research tools


@pytest.mark.parametrize(
    "outcome",
    [{"error": "Strategy Compilation Error: Importing 'os' is forbidden."}, {"error": "Runtime error in strategy at row 13"}],
)
def test_a_failed_backtest_is_an_error_not_a_result(monkeypatch, outcome):
    import app.tools.research as research

    monkeypatch.setattr(global_container.backtest_engine, "run", lambda *a, **k: outcome)
    payload = json.loads(research.run_backtest_simulation("x = 1", "AAPL", "1d"))
    assert payload["ok"] is False and payload["error"]["code"] == "backtest_error"
    assert payload["error"]["message"] == outcome["error"]


def test_a_backtest_that_runs_returns_its_result(monkeypatch):
    import app.tools.research as research

    monkeypatch.setattr(global_container.backtest_engine, "run", lambda *a, **k: {"pnl_percent": 1.0, "total_trades": 2})
    payload = json.loads(research.run_backtest_simulation("def on_candle(c, r, s): return 'hold'", "AAPL", "1d"))
    assert payload == {"ok": True, "data": {"result": {"pnl_percent": 1.0, "total_trades": 2}}}


def test_the_stress_test_tool_runs():
    import app.tools.research as research

    strategy = "def on_candle(close, rsi, state):\n    return 'buy' if rsi < 30 else ('sell' if rsi > 70 else 'hold')\n"
    payload = json.loads(research.run_synthetic_stress_test(strategy, '{"scenarios": 2, "length": 120}'))
    assert payload["ok"] is True, payload
    assert payload["data"]["result"]["summary"]["scenarios"] == 2


# ---------------------------------------------------------------- shared insights


@pytest.mark.parametrize(
    "signal,confidence,ttl", [("sideways-ish", 0.5, 60), ("bullish", 7.5, 60), ("bearish", -0.1, 60), ("neutral", 0.5, 0)]
)
def test_an_insight_outside_the_documented_fields_is_refused(signal, confidence, ttl):
    import app.tools.research as research

    payload = json.loads(research.post_market_insight("AAPL", "a", signal, confidence, "x", ttl))
    assert payload["error"]["code"] == "invalid_request"


# ---------------------------------------------------------------- news tools


def test_get_market_news_passes_the_ticker(monkeypatch):
    import app.tools.intelligence as intelligence

    calls = []
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")

    class Response:
        def json(self):
            return {"feed": [{"title": "AAPL beats", "source": "Wire"}]}

    monkeypatch.setattr("intelligence.core.requests.get", lambda url, params, timeout: calls.append(params) or Response())
    payload = json.loads(intelligence.get_market_news("aapl"))
    assert "AAPL beats" in payload["data"]["news"]
    assert calls[0]["tickers"] == "AAPL"


def test_fetch_rss_news_reads_the_built_in_feeds(monkeypatch):
    import app.tools.intelligence as intelligence

    class Feed:
        entries = [type("E", (), {"title": "Apple AAPL rallies", "summary": ""})(), type("E", (), {"title": "Oil slips", "summary": ""})()]

    monkeypatch.setattr("intelligence.core.feedparser.parse", lambda url: Feed())
    news = json.loads(intelligence.fetch_rss_news("AAPL"))["data"]["news"]
    assert "Apple AAPL rallies" in news and "Oil slips" not in news


def test_approval_errors_say_which_problem_it_is(monkeypatch):
    from fastapi.testclient import TestClient

    import app.api_server as api

    client = TestClient(api.app, headers=OPERATOR_HEADERS)

    def approve(request_id, token):
        return client.post("/api/approve-trade", json={"request_id": request_id, "confirm_token": token, "approve": True})

    assert approve("nope", "x").status_code == 404
    proposal = global_container.execution_store.create(kind="stock_order", payload={"symbol": "AAPL"})
    assert approve(proposal.request_id, "guess").status_code == 403
    global_container.execution_store.cancel(proposal.request_id, proposal.confirm_token)
    assert approve(proposal.request_id, proposal.confirm_token).status_code == 409  # cancelled


# ---------------------------------------------------------------- exits are not new exposure


def test_a_position_bigger_than_one_trade_can_be_sold_in_one_order(monkeypatch):
    fills = []
    monkeypatch.setattr(type(global_container.paper_engine), "get_balance", lambda self, user, asset: 300.0 if asset == "AAPL" else 0.0)
    monkeypatch.setattr(type(global_container.paper_engine), "execute_trade", lambda self, **kw: fills.append(kw) or "ok")
    # 300 shares at ~100 is ~30% of the account: an exit, so the size rule does not apply.
    check = trading.pre_trade_check("AAPL", "sell", 300.0)
    assert check["allowed"] and check["exposure_added_units"] == 0
    assert not trading.pre_trade_check("AAPL", "buy", 300.0)["allowed"]  # the same size as a BUY is refused


def test_after_the_drawdown_limit_selling_out_is_allowed(monkeypatch):
    monkeypatch.setattr(type(global_container.paper_engine), "get_risk_metrics", lambda self, account: {"daily_pnl_pct": -0.08, "drawdown_pct": 0.15})
    monkeypatch.setattr(type(global_container.paper_engine), "get_balance", lambda self, user, asset: 10.0 if asset == "AAPL" else 0.0)
    assert trading.pre_trade_check("AAPL", "sell", 10.0)["allowed"]
    buy = trading.pre_trade_check("AAPL", "buy", 1.0)
    assert not buy["allowed"] and "add exposure" in buy["reason"]


def test_a_live_sell_beyond_the_position_is_sized_as_a_short(monkeypatch, live):
    class Held(FakeBroker):
        def list_positions(self):
            return [{"symbol": "AAPL", "qty": 5.0}]

    monkeypatch.setitem(global_container.brokerages, "alpaca", Held(equity=1_000.0))
    assert json.loads(trading.place_stock_order("AAPL", "sell", 5.0, price=100.0))["ok"]  # an exit: 50% of the account
    payload = json.loads(trading.place_stock_order("AAPL", "sell", 20.0, price=100.0))  # 15 shares short: 150%
    assert payload["error"]["code"] == "risk_blocked" and payload["error"]["data"]["exposure_added_units"] == 15.0


def test_a_paper_proposal_never_executes_live(monkeypatch):
    from fastapi.testclient import TestClient

    import app.api_server as api

    monkeypatch.setattr(settings, "EXECUTION_APPROVAL_MODE", "approve_each")
    proposal = json.loads(trading.place_market_order("AAPL", "buy", 1.0))["data"]
    broker = FakeBroker()
    monkeypatch.setenv("API_OPERATOR_TOKEN", OPERATOR_TOKEN)
    monkeypatch.setattr(settings, "PAPER_MODE", False)
    monkeypatch.setattr(settings, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(settings, "TRADING_HALTED", False)
    monkeypatch.setitem(global_container.brokerages, "alpaca", broker)
    response = TestClient(api.app, headers=OPERATOR_HEADERS).post(
        "/api/approve-trade", json={"request_id": proposal["request_id"], "confirm_token": proposal["confirm_token"], "approve": True}
    )
    assert response.status_code == 409 and response.json()["detail"]["code"] == "mode_mismatch"
    assert broker.orders == []


def test_the_pending_list_shows_the_order_but_never_the_token(monkeypatch):
    from fastapi.testclient import TestClient

    import app.api_server as api

    monkeypatch.setattr(settings, "EXECUTION_APPROVAL_MODE", "approve_each")
    proposal = json.loads(trading.place_market_order("AAPL", "buy", 1.0))["data"]
    pending = TestClient(api.app, headers=OPERATOR_HEADERS).get("/api/pending-approvals").json()["pending"]
    mine = [p for p in pending if p["request_id"] == proposal["request_id"]][0]
    assert mine["order"]["symbol"] == "AAPL" and mine["order"]["side"] == "buy" and mine["order"]["paper_mode"] is True
    assert proposal["confirm_token"] not in json.dumps(pending)


def test_a_web_page_elsewhere_cannot_open_the_websocket():
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    import app.api_server as api

    client = TestClient(api.app, headers=OPERATOR_HEADERS)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={"Origin": "https://evil.example"}):
            pass
    with client.websocket_connect("/ws", headers={"Origin": "http://localhost:3000"}):
        pass


def test_a_large_trade_verdict_does_not_promise_a_confirmation():
    result = global_container.risk_guardian.validate_trade("buy", "AAPL", 8_000.0, 200_000.0)
    assert result["allowed"] and "requires manual confirmation" not in result["reason"] and "approve_each" in result["reason"]
