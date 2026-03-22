import uvicorn
import sys
import os
import threading
from pathlib import Path

# Thêm thư mục vào sys.path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(current_dir / "demand_forecasting"))
sys.path.insert(0, str(current_dir / "data_management"))
sys.path.insert(0, str(current_dir / "item_trends"))

# Thay đổi working directory
os.chdir(current_dir)

def run_data_app():
    """Run data management app on port 8001"""
    try:
        from data_management.main import app
        uvicorn.run(app, host="0.0.0.0", port=8001, reload=False, log_level="info")
    except Exception as e:
        print(f"Error running data app: {e}")

def run_forecast_app():
    """Run demand forecasting app on port 8002"""
    try:
        from demand_forecasting.app.main import app
        uvicorn.run(app, host="0.0.0.0", port=8002, reload=False, log_level="info")
    except Exception as e:
        print(f"Error running forecast app: {e}")

def run_item_trends_app():
    """Run item trends app on port 8003"""
    try:
        from item_trends.main import app
        uvicorn.run(app, host="0.0.0.0", port=8003, reload=False, log_level="info")
    except Exception as e:
        print(f"Error running item trends app: {e}")

if __name__ == "__main__":
    print("=== Starting Unified BI Dashboard Backend ===")
    print("Data Management API: http://0.0.0.0:8001")
    print("Demand Forecasting API: http://0.0.0.0:8002")
    print("Item Trends API: http://0.0.0.0:8003")
    print("=" * 50)
    
    # Start sub-apps in separate threads
    data_thread = threading.Thread(target=run_data_app, daemon=True)
    forecast_thread = threading.Thread(target=run_forecast_app, daemon=True)
    item_trends_thread = threading.Thread(target=run_item_trends_app, daemon=True)
    
    data_thread.start()
    forecast_thread.start()
    item_trends_thread.start()
    
    import time
    # Keep main thread alive
    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
