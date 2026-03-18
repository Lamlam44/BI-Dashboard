"""
Example script demonstrating how to use the demand forecasting module.
This can be run independently to test the data pipeline.
"""

import sys
from pathlib import Path

# Add the demand_forecasting directory to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

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
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def example_data_pipeline():
    """Example: Load and process data."""
    logger.info("=" * 60)
    logger.info("EXAMPLE 1: Data Loading and Processing")
    logger.info("=" * 60)
    
    # Load raw data
    fact_sales, dim_product, dim_date = load_raw_data()
    
    # Prepare sales data
    sales_data = prepare_sales_data(fact_sales, dim_product, dim_date)
    logger.info(f"\nMerged sales data shape: {sales_data.shape}")
    logger.info(f"Columns: {sales_data.columns.tolist()}")
    
    # Aggregate to daily level
    daily_sales = aggregate_daily_sales(sales_data)
    logger.info(f"\nDaily aggregated sales shape: {daily_sales.shape}")
    logger.info(f"\nSample of daily sales:")
    logger.info(daily_sales.head())
    
    return daily_sales


def example_feature_engineering(daily_sales):
    """Example: Create features for a specific product."""
    logger.info("\n" + "=" * 60)
    logger.info("EXAMPLE 2: Feature Engineering")
    logger.info("=" * 60)
    
    # Select a product with sufficient data
    product_id = daily_sales["ProductKey"].value_counts().index[0]
    logger.info(f"\nUsing product ID: {product_id}")
    
    # Get product time series
    product_ts = get_product_time_series(daily_sales, product_id)
    logger.info(f"Time series shape: {product_ts.shape}")
    logger.info(f"Date range: {product_ts['DateKey'].min()} to {product_ts['DateKey'].max()}")
    
    # Fill missing dates
    product_ts = fill_missing_dates(product_ts)
    logger.info(f"\nAfter filling missing dates: {product_ts.shape}")
    
    # Create all features
    features_df = create_all_features(product_ts)
    logger.info(f"\nFeatures shape: {features_df.shape}")
    
    # Get feature columns
    feature_cols = get_feature_columns(features_df)
    logger.info(f"Number of features: {len(feature_cols)}")
    logger.info(f"Feature columns: {feature_cols}")
    
    # Prepare model data
    model_data = prepare_model_data(features_df)
    logger.info(f"\nModel data shape (after removing NaN): {model_data.shape}")
    logger.info(f"\nSample of features:")
    logger.info(model_data[["DateKey", "SalesQuantity", "day_of_week", "month", "is_weekend"]].tail())
    
    return product_ts, features_df, model_data, feature_cols


def example_model_training(model_data, feature_cols):
    """Example: Train the forecasting model."""
    logger.info("\n" + "=" * 60)
    logger.info("EXAMPLE 3: Model Training")
    logger.info("=" * 60)
    
    # Initialize model
    model = DemandForecastingModel()
    logger.info("Model initialized")
    
    # Train model
    results = model.train(model_data, feature_cols)
    
    logger.info("\nTraining Results:")
    logger.info(f"  Train RMSE: {results['train_rmse']:.4f}")
    logger.info(f"  Test RMSE: {results['test_rmse']:.4f}")
    logger.info(f"  Train MAPE: {results['train_mape']:.2f}%")
    logger.info(f"  Test MAPE: {results['test_mape']:.2f}%")
    
    logger.info("\nTop 5 Most Important Features:")
    sorted_features = sorted(
        results['base_feature_importance'].items(),
        key=lambda x: x[1],
        reverse=True
    )
    for feature, importance in sorted_features[:5]:
        logger.info(f"  {feature}: {importance:.4f}")
    
    return model


def example_predictions(model, model_data):
    """Example: Make predictions with confidence bounds."""
    logger.info("\n" + "=" * 60)
    logger.info("EXAMPLE 4: Making Predictions")
    logger.info("=" * 60)
    
    # Make predictions with bounds
    predictions, lower_bounds, upper_bounds = model.predict_with_bounds(model_data)

    logger.info("\nSample In-Sample Predictions with Quantile Bounds:")
    logger.info("(Last 5 periods)")

    for i in range(-5, 0):
        actual = model_data["SalesQuantity"].iloc[i]
        pred = predictions[i]
        lower = lower_bounds[i]
        upper = upper_bounds[i]
        logger.info(
            f"  Actual: {actual:7.2f} | Predicted: {pred:7.2f} | "
            f"Bounds: [{lower:7.2f}, {upper:7.2f}]"
        )
        
    logger.info("\n" + "=" * 60)
    logger.info("EXAMPLE 5: Multi-Step Future Forecasting")
    logger.info("=" * 60)
    
    # Predict the next 14 days into the future
    future_steps = 14
    logger.info(f"Predicting {future_steps} days into the future recursively...")
    
    future_forecast = model.predict_future(model_data, n_steps=future_steps)
    
    logger.info("\nFuture Forecast Results:")
    for _, row in future_forecast.iterrows():
        date_str = row['DateKey'].strftime('%Y-%m-%d')
        pred = row['predicted']
        lower = row['lower_bound']
        upper = row['upper_bound']
        logger.info(
            f"  Date: {date_str} | Predicted: {pred:7.2f} | "
            f"Bounds: [{lower:7.2f}, {upper:7.2f}]"
        )
        
def main():
    """Run all examples."""
    try:
        # Example 1: Data Pipeline
        daily_sales = example_data_pipeline()
        product_ts, features_df, model_data, feature_cols = example_feature_engineering(
            daily_sales
        )
        
        # Example 3: Model Training
        model = example_model_training(model_data, feature_cols)
        
        # Example 4: Predictions
        example_predictions(model, model_data)
        
        logger.info("\n" + "=" * 60)
        logger.info("All examples completed successfully!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Example failed: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
