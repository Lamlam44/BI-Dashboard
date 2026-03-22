"""
Data loading module for the Demand Forecasting system.
Handles loading and merging FactSales, DimProduct, and DimDate datasets.
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional
import logging
from df_config import FACT_SALES_PATH, DIM_PRODUCT_PATH, DIM_DATE_PATH

logger = logging.getLogger(__name__)


def load_raw_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load raw data from CSV files.
    
    Returns:
        Tuple containing:
        - fact_sales: FactSales DataFrame
        - dim_product: DimProduct DataFrame
        - dim_date: DimDate DataFrame
    """
    try:
        logger.info("Loading FactSales data...")
        fact_sales = pd.read_csv(FACT_SALES_PATH)
        
        logger.info("Loading DimProduct data...")
        dim_product = pd.read_csv(DIM_PRODUCT_PATH)
        
        logger.info("Loading DimDate data...")
        dim_date = pd.read_csv(DIM_DATE_PATH)
        
        logger.info(f"FactSales shape: {fact_sales.shape}")
        logger.info(f"DimProduct shape: {dim_product.shape}")
        logger.info(f"DimDate shape: {dim_date.shape}")
        
        return fact_sales, dim_product, dim_date
    
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        raise


def prepare_sales_data(
    fact_sales: pd.DataFrame,
    dim_product: pd.DataFrame,
    dim_date: pd.DataFrame
) -> pd.DataFrame:
    """
    Merge and prepare sales data from fact and dimension tables.
    
    Args:
        fact_sales: FactSales DataFrame
        dim_product: DimProduct DataFrame
        dim_date: DimDate DataFrame
    
    Returns:
        Merged and prepared sales DataFrame
    """
    try:
        # Create copies to avoid modifying original data
        sales = fact_sales.copy()
        products = dim_product[["ProductKey", "ProductName", "UnitPrice"]].copy()
        dates = dim_date.copy()
        
        # Ensure DateKey is string for merging
        dates["DateKey"] = pd.to_datetime(dates["DateKey"])
        sales["DateKey"] = pd.to_datetime(sales["DateKey"])

        # Merge with product information
        sales = sales.merge(
            products,
            left_on="ProductKey",
            right_on="ProductKey",
            how="left",
            suffixes=('', '_dim')
        )
        
        # Resolve column names when merging created duplicates
        if "UnitPrice_dim" in sales.columns:
            # Prefer the UnitPrice from DimProduct if conflicting
            sales["UnitPrice"] = sales["UnitPrice_dim"].fillna(sales.get("UnitPrice_x", sales.get("UnitPrice", 0)))
            sales = sales.drop(columns=["UnitPrice_dim", "UnitPrice_x", "UnitPrice_y"], errors="ignore")
        elif "UnitPrice_x" in sales.columns:
            sales["UnitPrice"] = sales["UnitPrice_x"]
            sales = sales.drop(columns=["UnitPrice_x", "UnitPrice_y"], errors="ignore")

        # Merge with date information
        sales = sales.merge(
            dates,
            left_on="DateKey",
            right_on="DateKey",
            how="left"
        )
        
        # Điền tên cho các sản phẩm không có trong DimProduct (như 915)
        sales["ProductName"] = sales["ProductName"].fillna("Unknown Product " + sales["ProductKey"].astype(str))

        # Sort by ProductKey and DateKey
        sales = sales.sort_values(by=["ProductKey", "DateKey"]).reset_index(drop=True)
        
        logger.info(f"Prepared sales data shape: {sales.shape}")
        
        return sales
    
    except Exception as e:
        logger.error(f"Error preparing sales data: {e}")
        raise


def aggregate_daily_sales(sales_data: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate sales data to daily level by product with exogenous variables.
    
    Args:
        sales_data: Prepared sales DataFrame
    
    Returns:
        Daily aggregated sales DataFrame with columns:
        - DateKey: Date
        - ProductKey: Product ID
        - ProductName: Product name
        - SalesQuantity: Total quantity sold
        - SalesAmount: Total sales amount
        - UnitPrice: Mean unit price
        - DiscountAmount: Total discount applied
    """
    try:
        daily_sales = sales_data.groupby(
            ["DateKey", "ProductKey", "ProductName"]
        ).agg({
            "SalesQuantity": "sum",
            "SalesAmount": "sum",
            "UnitPrice": "mean",
            "DiscountAmount": "sum"
        }).reset_index()
        
        # Handle missing DiscountAmount column gracefully
        if "DiscountAmount" not in daily_sales.columns:
            daily_sales["DiscountAmount"] = 0.0
        
        daily_sales = daily_sales.sort_values(
            by=["ProductKey", "DateKey"]
        ).reset_index(drop=True)
        
        logger.info(f"Aggregated daily sales shape: {daily_sales.shape}")
        logger.info(f"Columns: {daily_sales.columns.tolist()}")
        
        return daily_sales
    
    except Exception as e:
        logger.error(f"Error aggregating daily sales: {e}")
        raise


def get_product_time_series(
    daily_sales: pd.DataFrame,
    product_id: int,
    min_observations: int = 30
) -> Optional[pd.DataFrame]:
    """
    Extract time series for a specific product.
    
    Args:
        daily_sales: Daily aggregated sales DataFrame
        product_id: Product key/ID
        min_observations: Minimum number of observations required
    
    Returns:
        Time series DataFrame for the product, or None if insufficient data
    """
    try:
        product_ts = daily_sales[
            daily_sales["ProductKey"] == product_id
        ].copy().reset_index(drop=True)
        
        if len(product_ts) < min_observations:
            logger.warning(
                f"Product {product_id} has only {len(product_ts)} observations "
                f"(minimum required: {min_observations})"
            )
            return None
        
        return product_ts
    
    except Exception as e:
        logger.error(f"Error extracting product time series: {e}")
        raise


def fill_missing_dates(
    product_ts: pd.DataFrame
) -> pd.DataFrame:
    """
    Fill missing dates in product time series with zero sales.
    
    Args:
        product_ts: Time series DataFrame for a product
    
    Returns:
        Time series with all dates and zero-filled missing values
    """
    try:
        # Set DateKey as index
        product_ts = product_ts.set_index("DateKey")
        
        # Create complete date range
        date_range = pd.date_range(
            start=product_ts.index.min(),
            end=product_ts.index.max(),
            freq="D"
        )
        
        # Reindex to include all dates
        product_ts = product_ts.reindex(date_range)
        product_ts["DateKey"] = product_ts.index
        
        # Fill missing values for target and exogenous variables
        product_ts["SalesQuantity"] = product_ts["SalesQuantity"].fillna(0)
        product_ts["SalesAmount"] = product_ts["SalesAmount"].fillna(0)
        product_ts["UnitPrice"] = product_ts["UnitPrice"].fillna(
            product_ts["UnitPrice"].mean()
        )
        product_ts["DiscountAmount"] = product_ts["DiscountAmount"].fillna(0)
        
        # Fill categorical columns
        product_ts["ProductKey"] = product_ts["ProductKey"].fillna(
            product_ts["ProductKey"].iloc[0]
        )
        product_ts["ProductName"] = product_ts["ProductName"].fillna(
            product_ts["ProductName"].iloc[0]
        )
        
        product_ts = product_ts.reset_index(drop=True)
        
        return product_ts
    
    except Exception as e:
        logger.error(f"Error filling missing dates: {e}")
        raise
