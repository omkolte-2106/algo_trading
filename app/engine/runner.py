"""Main trading engine runner loop (Role A).

Coordinates the end-to-end trading pipeline on closed candles:
MarketData -> Strategy (Signal) -> Risk Manager (evaluate) -> Executor (bracket order) -> Store (persist).
"""
import asyncio
import logging
import time
import uuid
from typing import Optional

from app.config import settings
from app.interfaces import Strategy, RiskManager, Executor, MarketData, Store
from app.models import OrderRequest, OrderResult, Candle

logger = logging.getLogger("app.engine.runner")


class EngineRunner:
    """Orchestrates the end-to-end autonomous trading loop."""

    def __init__(
        self,
        strategy: Strategy,
        risk_manager: RiskManager,
        executor: Executor,
        market_data: MarketData,
        store: Store,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        htf_timeframe: Optional[str] = None,
    ):
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.executor = executor
        self.market_data = market_data
        self.store = store
        self.symbol = symbol or settings.SYMBOL
        self.timeframe = timeframe or settings.TIMEFRAME
        self.htf_timeframe = htf_timeframe or settings.HTF_TIMEFRAME

        self._running: bool = False
        self._last_processed_candle_ts: int = 0
        self._loop_task: Optional[asyncio.Task] = None
        logger.info(
            "[engine] Initialized EngineRunner for %s (TF: %s, HTF: %s)",
            self.symbol,
            self.timeframe,
            self.htf_timeframe,
        )

    def run_tick(self) -> Optional[OrderResult]:
        """Execute one complete cycle of the trading pipeline:
        1. Guard against halted state.
        2. Fetch market candles (15m & 1h).
        3. Evaluate strategy signal.
        4. Pass signal through the 8-rule risk manager.
        5. If approved, construct OrderRequest and execute on exchange.
        6. Persist signal, decision, trade, and equity to storage.
        """
        if self.risk_manager.is_halted():
            logger.warning("[engine] Risk manager is HALTED. Skipping trading tick.")
            return None

        logger.info("[engine] Fetching candles for %s...", self.symbol)
        try:
            candles = self.market_data.get_candles(self.symbol, self.timeframe, limit=100)
            htf_candles = self.market_data.get_candles(self.symbol, self.htf_timeframe, limit=100)
        except Exception as e:
            logger.error("[engine] Failed to fetch market data: %s", e)
            return None

        if not candles:
            logger.warning("[engine] No candle data received. Skipping tick.")
            return None

        latest_candle = candles[-1]
        logger.info(
            "[engine] Latest bar close: %.2f at %d",
            latest_candle.close,
            latest_candle.ts,
        )

        # 2. Strategy Signal Generation
        try:
            signal = self.strategy.generate_signal(candles, htf_candles)
        except NotImplementedError:
            logger.debug("[engine] Strategy generate_signal is not yet implemented (Role B).")
            return None
        except Exception as e:
            logger.error("[engine] Error generating strategy signal: %s", e)
            return None

        if signal is None:
            logger.info("[engine] No signal generated for current bar.")
            return None

        logger.info(
            "[engine] Signal received: %s %s @ %.2f (SL: %.2f, TP: %.2f, Reason: %s)",
            signal.side.upper(),
            signal.symbol,
            signal.entry_price,
            signal.stop_loss,
            signal.take_profit,
            signal.reason,
        )

        # 3. Risk Engine Evaluation
        account = self.executor.get_account_state()
        decision = self.risk_manager.evaluate(signal, account)

        # Persist signal and risk decision
        if self.store:
            self.store.save_signal(signal, decision)

        if not decision.approved:
            logger.warning("[engine] Trade REJECTED by Risk Manager: %s", decision.reason)
            return None

        # 4. Order Construction and Execution
        client_order_id = f"ord-{self.symbol.lower()}-{signal.side}-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        order_request = OrderRequest(
            symbol=signal.symbol,
            side=signal.side,
            size=decision.size,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            client_order_id=client_order_id,
        )

        logger.info("[engine] Risk APPROVED. Sending OrderRequest: %s", order_request.client_order_id)
        result = self.executor.execute(order_request)

        # 5. Persistence
        if self.store:
            self.store.save_trade(order_request, result)
            self.store.save_equity(signal.ts, account.equity)

        logger.info(
            "[engine] Order result: ok=%s status=%s id=%s error=%s",
            result.ok,
            result.status,
            result.order_id,
            result.error,
        )
        return result

    async def run_loop(self, poll_interval_seconds: float = 30.0) -> None:
        """Asynchronous execution loop polling candles and running ticks."""
        self._running = True
        logger.info("[engine] Autonomous trading loop started (interval: %.1fs)", poll_interval_seconds)

        while self._running:
            try:
                self.run_tick()
            except Exception as e:
                logger.error("[engine] Error in trading loop tick: %s", e)

            await asyncio.sleep(poll_interval_seconds)

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None, interval: float = 30.0) -> asyncio.Task:
        """Start runner loop in asyncio background task."""
        active_loop = loop or asyncio.get_event_loop()
        self._loop_task = active_loop.create_task(self.run_loop(poll_interval_seconds=interval))
        return self._loop_task

    def stop(self) -> None:
        """Gracefully stop engine loop."""
        logger.info("[engine] Stopping trading engine runner...")
        self._running = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
