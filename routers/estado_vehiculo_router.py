"""
Endpoints para EstadoVehiculo.
CRUD completo con respuestas estandarizadas.
"""

from fastapi import APIRouter, Query
from typing import Optional
from models.estado_vehiculo_model import (
    EstadoVehiculoCreate,
    EstadoVehiculoUpdate,
)
from services.estado_vehiculo_service import EstadoVehiculoService
from utils.response_handler import (
    success_response,
    created_response,
    error_response,
    not_found_response,
    conflict_response,
    internal_error_response,
)

router = APIRouter(
    prefix="/estado-vehiculo",
    tags=["Estado de Vehículo"],
    responses={
        404: {"description": "No encontrado"},
        409: {"description": "Conflicto - Registro duplicado"},
        500: {"description": "Error interno del servidor"},
    }
)

service = EstadoVehiculoService()

# ──────────────────────────────────────────────
# POST - Crear
# ──────────────────────────────────────────────

@router.post(
    "/",
    summary="Crear estado de vehículo",
    description="Crea un nuevo estado de vehículo. El código debe ser único."
)
def crear_estado_vehiculo(body: EstadoVehiculoCreate):

    resultado = service.crear(body.model_dump())

    if "error" in resultado:
        status = resultado.get("status", 400)

        if status == 409:
            return conflict_response(resultado["error"])
        if status == 500:
            return internal_error_response(detail=resultado["error"])

        return error_response(resultado["error"], status_code=status)

    return created_response(
        data=resultado["data"],
        message="Estado de vehículo creado exitosamente"
    )


# ──────────────────────────────────────────────
# GET - Obtener por ID
# ──────────────────────────────────────────────

@router.get(
    "/{id_estado_vehiculo}",
    summary="Obtener estado de vehículo por ID"
)
def obtener_estado_vehiculo(id_estado_vehiculo: int):

    resultado = service.obtener_por_id(id_estado_vehiculo)

    if "error" in resultado:
        status = resultado.get("status", 400)

        if status == 404:
            return not_found_response(resultado["error"])

        return internal_error_response(detail=resultado["error"])

    return success_response(
        data=resultado["data"],
        message="Estado de vehículo obtenido exitosamente"
    )


# ──────────────────────────────────────────────
# GET - Listar paginado
# ──────────────────────────────────────────────

@router.get(
    "/",
    summary="Listar estados de vehículo (paginado)"
)
def listar_estados_vehiculo(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(10, ge=1, le=100),
    busqueda: Optional[str] = Query(None, description="Búsqueda en código o nombre")
):

    resultado = service.listar(
        pagina=pagina,
        por_pagina=por_pagina,
        busqueda=busqueda
    )

    if "error" in resultado:
        return internal_error_response(detail=resultado["error"])

    return success_response(
        data=resultado["data"],
        message="Listado de estados de vehículo obtenido exitosamente"
    )



# ──────────────────────────────────────────────
# GET - Listar todos
# ──────────────────────────────────────────────
@router.get(
    "/todos/lista",
    summary="Listar todos los estados de vehículo (sin paginación)",
    description="Lista todos los estados de vehículo activos. Ideal para dropdowns o selects."
)
def listar_todos_estados_vehiculo(
    codigo: Optional[str] = Query(None, description="Filtrar por código"),
    nombre: Optional[str] = Query(None, description="Filtrar por nombre"),
    busqueda: Optional[str] = Query(None, description="Búsqueda general")
):
    """Lista todos los estados de vehículo activos sin paginación."""
    resultado = service.listar_todos(
        codigo=codigo,
        nombre=nombre,
        busqueda=busqueda
    )

    if "error" in resultado:
        return internal_error_response(detail=resultado["error"])

    return success_response(
        data=resultado["data"],
        message="Listado completo de estados de vehículo obtenido exitosamente"
    )


# ──────────────────────────────────────────────
# PUT - Actualizar
# ──────────────────────────────────────────────

@router.put(
    "/{id_estado_vehiculo}",
    summary="Actualizar estado de vehículo"
)
def actualizar_estado_vehiculo(
    id_estado_vehiculo: int,
    body: EstadoVehiculoUpdate
):

    resultado = service.actualizar(
        id_estado_vehiculo,
        body.model_dump(exclude_none=True)
    )

    if "error" in resultado:
        status = resultado.get("status", 400)

        if status == 404:
            return not_found_response(resultado["error"])
        if status == 409:
            return conflict_response(resultado["error"])
        if status == 500:
            return internal_error_response(detail=resultado["error"])

        return error_response(resultado["error"], status_code=status)

    return success_response(
        data=resultado["data"],
        message="Estado de vehículo actualizado exitosamente"
    )


# ──────────────────────────────────────────────
# DELETE - Soft Delete
# ──────────────────────────────────────────────

@router.delete(
    "/{id_estado_vehiculo}",
    summary="Eliminar estado de vehículo (soft delete)"
)
def eliminar_estado_vehiculo(id_estado_vehiculo: int):

    resultado = service.eliminar(id_estado_vehiculo)

    if "error" in resultado:
        status = resultado.get("status", 400)

        if status == 404:
            return not_found_response(resultado["error"])
        if status == 409:
            return conflict_response(resultado["error"])
        if status == 500:
            return internal_error_response(detail=resultado["error"])

        return error_response(resultado["error"], status_code=status)

    return success_response(
        data=resultado["data"],
        message="Estado de vehículo eliminado exitosamente"
    )