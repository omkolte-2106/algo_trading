"""FastAPI API routes for live trading dashboard and controls (Role C).

Endpoints (available under both /api/* and /*):
- GET  /status       - System health, account summary, and live status
- GET  /positions    - Open derivatives positions
- GET  /orders       - Active and recorded orders
- GET  /trades       - Executed trades log from SQLite/PostgreSQL
- GET  /signals      - Strategy signals & risk decisions log
- GET  /pnl          - Daily & cumulative PnL summary
- GET  /equity       - Historical equity curve snapshots
- GET  /risk         - Real-time risk metrics (drawdown, daily loss, halt state)
- GET  /price        - Real-time mark/ticker price
- GET  /strategy     - Strategy state and configuration
- GET  /logs         - Application/bot logs
- POST /kill         - Emergency kill switch: flattens positions and halts trading
- POST /pause        - Pauses new trade generation
- POST /resume       - Resumes trading operations
- POST /demo/trigger - Trigger test trade pipeline (DEMO_MODE)
- WS   /ws           - Real-time bidirectional WebSocket stream for dashboard
- GET  /stream       - Server-Sent Events (SSE) live updates stream
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Query, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.models import Signal, RiskDecision, OrderRequest, OrderResult
from app.config import settings

logger = logging.getLogger("app.api.routes")

router = APIRouter(tags=["trading"])

# Dependency references set by app.main at startup or via set_services
_services: Dict[str, Any] = {}


def set_services(executor=None, risk_manager=None, store=None, market_data=None, strategy=None):
    """Register runtime services with the API router for dependency injection."""
    if executor is not None:
        _services["executor"] = executor
    if risk_manager is not None:
        _services["risk_manager"] = risk_manager
    if store is not None:
        _services["store"] = store
    if market_data is not None:
        _services["market_data"] = market_data
    if strategy is not None:
        _services["strategy"] = strategy


def get_service(name: str) -> Any:
    return _services.get(name)


class KillSwitchRequest(BaseModel):
    reason: Optional[str] = "Manual emergency kill switch triggered via API"


class DemoTriggerRequest(BaseModel):
    side: Optional[str] = "buy"
    price_offset_pct: Optional[float] = 0.0


# -----------------------------------------------------------------------------
# WebSocket Connection Manager
# -----------------------------------------------------------------------------

class ConnectionManager:
    """Manages active WebSocket connections for live dashboard streaming."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("[api.ws] Client connected (%d total)", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("[api.ws] Client disconnected (%d remaining)", len(self.active_connections))

    async def broadcast(self, message: Dict[str, Any]):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)


ws_manager = ConnectionManager()


def get_system_snapshot() -> Dict[str, Any]:
    """Helper compiling full system status snapshot for WebSocket/SSE."""
    executor = get_service("executor")
    risk_manager = get_service("risk_manager")
    store = get_service("store")
    market_data = get_service("market_data")

    account = executor.get_account_state() if executor else None
    is_halted = risk_manager.is_halted() if risk_manager else False
    halt_reason = (
        getattr(risk_manager, "halt_reason", "")
        or getattr(risk_manager, "_halt_reason", "")
        if risk_manager
        else ""
    )

    price = 0.0
    if market_data:
        candles = market_data.get_candles(settings.SYMBOL, settings.TIMEFRAME, limit=1)
        if candles:
            price = candles[-1].close

    trades = store.get_trades(limit=10) if store else []
    signals = store.get_signals(limit=10) if (store and hasattr(store, "get_signals")) else []
    curve = store.get_equity_curve(limit=20) if store else []

    peak = account.peak_equity if (account and account.peak_equity > 0) else 1.0
    current = account.equity if account else 1.0
    drawdown = max(0.0, round(((peak - current) / peak) * 100.0, 2))

    return {
        "status": "halted" if is_halted else "running",
        "equity": account.equity if account else 0.0,
        "daily_pnl": account.daily_pnl if account else 0.0,
        "peak_equity": account.peak_equity if account else 0.0,
        "is_halted": is_halted,
        "halt_reason": halt_reason,
        "drawdown_pct": drawdown,
        "price": price,
        "symbol": settings.SYMBOL,
        "open_positions": [p.model_dump() for p in account.open_positions] if account else [],
        "trades": trades,
        "signals": signals,
        "equity_curve": curve,
        "server_time": int(time.time()),
    }


