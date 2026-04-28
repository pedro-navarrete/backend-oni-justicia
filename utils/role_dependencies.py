# utils/role_dependencies.py
from authentication.auth_dependencies import require_permission


def require_role_access(endpoint: str):
    return require_permission(endpoint)
