"""
Configuration settings for the Demand Forecasting module.
"""

from pathlib import Path

# Project root directory
PROJECT_ROOT = Path(__file__).parent

# Data is loaded from MySQL — no CSV paths needed



# Model parameters (tuned for 16GB RAM / i5 machines)
MODEL_PARAMS = {
    "n_estimators": 100,
    "max_depth": 8,
    "learning_rate": 0.1,
    "num_leaves": 31,
    "random_state": 42,
    "verbose": -1,
    "force_col_wise": True,   # lower memory than row-wise on small datasets
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
