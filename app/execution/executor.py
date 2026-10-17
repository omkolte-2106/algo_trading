"""Order execution engine (Role A).

Implements Executor protocol with bracket orders (SL/TP attached),
idempotent client_order_id, status tracking, and emergency flattening.
"""
import logging
from app.models import OrderRequest, OrderResult, AccountState
from app.interfaces import Executor

logger = logging.getLogger("app.execution.executor")

class DeltaExecutor(Executor):
    """Executes trades on Delta Exchange testnet."""
    def __init__(self, client=None):
        self.client = client

    def execute(self, order: OrderRequest) -> OrderResult:
        """Place order with bracket SL/TP."""
        raise NotImplementedError("To be implemented in Phase A2")

    def flatten_all(self) -> None:
        """Emergency flatten all positions."""
        raise NotImplementedError("To be implemented in Phase A2")

    def get_account_state(self) -> AccountState:
        """Fetch current equity, positions, daily PnL, and peak equity."""
        raise NotImplementedError("To be implemented in Phase A2")
