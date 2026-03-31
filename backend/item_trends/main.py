import logging
import sys
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

current_dir = Path(__file__).parent
backend_root = current_dir.parent
sys.path.insert(0, str(backend_root))

from data_management.analytics import router as analytics_router
from it_cache import build_customer_segments_cache, refresh_customer_segments_cache

try:
    from it_config import API_HOST, API_PORT
except ImportError:
    from .it_config import API_HOST, API_PORT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="BI Item Trends API")
app.include_router(analytics_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _warm_cache_background() -> None:
    """Build customer segments cache in background on startup"""
    try:
        build_customer_segments_cache(force_refresh=False)
        logger.info("Item Trends cache warmup completed.")
    except Exception as exc:
        logger.warning(f"Item Trends cache warmup skipped: {exc}")


@app.on_event("startup")
async def startup_event():
    logger.info("Item Trends startup ready.")
    # Prime cache in background
    threading.Thread(target=_warm_cache_background, daemon=True).start()


@app.post("/cache/refresh")
async def refresh_cache():
    """Manually refresh customer segments cache"""
    try:
        result = refresh_customer_segments_cache()
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except Exception as e:
        logger.error(f"Error refreshing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("item_trends.main:app", host=API_HOST, port=API_PORT, reload=True)
