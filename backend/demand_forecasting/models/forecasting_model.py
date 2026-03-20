"""
LightGBM Forecasting Model for demand forecasting with quantile regression.
Implements multi-model approach for point forecasts and confidence bounds.
Supports multi-step recursive forecasting.
"""

import pandas as pd
import numpy as np
import logging
from typing import Tuple, List, Dict, Optional
import lightgbm as lgb
import joblib
import sys
from pathlib import Path

# Ensure parent directory is in path for config import
sys.path.insert(0, str(Path(__file__).parent.parent))

from df_config import MODEL_PARAMS, TRAIN_TEST_SPLIT

logger = logging.getLogger(__name__)


class DemandForecastingModel:
    """
    LightGBM model for demand forecasting with quantile regression.
    
    Trains 3 separate models:
    - Base model: Point forecasts (regression)
    - Lower bound model: 5th percentile (quantile)
    - Upper bound model: 95th percentile (quantile)
    """
    
    def __init__(self, model_params: Dict = None):
        """
        Initialize the model.
        
        Args:
            model_params: LightGBM model parameters (uses defaults if None)
        """
        self.model_params = model_params or MODEL_PARAMS
        
        # Three separate models for quantile regression
        self.model_base = None  # Point forecast
        self.model_lower = None  # 5th percentile (lower bound)
        self.model_upper = None  # 95th percentile (upper bound)
        
        self.feature_columns = None
        self.is_trained = False
        self.last_training_product_id = None
        
        # Store scaling statistics for recursive forecasting
        self.feature_means = None
        self.feature_stds = None
    
    def prepare_training_data(
        self,
        features_df: pd.DataFrame,
        feature_columns: List[str],
        target_col: str = "SalesQuantity",
        train_size: float = TRAIN_TEST_SPLIT
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Prepare training and test data with proper temporal split.
        
        FIXED: Data leakage issue - split BEFORE any scaling operations.
        For tree-based models like LightGBM, scaling is not necessary.
        
        Args:
            features_df: DataFrame with features
            feature_columns: List of feature column names
            target_col: Target column name
            train_size: Fraction of data for training
        
        Returns:
            Tuple of (X_train, X_test, y_train, y_test)
        """
        try:
            # Extract features and target
            X = features_df[feature_columns].values
            y = features_df[target_col].values
            
            # Temporal train/test split (BEFORE any scaling)
            split_idx = int(len(X) * train_size)
            
            X_train = X[:split_idx]
            X_test = X[split_idx:]
            y_train = y[:split_idx]
            y_test = y[split_idx:]
            
            logger.info(f"Training set size: {len(X_train)}")
            logger.info(f"Test set size: {len(X_test)}")
            logger.info(f"Features used: {len(feature_columns)}")
            
            self.feature_columns = feature_columns
            
            return X_train, X_test, y_train, y_test
        
        except Exception as e:
            logger.error(f"Error preparing training data: {e}")
            raise
    
    def train(
        self,
        features_df: pd.DataFrame,
        feature_columns: List[str],
        target_col: str = "SalesQuantity",
        product_id: Optional[int] = None
    ) -> Dict:
        """
        Train quantile regression models (3 LightGBM models).
        
        ISSUE #3: Quantile Regression Implementation
        Trains three separate models:
        1. Base model: objective='regression' for point forecasts
        2. Lower bound: objective='quantile', alpha=0.05 for 5th percentile
        3. Upper bound: objective='quantile', alpha=0.95 for 95th percentile
        
        Args:
            features_df: DataFrame with features
            feature_columns: List of feature column names
            target_col: Target column name
            product_id: Product ID for logging (optional)
        
        Returns:
            Training results dictionary with metrics
        """
        try:
            logger.info(f"Training quantile regression models {'for product ' + str(product_id) if product_id else ''}...")
            
            # Prepare training/test data
            X_train, X_test, y_train, y_test = self.prepare_training_data(
                features_df,
                feature_columns,
                target_col
            )
            
            # ============ Model 1: Base Model (Point Forecast) ============
            logger.info("Training base model (point forecast)...")
            base_params = self.model_params.copy()
            base_params["objective"] = "regression"
            
            self.model_base = lgb.LGBMRegressor(**base_params)
            self.model_base.fit(X_train, y_train, eval_set=[(X_test, y_test)], eval_metric="rmse")
            
            base_pred_train = self.model_base.predict(X_train)
            base_pred_test = self.model_base.predict(X_test)
            
            # ============ Model 2: Lower Bound Model (5th Percentile) ============
            logger.info("Training lower bound model (5th percentile)...")
            lower_params = self.model_params.copy()
            lower_params["objective"] = "quantile"
            lower_params["alpha"] = 0.05
            
            self.model_lower = lgb.LGBMRegressor(**lower_params)
            self.model_lower.fit(X_train, y_train, eval_set=[(X_test, y_test)], eval_metric="quantile")
            
            lower_pred_train = self.model_lower.predict(X_train)
            lower_pred_test = self.model_lower.predict(X_test)
            
            # ============ Model 3: Upper Bound Model (95th Percentile) ============
            logger.info("Training upper bound model (95th percentile)...")
            upper_params = self.model_params.copy()
            upper_params["objective"] = "quantile"
            upper_params["alpha"] = 0.95
            
            self.model_upper = lgb.LGBMRegressor(**upper_params)
            self.model_upper.fit(X_train, y_train, eval_set=[(X_test, y_test)], eval_metric="quantile")
            
            upper_pred_train = self.model_upper.predict(X_train)
            upper_pred_test = self.model_upper.predict(X_test)
            
            # ============ Calculate Metrics ============
            base_train_rmse = np.sqrt(np.mean((base_pred_train - y_train) ** 2))
            base_test_rmse = np.sqrt(np.mean((base_pred_test - y_test) ** 2))
            
            base_train_mape = np.mean(
                np.abs((y_train - base_pred_train) / np.maximum(np.abs(y_train), 1e-8))
            ) * 100
            base_test_mape = np.mean(
                np.abs((y_test - base_pred_test) / np.maximum(np.abs(y_test), 1e-8))
            ) * 100
            
            # Calculate interval score (how well bounds capture actual values)
            interval_width = np.mean(upper_pred_test - lower_pred_test)
            coverage = np.mean((y_test >= lower_pred_test) & (y_test <= upper_pred_test))
            
            self.is_trained = True
            self.last_training_product_id = product_id
            
            results = {
                "train_rmse": float(np.clip(base_train_rmse, 0, 1e6)),
                "test_rmse": float(np.clip(base_test_rmse, 0, 1e6)),
                "train_mape": float(np.clip(base_train_mape, 0, 100000)),
                "test_mape": float(np.clip(base_test_mape, 0, 100000)),
                "interval_width": float(interval_width),
                "interval_coverage": float(coverage),
                "base_feature_importance": {
                    col: float(imp)
                    for col, imp in zip(feature_columns, self.model_base.feature_importances_)
                }
            }
            
            logger.info(f"Training complete. Base Test RMSE: {base_test_rmse:.4f}, MAPE: {base_test_mape:.2f}%")
            logger.info(f"Interval Coverage: {coverage:.2%}, Avg Width: {interval_width:.2f}")
            
            return results
        
        except Exception as e:
            logger.error(f"Error training models: {e}")
            raise
    
    def predict(self, features_df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Make predictions using all three quantile models.
        
        Args:
            features_df: DataFrame with features matching training features
        
        Returns:
            Tuple of (base_predictions, lower_bound, upper_bound)
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before making predictions")
        
        try:
            # Extract features
            X = features_df[self.feature_columns].values
            
            # Get predictions from all three models
            base_pred = self.model_base.predict(X)
            lower_pred = self.model_lower.predict(X)
            upper_pred = self.model_upper.predict(X)
            
            # Ensure bounds are valid
            lower_pred = np.minimum(lower_pred, base_pred)
            upper_pred = np.maximum(upper_pred, base_pred)
            lower_pred = np.maximum(lower_pred, 0)  # No negative sales
            
            return base_pred, lower_pred, upper_pred
        
        except Exception as e:
            logger.error(f"Error making predictions: {e}")
            raise
    
    def predict_with_bounds(
        self,
        features_df: pd.DataFrame
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Make predictions with confidence bounds (wrapper for predict).
        
        Args:
            features_df: DataFrame with features
        
        Returns:
            Tuple of (predictions, upper_bound, lower_bound)
        """
        return self.predict(features_df)
    
    def predict_future(
        self,
        current_data_df: pd.DataFrame,
        n_steps: int = 7
    ) -> pd.DataFrame:
        """
        ISSUE #4: Multi-step Recursive Forecasting Implementation
        
        Recursively forecast n steps ahead by:
        1. Making a 1-step ahead prediction
        2. Appending the prediction to create new features
        3. Recalculating lag and rolling features
        4. Repeating for n_steps
        
        Args:
            current_data_df: Current product data with all features
            n_steps: Number of steps to forecast ahead
        
        Returns:
            DataFrame with recursive forecasts and bounds
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before forecasting")
        
        try:
            logger.info(f"Forecasting {n_steps} steps ahead (recursive)...")
            
            # Make a working copy
            future_data = current_data_df.copy()
            forecasts = []
            
            # Import feature engineering functions
            from data.feature_engineering import create_all_features
            
            for step in range(n_steps):
                # Get the last row to use for prediction
                last_row = future_data[self.feature_columns].iloc[-1:].values
                
                # Make prediction
                base_forecast = self.model_base.predict(last_row)[0]
                lower_bound = self.model_lower.predict(last_row)[0]
                upper_bound = self.model_upper.predict(last_row)[0]
                
                # Get the last date
                last_date = pd.to_datetime(future_data["DateKey"].iloc[-1])
                next_date = last_date + pd.Timedelta(days=1)
                
                # Create raw record for the new day
                new_record = {
                    "DateKey": next_date,
                    "SalesQuantity": base_forecast,
                    "SalesAmount": base_forecast * 10,  # Rough estimate
                    "UnitPrice": future_data["UnitPrice"].iloc[-1],  # Use last known price
                    "DiscountAmount": 0.0,
                    "ProductKey": future_data["ProductKey"].iloc[0] if "ProductKey" in future_data else 0,
                    "ProductName": future_data["ProductName"].iloc[0] if "ProductName" in future_data else "Unknown"
                }
                
                # Keep only raw columns to recreate all features properly
                raw_columns = ["DateKey", "ProductKey", "ProductName", "SalesQuantity", "SalesAmount", "UnitPrice", "DiscountAmount"]
                available_raw_cols = [col for col in raw_columns if col in future_data.columns]
                raw_future_data = future_data[available_raw_cols].copy()
                
                # Append to raw future data
                new_row = pd.DataFrame([new_record])
                raw_future_data = pd.concat([raw_future_data, new_row], ignore_index=True)
                
                # Recreate all features automatically (lag, rolling, calendar) for all target and exogenous vars
                future_data = create_all_features(raw_future_data)
                
                logger.debug(f"Step {step+1}/{n_steps}: Forecasted {base_forecast:.2f} (bounds: [{lower_bound:.2f}, {upper_bound:.2f}])")
                
                # Store the forecast
                forecasts.append({
                    "DateKey": next_date,
                    "SalesQuantity": base_forecast,
                    "predicted": base_forecast,
                    "lower_bound": lower_bound,
                    "upper_bound": upper_bound
                })
            
            # Build forecast dataframe
            forecast_df = pd.DataFrame(forecasts)

            
            logger.info(f"Recursive forecasting complete for {n_steps} steps")
            
            return forecast_df
        
        except Exception as e:
            logger.error(f"Error in recursive forecasting: {e}")
            raise
    def save(self, filepath: str):
        """Save the 3 models (base, lower, upper) and feature definitions to disk."""
        if not self.is_trained:
            logger.warning("Attempted to save an untrained model.")
            return

        model_data = {
            "model_base": self.model_base,
            "model_lower": self.model_lower,
            "model_upper": self.model_upper,
            "feature_columns": self.feature_columns,
            "last_training_product_id": self.last_training_product_id
        }
        
        joblib.dump(model_data, filepath)
        logger.info(f"💾 Model successfully saved to {filepath}")

    @classmethod
    def load(cls, filepath: str) -> "DemandForecastingModel":
        """Load the model definitions from disk."""
        model_data = joblib.load(filepath)
        
        instance = cls()
        instance.model_base = model_data["model_base"]
        instance.model_lower = model_data["model_lower"]
        instance.model_upper = model_data["model_upper"]
        instance.feature_columns = model_data["feature_columns"]
        instance.last_training_product_id = model_data.get("last_training_product_id", "GLOBAL")
        instance.is_trained = True
        
        logger.info(f"📂 Model successfully loaded from {filepath}")
        return instance
