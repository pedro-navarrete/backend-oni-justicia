# routers/mision_router.py - Agregar estos endpoints
import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from routers.user_router import require_bearer_token
from typing import Optional
from utils.role_dependencies import require_role_access
from services.solicitud_edicion_service import (
    solicitar_edicion_mision,
    aprobar_rechazar_solicitud,
    editar_mision_aprobada,
    obtener_solicitudes,
    obtener_solicitudes_resumen,
    obtener_bitacora_mision, obtener_solicitud_por_id
)
from models.edicion_models import (
    SolicitarEdicionMision,
    AprobarRechazarSolicitud,
    EditarMisionAprobada
)
from datetime import date



logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mision", tags=["ONI Misión"])


# ==================== SOLICITUDES DE EDICIÓN ====================

@router.post("/solicitar-edicion",
             summary="Solicitar edición de misión",
             description="Crea una solicitud para editar una misión existente"
             )
def api_solicitar_edicion(
        payload: SolicitarEdicionMision,
        current_user: dict = Depends(require_bearer_token),
        _: bool = Depends(require_role_access("/mision/solicitar-edicion"))
):
    """
    Endpoint para solicitar la edición de una misión.
    La solicitud debe ser aprobada antes de poder editar.
    """
    try:
        user = current_user
        id_solicitud = solicitar_edicion_mision(payload, user)
        return {
            "status": 200,
            "message": "Solicitud de edición creada exitosamente",
            "id_solicitud": id_solicitud
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error creando solicitud de edición: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creando solicitud: {str(e)}"
        )


@router.put("/revisar-solicitud",
            summary="Aprobar o rechazar solicitud",
            description="Aprueba o rechaza una solicitud de edición de misión"
            )
def api_revisar_solicitud(
        payload: AprobarRechazarSolicitud,
        current_user: dict = Depends(require_bearer_token),
        _: bool = Depends(require_role_access("/mision/revisar-solicitud"))
):
    """
    Endpoint para aprobar o rechazar una solicitud de edición.
    Solo usuarios autorizados pueden revisar solicitudes.
    """
    try:
        logger.info(f"Solicitando revisioon de solicutud de aprobacion: {payload}")
        resultado = aprobar_rechazar_solicitud(payload)

        accion_texto = "aprobada" if payload.accion == "aprobar" else "rechazada"

        return {
            "status": 200,
            "message": f"Solicitud {accion_texto} exitosamente",
            "data": resultado
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error revisando solicitud: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error revisando solicitud: {str(e)}"
        )


@router.put("/editar-con-solicitud",
            summary="Editar misión con solicitud aprobada",
            description="Edita una misión que tiene una solicitud aprobada"
            )
def api_editar_con_solicitud(
        payload: EditarMisionAprobada,
        current_user: dict = Depends(require_bearer_token),
        _: bool = Depends(require_role_access("/mision/editar-con-solicitud"))
):
    """
    Endpoint para editar una misión usando una solicitud aprobada.
    Los cambios quedan registrados en la bitácora.
    """
    try:
        resultado = editar_mision_aprobada(payload)

        return {
            "status": 200,
            "message": "Misión editada exitosamente",
            "data": resultado
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error editando misión: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error editando misión: {str(e)}"
        )


@router.get("/solicitudes-resumen",
            summary="Resumen de solicitudes",
            description="Obtiene un resumen de solicitudes con información clave"
            )
