from pathlib import Path

# Project root directory
PROJECT_ROOT = Path(__file__).parent
BACKUP_DIR = PROJECT_ROOT / "backups"
SCHEMA_FILE = PROJECT_ROOT / "schema_config.json"

# Ensure dirs exist
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

API_HOST = "0.0.0.0"
API_PORT = 8001

