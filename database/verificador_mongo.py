# database/verificador_mongo.py
import os
import logging
from pymongo import MongoClient, errors
from dotenv import load_dotenv

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
load_dotenv()

# ---------------------------- Variables globales ----------------------------
_client = None
_db = None


def _validar_variables():
    """Valida que todas las variables de entorno estén presentes."""
    uri = os.getenv('DB_URI')  # Permite URI completa (opcional)
    if uri:
        return uri, None, None, None, None, None, None

    server = os.getenv('DB_HOST')
    port = os.getenv('DB_PORT')
    database = os.getenv('DB_NAME')
    username = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    auth_db = os.getenv('DB_AUTH_DB')

    missing = [var for var, val in {
        'DB_HOST': server,
        'DB_PORT': port,
        'DB_NAME': database,
        'DB_USER': username,
        'DB_PASSWORD': password,
        'DB_AUTH_DB': auth_db
    }.items() if not val]

    if missing:
        raise EnvironmentError(f"Faltan variables en .env: {', '.join(missing)}")

    return None, server, int(port), database, username, password, auth_db


def init_mongo():
    """Inicializa la conexión global a MongoDB si no existe."""
    global _client, _db
    if _client is not None:
        return  # Ya está inicializado

    uri, server, port, database, username, password, auth_db = _validar_variables()

    try:
        if uri:
            # Conexión mediante cadena completa (DB_URI)
            _client = MongoClient(uri)
            database = os.getenv('DB_NAME') or 'admin'
            logging.info("Conectando con cadena URI a MongoDB")
            logging.info(uri)
        else:
            # Conexión mediante variables separadas
            _client = MongoClient(
                host=server,
                port=port,
                username=username,
                password=password,
                authSource=auth_db,
                serverSelectionTimeoutMS=5000,
                maxPoolSize=50,
                minPoolSize=1,
                retryWrites=True
            )
            logging.info(f"Conectando a MongoDB en {server}:{port}")

        # Verificar conexión con ping
        _client.admin.command('ping')

        # Asignar base de datos activa
        _db = _client[database]

        logging.info(f"Conexión persistente establecida con la base de datos '{database}'")

    except errors.ConnectionFailure as e:
        logging.error(f"No se pudo conectar a MongoDB: {e}")
        raise
    except Exception as e:
        logging.error(f"Error conectando a MongoDB: {e}")
        raise


def get_db():
    """Devuelve la base de datos inicializada."""
    if _db is None:
        init_mongo()
    return _db



# ---------------------------- Operaciones CRUD ----------------------------
def ejecutar_query(collection_name: str, filtro: dict = None) -> list[dict]:
    filtro = filtro or {}
    try:
        resultados = list(get_db()[collection_name].find(filtro))
        logging.info(f"Consulta ejecutada en '{collection_name}', documentos obtenidos: {len(resultados)}")
        return resultados
    except Exception as e:
        logging.error(f"Error ejecutando consulta: {e}")
        return []

def ejecutar_query_V2(collection_name: str, filtro: dict = None, projection: dict = None) -> list[dict]:
    """
    Ejecuta una consulta en MongoDB y devuelve una lista de diccionarios.
    Por defecto excluye el campo '_id' para evitar errores al serializar.
    """
    filtro = filtro or {}
    if projection is None:
        projection = {"_id": 0}  # Excluir _id por defecto

    try:
        resultados = list(get_db()[collection_name].find(filtro, projection))
        logging.info(f"Consulta ejecutada en '{collection_name}', documentos obtenidos: {len(resultados)}")
        return resultados
    except Exception as e:
        logging.error(f"Error ejecutando consulta: {e}")
        return []


def ejecutar_query_V3(
        collection_name: str,
        filtro: dict = None,
        projection: dict = None,
        skip: int = 0,
        limit: int = 20,
        sort: list[tuple] = None  # <-- nuevo parámetro
) -> list[dict]:
    """
    Ejecuta una consulta en MongoDB con soporte de paginación y ordenamiento.

    Parámetros:
        - collection_name: nombre de la colección.
        - filtro: dict con condiciones de búsqueda.
        - projection: dict con campos a incluir/excluir.
        - skip: cantidad de documentos a omitir (para paginación).
        - limit: cantidad máxima de documentos a retornar.
        - sort: lista de tuplas (campo, 1/-1) para ordenar.

    Devuelve una lista de diccionarios (por defecto excluye '_id').
    """
    filtro = filtro or {}
    projection = projection or {"_id": 0}  # Excluir _id por defecto

    try:
        cursor = get_db()[collection_name].find(filtro, projection)
        if sort:
            cursor = cursor.sort(sort)  # aplicar ordenamiento
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)

        resultados = list(cursor)
        logging.info(
            f"Consulta ejecutada en '{collection_name}', documentos obtenidos: {len(resultados)} (skip={skip}, limit={limit})")
        return resultados
    except Exception as e:
        logging.error(f"Error ejecutando consulta en '{collection_name}': {e}")
        return []

