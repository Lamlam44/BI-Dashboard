"""
README for the AI Demand Forecasting Module
"""

# AI Demand Forecasting Module

A production-ready FastAPI backend for demand forecasting using the Microsoft Contoso dataset with LightGBM.

## Project Structure

```
demand_forecasting/
├── app/
│   ├── __init__.py
│   └── main.py              # FastAPI application
├── data/
│   ├── __init__.py
│   ├── data_loader.py       # Data loading and processing
│   └── feature_engineering.py # Feature engineering
├── models/
│   ├── __init__.py
│   └── forecasting_model.py # LightGBM model wrapper
├── config.py                # Configuration settings
├── requirements.txt         # Python dependencies
├── run.py                   # Entry point
└── README.md
```

## Features

### Data Processing
- **CSV Loading**: Loads FactSales, DimProduct, and DimDate from Contoso dataset
- **Data Merging**: Intelligently merges dimension and fact tables
- **Daily Aggregation**: Aggregates sales data to daily granularity by product
- **Missing Date Handling**: Fills gaps with zero sales

### Feature Engineering
- **Lag Features**: 7, 14, and 30-day lags on sales quantity
- **Rolling Statistics**: 7-day rolling mean and standard deviation
- **Calendar Features**:
  - Day of week
  - Month, Quarter, Week number
  - Day of month
  - Weekend indicator
  - Day of month

### Machine Learning Model
- **Algorithm**: LightGBM Regressor
- **Training**: Time-series train/test split (80/20)
- **Predictions**: Point estimates + confidence bounds (95%)
- **Metrics**: RMSE, MAPE, Feature Importance

### API Endpoints
- `GET /health` - Health check
- `GET /products` - List available products (paginated)
- `POST /train/{product_id}` - Train model for a product
- `GET /forecast/{product_id}` - Get forecast with bounds
- `GET /forecast-latest/{product_id}` - Get latest forecast with metadata
- `GET /docs` - Swagger API documentation
- `GET /redoc` - ReDoc API documentation

## Installation

1. Create a virtual environment:
```bash
python -m venv venv
source venv/Scripts/activate  # Windows
# or
source venv/bin/activate      # Unix
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

Edit `config.py` to customize:
- Model parameters (LightGBM hyperparameters)
- Feature engineering parameters (lag days, rolling window)
- Data paths
- API settings

## Running the Application

```bash
python run.py
```

The API will be available at `http://localhost:8000`

API documentation available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## API Usage Examples

### 1. Check Health
```bash
curl http://localhost:8000/health
```

### 2. List Products
```bash
curl "http://localhost:8000/products?limit=5"
```

### 3. Train Model for a Product
```bash
curl -X POST http://localhost:8000/train/100
```

Response includes training metrics like RMSE and MAPE.

### 4. Get Forecast
```bash
curl "http://localhost:8000/forecast/100?days_ahead=7"
```

Response includes:
- Historical actual values
- Predicted values
- Upper and lower confidence bounds

### 5. Get Latest Forecast
```bash
curl "http://localhost:8000/forecast-latest/100?forecast_length=30"
```

## Data Format

### Forecast Response
```json
{
  "product_id": 100,
  "product_name": "Product Name",
  "forecast_points": [
    {
      "date": "2024-01-01",
      "actual": 150.5,
      "predicted": 152.3,
      "upper_bound": 180.1,
      "lower_bound": 124.5
    }
  ]
}
```

## Key Design Decisions

1. **Modular Architecture**: Separate modules for data, features, and models enable easy testing and maintenance.

2. **Feature Engineering Flexibility**: Calendar features are extracted to capture seasonal patterns common in demand.

3. **Confidence Intervals**: Predictions include bounds based on model uncertainty estimation.

4. **Time-Series Validation**: Uses historical train/test split for proper time-series validation.

5. **Data Caching**: Loads data once at startup for performance.

6. **Error Handling**: Comprehensive logging and HTTP exceptions for debugging.

## Performance Considerations

- **Data Loading**: Optimized for the Contoso dataset size (~100MB)
- **Feature Creation**: Vectorized operations using pandas/numpy
- **Model Training**: LightGBM is efficient for large datasets
- **Predictions**: In-memory model for sub-second latency

## Future Enhancements

- Model serialization (save/load trained models)
- Batch forecasting for multiple products
- Anomaly detection for unusual patterns
- Automated retraining scheduler
- Model comparison (compare LightGBM vs ARIMA, Prophet, etc.)
- Missing history imputation methods
- External regressors (holidays, promotions, competitor activity)

## Troubleshooting

**Data not found**: Verify the CSV files exist in `BI_Datasets/` directory.

**Model not trained**: Call `/train/{product_id}` before requesting forecasts.

**Insufficient data**: Some products may have fewer than 30 observations; increase the threshold in `config.py`.

**Memory issues**: Reduce data processing in batches or implement streaming.

## License

This module is part of the BI Dashboard project.
