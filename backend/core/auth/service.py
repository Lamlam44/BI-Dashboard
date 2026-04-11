"""
Authentication & Authorization service for BI Dashboard.

- JWT authentication (HS256, no external dependency)
- Password hashing (SHA-256 + salt)
- Role-based access control (RBAC)
- Row-level security (RLS) based on user role/region/store
"""

import hashlib
import hmac
import json
import base64
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────
JWT_SECRET = os.getenv("JWT_SECRET", "bi-dashboard-secret-key-change-in-prod")
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))

VALID_ROLES = ("executive", "regional_manager", "store_manager", "admin")


# ╔══════════════════════════════════════════════════════════════╗
# ║  PASSWORD HASHING                                            ║
# ╚══════════════════════════════════════════════════════════════╝

def hash_password(plain: str) -> str:
    """Create salt$hash from plain text."""
    salt = os.urandom(16).hex()
    h = hashlib.sha256(f"{salt}:{plain}".encode()).hexdigest()
    return f"{salt}${h}"


def verify_password(plain: str, stored: str) -> bool:
    """Verify plain text against salt$hash."""
    if "$" not in stored:
        return False
    salt, h = stored.split("$", 1)
    return hmac.compare_digest(
        hashlib.sha256(f"{salt}:{plain}".encode()).hexdigest(), h
    )


# ╔══════════════════════════════════════════════════════════════╗
# ║  JWT (lightweight, no PyJWT dependency)                      ║
# ╚══════════════════════════════════════════════════════════════╝

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padded = s + "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(padded)


def jwt_sign(payload: dict, secret: str) -> str:
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64url_encode(json.dumps(payload, default=str).encode())
    sig_input = f"{header}.{body}".encode()
    sig = _b64url_encode(
        hmac.new(secret.encode(), sig_input, hashlib.sha256).digest()
    )
    return f"{header}.{body}.{sig}"


def jwt_decode(token: str, secret: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format")
    header_b, body_b, sig_b = parts
    expected_sig = _b64url_encode(
        hmac.new(secret.encode(), f"{header_b}.{body_b}".encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected_sig, sig_b):
        raise ValueError("Invalid JWT signature")
    payload = json.loads(_b64url_decode(body_b))
    if payload.get("exp") and payload["exp"] < time.time():
        raise ValueError("JWT expired")
    return payload


def create_access_token(user: Dict[str, Any]) -> str:
    now = time.time()
    payload = {
        "sub": user["username"],
        "uid": user.get("id"),
        "role": user["role"],
        "region": user.get("region"),
        "store_key": user.get("store_key"),
        "display_name": user.get("display_name"),
        "iat": int(now),
        "exp": int(now + JWT_EXPIRY_HOURS * 3600),
    }
    return jwt_sign(payload, JWT_SECRET)


# ╔══════════════════════════════════════════════════════════════╗
# ║  DATABASE: bi_users table                                    ║
# ╚══════════════════════════════════════════════════════════════╝

def ensure_auth_tables(engine: Engine) -> None:
    """Create bi_users table if not exists, migrate schema, seed demo users."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS bi_users (
                id            INT AUTO_INCREMENT PRIMARY KEY,
                username      VARCHAR(100) NOT NULL UNIQUE,
                password_hash VARCHAR(200) NOT NULL,
                role          VARCHAR(50)  NOT NULL DEFAULT 'store_manager',
                region        VARCHAR(100) DEFAULT NULL,
                store_key     INT          DEFAULT NULL,
                employee_key  BIGINT       DEFAULT NULL,
                display_name  VARCHAR(200) DEFAULT '',
                is_active     TINYINT(1)   NOT NULL DEFAULT 1,
                created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
                updated_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """))

        # ── Schema migration for pre-existing tables ──
        cols = {r[0] for r in conn.execute(text("SHOW COLUMNS FROM bi_users")).fetchall()}
        if "hashed_password" in cols and "password_hash" not in cols:
            conn.execute(text(
                "ALTER TABLE bi_users CHANGE COLUMN hashed_password password_hash VARCHAR(200) NOT NULL"
            ))
            cols.discard("hashed_password")
            cols.add("password_hash")
        for col_name, col_def in [
            ("region", "VARCHAR(100) DEFAULT NULL"),
            ("store_key", "INT DEFAULT NULL"),
        ]:
            if col_name not in cols:
                conn.execute(text(f"ALTER TABLE bi_users ADD COLUMN {col_name} {col_def}"))

        # ── Re-hash legacy passwords (no salt$hash format) ──
        legacy = conn.execute(
            text("SELECT id, username FROM bi_users WHERE password_hash NOT LIKE :pat"),
            {"pat": "%$%"},
        ).fetchall()
        default_pw = {"admin": "admin123"}
        for row in legacy:
            pw = default_pw.get(row[1], "demo123")
            conn.execute(
                text("UPDATE bi_users SET password_hash = :p WHERE id = :id"),
                {"p": hash_password(pw), "id": row[0]},
            )

        # ── Seed demo users if table is empty or only has admin ──
        user_count = conn.execute(text("SELECT COUNT(*) FROM bi_users")).scalar()
        if user_count <= 1:
            demo_users = [
                ("admin",      "admin123", "admin",            None,            None, "System Administrator"),
                ("ceo",        "demo123",  "executive",        None,            None, "CEO / Ban Giám đốc"),
                ("rm_asia",    "demo123",  "regional_manager", "Asia",          None, "Regional Manager Asia"),
                ("rm_europe",  "demo123",  "regional_manager", "Europe",        None, "Regional Manager Europe"),
                ("rm_na",      "demo123",  "regional_manager", "North America", None, "Regional Manager NA"),
                ("sm_store4",  "demo123",  "store_manager",    None,            4,    "SM Contoso Bellevue"),
                ("sm_store156","demo123",  "store_manager",    None,            156,  "SM Contoso Cambridge"),
            ]
            for uname, pw, role, region, sk, dname in demo_users:
                conn.execute(text("""
                    INSERT IGNORE INTO bi_users
                        (username, password_hash, role, region, store_key, display_name)
                    VALUES (:u, :p, :r, :reg, :sk, :dn)
                """), {
                    "u": uname, "p": hash_password(pw), "r": role,
                    "reg": region, "sk": sk, "dn": dname,
                })

    logger.info("Auth tables ensured (bi_users).")


