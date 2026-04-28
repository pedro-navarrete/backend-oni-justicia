import os
from datetime import datetime
import pytz
from dotenv import load_dotenv
from database.verificador_mongo import ejecutar_query, insert_document
from services.user_service import UserService  # ✅ Importamos tu servicio que usa Argon2

# Cargar variables de entorno
load_dotenv()

# Leer zona horaria desde .env o usar default
TIMEZONE_STR = os.getenv("TIMEZONE", "America/El_Salvador").strip().replace('"', '')
try:
    TIMEZONE = pytz.timezone(TIMEZONE_STR)
except pytz.UnknownTimeZoneError:
    TIMEZONE = pytz.timezone("America/El_Salvador")


def crear_usuario_test(
    dui="06003338-0",
    oni="ONI-0005",
    username="pedro",
    password="Test1234!",
    full_name="Pedro Navarrete",
    email="pedro.navarrete@seguridad.gob.sv",
    role="WEB_USER"
):
    """
    Crea un usuario de prueba en MongoDB si no existe.
    Usa Argon2 para hashear la contraseña.
    """

    # 1. Verificar si ya existe
    existente = ejecutar_query("users", {"Username": username})
    if existente:
        print(f"El usuario '{username}' ya existe con _id: {existente[0]['_id']}")
        return str(existente[0]["_id"])

    # 2. Hashear la contraseña con Argon2 (usando tu servicio)
    password_hash = UserService.hash_password(password)

    # 3. Obtener timestamp con zona horaria
    now = datetime.now(TIMEZONE)

    # 4. Crear el documento del usuario
    usuario = {
        "Dui": dui,
        "Oni": oni,
        "Roles": [role],
        "FullName": full_name,
        "Email": email,
        "Username": username,
        "PasswordHash": password_hash,
        "IsActive": True,
        "CreatedAt": now,
        "UpdatedAt": None
    }

    # 5. Insertar en MongoDB
    inserted_id = insert_document("users", usuario)
    if inserted_id:
        print(f"✅ Usuario creado con _id: {inserted_id}")
    else:
        print("❌ Error creando el usuario")

    return inserted_id


if __name__ == "__main__":
    crear_usuario_test()
