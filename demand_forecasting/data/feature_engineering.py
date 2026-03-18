"""
Feature Engineering module for time series data.
Creates lag features, rolling statistics, and calendar features.
"""

import pandas as pd
import numpy as np
from typing import List
import logging
from config import LAG_DAYS, ROLLING_MEAN_DAYS

logger = logging.getLogger(__name__)


def create_lag_features(
    product_ts: pd.DataFrame,
    lag_days: List[int] = None,
    target_col: str = "SalesQuantity"
) -> pd.DataFrame:
    """
    Create lag features for time series data.
    
    Args:
        product_ts: Time series DataFrame
        lag_days: List of lag periods (default: [7, 14, 30])
        target_col: Column name to create lags from
    
    Returns:
        DataFrame with lag features added
    """
    if lag_days is None:
        lag_days = LAG_DAYS
    
    try:
        features = product_ts.copy()
        
        for lag in lag_days:
            col_name = f"{target_col}_lag_{lag}"
            features[col_name] = features[target_col].shift(lag)
            logger.debug(f"Created {col_name}")
        
        return features
    
    except Exception as e:
        logger.error(f"Error creating lag features: {e}")
        raise


def create_rolling_features(
    product_ts: pd.DataFrame,
    window: int = None,
    target_col: str = "SalesQuantity"
) -> pd.DataFrame:
    """
    Create rolling mean features for time series data.
    
    Args:
        product_ts: Time series DataFrame
        window: Rolling window size (default: 7)
        target_col: Column name to compute rolling stats from
    
    Returns:
        DataFrame with rolling features added
    """
    if window is None:
        window = ROLLING_MEAN_DAYS
    
    try:
        features = product_ts.copy()
        
        # Rolling mean
        col_name = f"{target_col}_rolling_mean_{window}"
        features[col_name] = features[target_col].rolling(
            window=window,
            min_periods=1
        ).mean()
        logger.debug(f"Created {col_name}")
        
        # Rolling std (optional but useful)
        col_name_std = f"{target_col}_rolling_std_{window}"
        features[col_name_std] = features[target_col].rolling(
            window=window,
            min_periods=1
        ).std()
        logger.debug(f"Created {col_name_std}")
        
        return features
    
    except Exception as e:
        logger.error(f"Error creating rolling features: {e}")
        raise


def create_calendar_features(
    product_ts: pd.DataFrame,
    date_col: str = "DateKey"
) -> pd.DataFrame:
    """
    Extract calendar features from date column.
    
    Args:
        product_ts: Time series DataFrame with DateKey column
        date_col: Column name containing dates
    
    Returns:
        DataFrame with calendar features added
    """
    try:
        features = product_ts.copy()
        
        # Ensure DateKey is datetime
        if not pd.api.types.is_datetime64_any_dtype(features[date_col]):
            features[date_col] = pd.to_datetime(features[date_col])
        
        # Day of week (0=Monday, 6=Sunday)
        features["day_of_week"] = features[date_col].dt.dayofweek
        logger.debug("Created day_of_week")
        
        # Month
        features["month"] = features[date_col].dt.month
        logger.debug("Created month")
        
        # Quarter
        features["quarter"] = features[date_col].dt.quarter
        logger.debug("Created quarter")
        
        # Day of month
        features["day_of_month"] = features[date_col].dt.day
        logger.debug("Created day_of_month")
        
        # Week number
        features["week_of_year"] = features[date_col].dt.isocalendar().week
        logger.debug("Created week_of_year")
        
        # Is weekend (Saturday=5, Sunday=6)
        features["is_weekend"] = (
            features["day_of_week"].isin([5, 6]).astype(int)
        )
        logger.debug("Created is_weekend")
        
        return features
    
    except Exception as e:
        logger.error(f"Error creating calendar features: {e}")
        raise


def create_all_features(
    product_ts: pd.DataFrame,
    target_col: str = "SalesQuantity",
    date_col: str = "DateKey",
    exogenous_cols: List[str] = None
) -> pd.DataFrame:
    """
    Create all features: lags, rolling means, and calendar features for target and exogenous variables.
    
    Args:
        product_ts: Time series DataFrame
        target_col: Target column for lag and rolling features
        date_col: Date column for calendar features
        exogenous_cols: Exogenous variable columns to create features for (default: ["UnitPrice", "DiscountAmount"])
    
    Returns:
        DataFrame with all engineered features
    """
    try:
        if exogenous_cols is None:
            exogenous_cols = ["UnitPrice", "DiscountAmount"]
        
        logger.info("Creating all features...")
        
        # Create lag features for target
        features = create_lag_features(product_ts, target_col=target_col)
        
        # Create lag features for exogenous variables
        for exo_col in exogenous_cols:
            if exo_col in features.columns:
                features = create_lag_features(
                    features,
                    lag_days=LAG_DAYS,
                    target_col=exo_col
                )
                logger.debug(f"Created lag features for {exo_col}")
        
        # Create rolling features for target
        features = create_rolling_features(features, target_col=target_col)
        
        # Create rolling features for exogenous variables
        for exo_col in exogenous_cols:
            if exo_col in features.columns:
                features = create_rolling_features(
                    features,
                    window=ROLLING_MEAN_DAYS,
                    target_col=exo_col
                )
                logger.debug(f"Created rolling features for {exo_col}")
        
        # Create calendar features
        features = create_calendar_features(features, date_col=date_col)
        
        logger.info(f"Total features created: {features.shape[1]}")
        
        return features
    
    except Exception as e:
        logger.error(f"Error creating all features: {e}")
        raise


def prepare_model_data(
    features_df: pd.DataFrame,
    target_col: str = "SalesQuantity",
    min_lag_periods: int = 30
) -> pd.DataFrame:
    """
    Prepare data for model training by removing rows with NaN values
    created by lagging operations.
    
    Args:
        features_df: Features DataFrame
        target_col: Target column
        min_lag_periods: Rows to drop to account for lag creation
    
    Returns:
        Clean DataFrame ready for modeling
    """
    try:
        model_data = features_df.copy()
        
        # Drop rows with NaN values created by lagging
        initial_rows = len(model_data)
        model_data = model_data.dropna(subset=[
            f"{target_col}_lag_{lag}" for lag in LAG_DAYS
        ])
        
        rows_dropped = initial_rows - len(model_data)
        logger.info(f"Dropped {rows_dropped} rows with NaN lag features")
        
        return model_data
    
    except Exception as e:
        logger.error(f"Error preparing model data: {e}")
        raise


def get_feature_columns(features_df: pd.DataFrame) -> List[str]:
    """
    Get list of feature columns (excluding metadata and target).
    Automatically includes lag, rolling, and calendar features for both
    target and exogenous variables.
    
    Args:
        features_df: Features DataFrame
    
    Returns:
        List of feature column names
    """
    exclude_cols = {
        "DateKey", "ProductKey", "ProductName",
        "SalesQuantity", "SalesAmount",
        "UnitPrice", "DiscountAmount"
    }
    
    feature_cols = [
        col for col in features_df.columns
        if col not in exclude_cols
    ]
    
    logger.info(f"Selected {len(feature_cols)} feature columns: {feature_cols}")
    
    return feature_cols
