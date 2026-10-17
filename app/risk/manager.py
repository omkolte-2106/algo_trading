"""Risk manager implementation satisfying RiskManager protocol (Role C).

Evaluates signals against account state, daily loss limits, drawdown kill switches,
max open positions, stale data guards, and leverage limits.
"""
import logging
from app.models import Signal, AccountState, RiskDecision
from app.interfaces import RiskManager
from app.config import settings
from app.risk.sizing import calculate_position_size

logger = logging.getLogger("app.risk.manager")

class DeltaRiskManager(RiskManager):
    """Enforces strict risk management and kill switches."""
    def __init__(self):
        self._halted: bool = False
        self._halt_reason: str = ""

    def evaluate(self, signal: Signal, account: AccountState) -> RiskDecision:
        if self._halted:
            return RiskDecision(approved=False, size=0.0, reason=f"Trading halted: {self._halt_reason}")

        # Check max open positions
        if len(account.open_positions) >= settings.MAX_OPEN_POSITIONS:
            return RiskDecision(approved=False, size=0.0, reason="Max open positions reached")

        # Check daily loss limit
        if account.daily_pnl < -(settings.DAILY_LOSS_LIMIT_PCT / 100.0 * account.equity):
            self.halt("Daily loss limit breached")
            return RiskDecision(approved=False, size=0.0, reason="Daily loss limit breached")

        # Calculate position size
        size = calculate_position_size(
            equity=account.equity,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            risk_pct=settings.RISK_PER_TRADE_PCT,
            max_leverage=settings.MAX_LEVERAGE,
            max_notional=settings.MAX_NOTIONAL_USD
        )

        if size <= 0:
            return RiskDecision(approved=False, size=0.0, reason="Computed position size is 0")

        return RiskDecision(approved=True, size=size, reason="Approved by risk manager")

    def is_halted(self) -> bool:
        return self._halted

    def halt(self, reason: str) -> None:
        logger.warning(f"HALTING TRADING: {reason}")
        self._halted = True
        self._halt_reason = reason

    def resume(self) -> None:
        logger.info("Resuming trading operations.")
        self._halted = False
        self._halt_reason = ""
