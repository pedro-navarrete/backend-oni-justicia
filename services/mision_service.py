# services/mision_service.py
import pytz
import asyncio
from starlette.responses import JSONResponse
from database.verificador_mongo import ejecutar_query, insert_document, update_document, update_document2, get_db, \
    ejecutar_query_V2, ejecutar_query_V3
from models.models import CrearMision, ActualizarMision, Coordenada, EditarMision, AgregarFactura, EditarFactura, \
    EliminarFactura, CoordenadasBatchRequest
from .verificar_service import verificar_placa, verificar_dui
from fastapi import HTTPException
from typing import Optional, List
import uuid
import os
import json
import logging
from datetime import datetime, date, time, timezone
from typing import Any, Dict
import websockets
from dotenv import load_dotenv
from database.verificador_sqlserver import VerificadorSQL
from utils.websocket_client import enviar_por_websocket


COLLECTION = "Misiones"
ULTIMOMOVS = "UltimoMovs"
HISTORICO = "HistoriDiaMovs"
USERCOLLECTION = "users"
PLACACOLLETION = "CatalogoDeVehiculos"
MISIONEDTILOGS="MisionEditLogs"
EDIT_REQUESTS = "MisionEditRequests"
SOLICITUDES_EDICION = "SolicitudesEdicionMision"
BITACORA_CAMBIOS = "BitacoraCambiosMision"


load_dotenv()
logger = logging.getLogger(__name__)


# -------------------- Auxiliar: Actualizar estados en SQL Server --------------------
def _actualizar_estados_sql(
    solicitud_id: Optional[str] = None,
    dui: Optional[str] = None,
    placa: Optional[str] = None,
    estado_solicitud: Optional[int] = None,
    disponibilidad_motorista: Optional[int] = None,
    estado_vehiculo: Optional[int] = None,
    operacion: str = "crear_mision"
):
    """
    Consolida actualizaciones de estado en SQL Server para solicitudes, motoristas y vehículos.

    NO bloquea la misión principal si falla. Log errores para análisis.

    Args:
        solicitud_id: ID de solicitud a actualizar
        dui: DUI del motorista
        placa: Placa del vehículo
        estado_solicitud: Estado de solicitud (ej: 4=iniciada, 5=finalizada)
        disponibilidad_motorista: Disponibilidad del motorista (ej: 1=disponible, 2=ocupado)
        estado_vehiculo: Estado del vehículo (ej: 1=disponible, 2=en_uso)
        operacion: Nombre de la operación que llama (para logging)
    """
    try:
        db = VerificadorSQL(prefix="MSSQL")

        # Actualizar solicitud
        if solicitud_id and estado_solicitud is not None:
            try:
                filas = db.ejecutar_querySQL(
                    query="UPDATE solicitudes SET estado = %s WHERE idSolicitud = %s",
                    tipo="UPDATE",
                    params=(estado_solicitud, solicitud_id)
                )
                logger.info(
                    f"[SQL][{operacion}] Solicitud actualizada | "
                    f"idSolicitud={solicitud_id} estado={estado_solicitud} filas={filas}"
                )
            except Exception as e:
                logger.error(
                    f"[SQL][{operacion}] Error actualizando solicitud | "
                    f"idSolicitud={solicitud_id} | {type(e).__name__}: {e}"
                )

        # Actualizar motorista
        if dui and disponibilidad_motorista is not None:
            try:
                filas = db.ejecutar_querySQL(
                    query="UPDATE motoristas SET disponibilidad = %s WHERE dui = %s",
                    tipo="UPDATE",
                    params=(disponibilidad_motorista, dui)
                )
                logger.info(
                    f"[SQL][{operacion}] Motorista actualizado | "
                    f"dui={dui} disponibilidad={disponibilidad_motorista} filas={filas}"
                )
            except Exception as e:
                logger.error(
                    f"[SQL][{operacion}] Error actualizando motorista | "
                    f"dui={dui} | {type(e).__name__}: {e}"
                )

        # Actualizar vehículo
        if placa and estado_vehiculo is not None:
            try:
                filas = db.ejecutar_querySQL(
                    query="UPDATE vehiculos SET estado = %s WHERE placaVehiculo = %s",
                    tipo="UPDATE",
                    params=(estado_vehiculo, placa)
                )
                logger.info(
                    f"[SQL][{operacion}] Vehículo actualizado | "
                    f"placa={placa} estado={estado_vehiculo} filas={filas}"
                )
            except Exception as e:
                logger.error(
                    f"[SQL][{operacion}] Error actualizando vehículo | "
                    f"placa={placa} | {type(e).__name__}: {e}"
                )

    except Exception as e:
        logger.error(
            f"[SQL][{operacion}] Error general en actualización de estados | "
            f"{type(e).__name__}: {e}",
            exc_info=True
        )


# -------------------- Crear misión --------------------
def crear_mision(data: CrearMision) -> str:
    """Crea una nueva misión para un vehículo (valida DUI y placa)."""

    #obtener nombre del motorista por dui (ejecutar_query devuelve lista)
    usuarios = ejecutar_query(USERCOLLECTION, {"$or": [{"dui": data.dui}, {"Dui": data.dui}]})
    if not usuarios:
        raise HTTPException(
            status_code=409,
            detail=f"El DUI {data.dui} NO FUE ENCONTRADO EN USUARIOS"
        )
    usuario = usuarios[0]
    nombremotorista = usuario.get("FullName") or usuario.get("Name") or data.nombre_motorista or ""

    # Verificar que no exista una misión abierta para el DUI
    # Fuente: HistoriDiaMovs (única fuente de verdad para coordenadas)
    historico_dui = get_db()[HISTORICO].find_one({"Dui": data.dui})
    if historico_dui:
        for mision in historico_dui.get("Misiones", []):
            coordenadas = mision.get("coordenadas", [])
            if coordenadas:
                estado_ultimo = (coordenadas[-1] or {}).get("Estado")
                if estado_ultimo != "final":
                    logging.error(f"El DUI {data.dui} ya tiene una misión abierta. Debe finalizarse antes de iniciar otra.")
                    raise HTTPException(
                        status_code=409,
                        detail=f"El DUI {data.dui} ya tiene una misión abierta. Debe finalizarse antes de iniciar otra."
                    )

    # Verificar si ya existe una misión abierta para la placa
    # Fuente: HistoriDiaMovs (única fuente de verdad para coordenadas)
    historico_placa = get_db()[HISTORICO].find_one({"Placa": data.placa})
    if historico_placa:
        for mision in historico_placa.get("Misiones", []):
            coordenadas = mision.get("coordenadas", [])
            if coordenadas:
                estado_ultimo = (coordenadas[-1] or {}).get("Estado")
                if estado_ultimo != "final":
                    logging.error(f"La placa {data.placa} ya tiene una misión abierta. Debe finalizarse antes de iniciar otra.")
                    raise HTTPException(
                        status_code=409,
                        detail=f"La placa {data.placa} ya tiene una misión abierta. Debe finalizarse antes de iniciar otra."
                    )

    #Generar NoMision
    misionid= list(get_db()[COLLECTION].find({"Dui": data.dui,"Placa": data.placa} , {"_id": 0, "NoMision": 1}).sort("TimeStamp", -1).limit(1))
    if misionid:
        misionid=misionid[0]["NoMision"]
        misionnewid=int(misionid.split(".")[-1])+1
    else:
        misionnewid=1


    id_mision = str(uuid.uuid4())
    doc = {
        "Placa": data.placa,
        "Dui": data.dui,
        "NoMision": f"{data.dui}.{data.placa}.{misionnewid}",
        "KilometrajeInicial": data.kilometraje_inicial,
        "NombreMotorista": nombremotorista,
        "MarcadorTanqueInicial": data.marcador_tanque_inicial,
        "Solicitante": data.solicitante,
        "lugares_a_visitar": data.lugares_visitados,
        "FechaHoraSalida": data.fecha_hora_salida,
        "TimeStamp": datetime.utcnow(),
        "IdMision": id_mision
    }

    logging.info(f"Creando nueva misión: {doc}")
    insert_document(COLLECTION, doc)

    # Actualizar estados en SQL Server (sin bloquear la misión principal)
    try:
        solicitud_id = data.solicitud
        db = VerificadorSQL(prefix="MSSQL")

        # PASO 1: Buscar data.solicitud directamente en SQL Server
        solicitud_directa = None
        if solicitud_id:
            resultado = db.ejecutar_querySQL(
                query="SELECT idSolicitud FROM solicitudes WHERE idSolicitud = %s AND estado = 1",
                tipo="SELECT",
                params=(solicitud_id,)
            )
            if resultado:
                solicitud_directa = resultado[0]['idSolicitud']

        if solicitud_directa:
            # PASO 2: Comparar contra el del DUI
            solicitud_dui = get_misiones_solicitadas_SQL_por_dui(data.dui)
            id_dui = solicitud_dui.get('idSolicitud') if solicitud_dui else None

            if id_dui and int(solicitud_directa) != int(id_dui):
                # No coinciden → lanzar error
                logger.error(
                    f"Conflicto de solicitud: data.solicitud={solicitud_directa} "
                    f"no coincide con solicitud del DUI={id_dui}"
                )
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"La solicitud enviada ({solicitud_directa}) no corresponde "
                        f"a la solicitud activa del motorista ({id_dui})"
                    )
                )

            # Usar la función consolidada para actualizar
            _actualizar_estados_sql(
                solicitud_id=solicitud_directa,
                dui=data.dui,
                placa=data.placa,
                estado_solicitud=4,
                disponibilidad_motorista=2,
                estado_vehiculo=2,
                operacion="crear_mision"
            )

        else:
            # PASO 3: Fallback → usar solicitud del DUI
            logger.warning(
                f"data.solicitud={solicitud_id} no encontrado en SQL, "
                f"intentando fallback por DUI {data.dui}"
            )
            solicitud_dui = get_misiones_solicitadas_SQL_por_dui(data.dui)
            id_dui = solicitud_dui.get('idSolicitud') if solicitud_dui else None

            if id_dui:
                _actualizar_estados_sql(
                    solicitud_id=id_dui,
                    dui=data.dui,
                    placa=data.placa,
                    estado_solicitud=4,
                    disponibilidad_motorista=2,
                    estado_vehiculo=2,
                    operacion="crear_mision_fallback"
                )
            else:
                logger.warning(f"No se encontró solicitud activa para DUI {data.dui}, no se actualiza estado.")

    except HTTPException:
        raise  # Re-lanzar errores de negocio sin atraparlos
    except Exception as e:
        logger.exception("Error actualizando estado de la solicitud en SQL Server: %s", e)

    return id_mision


