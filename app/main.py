import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.fakes import FakeExecutor, FakeMarketData
from app.storage.store import get_default_store
from app.risk.manager import DeltaRiskManager
from app.api.routes import router as api_router, set_services

# Setup logging per working rules: [module] message
logging.basicConfig(
    level=logging.INFO,
    format="[%(name)s] %(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("app.main")

# Global services
store = get_default_store()
executor = FakeExecutor()
risk_manager = DeltaRiskManager(flatten_callback=executor.flatten_all)
market_data = FakeMarketData()

# Connect runtime services to API router
set_services(
    executor=executor,
    risk_manager=risk_manager,
    store=store,
    market_data=market_data,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Algo Trading Bot...")
    logger.info(f"Target Symbol: {settings.SYMBOL}, Timeframe: {settings.TIMEFRAME}")
    logger.info(f"Testnet URL: {settings.DELTA_BASE_URL}")
    logger.info(f"Database: PostgreSQL '{settings.DB_NAME}' on {settings.DB_HOST}:{settings.DB_PORT}")
    yield
    logger.info("Shutting down Algo Trading Bot...")

app = FastAPI(
    title="Delta Exchange Algo Trading Bot",
    description="Automated algorithmic trading system on Delta Exchange Testnet",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {
        "name": "Delta Exchange Algo Trader",
        "status": "running",
        "symbol": settings.SYMBOL,
        "demo_mode": settings.DEMO_MODE,
        "database": getattr(store, "__class__", type(store)).__name__
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/status")
def get_status():
    account = executor.get_account_state()
    return {
        "status": "halted" if risk_manager.is_halted() else "online",
        "equity": account.equity,
        "daily_pnl": account.daily_pnl,
        "is_halted": risk_manager.is_halted(),
        "open_positions": [p.model_dump() for p in account.open_positions]
    }

app.include_router(api_router)
