# services/solicitud_edicion_service.py
import asyncio
import json
import os
import uuid
import logging
import websockets
import re
from datetime import datetime, date, timezone
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from fastapi import HTTPException
from database.verificador_mongo import ejecutar_query, insert_document, update_document, get_db, ejecutar_query_V3
from models.edicion_models import *

# Colecciones
COLLECTION_MISIONES = "Misiones"
COLLECTION_SOLICITUDES = "SolicitudesEdicionMision"
COLLECTION_BITACORA = "BitacoraCambiosMision"
COLLECTION_USERS = "users"

load_dotenv()
logger = logging.getLogger(__name__)


# Configuración desde ENV
WEBSOCKET_URL = os.getenv("WEBSOCKET_URL")
WEBSOCKET_TOKEN = os.getenv("WEBSOCKET_TOKEN")

if not WEBSOCKET_URL or not WEBSOCKET_TOKEN:
    raise RuntimeError("WEBSOCKET_URL o WEBSOCKET_TOKEN no están configurados en el entorno")


# ---------------- Serializador JSON ----------------
def json_serializer(obj: Any):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Tipo no serializable: {type(obj)}")

# ---------------- Envío WebSocket ----------------
async def enviar_por_websocket(
    category: str,
    data: Dict[str, Any],
):
    """
    Envía un mensaje estructurado por WebSocket.

    Estructura enviada:
    {
        "category": "<category>",
        "data": { ... }
    }
    """

    payload = {
        "category": category,
        "data": data
    }

    ws_url = f"{WEBSOCKET_URL}?token={WEBSOCKET_TOKEN}"

    try:
        logger.info("Conectando a WebSocket: %s", ws_url)
        async with websockets.connect(ws_url) as websocket:
            await websocket.send(
                json.dumps(payload, default=json_serializer)
            )

            print(payload)

            logger.info(
                "Mensaje WebSocket enviado | category=%s", category
            )

    except Exception as e:
        logger.exception("Error enviando mensaje por WebSocket")
        raise e

# ==================== SOLICITAR EDICIÓN ====================
def solicitar_edicion_mision(data: SolicitarEdicionMision, current_user: dict) -> str:
    """
    Crea una solicitud para editar una misión.
    Requiere: NoMision o IdMision, DUI del solicitante y descripción.
    """



    # Validar que se proporcione al menos uno
    if not data.no_mision and not data.id_mision:
        raise HTTPException(
            status_code=400,
            detail="Debe proporcionar NoMision o IdMision"
        )

    # Buscar la misión
    filtro_mision = {}
    if data.id_mision:
        filtro_mision["IdMision"] = data.id_mision
    elif data.no_mision:
        filtro_mision["NoMision"] = data.no_mision

    misiones = ejecutar_query(COLLECTION_MISIONES, filtro_mision)
    print(misiones)
    kiloIncial = misiones[0]["KilometrajeInicial"]
    print(kiloIncial)

    if not misiones:
        raise HTTPException(
            status_code=404,
            detail="Misión no encontrada"
        )

    mision = misiones[0]


    # Verificar que el usuario existe
    user = get_db()[COLLECTION_USERS].find_one({"Dui": data.dui_solicitante})
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"Usuario con DUI {data.dui_solicitante} no registrado"
        )

    # Verificar si ya existe una solicitud pendiente para esta misión
    solicitud_existente = ejecutar_query(COLLECTION_SOLICITUDES, {
        "NoMision": mision["NoMision"],
        "type": "mision_edicion",
        "status": "pending"
    })

    if solicitud_existente:
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe una solicitud pendiente para la misión {mision['NoMision']}"
        )

    # Crear la solicitud
    id_solicitud = str(uuid.uuid4())

    documento_solicitud = {
        "IdSolicitud": id_solicitud,
        "type": "mision_edicion",
        "NoMision": mision["NoMision"],
        "IdMision": mision["IdMision"],
        "Placa": mision.get("Placa"),
        "Dui": mision.get("Dui"),
        "requested_by": {
            "dui": user.get("Dui"),
            "name": user.get("FullName")
        },
        #"requested_changes": data.descripcion,
        "kilometraje_inicial_anterior": kiloIncial,
        "requested_changes_KilometrajeInicial": data.kilometraje_inicial,
        "status": "pending",  # pending, approved, rejected
        "reviewed_by": None,
        "review_observations": None,
        "created_at": datetime.now(timezone.utc),
        "reviewed_at": None
    }

    insert_document(COLLECTION_SOLICITUDES, documento_solicitud)

    logger.info(f"Solicitud de edición creada: {id_solicitud} para misión {mision['NoMision']}")

    # ========== ENVÍO POR WEBSOCKET ==========
    try:
        ws_data = {
            "IdSolicitud": id_solicitud,
            "NoMision": mision["NoMision"],
            "Placa": mision.get("Placa"),
            "Dui": mision.get("Dui"),
            "solicitante": user.get("FullName"),
            "dui_solicitante": user.get("Dui"),
            #"descripcion": data.descripcion,
            "status": "pending",
            "fecha_solicitud": documento_solicitud["created_at"]
        }

        asyncio.run(
            enviar_por_websocket(
                category="solicitud_creada",
                data=ws_data
            )
        )
        logger.info(f"Notificación WebSocket enviada para solicitud {id_solicitud}")
    except Exception as e:
        logger.error(f"Error enviando notificación WebSocket: {e}")
        # No falla la operación si falla el WebSocket

    return id_solicitud


