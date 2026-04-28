# services/solicitud_edicion_service.py
import asyncio
import uuid
import logging
import re
from datetime import datetime, date, timezone
from typing import Optional, Dict, Any, List, Tuple
from dotenv import load_dotenv
from fastapi import HTTPException
from database.verificador_mongo import ejecutar_query, insert_document, update_document, get_db, ejecutar_query_V3
from models.edicion_models import *
from utils.websocket_client import enviar_por_websocket

# ==================== CONSTANTES ====================
COLLECTION_MISIONES = "Misiones"
COLLECTION_SOLICITUDES = "SolicitudesEdicionMision"
COLLECTION_BITACORA = "BitacoraCambiosMision"
COLLECTION_USERS = "users"


# Estados de solicitudes
class EstadoSolicitud:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    DELETED = "deleted"


# Tipos de solicitudes
class TipoSolicitud:
    MISION_EDICION = "mision_edicion"
    FACTURA_EDICION = "factura_edicion"
    FACTURA_ELIMINACION = "factura_eliminacion"


# Mapeo de campos de misión
MAPEO_CAMPOS_MISION = {
    "kilometraje_inicial": "KilometrajeInicial",
    # Agregar más campos cuando se necesiten
}

load_dotenv()
logger = logging.getLogger(__name__)


# ==================== FUNCIONES DE VALIDACIÓN ====================

def _validar_mision_existe(filtro_mision: Dict[str, str]) -> Dict[str, Any]:
    """
    Valida que exista una misión y la retorna.
    Lanza HTTPException si no existe.
    """
    misiones = ejecutar_query(COLLECTION_MISIONES, filtro_mision)

    if not misiones:
        raise HTTPException(
            status_code=404,
            detail="Misión no encontrada"
        )

    return misiones[0]


def _validar_usuario_existe(dui: str, rol_descripcion: str = "Usuario") -> Dict[str, Any]:
    """
    Valida que exista un usuario y lo retorna.
    Lanza HTTPException si no existe.
    """
    user = get_db()[COLLECTION_USERS].find_one({"Dui": dui})

    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"{rol_descripcion} con DUI {dui} no encontrado"
        )

    return user


def _validar_solicitud_existe(id_solicitud: str) -> Dict[str, Any]:
    """
    Valida que exista una solicitud y la retorna.
    Lanza HTTPException si no existe.
    """
    solicitudes = ejecutar_query(COLLECTION_SOLICITUDES, {"IdSolicitud": id_solicitud})

    if not solicitudes:
        raise HTTPException(
            status_code=404,
            detail="Solicitud no encontrada"
        )

    return solicitudes[0]


def _validar_solicitud_pendiente(solicitud: Dict[str, Any]) -> None:
    """
    Valida que una solicitud esté en estado pendiente.
    Lanza HTTPException si no lo está.
    """
    if solicitud["status"] != EstadoSolicitud.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"La solicitud ya fue {solicitud['status']}"
        )


def _validar_solicitud_aprobada(solicitud: Dict[str, Any]) -> None:
    """
    Valida que una solicitud esté aprobada.
    Lanza HTTPException si no lo está.
    """
    if solicitud["status"] != EstadoSolicitud.APPROVED:
        raise HTTPException(
            status_code=403,
            detail=f"La solicitud debe estar aprobada. Estado actual: {solicitud['status']}"
        )


def _validar_solicitud_no_aplicada(solicitud: Dict[str, Any]) -> None:
    """
    Valida que una solicitud no haya sido aplicada previamente.
    Lanza HTTPException si ya fue aplicada.
    """
    if solicitud.get("applied"):
        raise HTTPException(
            status_code=409,
            detail="Esta solicitud ya fue aplicada anteriormente"
        )


def _validar_no_existe_solicitud_pendiente(no_mision: str, tipo_solicitud: str,
                                           id_factura: Optional[str] = None) -> None:
    """
    Valida que no exista una solicitud pendiente para la misión/factura.
    Lanza HTTPException si existe.
    """
    filtro = {
        "type": tipo_solicitud,
        "status": EstadoSolicitud.PENDING
    }

    if id_factura:
        filtro["IdFactura"] = id_factura
    else:
        filtro["NoMision"] = no_mision

    solicitud_existente = ejecutar_query(COLLECTION_SOLICITUDES, filtro)

    if solicitud_existente:
        detalle = f"factura {id_factura}" if id_factura else f"misión {no_mision}"
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe una solicitud pendiente para la {detalle}"
        )


