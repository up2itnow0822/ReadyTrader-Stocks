"""
Regression tests for the cross-repository review of the 2026-09-24 UAT (uat/runs/2026-09-24-01,
checks XR-01..XR-11): defect classes found in ReadyTrader-Crypto, checked here. Each fails on the
code before its fix. Live orders reach a fake brokerage only.
"""

import json
import sqlite3
from pathlib import Path

import market_bars as mb
import pytest
from fastapi.testclient import TestClient

import app.api_server as api
import app.tools.trading as trading
from app.core.config import settings
from app.core.container import global_container
from core.paper import PaperTradingEngine

REPO = Path(__file__).resolve().parents[1]
LAST = mb.calm()[-1][4]  # the conftest quote and last daily close (about 103)
OPERATOR = {"Authorization": "Bearer review-operator-token"}


class Broker:
    def __init__(self, positions=None, equity=100_000.0):
        self.orders, self.positions, self.equity = [], positions or [], equity

    def is_available(self):
        return True

    def get_account_balance(self):
        return {"equity": self.equity, "cash": self.equity}

    def list_positions(self):
        return list(self.positions)

    def place_order(self, **kw):
        self.orders.append(kw)
        return {"id": "fake", **kw}


@pytest.fixture
def paper(monkeypatch, tmp_path):
    engine = PaperTradingEngine(db_path=str(tmp_path / "paper.db"))
    monkeypatch.setattr(global_container, "paper_engine", engine)
    monkeypatch.setattr(settings, "PAPER_MODE", True)
    return engine


@pytest.fixture
def live(monkeypatch):
    broker = Broker()
    monkeypatch.setenv("API_OPERATOR_TOKEN", "review-operator-token")
    for key, value in dict(PAPER_MODE=False, LIVE_TRADING_ENABLED=True, TRADING_HALTED=False, MARKET_GUARD_ON_DATA_ERROR="").items():
        monkeypatch.setattr(settings, key, value)
    monkeypatch.setitem(global_container.brokerages, "alpaca", broker)
    return broker


def _j(out):
    return json.loads(out)


# ------------------------------------------------------------------------------ XR-01


def test_a_live_order_is_valued_at_the_market_not_at_the_price_it_carries(live):
    out = _j(trading.place_stock_order("AAPL", "buy", 1000.0, price=1.0))  # market order, 1000 x ~103
    assert out["error"]["code"] == "risk_blocked" and "Position size too large" in out["error"]["message"]
    assert out["error"]["data"]["reference_price"] == pytest.approx(LAST)
    limit = trading.pre_trade_check("AAPL", "sell", 1000.0, 1.0, order_type="limit")  # marketable: fills at ~103
    assert limit["allowed"] is False and limit["reference_price"] == pytest.approx(LAST)
    assert live.orders == []


def test_without_a_market_price_an_order_that_adds_exposure_is_refused(live, monkeypatch):
    monkeypatch.setattr(trading, "_fetch_daily_bars", lambda s: (_ for _ in ()).throw(RuntimeError("no bars")))
    monkeypatch.setattr(global_container.exchange_provider, "fetch_ticker", lambda s: (_ for _ in ()).throw(RuntimeError("no quote")))
    out = _j(trading.place_stock_order("AAPL", "sell", 1000.0, price=1.0, order_type="limit"))
    assert out["error"]["code"] == "risk_blocked" and "No market price" in out["error"]["message"]
    assert live.orders == []


# ------------------------------------------------------------------------------ XR-02


def test_live_orders_say_which_loss_rules_do_not_run(live):
    assert trading.pre_trade_check("AAPL", "buy", 1.0)["inactive_rules"] == ["daily_loss_limit", "max_drawdown"]


# ------------------------------------------------------------------------------ XR-03 / XR-05