def _obtener_mision_por_identificadores(id_mision: str, dui: str, placa: str) -> dict:
    """Busca una misión por combinación exacta e informa qué identificador no coincide."""
    filtro = {"IdMision": id_mision, "Dui": dui, "Placa": placa}
    misiones = ejecutar_query(COLLECTION, filtro)

    if misiones:
        if len(misiones) > 1:
            raise HTTPException(status_code=409, detail="Error: Se encontraron múltiples misiones con los mismos datos")
        return misiones[0]

    failed_fields = []
    por_id = ejecutar_query(COLLECTION, {"IdMision": id_mision})

    if not por_id:
        failed_fields.append("IdMision")
        if not ejecutar_query(COLLECTION, {"Dui": dui}):
            failed_fields.append("Dui")
        if not ejecutar_query(COLLECTION, {"Placa": placa}):
            failed_fields.append("Placa")
    else:
        if len(por_id) > 1:
            raise HTTPException(status_code=409, detail="Error: Se encontraron múltiples misiones con el mismo IdMision")

        mision = por_id[0]
        if mision.get("Dui") != dui:
            failed_fields.append("Dui")
        if mision.get("Placa") != placa:
            failed_fields.append("Placa")

    if not failed_fields:
        failed_fields = ["IdMision/Dui/Placa"]

    raise HTTPException(
        status_code=404,
        detail={
            "message": "Misión no encontrada",
            "failed_fields": failed_fields
        }
    )


def _obtener_mision_por_id(id_mision: str) -> dict:
    """Busca una misión por IdMision validando existencia y unicidad."""
    misiones = ejecutar_query(COLLECTION, {"IdMision": id_mision})

    if not misiones:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Misión no encontrada",
                "failed_fields": ["IdMision"]
            }
        )

    if len(misiones) > 1:
        raise HTTPException(status_code=409, detail="Error: Se encontraron múltiples misiones con el mismo IdMision")

    return misiones[0]


def _obtener_coordenadas_desde_historial(placa: str, dui: str, no_mision: str) -> List[dict]:
    """Obtiene coordenadas de una misión desde HistoriDiaMovs."""
    if not placa or not dui or not no_mision:
        return []

    doc = get_db()[HISTORICO].find_one({"Placa": placa, "Dui": dui, "Misiones.Mision": no_mision})
    if not doc:
        return []

    for mision in doc.get("Misiones", []):
        if mision.get("Mision") == no_mision:
            return mision.get("coordenadas", []) or []

    return []


def _obtener_coordenadas_mision(mision: dict) -> List[dict]:
    """Fuente de verdad: HistoriDiaMovs; fallback a Misiones para compatibilidad legacy."""
    no_mision = mision.get("NoMision")
    placa = mision.get("Placa")
    dui = mision.get("Dui")

    coordenadas_hist = _obtener_coordenadas_desde_historial(placa, dui, no_mision)
    if coordenadas_hist:
        return coordenadas_hist

    return mision.get("Coordenadas", []) or []


def _obtener_estado_actual_mision(mision: dict) -> Optional[str]:
    coordenadas = _obtener_coordenadas_mision(mision)
    if not coordenadas:
        return None
    return (coordenadas[-1] or {}).get("Estado")


def _obtener_no_misiones_por_estado(
    estado: str,
    placa: str = None,
    dui: str = None,
    no_mision: str = None
) -> set:
    """Obtiene NoMision cuyo último estado (en HistoriDiaMovs) coincide con el filtro."""
    match_doc = {}
    if placa:
        match_doc["Placa"] = placa
    if dui:
        match_doc["Dui"] = dui
    if no_mision:
        match_doc["Misiones.Mision"] = no_mision

    pipeline = []
    if match_doc:
        pipeline.append({"$match": match_doc})

    pipeline.append({"$unwind": "$Misiones"})
    if no_mision:
        pipeline.append({"$match": {"Misiones.Mision": no_mision}})
    pipeline.extend([
        {
            "$project": {
                "_id": 0,
                "NoMision": "$Misiones.Mision",
                "Estado": {"$arrayElemAt": ["$Misiones.coordenadas.Estado", -1]}
            }
        },
        {"$match": {"Estado": estado}}
    ])

    try:
        rows = list(get_db()[HISTORICO].aggregate(pipeline))
        return {row.get("NoMision") for row in rows if row.get("NoMision")}
    except Exception:
        logger.exception("Error consultando estado de misiones en HistoriDiaMovs")
        return set()

# -------------------- Auxiliar Interno: Guardar Coordenada (Lógica Unificada) --------------------
def _guardar_coordenada_interna(data: Coordenada, origen: str = "guardar_coordenada") -> bool:
    """Compatibilidad hacia atrás para guardar una única coordenada."""
    _guardar_coordenadas_en_lote([data], origen=origen)
    return True


