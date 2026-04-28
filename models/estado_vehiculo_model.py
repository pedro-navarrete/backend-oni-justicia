# models/estado_vehiculo_model.py
"""
Modelos Pydantic para EstadoVehiculo.
Schemas de request (crear/actualizar) y response.
Incluye campo adicional: PermiteAsignacion.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List


# ──────────────────────────────────────────────
# Request: Crear
# ──────────────────────────────────────────────

class EstadoVehiculoCreate(BaseModel):
    """Schema para crear un nuevo estado de vehículo"""
    codigo: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Código único del estado de vehículo"
    )
    nombre: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Nombre del estado de vehículo"
    )
    descripcion: Optional[str] = Field(
        None,
        max_length=250,
        description="Descripción del estado de vehículo"
    )
    permiteAsignacion: bool = Field(
        ...,
        description="Indica si un vehículo en este estado puede ser asignado a misiones"
    )

    @field_validator("codigo")
    @classmethod
    def codigo_sin_espacios(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("El código no puede estar vacío")
        if " " in v:
            raise ValueError("El código no debe contener espacios, use guion bajo (_) como separador")
        return v

    @field_validator("nombre")
    @classmethod
    def nombre_no_vacio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede estar vacío")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "codigo": "DISPONIBLE",
                "nombre": "Disponible",
                "descripcion": "El vehículo está disponible para asignación",
                "permiteAsignacion": True
            }
        }


# ──────────────────────────────────────────────
# Request: Actualizar
# ──────────────────────────────────────────────

class EstadoVehiculoUpdate(BaseModel):
    """Schema para actualizar un estado de vehículo existente"""
    codigo: Optional[str] = Field(None, min_length=1, max_length=50)
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=250)
    permiteAsignacion: Optional[bool] = None

    @field_validator("codigo")
    @classmethod
    def codigo_sin_espacios(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip().upper()
            if not v:
                raise ValueError("El código no puede estar vacío")
            if " " in v:
                raise ValueError("El código no debe contener espacios, use guion bajo (_) como separador")
        return v

    @field_validator("nombre")
    @classmethod
    def nombre_no_vacio(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("El nombre no puede estar vacío")
        return v


# ──────────────────────────────────────────────
# Response
# ──────────────────────────────────────────────

class EstadoVehiculoResponse(BaseModel):
    """Schema de respuesta de un estado de vehículo"""
    id: int
    codigo: str
    nombre: str
    descripcion: Optional[str] = None
    permiteAsignacion: bool
    eliminado: bool
    fechaHoraCreacion: Optional[str] = None
    fechaHoraActualizacion: Optional[str] = None


# ──────────────────────────────────────────────
# Response: Lista paginada
# ──────────────────────────────────────────────

class EstadoVehiculoListResponse(BaseModel):
    """Schema para listado paginado de estados de vehículo"""
    total: int
    pagina: int
    porPagina: int
    registros: List[EstadoVehiculoResponse]