# routers/auth_router.py - VERSIÓN CON ENDPOINTS SEPARADOS

import logging
import os
from datetime import datetime
from fastapi import APIRouter, Form, HTTPException, Request, Depends
from fastapi.security import HTTPBasicCredentials
import pytz
from starlette.responses import JSONResponse
from authentication.auth_dependencies import require_bearer_token
from authentication.jwt_service import JWTService
from authentication.session_manager import SessionManager
from authentication.basic_auth_service import BasicAuthService, security
from services.imei_service import DispositivoService
from services.motorista_service import MotoristaService

# Leer zona horaria desde .env o usar default
TIMEZONE_STR = os.getenv("TIMEZONE", "America/El_Salvador")
TIMEZONE = pytz.timezone(TIMEZONE_STR)

# Usuario maestro configurable por .env (por defecto 'root')
MASTER_USERNAME = os.getenv("MASTER_USERNAME", "root")

router = APIRouter(prefix="/auth", tags=["authentication"])
dispositivo_service = DispositivoService()
logger = logging.getLogger(__name__)


def _build_login_response(user: dict, tokens: dict, user_type: str) -> dict:
    roles = MotoristaService.resolve_roles(user)
    active_role = tokens.get("active_role", user_type)
    return {
        "status": 200,
        "msg": "Login exitoso",
        "dui": MotoristaService.get_dui(user),
        "jwt": tokens["access_token"],
        "expires_in": tokens["expires_in"],
        "refresh_token": tokens["refresh_token"],
        "user_type": user_type,
        "active_role": active_role,
        "roles": roles,
        "nombre_completo": MotoristaService.get_full_name(user),
        "username": MotoristaService.get_username(user),
    }


def _build_logout_ws_payload(current_user: dict, scope: str, revoked_user_type: str) -> dict:
    """Arma payload estandar para notificar cierre de sesion por WebSocket."""
    return {
        "event": "logout",
        "scope": scope,
        "revoked_user_type": revoked_user_type,
        "dui": MotoristaService.get_dui(current_user),
        "username": MotoristaService.get_username(current_user),
        "nombre_completo": MotoristaService.get_full_name(current_user),
        "active_role": current_user.get("_active_role"),
        "session_imei": current_user.get("_session_imei"),
        "timestamp": datetime.utcnow(),
    }


def _should_notify_auth_ws(user: dict) -> bool:
    """Envía eventos auth WS solo para usuarios con ambos roles (WEB_USER + ANDROID_USER)."""
    roles = set(MotoristaService.resolve_roles(user))
    return {"WEB_USER", "ANDROID_USER"}.issubset(roles)


def _build_login_ws_payload(user: dict, scope: str, user_type: str, session_imei: str = None) -> dict:
    return {
        "event": "login",
        "scope": scope,
        "user_type": user_type,
        "dui": MotoristaService.get_dui(user),
        "username": MotoristaService.get_username(user),
        "nombre_completo": MotoristaService.get_full_name(user),
        "active_role": user_type,
        "session_imei": session_imei,
        "timestamp": datetime.utcnow(),
    }


async def _notificar_login_ws(user: dict, scope: str, user_type: str, session_imei: str = None):
    """Notifica login por WebSocket sin bloquear el flujo principal (solo dual-role)."""
    if not _should_notify_auth_ws(user):
        logger.debug("WS auth_login omitido: usuario no tiene ambos roles")
        return

    try:
        from services.mision_service import enviar_por_websocket

        await enviar_por_websocket(
            category="auth_login",
            data=_build_login_ws_payload(user, scope=scope, user_type=user_type, session_imei=session_imei),
        )
    except Exception as e:
        logger.error(
            "No se pudo enviar evento login por WebSocket | scope=%s user_type=%s | %s: %s",
            scope,
            user_type,
            type(e).__name__,
            e,
            exc_info=True,
        )


async def _notificar_logout_ws(current_user: dict, scope: str, revoked_user_type: str):
    """Notifica logout por WebSocket sin bloquear el flujo principal (solo dual-role)."""
    if not _should_notify_auth_ws(current_user):
        logger.debug("WS auth_logout omitido: usuario no tiene ambos roles")
        return

    try:
        # Import local para evitar acoplar el arranque de auth a la config WS de misiones.
        from services.mision_service import enviar_por_websocket

        await enviar_por_websocket(
            category="auth_logout",
            data=_build_logout_ws_payload(current_user, scope, revoked_user_type),
        )
    except Exception as e:
        logger.error(
            "No se pudo enviar evento logout por WebSocket | scope=%s revoked_user_type=%s | %s: %s",
            scope,
            revoked_user_type,
            type(e).__name__,
            e,
            exc_info=True,
        )