# -----------------------------------------------------------------------------
# REST Endpoints
# -----------------------------------------------------------------------------

@router.get("/status")
def get_status() -> Dict[str, Any]:
    executor = get_service("executor")
    risk_manager = get_service("risk_manager")
    market_data = get_service("market_data")

    account = executor.get_account_state() if executor else None
    is_halted = risk_manager.is_halted() if risk_manager else False
    halt_reason = (
        getattr(risk_manager, "halt_reason", "")
        or getattr(risk_manager, "_halt_reason", "")
        if risk_manager
        else ""
    )

    current_price = None
    if market_data:
        candles = market_data.get_candles(settings.SYMBOL, settings.TIMEFRAME, limit=1)
        if candles:
            current_price = candles[-1].close

    return {
        "status": "halted" if is_halted else "running",
        "equity": account.equity if account else 0.0,
        "daily_pnl": account.daily_pnl if account else 0.0,
        "peak_equity": account.peak_equity if account else 0.0,
        "open_positions_count": len(account.open_positions) if account else 0,
        "is_halted": is_halted,
        "halt_reason": halt_reason,
        "symbol": settings.SYMBOL,
        "current_price": current_price,
        "demo_mode": settings.DEMO_MODE,
        "server_time": int(time.time()),
    }


@router.get("/positions")
def get_positions() -> List[Dict[str, Any]]:
    executor = get_service("executor")
    if not executor:
        return []
    account = executor.get_account_state()
    return [pos.model_dump() for pos in account.open_positions]


@router.get("/orders")
def get_orders() -> List[Dict[str, Any]]:
    executor = get_service("executor")
    if not executor:
        return []
    if hasattr(executor, "get_open_orders"):
        return executor.get_open_orders()
    if hasattr(executor, "orders"):
        raw_orders = getattr(executor, "orders", [])
        return [
            o.model_dump() if hasattr(o, "model_dump") else dict(o)
            for o in raw_orders
        ]
    return []


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
        return {"daily_pnl": 0.0, "total_pnl": 0.0, "unrealized_pnl": 0.0, "equity": 0.0, "peak_equity": 0.0}

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
    halt_reason = (
        getattr(risk_manager, "halt_reason", "")
        or getattr(risk_manager, "_halt_reason", "")
        if risk_manager
        else ""
    )

    peak = account.peak_equity if (account and account.peak_equity > 0) else 1.0
    current = account.equity if account else 1.0
    current_drawdown_pct = max(0.0, round(((peak - current) / peak) * 100.0, 2))
    daily_loss_used_pct = (
        round(abs(min(0.0, account.daily_pnl)) / max(1.0, current) * 100.0, 2)
        if account
        else 0.0
    )

    events = store.get_risk_events(limit=10) if (store and hasattr(store, "get_risk_events")) else []

    return {
        "halted": is_halted,
        "halt_reason": halt_reason,
        "daily_loss_used_pct": daily_loss_used_pct,
        "daily_loss_limit_pct": settings.DAILY_LOSS_LIMIT_PCT,
        "current_drawdown_pct": current_drawdown_pct,
        "max_drawdown_pct": settings.MAX_DRAWDOWN_PCT,
        "max_leverage": settings.MAX_LEVERAGE,
        "max_open_positions": settings.MAX_OPEN_POSITIONS,
        "max_notional_usd": settings.MAX_NOTIONAL_USD,
        "stale_data_seconds": settings.STALE_DATA_SECONDS,
        "recent_risk_events": events,
    }


