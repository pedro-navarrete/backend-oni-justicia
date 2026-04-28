# routers/mision_estadisticas_router.py

from fastapi import APIRouter, Depends, Query
from datetime import date
from typing import Optional
from services.mision_estadisticas_services import obtener_estadisticas_solicitudes, obtener_detalle_solicitudes
from routers.user_router import require_bearer_token
from utils.role_dependencies import require_role_access



router = APIRouter(prefix="/mision", tags=["ONI Misión"])

# -------------------- Endpoint de Estadísticas de Solicitudes --------------------
@router.get("/solicitudes/estadisticas")
def api_estadisticas_solicitudes(
        fecha_inicio: Optional[date] = Query(
            None,
            description="Fecha inicial del rango (YYYY-MM-DD)",
            examples=["2026-01-01"]
        ),
        fecha_fin: Optional[date] = Query(
            None,
            description="Fecha final del rango (YYYY-MM-DD)",
            examples=["2026-01-31"]
        ),
        tipo_solicitud: Optional[str] = Query(
            None,
            description="Tipo de solicitud: mision_edicion, factura_edicion, factura_eliminacion",
            examples=["mision_edicion"]
        ),
        current_user: dict = Depends(require_bearer_token),
        _: bool = Depends(require_role_access("/mision/solicitudes/estadisticas"))
):
    """
    Obtiene estadísticas de las solicitudes de edición de misión.

    **Retorna:**
    - total: Total de solicitudes
    - aprobadas: Cantidad de solicitudes aprobadas
    - rechazadas: Cantidad de solicitudes rechazadas
    - pendientes: Cantidad de solicitudes pendientes
    - por_tipo: Desglose por tipo de solicitud (si no se filtró por tipo)
    - filtros_aplicados: Filtros que se aplicaron en la consulta

    **Filtros opcionales:**
    - fecha_inicio: Fecha inicial del rango
    - fecha_fin: Fecha final del rango
    - tipo_solicitud: Tipo específico de solicitud

    **Ejemplo de uso:**
    ```
    GET /mision/solicitudes/estadisticas
    GET /mision/solicitudes/estadisticas?fecha_inicio=2026-01-01&fecha_fin=2026-01-31
    GET /mision/solicitudes/estadisticas?tipo_solicitud=mision_edicion
    GET /mision/solicitudes/estadisticas?fecha_inicio=2026-01-01&tipo_solicitud=factura_edicion
    ```
    """
    try:
        estadisticas = obtener_estadisticas_solicitudes(
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            tipo_solicitud=tipo_solicitud
        )

        return {
            "status": 200,
            "message": "Estadísticas obtenidas exitosamente",
            "data": estadisticas
        }
    except Exception as e:
        raise


# -------------------- Endpoint de Detalle de Solicitudes --------------------
@router.get("/solicitudes/listado")
def api_listado_solicitudes(
        fecha_inicio: Optional[date] = Query(
            None,
            description="Fecha inicial del rango (YYYY-MM-DD)"
        ),
        fecha_fin: Optional[date] = Query(
            None,
            description="Fecha final del rango (YYYY-MM-DD)"
        ),
        tipo_solicitud: Optional[str] = Query(
            None,
            description="Tipo: mision_edicion, factura_edicion, factura_eliminacion"
        ),
        estado: Optional[str] = Query(
            None,
            description="Estado: pending, approved, rejected"
        ),
        origen: Optional[str] = Query(
            None,
            description="Origen: manual, automatico, directo"
        ),
        flujo: Optional[str] = Query(
            None,
            description="Flujo: completo, simplificado"
        ),
        aplicada: Optional[bool] = Query(
            None,
            description="Filtrar por solicitudes aplicadas (true) o no aplicadas (false)"
        ),
        page: int = Query(1, ge=1, description="Número de página"),
        limit: int = Query(20, ge=1, le=100, description="Resultados por página"),
        current_user: dict = Depends(require_bearer_token),
        _: bool = Depends(require_role_access("/mision/solicitudes/listado"))
):
    """
    Obtiene el listado detallado de solicitudes con filtros avanzados.

    **Retorna:**
    - solicitudes: Lista de solicitudes
    - paginacion: Información de paginación
    - filtros_aplicados: Filtros que se aplicaron

    **Filtros opcionales:**
    - fecha_inicio: Fecha inicial del rango
    - fecha_fin: Fecha final del rango
    - tipo_solicitud: Tipo específico de solicitud
    - estado: Estado de la solicitud (approved, rejected, pending)
    - origen: Origen de la solicitud (manual, automatico, directo)
    - flujo: Flujo de la solicitud (completo, simplificado)
    - aplicada: Si la solicitud fue aplicada (true/false)
    - page: Número de página (por defecto 1)
    - limit: Cantidad de resultados por página (por defecto 20, máximo 100)

    **Ejemplo de uso:**
    ```
    GET /mision/solicitudes/listado
    GET /mision/solicitudes/listado?estado=pending
    GET /mision/solicitudes/listado?tipo_solicitud=mision_edicion&estado=approved
    GET /mision/solicitudes/listado?origen=directo&flujo=simplificado
    GET /mision/solicitudes/listado?aplicada=false&page=2&limit=50
    ```
    """
    try:
        resultado = obtener_detalle_solicitudes(
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            tipo_solicitud=tipo_solicitud,
            estado=estado,
            origen=origen,
            flujo=flujo,
            aplicada=aplicada,
            page=page,
            limit=limit
        )

        return {
            "status": 200,
            "message": "Listado obtenido exitosamente",
            "data": resultado
        }
    except Exception as e:
        raise