# -------------------- Helper: Basic Auth --------------------
async def verify_basic_auth(request: Request):
    """
    Valida Basic Auth
    """
    credentials: HTTPBasicCredentials = await security(request)
    return BasicAuthService.verify_client(credentials)


async def verify_basic_auth_for_legacy(request: Request):
    """Solo exige Basic Auth cuando grant_type=password en endpoint legacy."""
    form = await request.form()
    if form.get("grant_type") == "password":
        credentials: HTTPBasicCredentials = await security(request)
        return BasicAuthService.verify_client(credentials)
    return None


# ==================== LOGIN WEB USER ====================
@router.post("/login/web")
async def login_web(
        username: str = Form(...),
        password: str = Form(None),
        basic_auth_user: str = Depends(verify_basic_auth),
):
    """
    Login para usuarios WEB_USER.

    Requiere:
    - Basic Auth (client credentials)
    - username (DUI o Username)
    - password (excepto para usuario maestro)

    Retorna:
    - JWT con expiración configurada para WEB (default: 30 minutos)
    - Refresh token con expiración configurada para WEB (default: 24 horas)
    """
    # Obtener usuario
    user = MotoristaService.get_motorista_by_any(username)

    if not user:
        return JSONResponse(
            status_code=401,
            content={"type": "DUI", "status": 401, "detail": "DUI no registrado"}
        )

    if not MotoristaService.is_active(user):
        raise HTTPException(status_code=403, detail="Usuario inactivo")

    # Verificar que sea WEB_USER
    if not MotoristaService.has_role(user, "WEB_USER"):
        raise HTTPException(
            status_code=403,
            detail="Este endpoint es solo para WEB_USER"
        )

    # Validar password (excepto para usuario maestro)
    if MotoristaService.get_username(user) != MASTER_USERNAME:
        if not password:
            return JSONResponse(
                status_code=400,
                content={
                    "type": "Password",
                    "status": 400,
                    "detail": "Password es requerido para WEB_USER"
                }
            )

        if not MotoristaService.verify_password(user, password):
            raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    else:
        logging.info(f"Acceso maestro sin password para usuario: {MASTER_USERNAME}")

    # Crear tokens con configuración WEB
    tokens = JWTService.create_tokens_for_login(
        user,
        user_type="WEB_USER",
        active_role="WEB_USER",
    )

    active_sessions = SessionManager.get_active_sessions(user)
    logging.info(
        "Login Web exitoso | user=%s | web_active=%s | android_active=%s | android_imei=%s",
        MotoristaService.get_username(user),
        active_sessions.get("web_active"),
        active_sessions.get("android_active"),
        active_sessions.get("android_imei"),
    )

    await _notificar_login_ws(user, scope="web", user_type="WEB_USER")
    return _build_login_response(user, tokens, "WEB_USER")


