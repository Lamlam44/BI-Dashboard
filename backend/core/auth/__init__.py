"""core.auth – Authentication & Authorization package."""

from .service import (
    UserContext,
    authenticate_user,
    create_access_token,
    ensure_auth_tables,
    get_current_user,
    get_rls_store_keys,
    apply_rls_to_df,
    hash_password,
    require_roles,
    VALID_ROLES,
)

__all__ = [
    "UserContext",
    "authenticate_user",
    "create_access_token",
    "ensure_auth_tables",
    "get_current_user",
    "get_rls_store_keys",
    "apply_rls_to_df",
    "hash_password",
    "require_roles",
    "VALID_ROLES",
]