# ==================== APROBAR/RECHAZAR SOLICITUD ====================
def aprobar_rechazar_solicitud(data: AprobarRechazarSolicitud) -> Dict[str, Any]:
    """
    Aprueba o rechaza una solicitud de edición de misión.
    """

    # Buscar la solicitud
    solicitudes = ejecutar_query(COLLECTION_SOLICITUDES, {"IdSolicitud": data.id_solicitud})

    if not solicitudes:
        raise HTTPException(
            status_code=404,
            detail="Solicitud no encontrada"
        )

    solicitud = solicitudes[0]

    # Verificar que esté pendiente
    if solicitud["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"La solicitud ya fue {solicitud['status']}"
        )

    # Verificar que el revisor existe
    revisor = get_db()[COLLECTION_USERS].find_one({"Dui": data.dui_revisor})
    if not revisor:
        raise HTTPException(
            status_code=404,
            detail=f"Revisor con DUI {data.dui_revisor} no encontrado"
        )

    # Determinar el nuevo estado
    nuevo_estado = "approved" if data.accion == "aprobar" else "rejected"

    # Actualizar la solicitud
    actualizacion = {
        "status": nuevo_estado,
        "reviewed_by": {
            "dui": revisor.get("Dui"),
            "name": revisor.get("FullName")
        },
        "review_observations": data.observaciones,
        "reviewed_at": datetime.now(timezone.utc)
    }

    updated_count = update_document(
        COLLECTION_SOLICITUDES,
        {"IdSolicitud": data.id_solicitud},
        {"$set": actualizacion}
    )

    if updated_count <= 0:
        raise HTTPException(
            status_code=500,
            detail="No se pudo actualizar la solicitud"
        )

    logger.info(f"Solicitud {data.id_solicitud} {nuevo_estado} por {revisor.get('FullName')}")

    # Si la solicitud corresponde a una factura, actualizar el campo SolicitudActiva en la factura
    try:
        # Sólo intentamos si la solicitud tiene referencia a IdFactura
        if solicitud.get("IdFactura"):
            misiones = ejecutar_query(COLLECTION_MISIONES, {"IdMision": solicitud.get("IdMision")})
            if misiones:
                m = misiones[0]
                facturas = m.get("Facturas", [])
                changed = False
                for idx, f in enumerate(facturas):
                    if f.get("IdFactura") == solicitud.get("IdFactura"):
                        # Construir objeto SolicitudActiva actualizado
                        # incluir el tipo de solicitud y metadata de revisión
                        solicitud_activa = {
                            "IdSolicitud": solicitud.get("IdSolicitud"),
                            "type": solicitud.get("type"),
                            "status": nuevo_estado,
                            "updated_at": datetime.now(timezone.utc),
                            "reviewed_by": {
                                "dui": revisor.get("Dui"),
                                "name": revisor.get("FullName")
                            },
                            "review_observations": data.observaciones
                        }
                        facturas[idx]["SolicitudActiva"] = solicitud_activa
                        changed = True
                        break

                if changed:
                    # Persistir cambio en la misión
                    update_document(
                        COLLECTION_MISIONES,
                        {"IdMision": m.get("IdMision")},
                        {"$set": {"Facturas": facturas, "TimeStampActualizacion": datetime.now(timezone.utc)}}
                    )
    except Exception:
        # No hacemos fallar la operación principal si falla esta actualización; sólo logueamos
        logger.exception("Error actualizando SolicitudActiva en la factura después de revisión")

    return {
        "id_solicitud": data.id_solicitud,
        "no_mision": solicitud["NoMision"],
        "status": nuevo_estado,
        "reviewed_by": revisor.get("FullName"),
        "reviewed_at": actualizacion["reviewed_at"]
    }


