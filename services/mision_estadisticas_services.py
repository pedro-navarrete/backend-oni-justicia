# services/mision_estadisticas_services.py

from datetime import datetime, date
from typing import Optional, Dict, Any
from database.verificador_mongo import get_db, ejecutar_query_V3, count_documents
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

# Nombre de la colección de solicitudes de edición
SOLICITUDES_EDICION = "SolicitudesEdicionMision"


def obtener_estadisticas_solicitudes(
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        tipo_solicitud: Optional[str] = None
) -> Dict[str, Any]:
    """
    Obtiene estadísticas completas de las solicitudes de edición.

    Estadísticas incluidas:
    - Por estado: pending, approved, rejected, applied
    - Por tipo: mision_edicion, factura_edicion, factura_eliminacion
    - Por origen: manual, automatico, directo (nuevo formato V2)
    - Por flujo: completo, simplificado (nuevo formato V2)
    - Solicitudes aplicadas vs no aplicadas

    Args:
        fecha_inicio: Fecha inicial del rango de búsqueda
        fecha_fin: Fecha final del rango de búsqueda
        tipo_solicitud: Tipo de solicitud a filtrar

    Returns:
        Diccionario con estadísticas detalladas
    """
    try:
        # Construir el filtro de agregación
        match_stage = {}

        # Filtro por rango de fechas (usando created_at)
        if fecha_inicio or fecha_fin:
            date_filter = {}
            if fecha_inicio:
                fecha_inicio_dt = datetime.combine(fecha_inicio, datetime.min.time())
                date_filter["$gte"] = fecha_inicio_dt
            if fecha_fin:
                fecha_fin_dt = datetime.combine(fecha_fin, datetime.max.time())
                date_filter["$lte"] = fecha_fin_dt
            match_stage["created_at"] = date_filter

        # Filtro por tipo de solicitud
        if tipo_solicitud:
            tipos_validos = ["mision_edicion", "factura_edicion", "factura_eliminacion"]
            if tipo_solicitud not in tipos_validos:
                raise HTTPException(
                    status_code=400,
                    detail=f"Tipo de solicitud inválido. Debe ser uno de: {', '.join(tipos_validos)}"
                )
            match_stage["type"] = tipo_solicitud

        db = get_db()

        # ==================== ESTADÍSTICAS POR ESTADO ====================
        pipeline_estado = []
        if match_stage:
            pipeline_estado.append({"$match": match_stage})

        pipeline_estado.append({
            "$group": {
                "_id": "$status",
                "count": {"$sum": 1}
            }
        })

        resultados_estado = list(db[SOLICITUDES_EDICION].aggregate(pipeline_estado))

        # ==================== ESTADÍSTICAS POR TIPO ====================
        pipeline_tipo = []
        if match_stage:
            pipeline_tipo.append({"$match": match_stage})

        pipeline_tipo.append({
            "$group": {
                "_id": "$type",
                "count": {"$sum": 1}
            }
        })

        resultados_tipo = list(db[SOLICITUDES_EDICION].aggregate(pipeline_tipo))

        # ==================== ESTADÍSTICAS POR ORIGEN (NUEVO) ====================
        pipeline_origen = []
        if match_stage:
            pipeline_origen.append({"$match": match_stage})

        pipeline_origen.append({
            "$group": {
                "_id": "$metadata.origen",
                "count": {"$sum": 1}
            }
        })

        resultados_origen = list(db[SOLICITUDES_EDICION].aggregate(pipeline_origen))

        # ==================== ESTADÍSTICAS POR FLUJO (NUEVO) ====================
        pipeline_flujo = []
        if match_stage:
            pipeline_flujo.append({"$match": match_stage})

        pipeline_flujo.append({
            "$group": {
                "_id": "$metadata.flujo",
                "count": {"$sum": 1}
            }
        })

        resultados_flujo = list(db[SOLICITUDES_EDICION].aggregate(pipeline_flujo))

        # ==================== ESTADÍSTICAS DE APLICADAS ====================
        pipeline_aplicadas = []
        if match_stage:
            pipeline_aplicadas.append({"$match": match_stage})

        pipeline_aplicadas.append({
            "$group": {
                "_id": "$applied",
                "count": {"$sum": 1}
            }
        })

        resultados_aplicadas = list(db[SOLICITUDES_EDICION].aggregate(pipeline_aplicadas))

        # ==================== ESTADÍSTICAS COMBINADAS (TIPO + ESTADO) ====================
        pipeline_combinado = []
        if match_stage:
            pipeline_combinado.append({"$match": match_stage})

        pipeline_combinado.append({
            "$group": {
                "_id": {
                    "type": "$type",
                    "status": "$status"
                },
                "count": {"$sum": 1}
            }
        })

        resultados_combinado = list(db[SOLICITUDES_EDICION].aggregate(pipeline_combinado))

        # ==================== PROCESAR RESULTADOS ====================

        # Inicializar estructura de estadísticas
        estadisticas = {
            "total": 0,

            # Por estado
            "por_estado": {
                "pending": 0,
                "approved": 0,
                "rejected": 0,
                "applied": 0
            },

            # Por tipo
            "por_tipo": {
                "mision_edicion": 0,
                "factura_edicion": 0,
                "factura_eliminacion": 0
            },

            # Por origen (nuevo)
            "por_origen": {
                "manual": 0,
                "automatico": 0,
                "directo": 0,
                "sin_metadata": 0  # Para solicitudes antiguas
            },

            # Por flujo (nuevo)
            "por_flujo": {
                "completo": 0,
                "simplificado": 0,
                "sin_metadata": 0  # Para solicitudes antiguas
            },

            # Aplicadas vs pendientes de aplicar
            "aplicacion": {
                "aplicadas": 0,
                "no_aplicadas": 0
            },

            # Detalle combinado tipo + estado
            "detalle_por_tipo": {
                "mision_edicion": {
                    "total": 0,
                    "pending": 0,
                    "approved": 0,
                    "rejected": 0,
                    "applied": 0
                },
                "factura_edicion": {
                    "total": 0,
                    "pending": 0,
                    "approved": 0,
                    "rejected": 0,
                    "applied": 0
                },
                "factura_eliminacion": {
                    "total": 0,
                    "pending": 0,
                    "approved": 0,
                    "rejected": 0,
                    "applied": 0
                }
            }
        }

        # Procesar resultados por estado
        for item in resultados_estado:
            status = item["_id"] or "pending"
            count = item["count"]
            estadisticas["total"] += count
            if status in estadisticas["por_estado"]:
                estadisticas["por_estado"][status] = count

        # Procesar resultados por tipo
        for item in resultados_tipo:
            tipo = item["_id"]
            count = item["count"]
            if tipo and tipo in estadisticas["por_tipo"]:
                estadisticas["por_tipo"][tipo] = count

        # Procesar resultados por origen
        for item in resultados_origen:
            origen = item["_id"] or "sin_metadata"
            count = item["count"]
            if origen in estadisticas["por_origen"]:
                estadisticas["por_origen"][origen] = count
            else:
                estadisticas["por_origen"]["sin_metadata"] += count

        # Procesar resultados por flujo
        for item in resultados_flujo:
            flujo = item["_id"] or "sin_metadata"
            count = item["count"]
            if flujo in estadisticas["por_flujo"]:
                estadisticas["por_flujo"][flujo] = count
            else:
                estadisticas["por_flujo"]["sin_metadata"] += count

        # Procesar resultados de aplicadas
        for item in resultados_aplicadas:
            aplicada = item["_id"]
            count = item["count"]
            if aplicada:
                estadisticas["aplicacion"]["aplicadas"] = count
            else:
                estadisticas["aplicacion"]["no_aplicadas"] = count

        # Procesar resultados combinados (tipo + estado)
        for item in resultados_combinado:
            tipo = item["_id"].get("type")
            status = item["_id"].get("status", "pending")
            count = item["count"]

            if tipo and tipo in estadisticas["detalle_por_tipo"]:
                estadisticas["detalle_por_tipo"][tipo]["total"] += count
                if status in estadisticas["detalle_por_tipo"][tipo]:
                    estadisticas["detalle_por_tipo"][tipo][status] = count

        # Agregar información de filtros aplicados
        estadisticas["filtros_aplicados"] = {
            "fecha_inicio": fecha_inicio.isoformat() if fecha_inicio else None,
            "fecha_fin": fecha_fin.isoformat() if fecha_fin else None,
            "tipo_solicitud": tipo_solicitud
        }

        # Agregar resumen útil
        estadisticas["resumen"] = {
            "total": estadisticas["total"],
            "pendientes_revision": estadisticas["por_estado"]["pending"],
            "pendientes_aplicacion": estadisticas["por_estado"]["approved"],
            "aplicadas": estadisticas["aplicacion"]["aplicadas"],
            "rechazadas": estadisticas["por_estado"]["rejected"],
            "ediciones_directas": estadisticas["por_origen"]["directo"],
            "con_flujo_aprobacion": estadisticas["por_flujo"]["completo"]
        }

        logger.info(
            f"Estadísticas obtenidas: Total={estadisticas['total']}, "
            f"Pendientes={estadisticas['por_estado']['pending']}, "
            f"Aprobadas={estadisticas['por_estado']['approved']}, "
            f"Aplicadas={estadisticas['aplicacion']['aplicadas']}"
        )

        return estadisticas

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas de solicitudes: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo estadísticas: {str(e)}"
        )