def test_a_deposit_does_not_end_a_drawdown_halt(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "p.db"))
    e.deposit("u", "USD", 10_000.0)
    e.execute_trade("u", "buy", "AAPL", amount=100.0, price=100.0)
    e.execute_trade("u", "sell", "AAPL", amount=100.0, price=88.0)  # -1,200: 12%
    e.deposit("u", "USD", 5_000.0)
    m = e.get_risk_metrics("u")
    assert m["drawdown_pct"] == pytest.approx(0.12) and m["daily_pnl_pct"] == pytest.approx(-0.12)


def test_a_week_old_snapshot_is_not_the_start_of_today(tmp_path, monkeypatch):
    e = PaperTradingEngine(db_path=str(tmp_path / "p.db"))
    e.deposit("u", "USD", 15_000.0)
    e.execute_trade("u", "buy", "AAPL", amount=100.0, price=100.0)
    e.mark_price_usd("AAPL", 91.0)  # -6% of the account over the week
    e._snapshot_equity("u")
    conn = sqlite3.connect(e.db_path)
    conn.execute("UPDATE equity_snapshots SET timestamp='2026-09-17T12:00:00+00:00'")
    conn.commit()
    conn.close()
    monkeypatch.setattr(e, "_now_iso", lambda: "2026-09-24T12:00:00+00:00")
    e.mark_day_open("u")
    assert e.get_risk_metrics("u")["daily_pnl_pct"] == pytest.approx(0.0, abs=1e-12)


# ------------------------------------------------------------------------------ XR-04


def test_the_paper_account_is_marked_to_market_before_the_check(paper, monkeypatch):
    paper.deposit("agent_zero", "USD", 10_000.0)
    paper.execute_trade("agent_zero", "buy", "AAPL", amount=50.0, price=100.0)
    monkeypatch.setattr(global_container.exchange_provider, "fetch_ticker", lambda s: {"symbol": s, "last": 60.0})
    check = trading.pre_trade_check("MSFT", "buy", 1.0)  # AAPL down 40%: the account is 20% below its peak
    assert check["allowed"] is False and "Drawdown" in check["reason"]


# ------------------------------------------------------------------------------ XR-06


def test_a_ticker_never_trades_against_the_paper_cash(paper):
    paper.deposit("agent_zero", "USD", 10_000.0)
    for symbol in ("USD", "usd", "BRK/B"):
        out = _j(trading.place_market_order(symbol, "sell", 5.0))
        assert out["error"]["code"] == "invalid_request", (symbol, out)
    assert paper.get_balances("agent_zero") == {"USD": 10_000.0}


# ------------------------------------------------------------------------------ XR-07


def test_a_market_orders_price_is_ignored_and_a_bad_sentiment_is_refused(paper, monkeypatch):
    paper.deposit("agent_zero", "USD", 10_000.0)
    monkeypatch.setattr(settings, "EXECUTION_APPROVAL_MODE", "approve_each")
    out = _j(trading.place_stock_order("AAPL", "buy", 1.0, price=float("nan")))
    assert out["ok"] is True and out["data"]["order_details"]["price"] == 0.0
    assert TestClient(api.app).get("/api/pending-approvals").status_code == 200
    for score in (float("nan"), float("inf")):
        assert _j(trading.place_stock_order("AAPL", "buy", 1.0, sentiment_score=score))["error"]["code"] == "invalid_request"
        assert _j(trading.validate_trade_risk("buy", "AAPL", 100.0, 10_000.0, score))["error"]["code"] == "invalid_request"


# ------------------------------------------------------------------------------ XR-08


def test_the_docker_build_context_leaves_out_secrets_in_any_folder():
    rules = {line.strip() for line in (REPO / ".dockerignore").read_text().splitlines()}
    assert {"**/.env*", "**/*.pem", "**/*.key", "**/*.db", "**/__pycache__/"} <= rules
    assert "USER readytrader" in (REPO / "Dockerfile").read_text()


# ------------------------------------------------------------------------------ XR-09


