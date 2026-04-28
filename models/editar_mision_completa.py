# models/models.py - AGREGAR ESTE MODELO

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime



class CuponEdicion(BaseModel):
    """Modelo para editar cupones dentro de una factura"""
    numero_cupon: str = Field(..., description="Número del cupón")

    @field_validator("numero_cupon")
    @classmethod
    def validar_numero_cupon(cls, value):
        if not value or not value.strip():
            raise ValueError("El número de cupón no puede estar vacío")
        return value.strip()


class FacturaEdicionCompleta(BaseModel):
    """
    Modelo para editar una factura existente dentro de la misión.
    SOLO para edición, NO para agregar nuevas facturas.
    """
    id_factura: str = Field(..., description="ID de la factura a editar (OBLIGATORIO)")
    numero_factura: Optional[str] = Field(None, description="Nuevo número de factura")
    cantidad_galones: Optional[float] = Field(None, gt=0, description="Nueva cantidad de galones")
    cantidad_dolares: Optional[float] = Field(None, gt=0, description="Nuevo monto en dólares")
    cupones: Optional[List[CuponEdicion]] = Field(
        None,
        description="Nueva lista de cupones (reemplaza completamente la lista actual)"
    )

    @field_validator("cantidad_galones")
    @classmethod
    def validar_galones(cls, value):
        if value is not None and value <= 0:
            raise ValueError("La cantidad de galones debe ser mayor a 0")
        return value

    @field_validator("cantidad_dolares")
    @classmethod
    def validar_dolares(cls, value):
        if value is not None and value <= 0:
            raise ValueError("La cantidad de dólares debe ser mayor a 0")
        return value

    @field_validator("id_factura")
    @classmethod
    def validar_id_factura(cls, value):
        if not value or not value.strip():
            raise ValueError("El ID de la factura no puede estar vacío")
        return value.strip()


class EditarMisionCompleta(BaseModel):
    """
    Modelo para editar una misión completa, incluyendo:
    - Datos básicos de la misión
    - Edición de facturas existentes (incluyendo cupones)

    NO permite agregar nuevas facturas, solo editar las existentes.
    """
    # -------- Campo obligatorio --------
    nomision: str = Field(..., description="Número de misión a editar")

    # -------- Datos básicos de la misión (todos opcionales) --------
    FechaHoraSalida: Optional[datetime] = Field(None, description="Fecha y hora de salida")
    KilometrajeInicial: Optional[int] = Field(None, ge=0, description="Kilometraje inicial")
    MarcadorTanqueInicial: Optional[float] = Field(None, ge=0, le=1, description="Marcador de tanque inicial (0-1)")
    Solicitante: Optional[str] = Field(None, description="Solicitante")
    lugares_a_visitar: Optional[str] = Field(None, description="Lugares a visitar")

    # -------- Datos de finalización (opcionales) --------
    fecha_hora_entrada: Optional[datetime] = Field(None, description="Fecha y hora de entrada")
    kilometraje_final: Optional[int] = Field(None, ge=0, description="Kilometraje final")
    marcador_tanque_final: Optional[float] = Field(None, ge=0, le=1, description="Marcador de tanque final (0-1)")
    lugares_visitados: Optional[str] = Field(None, description="Lugares visitados")

    # -------- Facturas a editar (opcional) --------
    facturas: Optional[List[FacturaEdicionCompleta]] = Field(
        None,
        description="Lista de facturas a EDITAR (debe incluir id_factura). NO se pueden agregar nuevas."
    )

    # -------- Validaciones --------
    @field_validator("KilometrajeInicial")
    @classmethod
    def validar_kilometraje_inicial(cls, value):
        if value is not None and value < 0:
            raise ValueError("El kilometraje inicial no puede ser negativo")
        return value

    @field_validator("kilometraje_final")
    @classmethod
    def validar_kilometraje_final(cls, value):
        if value is not None and value < 0:
            raise ValueError("El kilometraje final no puede ser negativo")
        return value

    @field_validator("MarcadorTanqueInicial")
    @classmethod
    def validar_marcador_inicial(cls, value):
        if value is not None:
            if value < 0 or value > 1:
                raise ValueError("El marcador del tanque inicial debe estar entre 0 y 1")
        return value

    @field_validator("marcador_tanque_final")
    @classmethod
    def validar_marcador_final(cls, value):
        if value is not None:
            if value < 0 or value > 1:
                raise ValueError("El marcador del tanque final debe estar entre 0 y 1")
        return value

    @field_validator("nomision")
    @classmethod
    def validar_nomision(cls, value):
        if not value or not value.strip():
            raise ValueError("El número de misión no puede estar vacío")
        return value.strip()

    model_config = {
        "json_schema_extra": {
            "example": {
                "nomision": "00872688-8.N-21286.20",
                "KilometrajeInicial": 200,
                "Solicitante": "Departamento de Seguridad",
                "lugares_visitados": "San Salvador, Santa Ana, Sonsonate",
                "kilometraje_final": 350,
                "marcador_tanque_final": 0.25,
                "facturas": [
                    {
                        "id_factura": "6fd37188-a884-4eb5-a4ec-e539a5682de1",
                        "numero_factura": "FAC-2026-100-EDITADA",
                        "cantidad_galones": 20.5,
                        "cantidad_dolares": 61.50,
                        "cupones": [
                            {"numero_cupon": "CUPON-001"},
                            {"numero_cupon": "CUPON-002"},
                            {"numero_cupon": "CUPON-003"}
                        ]
                    }
                ]
            }
        },
        "arbitrary_types_allowed": True
    }