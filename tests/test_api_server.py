"""The approval/dashboard API as an operator runs it: start-up, the portfolio view, and approvals
created by the MCP server (a separate process) and approved through the API."""


import pytest
from fastapi.testclient import TestClient

from app.core.container import global_container
from execution.store import ExecutionStore


def test_the_portfolio_view_returns_balances_and_equity(monkeypatch, tmp_path):
    import app.api_server as api
    from core.paper import PaperTradingEngine

    engine = PaperTradingEngine(db_path=str(tmp_path / "paper.db"))
    engine.deposit("agent_zero", "USD", 2_500.0)
    monkeypatch.setattr(global_container, "paper_engine", engine)
    response = TestClient(api.app).get("/api/portfolio")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["balances"] == {"USD": 2500.0}
    assert body["metrics"]["equity"] == pytest.approx(2500.0)


def _two_processes(monkeypatch, tmp_path, session_id):
    monkeypatch.setenv("EXECUTION_DB_PATH", str(tmp_path / "execution.db"))
    if session_id:
        monkeypatch.setenv("EXECUTION_SESSION_ID", session_id)
    else:
        monkeypatch.delenv("EXECUTION_SESSION_ID", raising=False)
    return ExecutionStore(), ExecutionStore()  # the MCP server's store, the API server's store


def test_a_shared_session_id_lets_the_api_see_and_confirm_the_servers_proposals(monkeypatch, tmp_path):
    mcp_store, api_store = _two_processes(monkeypatch, tmp_path, "desk-1")
    proposal = mcp_store.create(kind="stock_order", payload={"symbol": "AAPL", "side": "buy", "amount": 1})
    assert [p["request_id"] for p in api_store.list_pending()["pending"]] == [proposal.request_id]
    confirmed = api_store.confirm(proposal.request_id, proposal.confirm_token)
    assert confirmed.payload["symbol"] == "AAPL"


def test_without_a_shared_session_id_proposals_stay_private_to_their_process(monkeypatch, tmp_path):
    mcp_store, api_store = _two_processes(monkeypatch, tmp_path, None)
    proposal = mcp_store.create(kind="stock_order", payload={"symbol": "AAPL"})
    assert api_store.list_pending()["pending"] == []
    with pytest.raises(ValueError):
        api_store.confirm(proposal.request_id, proposal.confirm_token)


def test_a_shared_proposal_still_needs_its_confirm_token(monkeypatch, tmp_path):
    mcp_store, api_store = _two_processes(monkeypatch, tmp_path, "desk-1")
    proposal = mcp_store.create(kind="stock_order", payload={"symbol": "AAPL"})
    with pytest.raises(ValueError):
        api_store.confirm(proposal.request_id, "not-the-token")


def test_a_foreign_web_page_gets_no_cors_grant():
    import app.api_server as api

    client = TestClient(api.app)
    foreign = client.get("/api/pending-approvals", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in foreign.headers
    preflight = client.options(
        "/api/approve-trade",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in preflight.headers


def test_the_dashboard_origin_is_allowed():
    import app.api_server as api

    response = TestClient(api.app).get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cancelling_a_proposal_needs_its_confirm_token(monkeypatch, tmp_path):
    import app.api_server as api

    monkeypatch.setenv("EXECUTION_DB_PATH", str(tmp_path / "execution.db"))
    store = ExecutionStore()
    monkeypatch.setattr(global_container, "execution_store", store)
    proposal = store.create(kind="stock_order", payload={"symbol": "AAPL", "side": "buy", "amount": 1})
    client = TestClient(api.app)
    guessed = client.post(
        "/api/approve-trade", json={"request_id": proposal.request_id, "confirm_token": "guess", "approve": False}
    )
    assert guessed.json() == {"ok": False}
    assert [p["request_id"] for p in store.list_pending()["pending"]] == [proposal.request_id]
    real = client.post(
        "/api/approve-trade",
        json={"request_id": proposal.request_id, "confirm_token": proposal.confirm_token, "approve": False},
    )
    assert real.json() == {"ok": True} and store.list_pending()["pending"] == []