def test_api_responses_carry_a_request_id_and_hide_internal_errors(monkeypatch):
    client = TestClient(api.app, raise_server_exceptions=False)
    a, b = client.get("/api/health"), client.get("/api/health")
    assert a.headers["x-request-id"] != b.headers["x-request-id"] and a.headers["x-frame-options"] == "DENY"

    def boom(*args, **kwargs):
        raise RuntimeError("secret internal detail: /home/op/.env line 3")

    monkeypatch.setattr(type(global_container.paper_engine), "get_balances", boom)
    monkeypatch.setattr(settings, "PAPER_MODE", True)
    r = client.get("/api/portfolio")
    assert r.status_code == 500 and r.headers["x-request-id"] and "secret" not in r.text
    assert r.json()["detail"]["code"] == "internal_error"


# ------------------------------------------------------------------------------ XR-10


def test_a_live_order_reaches_the_brokerage_with_the_normalised_symbol(live):
    live.positions = [{"symbol": "BRK.B", "qty": 100.0}]
    out = _j(trading.place_stock_order("brk.b ", "sell", 10.0))
    assert out["ok"] is True, out
    assert live.orders[-1]["symbol"] == "BRK.B"


# ------------------------------------------------------------------------------ XR-11


def test_a_live_proposal_needs_the_operator_token(live, monkeypatch):
    monkeypatch.setattr(settings, "EXECUTION_APPROVAL_MODE", "approve_each")
    proposal = _j(trading.place_stock_order("AAPL", "buy", 1.0))["data"]
    body = {"request_id": proposal["request_id"], "confirm_token": proposal["confirm_token"], "approve": True}
    assert TestClient(api.app).post("/api/approve-trade", json=body).status_code == 401  # the agent's token alone
    monkeypatch.delenv("API_OPERATOR_TOKEN")
    denied = TestClient(api.app).post("/api/approve-trade", json=body)
    assert denied.status_code == 403 and denied.json()["detail"]["code"] == "operator_token_required"
    assert live.orders == []
    monkeypatch.setenv("API_OPERATOR_TOKEN", "review-operator-token")
    assert TestClient(api.app, headers=OPERATOR).post("/api/approve-trade", json=body).status_code == 200
    assert len(live.orders) == 1


# ------------------------------------------------------------------------------ XR-12


def test_the_smithery_listing_offers_only_settings_that_work_there():
    import yaml

    start = yaml.safe_load((REPO / "smithery.yaml").read_text())["startCommand"]
    assert "EXECUTION_APPROVAL_MODE" not in start["configSchema"]["properties"]
    assert "EXECUTION_APPROVAL_MODE: 'auto'" in start["commandFunction"]


# ------------------------------------------------------------------------------ XR-13


def test_an_mcp_client_cannot_send_true_as_a_number(paper):
    import asyncio

    from fastmcp import Client

    from app.main import mcp

    async def calls():
        async with Client(mcp) as client:
            return [
                await client.call_tool(tool, args, raise_on_error=False)
                for tool, args in (
                    ("deposit_paper_funds", {"asset": "USD", "amount": True}),
                    ("place_market_order", {"symbol": "AAPL", "side": "buy", "amount": True}),
                    ("validate_trade_risk", {"side": "buy", "symbol": "AAPL", "amount_usd": True, "portfolio_value": 1e4}),
                )
            ]

    for result in asyncio.run(calls()):  # argument validation used to turn true into 1.0
        assert result.is_error and "not true/false" in result.content[0].text
    assert paper.get_balances("agent_zero") == {}


# ------------------------------------------------------------------------------ XR-14