# ==================== EDITAR MISIÓN CON SOLICITUD APROBADA ====================
def editar_mision_aprobada(data: EditarMisionAprobada) -> Dict[str, Any]:
    """
    Edita una misión que tiene una solicitud aprobada.
    Guarda los cambios en la bitácora.
    """

    # Buscar la solicitud
    solicitudes = ejecutar_query(COLLECTION_SOLICITUDES, {"IdSolicitud": data.id_solicitud})

    if not solicitudes:
        raise HTTPException(
            status_code=404,
            detail="Solicitud no encontrada"
        )

    solicitud = solicitudes[0]

    # Verificar que esté aprobada
    if solicitud["status"] != "approved":
        raise HTTPException(
            status_code=403,
            detail=f"La solicitud debe estar aprobada. Estado actual: {solicitud['status']}"
        )

    # Verificar que el editor existe
    editor = get_db()[COLLECTION_USERS].find_one({"Dui": data.dui_editor})
    if not editor:
        raise HTTPException(
            status_code=404,
            detail=f"Editor con DUI {data.dui_editor} no encontrado"
        )

    # Buscar la misión
    misiones = ejecutar_query(COLLECTION_MISIONES, {"IdMision": solicitud["IdMision"]})

    if not misiones:
        raise HTTPException(
            status_code=404,
            detail="Misión no encontrada"
        )

    mision_original = misiones[0]

    # Preparar los cambios (solo campos con valores)
    cambios = {}
    campos_anteriores = {}

    mapeo_campos = {
        "kilometraje_inicial": "KilometrajeInicial",
        # "nombre_motorista": "NombreMotorista",
        # "marcador_tanque_inicial": "MarcadorTanqueInicial",
        # "solicitante": "Solicitante",
        # "fecha_hora_salida": "FechaHoraSalida",
        # "kilometraje_final": "KilometrajeFinal",
        # "marcador_tanque_final": "MarcadorTanqueFinal",
        # "fecha_hora_llegada": "FechaHoraLlegada",
        # "observacion_final": "ObservacionFinal"
    }

    # Construir diccionario de cambios
    for campo_modelo, campo_db in mapeo_campos.items():
        valor_nuevo = getattr(data, campo_modelo, None)
        if valor_nuevo is not None:
            valor_anterior = mision_original.get(campo_db)

            # Solo agregar si realmente cambió
            if valor_anterior != valor_nuevo:
                cambios[campo_db] = valor_nuevo
                campos_anteriores[campo_db] = valor_anterior

    if not cambios:
        raise HTTPException(
            status_code=400,
            detail="No hay cambios para aplicar"
        )

    # Agregar timestamp de actualización
    cambios["TimeStampActualizacion"] = datetime.now(timezone.utc)
    # No guardamos UltimaEdicionPor en la misión; la auditoría queda en la colección Solicitudes

    # Actualizar la misión
    updated_count = update_document(
        COLLECTION_MISIONES,
        {"IdMision": solicitud["IdMision"]},
        {"$set": cambios}
    )

    if updated_count <= 0:
        raise HTTPException(
            status_code=500,
            detail="No se pudo actualizar la misión"
        )

    # Guardar en bitácora
    _guardar_bitacora_cambios(
        mision_original=mision_original,
        campos_anteriores=campos_anteriores,
        campos_nuevos={k: v for k, v in cambios.items() if k in mapeo_campos.values()},
        solicitud=solicitud,
        editor=editor
    )

    # Marcar la solicitud como aplicada
    update_document(
        COLLECTION_SOLICITUDES,
        {"IdSolicitud": data.id_solicitud},
        {"$set": {
            "applied": True,
            "applied_at": datetime.now(timezone.utc),
            "applied_by": {
                "dui": editor.get("Dui"),
                "name": editor.get("FullName")
            }
        }}
    )

    logger.info(f"Misión {mision_original['NoMision']} editada por {editor.get('FullName')}")

    return {
        "no_mision": mision_original["NoMision"],
        "id_mision": mision_original["IdMision"],
        "campos_modificados": list(cambios.keys()),
        "editado_por": editor.get("FullName"),
        "fecha_edicion": cambios["TimeStampActualizacion"]
    }

# ==================== BITÁCORA DE CAMBIOS ====================
def _guardar_bitacora_cambios(
        mision_original: Dict,
        campos_anteriores: Dict,
        campos_nuevos: Dict,
        solicitud: Dict,
        editor: Dict
):
    """
    Guarda un registro en la bitácora de cambios.
    """

    id_bitacora = str(uuid.uuid4())

    documento_bitacora = {
        "IdBitacora": id_bitacora,
        "IdMision": mision_original["IdMision"],
        "NoMision": mision_original["NoMision"],
        "Placa": mision_original.get("Placa"),
        "Dui": mision_original.get("Dui"),
        "IdSolicitud": solicitud["IdSolicitud"],
        "cambios": [
            {
                "campo": campo,
                "valor_anterior": campos_anteriores.get(campo),
                "valor_nuevo": campos_nuevos.get(campo)
            }
            for campo in campos_nuevos.keys()
        ],
        "editado_por": {
            "dui": editor.get("Dui"),
            "name": editor.get("FullName")
        },
        "solicitado_por": solicitud["requested_by"],
        "aprobado_por": solicitud.get("reviewed_by"),
        "solicitud_type": solicitud.get("type"),
        "solicitud_status": solicitud.get("status"),
        "fecha_edicion": datetime.now(timezone.utc),
        "descripcion_solicitud": solicitud.get("requested_changes")
    }

    insert_document(COLLECTION_BITACORA, documento_bitacora)

    logger.info(f"Cambios guardados en bitácora: {id_bitacora}")


# ==================== CONSULTAS ====================
def obtener_solicitudes(
        status: Optional[str] = None,
        dui_solicitante: Optional[str] = None,
        no_mision: Optional[str] = None,
        id_solicitud: Optional[str] = None,
        page: int = 1,
        limit: int = 20
) -> Dict[str, Any]:
    """
    Obtiene solicitudes de edición con filtros.
    """

    filtro = {}

    if status:
        status = status.strip().lower()
        if status not in ["pending", "approved", "rejected"]:
            raise HTTPException(
                status_code=400,
                detail="Status debe ser: pending, approved o rejected"
            )
        filtro["status"] = status

    if dui_solicitante:
        filtro["requested_by.dui"] = dui_solicitante

    if no_mision:
        filtro["NoMision"] = no_mision

    if id_solicitud:
        filtro["IdSolicitud"] = id_solicitud

    skip = (page - 1) * limit
    sort = [("created_at", -1)]

    db = get_db()
    # cursor = db[COLLECTION_SOLICITUDES].find(filtro).skip(skip).limit(limit).sort(sort)
    cursor = ejecutar_query_V3(
        COLLECTION_SOLICITUDES,
        filtro=filtro,
        skip=skip,
        limit=limit,
        sort=sort
    )
    solicitudes = list(cursor)

    total = db[COLLECTION_SOLICITUDES].count_documents(filtro)
    total_pages = (total + limit - 1) // limit

    return {
        "count": total,
        "page": page,
        "total_pages": total_pages,
        "limit": limit,
        "solicitudes": solicitudes
    }


