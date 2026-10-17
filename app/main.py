import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.fakes import FakeExecutor, FakeMarketData, FakeStore
from app.models import Position, AccountState

# Setup logging per working rules: [module] message
logging.basicConfig(
    level=logging.INFO,
    format="[%(name)s] %(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("app.main")

# Global services (defaults to fakes during Phase 0 / development)
executor = FakeExecutor()
market_data = FakeMarketData()
store = FakeStore()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Algo Trading Bot...")
    logger.info(f"Target Symbol: {settings.SYMBOL}, Timeframe: {settings.TIMEFRAME}")
    logger.info(f"Testnet URL: {settings.DELTA_BASE_URL}")
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
        "demo_mode": settings.DEMO_MODE
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/status")
def get_status():
    account = executor.get_account_state()
    return {
        "status": "online",
        "equity": account.equity,
        "daily_pnl": account.daily_pnl,
        "open_positions": [p.model_dump() for p in account.open_positions]
    }

from app.api.routes import router as api_router
app.include_router(api_router)

