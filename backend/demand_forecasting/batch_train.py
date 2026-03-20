import pandas as pd
import numpy as np
import logging
import os
import joblib
from pathlib import Path
import lightgbm as lgb
from tqdm import tqdm

from data.data_loader import load_raw_data, prepare_sales_data, aggregate_daily_sales
from data.feature_engineering import create_all_features
from models.forecasting_model import DemandForecastingModel

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def train_global_model():
    print("=== STARTING GLOBAL MODEL BATCH TRAINING ===")
    
    # 1. Load data
    logger.info("Loading all dataset. This might take a while...")
    fact_sales, dim_product, dim_date = load_raw_data()
    
    # Clean up massive raw dataframe into a unified view
    global_df = prepare_sales_data(fact_sales, dim_product, dim_date)
    
    # Aggregate sales to daily level just like the API does
    logger.info("Aggregating to daily continuous product sales...")
    global_df = aggregate_daily_sales(global_df)
    
    # Add StoreKey if needed, ensuring ProductKey is present
    if "ProductKey" not in global_df.columns:
        raise ValueError("ProductKey is missing from data.")
    
    print(f"Global dataset loaded. Shape: {global_df.shape}. Number of unique products: {global_df['ProductKey'].nunique()}")
    
    # 2. Extract features without overlapping products
    # We must group by ProductKey so we don't accidentally compute "Rolling features" using Product A's sales for Product B's dates.
    logger.info("Engineering features per product to avoid data leakage...")
    
    # Sort by ProductKey and DateKey to ensure time series flows correctly
    global_df["DateKey"] = pd.to_datetime(global_df["DateKey"])
    global_df = global_df.sort_values(["ProductKey", "DateKey"])
    
    feature_dfs = []
    
    # Get top 200 products by volume to train faster and demonstrate (optional, but 2000+ will take mere minutes anyway for lightgbm)
    tqdm.pandas(desc="Processing Features")
    global_df = global_df.groupby("ProductKey", group_keys=False).apply(create_all_features)
    
    # We drop NAs because rolling means and lags create NaNs at the beginning of each product's timeline
    global_df = global_df.dropna()
    global_df = global_df.reset_index(drop=True)
    
    # Determine the train-test split temporally (e.g. last 30 days as test)
    # LightGBM handles large splits natively, we will pass everything to `.fit` via our `forecasting_model`
    
    target_col = "SalesQuantity"
    
    # Use the official feature_engineering getter to ensure complete match with API
    from data.feature_engineering import get_feature_columns
    feature_columns = get_feature_columns(global_df)
    
    # Remove any completely non-numeric columns that slipped through
    numeric_cols = set(global_df.select_dtypes(include=[np.number, bool]).columns)
    feature_columns = [col for col in feature_columns if col in numeric_cols]
    
    logger.info(f"Feature columns: {feature_columns}")

    # Ensure DateKey is datetime
    global_df['DateKey'] = pd.to_datetime(global_df['DateKey'])
    
    # Sort entirely by DateKey to let `prepare_training_data` do an 80/20 train/test split purely based on time
    logger.info("Sorting fully by DateKey for temporal training...")
    global_df = global_df.sort_values("DateKey")
    
    # 4. Initialize and train model
    model = DemandForecastingModel()
    
    logger.info(f"Target count: {len(global_df)}. Beginning fit with 3 Quantiles. Features: {len(feature_columns)}")
    
    metrics = model.train(
        features_df=global_df,
        feature_columns=feature_columns,
        target_col=target_col,
        product_id="GLOBAL_BATCH_ID" # Signal that it's all products
    )
    
    print("\n=== Model Metrics ===")
    print(metrics)
    
    # 5. Save the 3 brains
    model_dir = Path("saved_models")
    model_dir.mkdir(exist_ok=True)
    
    model_path = model_dir / "global_demand_model.pkl"
    model.save(str(model_path))
    
    print(f"\n✅ FULL WORKFLOW COMPLETE! Model saved as 3 components in '{model_path}'")

if __name__ == "__main__":
    train_global_model()