@router.get("/price")
def get_price(symbol: Optional[str] = None) -> Dict[str, Any]:
    sym = symbol or settings.SYMBOL
    market_data = get_service("market_data")
    if not market_data:
        return {"symbol": sym, "price": 0.0, "timestamp": int(time.time())}
    candles = market_data.get_candles(sym, settings.TIMEFRAME, limit=1)
    if not candles:
        return {"symbol": sym, "price": 0.0, "timestamp": int(time.time())}
    latest = candles[-1]
    return {
        "symbol": sym,
        "price": latest.close,
        "open": latest.open,
        "high": latest.high,
        "low": latest.low,
        "volume": latest.volume,
        "timestamp": latest.ts,
    }


@router.get("/strategy")
def get_strategy_state() -> Dict[str, Any]:
    strategy = get_service("strategy")
    risk_manager = get_service("risk_manager")
    is_halted = risk_manager.is_halted() if risk_manager else False

    name = strategy.__class__.__name__ if strategy else "TrendFollowingStrategy"
    return {
        "name": name,
        "symbol": settings.SYMBOL,
        "timeframe": settings.TIMEFRAME,
        "htf_timeframe": settings.HTF_TIMEFRAME,
        "status": "halted" if is_halted else "active",
        "description": "Trend-following with volatility filter on BTCUSD perpetual, 15m candles",
    }


@router.get("/logs")
def get_logs(limit: int = Query(default=100, ge=1, le=1000)) -> List[Dict[str, Any]]:
    store = get_service("store")
    if not store:
        return []
    if hasattr(store, "get_logs"):
        return store.get_logs(limit=limit)
    return []


@router.post("/kill")
async def trigger_kill_switch(payload: Optional[KillSwitchRequest] = None) -> Dict[str, Any]:
    reason = payload.reason if payload and payload.reason else "Manual emergency kill switch triggered via API"
    logger.warning("[api] EMERGENCY KILL SWITCH TRIGGERED: %s", reason)

    risk_manager = get_service("risk_manager")
    executor = get_service("executor")
    store = get_service("store")

    if risk_manager:
        risk_manager.halt(reason)

    if executor:
        executor.flatten_all()

    if store and hasattr(store, "save_risk_event"):
        store.save_risk_event("KILL_SWITCH", reason)

    response = {
        "status": "killed",
        "message": "Positions flattened and trading halted",
        "reason": reason,
        "timestamp": int(time.time()),
    }
    await ws_manager.broadcast({"type": "kill_switch", "data": response})
    return response


@router.post("/pause")
async def pause_trading() -> Dict[str, Any]:
    reason = "Trading paused via API"
    logger.info("[api] %s", reason)

    risk_manager = get_service("risk_manager")
    store = get_service("store")

    if risk_manager:
        risk_manager.halt(reason)

    if store and hasattr(store, "save_risk_event"):
        store.save_risk_event("PAUSE", reason)

    response = {
        "status": "paused",
        "timestamp": int(time.time()),
    }
    await ws_manager.broadcast({"type": "pause", "data": response})
    return response


@router.post("/resume")
async def resume_trading() -> Dict[str, Any]:
    logger.info("[api] Resuming trading operations via API")

    risk_manager = get_service("risk_manager")
    store = get_service("store")

    if risk_manager:
        risk_manager.resume()

    if store and hasattr(store, "save_risk_event"):
        store.save_risk_event("RESUME", "Trading resumed via API")

    response = {
        "status": "resumed",
        "timestamp": int(time.time()),
    }
    await ws_manager.broadcast({"type": "resume", "data": response})
    return response


