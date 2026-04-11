"""
Centralized configuration for BI Dashboard Backend.
All environment variables and shared settings are defined here.
"""

import os
from pathlib import Path

# ── Project Paths ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent  # backend/
FRONTEND_DIR = PROJECT_ROOT.parent / "frontend"


# ── BI Data Warehouse (Star Schema) ───────────────────────────
DW_HOST = os.getenv("DB_HOST", "127.0.0.1")
DW_PORT = int(os.getenv("DB_PORT", "3306"))
DW_USER = os.getenv("DB_USER", "root")
DW_PASSWORD = os.getenv("DB_PASSWORD", "12345")
DW_DATABASE = os.getenv("DB_NAME", "retails_dataset")

# ── Simulated POS System (Normalized Schema) ──────────────────
POS_HOST = os.getenv("POS_DB_HOST", "127.0.0.1")
POS_PORT = int(os.getenv("POS_DB_PORT", "3306"))
POS_USER = os.getenv("POS_DB_USER", "root")
POS_PASSWORD = os.getenv("POS_DB_PASSWORD", "12345")
POS_DATABASE = os.getenv("POS_DB_NAME", "pos_system")

# ── API Server ─────────────────────────────────────────────────
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# ── Cache Settings ─────────────────────────────────────────────
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL", "600"))       # 10 minutes
ANALYTICS_CACHE_TTL = int(os.getenv("ANALYTICS_CACHE_TTL", "900"))  # 15 minutes
