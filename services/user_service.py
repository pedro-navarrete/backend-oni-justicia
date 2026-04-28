# services/user_service.py
from typing import Optional
from database.verificador_mongo import ejecutar_query, ejecutar_query_V3, get_db
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

class UserService:
    """Servicio central para operaciones de usuarios"""

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
    def resolve_roles(user: dict) -> list[str]:
        """Resuelve roles únicamente desde Roles[]."""
        roles = []

        raw_roles = UserService._get(user, "roles", "Roles")
        if isinstance(raw_roles, list):
            for role in raw_roles:
                if isinstance(role, str) and role.strip() and role.strip() not in roles:
                    roles.append(role.strip())

        return roles

    @staticmethod
    def has_role(user: dict, role: str) -> bool:
        if not role:
            return False
        return role in UserService.resolve_roles(user)

    # ------------------ BUSQUEDAS ------------------
    @staticmethod
    def get_user_by_username(username: str) -> dict | None:
        """Obtiene un usuario por Username"""
        users = ejecutar_query(
            UserService.COLLECTION,
            {"$or": [{"username": username}, {"Username": username}, {"UserName": username}]},
        )
        return users[0] if users else None

    @staticmethod
    def get_user_by_dui(dui: str) -> dict | None:
        """Obtiene un usuario por Dui"""
        users = ejecutar_query(UserService.COLLECTION, {"$or": [{"dui": dui}, {"Dui": dui}]})
        return users[0] if users else None

    @staticmethod
    def get_user_by_oni(oni: str) -> dict | None:
        """Obtiene un usuario por Oni"""
        users = ejecutar_query(UserService.COLLECTION, {"$or": [{"oni": oni}, {"Oni": oni}, {"ONI": oni}]})
        return users[0] if users else None


    @staticmethod
    def get_user_by_username_or_dui(identifier: str) -> dict | None:
        """Busca usuario por Username o por Dui"""
        user = UserService.get_user_by_username(identifier)
        if not user:
            user = UserService.get_user_by_dui(identifier)
        return user

    @staticmethod
    def get_user_by_any(identifier: str) -> dict | None:
        """
        Busca un usuario por Username, DUI u ONI (en ese orden de prioridad).
        Args:identifier (str): Valor a buscar (puede ser username, dui u oni)
        Returns: dict | None: Documento del usuario si se encuentra, o None si no existe.
        """
        if not identifier or not isinstance(identifier, str):
            return None

        # Intentar por Username
        user = UserService.get_user_by_username(identifier)
        if user:
            return user

        # Intentar por DUI
        user = UserService.get_user_by_dui(identifier)
        if user:
            return user

        # Intentar por ONI
        user = UserService.get_user_by_oni(identifier)
        if user:
            return user

        # No encontrado
        return None

    # ------------------ PASSWORD ------------------
    @staticmethod
    def verify_password(user: dict, password: str) -> bool:
        """Verifica si el password coincide con el hash guardado"""
        password_hash = UserService._get(user, "password_hash", "passwordHash", "PasswordHash") or ""
        return pwd_context.verify(password, password_hash)

    @staticmethod
    def hash_password(password: str) -> str:
        """Genera hash de un password"""
        return pwd_context.hash(password)

    #---------------------Obtener todos los usuarios-------------------
    def get_motoristas_data(
            nombre: Optional[str] = None,
            dui: Optional[str] = None,
            cargo: Optional[str] = None,
            ubicacion: Optional[str] = None,
            page: int = 1,
            limit: int = 20
    ):
        """
        Devuelve motoristas (usuarios con Roles[] que incluye ANDROID_USER) filtrados y paginados desde MongoDB.
        """

        filtro = {
            "$or": [
                {"roles": "ANDROID_USER"},
                {"Roles": "ANDROID_USER"},
            ]
        }

        # === FILTROS ===
        or_filters = []
        if nombre:
            or_filters.append({"FullName": {"$regex": nombre, "$options": "i"}})
            or_filters.append({"full_name": {"$regex": nombre, "$options": "i"}})

        if dui:
            or_filters.append({"dui": {"$regex": dui, "$options": "i"}})
            or_filters.append({"Dui": {"$regex": dui, "$options": "i"}})

        if cargo:
            or_filters.append({"cargo_funcional": {"$regex": cargo, "$options": "i"}})
            or_filters.append({"cargo_nominal": {"$regex": cargo, "$options": "i"}})
            or_filters.append({"FunctionalPosition": {"$regex": cargo, "$options": "i"}})
            or_filters.append({"NominalPosition": {"$regex": cargo, "$options": "i"}})

        if ubicacion:
            or_filters.append({"ubicacion": {"$regex": ubicacion, "$options": "i"}})
            or_filters.append({"Location": {"$regex": ubicacion, "$options": "i"}})
            or_filters.append({"Location2": {"$regex": ubicacion, "$options": "i"}})

        if or_filters:
            filtro = {
                "$and": [
                    filtro,
                    {"$or": or_filters}
                ]
            }

        # === PAGINACIÓN ===
        skip = (page - 1) * limit
        sort = [("FullName", 1)]

        documentos = ejecutar_query_V3(
            UserService.COLLECTION,
            filtro=filtro,
            skip=skip,
            limit=limit,
            sort=sort
        )

        total_docs = get_db()[UserService.COLLECTION].count_documents(filtro)
        total_pages = (total_docs + limit - 1) // limit

        # === FORMATEO ===
        motoristas = []
        for u in documentos:
            motoristas.append({
                "Activo": bool(UserService._get(u, "is_active", "IsActive", "active")),
                "Usuario": UserService._get(u, "username", "Username", "UserName") or "",
                "DUI": UserService._get(u, "dui", "Dui", "DUI") or "",
                "Nombre": UserService._get(u, "FullName", "full_name") or "",
                "Teléfono": UserService._get(u, "telefono", "Telefono") or "",
                "IMEI": UserService._get(u, "imei", "Imei") or "",
                "Cargo Nominal": UserService._get(u, "cargo_nominal", "NominalPosition") or "",
                "Cargo Funcional": UserService._get(u, "cargo_funcional", "FunctionalPosition") or "",
                "Ubicación Física": UserService._get(u, "ubicacion", "Location") or "",
                "Ubicación Física 2": u.get("Location2", ""),

            })

        return {
            "status": 200,
            "data": {
                "count": total_docs,
                "page": page,
                "total_pages": total_pages,
                "limit": limit,
                "content": motoristas
            }
        }
