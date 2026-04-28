"""Migra tokens de users hacia sessions y limpia campos legacy."""

from datetime import datetime

import pytz

from database.verificador_mongo import get_db

TIMEZONE = pytz.timezone("America/El_Salvador")

LEGACY_TOKEN_FIELDS = [
    "WebJwtToken",
    "WebTokenCreatedAt",
    "WebRefreshToken",
    "WebRefreshTokenCreatedAt",
    "AndroidJwtToken",
    "AndroidTokenCreatedAt",
    "AndroidRefreshToken",
    "AndroidRefreshTokenCreatedAt",
    "AndroidSessionImei",
    "JwtToken",
    "TokenCreatedAt",
    "RefreshToken",
    "RefreshTokenCreatedAt",
    "TokenUserType",
    "ActiveRole",
]


def _compose_full_name(user: dict) -> str:
    full_name = user.get("FullName")
    if isinstance(full_name, str) and full_name.strip():
        return full_name.strip()
    parts = [
        user.get("primer_nombre"),
        user.get("segundo_nombre"),
        user.get("primer_ape"),
        user.get("segundo_ape"),
    ]
    return " ".join(str(p).strip() for p in parts if p and str(p).strip())


def run() -> None:
    db = get_db()
    users_col = db["users"]
    sessions_col = db["sessions"]
    now = datetime.now(TIMEZONE)

    migrated_sessions = 0
    updated_users = 0

    for user in users_col.find({}):
        dui = user.get("dui") or user.get("Dui")
        if not dui:
            continue

        full_name = _compose_full_name(user)
        has_legacy_token_data = any(user.get(field) is not None for field in LEGACY_TOKEN_FIELDS)

        if has_legacy_token_data:
            sessions_col.update_one(
                {"dui": dui},
                {
                    "$set": {
                        "dui": dui,
                        "web_token": user.get("WebJwtToken") or user.get("JwtToken"),
                        "web_token_created_at": user.get("WebTokenCreatedAt") or user.get("TokenCreatedAt"),
                        "web_refresh_token": user.get("WebRefreshToken") or user.get("RefreshToken"),
                        "web_refresh_created_at": user.get("WebRefreshTokenCreatedAt") or user.get("RefreshTokenCreatedAt"),
                        "android_token": user.get("AndroidJwtToken"),
                        "android_token_created_at": user.get("AndroidTokenCreatedAt"),
                        "android_refresh_token": user.get("AndroidRefreshToken"),
                        "android_refresh_created_at": user.get("AndroidRefreshTokenCreatedAt"),
                        "android_session_imei": user.get("AndroidSessionImei"),
                        "last_web_login": user.get("LastWebLoginAt"),
                        "last_android_login": user.get("LastAndroidLoginAt"),
                        "updated_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
            migrated_sessions += 1

        update_set = {"updated_at": now}
        if full_name:
            update_set["FullName"] = full_name

        users_col.update_one(
            {"_id": user["_id"]},
            {
                "$set": update_set,
                "$unset": {field: "" for field in LEGACY_TOKEN_FIELDS},
            },
        )
        updated_users += 1

    users_col.create_index([("dui", 1)], unique=True, sparse=True)
    users_col.create_index([("username", 1)], unique=True, sparse=True)
    users_col.create_index([("email", 1)], unique=True, sparse=True)
    users_col.create_index([("is_active", 1)], sparse=True)
    users_col.create_index([("Dui", 1)], unique=True, sparse=True)
    users_col.create_index([("Username", 1)], unique=True, sparse=True)
    users_col.create_index([("Email", 1)], unique=True, sparse=True)
    users_col.create_index([("IsActive", 1)], sparse=True)

    sessions_col.create_index([("dui", 1)], unique=True)
    sessions_col.create_index([("updated_at", 1)], expireAfterSeconds=60 * 60 * 24 * 30)

    print(f"Usuarios actualizados: {updated_users}")
    print(f"Sesiones migradas: {migrated_sessions}")


if __name__ == "__main__":
    run()