def _validar_lote_coordenadas(coordenadas: List[Coordenada], mision: dict, origen: str):
    """Valida que el lote pertenezca a la misma misión y respete el flujo actual."""
    if not coordenadas:
        raise HTTPException(status_code=400, detail="Debe enviar al menos una coordenada")

    referencia = coordenadas[0]
    for indice, coordenada in enumerate(coordenadas[1:], start=1):
        if (
            coordenada.id_mision != referencia.id_mision
            or coordenada.dui != referencia.dui
            or coordenada.placa != referencia.placa
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Todas las coordenadas del lote deben pertenecer a la misma misión, DUI y placa. "
                    f"Error en el elemento {indice}."
                )
            )

    coordenadas_existentes = _obtener_coordenadas_mision(mision)

    if coordenadas_existentes and coordenadas_existentes[-1].get("Estado") == "final":
        logger.warning(
            f"[{origen}] Intento de agregar coordenadas a misión finalizada | "
            f"IdMision={referencia.id_mision} Placa={referencia.placa} Dui={referencia.dui}"
        )
        raise HTTPException(status_code=409, detail="No se pueden agregar coordenadas: la misión ya está finalizada")

    if coordenadas_existentes:
        for coordenada in coordenadas:
            if coordenada.estado == "inicio":
                logger.warning(
                    f"[{origen}] Intento de agregar estado 'inicio' cuando ya existen coordenadas | "
                    f"IdMision={referencia.id_mision} Placa={referencia.placa} Dui={referencia.dui}"
                )
                raise HTTPException(status_code=400, detail="Solo la primera coordenada puede tener estado 'inicio'")
    else:
        for indice, coordenada in enumerate(coordenadas[1:], start=1):
            if coordenada.estado == "inicio":
                raise HTTPException(
                    status_code=400,
                    detail=f"Solo la primera coordenada del lote puede tener estado 'inicio' (elemento {indice})."
                )

    seen_final = False
    for indice, coordenada in enumerate(coordenadas):
        if seen_final:
            raise HTTPException(
                status_code=400,
                detail=f"No se pueden enviar coordenadas después de una coordenada con estado 'final' (elemento {indice})."
            )
        if coordenada.estado == "final":
            seen_final = True


def _guardar_coordenadas_en_lote(
    coordenadas: List[Coordenada],
    origen: str = "guardar_coordenada",
    ws_solo_ultima_en_lote: bool = False
) -> dict:
    """Guarda una o múltiples coordenadas de forma secuencial y consistente."""
    if not coordenadas:
        raise HTTPException(status_code=400, detail="Debe enviar al menos una coordenada")

    referencia = coordenadas[0]
    mision = _obtener_mision_por_identificadores(referencia.id_mision, referencia.dui, referencia.placa)
    _validar_lote_coordenadas(coordenadas, mision, origen)

    nuevos_docs = []

    for coordenada in coordenadas:
        coord_doc = _construir_documento_coordenada(coordenada)
        nuevos_docs.append((coordenada, coord_doc))

    logger.debug(
        f"[{origen}] Lote preparado para guardar en HistoriDiaMovs | "
        f"IdMision={referencia.id_mision} Total={len(coordenadas)}"
    )

    no_mision = mision.get("NoMision")
    total_docs = len(nuevos_docs)
    for indice, (coordenada, coord_doc) in enumerate(nuevos_docs):
        emitir_ws = (indice == total_docs - 1) if ws_solo_ultima_en_lote else True
        _replicar_secundarias(coordenada, no_mision, coord_doc, origen, emitir_ws=emitir_ws)

    return {
        "id_mision": referencia.id_mision,
        "dui": referencia.dui,
        "placa": referencia.placa,
        "total_recibidas": len(coordenadas),
        "total_guardadas": len(coordenadas)
    }


def _construir_documento_coordenada(data: Coordenada) -> dict:
    """Construye el documento de una coordenada con todos sus campos opcionales."""
    coord_doc = {
        "LatitudAct": data.latitud,
        "LongitudAct": data.longitud,
        "FechaHoraAct": data.fecha_hora,
        "Estado": data.estado,
        "StatusOperacion": 200,
        "NivelBateria": data.nivel_bateria,
        "TimeStamp": datetime.utcnow()
    }

    # Agregar campos opcionales si existen
    if data.velocidad is not None:
        coord_doc["Velocidad"] = data.velocidad
    if data.rumbo is not None:
        coord_doc["Rumbo"] = data.rumbo
    if data.altitud is not None:
        coord_doc["Altitud"] = data.altitud
    if data.precision is not None:
        coord_doc["Precision"] = data.precision
    if data.proveedor is not None:
        coord_doc["Proveedor"] = data.proveedor

    return coord_doc


def _replicar_secundarias(
    data: Coordenada,
    no_mision: str,
    coord_doc: dict,
    origen: str,
    emitir_ws: bool = True
):
    """Replica coordenada en UltimoMovs e HistoriDiaMovs (sin bloquear la respuesta)."""

    # Actualizar UltimoMovs
    try:
        _actualizar_ultimo_mov(data.placa, data.dui, no_mision, coord_doc, emitir_ws=emitir_ws)
    except Exception as e:
        logger.error(
            f"[{origen}] ERROR actualizando UltimoMovs | "
            f"IdMision={data.id_mision} Placa={data.placa} Dui={data.dui} | "
            f"{type(e).__name__}: {e}",
            exc_info=True
        )

    # Replicar en HistoriDiaMovs
    try:
        _replicar_historial(data.placa, data.dui, no_mision, coord_doc, data.estado, data.id_mision)
    except Exception as e:
        logger.error(
            f"[{origen}] ERROR replicando en HistoriDiaMovs | "
            f"IdMision={data.id_mision} Placa={data.placa} Dui={data.dui} | "
            f"{type(e).__name__}: {e}",
            exc_info=True
        )


# -------------------- Guardar coordenada --------------------
def guardar_coordenada(data: Coordenada) -> bool:
    """Agrega una coordenada de misión (HistoriDiaMovs fuente de verdad)."""
    _guardar_coordenadas_en_lote([data], origen="guardar_coordenada")
    return True


def guardar_coordenadas(data: List[Coordenada]) -> dict:
    """Agrega una lista de coordenadas de misión (HistoriDiaMovs fuente de verdad)."""
    return _guardar_coordenadas_en_lote(data, origen="guardar_coordenadas")


def guardar_coordenadas_por_id_mision(data: CoordenadasBatchRequest) -> dict:
    """Agrega coordenadas por lote usando solo IdMision y completa DUI/placa internamente."""
    mision = _obtener_mision_por_id(data.id_mision)
    dui = mision.get("Dui")
    placa = mision.get("Placa")

    if not dui or not placa:
        raise HTTPException(
            status_code=409,
            detail="La misión no tiene DUI o placa válidos para guardar coordenadas"
        )

    coordenadas_completas = [
        Coordenada(
            id_mision=data.id_mision,
            dui=dui,
            placa=placa,
            **coordenada.model_dump()
        )
        for coordenada in data.coordenadas
    ]

    return _guardar_coordenadas_en_lote(
        coordenadas_completas,
        origen="guardar_coordenadas_por_id_mision",
        ws_solo_ultima_en_lote=True
    )


#-----------------------Inicio y final de mision-----------------------
def InicioFinalMision(data: Coordenada):
    """Agrega una coordenada con estado 'inicio' o 'final' a la misión."""
    # Validar que solo se permitan estos estados
    if data.estado not in ("inicio", "final"):
        raise HTTPException(status_code=400, detail="Solo se permiten coordenadas con estado 'inicio' o 'final'")

    return _guardar_coordenada_interna(data, origen="InicioFinalMision")

