"""FastAPI API routes for live trading dashboard and controls (Role C).

Endpoints:
- GET  /api/status     - System health, account summary, and live status
- GET  /api/positions  - Open derivatives positions
- GET  /api/trades     - Executed trades log from PostgreSQL
- GET  /api/signals    - Strategy signals & risk decisions log
- GET  /api/pnl        - Daily & cumulative PnL summary
- GET  /api/equity     - Historical equity curve snapshots
- GET  /api/risk       - Real-time risk metrics (drawdown, daily loss, halt state)
- POST /api/kill       - Emergency kill switch: flattens positions and halts trading
- POST /api/pause      - Pauses new trade generation
- POST /api/resume     - Resumes trading operations
"""
import logging
import time
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("app.api.routes")

router = APIRouter(prefix="/api", tags=["trading"])

# Dependency references set by app.main at startup
_services: Dict[str, Any] = {}

def set_services(executor, risk_manager, store, market_data=None):
    """Register runtime services with the API router."""
    _services["executor"] = executor
    _services["risk_manager"] = risk_manager
    _services["store"] = store
    _services["market_data"] = market_data

def get_service(name: str):
    return _services.get(name)


class KillSwitchRequest(BaseModel):
    reason: Optional[str] = "Manual emergency kill switch triggered via API"


@router.get("/status")
def get_status() -> Dict[str, Any]:
    executor = get_service("executor")
    risk_manager = get_service("risk_manager")
    
    account = executor.get_account_state() if executor else None
    is_halted = risk_manager.is_halted() if risk_manager else False

    return {
        "status": "halted" if is_halted else "running",
        "equity": account.equity if account else 0.0,
        "daily_pnl": account.daily_pnl if account else 0.0,
        "peak_equity": account.peak_equity if account else 0.0,
        "open_positions_count": len(account.open_positions) if account else 0,
        "is_halted": is_halted,
        "server_time": int(time.time()),
    }


@router.get("/positions")
def get_positions() -> List[Dict[str, Any]]:
    executor = get_service("executor")
    if not executor:
        return []
    account = executor.get_account_state()
    return [pos.model_dump() for pos in account.open_positions]


@router.get("/trades")
def get_trades(limit: int = Query(default=100, ge=1, le=1000)) -> List[Dict[str, Any]]:
    store = get_service("store")
    if not store:
        return []
    return store.get_trades(limit=limit)


@router.get("/signals")
def get_signals(limit: int = Query(default=100, ge=1, le=1000)) -> List[Dict[str, Any]]:
    store = get_service("store")
    if not store:
        return []
    if hasattr(store, "get_signals"):
        return store.get_signals(limit=limit)
    return getattr(store, "signals", [])[-limit:]


@router.get("/pnl")
def get_pnl() -> Dict[str, Any]:
    executor = get_service("executor")
    if not executor:
        return {"daily_pnl": 0.0, "total_pnl": 0.0, "unrealized_pnl": 0.0}
    
    account = executor.get_account_state()
    unrealized = sum(p.unrealized_pnl for p in account.open_positions)
    return {
        "daily_pnl": round(account.daily_pnl, 2),
        "unrealized_pnl": round(unrealized, 2),
        "equity": round(account.equity, 2),
        "peak_equity": round(account.peak_equity, 2),
    }


@router.get("/equity")
def get_equity(limit: int = Query(default=1000, ge=1, le=5000)) -> List[Dict[str, Any]]:
    store = get_service("store")
    if not store:
        return []
    return store.get_equity_curve(limit=limit)


@router.get("/risk")
def get_risk_status() -> Dict[str, Any]:
    risk_manager = get_service("risk_manager")
    executor = get_service("executor")
    store = get_service("store")
    
    account = executor.get_account_state() if executor else None
    is_halted = risk_manager.is_halted() if risk_manager else False
    halt_reason = getattr(risk_manager, "_halt_reason", "") if risk_manager else ""
    
    peak = account.peak_equity if account and account.peak_equity > 0 else 1.0
    current = account.equity if account else 1.0
    current_drawdown_pct = max(0.0, round(((peak - current) / peak) * 100.0, 2))
    
    events = store.get_risk_events(limit=10) if (store and hasattr(store, "get_risk_events")) else []

    return {
        "halted": is_halted,
        "halt_reason": halt_reason,
        "daily_loss_used_pct": round(abs(min(0.0, account.daily_pnl)) / max(1.0, current) * 100.0, 2) if account else 0.0,
        "current_drawdown_pct": current_drawdown_pct,
        "recent_risk_events": events,
    }


@router.post("/kill")
def trigger_kill_switch(payload: Optional[KillSwitchRequest] = None) -> Dict[str, Any]:
    reason = payload.reason if payload and payload.reason else "Manual emergency kill switch triggered via API"
    logger.warning(f"[api] EMERGENCY KILL SWITCH TRIGGERED: {reason}")
    
    risk_manager = get_service("risk_manager")
    executor = get_service("executor")
    store = get_service("store")

    if risk_manager:
        risk_manager.halt(reason)
    
    if executor:
        executor.flatten_all()

    if store and hasattr(store, "save_risk_event"):
        store.save_risk_event("KILL_SWITCH", reason)

    return {
        "status": "killed",
        "message": "Positions flattened and trading halted",
        "reason": reason,
        "timestamp": int(time.time()),
    }


@router.post("/pause")
def pause_trading() -> Dict[str, Any]:
    reason = "Trading paused via API"
    logger.info(f"[api] {reason}")
    
    risk_manager = get_service("risk_manager")
    store = get_service("store")

    if risk_manager:
        risk_manager.halt(reason)

    if store and hasattr(store, "save_risk_event"):
        store.save_risk_event("PAUSE", reason)

    return {
        "status": "paused",
        "timestamp": int(time.time()),
    }


@router.post("/resume")
def resume_trading() -> Dict[str, Any]:
    logger.info("[api] Resuming trading operations via API")
    
    risk_manager = get_service("risk_manager")
    store = get_service("store")

    if risk_manager:
        risk_manager.resume()

    if store and hasattr(store, "save_risk_event"):
        store.save_risk_event("RESUME", "Trading resumed via API")

    return {
        "status": "resumed",
        "timestamp": int(time.time()),
    }
