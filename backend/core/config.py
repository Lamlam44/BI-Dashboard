"""
Centralized configuration for BI Dashboard Backend.
All environment variables and shared settings are defined here.
"""

import os
from pathlib import Path

# ── Project Paths ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent  # backend/
FRONTEND_DIR = PROJECT_ROOT.parent / "frontend"


# ── BI Data Warehouse (CLOUD TiDB) ────────────────────────────
# [CLOUD] TiDB Cloud / Render setup
DW_HOST = os.getenv("DB_HOST", "gateway01.ap-southeast-1.prod.aws.tidbcloud.com")
DW_PORT = int(os.getenv("DB_PORT", "4000"))  # TiDB Cloud sử dụng port 4000
DW_USER = os.getenv("DB_USER", "3FhVda33nHpaura.root")
DW_PASSWORD = os.getenv("DB_PASSWORD", "8KbTcgZ9LmZOBIrI")
DW_DATABASE = os.getenv("DB_NAME", "retails_dataset")
# Cấu hình SSL (Bắt buộc cho TiDB Cloud Serverless)
DW_SSL_CA = os.getenv("SSL_CA_PATH", "/etc/ssl/certs/ca-certificates.crt")

# [LOCAL - COMMENTED OUT] Kết nối MySQL local
# DW_HOST = os.getenv("DB_HOST", "127.0.0.1")
# DW_PORT = int(os.getenv("DB_PORT", "3306"))
# DW_USER = os.getenv("DB_USER", "root")
# DW_PASSWORD = os.getenv("DB_PASSWORD", "12345")
# DW_DATABASE = os.getenv("DB_NAME", "retails_dataset")

# [LOCAL - COMMENTED OUT] Không dùng SSL cho MySQL local
# DW_SSL_CA = os.getenv("SSL_CA_PATH", "")

# ── API Server ─────────────────────────────────────────────────
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# ── Cache Settings ─────────────────────────────────────────────
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL", "600"))       # 10 minutes
ANALYTICS_CACHE_TTL = int(os.getenv("ANALYTICS_CACHE_TTL", "900"))  # 15 minutes

# ── Invoice Ingest API Key ──────────────────────────────────────
INGEST_API_KEY = os.getenv("INGEST_API_KEY", "bi-dashboard-ingest-key-2026")