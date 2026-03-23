import os
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(current_dir / "demand_forecasting"))
sys.path.insert(0, str(current_dir / "data_management"))
sys.path.insert(0, str(current_dir / "item_trends"))
os.chdir(current_dir)

from data_management.main import app as data_app
from demand_forecasting.app.main import app as forecast_app
from item_trends.main import app as trends_app

app = FastAPI(title="Unified BI Dashboard API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/data", data_app)
app.mount("/forecast", forecast_app)
app.mount("/trends", trends_app)


@app.get("/")
def root():
    return {
        "message": "Unified BI Dashboard Backend is running.",
        "services": {
            "data_management": "/data",
            "demand_forecasting": "/forecast",
            "item_trends": "/trends",
        },
    }


if __name__ == "__main__":
    print("=== Starting Unified BI Dashboard Backend (Single Port) ===")
    print("Unified API: http://0.0.0.0:8000")
    print("Data Management: http://0.0.0.0:8000/data")
    print("Demand Forecasting: http://0.0.0.0:8000/forecast")
    print("Item Trends: http://0.0.0.0:8000/trends")
    print("=" * 58)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
