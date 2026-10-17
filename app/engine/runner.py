"""Main trading engine runner loop (Role A).

Coordinates the pipeline on closed candles:
Data -> Strategy (Signal) -> Risk Manager (evaluate) -> Executor (order) -> Store (persist).
"""
import logging
from app.interfaces import Strategy, RiskManager, Executor, MarketData, Store

logger = logging.getLogger("app.engine.runner")

class EngineRunner:
    """Orchestrates end-to-end trading loop."""
    def __init__(
        self,
        strategy: Strategy,
        risk_manager: RiskManager,
        executor: Executor,
        market_data: MarketData,
        store: Store,
    ):
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.executor = executor
        self.market_data = market_data
        self.store = store

    def run_tick(self) -> None:
        """Execute one iteration of the strategy-to-execution pipeline."""
        if self.risk_manager.is_halted():
            logger.warning("Risk manager is HALTED. Skipping trading cycle.")
            return
        logger.info("Executing trading tick...")
