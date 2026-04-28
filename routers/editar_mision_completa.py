# routers/mision_router.py - AGREGAR ESTOS ENDPOINTS

from fastapi import APIRouter, HTTPException, Depends, Query
from services.editar_mision_service import editar_mision_completa, obtener_detalle_mision_completo
from models.editar_mision_completa import EditarMisionCompleta
from routers.user_router import require_bearer_token
from utils.role_dependencies import require_role_access
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mision", tags=["ONI Misión"])


@router.put("/editar-completa", summary="Editar misión completa")
def api_editar_mision_completa(
        payload: EditarMisionCompleta,
        current_user: dict = Depends(require_bearer_token),
        _: bool = Depends(require_role_access("/mision/editar-completa"))
):
    """
    Edita una misión completa, incluyendo datos básicos y facturas con cupones.

    **Operaciones permitidas:**

    1. **Editar datos básicos de la misión:**
       - FechaHoraSalida
       - KilometrajeInicial / kilometraje_final
       - MarcadorTanqueInicial / marcador_tanque_final
       - Solicitante
       - lugares_a_visitar / lugares_visitados

    2. **Editar facturas existentes:**
       - Número de factura
       - Cantidad de galones
       - Cantidad de dólares
       - Cupones (se reemplazan completamente)

    **Operaciones NO permitidas:**
    - Agregar nuevas facturas (usar `/factura/agregar`)
    - Eliminar facturas (usar `/factura/eliminar`)

    **Nota importante sobre cupones:**
    Los cupones se REEMPLAZAN completamente. Si quieres mantener cupones existentes,
    debes incluirlos todos en la lista.

    ---

    **Ejemplo 1: Solo editar datos básicos**
    ```json
    {
      "nomision": "00872688-8.N-21286.20",
      "KilometrajeInicial": 200,
      "Solicitante": "Departamento Legal",
      "lugares_visitados": "San Salvador, Santa Ana"
    }
    ```

    **Ejemplo 2: Solo editar cupones de una factura**
    ```json
    {
      "nomision": "00872688-8.N-21286.20",
      "facturas": [
        {
          "id_factura": "6fd37188-a884-4eb5-a4ec-e539a5682de1",
          "cupones": [
            {"numero_cupon": "123456"},
            {"numero_cupon": "789012"}
          ]
        }
      ]
    }
    ```

    **Ejemplo 3: Editar todo junto**
    ```json
    {
      "nomision": "00872688-8.N-21286.20",
      "KilometrajeInicial": 200,
      "kilometraje_final": 350,
      "lugares_visitados": "San Salvador, Santa Ana, Sonsonate",
      "facturas": [
        {
          "id_factura": "6fd37188-a884-4eb5-a4ec-e539a5682de1",
          "numero_factura": "FAC-2026-100-CORREGIDA",
          "cantidad_galones": 20.5,
          "cantidad_dolares": 61.50,
          "cupones": [
            {"numero_cupon": "NUEVO-001"},
            {"numero_cupon": "NUEVO-002"}
          ]
        }
      ]
    }
    ```
    """
    try:
        resultado = editar_mision_completa(payload)

        return {
            "status": 200,
            "message": "Misión editada con éxito",
            "data": resultado
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error editando misión completa: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error editando misión: {str(e)}"
        )


@router.get("/detalle-completo", summary="Obtener detalle completo de misión")
def api_obtener_detalle_completo(
        nomision: str = Query(..., description="Número de la misión"),
        current_user: dict = Depends(require_bearer_token),
        _: bool = Depends(require_role_access("/mision/detalle-completo"))
):
    """
    Obtiene el detalle completo de una misión, incluyendo todas sus facturas y cupones.

    **Útil para:**
    - Consultar estado actual antes de editar
    - Obtener IDs de facturas para edición
    - Ver cupones actuales de cada factura
    - Verificar datos completos

    **Respuesta incluye:**
    - Todos los datos de la misión
    - Array completo de facturas con cupones
    - Resumen agregado:
      - Total de facturas
      - Total de galones
      - Total de dólares
      - Total de cupones
      - Detalle de cada factura con sus cupones

    ---

    **Ejemplo de uso:**
    ```
    GET /mision/detalle-completo?nomision=00872688-8.N-21286.20
    ```

    **Respuesta:**
    ```json
    {
      "status": 200,
      "message": "Detalle obtenido exitosamente",
      "data": {
        "NoMision": "00872688-8.N-21286.20",
        "Placa": "N-21286",
        "Dui": "00872688-8",
        "KilometrajeInicial": 5,
        "Facturas": [...],
        "resumen_facturas": {
          "total_facturas": 2,
          "total_galones": 50,
          "total_dolares": 150,
          "total_cupones": 5,
          "detalle_facturas": [
            {
              "id_factura": "6fd37188-...",
              "numero_factura": "FAC-001",
              "galones": 30,
              "dolares": 90,
              "cantidad_cupones": 3,
              "cupones": ["123", "456", "789"]
            }
          ]
        }
      }
    }
    ```
    """
    try:
        detalle = obtener_detalle_mision_completo(nomision)

        return {
            "status": 200,
            "message": "Detalle obtenido exitosamente",
            "data": detalle
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error obteniendo detalle: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo detalle: {str(e)}"
        )