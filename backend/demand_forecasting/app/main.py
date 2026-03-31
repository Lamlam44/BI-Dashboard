"""
FastAPI application for Demand Forecasting.
Provides endpoints for product demand forecasting.
"""

import logging
import threading
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
import pandas as pd
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.data_loader import (
    fill_missing_dates,
    load_product_time_series_from_parquet,
    load_products_summary_from_db,
    ensure_parquet_cache,
    load_overview_from_parquet,
    load_alerts_from_parquet,
    query_bulk_from_parquet,
    DAILY_SNAPSHOT_FILE,
    ABC_XYZ_FILE,
    get_snapshot_row_count,
)
from data.feature_engineering import (
    create_all_features,
    prepare_model_data,
    get_feature_columns
)
from models.forecasting_model import DemandForecastingModel
import df_config as config
from batch_train import train_global_model

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="AI Demand Forecasting API",
    description="Demand forecasting API using LightGBM",
    version="1.0.0"
)

# Add CORS middleware
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

# Global model and data storage
model = None
init_error = None
init_started = False
_init_lock = threading.Lock()
_cache_build_lock = threading.Lock()
_cache_building = False
_recalculate_running = False


# Pydantic models for API responses
class ForecastPoint(BaseModel):
    """Single forecast data point."""
    date: str
    actual: Optional[float]
    predicted: float
    upper_bound: float
    lower_bound: float


class ForecastResponse(BaseModel):
    """Forecast API response."""
    product_id: int
    product_name: str
    forecast_points: List[ForecastPoint]


class ModelMetrics(BaseModel):
    """Model training metrics."""
    train_rmse: float
    test_rmse: float
    train_mape: float
    test_mape: float


class TrainingResponse(BaseModel):
    """Model training response."""
    product_id: int
    status: str
    metrics: ModelMetrics
    message: str


def initialize_forecasting_assets(force_reload: bool = False):
    global model, init_error, init_started

    with _init_lock:
        if model is not None and not force_reload:
            return

        if not force_reload and init_started and init_error is None and model is not None:
            return

        init_started = True
        init_error = None

        try:
            logger.info("Starting up - Loading forecast model...")

            model_path = Path(__file__).parent.parent / "saved_models" / "global_demand_model.pkl"
            try:
                model = DemandForecastingModel.load(str(model_path))
                logger.info(f"✅ Global Model loaded successfully from {model_path}.")
            except Exception as model_error:
                model = DemandForecastingModel()
                logger.warning(
                    f"⚠️ Could not load Global Model from {model_path}, it will run in On-Demand mode: {model_error}"
                )

            # Build parquet snapshots in background-friendly path to avoid heavy raw loads at runtime.
            ensure_parquet_cache(force_refresh=force_reload)
        except Exception as e:
            init_error = str(e)
            logger.error(f"Error during startup: {e}")


def _start_background_initialization():
    worker = threading.Thread(target=initialize_forecasting_assets, daemon=True)
    worker.start()


def _start_background_cache_build():
    global _cache_building

    if DAILY_SNAPSHOT_FILE.exists() and ABC_XYZ_FILE.exists() and get_snapshot_row_count() > 0:
        return

    with _cache_build_lock:
        if _cache_building:
            return
        _cache_building = True

    def _worker():
        global _cache_building
        try:
            ensure_parquet_cache(force_refresh=False)
        except Exception as e:
            logger.error(f"Background parquet cache build failed: {e}")
        finally:
            with _cache_build_lock:
                _cache_building = False

    threading.Thread(target=_worker, daemon=True).start()


def ensure_cache_ready():
    if DAILY_SNAPSHOT_FILE.exists() and ABC_XYZ_FILE.exists() and get_snapshot_row_count() > 0:
        return

    _start_background_cache_build()
    raise HTTPException(
        status_code=503,
        detail="Parquet cache is initializing. Please retry in a moment.",
    )


@app.on_event("startup")
async def startup_event():
    """Delay heavy forecasting initialization until first readiness/data request."""
    logger.info("Forecast startup deferred; initialization will run lazily.")


def ensure_initialized():
    if model is None:
        initialize_forecasting_assets()

    if init_error:
        raise HTTPException(status_code=500, detail=f"Initialization failed: {init_error}")


# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "model_trained": bool(model and model.is_trained),
        "data_loaded": True,
        "initializing": model is None,
        "init_error": init_error,
    }


