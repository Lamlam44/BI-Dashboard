"""
Configuration settings for the Demand Forecasting module.
"""

import os
from pathlib import Path

# Project root directory
PROJECT_ROOT = Path(__file__).parent

# Data directories
DATA_DIR = PROJECT_ROOT.parent / "BI_Datasets"
FACT_SALES_PATH = DATA_DIR / "FactSales.csv"
DIM_PRODUCT_PATH = DATA_DIR / "DimProduct.csv"
DIM_DATE_PATH = DATA_DIR / "DimDate.csv"

# Model parameters
MODEL_PARAMS = {
    "n_estimators": 100,
    "max_depth": 8,
    "learning_rate": 0.1,
    "num_leaves": 31,
    "random_state": 42,
}

# Feature engineering parameters
LAG_DAYS = [7, 14, 30]
ROLLING_MEAN_DAYS = 7
TRAIN_TEST_SPLIT = 0.8

# API settings
API_HOST = "0.0.0.0"
API_PORT = 8000
