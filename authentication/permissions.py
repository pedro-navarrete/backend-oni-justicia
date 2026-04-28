import json
from pathlib import Path

ROLES_FILE = Path(__file__).resolve().parent.parent / "roles.json"
_roles_cache: dict | None = None
_roles_mtime: float | None = None


class PermissionManager:
    """Gestiona carga de configuración de roles y validación de permisos por endpoint."""

    @staticmethod
    def load_roles_config() -> dict:
        global _roles_cache, _roles_mtime

        current_mtime = ROLES_FILE.stat().st_mtime
        if _roles_cache is not None and _roles_mtime == current_mtime:
            return _roles_cache

        with open(ROLES_FILE, "r", encoding="utf-8") as file:
            _roles_cache = json.load(file)
            _roles_mtime = current_mtime
            return _roles_cache

    @staticmethod
    def has_permission(user_type: str, endpoint: str) -> bool:
        roles = PermissionManager.load_roles_config()
        permissions = roles.get(user_type, {}).get("permissions", [])
        return endpoint in permissions

    @staticmethod
    def get_user_permissions(user_type: str) -> list[str]:
        roles = PermissionManager.load_roles_config()
        return list(roles.get(user_type, {}).get("permissions", []))
