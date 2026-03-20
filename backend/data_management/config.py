import os
from pathlib import Path

# Project root directory
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT.parent.parent / "BI_Datasets"
BACKUP_DIR = PROJECT_ROOT / "backups"
SCHEMA_FILE = PROJECT_ROOT / "schema_config.json"

# Ensure dirs exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

API_HOST = "0.0.0.0"
API_PORT = 8001