def obtener_solicitud_por_id(
        id_solicitud: str
) -> Dict[str, Any]:
    """
    Obtiene una solicitud de edición por IdSolicitud.
    """

    if not id_solicitud:
        raise HTTPException(
            status_code=400,
            detail="IdSolicitud es requerido"
        )

    filtro = {
        "IdSolicitud": id_solicitud
    }

    cursor = ejecutar_query_V3(
        COLLECTION_SOLICITUDES,
        filtro=filtro,
        limit=1
    )

    solicitudes = list(cursor)

    if not solicitudes:
        raise HTTPException(
            status_code=404,
            detail="Solicitud no encontrada"
        )

    return solicitudes[0]


def _build_contains_regex(value: Optional[str]) -> Optional[Dict[str, str]]:
    """Construye una búsqueda case-insensitive tipo LIKE segura para Mongo."""
    if not value:
        return None

    text = value.strip()
    if not text:
        return None

    return {"$regex": re.escape(text), "$options": "i"}


def obtener_solicitudes_resumen(
        status: Optional[str] = None,
        no_mision: Optional[str] = None,
        dui: Optional[str] = None,
        conductor: Optional[str] = None,
        placa: Optional[str] = None,
        tipo_solicitud: Optional[str] = None,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        filtro_avanzado: Optional[str] = None,
        page: int = 1,
        limit: int = 20
) -> Dict[str, Any]:
    """
    Obtiene un resumen de solicitudes con los campos:
    - ID de Solicitud (IdSolicitud)
    - Número de misión (NoMision)
    - DUI
    - Estado de la solicitud (status)
    - Conductor (requested_by.name)
    - Número de placa (Placa)
    - Fecha de solicitud (created_at)
    - Tipo de solicitud (type)

    Filtros soportados:
    - status exacto
    - no_mision exacto
    - dui like
    - conductor like
    - placa like
    - tipo_solicitud (internamente en type o solicitud_type)
    - rango de fechas por created_at
    - filtro avanzado like interno por nombre, dui y placa
    """

    filtro: Dict[str, Any] = {}
    and_conditions = []

    if status:
        status = status.strip().lower()
        valid_status = ["pending", "approved", "rejected", "applied", "deleted"]
        if status not in valid_status:
            raise HTTPException(
                status_code=400,
                detail="Status debe ser: pending, approved, rejected, applied o deleted"
            )
        filtro["status"] = status

    if no_mision:
        no_mision_clean = no_mision.strip()
        if no_mision_clean:
            filtro["NoMision"] = no_mision_clean

    dui_like = _build_contains_regex(dui)
    if dui_like:
        filtro["Dui"] = dui_like

    conductor_like = _build_contains_regex(conductor)
    if conductor_like:
        filtro["requested_by.name"] = conductor_like

    placa_like = _build_contains_regex(placa)
    if placa_like:
        filtro["Placa"] = placa_like

    if tipo_solicitud:
        tipo_solicitud_clean = tipo_solicitud.strip().lower()
        if tipo_solicitud_clean:
            tipo_regex = {"$regex": f"^{re.escape(tipo_solicitud_clean)}$", "$options": "i"}
            and_conditions.append({
                "$or": [
                    {"type": tipo_regex},
                    {"solicitud_type": tipo_regex}
                ]
            })

    # Si viene una sola fecha, filtra exactamente ese día (UTC)
    if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
        raise HTTPException(
            status_code=400,
            detail="fecha_inicio no puede ser mayor que fecha_fin"
        )

    if fecha_inicio or fecha_fin:
        fecha_base_inicio = fecha_inicio or fecha_fin
        fecha_base_fin = fecha_fin or fecha_inicio

        # En este punto siempre hay al menos una fecha
        if fecha_base_inicio is None or fecha_base_fin is None:
            raise HTTPException(
                status_code=400,
                detail="Debe enviar fecha_inicio o fecha_fin"
            )

        inicio_dt = datetime.combine(fecha_base_inicio, datetime.min.time(), tzinfo=timezone.utc)
        fin_dt = datetime.combine(fecha_base_fin, datetime.max.time(), tzinfo=timezone.utc)

        filtro["created_at"] = {
            "$gte": inicio_dt,
            "$lte": fin_dt
        }

    texto_avanzado = _build_contains_regex(filtro_avanzado)
    if texto_avanzado:
        and_conditions.append({
            "$or": [
                {"requested_by.name": texto_avanzado},
                {"Dui": texto_avanzado},
                {"Placa": texto_avanzado}
            ]
        })

    if and_conditions:
        if filtro:
            and_conditions.insert(0, dict(filtro))
        filtro = {"$and": and_conditions} if len(and_conditions) > 1 else and_conditions[0]

    skip = (page - 1) * limit

    db = get_db()

    pipeline = [
        {"$match": filtro},
        {"$sort": {"created_at": -1}},
        {"$skip": skip},
        {"$limit": limit},
        {
            "$project": {
                "_id": 0,
                "NoMision": 1,
                "Dui": 1,
                "status": 1,
                "Conductor": "$requested_by.name",
                "Placa": 1,
                "FechaSolicitud": "$created_at",
                "IdSolicitud": 1,
                "type": {"$ifNull": ["$type", "$solicitud_type"]}
            }
        }
    ]

    cursor = db[COLLECTION_SOLICITUDES].aggregate(pipeline)
    solicitudes = list(cursor)

    total = db[COLLECTION_SOLICITUDES].count_documents(filtro)
    total_pages = (total + limit - 1) // limit

    return {
        "count": total,
        "page": page,
        "total_pages": total_pages,
        "limit": limit,
        "solicitudes": solicitudes
    }