def api_resumen_solicitudes(
        status: Optional[str] = Query(None, description="Estado: pending, approved, rejected, applied, deleted"),
        no_mision: Optional[str] = Query(None, description="Número de misión exacto"),
        dui: Optional[str] = Query(None, description="DUI (búsqueda tipo like)"),
        conductor: Optional[str] = Query(None, description="Conductor (búsqueda tipo like en requested_by.name)"),
        placa: Optional[str] = Query(None, description="Placa (búsqueda tipo like)"),
        tipo_solicitud: Optional[str] = Query(None, description="Tipo de solicitud (filtra por type o solicitud_type)"),
        fecha_inicio: Optional[date] = Query(None, description="Fecha inicio (YYYY-MM-DD)"),
        fecha_fin: Optional[date] = Query(None, description="Fecha fin (YYYY-MM-DD)"),
        filtro_avanzado: Optional[str] = Query(None, description="Búsqueda avanzada like sobre nombre, DUI y placa"),
        page: int = Query(1, ge=1, description="Página"),
        limit: int = Query(20, ge=1, le=100, description="Límite por página"),
        current_user: dict = Depends(require_bearer_token),
        _: bool = Depends(require_role_access("/mision/solicitudes-resumen"))
):
    """
    Endpoint para listar un resumen de solicitudes de edición.
    Devuelve: IdSolicitud, número de misión, DUI, estado, conductor, placa, fecha y tipo.
    """
    try:
        resultado = obtener_solicitudes_resumen(
            status=status,
            no_mision=no_mision,
            dui=dui,
            conductor=conductor,
            placa=placa,
            tipo_solicitud=tipo_solicitud,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            filtro_avanzado=filtro_avanzado,
            page=page,
            limit=limit
        )

        return {
            "status": 200,
            "data": resultado
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error obteniendo resumen de solicitudes: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo solicitudes: {str(e)}"
        )


@router.get("/solicitudes",
            summary="Listar solicitudes de edición",
            description="Obtiene solicitudes de edición con filtros"
            )
def api_listar_solicitudes(
        status: Optional[str] = Query(None, description="Estado: pending, approved, rejected"),
        dui_solicitante: Optional[str] = Query(None, description="DUI del solicitante"),
        no_mision: Optional[str] = Query(None, description="Número de misión"),
        id_solicitante: Optional[str] = Query(None, description="ID del solicitante"),
        page: int = Query(1, ge=1, description="Página"),
        limit: int = Query(20, ge=1, le=100, description="Límite por página"),
        current_user: dict = Depends(require_bearer_token),
        _: bool = Depends(require_role_access("/mision/solicitudes"))
):
    """
    Endpoint para listar solicitudes de edición con filtros.
    """
    try:
        resultado = obtener_solicitudes(
            status=status,
            dui_solicitante=dui_solicitante,
            id_solicitud=id_solicitante,
            no_mision=no_mision,
            page=page,
            limit=limit
        )

        return {
            "status": 200,
            "data": resultado
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error obteniendo solicitudes: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo solicitudes: {str(e)}"
        )

@router.get("/solicitud/{id_solicitud}")
def get_solicitud_por_id(
    id_solicitud: str,
        current_user: dict = Depends(require_bearer_token),
        _: bool = Depends(require_role_access("/mision/getSolicitud"))
):
    """
    Obtiene una solicitud de edición por su IdSolicitud
    """

    # (Opcional) aquí luego puedes validar roles o permisos
    # ejemplo:
    # if "ADMIN" not in current_user["roles"]:
    #     raise HTTPException(status_code=403, detail="Acceso denegado")

    return obtener_solicitud_por_id(id_solicitud)


@router.get("/bitacora-cambios",
            summary="Bitácora de cambios de misión",
            description="Obtiene el historial de cambios de una misión"
            )
def api_bitacora_cambios(
        id_mision: Optional[str] = Query(None, description="ID de misión"),
        no_mision: Optional[str] = Query(None, description="Número de misión"),
        page: int = Query(1, ge=1, description="Página"),
        limit: int = Query(20, ge=1, le=100, description="Límite por página"),
        current_user: dict = Depends(require_bearer_token),
        _: bool = Depends(require_role_access("/mision/bitacora-cambios"))
):
    """
    Endpoint para consultar la bitácora de cambios de una misión.
    """
    try:
        resultado = obtener_bitacora_mision(
            id_mision=id_mision,
            no_mision=no_mision,
            page=page,
            limit=limit
        )

        return {
            "status": 200,
            "data": resultado
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error obteniendo bitácora: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo bitácora: {str(e)}"
        )