def ejecutar_query_V4(collection_name: str, filtro: dict = None, projection: dict = None) -> list[dict]:
    """
    Ejecuta una consulta en MongoDB y devuelve una lista de diccionarios.
    Por defecto excluye el campo '_id' para evitar errores al serializar.
    """
    filtro = filtro or {}
    if projection is None:
        projection = {
            "_id": 0,
            "Coordenadas": 0
        }

    try:
        resultados = list(get_db()[collection_name].find(filtro, projection))
        logging.info(f"Consulta ejecutada en '{collection_name}', documentos obtenidos: {len(resultados)}")
        return resultados
    except Exception as e:
        logging.error(f"Error ejecutando consulta: {e}")
        return []

def insert_document(collection_name: str, data: dict) -> str | None:
    try:
        result = get_db()[collection_name].insert_one(data)
        logging.info(f"Documento insertado en '{collection_name}' con _id: {result.inserted_id}")
        return str(result.inserted_id)
    except Exception as e:
        logging.error(f"Error insertando documento: {e}")
        return None


def insert_many_documents(collection_name: str, data_list: list[dict]) -> list[str]:
    try:
        result = get_db()[collection_name].insert_many(data_list)
        logging.info(f"{len(result.inserted_ids)} documentos insertados en '{collection_name}'")
        return [str(_id) for _id in result.inserted_ids]
    except Exception as e:
        logging.error(f"Error insertando documentos: {e}")
        return []


def update_document(collection_name: str, filtro: dict, update: dict, multiple: bool = False) -> int:
    try:
        result = (
            get_db()[collection_name].update_many(filtro, update)
            if multiple else
            get_db()[collection_name].update_one(filtro, update)
        )
        logging.info(f"{result.modified_count} documento(s) actualizados en '{collection_name}'")
        return result.modified_count
    except Exception as e:
        logging.error(f"Error actualizando documentos: {e}")
        return 0

def update_document2(collection_name: str, filtro: dict, update: dict, multiple: bool = False, upsert: bool = False) -> int:
    try:
        if multiple:
            result = get_db()[collection_name].update_many(filtro, update, upsert=upsert)
        else:
            result = get_db()[collection_name].update_one(filtro, update, upsert=upsert)
        logging.info(f"{result.modified_count} documento(s) actualizados en '{collection_name}'")
        return result.modified_count
    except Exception as e:
        logging.error(f"Error actualizando documentos: {e}")
        return 0



def delete_document(collection_name: str, filtro: dict, multiple: bool = False) -> int:
    try:
        result = (
            get_db()[collection_name].delete_many(filtro)
            if multiple else
            get_db()[collection_name].delete_one(filtro)
        )
        logging.info(f"{result.deleted_count} documento(s) eliminados de '{collection_name}'")
        return result.deleted_count
    except Exception as e:
        logging.error(f"Error eliminando documentos: {e}")
        return 0


# ---------------------------- Operaciones avanzadas ----------------------------
def aggregate(collection_name: str, pipeline: list[dict]) -> list[dict]:
    try:
        resultados = list(get_db()[collection_name].aggregate(pipeline))
        logging.info(f"Agregación ejecutada en '{collection_name}', documentos obtenidos: {len(resultados)}")
        return resultados
    except Exception as e:
        logging.error(f"Error ejecutando agregación: {e}")
        return []


def count_documents(collection_name: str, filtro: dict = None) -> int:
    filtro = filtro or {}
    try:
        count = get_db()[collection_name].count_documents(filtro)
        logging.info(f"Conteo en '{collection_name}': {count} documento(s) encontrados")
        return count
    except Exception as e:
        logging.error(f"Error contando documentos: {e}")
        return 0