def _validar_tipo_solicitud(solicitud: Dict[str, Any], tipo_esperado: str) -> None:
    """
    Valida que la solicitud sea del tipo correcto.
    Lanza HTTPException si no coincide.
    """
    tipo_actual = solicitud.get("type")
    if tipo_actual != tipo_esperado:
        raise HTTPException(
            status_code=400,
            detail=f"Esta solicitud es de tipo '{tipo_actual}', no '{tipo_esperado}'"
        )


def _buscar_factura_en_mision(mision: Dict[str, Any], id_factura: str) -> Tuple[Optional[Dict], Optional[int]]:
    """
    Busca una factura en una misión y retorna la factura y su índice.
    Retorna (None, None) si no se encuentra.
    """
    facturas = mision.get("Facturas", [])

    for idx, factura in enumerate(facturas):
        if factura.get("IdFactura") == id_factura:
            return factura, idx

    return None, None


def _validar_factura_existe(mision: Dict[str, Any], id_factura: str) -> Tuple[Dict, int]:
    """
    Valida que exista una factura en la misión y retorna la factura y su índice.
    Lanza HTTPException si no existe.
    """
    factura, idx = _buscar_factura_en_mision(mision, id_factura)

    if factura is None:
        raise HTTPException(
            status_code=404,
            detail=f"Factura con ID {id_factura} no encontrada en la misión"
        )

    return factura, idx


# ==================== FUNCIONES AUXILIARES ====================

def _construir_filtro_mision(id_mision: Optional[str] = None, no_mision: Optional[str] = None) -> Dict[str, str]:
    """
    Construye el filtro para buscar una misión por ID o NoMision.
    """
    if id_mision:
        return {"IdMision": id_mision}
    elif no_mision:
        return {"NoMision": no_mision}
    else:
        raise HTTPException(
            status_code=400,
            detail="Debe proporcionar IdMision o NoMision"
        )


def _crear_info_usuario(user: Dict[str, Any]) -> Dict[str, str]:
    """
    Crea el objeto de información de usuario estándar.
    """
    return {
        "dui": user.get("Dui"),
        "name": user.get("FullName")
    }