def _alpaca(monkeypatch, is_open):
    from unittest.mock import MagicMock

    from execution import alpaca_service

    client = MagicMock()
    client.get_clock.return_value = MagicMock(is_open=is_open, next_open="2026-09-25T13:30:00Z")
    client.submit_order.return_value = MagicMock(id="o1", client_order_id="c1", status="accepted", symbol="AAPL", side="buy", qty="10", type="limit")
    # IOC settles at once: the read-back finds it filled
    client.get_order_by_id.return_value = MagicMock(
        id="o1", client_order_id="c1", status="filled", symbol="AAPL", side="buy", qty="10", type="limit", filled_qty="10", filled_avg_price="180"
    )
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_API_SECRET", "secret")
    monkeypatch.setattr(alpaca_service, "TradingClient", lambda *a, **k: client)
    return alpaca_service.AlpacaBrokerage(), client


def test_a_live_alpaca_order_fills_now_or_not_at_all(monkeypatch):
    from alpaca.trading.enums import TimeInForce

    broker, client = _alpaca(monkeypatch, is_open=True)
    broker.place_order("AAPL", "buy", 10, order_type="limit", price=180.0)
    assert client.submit_order.call_args.kwargs["order_data"].time_in_force == TimeInForce.IOC
    out = broker.place_order("AAPL", "buy", 10)  # whole shares: IOC too (a trading halt cancels it)
    assert client.submit_order.call_args.kwargs["order_data"].time_in_force == TimeInForce.IOC
    assert out["status"] == "filled" and out["filled_qty"] == 10.0
    broker.place_order("AAPL", "buy", 0.5)  # Alpaca takes fractional shares only as DAY orders
    assert client.submit_order.call_args.kwargs["order_data"].time_in_force == TimeInForce.DAY


def test_no_alpaca_order_waits_for_the_open(monkeypatch):
    broker, client = _alpaca(monkeypatch, is_open=False)
    for kind, price in (("market", None), ("limit", 180.0)):
        with pytest.raises(RuntimeError, match="market is closed"):
            broker.place_order("AAPL", "buy", 10, order_type=kind, price=price)
    client.get_clock.side_effect = RuntimeError("clock unavailable")
    with pytest.raises(RuntimeError, match="market clock"):
        broker.place_order("AAPL", "buy", 10)
    client.submit_order.assert_not_called()


# ------------------------------------------------------------------------------ AR-01..AR-10
# The independent review of the fixes above.


def _asgi(path, root_path="", host=b"127.0.0.1:8000", headers=()):
    import asyncio

    sent = []
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
        "path": path, "raw_path": path.encode(), "root_path": root_path, "query_string": b"",
        "headers": [(b"host", host), *headers], "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 8000),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(api.app(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    return start["status"], {k.decode(): v.decode() for k, v in start["headers"]}


def test_the_operator_token_cannot_be_steered_past(monkeypatch):
    monkeypatch.setenv("API_OPERATOR_TOKEN", "review-operator-token")
    for host in (b"127.0.0.1:8000", b"127.0.0.1:8000#", b"127.0.0.1:8000?", b"127.0.0.1:8000/x"):
        assert _asgi("/api/portfolio", host=host)[0] == 401, host
    assert _asgi("/rt/api/pending-approvals", root_path="/rt")[0] == 401
    assert _asgi("/rt/api/health", root_path="/rt")[0] == 200


def test_every_answer_carries_the_cors_headers(monkeypatch):
    monkeypatch.setenv("API_OPERATOR_TOKEN", "review-operator-token")
    status, headers = _asgi("/api/portfolio", headers=[(b"origin", b"http://localhost:3000")])
    assert status == 401 and headers.get("access-control-allow-origin") == "http://localhost:3000"


class _Unconfigured:
    def is_available(self):
        return False