#-------------------- Auxiliar: UltimoMovs MEJORADO --------------------
def _actualizar_ultimo_mov(
    placa: str,
    dui: str,
    no_mision: Optional[str],
    coord_doc: dict,
    emitir_ws: bool = True
):
    """
    Mantiene un único documento por (Placa, Dui, NoMision) con la coordenada actual y anterior.
    - Crea si no existe (upsert)
    - Bloquea si estado == 'final' (fallback sin error)
    - Actualiza moviendo Act -> Ant
    """

    filtro = {"Placa": placa, "Dui": dui, "NoMision": no_mision}
    now = datetime.utcnow()

    # Obtener documento existente
    docs = ejecutar_query(ULTIMOMOVS, filtro)
    misiones = ejecutar_query(COLLECTION, filtro)
    mision_actual = misiones[0] if misiones else {}
    no_solicitud = mision_actual.get("solicitud", mision_actual.get("Solicitud"))

    # Obtener nombre del motorista
    def obtener_motorista_nombre(dui: str) -> str:
        motorista = get_db()[USERCOLLECTION].find_one({"Dui": dui})
        if not motorista:
            return ""

        primer_nombre = motorista.get("primer_nombre", "").strip()
        primer_ape = motorista.get("primer_ape", "").strip()

        # Combinar: "FABRICIO NERIO"
        nombre_completo = f"{primer_nombre} {primer_ape}".strip()
        return nombre_completo

    def obtener_motorista_nombre_Completo(dui: str) -> str:
        motorista = get_db()[USERCOLLECTION].find_one({"Dui": dui})
        return motorista.get("FullName", "") if motorista else ""

    motorista_nombre_Completo = obtener_motorista_nombre_Completo(dui)

    motorista_nombre = obtener_motorista_nombre(dui)

    if docs:
        doc_actual = docs[0]

        # Si ya está finalizado, bloquear silenciosamente (la misión ya fue guardada)
        if doc_actual.get("Estado") == "final":
            logger.info(
                f"[UltimoMovs] Estado 'final' ya registrado | "
                f"Placa={placa} Dui={dui} NoMision={no_mision} | Omitiendo actualización"
            )
            return

        # Mover Act -> Ant
        nuevo_doc = {
            "LatitudAnt": doc_actual.get("LatitudAct"),
            "LongitudAnt": doc_actual.get("LongitudAct"),
            "FechaHoraAnt": doc_actual.get("FechaHoraAct"),
            "LatitudAct": coord_doc["LatitudAct"],
            "LongitudAct": coord_doc["LongitudAct"],
            "FechaHoraAct": coord_doc["FechaHoraAct"],
            "Motorista": motorista_nombre_Completo,
            "Estado": coord_doc["Estado"],
            "NivelBateria": coord_doc["NivelBateria"],
            "StatusOperacion": coord_doc.get("StatusOperacion", 200),
            "TimeStamp": now
        }
    else:
        # Crear documento nuevo
        nuevo_doc = {
            "Placa": placa,
            "Dui": dui,
            "NoMision": no_mision,
            "LatitudAnt": None,
            "LongitudAnt": None,
            "FechaHoraAnt": None,
            "LatitudAct": coord_doc["LatitudAct"],
            "LongitudAct": coord_doc["LongitudAct"],
            "FechaHoraAct": coord_doc["FechaHoraAct"],
            "Motorista": motorista_nombre_Completo,
            "Estado": coord_doc["Estado"],
            "NivelBateria": coord_doc["NivelBateria"],
            "StatusOperacion": coord_doc.get("StatusOperacion", 200),
            "TimeStamp": now
        }

    # Actualizar con upsert
    update_document2(ULTIMOMOVS, filtro, {"$set": nuevo_doc}, upsert=True)

    logger.debug(
        f"[UltimoMovs] Actualizado | Placa={placa} Dui={dui} "
        f"Estado={nuevo_doc.get('Estado')} | Lat={coord_doc['LatitudAct']}"
    )

    # Construir y enviar documento por WebSocket
    if not emitir_ws:
        return

    ws_doc = {
        "Solicitud": no_solicitud,
        "Placa": placa,
        "Dui": dui,
        "Motorista": motorista_nombre,
        "NoMision": no_mision,
        "LatitudAnt": nuevo_doc.get("LatitudAnt"),
        "LongitudAnt": nuevo_doc.get("LongitudAnt"),
        "FechaHoraAnt": nuevo_doc.get("FechaHoraAnt"),
        "LatitudAct": nuevo_doc.get("LatitudAct"),
        "LongitudAct": nuevo_doc.get("LongitudAct"),
        "FechaHoraAct": nuevo_doc.get("FechaHoraAct"),
        "Estado": nuevo_doc.get("Estado"),
        "NivelBateria": nuevo_doc.get("NivelBateria"),
        "StatusOperacion": nuevo_doc.get("StatusOperacion", 200),
        "TimeStamp": nuevo_doc.get("TimeStamp")
    }

    try:
        asyncio.run(
            enviar_por_websocket(
                category="mision_actualizada",
                data=ws_doc
            )
        )
        logger.debug(f"[WebSocket] Actualización enviada | Placa={placa} Dui={dui}")
    except Exception as e:
        logger.error(f"[WebSocket] Error enviando actualización: {e}")


# -------------------- Auxiliar: HistoriDiaMovs CORREGIDO --------------------
def _replicar_historial(placa: str, dui: str, no_mision: Optional[str], coord_doc: dict, estado: str, id_mision: str = ""):
    """
    Replica la coordenada en HistoriDiaMovs de forma GARANTIZADA.

    IMPORTANTE: Esta función NO lanza excepciones. Ante cualquier fallo registra
    el error crítico en el log para análisis posterior.

    Estrategia mejorada:
    1. estado == 'inicio': Crea nueva entrada de misión en el array Misiones
    2. estado in ('enruta', 'final'): Intenta $push atómico
    3. Si $push falla (misión no existe en histórico), crea fallback garantizado
    4. Logging exhaustivo en todos los caminos para debugging
    """

    ahora = datetime.utcnow()
    mision_key = no_mision or ""

    # Construir entrada de histórico
    hist_entry = {
        "LatitudAct": coord_doc["LatitudAct"],
        "LongitudAct": coord_doc["LongitudAct"],
        "FechaHoraAct": coord_doc["FechaHoraAct"],
        "Estado": coord_doc["Estado"],
        "StatusOperacion": coord_doc.get("StatusOperacion", 200),
        "NivelBateria": coord_doc["NivelBateria"],
        "TimeStamp": coord_doc.get("TimeStamp", ahora)
    }

    col = get_db()[HISTORICO]
    filtro_doc = {"Placa": placa, "Dui": dui}

    # Se usa al crear el documento de historico por primera vez (upsert)
    motorista = get_db()[USERCOLLECTION].find_one({"Dui": dui})
    motorista_nombre = (motorista or {}).get("FullName") or (motorista or {}).get("Name") or ""

    try:
        if estado == "inicio":
            # ============ CASO 1: INICIO ============
            # Crear nueva entrada de misión con la primera coordenada
            result = col.update_one(
                filtro_doc,
                {
                    "$push": {"Misiones": {"Mision": mision_key, "coordenadas": [hist_entry]}},
                    "$set": {"TimeStamp": ahora, "Motorista": motorista_nombre}
                },
                upsert=True
            )

            logger.info(
                f"[HistoriDiaMovs][inicio] NUEVO INICIO | "
                f"Placa={placa} Dui={dui} NoMision={mision_key} | "
                f"upserted={result.upserted_id is not None} modified={result.modified_count} | "
                f"IdMision={id_mision}"
            )

        else:
            # ============ CASO 2: ENRUTA / FINAL ============
            # Intentar $push atómico a coordenadas de misión existente
            result = col.update_one(
                {"Placa": placa, "Dui": dui, "Misiones.Mision": mision_key},
                {
                    "$push": {"Misiones.$.coordenadas": hist_entry},
                    "$set": {"TimeStamp": ahora, "Motorista": motorista_nombre}
                }
            )

            if result.modified_count > 0:
                # ✓ $push atómico exitoso
                logger.debug(
                    f"[HistoriDiaMovs][{estado}] $push atómico EXITOSO | "
                    f"Placa={placa} Dui={dui} NoMision={mision_key} | "
                    f"IdMision={id_mision}"
                )
            else:
                # ✗ La entrada de misión no existe en el histórico
                # FALLBACK GARANTIZADO: Crear entrada nueva
                logger.warning(
                    f"[HistoriDiaMovs][{estado}] FALLBACK: Misión no encontrada en histórico | "
                    f"Placa={placa} Dui={dui} NoMision={mision_key} | "
                    f"IdMision={id_mision} | Creando entrada nueva..."
                )

                fallback = col.update_one(
                    filtro_doc,
                    {
                        "$push": {"Misiones": {"Mision": mision_key, "coordenadas": [hist_entry]}},
                        "$set": {"TimeStamp": ahora, "Motorista": motorista_nombre}
                    },
                    upsert=True
                )

                logger.critical(
                    f"[HistoriDiaMovs][fallback] RECUPERACIÓN REALIZADA | "
                    f"Placa={placa} Dui={dui} NoMision={mision_key} | "
                    f"upserted={fallback.upserted_id is not None} modified={fallback.modified_count} | "
                    f"IdMision={id_mision} | Estado={estado}"
                )

    except Exception as e:
        # ERROR CRÍTICO: Registrar con contexto completo para análisis
        logger.critical(
            f"[HistoriDiaMovs] ERROR CRÍTICO en replicación | "
            f"Placa={placa} Dui={dui} NoMision={mision_key} Estado={estado} | "
            f"IdMision={id_mision} | "
            f"{type(e).__name__}: {e}",
            exc_info=True
        )
        # No re-lanzar: no debe bloquear la actualización en tiempo real (UltimoMovs)


