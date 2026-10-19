import json
import pytest
from fastapi.testclient import TestClient
from app.main import app, risk_manager, executor, store, market_data
from app.models import Signal, RiskDecision, OrderRequest, OrderResult

@pytest.fixture(autouse=True)
def reset_state():
    # Ensure clean state before each test
    risk_manager.resume()
    executor.flatten_all()
    if hasattr(store, "clear_all"):
        store.clear_all()
    yield
    risk_manager.resume()
    executor.flatten_all()


def test_app_health_and_root():
    client = TestClient(app)

    resp_root = client.get("/")
    assert resp_root.status_code == 200
    assert resp_root.json()["status"] == "running"

    resp_health = client.get("/health")
    assert resp_health.status_code == 200
    assert resp_health.json() == {"status": "ok"}


def test_api_status_and_pnl_dual_prefix():
    client = TestClient(app)

    # Test /api/status and /status both return valid responses
    resp1 = client.get("/api/status")
    resp2 = client.get("/status")
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["status"] == "running"
    assert resp2.json()["status"] == "running"
    assert "equity" in resp1.json()
    assert "daily_pnl" in resp1.json()
    assert "is_halted" in resp1.json()
    assert resp1.json()["is_halted"] is False

    # Test /api/pnl and /pnl
    resp_pnl1 = client.get("/api/pnl")
    resp_pnl2 = client.get("/pnl")
    assert resp_pnl1.status_code == 200
    assert resp_pnl2.status_code == 200
    assert "daily_pnl" in resp_pnl1.json()
    assert "unrealized_pnl" in resp_pnl1.json()
    assert "equity" in resp_pnl1.json()


def test_api_trades_signals_equity_persistence():
    client = TestClient(app)

    sig = Signal(
        symbol="BTCUSD",
        side="buy",
        entry_price=64000.0,
        stop_loss=63000.0,
        take_profit=66000.0,
        reason="Test route signal",
        ts=1700000000,
    )
    dec = RiskDecision(approved=True, size=0.05, reason="Approved by risk")
    store.save_signal(sig, dec)

    order = OrderRequest(
        symbol="BTCUSD",
        side="buy",
        size=0.05,
        entry_price=64000.0,
        stop_loss=63000.0,
        take_profit=66000.0,
        client_order_id="client-test-api-001",
    )
    result = OrderResult(ok=True, order_id="delta-order-001", status="FILLED")
    store.save_trade(order, result)
    store.save_equity(1700000000, 10000.0)

    # Test GET /api/trades and /trades
    resp_trades = client.get("/api/trades?limit=10")
    assert resp_trades.status_code == 200
    assert len(resp_trades.json()) == 1
    assert resp_trades.json()[0]["symbol"] == "BTCUSD"

    # Test GET /api/signals and /signals
    resp_signals = client.get("/signals?limit=10")
    assert resp_signals.status_code == 200
    assert len(resp_signals.json()) == 1
    assert resp_signals.json()[0]["reason"] == "Test route signal"

    # Test GET /api/equity and /equity
    resp_equity = client.get("/api/equity?limit=10")
    assert resp_equity.status_code == 200
    assert len(resp_equity.json()) == 1
    assert resp_equity.json()[0]["equity"] == 10000.0


def test_api_kill_switch_and_resume():
    client = TestClient(app)

    # Initial state: running
    assert not risk_manager.is_halted()

    # Trigger emergency kill switch
    resp_kill = client.post("/api/kill", json={"reason": "Emergency hackathon kill test"})
    assert resp_kill.status_code == 200
    data = resp_kill.json()
    assert data["status"] == "killed"
    assert data["reason"] == "Emergency hackathon kill test"
    assert risk_manager.is_halted()

    # GET /api/risk should reflect halted state
    resp_risk = client.get("/api/risk")
    assert resp_risk.status_code == 200
    assert resp_risk.json()["halted"] is True
    assert "kill" in resp_risk.json()["halt_reason"].lower()

    # Resume trading via /resume
    resp_resume = client.post("/resume")
    assert resp_resume.status_code == 200
    assert resp_resume.json()["status"] == "resumed"
    assert not risk_manager.is_halted()


def test_api_pause():
    client = TestClient(app)

    resp_pause = client.post("/pause")
    assert resp_pause.status_code == 200
    assert resp_pause.json()["status"] == "paused"
    assert risk_manager.is_halted()


def test_api_price_and_ticker():
    client = TestClient(app)

    resp = client.get("/api/price")
    assert resp.status_code == 200
    data = resp.json()
    assert "price" in data
    assert "symbol" in data
    assert data["symbol"] == "BTCUSD"
    assert data["price"] > 0


