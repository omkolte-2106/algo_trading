import pytest
from app.fakes import FakeExecutor
from app.models import OrderRequest

def test_fake_executor():
    executor = FakeExecutor(initial_equity=10000.0)
    order = OrderRequest(
        symbol="BTCUSD",
        side="buy",
        size=0.1,
        entry_price=60000.0,
        stop_loss=59000.0,
        take_profit=62000.0,
        client_order_id="test-123"
    )
    result = executor.execute(order)
    assert result.ok
    assert result.status == "FILLED"
    assert len(executor.orders) == 1

    state = executor.get_account_state()
    assert state.equity == 10000.0
    assert len(state.open_positions) == 1

    executor.flatten_all()
    assert len(executor.get_account_state().open_positions) == 0
