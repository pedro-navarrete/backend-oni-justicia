# utils/response_handler.py
"""
Estandarización de respuestas de la API.
Todos los mensajes en español.
"""

from typing import Any, Optional
from fastapi.responses import JSONResponse


def success_response(
    data: Any = None,
    message: str = "Operación exitosa",
    status_code: int = 200
) -> JSONResponse:
    """Respuesta exitosa estandarizada"""
    content = {
        "exito": True,
        "mensaje": message,
        "datos": data
    }
    return JSONResponse(status_code=status_code, content=content)


def created_response(
    data: Any = None,
    message: str = "Registro creado exitosamente"
) -> JSONResponse:
    """Respuesta 201 estandarizada"""
    return success_response(data=data, message=message, status_code=201)


def error_response(
    message: str = "Error en la operación",
    detail: Optional[str] = None,
    status_code: int = 400
) -> JSONResponse:
    """Respuesta de error estandarizada"""
    content = {
        "exito": False,
        "mensaje": message,
        "detalle": detail
    }
    return JSONResponse(status_code=status_code, content=content)


def not_found_response(
    message: str = "Recurso no encontrado"
) -> JSONResponse:
    """Respuesta 404 estandarizada"""
    return error_response(message=message, status_code=404)


def conflict_response(
    message: str = "El registro ya existe"
) -> JSONResponse:
    """Respuesta 409 para duplicados"""
    return error_response(message=message, status_code=409)


def validation_error_response(
    message: str = "Error de validación",
    detail: Optional[str] = None
) -> JSONResponse:
    """Respuesta 422 para errores de validación"""
    return error_response(message=message, detail=detail, status_code=422)


def internal_error_response(
    message: str = "Error interno del servidor",
    detail: Optional[str] = None
) -> JSONResponse:
    """Respuesta 500 para errores internos"""
    return error_response(message=message, detail=detail, status_code=500)