@router.post("/demo/trigger")
async def trigger_demo_signal(payload: Optional[DemoTriggerRequest] = None) -> Dict[str, Any]:
    """Demo mode trigger: generates a test signal that flows through the full pipeline:
    RiskManager.evaluate -> Executor.execute -> Store.save_*.
    """
    market_data = get_service("market_data")
    risk_manager = get_service("risk_manager")
    executor = get_service("executor")
    store = get_service("store")

    side = (payload.side if payload and payload.side else "buy").lower()
    if side not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="side must be 'buy' or 'sell'")

    # Determine reference price
    ref_price = 65000.0
    if market_data:
        candles = market_data.get_candles(settings.SYMBOL, settings.TIMEFRAME, limit=1)
        if candles:
            ref_price = candles[-1].close

    if payload and payload.price_offset_pct:
        ref_price *= (1.0 + payload.price_offset_pct / 100.0)

    now = int(time.time())
    if side == "buy":
        entry = round(ref_price, 2)
        sl = round(entry * 0.985, 2)
        tp = round(entry * 1.03, 2)
    else:
        entry = round(ref_price, 2)
        sl = round(entry * 1.015, 2)
        tp = round(entry * 0.97, 2)

    signal = Signal(
        symbol=settings.SYMBOL,
        side=side,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        reason=f"Demo triggered {side.upper()} test signal",
        ts=now,
    )

    account = executor.get_account_state() if executor else None
    if not account:
        raise HTTPException(status_code=500, detail="Executor account state unavailable")

    decision = (
        risk_manager.evaluate(signal, account)
        if risk_manager
        else RiskDecision(approved=False, reason="No risk manager")
    )

    if store:
        store.save_signal(signal, decision)

    order_result = None
    order_req = None
    if decision.approved:
        order_req = OrderRequest(
            symbol=signal.symbol,
            side=signal.side,
            size=decision.size,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            client_order_id=f"demo-{uuid.uuid4().hex[:8]}",
        )
        if executor:
            order_result = executor.execute(order_req)
            if store:
                store.save_trade(order_req, order_result)

    result_data = {
        "signal": signal.model_dump(),
        "decision": decision.model_dump(),
        "order": order_req.model_dump() if order_req else None,
        "result": order_result.model_dump() if order_result else None,
    }
    await ws_manager.broadcast({"type": "demo_trade", "data": result_data})
    return result_data


# -----------------------------------------------------------------------------
# WebSocket & SSE Streaming
# -----------------------------------------------------------------------------

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Bidirectional WebSocket for live dashboard data and control signals."""
    await ws_manager.connect(websocket)
    try:
        # Send initial snapshot
        snapshot = get_system_snapshot()
        await websocket.send_json({"type": "snapshot", "data": snapshot})

        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                action = msg.get("action")
                if action == "ping":
                    await websocket.send_json({"type": "pong", "ts": int(time.time())})
                elif action == "snapshot":
                    snapshot = get_system_snapshot()
                    await websocket.send_json({"type": "snapshot", "data": snapshot})
                elif action == "kill":
                    reason = msg.get("reason", "Kill switch via WebSocket")
                    rm = get_service("risk_manager")
                    ex = get_service("executor")
                    st = get_service("store")
                    if rm:
                        rm.halt(reason)
                    if ex:
                        ex.flatten_all()
                    if st and hasattr(st, "save_risk_event"):
                        st.save_risk_event("KILL_SWITCH", reason)
                    await ws_manager.broadcast({
                        "type": "kill_switch",
                        "data": {"status": "killed", "reason": reason, "timestamp": int(time.time())},
                    })
                elif action == "pause":
                    rm = get_service("risk_manager")
                    if rm:
                        rm.halt("Paused via WebSocket")
                    await ws_manager.broadcast({"type": "pause", "data": {"status": "paused"}})
                elif action == "resume":
                    rm = get_service("risk_manager")
                    if rm:
                        rm.resume()
                    await ws_manager.broadcast({"type": "resume", "data": {"status": "resumed"}})
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error("[api.ws] WebSocket error: %s", e)
        ws_manager.disconnect(websocket)


@router.get("/stream")
async def sse_stream():
    """Server-Sent Events (SSE) live updates stream."""
    async def event_generator():
        while True:
            snapshot = get_system_snapshot()
            yield f"data: {json.dumps(snapshot)}\n\n"
            await asyncio.sleep(2.0)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
