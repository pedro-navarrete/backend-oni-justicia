# services/vehiculo_service.py
from database.verificador_mongo import ejecutar_query, insert_document, update_document, delete_document
from models.models import Vehiculo, ActualizarVehiculoRequest
from typing import Optional, List

COLLECTION = "CatalogoDeVehiculos"

# -------------------- CRUD --------------------
def crear_vehiculo(data: Vehiculo) -> dict:
    """Crea un nuevo vehículo validando que no exista la placa"""
    # Validar duplicado
    exist = ejecutar_query(COLLECTION, {"placa": data.placa})
    if exist:
        return {"status": 400, "msg": "Vehículo duplicado, registro por placa no válido"}

    # Insertar
    doc = data.model_dump()
    inserted_id = insert_document(COLLECTION, doc)
    if inserted_id:
        return {"status": 200, "msg": "Registro completado con éxito"}
    else:
        return {"status": 500, "msg": "Error al registrar el vehículo"}


def obtener_datos_vehiculo(placa: str) -> Optional[dict]:
    """Buscar un vehículo por placa"""
    result = ejecutar_query(COLLECTION, {"placa": placa})
    if not result:
        return None
    result = result[0]
    result.pop("_id", None)

    return result

def actualizar_vehiculo(data: ActualizarVehiculoRequest) -> bool:
    """Actualiza solo los campos que vienen en el request"""
    placa = data.placa
    update_data = {k: v for k, v in data.model_dump(exclude={"placa"}).items() if v is not None}
    if not update_data:
        return False
    updated_count = update_document(COLLECTION, {"placa": placa}, {"$set": update_data})
    return updated_count > 0

def eliminar_vehiculo(placa: str) -> bool:
    """Elimina un vehículo por placa"""
    deleted_count = delete_document(COLLECTION, {"placa": placa})
    return deleted_count > 0


def listar_vehiculos() -> dict:
    """Retorna todos los vehículos"""
    documentos = ejecutar_query(COLLECTION, {})

    if not documentos:
        return {"mensaje": "No hay vehículos registrados"}

    vehiculos = []
    for doc in documentos:
        doc.pop("_id", None)  # eliminar _id
        vehiculos.append(doc)

    return {"vehiculos": vehiculos}


# -------------------- Validaciones --------------------
def EstadoVehiculo(placa: str) -> str:
    """Verifica el estado de un vehículo"""
    vehiculo = obtener_datos_vehiculo(placa)
    if not vehiculo:
        return "no_encontrado"
    return vehiculo.get("estado", "desconocido")
