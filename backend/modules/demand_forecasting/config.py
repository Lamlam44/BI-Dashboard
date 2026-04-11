"""
Configuration settings for the Demand Forecasting module.
"""

from pathlib import Path

# Project root directory
PROJECT_ROOT = Path(__file__).parent

# Data is loaded from MySQL â€” no CSV paths needed



# Model parameters â€” XGBoost (tuned for 16GB RAM / i5 machines)
# Migration note: num_leaves â†’ max_depth, force_col_wise removed, verbose â†’ verbosity
MODEL_PARAMS = {
    "n_estimators": 100,
    "max_depth": 8,
    "learning_rate": 0.1,
    "random_state": 42,
    "verbosity": 0,
    "tree_method": "hist",        # fast histogram-based (equivalent to LGBM default)
    "n_jobs": -1,                 # use all cores
}

# Feature engineering parameters
LAG_DAYS = [7, 14, 30]
ROLLING_MEAN_DAYS = 7
TRAIN_TEST_SPLIT = 0.8

# API settings
API_HOST = "0.0.0.0"
API_PORT = 8000

# Snapshot settings for management-by-exception endpoints.
# Keep parquet build bounded on very large warehouses.
PARQUET_LOOKBACK_DAYS = 120

