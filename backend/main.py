import logging
import os
import sys
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(current_dir / "demand_forecasting"))
sys.path.insert(0, str(current_dir / "data_management"))
sys.path.insert(0, str(current_dir / "item_trends"))
sys.path.insert(0, str(current_dir / "employee_performance"))
sys.path.insert(0, str(current_dir / "realtime"))
os.chdir(current_dir)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from auth_api import router as auth_router
from data_management.main import app as data_app
from demand_forecasting.app.main import app as forecast_app
from item_trends.main import app as trends_app
from employee_performance.api import router as employee_performance_router
from sale_profit.api import router as sale_profit_router
from realtime.main import app as realtime_app

app = FastAPI(
    title="BI Dashboard API",
    version="5.0.0",
    description="Retail BI Dashboard – Sales, Profit, Inventory, Forecasting & Employee Performance with Real-time Metrics",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://bi-dashboard-green.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.mount("/realtime", realtime_app)
app.mount("/data", data_app)
app.mount("/forecast", forecast_app)
app.mount("/trends", trends_app)
app.include_router(auth_router)
app.include_router(employee_performance_router)
app.include_router(sale_profit_router)


def _run_startup_etl():
    """Run DB migration + aggregate tables in background."""
    try:
        from db_migration import run_migration
        run_migration()
        logger.info("DB migration completed.")
    except Exception as exc:
        logger.warning("DB migration skipped: %s", exc)

    try:
        from etl_pipeline import create_aggregate_tables
        logger.info("Building aggregate KPI tables…")
        create_aggregate_tables()
    except Exception as exc:
        logger.warning("Aggregate table build skipped: %s", exc)


@app.on_event("startup")
async def on_startup():
    threading.Thread(target=_run_startup_etl, daemon=True).start()


@app.get("/")
def root():
    return {
        "message": "BI Dashboard Backend is running.",
        "version": "5.0.0",
        "services": {
            "auth": "/auth",
            "realtime": "/realtime",
            "data_management": "/data",
            "demand_forecasting": "/forecast",
            "item_trends": "/trends",
            "employee_performance": "/employee-performance",
            "sale_profit": "/sale-profit",
        },
    }


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    print("=" * 60)
    print("  BI Dashboard Backend v5.0.0")
    print("  API: http://0.0.0.0:8000")
    print("  Docs: http://0.0.0.0:8000/docs")
    print("=" * 60)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