# ╔══════════════════════════════════════════════════════════════╗
# ║  AUTH OPERATIONS                                             ║
# ╚══════════════════════════════════════════════════════════════╝

def authenticate_user(engine: Engine, username: str, password: str) -> Optional[Dict[str, Any]]:
    """Verify credentials.  Returns user dict (without password) or None."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM bi_users WHERE username = :u AND is_active = 1"),
            {"u": username},
        ).mappings().first()
    if not row:
        return None
    user = dict(row)
    if not verify_password(password, user["password_hash"]):
        return None
    user.pop("password_hash", None)
    return user


# ╔══════════════════════════════════════════════════════════════╗
# ║  FASTAPI DEPENDENCY: get_current_user                        ║
# ╚══════════════════════════════════════════════════════════════╝

@dataclass
class UserContext:
    username: str
    uid: Optional[int]
    role: str
    region: Optional[str]
    store_key: Optional[int]
    display_name: Optional[str]
    is_anonymous: bool = False


def get_current_user(request: Request) -> UserContext:
    """FastAPI dependency — extracts user from Bearer token.
    Returns anonymous admin if no token (backwards-compatible).
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return UserContext(
            username="anonymous", uid=None, role="admin",
            region=None, store_key=None, display_name="Anonymous",
            is_anonymous=True,
        )
    token = auth_header[7:]
    try:
        payload = jwt_decode(token, JWT_SECRET)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return UserContext(
        username=payload.get("sub", ""),
        uid=payload.get("uid"),
        role=payload.get("role", "store_manager"),
        region=payload.get("region"),
        store_key=payload.get("store_key"),
        display_name=payload.get("display_name"),
    )


def require_roles(*roles: str):
    """FastAPI dependency factory — raise 403 if user not in allowed roles."""
    def _check(user: UserContext = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return _check


# ╔══════════════════════════════════════════════════════════════╗
# ║  ROW-LEVEL SECURITY (RLS)                                   ║
# ╚══════════════════════════════════════════════════════════════╝

def get_rls_store_keys(engine: Engine, user: UserContext) -> Optional[List[int]]:
    """Return list of StoreKeys the user may access, or None for 'all'.

    - executive / admin → None (no restriction, bypass RLS)
    - regional_manager → stores in their ContinentName
    - store_manager → only their assigned store
    """
    if user.role in ("executive", "admin") or user.is_anonymous:
        return None

    if user.role == "store_manager" and user.store_key is not None:
        return [user.store_key]

    if user.role == "regional_manager" and user.region:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT ds.StoreKey
                FROM DimStore ds
                JOIN DimGeography dg ON ds.GeographyKey = dg.GeographyKey
                WHERE dg.ContinentName = :region
            """), {"region": user.region}).fetchall()
        return [int(r[0]) for r in rows]

    return None


def apply_rls_to_df(df, user: UserContext, engine: Engine, store_col: str = "StoreKey"):
    """Filter a pandas DataFrame by RLS.  Returns filtered df."""
    keys = get_rls_store_keys(engine, user)
    if keys is None:
        return df
    return df[df[store_col].isin(keys)]
