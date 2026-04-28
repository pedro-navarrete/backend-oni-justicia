# routers/mision_router.py - Agregar estos endpoints
import logging
from fastapi import APIRouter, HTTPException, Depends,Query
from routers.user_router import require_bearer_token
from typing import Optional
from utils.role_dependencies import require_role_access
from models.edicion_models import (
    SolicitarEdicionFactura,
    SolicitarEliminacionFactura,
    EditarFacturaAprobada,
    EliminarFacturaAprobada
)
from services.solicitud_edicion_service import (
    solicitar_edicion_factura,
    solicitar_eliminacion_factura,
    editar_factura_aprobada,
    eliminar_factura_aprobada
)



logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mision", tags=["ONI Misión"])

# ==================== SOLICITUDES PARA FACTURAS ====================

@router.post("/factura/solicitar-edicion",
             summary="Solicitar edición de factura",
             description="Crea una solicitud para editar una factura existente"
             )
def api_solicitar_edicion_factura(
        payload: SolicitarEdicionFactura,
        current_user: dict = Depends(require_bearer_token),
        _: bool = Depends(require_role_access("/mision/factura/solicitar-edicion"))
):
    """
    Endpoint para solicitar la edición de una factura.
    La solicitud debe ser aprobada antes de poder editar.

    **Campos editables:**
    - numero_factura
    - cantidad_galones
    - cantidad_dolares
    - cupones (lista completa de reemplazo)
    """
    try:
        user = current_user
        id_solicitud = solicitar_edicion_factura(payload, user)
        return {
            "status": 200,
            "message": "Solicitud de edición de factura creada exitosamente",
            "id_solicitud": id_solicitud
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error creando solicitud de edición de factura: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creando solicitud: {str(e)}"
        )


@router.post("/factura/solicitar-eliminacion",
             summary="Solicitar eliminación de factura",
             description="Crea una solicitud para eliminar una factura"
             )
def api_solicitar_eliminacion_factura(
        payload: SolicitarEliminacionFactura,
        current_user: dict = Depends(require_bearer_token),
        _: bool = Depends(require_role_access("/mision/factura/solicitar-eliminacion"))
):
    """
    Endpoint para solicitar la eliminación de una factura.
    La solicitud debe ser aprobada antes de poder eliminar.

    **Importante:** La eliminación es permanente e irreversible.
    """
    try:
        user = current_user
        id_solicitud = solicitar_eliminacion_factura(payload, user)
        return {
            "status": 200,
            "message": "Solicitud de eliminación de factura creada exitosamente",
            "id_solicitud": id_solicitud
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error creando solicitud de eliminación de factura: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creando solicitud: {str(e)}"
        )


@router.put("/factura/editar-con-solicitud",
            summary="Editar factura con solicitud aprobada",
            description="Edita una factura que tiene una solicitud aprobada"
            )
def api_editar_factura_con_solicitud(
        payload: EditarFacturaAprobada,
        current_user: dict = Depends(require_bearer_token),
        _: bool = Depends(require_role_access("/mision/factura/editar-con-solicitud"))
):
    """
    Endpoint para editar una factura usando una solicitud aprobada.
    Los cambios quedan registrados en la bitácora.

    **Requisitos:**
    - La solicitud debe estar en estado 'approved'
    - La solicitud debe ser de tipo 'factura_edicion'
    """
    try:
        resultado = editar_factura_aprobada(payload)
        return {
            "status": 200,
            "message": "Factura editada exitosamente",
            "data": resultado
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error editando factura: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error editando factura: {str(e)}"
        )


@router.delete("/factura/eliminar-con-solicitud",
               summary="Eliminar factura con solicitud aprobada",
               description="Elimina una factura que tiene una solicitud aprobada"
               )
def api_eliminar_factura_con_solicitud(
        payload: EliminarFacturaAprobada,
        current_user: dict = Depends(require_bearer_token),
        _: bool = Depends(require_role_access("/mision/factura/eliminar-con-solicitud"))
):
    """
    Endpoint para eliminar una factura usando una solicitud aprobada.
    La eliminación queda registrada en la bitácora.

    **Requisitos:**
    - La solicitud debe estar en estado 'approved'
    - La solicitud debe ser de tipo 'factura_eliminacion'

    **Importante:** La eliminación es permanente e irreversible.
    """
    try:
        resultado = eliminar_factura_aprobada(payload)
        return {
            "status": 200,
            "message": "Factura eliminada exitosamente",
            "data": resultado
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error eliminando factura: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error eliminando factura: {str(e)}"
        )