def obtener_bitacora_mision(
        id_mision: Optional[str] = None,
        no_mision: Optional[str] = None,
        page: int = 1,
        limit: int = 20
) -> Dict[str, Any]:
    """
    Obtiene la bitácora de cambios de una misión.
    """

    if not id_mision and not no_mision:
        raise HTTPException(
            status_code=400,
            detail="Debe proporcionar IdMision o NoMision"
        )

    filtro = {}
    if id_mision:
        filtro["IdMision"] = id_mision
    elif no_mision:
        filtro["NoMision"] = no_mision

    skip = (page - 1) * limit
    sort = [("fecha_edicion", -1)]

    db = get_db()
    # cursor = db[COLLECTION_BITACORA].find(filtro).skip(skip).limit(limit).sort(sort)
    cursor = ejecutar_query_V3(
        COLLECTION_SOLICITUDES,
        filtro=filtro,
        skip=skip,
        limit=limit,
        sort=sort
    )
    bitacora = list(cursor)

    total = db[COLLECTION_BITACORA].count_documents(filtro)
    total_pages = (total + limit - 1) // limit

    return {
        "count": total,
        "page": page,
        "total_pages": total_pages,
        "limit": limit,
        "cambios": bitacora
    }


# ==================== SOLICITUDES PARA FACTURAS ====================
def solicitar_edicion_factura(data: SolicitarEdicionFactura, current_user: dict) -> str:
    """
    Crea una solicitud para editar una factura.
    """

    # Buscar la misión
    misiones = ejecutar_query(COLLECTION_MISIONES, {"IdMision": data.id_mision})
    if not misiones:
        raise HTTPException(
            status_code=404,
            detail="Misión no encontrada"
        )

    mision = misiones[0]
    facturas = mision.get("Facturas", [])

    # Buscar la factura
    # factura_encontrada = None
    # for factura in facturas:
    #     if factura.get("IdFactura") == data.id_factura:
    #         factura_encontrada = factura
    #         break

    # Buscar la factura
    factura_encontrada = None
    factura_index = None
    for idx, factura in enumerate(facturas):
        if factura.get("IdFactura") == data.id_factura:
            factura_encontrada = factura
            factura_index = idx
            break

    if not factura_encontrada:
        raise HTTPException(
            status_code=404,
            detail=f"Factura con ID {data.id_factura} no encontrada en la misión"
        )

    # Verificar que el usuario existe
    user = get_db()[COLLECTION_USERS].find_one({"Dui": data.dui_solicitante})
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"Usuario con DUI {data.dui_solicitante} no registrado"
        )

    # Verificar si ya existe una solicitud pendiente para esta factura
    solicitud_existente = ejecutar_query(COLLECTION_SOLICITUDES, {
        "IdFactura": data.id_factura,
        "type": "factura_edicion",
        "status": "pending"
    })

    if solicitud_existente:
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe una solicitud pendiente para esta factura"
        )

    # Preparar los cambios solicitados
    cambios_solicitados = {}
    if data.numero_factura is not None:
        cambios_solicitados["NumeroFactura"] = data.numero_factura
    if data.cantidad_galones is not None:
        cambios_solicitados["CantidadGalones"] = data.cantidad_galones
    if data.cantidad_dolares is not None:
        cambios_solicitados["CantidadDolares"] = data.cantidad_dolares
    if data.cupones is not None:
        cambios_solicitados["Cupones"] = [{"NumeroCupon": c.numero_cupon} for c in data.cupones]

    if not cambios_solicitados:
        raise HTTPException(
            status_code=400,
            detail="Debe especificar al menos un campo para editar"
        )

    # Crear la solicitud
    id_solicitud = str(uuid.uuid4())
    documento_solicitud = {
        "IdSolicitud": id_solicitud,
        "type": "factura_edicion",  # NUEVO CAMPO
        "NoMision": mision["NoMision"],
        "IdMision": mision["IdMision"],
        "IdFactura": data.id_factura,
        "Placa": mision.get("Placa"),
        "Dui": mision.get("Dui"),
        "requested_by": {
            "dui": user.get("Dui"),
            "name": user.get("FullName")
        },
        "descripcion": data.descripcion,
        "datos_actuales_factura": {
            "NumeroFactura": factura_encontrada.get("NumeroFactura"),
            "CantidadGalones": factura_encontrada.get("CantidadGalones"),
            "CantidadDolares": factura_encontrada.get("CantidadDolares"),
            "Cupones": factura_encontrada.get("Cupones", [])
        },
        "cambios_solicitados": cambios_solicitados,
        "status": "pending",
        "reviewed_by": None,
        "review_observations": None,
        "created_at": datetime.now(timezone.utc),
        "reviewed_at": None
    }

    insert_document(COLLECTION_SOLICITUDES, documento_solicitud)
    logger.info(f"Solicitud de edición de factura creada: {id_solicitud}")

    # Guardar un objeto SolicitudActiva completo en la factura (incluye type)
    facturas[factura_index]["SolicitudActiva"] = {
        "IdSolicitud": id_solicitud,
        "type": documento_solicitud["type"],
        "status": "pending",
        "created_at": documento_solicitud["created_at"]
    }

    # Actualizar la misión con el campo SolicitudActiva
    updated_count = update_document(
        COLLECTION_MISIONES,
        {"IdMision": data.id_mision},
        {
            "$set": {
                "Facturas": facturas,
                "TimeStampActualizacion": datetime.now(timezone.utc)
            }
        }
    )

    if updated_count <= 0:
        raise HTTPException(
            status_code=500,
            detail="No se pudo actualizar el campo SolicitudActiva en la factura"
        )

    logger.info(f"Campo SolicitudActiva actualizado en factura {data.id_factura}")

    # Envío por WebSocket
    try:
        ws_data = {
            "IdSolicitud": id_solicitud,
            "type": "factura_edicion",
            "NoMision": mision["NoMision"],
            "IdFactura": data.id_factura,
            "solicitante": user.get("FullName"),
            "descripcion": data.descripcion,
            "status": "pending",
            "fecha_solicitud": documento_solicitud["created_at"]
        }
        asyncio.run(
            enviar_por_websocket(
                category="solicitud_factura_creada",
                data=ws_data
            )
        )
    except Exception as e:
        logger.error(f"Error enviando notificación WebSocket: {e}")

    return id_solicitud


