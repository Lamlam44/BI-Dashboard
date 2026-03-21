"""
FastAPI application for Demand Forecasting.
Provides endpoints for product demand forecasting.
"""

import logging
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
    load_raw_data,
    prepare_sales_data,
    aggregate_daily_sales,
    get_product_time_series,
    fill_missing_dates
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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global model and data storage
model = None
daily_sales = None
available_products = None


# Pydantic models for API responses
class ForecastPoint(BaseModel):
    """Single forecast data point."""
    date: str
    actual: float
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


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize data on application startup."""
    global daily_sales, available_products, model
    try:
        logger.info("Starting up - Loading data...")
        
        # Load raw data
        fact_sales, dim_product, dim_date = load_raw_data()
        
        # Prepare sales data
        sales_data = prepare_sales_data(fact_sales, dim_product, dim_date)
        
        # Aggregate to daily level
        daily_sales = aggregate_daily_sales(sales_data)
        
        # Get list of available products
        available_products = daily_sales["ProductKey"].unique().tolist()
        
        logger.info(f"Data loaded successfully!")
        logger.info(f"Available products: {len(available_products)}")

        # Try to load pre-trained global model
        model_path = Path(__file__).parent.parent / "saved_models" / "global_demand_model.pkl"
        try:
            model = DemandForecastingModel.load(str(model_path))
            logger.info(f"✅ Global Model loaded successfully from {model_path}.")
        except Exception as e:
            model = DemandForecastingModel()
            logger.warning(f"⚠️ Could not load Global Model from {model_path}, it will run in On-Demand mode: {e}")
            
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise


# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "model_trained": model.is_trained,
        "data_loaded": daily_sales is not None
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
        if daily_sales is None:
            raise HTTPException(status_code=503, detail="Data not loaded")
        
        products = daily_sales.groupby("ProductKey").agg({
            "ProductName": "first",
            "SalesQuantity": ["sum", "mean", "max"]
        }).head(limit)
        
        result = []
        for idx, row in products.iterrows():
            result.append({
                "product_id": int(idx),
                "product_name": row[("ProductName", "first")],
                "total_quantity": float(row[("SalesQuantity", "sum")]),
                "avg_daily_quantity": float(row[("SalesQuantity", "mean")]),
                "max_daily_quantity": float(row[("SalesQuantity", "max")])
            })
        
        return {"products": result}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing products: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/refresh-ai-data")
async def refresh_ai_data():
    """Refreshes the in-memory data and Retrains the global model from the latest CSV"""
    global daily_sales, available_products, model
    try:
        logger.info("Triggering data refresh and AI retraining...")
        
        # This will reload files, train, and save to .pkl overwriting the old one
        train_global_model()
        
        # After successful train and save, we must update our in-memory global vars
        # Load raw data
        fact_sales, dim_product, dim_date = load_raw_data()
        
        # Prepare sales data
        sales_data = prepare_sales_data(fact_sales, dim_product, dim_date)
        
        # Aggregate to daily level
        daily_sales = aggregate_daily_sales(sales_data)
        
        # Get list of available products
        available_products = daily_sales["ProductKey"].unique().tolist()
        
        # Reload model
        model_path = Path(__file__).parent.parent / "saved_models" / "global_demand_model.pkl"
        model = DemandForecastingModel.load(str(model_path))
        
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
        if daily_sales is None:
            raise HTTPException(status_code=503, detail="Data not loaded")
        
        logger.info(f"Training request for product {product_id}")
        
        # Get product time series
        product_ts = get_product_time_series(daily_sales, product_id)
        if product_ts is None:
            raise HTTPException(
                status_code=404,
                detail=f"Product {product_id} not found or insufficient data"
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
        if daily_sales is None:
            raise HTTPException(status_code=503, detail="Data not loaded")
        
        if not model.is_trained:
            raise HTTPException(
                status_code=400,
                detail=f"Model not trained. Call /train/{product_id} first"
            )
        
        logger.info(f"Forecast request for product {product_id}, {days_ahead} days")
        
        # Get product time series
        product_ts = get_product_time_series(daily_sales, product_id)
        if product_ts is None:
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
        
        # Make predictions with bounds
        predictions, upper_bounds, lower_bounds = model.predict_with_bounds(
            features_df
        )
        
        # Build forecast response
        forecast_points = []
        for idx, row in features_df.iterrows():
            forecast_points.append(ForecastPoint(
                date=row["DateKey"].strftime("%Y-%m-%d"),
                actual=float(row["SalesQuantity"]),
                predicted=float(predictions[idx]),
                upper_bound=float(upper_bounds[idx]),
                lower_bound=float(lower_bounds[idx])
            ))
        
        # Return last days_ahead points
        return ForecastResponse(
            product_id=product_id,
            product_name=product_ts["ProductName"].iloc[0],
            forecast_points=forecast_points[-days_ahead:]
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
        if daily_sales is None:
            raise HTTPException(status_code=503, detail="Data not loaded")
        
        if not model.is_trained:
            raise HTTPException(
                status_code=400,
                detail=f"Model not trained. Call /train/{product_id} first"
            )
        
        # Get product time series
        product_ts = get_product_time_series(daily_sales, product_id)
        if product_ts is None:
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
        
        # Make predictions
        predictions, upper_bounds, lower_bounds = model.predict_with_bounds(
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
