# services/mision_estadisticas_services.py

from datetime import datetime, date
from typing import Optional, Dict, Any
from database.verificador_mongo import get_db
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
    Obtiene estadísticas de las solicitudes de edición de misión.

    Args:
        fecha_inicio: Fecha inicial del rango de búsqueda
        fecha_fin: Fecha final del rango de búsqueda
        tipo_solicitud: Tipo de solicitud a filtrar (mision_edicion, factura_edicion, factura_eliminacion)

    Returns:
        Diccionario con las estadísticas:
        - total: Total de solicitudes
        - aprobadas: Cantidad de solicitudes aprobadas
        - rechazadas: Cantidad de solicitudes rechazadas
        - pendientes: Cantidad de solicitudes pendientes
        - por_tipo: Desglose por tipo de solicitud (si no se filtró por tipo)
    """
    try:
        # Construir el filtro de agregación
        match_stage = {}

        # Filtro por rango de fechas (usando created_at)
        if fecha_inicio or fecha_fin:
            date_filter = {}
            if fecha_inicio:
                # Convertir fecha a datetime (inicio del día)
                fecha_inicio_dt = datetime.combine(fecha_inicio, datetime.min.time())
                date_filter["$gte"] = fecha_inicio_dt
            if fecha_fin:
                # Convertir fecha a datetime (fin del día)
                fecha_fin_dt = datetime.combine(fecha_fin, datetime.max.time())
                date_filter["$lte"] = fecha_fin_dt

            match_stage["created_at"] = date_filter

        # Filtro por tipo de solicitud
        if tipo_solicitud:
            # Validar tipo de solicitud
            tipos_validos = ["mision_edicion", "factura_edicion", "factura_eliminacion"]
            if tipo_solicitud not in tipos_validos:
                raise HTTPException(
                    status_code=400,
                    detail=f"Tipo de solicitud inválido. Debe ser uno de: {', '.join(tipos_validos)}"
                )
            match_stage["type"] = tipo_solicitud

        # Pipeline de agregación
        pipeline = []

        # Agregar stage de match si hay filtros
        if match_stage:
            pipeline.append({"$match": match_stage})

        # Agregar stage para contar por estado
        pipeline.extend([
            {
                "$group": {
                    "_id": {
                        "status": "$status",
                        "type": "$type"
                    },
                    "count": {"$sum": 1}
                }
            }
        ])

        # Ejecutar la agregación
        db = get_db()
        resultados = list(db[SOLICITUDES_EDICION].aggregate(pipeline))

        # Procesar resultados
        estadisticas = {
            "total": 0,
            "aprobadas": 0,
            "rechazadas": 0,
            "pendientes": 0,
            "por_tipo": {
                "mision_edicion": {"total": 0, "aprobadas": 0, "rechazadas": 0, "pendientes": 0},
                "factura_edicion": {"total": 0, "aprobadas": 0, "rechazadas": 0, "pendientes": 0},
                "factura_eliminacion": {"total": 0, "aprobadas": 0, "rechazadas": 0, "pendientes": 0},
                "sin_tipo": {"total": 0, "aprobadas": 0, "rechazadas": 0, "pendientes": 0}
                # Para solicitudes antiguas sin tipo
            }
        }

        # Contar por estado y tipo
        for item in resultados:
            status = item["_id"].get("status", "pending")
            tipo = item["_id"].get("type", "sin_tipo")
            count = item["count"]

            # Si no tiene tipo, usar "sin_tipo" (para compatibilidad con solicitudes antiguas)
            if not tipo:
                tipo = "sin_tipo"

            # Actualizar totales generales
            estadisticas["total"] += count

            if status == "approved":
                estadisticas["aprobadas"] += count
            elif status == "rejected":
                estadisticas["rechazadas"] += count
            else:
                estadisticas["pendientes"] += count

            # Actualizar estadísticas por tipo
            if tipo in estadisticas["por_tipo"]:
                estadisticas["por_tipo"][tipo]["total"] += count

                if status == "approved":
                    estadisticas["por_tipo"][tipo]["aprobadas"] += count
                elif status == "rejected":
                    estadisticas["por_tipo"][tipo]["rechazadas"] += count
                else:
                    estadisticas["por_tipo"][tipo]["pendientes"] += count

        # Si se filtró por tipo específico, simplificar la respuesta
        if tipo_solicitud:
            tipo_stats = estadisticas["por_tipo"].get(tipo_solicitud, {
                "total": 0, "aprobadas": 0, "rechazadas": 0, "pendientes": 0
            })
            estadisticas["detalles_tipo"] = tipo_stats
            # No necesitamos el desglose completo si se filtró por tipo
            del estadisticas["por_tipo"]

        # Agregar información de filtros aplicados
        estadisticas["filtros_aplicados"] = {
            "fecha_inicio": fecha_inicio.isoformat() if fecha_inicio else None,
            "fecha_fin": fecha_fin.isoformat() if fecha_fin else None,
            "tipo_solicitud": tipo_solicitud
        }

        logger.info(
            f"Estadísticas obtenidas: Total={estadisticas['total']}, "
            f"Aprobadas={estadisticas['aprobadas']}, "
            f"Rechazadas={estadisticas['rechazadas']}, "
            f"Pendientes={estadisticas['pendientes']}"
        )

        return estadisticas

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas de solicitudes: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo estadísticas: {str(e)}"
        )


def obtener_detalle_solicitudes(
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        tipo_solicitud: Optional[str] = None,
        estado: Optional[str] = None,
        page: int = 1,
        limit: int = 20
) -> Dict[str, Any]:
    """
    Obtiene el listado detallado de solicitudes con filtros.

    Args:
        fecha_inicio: Fecha inicial del rango
        fecha_fin: Fecha final del rango
        tipo_solicitud: Tipo de solicitud
        estado: Estado de la solicitud (approved, rejected, pending)
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
            estados_validos = ["approved", "rejected", "pending"]
            if estado not in estados_validos:
                raise HTTPException(
                    status_code=400,
                    detail=f"Estado inválido. Debe ser uno de: {', '.join(estados_validos)}"
                )
            filtro["status"] = estado

        # Calcular skip para paginación
        skip = (page - 1) * limit

        # Ordenar por fecha de creación descendente
        sort = [("created_at", -1)]

        # Ejecutar query con paginación
        from database.verificador_mongo import ejecutar_query_V3, count_documents

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
                "estado": estado
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo detalle de solicitudes: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo detalle de solicitudes: {str(e)}"
        )