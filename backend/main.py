import logging
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Core imports ───────────────────────────────────────────────
from core.auth.router import router as auth_router

# ── Module routers ─────────────────────────────────────────────
from modules.sale_profit.router import router as sale_profit_router
from modules.employee_performance.router import router as employee_performance_router
from modules.item_trends.router import router as item_trends_router
from modules.data_management.router import router as data_management_router
from modules.demand_forecasting.router import router as forecast_router
from modules.realtime.router import router as realtime_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_run_startup_etl, daemon=True).start()
    threading.Thread(target=_run_periodic_etl, daemon=True).start()
    yield


app = FastAPI(
    title="BI Dashboard API",
    version="6.0.0",
    description="Retail BI Dashboard – Sales, Profit, Inventory, Forecasting & Employee Performance with Real-time Metrics",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # [LOCAL] localhost URLs
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        # [CLOUD - COMMENTED OUT] Vercel deployment URLs
        # "https://bi-dashboard-green.vercel.app",
        # "https://*.vercel.app",  # Wildcard for all Vercel preview URLs
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register all routers ───────────────────────────────────────
app.include_router(auth_router)
app.include_router(sale_profit_router)
app.include_router(employee_performance_router)
app.include_router(item_trends_router,    prefix="/trends")
app.include_router(data_management_router, prefix="/data")
app.include_router(forecast_router,        prefix="/forecast")
app.include_router(realtime_router,        prefix="/realtime")


def _run_startup_etl():
    """Run DB migration + aggregate tables in background."""
    try:
        from migrations.db_migration import run_migration
        run_migration()
        logger.info("DB migration completed.")
    except Exception as exc:
        logger.warning("DB migration skipped: %s", exc)

    try:
        from migrations.etl_pipeline import create_aggregate_tables
        logger.info("Building aggregate KPI tables…")
        create_aggregate_tables()
    except Exception as exc:
        logger.warning("Aggregate table build skipped: %s", exc)


def _run_periodic_etl():
    """Auto-trigger aggregate ETL every 30 seconds.
    Refreshes aggregate KPI tables from retails_dataset fact tables.
    Runs as a daemon thread so it never blocks the API server.
    """
    import time as _time
    ETL_INTERVAL = 300  # 5 minutes — aggregate refresh interval
    _time.sleep(ETL_INTERVAL)  # Wait before first run (startup ETL already ran)
    while True:
        try:
            logger.info("Periodic ETL: starting incremental sync…")
            from migrations.etl_pipeline import run_etl
            run_etl()
            from modules.sale_profit.service import refresh_sales_profit_cache, clear_all_caches
            clear_all_caches()
            refresh_sales_profit_cache()
            logger.info("Periodic ETL: completed successfully.")
        except Exception as exc:
            logger.warning("Periodic ETL failed (non-critical): %s", exc)
        _time.sleep(ETL_INTERVAL)


if __name__ == "__main__":
    from core.config import API_HOST, API_PORT
    uvicorn.run("main:app", host=API_HOST, port=API_PORT, reload=True)
