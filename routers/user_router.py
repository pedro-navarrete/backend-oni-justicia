# routers/user_router.py
import datetime, os, pytz
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from authentication.auth_dependencies import require_bearer_token
from database.verificador_mongo import ejecutar_query, insert_document, update_document
from passlib.context import CryptContext
from models.models import UserManageRequest
from services.user_service import UserService
from utils.role_dependencies import require_role_access

router = APIRouter(prefix="/users", tags=["users"])
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Leer zona horaria desde .env o usar default
TIMEZONE_STR = os.getenv("TIMEZONE", "America/El_Salvador")
TIMEZONE = pytz.timezone(TIMEZONE_STR)


def _user_field(user: dict, *keys: str):
    for key in keys:
        if key in user and user.get(key) is not None:
            return user.get(key)
    return None

@router.post("/manage")
def manage_user(
    payload: UserManageRequest,
    current_user: dict = Depends(require_bearer_token),
    _: bool = Depends(require_role_access("/users/manage"))
):
    """
    Crea, actualiza, cambia contraseña o activa/desactiva un usuario.
    Acceso solo con Bearer token válido.
    """
    action = payload.action.lower()
    identifier = payload.username or payload.dui or getattr(payload, "oni", None)
    if action != "create" and not identifier:
        raise HTTPException(status_code=400, detail="Debes enviar username, dui u oni")
    identifier_value = str(identifier).strip() if identifier else ""

    # Buscar usuario por cualquier parámetro enviado
    user = UserService.get_user_by_any(identifier_value)
    user_exists = bool(user)

    now = datetime.datetime.now(TIMEZONE)

    # -------------------- CREATE --------------------
    if action == "create":
        if user_exists:
            raise HTTPException(status_code=400, detail="Registro duplicado, usuario ya existente")
        if not payload.password:
            raise HTTPException(status_code=400, detail="Password requerido para crear usuario")
        hashed_password = pwd_context.hash(payload.password)
        roles = payload.roles or ([payload.role] if payload.role else [])
        roles = [r for r in roles if isinstance(r, str) and r]
        doc = {
            "oni": payload.oni or "",
            "Oni": payload.oni or "",
            "username": payload.username or "",
            "Username": payload.username or "",
            "FullName": payload.full_name or "",
            "dui": payload.dui or "",
            "Dui": payload.dui or "",
            "roles": roles,
            "Roles": roles,
            "email": payload.email or "",
            "Email": payload.email or "",
            "password_hash": hashed_password,
            "PasswordHash": hashed_password,
            "is_active": True,
            "IsActive": True,
            "created_at": now,
            "updated_at": None,
            "CreatedAt": now,
            "UpdatedAt": None,
        }
        inserted_id = insert_document("users", doc)
        return {"status": "success", "user_id": inserted_id}

    # -------------------- UPDATE / PASSWORD / ACTIVATE / DEACTIVATE --------------------
    if not user_exists:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user_data = user or {}

    update_data = {}

    if action == "update":
        if payload.full_name is not None:
            update_data["FullName"] = payload.full_name
        if payload.email is not None:
            update_data["email"] = payload.email
            update_data["Email"] = payload.email
        if payload.role is not None or payload.roles is not None:
            new_roles = payload.roles or ([payload.role] if payload.role else [])
            new_roles = [r for r in new_roles if isinstance(r, str) and r]
            update_data["roles"] = new_roles
            update_data["Roles"] = new_roles
    elif action == "password":
        if not payload.password:
            raise HTTPException(status_code=400, detail="Password requerido")
        new_hash = pwd_context.hash(payload.password)
        update_data["password_hash"] = new_hash
        update_data["PasswordHash"] = new_hash
    elif action == "activate":
        if bool(_user_field(user_data, "is_active", "IsActive")):
            raise HTTPException(status_code=400, detail="El usuario ya está activo")
        update_data["is_active"] = True
        update_data["IsActive"] = True
    elif action == "deactivate":
        if not bool(_user_field(user_data, "is_active", "IsActive")):
            raise HTTPException(status_code=400, detail="El usuario ya está inactivo")
        update_data["is_active"] = False
        update_data["IsActive"] = False
    else:
        raise HTTPException(status_code=400, detail="Acción inválida")

    # Ejecutar actualización
    if update_data:
        update_data["updated_at"] = now
        update_data["UpdatedAt"] = now

        # --- Filtro más inteligente basado en lo que tiene el usuario encontrado ---
        query_filter = {}
        username = _user_field(user_data, "username", "Username", "UserName")
        dui = _user_field(user_data, "dui", "Dui")
        oni = _user_field(user_data, "oni", "Oni", "ONI")

        if username:
            query_filter["$or"] = [{"username": username}, {"Username": username}, {"UserName": username}]
        elif dui:
            query_filter["$or"] = [{"dui": dui}, {"Dui": dui}]
        elif oni:
            query_filter["$or"] = [{"oni": oni}, {"Oni": oni}, {"ONI": oni}]
        else:
            raise HTTPException(status_code=400, detail="No se pudo determinar campo de identificación del usuario")


        modified_count = update_document("users", query_filter, {"$set": update_data})
        return {"status": "success", "modified_count": modified_count}

    raise HTTPException(status_code=400, detail="No hay datos para actualizar")




@router.get("/users")
def getusers(current_user: dict = Depends(require_bearer_token),
             _: bool = Depends(require_role_access("/users/users"))
             ):
    """
    Retorna todos los usuarios de la colección users.
    Acceso solo con Bearer token válido.
    """
    users = ejecutar_query("users", {})
    # Convertir _id a string para JSON
    for u in users:
        u["_id"] = str(u["_id"])
    return {"users": users}

@router.get("/motoristas")
def get_motoristas(
    current_user: dict = Depends(require_bearer_token),
    _: bool = Depends(require_role_access("/users/motoristas")),
    nombre: Optional[str] = Query(None, description="Filtrar por nombre del empleado"),
    dui: Optional[str] = Query(None, description="Filtrar por DUI del motorista"),
    cargo: Optional[str] = Query(None, description="Filtrar por cargo funcional"),
    ubicacion: Optional[str] = Query(None, description="Filtrar por ubicación física"),
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(20, ge=1, le=100, description="Límite de resultados por página")
):
    """
    Retorna todos los usuarios con rol MOTORISTA (ANDROID_USER).
    Permite filtrar por nombre, DUI, cargo y ubicación.
    Incluye paginación.
    """

    # Llamamos al servicio
    result = UserService.get_motoristas_data(
        nombre=nombre,
        dui=dui,
        cargo=cargo,
        ubicacion=ubicacion,
        page=page,
        limit=limit
    )

    return result