def obtener_detalle_solicitudes(
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        tipo_solicitud: Optional[str] = None,
        estado: Optional[str] = None,
        origen: Optional[str] = None,
        flujo: Optional[str] = None,
        aplicada: Optional[bool] = None,
        page: int = 1,
        limit: int = 20
) -> Dict[str, Any]:
    """
    Obtiene el listado detallado de solicitudes con filtros.

    Args:
        fecha_inicio: Fecha inicial del rango
        fecha_fin: Fecha final del rango
        tipo_solicitud: Tipo de solicitud
        estado: Estado de la solicitud (approved, rejected, pending, applied)
        origen: Origen de la solicitud (manual, automatico, directo)
        flujo: Flujo de la solicitud (completo, simplificado)
        aplicada: Si la solicitud fue aplicada (true/false)
        page: Número de página
        limit: Cantidad de resultados por página

    Returns:
        Diccionario con las solicitudes y metadatos de paginación
    """
    try:
        # Construir filtro
        filtro = {}

        # Filtro por fechas
        if fecha_inicio or fecha_fin:
            date_filter = {}
            if fecha_inicio:
                fecha_inicio_dt = datetime.combine(fecha_inicio, datetime.min.time())
                date_filter["$gte"] = fecha_inicio_dt
            if fecha_fin:
                fecha_fin_dt = datetime.combine(fecha_fin, datetime.max.time())
                date_filter["$lte"] = fecha_fin_dt
            filtro["created_at"] = date_filter

        # Filtro por tipo
        if tipo_solicitud:
            tipos_validos = ["mision_edicion", "factura_edicion", "factura_eliminacion"]
            if tipo_solicitud not in tipos_validos:
                raise HTTPException(
                    status_code=400,
                    detail=f"Tipo de solicitud inválido. Debe ser uno de: {', '.join(tipos_validos)}"
                )
            filtro["type"] = tipo_solicitud

        # Filtro por estado
        if estado:
            estados_validos = ["approved", "rejected", "pending", "applied"]
            if estado not in estados_validos:
                raise HTTPException(
                    status_code=400,
                    detail=f"Estado inválido. Debe ser uno de: {', '.join(estados_validos)}"
                )
            filtro["status"] = estado

        # Filtro por origen
        if origen:
            origenes_validos = ["manual", "automatico", "directo"]
            if origen not in origenes_validos:
                raise HTTPException(
                    status_code=400,
                    detail=f"Origen inválido. Debe ser uno de: {', '.join(origenes_validos)}"
                )
            filtro["metadata.origen"] = origen

        # Filtro por flujo
        if flujo:
            flujos_validos = ["completo", "simplificado"]
            if flujo not in flujos_validos:
                raise HTTPException(
                    status_code=400,
                    detail=f"Flujo inválido. Debe ser uno de: {', '.join(flujos_validos)}"
                )
            filtro["metadata.flujo"] = flujo

        # Filtro por aplicada
        if aplicada is not None:
            filtro["applied"] = aplicada

        # Calcular skip para paginación
        skip = (page - 1) * limit

        # Ordenar por fecha de creación descendente
        sort = [("created_at", -1)]

        # Ejecutar query con paginación
        solicitudes = ejecutar_query_V3(
            collection_name=SOLICITUDES_EDICION,
            filtro=filtro,
            skip=skip,
            limit=limit,
            sort=sort
        )

        # Contar total de documentos
        total_solicitudes = count_documents(SOLICITUDES_EDICION, filtro)

        # Calcular total de páginas
        total_pages = (total_solicitudes + limit - 1) // limit

        return {
            "solicitudes": solicitudes,
            "paginacion": {
                "page": page,
                "limit": limit,
                "total_solicitudes": total_solicitudes,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            },
            "filtros_aplicados": {
                "fecha_inicio": fecha_inicio.isoformat() if fecha_inicio else None,
                "fecha_fin": fecha_fin.isoformat() if fecha_fin else None,
                "tipo_solicitud": tipo_solicitud,
                "estado": estado,
                "origen": origen,
                "flujo": flujo,
                "aplicada": aplicada
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo detalle de solicitudes: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo detalle de solicitudes: {str(e)}"
        )