@app.get("/ready")
async def readiness_check():
    """Readiness endpoint for frontend polling before expensive forecast calls."""
    if model is None and not init_started:
        _start_background_initialization()

    cache_ready = DAILY_SNAPSHOT_FILE.exists() and ABC_XYZ_FILE.exists() and get_snapshot_row_count() > 0

    return {
        "ready": cache_ready,
        "data_loaded": True,
        "model_loaded": model is not None,
        "cache_ready": cache_ready,
        "cache_rows": get_snapshot_row_count(),
        "cache_building": _cache_building,
        "recalculate_running": _recalculate_running,
        "initializing": model is None,
        "init_error": init_error,
    }


@app.get("/products")
async def list_products(limit: int = Query(10, ge=1, le=100)):
    """
    Get list of available products.
    
    Args:
        limit: Maximum number of products to return
    
    Returns:
        List of product information
    """
    try:
        ensure_initialized()

        products = load_products_summary_from_db(limit=limit)

        result = []
        for _, row in products.iterrows():
            result.append({
                "product_id": int(row["ProductKey"]),
                "product_name": row["ProductName"],
                "total_quantity": float(row["total_quantity"]),
                "avg_daily_quantity": float(row["avg_daily_quantity"]),
                "max_daily_quantity": float(row["max_daily_quantity"])
            })
        
        return {"products": result}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing products: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/overview")
async def forecast_overview(horizon_days: int = Query(14, ge=1, le=60)):
    try:
        ensure_cache_ready()
        return load_overview_from_parquet(horizon_days=horizon_days)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading overview: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/alerts")