def solicitar_eliminacion_factura(data: SolicitarEliminacionFactura, current_user: dict) -> str:
    """
    Crea una solicitud para eliminar una factura.
    """

    # Buscar la misión
    misiones = ejecutar_query(COLLECTION_MISIONES, {"IdMision": data.id_mision})
    if not misiones:
        raise HTTPException(
            status_code=404,
            detail="Misión no encontrada"
        )

    mision = misiones[0]
    facturas = mision.get("Facturas", [])

    # Buscar la factura
    # factura_encontrada = None
    # for factura in facturas:
    #     if factura.get("IdFactura") == data.id_factura:
    #         factura_encontrada = factura
    #         break

    # Buscar la factura
    factura_encontrada = None
    factura_index = None
    for idx, factura in enumerate(facturas):
        if factura.get("IdFactura") == data.id_factura:
            factura_encontrada = factura
            factura_index = idx
            break

    if not factura_encontrada:
        raise HTTPException(
            status_code=404,
            detail=f"Factura con ID {data.id_factura} no encontrada en la misión"
        )

    # Verificar que el usuario existe
    user = get_db()[COLLECTION_USERS].find_one({"Dui": data.dui_solicitante})
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"Usuario con DUI {data.dui_solicitante} no registrado"
        )

    # Verificar si ya existe una solicitud pendiente para esta factura
    solicitud_existente = ejecutar_query(COLLECTION_SOLICITUDES, {
        "IdFactura": data.id_factura,
        "type": "factura_eliminacion",
        "status": "pending"
    })

    if solicitud_existente:
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe una solicitud pendiente para eliminar esta factura"
        )

    # Crear la solicitud
    id_solicitud = str(uuid.uuid4())
    documento_solicitud = {
        "IdSolicitud": id_solicitud,
        "type": "factura_eliminacion",  # NUEVO CAMPO
        "NoMision": mision["NoMision"],
        "IdMision": mision["IdMision"],
        "IdFactura": data.id_factura,
        "Placa": mision.get("Placa"),
        "Dui": mision.get("Dui"),
        "requested_by": {
            "dui": user.get("Dui"),
            "name": user.get("FullName")
        },
        "descripcion": data.descripcion,
        "datos_actuales_factura": {
            "NumeroFactura": factura_encontrada.get("NumeroFactura"),
            "CantidadGalones": factura_encontrada.get("CantidadGalones"),
            "CantidadDolares": factura_encontrada.get("CantidadDolares"),
            "FechaFactura": factura_encontrada.get("FechaFactura"),
            "Cupones": factura_encontrada.get("Cupones", [])
        },
        "status": "pending",
        "reviewed_by": None,
        "review_observations": None,
        "created_at": datetime.now(timezone.utc),
        "reviewed_at": None
    }

    insert_document(COLLECTION_SOLICITUDES, documento_solicitud)
    logger.info(f"Solicitud de eliminación de factura creada: {id_solicitud}")

    # ========== ACTUALIZAR CAMPO SolicitudActiva EN LA FACTURA ==========
    # Guardamos un objeto completo para facilitar seguimiento (incluye type)
    facturas[factura_index]["SolicitudActiva"] = {
        "IdSolicitud": id_solicitud,
        "type": documento_solicitud["type"],
        "status": "pending",
        "created_at": documento_solicitud["created_at"]
    }

    # Actualizar la misión con el campo SolicitudActiva
    updated_count = update_document(
        COLLECTION_MISIONES,
        {"IdMision": data.id_mision},
        {
            "$set": {
                "Facturas": facturas,
                "TimeStampActualizacion": datetime.now(timezone.utc)
            }
        }
    )

    if updated_count <= 0:
        raise HTTPException(
            status_code=500,
            detail="No se pudo actualizar el campo SolicitudActiva en la factura"
        )

    logger.info(f"Campo SolicitudActiva actualizado en factura {data.id_factura}")

    # Envío por WebSocket
    try:
        ws_data = {
            "IdSolicitud": id_solicitud,
            "type": "factura_eliminacion",
            "NoMision": mision["NoMision"],
            "IdFactura": data.id_factura,
            "NumeroFactura": factura_encontrada.get("NumeroFactura"),
            "solicitante": user.get("FullName"),
            "descripcion": data.descripcion,
            "status": "pending",
            "fecha_solicitud": documento_solicitud["created_at"]
        }
        asyncio.run(
            enviar_por_websocket(
                category="solicitud_eliminacion_factura_creada",
                data=ws_data
            )
        )
    except Exception as e:
        logger.error(f"Error enviando notificación WebSocket: {e}")

    return id_solicitud


