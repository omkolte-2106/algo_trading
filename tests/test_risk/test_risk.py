import pytest
from app.risk.sizing import calculate_position_size
from app.risk.manager import DeltaRiskManager
from app.models import Signal, AccountState

def test_calculate_position_size():
    # Equity $10,000, 1% risk = $100. Entry 60000, Stop 59000 -> dist 1000 -> size 0.1 BTC
    size = calculate_position_size(
        equity=10000.0,
        entry_price=60000.0,
        stop_loss=59000.0,
        risk_pct=1.0,
        max_leverage=5.0,
        max_notional=50000.0
    )
    assert size == 0.1

def test_risk_manager_halts():
    rm = DeltaRiskManager()
    assert not rm.is_halted()
    rm.halt("Manual kill switch")
    assert rm.is_halted()

    signal = Signal(
        symbol="BTCUSD",
        side="buy",
        entry_price=60000.0,
        stop_loss=59000.0,
        take_profit=62000.0,
        reason="Test",
        ts=1700000000
    )
    account = AccountState(
        equity=10000.0,
        open_positions=[],
        daily_pnl=0.0,
        peak_equity=10000.0,
        last_data_ts=1700000000
    )
    decision = rm.evaluate(signal, account)
    assert not decision.approved
    assert "halted" in decision.reason
