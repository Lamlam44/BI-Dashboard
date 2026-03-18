"""
Quick start guide and testing utilities.
"""

import sys
from pathlib import Path
import json

# Add project to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_imports():
    """Test that all modules can be imported successfully."""
    print("Testing imports...")
    
    try:
        from data.data_loader import load_raw_data, prepare_sales_data
        print("✓ data_loader imported")
        
        from data.feature_engineering import create_all_features
        print("✓ feature_engineering imported")
        
        from models.forecasting_model import DemandForecastingModel
        print("✓ forecasting_model imported")
        
        from app.main import app
        print("✓ FastAPI app imported")
        
        print("\nAll imports successful!\n")
        return True
    
    except ImportError as e:
        print(f"✗ Import failed: {e}\n")
        return False


def test_config():
    """Test configuration settings."""
    print("Testing configuration...")
    
    try:
        import config
        
        print(f"Project root: {config.PROJECT_ROOT}")
        print(f"Data directory: {config.DATA_DIR}")
        print(f"FactSales path: {config.FACT_SALES_PATH}")
        print(f"Model params: {json.dumps(config.MODEL_PARAMS, indent=2)}")
        print(f"Lag days: {config.LAG_DAYS}")
        print(f"Rolling mean days: {config.ROLLING_MEAN_DAYS}")
        
        print("\nConfiguration looks good!\n")
        return True
    
    except Exception as e:
        print(f"✗ Configuration test failed: {e}\n")
        return False


def test_data_files():
    """Check if data files exist."""
    print("Testing data files...")
    
    try:
        import config
        
        files_to_check = [
            config.FACT_SALES_PATH,
            config.DIM_PRODUCT_PATH,
            config.DIM_DATE_PATH
        ]
        
        all_exist = True
        for file_path in files_to_check:
            if file_path.exists():
                size_mb = file_path.stat().st_size / (1024 * 1024)
                print(f"✓ {file_path.name} ({size_mb:.1f} MB)")
            else:
                print(f"✗ {file_path.name} NOT FOUND")
                all_exist = False
        
        print()
        return all_exist
    
    except Exception as e:
        print(f"✗ Data file check failed: {e}\n")
        return False


def run_quick_start():
    """Run quick start tests."""
    print("=" * 60)
    print("AI Demand Forecasting - Quick Start Check")
    print("=" * 60)
    print()
    
    # Run tests
    imports_ok = test_imports()
    config_ok = test_config()
    data_ok = test_data_files()
    
    # Summary
    print("=" * 60)
    if imports_ok and config_ok and data_ok:
        print("✓ All checks passed! Ready to run.")
        print("\nTo start the API server, run:")
        print("  python run.py")
        print("\nTo run examples, run:")
        print("  python example.py")
        return 0
    else:
        print("✗ Some checks failed. Review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(run_quick_start())
