import pytest
from fastapi.testclient import TestClient
from app.main import app, risk_manager, executor, store
from app.models import Signal, RiskDecision, OrderRequest, OrderResult

@pytest.fixture(autouse=True)
def reset_state():
    # Ensure clean state before each test
    risk_manager.resume()
    executor.flatten_all()
    yield
    risk_manager.resume()

def test_app_health_and_root():
    client = TestClient(app)
    
    resp_root = client.get("/")
    assert resp_root.status_code == 200
    assert resp_root.json()["status"] == "running"

    resp_health = client.get("/health")
    assert resp_health.status_code == 200
    assert resp_health.json() == {"status": "ok"}


def test_api_status_and_pnl():
    client = TestClient(app)
    
    resp_status = client.get("/api/status")
    assert resp_status.status_code == 200
    data = resp_status.json()
    assert "equity" in data
    assert "is_halted" in data
    assert data["is_halted"] is False

    resp_pnl = client.get("/api/pnl")
    assert resp_pnl.status_code == 200
    pnl_data = resp_pnl.json()
    assert "daily_pnl" in pnl_data
    assert "equity" in pnl_data


def test_api_trades_and_signals():
    client = TestClient(app)
    
    # Save a test signal and trade
    sig = Signal(
        symbol="BTCUSD",
        side="buy",
        entry_price=64000.0,
        stop_loss=63000.0,
        take_profit=66000.0,
        reason="Test route signal",
        ts=1700000000
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
        client_order_id="client-test-api-001"
    )
    result = OrderResult(ok=True, order_id="delta-order-001", status="FILLED")
    store.save_trade(order, result)
    store.save_equity(1700000000, 10000.0)

    # Test GET /api/trades
    resp_trades = client.get("/api/trades?limit=10")
    assert resp_trades.status_code == 200
    assert len(resp_trades.json()) >= 1
    assert resp_trades.json()[0]["symbol"] == "BTCUSD"

    # Test GET /api/signals
    resp_signals = client.get("/api/signals?limit=10")
    assert resp_signals.status_code == 200
    assert len(resp_signals.json()) >= 1

    # Test GET /api/equity
    resp_equity = client.get("/api/equity?limit=10")
    assert resp_equity.status_code == 200
    assert len(resp_equity.json()) >= 1


def test_api_kill_switch_and_resume():
    client = TestClient(app)
    
    # Verify initially running
    assert not risk_manager.is_halted()

    # Trigger emergency kill switch
    resp_kill = client.post("/api/kill", json={"reason": "Emergency hackathon test"})
    assert resp_kill.status_code == 200
    assert resp_kill.json()["status"] == "killed"
    assert risk_manager.is_halted()

    # GET /api/risk should reflect halted
    resp_risk = client.get("/api/risk")
    assert resp_risk.status_code == 200
    assert resp_risk.json()["halted"] is True

    # Resume trading
    resp_resume = client.post("/api/resume")
    assert resp_resume.status_code == 200
    assert resp_resume.json()["status"] == "resumed"
    assert not risk_manager.is_halted()


def test_api_pause():
    client = TestClient(app)
    
    resp_pause = client.post("/api/pause")
    assert resp_pause.status_code == 200
    assert resp_pause.json()["status"] == "paused"
    assert risk_manager.is_halted()
