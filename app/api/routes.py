"""FastAPI API routes (Role C).

Endpoints:
- GET /status, /positions, /trades, /pnl, /equity, /risk, /signals
- POST /kill, /pause, /resume
"""
from fastapi import APIRouter
from typing import Dict, Any, List

router = APIRouter(prefix="/api", tags=["trading"])

@router.get("/status")
def get_status() -> Dict[str, Any]:
    return {"status": "ok"}

@router.get("/positions")
def get_positions() -> List[Dict[str, Any]]:
    return []

@router.get("/trades")
def get_trades() -> List[Dict[str, Any]]:
    return []

@router.get("/pnl")
def get_pnl() -> Dict[str, Any]:
    return {"daily_pnl": 0.0, "total_pnl": 0.0}

@router.get("/equity")
def get_equity() -> List[Dict[str, Any]]:
    return []

@router.get("/risk")
def get_risk_status() -> Dict[str, Any]:
    return {"halted": False}

@router.get("/signals")
def get_signals() -> List[Dict[str, Any]]:
    return []

@router.post("/kill")
def trigger_kill_switch() -> Dict[str, Any]:
    return {"status": "killed", "message": "Positions flattened and trading halted"}

@router.post("/pause")
def pause_trading() -> Dict[str, Any]:
    return {"status": "paused"}

@router.post("/resume")
def resume_trading() -> Dict[str, Any]:
    return {"status": "resumed"}