def editar_factura_aprobada(data: EditarFacturaAprobada) -> Dict[str, Any]:
    """
    Edita una factura con solicitud aprobada.
    """

    # Buscar la solicitud
    solicitudes = ejecutar_query(COLLECTION_SOLICITUDES, {"IdSolicitud": data.id_solicitud})
    if not solicitudes:
        raise HTTPException(
            status_code=404,
            detail="Solicitud no encontrada"
        )

    solicitud = solicitudes[0]

    # Verificar que sea del tipo correcto
    if solicitud.get("type") != "factura_edicion":
        raise HTTPException(
            status_code=400,
            detail=f"Esta solicitud es de tipo '{solicitud.get('type')}', no 'factura_edicion'"
        )

    # Verificar que esté aprobada
    if solicitud["status"] != "approved":
        raise HTTPException(
            status_code=403,
            detail=f"La solicitud debe estar aprobada. Estado actual: {solicitud['status']}"
        )

    # Verificar que el editor existe
    editor = get_db()[COLLECTION_USERS].find_one({"Dui": data.dui_editor})
    if not editor:
        raise HTTPException(
            status_code=404,
            detail=f"Editor con DUI {data.dui_editor} no encontrado"
        )

    # Buscar la misión y la factura
    misiones = ejecutar_query(COLLECTION_MISIONES, {"IdMision": solicitud["IdMision"]})
    if not misiones:
        raise HTTPException(
            status_code=404,
            detail="Misión no encontrada"
        )

    mision = misiones[0]
    facturas = mision.get("Facturas", [])

    # Buscar y modificar la factura
    factura_modificada = False
    cambios_aplicados = {}

    for factura in facturas:
        if factura.get("IdFactura") == solicitud["IdFactura"]:
            # Aplicar los cambios solicitados
            cambios_solicitados = solicitud.get("cambios_solicitados", {})

            for campo, valor_nuevo in cambios_solicitados.items():
                valor_anterior = factura.get(campo)
                factura[campo] = valor_nuevo
                cambios_aplicados[campo] = {
                    "anterior": valor_anterior,
                    "nuevo": valor_nuevo
                }

            # Agregar timestamp de edición
            factura["TimeStampActualizacion"] = datetime.now(timezone.utc)

            # Marcar la solicitud activa como aplicada en la factura
            # Incluir type y applied_at; no se guarda applied_by en la factura
            factura["SolicitudActiva"] = {
                "IdSolicitud": data.id_solicitud,
                "type": solicitud.get("type"),
                "status": "applied",
                "applied_at": datetime.now(timezone.utc)
            }

            # Asegurar estado de la factura
            factura["Estado"] = "active"

            factura_modificada = True
            break

    if not factura_modificada:
        raise HTTPException(
            status_code=404,
            detail="Factura no encontrada en la misión"
        )

    # Actualizar la misión
    updated_count = update_document(
        COLLECTION_MISIONES,
        {"IdMision": solicitud["IdMision"]},
        {"$set": {
            "Facturas": facturas,
            "TimeStampActualizacion": datetime.now(timezone.utc)
        }}
    )

    if updated_count <= 0:
        raise HTTPException(
            status_code=500,
            detail="No se pudo actualizar la misión"
        )

    # Guardar en bitácora
    _guardar_bitacora_factura(
        tipo_operacion="edicion",
        mision=mision,
        solicitud=solicitud,
        editor=editor,
        cambios=cambios_aplicados
    )

    # Marcar la solicitud como aplicada
    update_document(
        COLLECTION_SOLICITUDES,
        {"IdSolicitud": data.id_solicitud},
        {"$set": {
            "status": "applied",
            "applied": True,
            "applied_at": datetime.now(timezone.utc),
            "applied_by": {
                "dui": editor.get("Dui"),
                "name": editor.get("FullName")
            }
        }}
    )

    logger.info(f"Factura {solicitud['IdFactura']} editada por {editor.get('FullName')}")

    return {
        "no_mision": mision["NoMision"],
        "id_factura": solicitud["IdFactura"],
        "campos_modificados": list(cambios_aplicados.keys()),
        "editado_por": editor.get("FullName"),
        "fecha_edicion": datetime.now(timezone.utc)
    }


