import os
from pathlib import Path

# Project root directory
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT.parent.parent / "BI_Datasets"
SEGMENTS_FILE = PROJECT_ROOT / "Customer_Segments_Final.csv"

API_HOST = "0.0.0.0"
API_PORT = 8003