# ==================== LOGIN ANDROID USER ====================
@router.post("/login/android")
async def login_android(
        username: str = Form(...),
        imei: str = Form(...),
        basic_auth_user: str = Depends(verify_basic_auth),
):
    """
    Login para usuarios ANDROID_USER.

    Requiere:
    - Basic Auth (client credentials)
    - username (DUI)
    - imei (IMEI del dispositivo)

    Validaciones:
    - Usuario activo
    - IMEI registrado y coincidente

    Retorna:
    - JWT con expiración configurada para ANDROID (default: 10 minutos)
    - Refresh token con expiración configurada para ANDROID (default: 24 horas)
    """
    # Obtener usuario
    user = MotoristaService.get_motorista_by_any(username)

    if not user:
        return JSONResponse(
            status_code=401,
            content={"type": "DUI", "status": 401, "detail": "DUI no registrado"}
        )

    if not MotoristaService.is_active(user):
        raise HTTPException(status_code=403, detail="Usuario inactivo")

    # Verificar que sea ANDROID_USER
    if not MotoristaService.has_role(user, "ANDROID_USER"):
        raise HTTPException(
            status_code=403,
            detail=f"Usuario no autorizado"
        )

    # Política: si cambia el IMEI, revocar solo la sesión Android previa.
    SessionManager.handle_android_login_policy(user, imei)


    # ========== VALIDAR IMEI ==========
    # if not imei:
    #     raise HTTPException(
    #         status_code=400,
    #         detail="IMEI requerido para usuarios Android"
    #     )
    #
    # registered_imei = user.get("Imei")
    # if not registered_imei:
    #     raise HTTPException(
    #         status_code=403,
    #         detail="Usuario no tiene IMEI registrado"
    #     )
    #
    # if registered_imei != imei:
    #     raise HTTPException(
    #         status_code=403,
    #         detail="IMEI del dispositivo no coincide con el registrado"
    #     )

    # ========== VALIDAR PASSWORD (OPCIONAL - COMENTADO) ==========
    # Descomentar cuando necesites validar password en android users
    # if not password:
    #     raise HTTPException(status_code=400, detail="Password es requerido")
    # if not UserService.verify_password(user, password):
    #     raise HTTPException(status_code=401, detail="Contraseña incorrecta")

    # ========== CONSULTAR DISPOSITIVO EN SOTI ==========
    # try:
    #     data_dispositivo = dispositivo_service.obtener_por_imei(imei)
    # except HTTPException as e:
    #     logging.error(f"Error al consultar SOTI para IMEI {imei}: {e.detail}")
    #     raise HTTPException(
    #         status_code=502,
    #         detail=f"Error al consultar información del dispositivo: {e.detail} en SOTI"
    #     )
    # except Exception as e:
    #     logging.exception(f"Error inesperado al consultar dispositivo SOTI para {imei}")
    #     raise HTTPException(
    #         status_code=500,
    #         detail="Error interno al consultar dispositivo en SOTI"
    #     )
    #
    # if not data_dispositivo:
    #     raise HTTPException(
    #         status_code=404,
    #         detail="Dispositivo no encontrado en SOTI"
    #     )
    #
    # # ========== VALIDAR TELÉFONO ==========
    # telefono_usuario = user.get("Telefono")
    # telefono_soti = data_dispositivo.get("telefono")
    #
    # logging.info(
    #     f"Login Android: usuario={username}, imei={imei}, "
    #     f"telefono_usuario={telefono_usuario}, telefono_soti={telefono_soti}"
    # )
    #
    # if not telefono_usuario:
    #     logging.error(f"Usuario {username} no tiene teléfono registrado")
    #     raise HTTPException(
    #         status_code=403,
    #         detail="Usuario no tiene teléfono registrado"
    #     )
    #
    # if not telefono_soti:
    #     logging.error(f"Dispositivo IMEI {imei} no tiene teléfono registrado en SOTI")
    #     raise HTTPException(
    #         status_code=403,
    #         detail="El dispositivo no tiene teléfono registrado en SOTI"
    #     )
    #
    # if str(telefono_usuario) != str(telefono_soti):
    #     logging.error(
    #         f"Teléfono del usuario ({telefono_usuario}) no coincide "
    #         f"con el del dispositivo ({telefono_soti})"
    #     )
    #     raise HTTPException(
    #         status_code=403,
    #         detail="El teléfono del dispositivo no coincide con el del usuario"
    #     )

    logging.info(f"Login Android autorizado: usuario={username}, imei={imei}")

    # Crear tokens con configuración ANDROID
    tokens = JWTService.create_tokens_for_login(
        user,
        user_type="ANDROID_USER",
        active_role="ANDROID_USER",
        session_imei=imei,
    )

    active_sessions = SessionManager.get_active_sessions(user)
    logging.info(
        "Login Android exitoso | user=%s | imei=%s | web_active=%s | android_active=%s",
        MotoristaService.get_username(user),
        imei,
        active_sessions.get("web_active"),
        active_sessions.get("android_active"),
    )

    await _notificar_login_ws(user, scope="android", user_type="ANDROID_USER", session_imei=imei)
    return _build_login_response(user, tokens, "ANDROID_USER")


