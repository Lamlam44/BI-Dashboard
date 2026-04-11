"""
Auth REST endpoints for BI Dashboard.

POST /auth/login          – authenticate & get JWT
GET  /auth/me             – current user info
GET  /auth/users          – list users (admin only)
POST /auth/users          – create user  (admin only)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from core.auth.service import (
    UserContext,
    authenticate_user,
    create_access_token,
    ensure_auth_tables,
    get_current_user,
    hash_password,
    require_roles,
    VALID_ROLES,
)
from core.database import get_engine

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


# ── Request / Response models ──────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "store_manager"
    region: Optional[str] = None
    store_key: Optional[int] = None
    display_name: str = ""


# ── Startup ────────────────────────────────────────────────────

@router.on_event("startup")
def auth_startup():
    try:
        ensure_auth_tables(get_engine())
    except Exception as exc:
        logger.warning("Auth table setup skipped: %s", exc)


# ── Endpoints ──────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest):
    user = authenticate_user(get_engine(), body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(user)
    return LoginResponse(
        access_token=token,
        user={
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "region": user.get("region"),
            "store_key": user.get("store_key"),
            "display_name": user.get("display_name", ""),
        },
    )


@router.get("/me")
def me(user: UserContext = Depends(get_current_user)):
    return {
        "username": user.username,
        "role": user.role,
        "region": user.region,
        "store_key": user.store_key,
        "display_name": user.display_name,
        "is_anonymous": user.is_anonymous,
    }


@router.get("/users")
def list_users(user: UserContext = Depends(require_roles("admin"))):
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, username, role, region, store_key, display_name, is_active "
            "FROM bi_users ORDER BY id"
        )).mappings().fetchall()
    return [dict(r) for r in rows]


@router.post("/users", status_code=201)
def create_user(body: CreateUserRequest, user: UserContext = Depends(require_roles("admin"))):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {VALID_ROLES}")

    engine = get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO bi_users (username, password_hash, role, region, store_key, display_name)
                VALUES (:u, :p, :r, :reg, :sk, :dn)
            """), {
                "u": body.username,
                "p": hash_password(body.password),
                "r": body.role,
                "reg": body.region,
                "sk": body.store_key,
                "dn": body.display_name,
            })
    except Exception as exc:
        if "Duplicate" in str(exc):
            raise HTTPException(status_code=409, detail="Username already exists")
        raise
    return {"status": "created", "username": body.username}
