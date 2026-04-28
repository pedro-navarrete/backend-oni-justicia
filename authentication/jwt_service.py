# authentication/jwt_service.py - VERSIÓN CON TOKENS POR CANAL Y ROL ACTIVO

import os
from datetime import datetime, timedelta

import jwt
import pytz
from dotenv import load_dotenv
from fastapi import HTTPException

from services.motorista_service import MotoristaService
from services.session_service import SessionService

load_dotenv()

# -------------------- TIMEZONE --------------------
TIMEZONE_STR = os.getenv("TIMEZONE", "America/El_Salvador")
TIMEZONE = pytz.timezone(TIMEZONE_STR)


class JWTService:
    """
    Servicio para crear y verificar JWT y Refresh Tokens.
    Soporta sesiones separadas para Web y Android en colección sessions.
    """

    # -------------------- CONFIG GENERAL --------------------
    JWT_SECRET = os.getenv("JWT_SECRET")
    JWT_ALG = os.getenv("JWT_ALG", "HS256")

    # -------------------- CONFIG WEB USER --------------------
    WEB_JWT_EXP_VALUE = int(os.getenv("WEB_JWT_EXP_VALUE", 30))
    WEB_JWT_EXP_UNIT = os.getenv("WEB_JWT_EXP_UNIT", "minutes")

    WEB_REFRESH_EXP_VALUE = int(os.getenv("WEB_REFRESH_EXP_VALUE", 24))
    WEB_REFRESH_EXP_UNIT = os.getenv("WEB_REFRESH_EXP_UNIT", "hours")

    # -------------------- CONFIG ANDROID USER --------------------
    ANDROID_JWT_EXP_VALUE = int(os.getenv("ANDROID_JWT_EXP_VALUE", 10))
    ANDROID_JWT_EXP_UNIT = os.getenv("ANDROID_JWT_EXP_UNIT", "minutes")

    ANDROID_REFRESH_EXP_VALUE = int(os.getenv("ANDROID_REFRESH_EXP_VALUE", 24))
    ANDROID_REFRESH_EXP_UNIT = os.getenv("ANDROID_REFRESH_EXP_UNIT", "hours")

    # -------------------- HELPERS --------------------
    @staticmethod
    def build_timedelta(value: int, unit: str) -> timedelta:
        unit = unit.lower()
        if unit == "minutes":
            return timedelta(minutes=value)
        if unit == "hours":
            return timedelta(hours=value)
        if unit == "days":
            return timedelta(days=value)
        raise ValueError(f"Unidad de tiempo inválida: {unit}")

    @staticmethod
    def get_exp_seconds(value: int, unit: str) -> int:
        unit = unit.lower()
        if unit == "minutes":
            return value * 60
        if unit == "hours":
            return value * 3600
        if unit == "days":
            return value * 86400
        raise ValueError(f"Unidad de tiempo inválida: {unit}")

    @classmethod
    def _is_token_valid(cls, token: str) -> bool:
        try:
            jwt.decode(token, cls.JWT_SECRET, algorithms=[cls.JWT_ALG])
            return True
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return False

    @classmethod
    def _is_access_token_valid(cls, token: str) -> bool:
        payload = cls._decode_payload(token)
        return bool(payload and payload.get("type") == "access")

    @classmethod
    def _decode_payload(cls, token: str) -> dict | None:
        try:
            return jwt.decode(token, cls.JWT_SECRET, algorithms=[cls.JWT_ALG])
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return None

    @staticmethod
    def _normalize_user_type(user_type: str | None) -> str:
        return user_type if user_type in {"WEB_USER", "ANDROID_USER"} else "WEB_USER"

    @classmethod
    def _resolve_user_type(cls, user: dict, user_type: str | None) -> str:
        if user_type in {"WEB_USER", "ANDROID_USER"}:
            return user_type

        roles = MotoristaService.resolve_roles(user)
        # Priorizamos WEB_USER cuando el usuario tiene ambos roles y no se solicitó un canal explícito.
        if "WEB_USER" in roles:
            return "WEB_USER"
        if "ANDROID_USER" in roles:
            return "ANDROID_USER"
        return cls._normalize_user_type(user_type)

    @classmethod
    def _get_storage_fields(cls, user_type: str) -> dict:
        user_type = cls._normalize_user_type(user_type)
        if user_type == "ANDROID_USER":
            return {
                "access": "android_token",
                "access_created": "android_token_created_at",
                "refresh": "android_refresh_token",
                "refresh_created": "android_refresh_created_at",
                "imei": "android_session_imei",
            }
        return {
            "access": "web_token",
            "access_created": "web_token_created_at",
            "refresh": "web_refresh_token",
            "refresh_created": "web_refresh_created_at",
            "imei": None,
        }

    @classmethod
    def get_remaining_seconds(cls, token: str) -> int:
        """Devuelve los segundos restantes de un JWT válido."""
        try:
            payload = jwt.decode(
                token,
                cls.JWT_SECRET,
                algorithms=[cls.JWT_ALG],
                options={"verify_exp": True}
            )
            exp = payload.get("exp")
            if not exp:
                return 0
            now = datetime.now(TIMEZONE).timestamp()
            return max(0, int(exp - now))
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return 0

    # -------------------- OBTENER CONFIGURACIÓN POR TIPO --------------------
    @classmethod
    def get_config_by_user_type(cls, user_type: str) -> dict:
        user_type = cls._normalize_user_type(user_type)
        if user_type == "ANDROID_USER":
            return {
                "jwt_value": cls.ANDROID_JWT_EXP_VALUE,
                "jwt_unit": cls.ANDROID_JWT_EXP_UNIT,
                "refresh_value": cls.ANDROID_REFRESH_EXP_VALUE,
                "refresh_unit": cls.ANDROID_REFRESH_EXP_UNIT
            }
        return {
            "jwt_value": cls.WEB_JWT_EXP_VALUE,
            "jwt_unit": cls.WEB_JWT_EXP_UNIT,
            "refresh_value": cls.WEB_REFRESH_EXP_VALUE,
            "refresh_unit": cls.WEB_REFRESH_EXP_UNIT
        }

    # -------------------- CREAR TOKENS --------------------
    @classmethod
    def create_access_token(
        cls,
        user: dict,
        expires_delta: timedelta = None,
        user_type: str = None,
        active_role: str = None,
        session_imei: str = None,
    ) -> str:
        """Crea access token."""
        try:
            now = datetime.now(TIMEZONE)
            user_type = cls._resolve_user_type(user, user_type)
            active_role = active_role or user_type
            roles = MotoristaService.resolve_roles(user)
            username = MotoristaService.get_username(user)
            dui = MotoristaService.get_dui(user)

            if expires_delta:
                expire = now + expires_delta
            else:
                config = cls.get_config_by_user_type(user_type)
                expire = now + cls.build_timedelta(config["jwt_value"], config["jwt_unit"])

            payload = {
                "sub": username or dui,
                "user_type": user_type,
                "active_role": active_role,
                "roles": roles,
                "iat": now,
                "exp": expire,
                "type": "access",
            }
            if user_type == "ANDROID_USER" and session_imei:
                payload["imei"] = session_imei

            return jwt.encode(payload, cls.JWT_SECRET, algorithm=cls.JWT_ALG)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error creando access token: {str(e)}")

    @classmethod
    def create_refresh_token(
        cls,
        user: dict,
        expires_delta: timedelta = None,
        user_type: str = None,
        active_role: str = None,
        session_imei: str = None,
    ) -> str:
        """Crea refresh token."""
        try:
            now = datetime.now(TIMEZONE)
            user_type = cls._resolve_user_type(user, user_type)
            active_role = active_role or user_type
            roles = MotoristaService.resolve_roles(user)
            username = MotoristaService.get_username(user)
            dui = MotoristaService.get_dui(user)

            if expires_delta:
                expire = now + expires_delta
            else:
                config = cls.get_config_by_user_type(user_type)
                expire = now + cls.build_timedelta(config["refresh_value"], config["refresh_unit"])

            payload = {
                "sub": username or dui,
                "user_type": user_type,
                "active_role": active_role,
                "roles": roles,
                "iat": now,
                "exp": expire,
                "type": "refresh",
            }
            if user_type == "ANDROID_USER" and session_imei:
                payload["imei"] = session_imei

            return jwt.encode(payload, cls.JWT_SECRET, algorithm=cls.JWT_ALG)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error creando refresh token: {str(e)}")

    @classmethod
    def create_tokens_for_login(
        cls,
        user: dict,
        user_type: str = None,
        active_role: str = None,
        session_imei: str = None,
    ) -> dict:
        """Login por canal; reutiliza tokens del canal cuando siguen válidos."""
        user_type = cls._resolve_user_type(user, user_type)
        active_role = active_role or user_type
        fields = cls._get_storage_fields(user_type)
        config = cls.get_config_by_user_type(user_type)
        dui = MotoristaService.get_dui(user)
        session = SessionService.create_or_get_session(dui) if dui else {}

        access_token = session.get(fields["access"])
        refresh_token = session.get(fields["refresh"])
        stored_imei = session.get(fields["imei"]) if fields["imei"] else None

        if user_type == "ANDROID_USER" and stored_imei and session_imei and stored_imei != session_imei:
            access_token = None
            refresh_token = None

        if access_token and refresh_token and cls._is_access_token_valid(access_token) and cls._is_token_valid(refresh_token):
            payload = cls._decode_payload(access_token) or {}
            same_role = payload.get("active_role") == active_role
            same_imei = user_type != "ANDROID_USER" or payload.get("imei") == session_imei
            if same_role and same_imei:
                return {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": "Bearer",
                    "expires_in": cls.get_remaining_seconds(access_token),
                    "user_type": user_type,
                    "active_role": active_role,
                }

        access_token = cls.create_access_token(
            user,
            user_type=user_type,
            active_role=active_role,
            session_imei=session_imei,
        )
        refresh_token = cls.create_refresh_token(
            user,
            user_type=user_type,
            active_role=active_role,
            session_imei=session_imei,
        )
        if dui:
            SessionService.update_tokens_by_user_type(
                dui=dui,
                user_type=user_type,
                access_token=access_token,
                refresh_token=refresh_token,
                session_imei=session_imei,
            )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": cls.get_exp_seconds(config["jwt_value"], config["jwt_unit"]),
            "user_type": user_type,
            "active_role": active_role,
        }

    @classmethod
    def create_tokens_for_refresh(
        cls,
        user: dict,
        user_type: str = None,
        active_role: str = None,
        session_imei: str = None,
    ) -> dict:
        """Crea nuevos tokens desde refresh por el mismo canal/sesión."""
        user_type = cls._resolve_user_type(user, user_type)
        active_role = active_role or user_type
        config = cls.get_config_by_user_type(user_type)
        dui = MotoristaService.get_dui(user)
        access_token = cls.create_access_token(
            user,
            user_type=user_type,
            active_role=active_role,
            session_imei=session_imei,
        )
        refresh_token = cls.create_refresh_token(
            user,
            user_type=user_type,
            active_role=active_role,
            session_imei=session_imei,
        )
        if dui:
            SessionService.update_tokens_by_user_type(
                dui=dui,
                user_type=user_type,
                access_token=access_token,
                refresh_token=refresh_token,
                session_imei=session_imei,
            )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": cls.get_exp_seconds(config["jwt_value"], config["jwt_unit"]),
            "user_type": user_type,
            "active_role": active_role,
        }

    @classmethod
    def create_tokens(cls, user: dict, user_type: str = None) -> dict:
        """Crea tokens (usado para creación manual)."""
        user_type = cls._resolve_user_type(user, user_type)
        config = cls.get_config_by_user_type(user_type)
        dui = MotoristaService.get_dui(user)
        access_token = cls.create_access_token(user, user_type=user_type, active_role=user_type)
        refresh_token = cls.create_refresh_token(user, user_type=user_type, active_role=user_type)
        if dui:
            SessionService.update_tokens_by_user_type(
                dui=dui,
                user_type=user_type,
                access_token=access_token,
                refresh_token=refresh_token,
            )

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": cls.get_exp_seconds(config["jwt_value"], config["jwt_unit"]),
            "refresh_token": refresh_token,
            "user_type": user_type,
            "active_role": user_type,
        }

    # -------------------- REVOCAR TOKENS --------------------
    @classmethod
    def revoke_tokens_by_user_type(cls, user: dict, user_type: str) -> int:
        """Revoca sesión de un canal específico (WEB_USER o ANDROID_USER)."""
        user_type = cls._normalize_user_type(user_type)
        dui = MotoristaService.get_dui(user)
        if not dui:
            return 0
        return SessionService.revoke_by_user_type(dui, user_type)

    @classmethod
    def revoke_all_tokens(cls, user: dict) -> int:
        """Revoca sesiones Web/Android."""
        dui = MotoristaService.get_dui(user)
        if not dui:
            return 0
        return SessionService.revoke_all(dui)

    # -------------------- VERIFICAR TOKENS --------------------
    @classmethod
    def verify_access_token(cls, token: str):
        payload = cls._decode_payload(token)
        if not payload or payload.get("type") != "access":
            return None

        sub = payload.get("sub")
        if not sub:
            return None

        user_type = payload.get("user_type")
        if user_type not in {"WEB_USER", "ANDROID_USER"}:
            return None
        fields = cls._get_storage_fields(user_type)
        user = MotoristaService.get_motorista_by_any(sub)
        if not user or not MotoristaService.is_active(user):
            return None

        dui = MotoristaService.get_dui(user)
        session = SessionService.get_session_by_dui(dui)
        if not session or session.get(fields["access"]) != token:
            return None

        current_roles = MotoristaService.resolve_roles(user)
        active_role = payload.get("active_role")
        if active_role and active_role not in current_roles:
            return None

        user["_active_role"] = active_role or user_type
        user["_user_type"] = user_type
        user["_roles"] = current_roles
        if payload.get("imei") and fields["imei"]:
            user["_session_imei"] = payload.get("imei")
        return user

    @classmethod
    def verify_refresh_token(cls, token: str):
        payload = cls._decode_payload(token)
        if not payload or payload.get("type") != "refresh":
            return None

        sub = payload.get("sub")
        if not sub:
            return None

        user_type = payload.get("user_type")
        if user_type not in {"WEB_USER", "ANDROID_USER"}:
            return None
        fields = cls._get_storage_fields(user_type)
        user = MotoristaService.get_motorista_by_any(sub)
        if not user or not MotoristaService.is_active(user):
            return None

        dui = MotoristaService.get_dui(user)
        session = SessionService.get_session_by_dui(dui)
        if not session or session.get(fields["refresh"]) != token:
            return None

        current_roles = MotoristaService.resolve_roles(user)
        active_role = payload.get("active_role")
        if active_role and active_role not in current_roles:
            return None

        user["_active_role"] = active_role or user_type
        user["_user_type"] = user_type
        user["_roles"] = current_roles
        if payload.get("imei") and fields["imei"]:
            user["_session_imei"] = payload.get("imei")
        return user