# ==================== REFRESH TOKEN (COMPARTIDO) ====================
@router.post("/token/refresh")
async def refresh_token(
        username: str = Form(...),
        refreshToken: str = Form(...),
):
    """
    Endpoint para refrescar tokens (compartido para Web y Android).

    Detecta automáticamente el tipo de usuario desde el refresh token
    y genera nuevos tokens con la configuración correspondiente.

    Requiere:
    - username (DUI o Username)
    - refreshToken (refresh token válido)

    NO requiere Basic Auth.
    """
    # Verificar refresh token
    user = JWTService.verify_refresh_token(refreshToken)

    if not user:
        raise HTTPException(status_code=401, detail="Refresh token inválido o expirado")

    # Verificar que el username corresponda al usuario
    allowed_ids = [
        MotoristaService.get_username(user),
        MotoristaService.get_dui(user),
        MotoristaService.get_oni(user),
    ]
    if username not in allowed_ids:
        raise HTTPException(
            status_code=401,
            detail="Refresh token no corresponde a este usuario"
        )

    # Obtener tipo de usuario y crear nuevos tokens
    user_type = str(user.get("_user_type") or "WEB_USER")
    active_role = str(user.get("_active_role") or user_type)
    if not MotoristaService.has_role(user, active_role):
        raise HTTPException(status_code=403, detail="Rol activo no autorizado para este usuario")

    session_imei = user.get("_session_imei")
    tokens = JWTService.create_tokens_for_refresh(
        user,
        user_type=user_type,
        active_role=active_role,
        session_imei=session_imei,
    )

    return {
        "status": 200,
        "msg": "Refresh token exitoso",
        "jwt": tokens["access_token"],
        "expires_in": tokens["expires_in"],
        "refresh_token": tokens["refresh_token"],
        "user_type": user_type,
        "active_role": active_role,
    }


@router.post("/logout/current")
async def logout_current(current_user: dict = Depends(require_bearer_token)):
    """Cierra la sesión del canal actual (web o android)."""
    user_type = current_user.get("_user_type")
    if user_type not in {"WEB_USER", "ANDROID_USER"}:
        raise HTTPException(status_code=401, detail="Tipo de sesión inválido")
    JWTService.revoke_tokens_by_user_type(current_user, user_type)
    await _notificar_logout_ws(current_user, scope="current", revoked_user_type=user_type)
    return {
        "status": 200,
        "msg": "Sesión cerrada exitosamente",
        "user_type": user_type,
    }


@router.post("/logout/android")
async def logout_android(current_user: dict = Depends(require_bearer_token)):
    """Cierra sesión Android sin afectar sesión Web."""
    if not MotoristaService.has_role(current_user, "ANDROID_USER"):
        raise HTTPException(status_code=403, detail="Usuario no tiene rol ANDROID_USER")

    current_user_type = current_user.get("_user_type")
    if current_user_type not in {"WEB_USER", "ANDROID_USER"}:
        raise HTTPException(status_code=401, detail="Tipo de sesión inválido")
    if current_user_type != "ANDROID_USER":
        raise HTTPException(
            status_code=403,
            detail=f"No puedes cerrar sesión Android con un token de tipo {current_user_type}",
        )

    JWTService.revoke_tokens_by_user_type(current_user, "ANDROID_USER")
    await _notificar_logout_ws(current_user, scope="android", revoked_user_type="ANDROID_USER")
    return {
        "status": 200,
        "msg": "Sesión Android cerrada exitosamente",
        "user_type": "ANDROID_USER",
    }


@router.post("/logout/web")
async def logout_web(current_user: dict = Depends(require_bearer_token)):
    """Cierra sesión Web sin afectar sesión Android."""
    if not MotoristaService.has_role(current_user, "WEB_USER"):
        raise HTTPException(status_code=403, detail="Usuario no tiene rol WEB_USER")

    current_user_type = current_user.get("_user_type")
    if current_user_type not in {"WEB_USER", "ANDROID_USER"}:
        raise HTTPException(status_code=401, detail="Tipo de sesión inválido")
    if current_user_type != "WEB_USER":
        raise HTTPException(
            status_code=403,
            detail=f"No puedes cerrar sesión Web con un token de tipo {current_user_type}",
        )

    JWTService.revoke_tokens_by_user_type(current_user, "WEB_USER")
    await _notificar_logout_ws(current_user, scope="web", revoked_user_type="WEB_USER")
    return {
        "status": 200,
        "msg": "Sesión Web cerrada exitosamente",
        "user_type": "WEB_USER",
    }


@router.post("/logout/all")
async def logout_all(current_user: dict = Depends(require_bearer_token)):
    """Cierra todas las sesiones activas del usuario."""
    JWTService.revoke_all_tokens(current_user)
    await _notificar_logout_ws(current_user, scope="all", revoked_user_type="ALL")
    return {
        "status": 200,
        "msg": "Todas las sesiones fueron cerradas exitosamente",
    }
