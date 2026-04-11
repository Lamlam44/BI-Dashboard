import logging
import threading

from fastapi import APIRouter, HTTPException

from modules.data_management.analytics import router as analytics_router
from .service import build_customer_segments_cache, refresh_customer_segments_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["item-trends"])
router.include_router(analytics_router)


def _warm_cache_background() -> None:
    """Build customer segments cache in background on startup"""
    try:
        build_customer_segments_cache(force_refresh=False)
        logger.info("Item Trends cache warmup completed.")
    except Exception as exc:
        logger.warning(f"Item Trends cache warmup skipped: {exc}")


def startup_event():
    logger.info("Item Trends startup ready.")
    # Prime cache in background
    threading.Thread(target=_warm_cache_background, daemon=True).start()


startup_event()


@router.post("/cache/refresh")
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




