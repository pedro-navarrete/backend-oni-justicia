# services/verificar_services.py
import logging
from starlette.responses import JSONResponse
from database.verificador_mongo import ejecutar_query

USERS_COLLECTION = "users"
VEHICULOS_COLLECTION = "CatalogoDeVehiculos"

logger = logging.getLogger(__name__)


def verificar_dui(dui: str):
    if not dui:
        logger.warning("Validación DUI fallida: DUI vacío")
        return JSONResponse(
            status_code=400,
            content={"status": 400, "detail": "DUI es requerido"}
        )

    logger.info(f"Validando DUI: {dui}")

    usuarios = ejecutar_query(USERS_COLLECTION, {"$or": [{"dui": dui}, {"Dui": dui}]})

    if not usuarios:
        logger.warning(f"DUI no encontrado: {dui}")
        return JSONResponse(
            status_code=404,
            content={"status": 404, "detail": f"DUI {dui} no encontrado"}
        )

    user = usuarios[0] if usuarios else {}
    if not bool(user.get("is_active", user.get("IsActive", False))):
        logger.error(f"Usuario inactivo: {dui}")
        return JSONResponse(
            status_code=403,
            content={
                "status": 403,
                "detail": f"El usuario con DUI {dui} está inactivo"
            }
        )

    logger.info(f"DUI válido y activo: {dui}")
    return None


def verificar_placa(placa: str):
    if not placa:
        logger.warning("Validación placa fallida: placa vacía")
        return JSONResponse(
            status_code=400,
            content={"status": 400, "detail": "Placa es requerida"}
        )

    logger.info(f"Validando placa: {placa}")

    vehiculos = ejecutar_query(VEHICULOS_COLLECTION, {"placa": placa})

    if not vehiculos:
        logger.warning(f"Placa no encontrada: {placa}")
        return JSONResponse(
            status_code=404,
            content={
                "type": "placa",
                "status": 404,
                "detail": f"Placa no regsitrada"
            }
        )

    logger.info(f"Placa válida: {placa}")
    return None  # éxito


def verificar_dui_placa(dui: str, placa: str):
    logger.info(f"Validación conjunta DUI+Placa | {dui} | {placa}")

    resp = verificar_dui(dui)
    if resp:
        return resp

    resp = verificar_placa(placa)
    if resp:
        return resp

    logger.info("Validación conjunta exitosa")
    return None
