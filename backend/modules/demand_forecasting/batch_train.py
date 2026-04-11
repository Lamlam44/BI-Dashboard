import pandas as pd
import numpy as np
import logging
import os
import gc
import joblib
from pathlib import Path
from tqdm import tqdm

from modules.demand_forecasting.data.data_loader import (
    load_raw_data,
    prepare_sales_data,
    aggregate_daily_sales,
    ensure_parquet_cache,
    DAILY_SNAPSHOT_FILE,
)
from modules.demand_forecasting.data.feature_engineering import create_all_features
from modules.demand_forecasting.models.forecasting_model import DemandForecastingModel

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# â”€â”€ Memory-safe configuration for 16 GB RAM machines â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
MAX_PRODUCTS = 500          # Limit to top N products by sales volume
CHUNK_SIZE = 50             # Process features in chunks of N products


def _load_daily_data() -> pd.DataFrame:
    """
    Load daily product-level sales data.
    
    Strategy (memory-safe):
      1. Prefer Parquet cache (~190K rows, ~29 MB) â€” instant & zero MySQL load.
      2. Fallback: build Parquet cache from summary_daily_sales table.
      3. Last resort: load_raw_data() â†’ aggregate (slow, high RAM).
    """
    # â”€â”€ 1. Try Parquet cache first â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if DAILY_SNAPSHOT_FILE.exists():
        logger.info("Loading data from Parquet cache (memory-safe)â€¦")
        df = pd.read_parquet(DAILY_SNAPSHOT_FILE)
        if len(df) > 0:
            logger.info(f"Parquet cache loaded: {len(df):,} rows, {df['ProductKey'].nunique()} products")
            return df

    # â”€â”€ 2. Build Parquet cache from DB â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    logger.info("Parquet cache not found. Building from databaseâ€¦")
    try:
        ensure_parquet_cache(force_refresh=True)
        df = pd.read_parquet(DAILY_SNAPSHOT_FILE)
        if len(df) > 0:
            logger.info(f"Parquet cache built: {len(df):,} rows")
            return df
    except Exception as exc:
        logger.warning("Parquet cache build failed: %s", exc)

    # â”€â”€ 3. Last resort: raw load + aggregate â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    logger.info("Falling back to raw data load (high memory)â€¦")
    fact_sales, dim_product, dim_date = load_raw_data()
    global_df = prepare_sales_data(fact_sales, dim_product, dim_date)
    # Free raw data immediately
    del fact_sales, dim_product, dim_date
    gc.collect()
    global_df = aggregate_daily_sales(global_df)
    return global_df


def train_global_model():
    print("=== STARTING GLOBAL MODEL BATCH TRAINING ===")
    
    # 1. Load data (memory-safe)
    logger.info("Loading daily sales dataâ€¦")
    global_df = _load_daily_data()

    # Keep only columns needed for training
    keep_cols = ["DateKey", "ProductKey", "ProductName",
                 "SalesQuantity", "SalesAmount", "UnitPrice", "DiscountAmount"]
    available = [c for c in keep_cols if c in global_df.columns]
    global_df = global_df[available].copy()

    # Ensure DiscountAmount exists
    if "DiscountAmount" not in global_df.columns:
        global_df["DiscountAmount"] = 0.0

    gc.collect()
    
    if "ProductKey" not in global_df.columns:
        raise ValueError("ProductKey is missing from modules.demand_forecasting.data.")
    
    # 2. Limit to top N products by volume to bound memory & training time
    product_volume = (
        global_df.groupby("ProductKey")["SalesQuantity"]
        .sum()
        .sort_values(ascending=False)
    )
    top_products = product_volume.head(MAX_PRODUCTS).index
    global_df = global_df[global_df["ProductKey"].isin(top_products)].copy()
    gc.collect()

    print(f"Dataset: {global_df.shape[0]:,} rows, {global_df['ProductKey'].nunique()} products (top {MAX_PRODUCTS})")
    print(f"Memory usage: {global_df.memory_usage(deep=True).sum() / (1024**2):.1f} MB")
    
    # 3. Feature engineering â€” process in chunks to limit peak RAM
    logger.info("Engineering features per product (chunked)â€¦")
    global_df["DateKey"] = pd.to_datetime(global_df["DateKey"])
    global_df = global_df.sort_values(["ProductKey", "DateKey"])

    unique_products = global_df["ProductKey"].unique()
    feature_chunks = []

    for i in range(0, len(unique_products), CHUNK_SIZE):
        chunk_keys = unique_products[i:i + CHUNK_SIZE]
        chunk_df = global_df[global_df["ProductKey"].isin(chunk_keys)].copy()
        chunk_df = chunk_df.groupby("ProductKey", group_keys=False).apply(create_all_features)
        feature_chunks.append(chunk_df)

        if (i // CHUNK_SIZE) % 5 == 0:
            gc.collect()

    global_df = pd.concat(feature_chunks, ignore_index=True)
    del feature_chunks
    gc.collect()

    # Drop NAs from rolling/lag creation
    global_df = global_df.dropna().reset_index(drop=True)
    
    # 4. Prepare features
    target_col = "SalesQuantity"
    
    from modules.demand_forecasting.data.feature_engineering import get_feature_columns
    feature_columns = get_feature_columns(global_df)
    
    numeric_cols = set(global_df.select_dtypes(include=[np.number, bool]).columns)
    feature_columns = [col for col in feature_columns if col in numeric_cols]
    
    logger.info(f"Feature columns ({len(feature_columns)}): {feature_columns}")

    global_df['DateKey'] = pd.to_datetime(global_df['DateKey'])
    global_df = global_df.sort_values("DateKey")
    
    print(f"Training data: {len(global_df):,} rows Ã— {len(feature_columns)} features")
    print(f"RAM before training: {global_df.memory_usage(deep=True).sum() / (1024**2):.1f} MB")

    # 5. Train model
    model = DemandForecastingModel()
    
    metrics = model.train(
        features_df=global_df,
        feature_columns=feature_columns,
        target_col=target_col,
        product_id="GLOBAL_BATCH_ID"
    )
    
    # Free training data
    del global_df
    gc.collect()

    print("\n=== Model Metrics ===")
    print(metrics)

    # 6. Save model
    base_dir = Path(__file__).parent
    model_dir = base_dir / "saved_models"
    model_dir.mkdir(exist_ok=True)

    model_path = model_dir / "global_demand_model.pkl"
    model.save(str(model_path))

    print(f"\nâœ… FULL WORKFLOW COMPLETE! Model saved to '{model_path}'")

if __name__ == "__main__":
    train_global_model()

