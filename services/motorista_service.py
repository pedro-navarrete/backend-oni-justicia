from database.verificador_mongo import ejecutar_query
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


class MotoristaService:
    """Servicio para datos maestros de motoristas en colección users."""

    COLLECTION = "users"

    @staticmethod
    def _get(user: dict, *keys: str):
        if not isinstance(user, dict):
            return None
        for key in keys:
            if key in user and user.get(key) is not None:
                return user.get(key)
        return None

    @staticmethod
    def get_dui(user: dict) -> str | None:
        value = MotoristaService._get(user, "dui", "Dui", "DUI")
        return str(value).strip() if value is not None else None

    @staticmethod
    def get_username(user: dict) -> str | None:
        value = MotoristaService._get(user, "username", "Username", "UserName")
        return str(value).strip() if value is not None else None

    @staticmethod
    def get_email(user: dict) -> str | None:
        value = MotoristaService._get(user, "email", "Email")
        return str(value).strip() if value is not None else None

    @staticmethod
    def get_oni(user: dict) -> str | None:
        value = MotoristaService._get(user, "oni", "Oni", "ONI")
        return str(value).strip() if value is not None else None

    @staticmethod
    def get_full_name(user: dict) -> str:
        full_name = MotoristaService._get(user, "FullName", "full_name")
        if isinstance(full_name, str) and full_name.strip():
            return full_name.strip()

        parts = [
            MotoristaService._get(user, "primer_nombre", "PrimerNombre"),
            MotoristaService._get(user, "segundo_nombre", "SegundoNombre"),
            MotoristaService._get(user, "primer_ape", "PrimerApe"),
            MotoristaService._get(user, "segundo_ape", "SegundoApe"),
        ]
        composed = " ".join(str(part).strip() for part in parts if part and str(part).strip())
        return composed.strip()

    @staticmethod
    def get_password_hash(user: dict) -> str:
        value = MotoristaService._get(user, "password_hash", "passwordHash", "PasswordHash")
        return str(value) if isinstance(value, str) else ""

    @staticmethod
    def is_active(user: dict) -> bool:
        value = MotoristaService._get(user, "is_active", "IsActive")
        return bool(value)

    @staticmethod
    def resolve_roles(user: dict) -> list[str]:
        roles = []
        raw_roles = MotoristaService._get(user, "roles", "Roles")
        if isinstance(raw_roles, list):
            for role in raw_roles:
                if isinstance(role, str):
                    clean_role = role.strip()
                    if clean_role and clean_role not in roles:
                        roles.append(clean_role)
        return roles

    @staticmethod
    def has_role(user: dict, role: str) -> bool:
        if not role:
            return False
        return role in MotoristaService.resolve_roles(user)

    @staticmethod
    def get_motorista_by_dui(dui: str) -> dict | None:
        users = ejecutar_query(MotoristaService.COLLECTION, {"$or": [{"dui": dui}, {"Dui": dui}]})
        return users[0] if users else None

    @staticmethod
    def get_motorista_by_email(email: str) -> dict | None:
        users = ejecutar_query(MotoristaService.COLLECTION, {"$or": [{"email": email}, {"Email": email}]})
        return users[0] if users else None

    @staticmethod
    def get_motorista_by_username(username: str) -> dict | None:
        users = ejecutar_query(
            MotoristaService.COLLECTION,
            {"$or": [{"username": username}, {"Username": username}, {"UserName": username}]},
        )
        return users[0] if users else None

    @staticmethod
    def get_motorista_by_any(identifier: str) -> dict | None:
        if not identifier or not isinstance(identifier, str):
            return None

        motorista = MotoristaService.get_motorista_by_username(identifier)
        if motorista:
            return motorista

        motorista = MotoristaService.get_motorista_by_dui(identifier)
        if motorista:
            return motorista

        return MotoristaService.get_motorista_by_email(identifier)

    @staticmethod
    def verify_password(user: dict, password: str) -> bool:
        return pwd_context.verify(password, MotoristaService.get_password_hash(user))

    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_context.hash(password)
