# authentication/auth_dependencies.py
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from authentication.jwt_service import JWTService
from authentication.permissions import PermissionManager

# Instancia de HTTPBearer que FastAPI usará para Swagger
bearer_scheme = HTTPBearer(auto_error=True)

def require_bearer_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
):
    """
    Valida un token JWT recibido en Authorization header tipo Bearer.
    Swagger mostrará el botón 'Authorize' automáticamente.
    """
    token = credentials.credentials  # Solo el token, sin "Bearer "
    user = JWTService.verify_access_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    return user


def require_permission(required_endpoint: str):
    async def permission_dependency(current_user: dict = Depends(require_bearer_token)):
        active_role = current_user.get("_active_role")
        if not active_role:
            raise HTTPException(status_code=403, detail="Rol activo no definido en la sesión")

        if not PermissionManager.has_permission(active_role, required_endpoint):
            raise HTTPException(status_code=403, detail="No tienes permiso para acceder a este recurso")

        return current_user

    return permission_dependency
