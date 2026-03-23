import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

current_dir = Path(__file__).parent
backend_root = current_dir.parent
sys.path.insert(0, str(backend_root))

from data_management.analytics import router as analytics_router
from db_migration import run_migration

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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    # Ensure indexes/views/summary table exist before serving analytics endpoints.
    run_migration()
    logger.info("Item Trends database migration checked.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("item_trends.main:app", host=API_HOST, port=API_PORT, reload=True)