# -------------------- Actualizar misión --------------------
def actualizar_mision(data: ActualizarMision) -> bool:
    """Actualiza los datos finales de la misión"""
    misiones = ejecutar_query(COLLECTION, {"IdMision": data.id_mision})
    if not misiones:
        return False

    raw = data.model_dump(exclude={"id_mision"})
    update_data = {k: (v if v is not None else "") for k, v in raw.items()}
    update_data["TimeStampActualizacion"] = datetime.utcnow()

    print(update_data)
    updated_count = update_document(
        COLLECTION,
        {"IdMision": data.id_mision},
        {"$set": update_data}
    )

    # Obtener datos de la misión para actualizaciones en SQL
    if misiones:
        vehiculo = misiones[0].get("Placa")
        moto = misiones[0].get("Dui")

        # Usar función consolidada para actualizar estados en SQL
        _actualizar_estados_sql(
            solicitud_id=data.solicitud,
            dui=moto,
            placa=vehiculo,
            estado_solicitud=5,
            disponibilidad_motorista=1,
            estado_vehiculo=1,
            operacion="actualizar_mision"
        )

    return updated_count > 0


#-------------------- Editar misiones --------------------
def editar_mision(data: EditarMision, current_user: dict = None) -> bool:
    """
    Edita los datos de una misión existente y guarda bitácora de cambios.
    
    Args:
        data: Datos a actualizar
        current_user: Usuario que realiza la edición (opcional, para bitácora)
    """

    # Verificamos el número de misión
    nomisiones = ejecutar_query(COLLECTION, {"NoMision": data.nomision})
    if not nomisiones:
        raise HTTPException(status_code=404, detail="Misión no encontrada")

    mision_original = nomisiones[0]

    descripcion = data.descripcion

    update_data = data.model_dump(
        exclude={"nomision"},
        exclude_unset=True
    )

    # Este campo se usa solo para la colección de solicitudes, nunca para actualizar Misiones.
    update_data.pop("descripcion", None)

    # Si no hay nada que actualizar
    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="No se enviaron campos para actualizar"
        )

    # Capturar valores anteriores antes de la actualización
    campos_anteriores = {campo: mision_original.get(campo) for campo in update_data.keys()}

    tz = pytz.timezone("America/El_Salvador")
    update_data["TimeStampActualizacion"] = datetime.now(tz)

    try:
        updated_count = update_document(
            COLLECTION,
            {"NoMision": data.nomision},
            {"$set": update_data}
        )
        
        # Si la actualización fue exitosa, guardar bitácora
        if updated_count > 0 and current_user:
            editor_dui = current_user.get("Dui") or current_user.get("dui") or "desconocido"
            editor_nombre = current_user.get("FullName") or current_user.get("full_name") or ""
            
            _guardar_bitacora_mision_directo(
                mision_original=mision_original,
                cambios_aplicados=update_data,
                campos_anteriores=campos_anteriores,
                editor_dui=editor_dui,
                editor_nombre=editor_nombre
            )

            _guardar_solicitud_mision_directa_aplicada(
                mision_original=mision_original,
                cambios_aplicados=update_data,
                campos_anteriores=campos_anteriores,
                editor_dui=editor_dui,
                editor_nombre=editor_nombre,
                descripcion=descripcion
            )

        return updated_count > 0

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error actualizando misión: {str(e)}"
        )

#-----------------------------------------Obtener misiones solicitadas--------------------



#----------------------------------------- Obtener misiones con filtros y paginación --------------------
def get_misiones(
    placa: str = None,
    dui: str = None,
    mision: str = None,
    solicitante: str = None,
    estado: str = None,
    fecha_inicio: date = None,
    fecha_fin: date = None,
    page: int = 1,
    limit: int = 20
):
    # ---------------- VALIDACIÓN DE RANGO DE FECHAS -----------------
    if fecha_inicio and fecha_fin:
        if fecha_fin < fecha_inicio:
            raise HTTPException(
                status_code=400,
                detail="La fecha_fin no puede ser menor que fecha_inicio."
            )


    filtro = {}
    if placa:
        filtro["Placa"] = placa
    if dui:
        filtro["Dui"] = dui
    if mision:
        filtro["NoMision"] = mision
    if solicitante:
        filtro["Solicitante"] = {"$regex": solicitante, "$options": "i"}
    if estado:
        no_misiones_estado = _obtener_no_misiones_por_estado(
            estado=estado,
            placa=placa,
            dui=dui,
            no_mision=mision
        )
        if not no_misiones_estado:
            return {
                "status": 200,
                "data": {
                    "count": 0,
                    "page": page,
                    "total_pages": 0,
                    "limit": limit,
                    "content": []
                }
            }
        filtro["NoMision"] = {"$in": list(no_misiones_estado)}

    if fecha_inicio:
        inicio_dt = datetime.combine(fecha_inicio, time.min)
        fin_dt = datetime.combine(fecha_fin or fecha_inicio, time.max)
        filtro["FechaHoraSalida"] = {"$gte": inicio_dt, "$lte": fin_dt}

    skip = (page - 1) * limit
    sort = [("FechaHoraSalida", -1)]  # Descendente: primero el más reciente

    documentos = ejecutar_query_V3(
        COLLECTION,
        filtro=filtro,
        skip=skip,
        limit=limit,
        sort=sort
    )

    total_docs = get_db()[COLLECTION].count_documents(filtro)
    total_pages = (total_docs + limit - 1) // limit

    return {
        "status": 200,
        "data": {
            "count": total_docs,
            "page": page,
            "total_pages": total_pages,
            "limit": limit,
            "content": documentos
        }
    }

#------------------Obtener el kilometraje por mision-----------------------
def get_kilometraje_misiones(IdMision: str = None) -> Optional[float]:
    if not IdMision:
        raise HTTPException(status_code=400, detail="Debe proporcionar un IdMision válido.")

    try:
        misiones = ejecutar_query(COLLECTION, {"IdMision": IdMision})
        if not misiones:
            raise HTTPException(status_code=404, detail="No se encontraron misiones con el IdMision proporcionado.")

        val = misiones[0].get("KilometrajeInicial")

        if val is None:
            return None

        # Intentar convertir a número (float) si es posible
        if isinstance(val, (int, float)):
            return float(val)
        try:
            return float(str(val))
        except (ValueError, TypeError):
            return None

    except HTTPException:
        # Re-lanzar errores HTTP para que conserven su código y detalle
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando la misión: {str(e)}")