def test_api_orders_and_positions():
    client = TestClient(app)

    resp_orders = client.get("/api/orders")
    assert resp_orders.status_code == 200
    assert isinstance(resp_orders.json(), list)

    resp_pos = client.get("/api/positions")
    assert resp_pos.status_code == 200
    assert isinstance(resp_pos.json(), list)


def test_api_strategy_endpoint():
    client = TestClient(app)

    resp = client.get("/api/strategy")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "BTCUSD"
    assert "timeframe" in data
    assert "status" in data


def test_api_logs_endpoint():
    client = TestClient(app)

    if hasattr(store, "save_log"):
        store.save_log("WARNING", "Test warning message", "test.module")

    resp = client.get("/api/logs?limit=10")
    assert resp.status_code == 200
    logs = resp.json()
    assert len(logs) >= 1
    assert any("Test warning" in l["message"] for l in logs)


def test_api_demo_trigger():
    client = TestClient(app)

    resp = client.post("/api/demo/trigger", json={"side": "buy"})
    assert resp.status_code == 200
    data = resp.json()
    assert "signal" in data
    assert "decision" in data
    assert data["signal"]["side"] == "buy"
    assert data["decision"]["approved"] is True
    assert data["order"] is not None
    assert data["result"]["ok"] is True

    # Trades endpoint should now have this demo trade
    trades_resp = client.get("/api/trades")
    assert trades_resp.status_code == 200
    assert len(trades_resp.json()) >= 1


def test_api_websocket_connection_and_actions():
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        # First message is snapshot
        data = ws.receive_json()
        assert data["type"] == "snapshot"
        assert "equity" in data["data"]
        assert "symbol" in data["data"]

        # Ping-pong
        ws.send_text(json.dumps({"action": "ping"}))
        pong = ws.receive_json()
        assert pong["type"] == "pong"
        assert "ts" in pong

        # Request snapshot on demand
        ws.send_text(json.dumps({"action": "snapshot"}))
        snap = ws.receive_json()
        assert snap["type"] == "snapshot"

        # Trigger kill switch via WebSocket
        ws.send_text(json.dumps({"action": "kill", "reason": "WS Kill Test"}))
        kill_msg = ws.receive_json()
        assert kill_msg["type"] == "kill_switch"
        assert risk_manager.is_halted()

        # Resume via WebSocket
        ws.send_text(json.dumps({"action": "resume"}))
        resume_msg = ws.receive_json()
        assert resume_msg["type"] == "resume"
        assert not risk_manager.is_halted()


def test_end_to_end_pipeline_integration():
    """End-to-end integration test per codex_team_prompt.md Phase C3:
    signal -> risk -> fake executor -> store -> API shows it.
    """
    client = TestClient(app)

    # 1. Generate Signal
    sig = Signal(
        symbol="BTCUSD",
        side="buy",
        entry_price=65000.0,
        stop_loss=64000.0,
        take_profit=67000.0,
        reason="E2E Pipeline Integration Test Signal",
        ts=1700000000,
    )

    # 2. Risk Manager Evaluate
    account = executor.get_account_state()
    decision = risk_manager.evaluate(sig, account)
    assert decision.approved
    assert decision.size > 0

    # 3. Fake Executor Execute
    order = OrderRequest(
        symbol=sig.symbol,
        side=sig.side,
        size=decision.size,
        entry_price=sig.entry_price,
        stop_loss=sig.stop_loss,
        take_profit=sig.take_profit,
        client_order_id="e2e-order-12345",
    )
    result = executor.execute(order)
    assert result.ok
    assert result.status == "FILLED"

    # 4. Store Persistence
    store.save_signal(sig, decision)
    store.save_trade(order, result)
    store.save_equity(1700000000, 10000.0)

    # 5. Verify API shows all saved data
    trades_resp = client.get("/api/trades")
    assert trades_resp.status_code == 200
    assert any(t["client_order_id"] == "e2e-order-12345" for t in trades_resp.json())

    signals_resp = client.get("/api/signals")
    assert signals_resp.status_code == 200
    assert any("E2E Pipeline" in s["reason"] for s in signals_resp.json())

    positions_resp = client.get("/api/positions")
    assert positions_resp.status_code == 200
    assert len(positions_resp.json()) >= 1
    assert positions_resp.json()[0]["symbol"] == "BTCUSD"

    status_resp = client.get("/api/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "running"
    assert status_resp.json()["open_positions_count"] >= 1