async def forecast_alerts(
    limit: int = Query(20, ge=1, le=200),
    abc_class: str = Query("A", pattern="^[ABC]$"),
):
    try:
        ensure_cache_ready()
        return {"alerts": load_alerts_from_parquet(limit=limit, abc_class=abc_class)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/bulk/query")
async def forecast_bulk_query(
    abc_class: Optional[str] = Query(None, pattern="^[ABC]$"),
    xyz_class: Optional[str] = Query(None, pattern="^[XYZ]$"),
    category_key: Optional[int] = Query(None, ge=0),
    limit: int = Query(200, ge=1, le=5000),
):
    try:
        ensure_cache_ready()
        rows = query_bulk_from_parquet(
            abc_class=abc_class,
            xyz_class=xyz_class,
            category_key=category_key,
            limit=limit,
        )
        return {"count": len(rows), "items": rows}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/recalculate")
async def recalculate_cache():
    global _recalculate_running

    try:
        ensure_initialized()

        if _recalculate_running:
            return {"status": "running", "message": "Recalculate is already in progress"}

        def _recalculate_worker():
            global _recalculate_running
            try:
                ensure_parquet_cache(force_refresh=True)
            except Exception as e:
                logger.error(f"Background recalculate failed: {e}")
            finally:
                _recalculate_running = False

        _recalculate_running = True
        threading.Thread(target=_recalculate_worker, daemon=True).start()
        return {"status": "accepted", "message": "Recalculate started in background"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recalculating cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/refresh-ai-data")
async def refresh_ai_data():
    """Refresh in-memory data and retrain global model from MySQL warehouse."""
    global model
    try:
        logger.info("Triggering data refresh and AI retraining...")
        
        ensure_initialized()

        # This will reload files, train, and save to .pkl overwriting the old one
        train_global_model()
        
        # Reload latest model artifact after retrain.
        initialize_forecasting_assets(force_reload=True)
        
        return {"status": "success", "message": "Tiến trình đồng bộ và Train lại Mô hình AI thành công. Đã ghi đè file .pkl."}
    
    except Exception as e:
        logger.error(f"Error during refresh: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/train/{product_id}")
async def train_model(product_id: int):
    """
    Train the forecasting model for a specific product.
    
    Args:
        product_id: Product ID to train on
    
    Returns:
        Training results and metrics
    """
    try:
        ensure_initialized()
        
        logger.info(f"Training request for product {product_id}")
        
        # Get product time series (on-demand from DB to avoid full RAM preload).
        product_ts = load_product_time_series_from_parquet(product_id)
        if product_ts.empty:
            raise HTTPException(
                status_code=404,
                detail=f"Product {product_id} not found or insufficient data"
            )

        if len(product_ts) < 30:
            raise HTTPException(
                status_code=404,
                detail=f"Product {product_id} has insufficient data (minimum: 30 observations)"
            )
        
        # Fill missing dates
        product_ts = fill_missing_dates(product_ts)
        
        # Create features
        features_df = create_all_features(product_ts)
        
        # Prepare model data
        model_data = prepare_model_data(features_df)
        
        # Get feature columns
        feature_cols = get_feature_columns(model_data)
        
        # Train model
        results = model.train(model_data, feature_cols, product_id=product_id)
        
        return TrainingResponse(
            product_id=product_id,
            status="success",
            metrics=ModelMetrics(**results),
            message=f"Model trained successfully for product {product_id}"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error training model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/forecast/{product_id}")
async def forecast(product_id: int, days_ahead: int = Query(7, ge=1, le=30)):
    """
    Get demand forecast for a specific product.
    
    Args:
        product_id: Product ID to forecast
        days_ahead: Number of days to forecast ahead
    
    Returns:
        Forecast with actual, predicted, upper and lower bounds
    """
    try:
        ensure_initialized()
        
        if not model.is_trained:
            raise HTTPException(
                status_code=400,
                detail=f"Model not trained. Call /train/{product_id} first"
            )
        
        logger.info(f"Forecast request for product {product_id}, {days_ahead} days")
        
        product_ts = load_product_time_series_from_parquet(product_id)
        if product_ts.empty:
            raise HTTPException(
                status_code=404,
                detail=f"Product {product_id} not found"
            )
        
        # Fill missing dates
        product_ts = fill_missing_dates(product_ts)
        
        # Create features
        features_df = create_all_features(product_ts)
        
        # Generate true future horizon using recursive forecasting.
        forecast_df = model.predict_future(features_df, n_steps=days_ahead)

        forecast_points = []
        for _, row in forecast_df.iterrows():
            forecast_points.append(ForecastPoint(
                date=pd.to_datetime(row["DateKey"]).strftime("%Y-%m-%d"),
                actual=None,
                predicted=float(row["predicted"]),
                upper_bound=float(row["upper_bound"]),
                lower_bound=float(row["lower_bound"])
            ))

        return ForecastResponse(
            product_id=product_id,
            product_name=product_ts["ProductName"].iloc[0],
            forecast_points=forecast_points
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating forecast: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/forecast-latest/{product_id}")
async def forecast_latest(
    product_id: int,
    forecast_length: int = Query(30, ge=1, le=90)
):
    """
    Get the latest forecast including historical accuracy metrics.
    
    Args:
        product_id: Product ID to forecast
        forecast_length: Length of forecast to return
    
    Returns:
        Latest forecast points with metadata
    """
    try:
        ensure_initialized()
        
        if not model.is_trained:
            raise HTTPException(
                status_code=400,
                detail=f"Model not trained. Call /train/{product_id} first"
            )
        
        product_ts = load_product_time_series_from_parquet(product_id)
        if product_ts.empty:
            raise HTTPException(
                status_code=404,
                detail=f"Product {product_id} not found"
            )
        
        # Fill missing dates
        product_ts = fill_missing_dates(product_ts)
        
        # Create features
        features_df = create_all_features(product_ts)
        
        # Get feature columns
        feature_cols = get_feature_columns(features_df)
        
        # Make in-sample predictions for accuracy inspection view.
        predictions, lower_bounds, upper_bounds = model.predict_with_bounds(
            features_df
        )
        
        # Build response with latest forecast
        result = {
            "product_id": product_id,
            "product_name": product_ts["ProductName"].iloc[0],
            "model_info": {
                "trained_for_product": model.last_training_product_id,
                "is_trained": model.is_trained
            },
            "forecast": []
        }
        
        # Get last forecast_length points
        start_idx = max(0, len(features_df) - forecast_length)
        for idx in range(start_idx, len(features_df)):
            row = features_df.iloc[idx]
            result["forecast"].append({
                "date": row["DateKey"].strftime("%Y-%m-%d"),
                "actual": float(row["SalesQuantity"]),
                "predicted": float(predictions[idx]),
                "upper_bound": float(upper_bounds[idx]),
                "lower_bound": float(lower_bounds[idx])
            })
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating latest forecast: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "AI Demand Forecasting API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "products": "/products",
            "train": "/train/{product_id}",
            "forecast": "/forecast/{product_id}",
            "forecast_latest": "/forecast-latest/{product_id}",
            "docs": "/docs",
            "redoc": "/redoc"
        }
    }