#--------------------------------------------------------------------------------------------------
def get_misiones_solicitadas_SQL_por_dui(dui: str):
    db = VerificadorSQL(prefix="MSSQL")

    query_solicitud = """
    SELECT TOP 1
    s.idSolicitud, 
    s.codSolicitud,
    s.estado,
    s.fechSolicitud,
    s.fechAprobacion,
    s.fechCancelacion,
    d.nombDepto,

    -- SOLICITANTE
    sol.nombSoli,
    sol.apeSoli,
    sol.cargoSoli,
    sol.emailSoli,

    -- VEHICULOS
    v_out.idVehiculo AS idVehiculoSalida,
    v_out.placaVehiculo AS placaSalida,
    v_out.marca AS marcaSalida,
    v_out.modelo AS modeloSalida,
    v_out.color AS colorSalida,

    v_in.idVehiculo AS idVehiculoEntrada,
    v_in.placaVehiculo AS placaEntrada,
    v_in.marca AS marcaEntrada,
    v_in.modelo AS modeloEntrada,
    v_in.color AS colorEntrada,

    -- MOTORISTAS
    m_out.idMoto AS idMotoristaSalida,
    m_out.primer_nombre AS nombreSalida,
    m_out.primer_ape AS apellidoSalida,
    m_out.dui AS duiSalida,
    m_out.telefono AS telefonoSalida,

    m_in.idMoto AS idMotoristaEntrada,
    m_in.primer_nombre AS nombreEntrada,
    m_in.primer_ape AS apellidoEntrada,
    m_in.dui AS duiEntrada,
    m_in.telefono AS telefonoEntrada,

    CONVERT(VARCHAR, ds.fecha, 23) AS fecha,
    CONVERT(VARCHAR, ds.hora, 108) AS hora,

    -- TIPO MOTORISTA
    CASE 
        WHEN m_out.dui = %s THEN 'salida'
        WHEN m_in.dui = %s THEN 'entrada'
    END AS tipo_motorista

    FROM solicitudes s
    INNER JOIN detallesolicitud ds 
        ON ds.idSolicitud = s.idSolicitud

    LEFT JOIN departamento d 
        ON d.idDepto = s.idDepto

    LEFT JOIN solicitantes sol 
        ON sol.idSoli = s.idSoli

    -- VEHICULOS
    LEFT JOIN vehiculos v_out 
        ON v_out.idVehiculo = ds.idVehiSalida
    LEFT JOIN vehiculos v_in  
        ON v_in.idVehiculo = ds.idVehiEntrada

    -- MOTORISTAS
    LEFT JOIN motoristas m_out 
        ON m_out.idMoto = ds.idMotoristaSalida
    LEFT JOIN motoristas m_in  
        ON m_in.idMoto = ds.idMotoristaEntrada

    WHERE (
        m_out.dui = %s
        OR m_in.dui = %s
    )
    AND s.estado = 1
   AND (CAST(ds.fecha AS DATETIME) + CAST(ds.hora AS DATETIME))
    >= DATEADD(HOUR, -6, GETDATE())

    AND (CAST(ds.fecha AS DATETIME) + CAST(ds.hora AS DATETIME))
    < DATEADD(DAY, 1, CONVERT(date, GETDATE()))

    ORDER BY CAST(CAST(ds.fecha AS datetime) + CAST(ds.hora AS datetime) AS datetime2) ASC
    """

    solicitud = db.ejecutar_querySQL(
        query=query_solicitud,
        tipo="SELECT",
        params=(dui, dui, dui, dui)  # 4 veces: 2 para el CASE, 2 para el WHERE
    )

    if not solicitud:
        return None

    # LUGARES
    query_lugares = """
    SELECT 
        dsl.idDetSoliLugares,
        dsl.idSolicitud,
        dsl.idLugares,
        dsl.puntoPartida,
        l.nombLugar,
        l.direLugar,
        l.logintud,
        l.latitud
    FROM detallesolicitudlugares dsl
    INNER JOIN lugares l 
        ON l.idLugar = dsl.idLugares
    WHERE dsl.idSolicitud = %s
    ORDER BY dsl.puntoPartida DESC
    """

    lugares = db.ejecutar_querySQL(
        query=query_lugares,
        tipo="SELECT",
        params=(solicitud[0]['idSolicitud'],)
    )

    solicitud[0]['lugares'] = lugares

    return solicitud[0]


# -------------------- Servicios para Facturas -------------------- #

def agregar_factura(data: AgregarFactura) -> str:
    """
    Agrega una nueva factura con cupones a una misión existente.

    Args:
        data: Datos de la factura a agregar

    Returns:
        id_factura: UUID de la factura creada

    Raises:
        HTTPException: Si la misión no existe o si ocurre un error
    """
    # Validar que la misión existe
    misiones = ejecutar_query(COLLECTION, {"IdMision": data.id_mision})

    if not misiones:
        raise HTTPException(
            status_code=404,
            detail=f"Misión con IdMision {data.id_mision} no encontrada"
        )

    mision = misiones[0]

    # Generar ID único para la factura
    id_factura = str(uuid.uuid4())

    # Preparar cupones
    cupones_list = [{"NumeroCupon": cupon.numero_cupon} for cupon in data.cupones]

    # Crear documento de factura
    factura_doc = {
        "IdFactura": id_factura,
        "NumeroFactura": data.numero_factura,
        "CantidadGalones": data.cantidad_galones,
        "CantidadDolares": data.cantidad_dolares,
        "FechaFactura": datetime.utcnow(),
        "Cupones": cupones_list,
        "TimeStamp": datetime.utcnow(),
        # Estado por defecto: active (las facturas recién agregadas están activas)
        "Estado": "active"
    }

    # Obtener facturas existentes o crear array vacío
    facturas = mision.get("Facturas", [])
    facturas.append(factura_doc)

    # Actualizar la misión
    updated_count = update_document(
        COLLECTION,
        {"IdMision": data.id_mision},
        {
            "$set": {
                "Facturas": facturas,
                "TimeStampActualizacion": datetime.utcnow()
            }
        }
    )

    if updated_count <= 0:
        raise HTTPException(
            status_code=500,
            detail="No se pudo agregar la factura a la misión"
        )

    logging.info(f"Factura {id_factura} agregada a misión {data.id_mision}")
    return id_factura

def editar_factura(data: EditarFactura, current_user: dict = None) -> bool:
    """
    Edita una factura existente en una misión y guarda bitácora de cambios.

    Args:
        data: Datos de la factura a editar
        current_user: Usuario que realiza la edición (opcional, para bitácora)

    Returns:
        bool: True si se editó correctamente

    Raises:
        HTTPException: Si la misión o factura no existe
    """
    # Validar que la misión existe
    misiones = ejecutar_query(COLLECTION, {"IdMision": data.id_mision})

    if not misiones:
        raise HTTPException(
            status_code=404,
            detail=f"Misión con IdMision {data.id_mision} no encontrada"
        )

    mision = misiones[0]
    facturas = mision.get("Facturas", [])

    if not facturas:
        raise HTTPException(
            status_code=404,
            detail="La misión no tiene facturas"
        )

    # Buscar la factura a editar y capturar valores anteriores
    factura_encontrada = False
    factura_anterior = None
    cambios_factura = {}
    
    for factura in facturas:
        if factura.get("IdFactura") == data.id_factura:
            factura_encontrada = True
            factura_anterior = factura.copy()  # Snapshot de la factura antes

            # Actualizar solo los campos proporcionados
            if data.numero_factura is not None:
                cambios_factura["NumeroFactura"] = data.numero_factura
                factura["NumeroFactura"] = data.numero_factura

            if data.cantidad_galones is not None:
                cambios_factura["CantidadGalones"] = data.cantidad_galones
                factura["CantidadGalones"] = data.cantidad_galones

            if data.cantidad_dolares is not None:
                cambios_factura["CantidadDolares"] = data.cantidad_dolares
                factura["CantidadDolares"] = data.cantidad_dolares

            if data.cupones is not None:
                # Reemplazar la lista completa de cupones
                cupones_nuevos = [{"NumeroCupon": cupon.numero_cupon} for cupon in data.cupones]
                cambios_factura["Cupones"] = cupones_nuevos
                factura["Cupones"] = cupones_nuevos

            # Actualizar timestamp de modificación
            factura["TimeStampActualizacion"] = datetime.utcnow()
            break

    if not factura_encontrada:
        raise HTTPException(
            status_code=404,
            detail=f"Factura con IdFactura {data.id_factura} no encontrada en la misión"
        )

    # Actualizar la misión con las facturas modificadas
    updated_count = update_document(
        COLLECTION,
        {"IdMision": data.id_mision},
        {
            "$set": {
                "Facturas": facturas,
                "TimeStampActualizacion": datetime.utcnow()
            }
        }
    )

    if updated_count <= 0:
        raise HTTPException(
            status_code=500,
            detail="No se pudo actualizar la factura"
        )

    # Si la actualización fue exitosa, guardar bitácora
    if current_user:
        editor_dui = current_user.get("Dui") or current_user.get("dui") or "desconocido"
        editor_nombre = current_user.get("FullName") or current_user.get("full_name") or ""
        
        # Preparar campos anteriores (solo los que se modificaron)
        campos_anteriores = {}
        for campo in cambios_factura.keys():
            campos_anteriores[campo] = factura_anterior.get(campo)
        
        _guardar_bitacora_factura_directo(
            id_mision=data.id_mision,
            no_mision=mision.get("NoMision"),
            id_factura=data.id_factura,
            cambios_aplicados=cambios_factura,
            campos_anteriores=campos_anteriores,
            editor_dui=editor_dui,
            editor_nombre=editor_nombre,
            placa=mision.get("Placa"),
            dui=mision.get("Dui")
        )

        _guardar_solicitud_factura_directa_aplicada(
            id_mision=data.id_mision,
            no_mision=mision.get("NoMision"),
            id_factura=data.id_factura,
            cambios_aplicados=cambios_factura,
            campos_anteriores=campos_anteriores,
            editor_dui=editor_dui,
            editor_nombre=editor_nombre,
            placa=mision.get("Placa"),
            dui=mision.get("Dui"),
            descripcion=data.descripcion,
            review_observations=data.review_observations
        )

    logging.info(f"Factura {data.id_factura} editada en misión {data.id_mision}")
    return True


