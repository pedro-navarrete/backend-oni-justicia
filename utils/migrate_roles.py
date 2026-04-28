"""Migra usuarios existentes para poblar Roles[] y limpiar campos Role/Role2."""

from database.verificador_mongo import ejecutar_query, update_document
from services.user_service import UserService


def run() -> None:
    users = ejecutar_query(UserService.COLLECTION, {})
    migrated = 0

    for user in users:
        roles = UserService.resolve_roles(user)
        legacy_roles = [user.get("Role"), user.get("Role2")]
        for legacy_role in legacy_roles:
            if not isinstance(legacy_role, str):
                continue
            clean_role = legacy_role.strip()
            if clean_role and clean_role not in roles:
                roles.append(clean_role)

        updates = {"Roles": roles}
        if user.get("Role") is not None or user.get("Role2") is not None:
            update_document(
                UserService.COLLECTION,
                {"_id": user["_id"]},
                {"$set": updates, "$unset": {"Role": "", "Role2": ""}},
            )
            migrated += 1
        elif user.get("Roles") != roles:
            update_document(
                UserService.COLLECTION,
                {"_id": user["_id"]},
                {"$set": updates},
            )
            migrated += 1

    print(f"Usuarios evaluados: {len(users)}")
    print(f"Usuarios sincronizados: {migrated}")


if __name__ == "__main__":
    run()
