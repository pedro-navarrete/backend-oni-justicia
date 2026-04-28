from datetime import datetime

import pytz

from database.verificador_mongo import get_db

TIMEZONE = pytz.timezone("America/El_Salvador")


class SessionService:
    COLLECTION = "sessions"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(TIMEZONE)

    @staticmethod
    def _base_session(dui: str) -> dict:
        now = SessionService._now()
        return {
            "dui": dui,
            "web_token": None,
            "web_token_created_at": None,
            "web_refresh_token": None,
            "web_refresh_created_at": None,
            "android_token": None,
            "android_token_created_at": None,
            "android_refresh_token": None,
            "android_refresh_created_at": None,
            "android_session_imei": None,
            "last_web_login": None,
            "last_android_login": None,
            "created_at": now,
            "updated_at": now,
        }

    @staticmethod
    def get_session_by_dui(dui: str) -> dict | None:
        if not dui:
            return None
        return get_db()[SessionService.COLLECTION].find_one({"dui": dui})

    @staticmethod
    def create_or_get_session(dui: str) -> dict:
        if not dui:
            return {}
        collection = get_db()[SessionService.COLLECTION]
        session = collection.find_one({"dui": dui})
        if session:
            return session
        base = SessionService._base_session(dui)
        collection.insert_one(base)
        return collection.find_one({"dui": dui}) or base

    @staticmethod
    def update_session_fields(dui: str, update_set: dict) -> int:
        if not dui:
            return 0
        collection = get_db()[SessionService.COLLECTION]
        now = SessionService._now()
        fields_to_update = (update_set or {}).copy()
        fields_to_update["updated_at"] = now

        result = collection.update_one({"dui": dui}, {"$set": fields_to_update})
        if result.matched_count == 0:
            base = SessionService._base_session(dui)
            base.update(fields_to_update)
            try:
                collection.insert_one(base)
                return 1
            except Exception:
                return 0
        return result.modified_count

    @staticmethod
    def update_tokens_by_user_type(
        dui: str,
        user_type: str,
        access_token: str,
        refresh_token: str,
        session_imei: str = None,
    ) -> int:
        now = SessionService._now()
        if user_type == "ANDROID_USER":
            return SessionService.update_session_fields(
                dui,
                {
                    "android_token": access_token,
                    "android_token_created_at": now,
                    "android_refresh_token": refresh_token,
                    "android_refresh_created_at": now,
                    "android_session_imei": session_imei,
                    "last_android_login": now,
                },
            )
        return SessionService.update_session_fields(
            dui,
            {
                "web_token": access_token,
                "web_token_created_at": now,
                "web_refresh_token": refresh_token,
                "web_refresh_created_at": now,
                "last_web_login": now,
            },
        )

    @staticmethod
    def revoke_by_user_type(dui: str, user_type: str) -> int:
        if user_type == "ANDROID_USER":
            return SessionService.update_session_fields(
                dui,
                {
                    "android_token": None,
                    "android_token_created_at": None,
                    "android_refresh_token": None,
                    "android_refresh_created_at": None,
                    "android_session_imei": None,
                },
            )
        return SessionService.update_session_fields(
            dui,
            {
                "web_token": None,
                "web_token_created_at": None,
                "web_refresh_token": None,
                "web_refresh_created_at": None,
            },
        )

    @staticmethod
    def revoke_all(dui: str) -> int:
        return SessionService.update_session_fields(
            dui,
            {
                "web_token": None,
                "web_token_created_at": None,
                "web_refresh_token": None,
                "web_refresh_created_at": None,
                "android_token": None,
                "android_token_created_at": None,
                "android_refresh_token": None,
                "android_refresh_created_at": None,
                "android_session_imei": None,
            },
        )
