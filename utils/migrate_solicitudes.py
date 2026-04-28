"""
Script para migrar solicitudes existentes al formato estandarizado V2.

Convierte documentos del formato legacy (con campos como `kilometraje_inicial_anterior`,
`requested_changes_KilometrajeInicial`, `datos_actuales_factura`, `cambios_solicitados`)
al formato unificado que usa `datos_anteriores` y `datos_solicitados`.

Ejecutar con: python utils/migrate_solicitudes.py
"""

import logging
from datetime import datetime, timezone
from database.verificador_mongo import get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

COLLECTION_SOLICITUDES = "SolicitudesEdicionMision"


def migrar_solicitudes_a_formato_v2():
    """Migra todas las solicitudes existentes al nuevo formato estandarizado."""
    db = get_db()
    solicitudes = list(db[COLLECTION_SOLICITUDES].find({}))

    count_migradas = 0
    count_omitidas = 0
    count_errores = 0

    for solicitud in solicitudes:
        # Solo migrar si no tiene el nuevo formato
        if "datos_anteriores" in solicitud:
            count_omitidas += 1
            continue

        try:
            nuevo_formato = _convertir_a_formato_v2(solicitud)
            db[COLLECTION_SOLICITUDES].replace_one(
                {"_id": solicitud["_id"]},
                nuevo_formato
            )
            count_migradas += 1
            logger.info(f"Migrada solicitud {solicitud.get('IdSolicitud', solicitud['_id'])}")
        except Exception as e:
            count_errores += 1
            logger.error(
                f"Error migrando solicitud {solicitud.get('IdSolicitud', solicitud['_id'])}: {e}"
            )

    logger.info(
        f"Migración completada: {count_migradas} migradas, "
        f"{count_omitidas} omitidas (ya en v2), {count_errores} con errores."
    )
    return {"migradas": count_migradas, "omitidas": count_omitidas, "errores": count_errores}


def _convertir_a_formato_v2(solicitud_vieja: dict) -> dict:
    """Convierte una solicitud del formato legacy al nuevo formato estandarizado."""
    tipo = solicitud_vieja.get("type")

    # Extraer datos según el tipo de solicitud
    if tipo == "mision_edicion":
        datos_anteriores = {
            "KilometrajeInicial": solicitud_vieja.get("kilometraje_inicial_anterior")
        }
        datos_solicitados = {
            "KilometrajeInicial": solicitud_vieja.get("requested_changes_KilometrajeInicial")
        }
    elif tipo in ("factura_edicion", "factura_eliminacion"):
        datos_anteriores = solicitud_vieja.get("datos_actuales_factura", {})
        datos_solicitados = solicitud_vieja.get("cambios_solicitados", {})
    else:
        datos_anteriores = {}
        datos_solicitados = {}

    # Determinar metadata
    metadata = {
        "origen": _determinar_origen(solicitud_vieja),
        "flujo": _determinar_flujo(solicitud_vieja),
        "prioridad": "normal",
        "razon": "correccion"
    }

    # Construir nuevo formato manteniendo todos los campos originales
    nuevo = {
        **solicitud_vieja,
        "datos_anteriores": datos_anteriores,
        "datos_solicitados": datos_solicitados,
        "metadata": solicitud_vieja.get("metadata", metadata),
        "observaciones_adicionales": solicitud_vieja.get("observaciones_adicionales"),
        "applied": solicitud_vieja.get("applied", False),
        "applied_by": solicitud_vieja.get("applied_by"),
        "applied_at": solicitud_vieja.get("applied_at"),
        "TimeStampCreacion": solicitud_vieja.get("TimeStampCreacion") or solicitud_vieja.get("created_at"),
        "TimeStampActualizacion": solicitud_vieja.get("TimeStampActualizacion") or solicitud_vieja.get("created_at"),
        "auditoria": solicitud_vieja.get("auditoria", {
            "intentos_aprobacion": 0,
            "modificado_por": [],
            "ip_origen": None,
            "dispositivo": None
        })
    }

    # Eliminar campos legacy para limpiar el documento
    campos_legacy = [
        "kilometraje_inicial_anterior",
        "requested_changes_KilometrajeInicial",
        "datos_actuales_factura",
        "cambios_solicitados",
        "tipo_edicion",
        "solicitud_type"
    ]
    for campo in campos_legacy:
        nuevo.pop(campo, None)

    return nuevo


def _determinar_origen(solicitud: dict) -> str:
    """Determina el origen de una solicitud legacy."""
    if solicitud.get("tipo_edicion") == "direct":
        return "directo"
    solicitud_type = solicitud.get("solicitud_type", "").lower()
    if "directa" in solicitud_type:
        return "directo"
    return "manual"


def _determinar_flujo(solicitud: dict) -> str:
    """Determina el flujo de una solicitud legacy."""
    if solicitud.get("tipo_edicion") == "direct":
        return "simplificado"
    return "completo"


if __name__ == "__main__":
    print("🚀 Iniciando migración de solicitudes al formato V2...")
    resultado = migrar_solicitudes_a_formato_v2()
    print(
        f"✅ Migración completada: "
        f"{resultado['migradas']} migradas, "
        f"{resultado['omitidas']} ya en formato V2, "
        f"{resultado['errores']} errores."
    )
