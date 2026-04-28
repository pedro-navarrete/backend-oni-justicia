import logging

from services.motorista_service import MotoristaService
from services.session_service import SessionService


logger = logging.getLogger(__name__)


class SessionManager:
    @staticmethod
    def _is_refresh_active(refresh_token: str | None) -> bool:
        if not refresh_token:
            return False

        from authentication.jwt_service import JWTService

        return JWTService._is_token_valid(str(refresh_token))

    @classmethod
    def get_active_sessions(cls, user: dict) -> dict:
        dui = MotoristaService.get_dui(user)
        session = SessionService.get_session_by_dui(dui) if dui else {}
        # Cuando la colección está vacía, find_one retorna None.
        session = session or {}

        web_active = cls._is_refresh_active(session.get("web_refresh_token"))
        android_active = cls._is_refresh_active(session.get("android_refresh_token"))

        return {
            "web_active": web_active,
            "android_active": android_active,
            "android_imei": session.get("android_session_imei"),
        }

    @classmethod
    def handle_android_login_policy(cls, user: dict, incoming_imei: str) -> dict:
        sessions = cls.get_active_sessions(user)
        active_imei = sessions.get("android_imei")

        if sessions["android_active"] and active_imei and active_imei != incoming_imei:
            from authentication.jwt_service import JWTService

            JWTService.revoke_tokens_by_user_type(user, "ANDROID_USER")
            logger.info(
                "Sesión Android previa revocada por cambio de IMEI | user=%s | imei_anterior=%s | imei_nuevo=%s",
                MotoristaService.get_username(user),
                active_imei,
                incoming_imei,
            )
            sessions["android_active"] = False
            sessions["android_imei"] = None

        return sessions