def obtener_facturas(id_mision: str, include_deleted: bool = False) -> dict:
    """
    Obtiene todas las facturas de una misión.

    Args:
        id_mision: ID de la misión

    Returns:
        dict: Información de la misión con sus facturas

    Raises:
        HTTPException: Si la misión no existe
    """
    # Validar que la misión existe
    misiones = ejecutar_query(COLLECTION, {"IdMision": id_mision})

    if not misiones:
        raise HTTPException(
            status_code=404,
            detail=f"Misión con IdMision {id_mision} no encontrada"
        )

    mision = misiones[0]
    facturas = mision.get("Facturas", [])

    # Decidir si incluir facturas eliminadas según parámetro
    if include_deleted:
        # incluir todas las facturas
        active_facturas = facturas
    else:
        # Filtrar sólo facturas activas (no marcadas como deleted)
        active_facturas = [f for f in facturas if f.get("Estado") != "deleted"]

    # Calcular totales sobre facturas consideradas
    total_galones = sum(f.get("CantidadGalones", 0) for f in active_facturas)
    total_dolares = sum(f.get("CantidadDolares", 0) for f in active_facturas)
    total_cupones = sum(len(f.get("Cupones", [])) for f in active_facturas)

    return {
         "IdMision": id_mision,
         "NoMision": mision.get("NoMision"),
         "Placa": mision.get("Placa"),
         "Dui": mision.get("Dui"),
         "NombreMotorista": mision.get("NombreMotorista"),
        "CantidadFacturas": len(active_facturas),
        "TotalGalones": total_galones,
        "TotalDolares": total_dolares,
        "TotalCupones": total_cupones,
        "Facturas": active_facturas
    }


def eliminar_factura(data: EliminarFactura) -> bool:
    """
    Elimina una factura de una misión.

    Args:
        data: Datos para eliminar la factura

    Returns:
        bool: True si se eliminó correctamente

    Raises:
        HTTPException: Si la misión o factura no existe
    """
    # Validar que la misión existe
    misiones = ejecutar_query(COLLECTION, {"IdMision": data.id_mision})

    if not misiones:
        raise HTTPException(
            status_code=404,
            detail=f"Misión con IdMision {data.id_mision} no encontrada"
        )

    mision = misiones[0]
    facturas = mision.get("Facturas", [])

    if not facturas:
        raise HTTPException(
            status_code=404,
            detail="La misión no tiene facturas"
        )

    # Filtrar la factura a eliminar
    facturas_filtradas = [f for f in facturas if f.get("IdFactura") != data.id_factura]

    # Verificar si se eliminó alguna factura
    if len(facturas_filtradas) == len(facturas):
        raise HTTPException(
            status_code=404,
            detail=f"Factura con IdFactura {data.id_factura} no encontrada en la misión"
        )

    # Actualizar la misión sin la factura eliminada
    updated_count = update_document(
        COLLECTION,
        {"IdMision": data.id_mision},
        {
            "$set": {
                "Facturas": facturas_filtradas,
                "TimeStampActualizacion": datetime.utcnow()
            }
        }
    )

    if updated_count <= 0:
        raise HTTPException(
            status_code=500,
            detail="No se pudo eliminar la factura"
        )

    logging.info(f"Factura {data.id_factura} eliminada de misión {data.id_mision}")
    return True

def forzar_estado_final_por_no_mision(no_mision: str) -> dict:
    """
    Fuerza estado `final` de la ultima coordenada usando HistoriDiaMovs como fuente de verdad.

    Flujo:
    1) HistoriDiaMovs (critico): cambia a `final` la ultima coordenada.
    2) UltimoMovs (secundario): marca `Estado=final`.
    """
    if not no_mision or not no_mision.strip():
        raise HTTPException(status_code=400, detail="Debe enviar un NoMision valido")

    no_mision = no_mision.strip()
    db = get_db()

    # Validar unicidad y estado actual antes de ejecutar pipeline
    misiones = ejecutar_query(COLLECTION, {"NoMision": no_mision})
    if not misiones:
        raise HTTPException(status_code=404, detail=f"No se encontro la mision {no_mision}")
    if len(misiones) > 1:
        raise HTTPException(status_code=409, detail=f"Existen multiples misiones con NoMision {no_mision}")

    mision = misiones[0]
    coordenadas = _obtener_coordenadas_desde_historial(mision.get("Placa"), mision.get("Dui"), no_mision)
    if not coordenadas:
        raise HTTPException(
            status_code=409,
            detail=(
                f"La mision {no_mision} no tiene coordenadas en HistoriDiaMovs; "
                "no se puede forzar estado final sobre la ultima coordenada. "
                "Verifique que existan coordenadas de la misión y que el histórico esté sincronizado."
            )
        )

    last_estado = (coordenadas[-1] or {}).get("Estado")

    # 1) HistoriDiaMovs - CRITICO
    try:
        resultado_hist = db[HISTORICO].update_one(
            {"Placa": mision.get("Placa"), "Dui": mision.get("Dui"), "Misiones.Mision": no_mision},
            [
                {
                    "$set": {
                        "Misiones": {
                            "$map": {
                                "input": "$Misiones",
                                "as": "m",
                                "in": {
                                    "$cond": {
                                        "if": {"$eq": ["$$m.Mision", no_mision]},
                                        "then": {
                                            "$mergeObjects": [
                                                "$$m",
                                                {
                                                    "coordenadas": {
                                                        "$concatArrays": [
                                                            {
                                                                "$slice": [
                                                                    "$$m.coordenadas",
                                                                    {"$subtract": [{"$size": "$$m.coordenadas"}, 1]}
                                                                ]
                                                            },
                                                            [
                                                                {
                                                                    "$mergeObjects": [
                                                                        {"$arrayElemAt": ["$$m.coordenadas", -1]},
                                                                        {"Estado": "final"}
                                                                    ]
                                                                }
                                                            ]
                                                        ]
                                                    }
                                                }
                                            ]
                                        },
                                        "else": "$$m"
                                    }
                                }
                            }
                        },
                        "TimeStamp": datetime.utcnow()
                    }
                }
            ]
        )

        if resultado_hist.matched_count == 0:
            logger.critical("[forzar_final] CRITICO: HistoriDiaMovs sin documento | NoMision=%s", no_mision)
            raise HTTPException(status_code=500, detail="No se pudo actualizar HistoriDiaMovs")
    except HTTPException:
        raise
    except Exception as e:
        logger.critical(
            "[forzar_final] CRITICO: Error actualizando HistoriDiaMovs | NoMision=%s | %s: %s",
            no_mision,
            type(e).__name__,
            e,
            exc_info=True
        )
        raise HTTPException(status_code=500, detail="Error critico actualizando HistoriDiaMovs")

    # 2) UltimoMovs - secundario
    estado_ultimo_movs = "ok"
    try:
        resultado_ult = db[ULTIMOMOVS].update_one(
            {"NoMision": no_mision},
            {"$set": {"Estado": "final", "TimeStamp": datetime.utcnow()}}
        )
        if resultado_ult.matched_count == 0:
            estado_ultimo_movs = "sin_documento"
            logger.warning("[forzar_final] UltimoMovs sin documento | NoMision=%s", no_mision)
    except Exception as e:
        estado_ultimo_movs = "error"
        logger.error(
            "[forzar_final] Error actualizando UltimoMovs | NoMision=%s | %s: %s",
            no_mision,
            type(e).__name__,
            e,
            exc_info=True
        )

    logger.info(
        "[forzar_final] Finalizacion aplicada | NoMision=%s | EstadoPrevio=%s | UltimoMovs=%s",
        no_mision,
        last_estado,
        estado_ultimo_movs
    )

    return {
        "NoMision": no_mision,
        "misiones": "ok",
        "ultimo_movs": estado_ultimo_movs,
        "histori_dia_movs": "ok",
        "estado_previo": last_estado,
        "estado_actual": "final"
    }

