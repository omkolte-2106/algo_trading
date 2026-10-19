import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.fakes import FakeExecutor, FakeMarketData
from app.storage.store import get_default_store, StoreLoggingHandler
from app.risk.manager import DeltaRiskManager
from app.api.routes import router as api_router, set_services, ws_manager

# Setup logging per working rules: [module] message
logging.basicConfig(
    level=logging.INFO,
    format="[%(name)s] %(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("app.main")

# Global services (Role C defaults to fakes & SQLiteStore, injectable at runtime)
store = get_default_store()
executor = FakeExecutor()
risk_manager = DeltaRiskManager(flatten_callback=executor.flatten_all)
market_data = FakeMarketData()

# Attach SQLite/Postgres Store logging handler
store_logging_handler = StoreLoggingHandler(store=store, level=logging.INFO)
logging.getLogger().addHandler(store_logging_handler)

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
    logger.info("Target Symbol: %s, Timeframe: %s", settings.SYMBOL, settings.TIMEFRAME)
    logger.info("Testnet URL: %s", settings.DELTA_BASE_URL)
    logger.info("Active Storage: %s", store.__class__.__name__)
    yield
    logger.info("Shutting down Algo Trading Bot...")

app = FastAPI(
    title="Delta Exchange Algo Trading Bot",
    description="Automated algorithmic trading system on Delta Exchange Testnet (Role C API & Risk Engine)",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for dashboard UI (React / Next.js / Tailwind on any local port)
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
        "status": "halted" if risk_manager.is_halted() else "running",
        "symbol": settings.SYMBOL,
        "demo_mode": settings.DEMO_MODE,
        "database": getattr(store, "__class__", type(store)).__name__
    }

@app.get("/health")
def health():
    return {"status": "ok"}

# Mount API router under both /api and root prefixes for seamless dashboard compatibility
app.include_router(api_router, prefix="/api")
app.include_router(api_router)