def eliminar_factura_aprobada(data: EliminarFacturaAprobada) -> Dict[str, Any]:
    """
    Elimina una factura con solicitud aprobada.
    """

    # Buscar la solicitud
    solicitudes = ejecutar_query(COLLECTION_SOLICITUDES, {"IdSolicitud": data.id_solicitud})
    if not solicitudes:
        raise HTTPException(
            status_code=404,
            detail="Solicitud no encontrada"
        )

    solicitud = solicitudes[0]

    # Verificar que sea del tipo correcto
    if solicitud.get("type") != "factura_eliminacion":
        raise HTTPException(
            status_code=400,
            detail=f"Esta solicitud es de tipo '{solicitud.get('type')}', no 'factura_eliminacion'"
        )

    # Verificar que esté aprobada
    if solicitud["status"] != "approved":
        raise HTTPException(
            status_code=403,
            detail=f"La solicitud debe estar aprobada. Estado actual: {solicitud['status']}"
        )

    # Verificar que el editor existe
    editor = get_db()[COLLECTION_USERS].find_one({"Dui": data.dui_editor})
    if not editor:
        raise HTTPException(
            status_code=404,
            detail=f"Editor con DUI {data.dui_editor} no encontrado"
        )

    # Buscar la misión y la factura
    misiones = ejecutar_query(COLLECTION_MISIONES, {"IdMision": solicitud["IdMision"]})
    if not misiones:
        raise HTTPException(
            status_code=404,
            detail="Misión no encontrada"
        )

    mision = misiones[0]
    facturas = mision.get("Facturas", [])

    # En lugar de eliminar la factura del array, la marcamos como eliminada
    # y dejamos el objeto en la misión (estado con valores)
    factura_eliminada = None
    for idx, factura in enumerate(facturas):
        if factura.get("IdFactura") == solicitud["IdFactura"]:
            # guardar una copia para bitácora
            factura_eliminada = dict(factura)
            # actualizar la factura in-place: estado y SolicitudActiva con type
            facturas[idx]["Estado"] = "deleted"
            facturas[idx]["SolicitudActiva"] = {
                "IdSolicitud": data.id_solicitud,
                "type": solicitud.get("type"),
                "status": "deleted",
                "applied_at": datetime.now(timezone.utc)
            }
            break

    # Persistir la misión con la factura marcada como eliminada
    updated_count = update_document(
        COLLECTION_MISIONES,
        {"IdMision": solicitud["IdMision"]},
        {"$set": {
            "Facturas": facturas,
            "TimeStampActualizacion": datetime.now(timezone.utc)
        }}
    )

    if updated_count <= 0:
        raise HTTPException(
            status_code=500,
            detail="No se pudo actualizar la misión"
        )

    # Guardar en bitácora
    _guardar_bitacora_factura(
        tipo_operacion="eliminacion",
        mision=mision,
        solicitud=solicitud,
        editor=editor,
        factura_eliminada=factura_eliminada
    )

    # Marcar la solicitud como aplicada
    update_document(
        COLLECTION_SOLICITUDES,
        {"IdSolicitud": data.id_solicitud},
        {"$set": {
            "status": "deleted",
            "applied": True,
            "applied_at": datetime.now(timezone.utc),
            "applied_by": {
                "dui": editor.get("Dui"),
                "name": editor.get("FullName")
            }
        }}
    )

    logger.info(f"Factura {solicitud['IdFactura']} eliminada por {editor.get('FullName')}")

    return {
        "no_mision": mision["NoMision"],
        "id_factura": solicitud["IdFactura"],
        "numero_factura": factura_eliminada.get("NumeroFactura") if factura_eliminada else None,
        "eliminado_por": editor.get("FullName"),
        "fecha_eliminacion": datetime.now(timezone.utc)
    }


def _guardar_bitacora_factura(
        tipo_operacion: str,  # "edicion" o "eliminacion"
        mision: Dict,
        solicitud: Dict,
        editor: Dict,
        cambios: Dict = None,
        factura_eliminada: Dict = None
):
    """
    Guarda un registro en la bitácora para operaciones de facturas.
    """
    id_bitacora = str(uuid.uuid4())

    documento_bitacora = {
        "IdBitacora": id_bitacora,
        "tipo_operacion": tipo_operacion,
        "tipo_registro": "factura",
        "IdMision": mision["IdMision"],
        "NoMision": mision["NoMision"],
        "Placa": mision.get("Placa"),
        "Dui": mision.get("Dui"),
        "IdSolicitud": solicitud["IdSolicitud"],
        "IdFactura": solicitud["IdFactura"],
        "editado_por": {
            "dui": editor.get("Dui"),
            "name": editor.get("FullName")
        },
        "solicitado_por": solicitud["requested_by"],
        "aprobado_por": solicitud.get("reviewed_by"),
        "solicitud_type": solicitud.get("type"),
        "solicitud_status": solicitud.get("status"),
        "fecha_operacion": datetime.now(timezone.utc)
    }

    if tipo_operacion == "edicion":
        documento_bitacora["cambios"] = cambios
        documento_bitacora["descripcion"] = solicitud.get("descripcion")
    elif tipo_operacion == "eliminacion":
        documento_bitacora["factura_eliminada"] = factura_eliminada
        documento_bitacora["descripcion"] = solicitud.get("descripcion")

    insert_document(COLLECTION_BITACORA, documento_bitacora)
    logger.info(f"Bitácora de factura guardada: {id_bitacora}")