# -------------------- Auxiliar: Guardar Bitácora de Cambios Directos --------------------
def _guardar_bitacora_mision_directo(
    mision_original: dict,
    cambios_aplicados: dict,
    campos_anteriores: dict,
    editor_dui: str,
    editor_nombre: str = ""
):
    """
    Guarda registro en BitacoraCambiosMision para ediciones DIRECTAS (sin solicitud).
    
    Args:
        mision_original: Documento de misión antes de cambios
        cambios_aplicados: Dict con campos modificados
        campos_anteriores: Dict con valores anteriores
        editor_dui: DUI del usuario que editó
        editor_nombre: Nombre del editor
    """
    try:
        id_bitacora = str(uuid.uuid4())
        
        documento_bitacora = {
            "IdBitacora": id_bitacora,
            "IdMision": mision_original.get("IdMision"),
            "NoMision": mision_original.get("NoMision"),
            "Placa": mision_original.get("Placa"),
            "Dui": mision_original.get("Dui"),
            "IdSolicitud": None,
            "tipo_edicion": "direct",
            "cambios": [
                {
                    "campo": campo,
                    "valor_anterior": campos_anteriores.get(campo),
                    "valor_nuevo": cambios_aplicados.get(campo)
                }
                for campo in cambios_aplicados.keys()
                if campo not in ["TimeStampActualizacion", "Facturas"]
            ],
            "editado_por": {
                "dui": editor_dui,
                "name": editor_nombre
            },
            "solicitado_por": None,
            "aprobado_por": None,
            "solicitud_type": "mision_edicion_directa",
            "solicitud_status": "direct",
            "fecha_edicion": datetime.utcnow(),
            "descripcion_solicitud": None
        }
        
        insert_document(BITACORA_CAMBIOS, documento_bitacora)
        
        logger.info(
            f"[Bitácora][Direct] Cambios guardados | NoMision={mision_original.get('NoMision')} "
            f"Editor={editor_dui} | IdBitacora={id_bitacora}"
        )
        
    except Exception as e:
        logger.error(
            f"[Bitácora][Direct] Error guardando bitácora | NoMision={mision_original.get('NoMision')} | {e}",
            exc_info=True
        )


def _guardar_solicitud_mision_directa_aplicada(
    mision_original: dict,
    cambios_aplicados: dict,
    campos_anteriores: dict,
    editor_dui: str,
    editor_nombre: str = "",
    descripcion: str = None
):
    """
    Guarda una solicitud aplicada para ediciones directas de misión.

    Se usa la misma colección de solicitudes para mantener trazabilidad homogénea
    con las flujos de aprobación, pero marcando la edición como directa y aplicada.
    """
    try:
        fecha_evento = datetime.now(timezone.utc)
        id_solicitud = str(uuid.uuid4())

        cambios_filtrados = {
            campo: valor
            for campo, valor in cambios_aplicados.items()
            if campo != "TimeStampActualizacion"
        }
        datos_actuales = {
            campo: campos_anteriores.get(campo)
            for campo in cambios_filtrados.keys()
        }

        editor_data = {
            "dui": editor_dui,
            "name": editor_nombre
        }

        documento_solicitud = {
            "IdSolicitud": id_solicitud,
            "type": "mision_edicion",
            "solicitud_type": "mision_edicion_directa",
            "tipo_edicion": "direct",
            "NoMision": mision_original.get("NoMision"),
            "IdMision": mision_original.get("IdMision"),
            "Placa": mision_original.get("Placa"),
            "Dui": mision_original.get("Dui"),
            "requested_by": editor_data,
            "descripcion": descripcion,
            "datos_actuales_mision": datos_actuales,
            "cambios_solicitados": cambios_filtrados,
            "status": "applied",
            "reviewed_by": editor_data,
            "review_observations": "Edición directa aplicada sin flujo de solicitud.",
            "created_at": fecha_evento,
            "reviewed_at": fecha_evento,
            "applied": True,
            "applied_at": fecha_evento,
            "applied_by": editor_data
        }

        insert_document(SOLICITUDES_EDICION, documento_solicitud)

        logger.info(
            f"[Solicitud][Direct] Solicitud aplicada guardada | NoMision={mision_original.get('NoMision')} "
            f"Editor={editor_dui} | IdSolicitud={id_solicitud}"
        )

    except Exception as e:
        logger.error(
            f"[Solicitud][Direct] Error guardando solicitud aplicada | NoMision={mision_original.get('NoMision')} | {e}",
            exc_info=True
        )


def _guardar_bitacora_factura_directo(
    id_mision: str,
    no_mision: str,
    id_factura: str,
    cambios_aplicados: dict,
    campos_anteriores: dict,
    editor_dui: str,
    editor_nombre: str = "",
    placa: str = None,
    dui: str = None
):
    """
    Guarda registro de edición DIRECTA de factura en BitacoraCambiosMision.
    """
    try:
        id_bitacora = str(uuid.uuid4())

        documento_bitacora = {
            "IdBitacora": id_bitacora,
            "IdMision": id_mision,
            "NoMision": no_mision,
            "Placa": placa,
            "Dui": dui,
            "IdSolicitud": None,
            "IdFactura": id_factura,
            "tipo_edicion": "direct",
            "cambios": [
                {
                    "campo": campo,
                    "valor_anterior": campos_anteriores.get(campo),
                    "valor_nuevo": cambios_aplicados.get(campo)
                }
                for campo in cambios_aplicados.keys()
                if campo not in ["TimeStampActualizacion", "TimeStampEdicion"]
            ],
            "editado_por": {
                "dui": editor_dui,
                "name": editor_nombre
            },
            "solicitado_por": None,
            "aprobado_por": None,
            "solicitud_type": "factura_edicion_directa",
            "solicitud_status": "direct",
            "fecha_edicion": datetime.utcnow(),
            "descripcion_solicitud": None
        }

        # IMPORTANTE: se usa la misma colección única de bitácora.
        insert_document(BITACORA_CAMBIOS, documento_bitacora)

        logger.info(
            f"[Bitácora][Factura][Direct] Cambios guardados en {BITACORA_CAMBIOS} | "
            f"NoMision={no_mision} IdFactura={id_factura} Editor={editor_dui} | IdBitacora={id_bitacora}"
        )

    except Exception as e:
        logger.error(
            f"[Bitácora][Factura][Direct] Error guardando bitácora | IdFactura={id_factura} | {e}",
            exc_info=True
        )


def _guardar_solicitud_factura_directa_aplicada(
    id_mision: str,
    no_mision: str,
    id_factura: str,
    cambios_aplicados: dict,
    campos_anteriores: dict,
    editor_dui: str,
    editor_nombre: str = "",
    placa: str = None,
    dui: str = None,
    descripcion: str = None,
    review_observations: str = None
):
    """
    Guarda una solicitud aplicada para ediciones directas de factura.

    Usa la misma colección de solicitudes y marca el flujo como edición directa aplicada.
    """
    try:
        fecha_evento = datetime.now(timezone.utc)
        id_solicitud = str(uuid.uuid4())

        editor_data = {
            "dui": editor_dui,
            "name": editor_nombre
        }

        documento_solicitud = {
            "IdSolicitud": id_solicitud,
            "type": "factura_edicion",
            "solicitud_type": "factura_edicion_directa",
            "tipo_edicion": "direct",
            "NoMision": no_mision,
            "IdMision": id_mision,
            "IdFactura": id_factura,
            "Placa": placa,
            "Dui": dui,
            "requested_by": editor_data,
            "descripcion": descripcion,
            "datos_actuales_factura": campos_anteriores,
            "cambios_solicitados": cambios_aplicados,
            "status": "applied",
            "reviewed_by": editor_data,
            "review_observations": review_observations or "Edición directa de factura aplicada sin flujo de solicitud.",
            "created_at": fecha_evento,
            "reviewed_at": fecha_evento,
            "applied": True,
            "applied_at": fecha_evento,
            "applied_by": editor_data
        }

        insert_document(SOLICITUDES_EDICION, documento_solicitud)

        logger.info(
            f"[Solicitud][Factura][Direct] Solicitud aplicada guardada | "
            f"NoMision={no_mision} IdFactura={id_factura} Editor={editor_dui} | IdSolicitud={id_solicitud}"
        )

    except Exception as e:
        logger.error(
            f"[Solicitud][Factura][Direct] Error guardando solicitud aplicada | "
            f"NoMision={no_mision} IdFactura={id_factura} | {e}",
            exc_info=True
        )