def test_the_operator_switches_answer_first_and_are_audited(monkeypatch):
    from unittest.mock import MagicMock

    events = MagicMock()
    monkeypatch.setattr(trading.global_compliance_ledger, "record_event", events)
    monkeypatch.setattr(settings, "PAPER_MODE", False)
    monkeypatch.setitem(global_container.brokerages, "alpaca", _Unconfigured())
    for enabled, halted, code in ((False, False, "live_trading_disabled"), (True, True, "trading_halted"), (True, False, "brokerage_not_configured")):
        monkeypatch.setattr(settings, "LIVE_TRADING_ENABLED", enabled)
        monkeypatch.setattr(settings, "TRADING_HALTED", halted)
        assert _j(trading.place_stock_order("AAPL", "buy", 1.0))["error"]["code"] == code
    assert [c.args[0] for c in events.call_args_list] == ["trade_start"] * 3


def test_an_approval_while_halted_or_closed_keeps_the_proposal(live, monkeypatch):
    monkeypatch.setattr(settings, "EXECUTION_APPROVAL_MODE", "approve_each")
    proposal = _j(trading.place_stock_order("AAPL", "buy", 1.0))["data"]
    body = {"request_id": proposal["request_id"], "confirm_token": proposal["confirm_token"], "approve": True}
    client = TestClient(api.app, headers=OPERATOR)
    monkeypatch.setattr(settings, "TRADING_HALTED", True)
    r = client.post("/api/approve-trade", json=body)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "trading_halted"
    monkeypatch.setattr(settings, "TRADING_HALTED", False)
    live.market_closed_reason = lambda: "Alpaca order not sent: the market is closed (next open 09:30)."
    r = client.post("/api/approve-trade", json=body)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "market_closed"
    live.market_closed_reason = lambda: None
    assert client.post("/api/approve-trade", json=body).status_code == 200  # still pending until now
    assert len(live.orders) == 1


def test_a_closed_market_refuses_before_anything_is_proposed(live, monkeypatch):
    monkeypatch.setattr(settings, "EXECUTION_APPROVAL_MODE", "approve_each")
    live.market_closed_reason = lambda: "Alpaca order not sent: the market is closed (next open 09:30)."
    before = len(global_container.execution_store.list_pending()["pending"])
    assert _j(trading.place_stock_order("AAPL", "buy", 1.0))["error"]["code"] == "market_closed"
    assert len(global_container.execution_store.list_pending()["pending"]) == before and live.orders == []


def test_alpaca_refuses_a_fractional_limit_and_reports_an_unfilled_ioc(monkeypatch):
    from unittest.mock import MagicMock

    broker, client = _alpaca(monkeypatch, is_open=True)
    with pytest.raises(RuntimeError, match="whole shares"):
        broker.place_order("AAPL", "buy", 0.5, order_type="limit", price=180.0)
    client.get_order_by_id.return_value = MagicMock(id="o1", status="canceled", filled_qty="0", filled_avg_price=None)
    with pytest.raises(RuntimeError, match="did not fill"):
        broker.place_order("AAPL", "buy", 10, order_type="limit", price=150.0)


def test_every_numeric_tool_parameter_refuses_true(paper):
    import asyncio

    from fastmcp import Client

    from app.main import mcp

    insight = {"symbol": "AAPL", "agent_id": "a", "signal": "bullish", "reasoning": "r"}

    async def calls():
        async with Client(mcp) as client:
            return [
                await client.call_tool(tool, args, raise_on_error=False)
                for tool, args in (
                    ("fetch_ohlcv", {"symbol": "AAPL", "limit": True}),
                    ("post_market_insight", {**insight, "confidence": True}),
                    ("post_market_insight", {**insight, "confidence": 0.5, "ttl_seconds": True}),
                )
            ]

    for result in asyncio.run(calls()):
        assert result.is_error and "not true/false" in result.content[0].text


def test_the_runbook_says_how_to_upgrade_a_volume():
    runbook = (REPO / "RUNBOOK.md").read_text()
    assert "--entrypoint chown readytrader-stocks -R 10001:10001 /app/data" in runbook
    assert "a BUY would fill at the\nnext open" not in (REPO / "docs/FALLING_KNIFE.md").read_text()