def _actualizar_solicitud_activa_factura(
        mision: Dict[str, Any],
        factura_index: int,
        id_solicitud: str,
        tipo_solicitud: str,
        status: str,
        extra_data: Optional[Dict] = None
) -> None:
    """
    Actualiza el campo SolicitudActiva en una factura.
    """
    facturas = mision.get("Facturas", [])

    solicitud_activa = {
        "IdSolicitud": id_solicitud,
        "type": tipo_solicitud,
        "status": status,
        "updated_at": datetime.now(timezone.utc)
    }

    if extra_data:
        solicitud_activa.update(extra_data)

    facturas[factura_index]["SolicitudActiva"] = solicitud_activa

    # Actualizar la misión
    updated_count = update_document(
        COLLECTION_MISIONES,
        {"IdMision": mision.get("IdMision")},
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


def _build_contains_regex(value: Optional[str], max_length: int = 100) -> Optional[Dict[str, str]]:
    """
    Construye una búsqueda case-insensitive tipo LIKE segura para Mongo.
    """
    if not value:
        return None

    text = value.strip()
    if not text or len(text) > max_length:
        return None

    return {"$regex": re.escape(text), "$options": "i"}


def _marcar_solicitud_aplicada(id_solicitud: str, editor: Dict[str, Any]) -> None:
    """
    Marca una solicitud como aplicada.
    """
    update_document(
        COLLECTION_SOLICITUDES,
        {"IdSolicitud": id_solicitud},
        {"$set": {
            "applied": True,
            "applied_at": datetime.now(timezone.utc),
            "applied_by": _crear_info_usuario(editor)
        }}
    )


# ==================== NOTIFICACIONES WEBSOCKET ====================

def _enviar_notificacion_websocket(category: str, data: Dict[str, Any]) -> None:
    """
    Envía una notificación por WebSocket y maneja errores.
    """
    try:
        asyncio.run(enviar_por_websocket(category=category, data=data))
        logger.info(f"Notificación WebSocket enviada: {category}")
    except Exception as e:
        logger.error(f"Error enviando notificación WebSocket ({category}): {e}")
        # No fallar la operación principal por error en WebSocket


# ==================== SOLICITAR EDICIÓN DE MISIÓN ====================

def solicitar_edicion_mision(data: SolicitarEdicionMision, current_user: dict) -> str:
    """
    Crea una solicitud para editar una misión.
    Requiere: NoMision o IdMision, DUI del solicitante y kilometraje inicial.
    """
    # Construir filtro y buscar misión
    filtro_mision = _construir_filtro_mision(data.id_mision, data.no_mision)
    mision = _validar_mision_existe(filtro_mision)

    kilometraje_actual = mision.get("KilometrajeInicial")

    # Validar usuario
    user = _validar_usuario_existe(data.dui_solicitante, "Usuario solicitante")

    # Validar que no exista solicitud pendiente
    _validar_no_existe_solicitud_pendiente(
        mision["NoMision"],
        TipoSolicitud.MISION_EDICION
    )

    # Crear la solicitud
    id_solicitud = str(uuid.uuid4())

    datos_anteriores = {"KilometrajeInicial": kilometraje_actual}
    datos_solicitados = {"KilometrajeInicial": data.kilometraje_inicial}

    metadata = {
        "origen": data.origen or "manual",
        "flujo": data.flujo or "completo",
        "prioridad": "normal",
        "razon": data.razon or "correccion"
    }

    documento_solicitud = {
        "IdSolicitud": id_solicitud,
        "type": TipoSolicitud.MISION_EDICION,
        "NoMision": mision["NoMision"],
        "IdMision": mision["IdMision"],
        "Placa": mision.get("Placa"),
        "Dui": mision.get("Dui"),
        "requested_by": _crear_info_usuario(user),
        "descripcion": data.descripcion,
        "metadata": metadata,
        "datos_anteriores": datos_anteriores,
        "datos_solicitados": datos_solicitados,
        "observaciones_adicionales": None,
        "status": EstadoSolicitud.PENDING,
        "applied": False,
        "reviewed_by": None,
        "review_observations": None,
        "applied_by": None,
        "created_at": datetime.now(timezone.utc),
        "reviewed_at": None,
        "applied_at": None,
        "TimeStampCreacion": datetime.now(timezone.utc),
        "TimeStampActualizacion": datetime.now(timezone.utc),
        "auditoria": {
            "intentos_aprobacion": 0,
            "modificado_por": [],
            "ip_origen": None,
            "dispositivo": None
        }
    }

    insert_document(COLLECTION_SOLICITUDES, documento_solicitud)

    logger.info(
        f"Solicitud de edición creada: {id_solicitud} para misión {mision['NoMision']}",
        extra={"id_solicitud": id_solicitud, "dui_solicitante": user.get("Dui")}
    )

    # Notificación WebSocket
    _enviar_notificacion_websocket(
        category="solicitud_creada",
        data={
            "IdSolicitud": id_solicitud,
            "NoMision": mision["NoMision"],
            "Placa": mision.get("Placa"),
            "Dui": mision.get("Dui"),
            "solicitante": user.get("FullName"),
            "dui_solicitante": user.get("Dui"),
            "status": EstadoSolicitud.PENDING,
            "fecha_solicitud": documento_solicitud["created_at"]
        }
    )

    return id_solicitud


# ==================== APROBAR/RECHAZAR SOLICITUD ====================

def aprobar_rechazar_solicitud(data: AprobarRechazarSolicitud) -> Dict[str, Any]:
    """
    Aprueba o rechaza una solicitud de edición de misión.
    """
    # Buscar y validar solicitud
    solicitud = _validar_solicitud_existe(data.id_solicitud)
    _validar_solicitud_pendiente(solicitud)

    # Validar revisor
    revisor = _validar_usuario_existe(data.dui_revisor, "Revisor")

    # Determinar el nuevo estado
    nuevo_estado = EstadoSolicitud.APPROVED if data.accion == "aprobar" else EstadoSolicitud.REJECTED

    # Actualizar la solicitud
    actualizacion = {
        "status": nuevo_estado,
        "reviewed_by": _crear_info_usuario(revisor),
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

    logger.info(
        f"Solicitud {data.id_solicitud} {nuevo_estado} por {revisor.get('FullName')}",
        extra={"id_solicitud": data.id_solicitud, "accion": nuevo_estado}
    )

    # Si la solicitud corresponde a una factura, actualizar SolicitudActiva
    _actualizar_solicitud_activa_en_factura_si_aplica(solicitud, nuevo_estado, revisor, data.observaciones)

    return {
        "id_solicitud": data.id_solicitud,
        "no_mision": solicitud["NoMision"],
        "status": nuevo_estado,
        "reviewed_by": revisor.get("FullName"),
        "reviewed_at": actualizacion["reviewed_at"]
    }


def _actualizar_solicitud_activa_en_factura_si_aplica(
        solicitud: Dict[str, Any],
        nuevo_estado: str,
        revisor: Dict[str, Any],
        observaciones: Optional[str]
) -> None:
    """
    Actualiza el campo SolicitudActiva en la factura si la solicitud es de tipo factura.
    """
    if not solicitud.get("IdFactura"):
        return

    try:
        misiones = ejecutar_query(COLLECTION_MISIONES, {"IdMision": solicitud.get("IdMision")})
        if not misiones:
            return

        mision = misiones[0]
        facturas = mision.get("Facturas", [])

        for idx, factura in enumerate(facturas):
            if factura.get("IdFactura") == solicitud.get("IdFactura"):
                _actualizar_solicitud_activa_factura(
                    mision,
                    idx,
                    solicitud.get("IdSolicitud"),
                    solicitud.get("type"),
                    nuevo_estado,
                    {
                        "reviewed_by": _crear_info_usuario(revisor),
                        "review_observations": observaciones
                    }
                )
                break
    except Exception as e:
        logger.exception(f"Error actualizando SolicitudActiva en factura: {e}")


# ==================== EDITAR MISIÓN CON SOLICITUD APROBADA ====================

def editar_mision_aprobada(data: EditarMisionAprobada) -> Dict[str, Any]:
    """
    Edita una misión que tiene una solicitud aprobada.
    Guarda los cambios en la bitácora.
    """
    # Buscar y validar solicitud
    solicitud = _validar_solicitud_existe(data.id_solicitud)
    _validar_solicitud_aprobada(solicitud)
    _validar_solicitud_no_aplicada(solicitud)

    # Validar editor
    editor = _validar_usuario_existe(data.dui_editor, "Editor")

    # Buscar la misión
    mision_original = _validar_mision_existe({"IdMision": solicitud["IdMision"]})

    # Preparar los cambios
    cambios, campos_anteriores = _preparar_cambios_mision(data, mision_original)

    if not cambios:
        raise HTTPException(
            status_code=400,
            detail="No hay cambios para aplicar"
        )

    # Agregar timestamp de actualización
    cambios["TimeStampActualizacion"] = datetime.now(timezone.utc)

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
        campos_nuevos={k: v for k, v in cambios.items() if k in MAPEO_CAMPOS_MISION.values()},
        solicitud=solicitud,
        editor=editor
    )

    # Marcar la solicitud como aplicada
    _marcar_solicitud_aplicada(data.id_solicitud, editor)

    logger.info(
        f"Misión {mision_original['NoMision']} editada por {editor.get('FullName')}",
        extra={"id_mision": mision_original["IdMision"], "editor_dui": editor.get("Dui")}
    )

    return {
        "no_mision": mision_original["NoMision"],
        "id_mision": mision_original["IdMision"],
        "campos_modificados": list(cambios.keys()),
        "editado_por": editor.get("FullName"),
        "fecha_edicion": cambios["TimeStampActualizacion"]
    }


def _preparar_cambios_mision(data: EditarMisionAprobada, mision_original: Dict) -> Tuple[Dict, Dict]:
    """
    Prepara los cambios a aplicar en la misión.
    Retorna: (cambios_a_aplicar, campos_anteriores)
    """
    cambios = {}
    campos_anteriores = {}

    for campo_modelo, campo_db in MAPEO_CAMPOS_MISION.items():
        valor_nuevo = getattr(data, campo_modelo, None)
        if valor_nuevo is not None:
            valor_anterior = mision_original.get(campo_db)

            # Solo agregar si realmente cambió
            if valor_anterior != valor_nuevo:
                cambios[campo_db] = valor_nuevo
                campos_anteriores[campo_db] = valor_anterior

    return cambios, campos_anteriores


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

    # Validar que no exista ya una bitácora para esta solicitud
    bitacora_existente = ejecutar_query(COLLECTION_BITACORA, {
        "IdSolicitud": solicitud["IdSolicitud"]
    })

    if bitacora_existente:
        logger.warning(f"Ya existe bitácora para solicitud {solicitud['IdSolicitud']}")
        return

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
        "editado_por": _crear_info_usuario(editor),
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
        valid_statuses = [
            EstadoSolicitud.PENDING,
            EstadoSolicitud.APPROVED,
            EstadoSolicitud.REJECTED
        ]
        if status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Status debe ser: {', '.join(valid_statuses)}"
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


def obtener_solicitud_por_id(id_solicitud: str) -> Dict[str, Any]:
    """
    Obtiene una solicitud de edición por IdSolicitud.
    """
    if not id_solicitud:
        raise HTTPException(
            status_code=400,
            detail="IdSolicitud es requerido"
        )

    solicitud = _validar_solicitud_existe(id_solicitud)
    return solicitud


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
    Obtiene un resumen de solicitudes con filtros avanzados.
    """
    filtro = _construir_filtro_solicitudes_resumen(
        status, no_mision, dui, conductor, placa,
        tipo_solicitud, fecha_inicio, fecha_fin, filtro_avanzado
    )

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


def _construir_filtro_solicitudes_resumen(
        status: Optional[str],
        no_mision: Optional[str],
        dui: Optional[str],
        conductor: Optional[str],
        placa: Optional[str],
        tipo_solicitud: Optional[str],
        fecha_inicio: Optional[date],
        fecha_fin: Optional[date],
        filtro_avanzado: Optional[str]
) -> Dict[str, Any]:
    """
    Construye el filtro complejo para la consulta de resumen de solicitudes.
    """
    filtro: Dict[str, Any] = {}
    and_conditions = []

    # Status
    if status:
        status = status.strip().lower()
        valid_statuses = [
            EstadoSolicitud.PENDING,
            EstadoSolicitud.APPROVED,
            EstadoSolicitud.REJECTED,
            EstadoSolicitud.APPLIED,
            EstadoSolicitud.DELETED
        ]
        if status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Status debe ser: {', '.join(valid_statuses)}"
            )
        filtro["status"] = status

    # NoMision exacto
    if no_mision:
        no_mision_clean = no_mision.strip()
        if no_mision_clean:
            filtro["NoMision"] = no_mision_clean

    # Filtros LIKE
    dui_like = _build_contains_regex(dui)
    if dui_like:
        filtro["Dui"] = dui_like

    conductor_like = _build_contains_regex(conductor)
    if conductor_like:
        filtro["requested_by.name"] = conductor_like

    placa_like = _build_contains_regex(placa)
    if placa_like:
        filtro["Placa"] = placa_like

    # Tipo de solicitud
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

    # Rango de fechas
    if fecha_inicio or fecha_fin:
        filtro["created_at"] = _construir_filtro_fechas(fecha_inicio, fecha_fin)

    # Filtro avanzado
    texto_avanzado = _build_contains_regex(filtro_avanzado)
    if texto_avanzado:
        and_conditions.append({
            "$or": [
                {"requested_by.name": texto_avanzado},
                {"Dui": texto_avanzado},
                {"Placa": texto_avanzado}
            ]
        })

    # Combinar condiciones
    if and_conditions:
        if filtro:
            and_conditions.insert(0, dict(filtro))
        filtro = {"$and": and_conditions} if len(and_conditions) > 1 else and_conditions[0]

    return filtro


def _construir_filtro_fechas(fecha_inicio: Optional[date], fecha_fin: Optional[date]) -> Dict[str, datetime]:
    """
    Construye el filtro de rango de fechas.
    """
    if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
        raise HTTPException(
            status_code=400,
            detail="fecha_inicio no puede ser mayor que fecha_fin"
        )

    fecha_base_inicio = fecha_inicio or fecha_fin
    fecha_base_fin = fecha_fin or fecha_inicio

    if fecha_base_inicio is None or fecha_base_fin is None:
        raise HTTPException(
            status_code=400,
            detail="Debe enviar fecha_inicio o fecha_fin"
        )

    inicio_dt = datetime.combine(fecha_base_inicio, datetime.min.time()).replace(tzinfo=timezone.utc)
    fin_dt = datetime.combine(fecha_base_fin, datetime.max.time()).replace(tzinfo=timezone.utc)

    return {
        "$gte": inicio_dt,
        "$lte": fin_dt
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
    # Construir filtro
    filtro = _construir_filtro_mision(id_mision, no_mision)

    skip = (page - 1) * limit
    sort = [("fecha_edicion", -1)]

    db = get_db()
    cursor = ejecutar_query_V3(
        COLLECTION_BITACORA,  # ✅ CORREGIDO
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
    mision = _validar_mision_existe({"IdMision": data.id_mision})

    # Buscar la factura
    factura, factura_index = _validar_factura_existe(mision, data.id_factura)

    # Validar usuario
    user = _validar_usuario_existe(data.dui_solicitante, "Usuario solicitante")

    # Validar que no exista solicitud pendiente
    _validar_no_existe_solicitud_pendiente(
        mision["NoMision"],
        TipoSolicitud.FACTURA_EDICION,
        data.id_factura
    )

    # Preparar los cambios solicitados
    cambios_solicitados = _preparar_cambios_factura(data)

    if not cambios_solicitados:
        raise HTTPException(
            status_code=400,
            detail="Debe especificar al menos un campo para editar"
        )

    # Crear la solicitud
    id_solicitud = str(uuid.uuid4())
    documento_solicitud = {
        "IdSolicitud": id_solicitud,
        "type": TipoSolicitud.FACTURA_EDICION,
        "NoMision": mision["NoMision"],
        "IdMision": mision["IdMision"],
        "IdFactura": data.id_factura,
        "Placa": mision.get("Placa"),
        "Dui": mision.get("Dui"),
        "requested_by": _crear_info_usuario(user),
        "descripcion": data.descripcion,
        "metadata": {
            "origen": "manual",
            "flujo": "completo",
            "prioridad": "normal",
            "razon": "correccion"
        },
        "datos_anteriores": {
            "NumeroFactura": factura.get("NumeroFactura"),
            "CantidadGalones": factura.get("CantidadGalones"),
            "CantidadDolares": factura.get("CantidadDolares"),
            "Cupones": factura.get("Cupones", [])
        },
        "datos_solicitados": cambios_solicitados,
        "observaciones_adicionales": None,
        "status": EstadoSolicitud.PENDING,
        "applied": False,
        "reviewed_by": None,
        "review_observations": None,
        "applied_by": None,
        "created_at": datetime.now(timezone.utc),
        "reviewed_at": None,
        "applied_at": None,
        "TimeStampCreacion": datetime.now(timezone.utc),
        "TimeStampActualizacion": datetime.now(timezone.utc),
        "auditoria": {
            "intentos_aprobacion": 0,
            "modificado_por": [],
            "ip_origen": None,
            "dispositivo": None
        }
    }

    insert_document(COLLECTION_SOLICITUDES, documento_solicitud)
    logger.info(f"Solicitud de edición de factura creada: {id_solicitud}")

    # Actualizar SolicitudActiva en la factura
    _actualizar_solicitud_activa_factura(
        mision,
        factura_index,
        id_solicitud,
        TipoSolicitud.FACTURA_EDICION,
        EstadoSolicitud.PENDING,
        {"created_at": documento_solicitud["created_at"]}
    )

    logger.info(f"Campo SolicitudActiva actualizado en factura {data.id_factura}")

    # Notificación WebSocket
    _enviar_notificacion_websocket(
        category="solicitud_factura_creada",
        data={
            "IdSolicitud": id_solicitud,
            "type": TipoSolicitud.FACTURA_EDICION,
            "NoMision": mision["NoMision"],
            "IdFactura": data.id_factura,
            "solicitante": user.get("FullName"),
            "descripcion": data.descripcion,
            "status": EstadoSolicitud.PENDING,
            "fecha_solicitud": documento_solicitud["created_at"]
        }
    )

    return id_solicitud


def _preparar_cambios_factura(data: SolicitarEdicionFactura) -> Dict[str, Any]:
    """
    Prepara los cambios solicitados para una factura.
    """
    cambios = {}

    if data.numero_factura is not None:
        cambios["NumeroFactura"] = data.numero_factura
    if data.cantidad_galones is not None:
        cambios["CantidadGalones"] = data.cantidad_galones
    if data.cantidad_dolares is not None:
        cambios["CantidadDolares"] = data.cantidad_dolares
    if data.cupones is not None:
        cambios["Cupones"] = [{"NumeroCupon": c.numero_cupon} for c in data.cupones]

    return cambios


def solicitar_eliminacion_factura(data: SolicitarEliminacionFactura, current_user: dict) -> str:
    """
    Crea una solicitud para eliminar una factura.
    """
    # Buscar la misión
    mision = _validar_mision_existe({"IdMision": data.id_mision})

    # Buscar la factura
    factura, factura_index = _validar_factura_existe(mision, data.id_factura)

    # Validar usuario
    user = _validar_usuario_existe(data.dui_solicitante, "Usuario solicitante")

    # Validar que no exista solicitud pendiente
    _validar_no_existe_solicitud_pendiente(
        mision["NoMision"],
        TipoSolicitud.FACTURA_ELIMINACION,
        data.id_factura
    )

    # Crear la solicitud
    id_solicitud = str(uuid.uuid4())
    documento_solicitud = {
        "IdSolicitud": id_solicitud,
        "type": TipoSolicitud.FACTURA_ELIMINACION,
        "NoMision": mision["NoMision"],
        "IdMision": mision["IdMision"],
        "IdFactura": data.id_factura,
        "Placa": mision.get("Placa"),
        "Dui": mision.get("Dui"),
        "requested_by": _crear_info_usuario(user),
        "descripcion": data.descripcion,
        "metadata": {
            "origen": "manual",
            "flujo": "completo",
            "prioridad": "normal",
            "razon": "duplicado"
        },
        "datos_anteriores": {
            "NumeroFactura": factura.get("NumeroFactura"),
            "CantidadGalones": factura.get("CantidadGalones"),
            "CantidadDolares": factura.get("CantidadDolares"),
            "FechaFactura": factura.get("FechaFactura"),
            "Cupones": factura.get("Cupones", [])
        },
        "datos_solicitados": {},
        "observaciones_adicionales": None,
        "status": EstadoSolicitud.PENDING,
        "applied": False,
        "reviewed_by": None,
        "review_observations": None,
        "applied_by": None,
        "created_at": datetime.now(timezone.utc),
        "reviewed_at": None,
        "applied_at": None,
        "TimeStampCreacion": datetime.now(timezone.utc),
        "TimeStampActualizacion": datetime.now(timezone.utc),
        "auditoria": {
            "intentos_aprobacion": 0,
            "modificado_por": [],
            "ip_origen": None,
            "dispositivo": None
        }
    }

    insert_document(COLLECTION_SOLICITUDES, documento_solicitud)
    logger.info(f"Solicitud de eliminación de factura creada: {id_solicitud}")

    # Actualizar SolicitudActiva en la factura
    _actualizar_solicitud_activa_factura(
        mision,
        factura_index,
        id_solicitud,
        TipoSolicitud.FACTURA_ELIMINACION,
        EstadoSolicitud.PENDING,
        {"created_at": documento_solicitud["created_at"]}
    )

    logger.info(f"Campo SolicitudActiva actualizado en factura {data.id_factura}")

    # Notificación WebSocket
    _enviar_notificacion_websocket(
        category="solicitud_eliminacion_factura_creada",
        data={
            "IdSolicitud": id_solicitud,
            "type": TipoSolicitud.FACTURA_ELIMINACION,
            "NoMision": mision["NoMision"],
            "IdFactura": data.id_factura,
            "NumeroFactura": factura.get("NumeroFactura"),
            "solicitante": user.get("FullName"),
            "descripcion": data.descripcion,
            "status": EstadoSolicitud.PENDING,
            "fecha_solicitud": documento_solicitud["created_at"]
        }
    )

    return id_solicitud


def editar_factura_aprobada(data: EditarFacturaAprobada) -> Dict[str, Any]:
    """
    Edita una factura con solicitud aprobada.
    """
    # Buscar y validar solicitud
    solicitud = _validar_solicitud_existe(data.id_solicitud)
    _validar_tipo_solicitud(solicitud, TipoSolicitud.FACTURA_EDICION)
    _validar_solicitud_aprobada(solicitud)
    _validar_solicitud_no_aplicada(solicitud)

    # Validar editor
    editor = _validar_usuario_existe(data.dui_editor, "Editor")

    # Buscar la misión y la factura
    mision = _validar_mision_existe({"IdMision": solicitud["IdMision"]})
    facturas = mision.get("Facturas", [])

    # Buscar y modificar la factura
    factura_modificada, cambios_aplicados = _aplicar_cambios_factura(
        facturas,
        solicitud,
        data.id_solicitud
    )

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
    _marcar_solicitud_aplicada(data.id_solicitud, editor)

    logger.info(f"Factura {solicitud['IdFactura']} editada por {editor.get('FullName')}")

    return {
        "no_mision": mision["NoMision"],
        "id_factura": solicitud["IdFactura"],
        "campos_modificados": list(cambios_aplicados.keys()),
        "editado_por": editor.get("FullName"),
        "fecha_edicion": datetime.now(timezone.utc)
    }


def _aplicar_cambios_factura(
        facturas: List[Dict],
        solicitud: Dict,
        id_solicitud: str
) -> Tuple[bool, Dict]:
    """
    Aplica los cambios solicitados a la factura correspondiente.
    Retorna: (factura_modificada, cambios_aplicados)
    """
    factura_modificada = False
    cambios_aplicados = {}

    for factura in facturas:
        if factura.get("IdFactura") == solicitud["IdFactura"]:
            # Aplicar los cambios solicitados (nuevo formato: datos_solicitados, legacy: cambios_solicitados)
            datos_solicitados_val = solicitud.get("datos_solicitados")
            cambios_solicitados = datos_solicitados_val if datos_solicitados_val is not None else solicitud.get("cambios_solicitados", {})

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
            factura["SolicitudActiva"] = {
                "IdSolicitud": id_solicitud,
                "type": solicitud.get("type"),
                "status": EstadoSolicitud.APPLIED,
                "applied_at": datetime.now(timezone.utc)
            }

            # Asegurar estado de la factura
            factura["Estado"] = "active"

            factura_modificada = True
            break

    return factura_modificada, cambios_aplicados


def eliminar_factura_aprobada(data: EliminarFacturaAprobada) -> Dict[str, Any]:
    """
    Elimina (marca como deleted) una factura con solicitud aprobada.
    """
    # Buscar y validar solicitud
    solicitud = _validar_solicitud_existe(data.id_solicitud)
    _validar_tipo_solicitud(solicitud, TipoSolicitud.FACTURA_ELIMINACION)
    _validar_solicitud_aprobada(solicitud)
    _validar_solicitud_no_aplicada(solicitud)

    # Validar editor
    editor = _validar_usuario_existe(data.dui_editor, "Editor")

    # Buscar la misión y la factura
    mision = _validar_mision_existe({"IdMision": solicitud["IdMision"]})
    facturas = mision.get("Facturas", [])

    # Marcar la factura como eliminada
    factura_eliminada = _marcar_factura_eliminada(facturas, solicitud, data.id_solicitud)

    if factura_eliminada is None:
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
        tipo_operacion="eliminacion",
        mision=mision,
        solicitud=solicitud,
        editor=editor,
        factura_eliminada=factura_eliminada
    )

    # Marcar la solicitud como aplicada
    _marcar_solicitud_aplicada(data.id_solicitud, editor)

    logger.info(f"Factura {solicitud['IdFactura']} eliminada por {editor.get('FullName')}")

    return {
        "no_mision": mision["NoMision"],
        "id_factura": solicitud["IdFactura"],
        "numero_factura": factura_eliminada.get("NumeroFactura"),
        "eliminado_por": editor.get("FullName"),
        "fecha_eliminacion": datetime.now(timezone.utc)
    }


def _marcar_factura_eliminada(
        facturas: List[Dict],
        solicitud: Dict,
        id_solicitud: str
) -> Optional[Dict]:
    """
    Marca una factura como eliminada (no la elimina físicamente).
    Retorna la factura eliminada o None si no se encontró.
    """
    factura_eliminada = None

    for idx, factura in enumerate(facturas):
        if factura.get("IdFactura") == solicitud["IdFactura"]:
            # Guardar una copia para bitácora
            factura_eliminada = dict(factura)

            # Actualizar la factura in-place: estado y SolicitudActiva
            facturas[idx]["Estado"] = "deleted"
            facturas[idx]["SolicitudActiva"] = {
                "IdSolicitud": id_solicitud,
                "type": solicitud.get("type"),
                "status": EstadoSolicitud.DELETED,
                "applied_at": datetime.now(timezone.utc)
            }
            break

    return factura_eliminada


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

    # Validar que no exista ya una bitácora para esta solicitud
    bitacora_existente = ejecutar_query(COLLECTION_BITACORA, {
        "IdSolicitud": solicitud["IdSolicitud"]
    })

    if bitacora_existente:
        logger.warning(f"Ya existe bitácora para solicitud {solicitud['IdSolicitud']}")
        return

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
        "editado_por": _crear_info_usuario(editor),
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