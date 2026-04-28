# models/edicion_models.py - Agregar estos modelos

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from typing import Optional
from datetime import date

class SolicitarEdicionMision(BaseModel):
    """Modelo para solicitar edición de una misión"""
    no_mision: Optional[str] = Field(None, description="Número de misión")
    id_mision: Optional[str] = Field(None, description="ID de misión")
    dui_solicitante: str = Field(..., description="DUI del usuario que solicita la edición")
    #descripcion: str = Field(..., min_length=10, description="Descripción/observación de los cambios solicitados")
    kilometraje_inicial: int = Field(...,description="Kilometraje inicial del vehiculo")

    class Config:
        json_schema_extra = {
            "example": {
                "id_mision": "9700073k6-3a61-4441-a2fd-235576204093",
                "no_mision": "12345678-9.P001.1",
                "dui_solicitante": "12345678-9",
                #: "Solicito corrección de kilometraje inicial de 1000 a 1500 km"
                "kilometraje_inicial": 1500
            }
        }

class AprobarRechazarSolicitud(BaseModel):
    """Modelo para aprobar o rechazar una solicitud de edición"""
    id_solicitud: str = Field(..., description="ID de la solicitud")
    accion: str = Field(..., pattern="^(aprobar|rechazar)$", description="Acción: aprobar o rechazar")
    dui_revisor: str = Field(..., description="DUI del usuario que revisa")
    observaciones: Optional[str] = Field(None, description="Observaciones del revisor")

    class Config:
        json_schema_extra = {
            "example": {
                "id_solicitud": "550e8400-e29b-41d4-a716-446655440000",
                "accion": "aprobar",
                "dui_revisor": "87654321-0",
                "observaciones": "Aprobado por verificación de documentos"
            }
        }

class EditarMisionAprobada(BaseModel):
    """Modelo para editar una misión con solicitud aprobada"""
    id_solicitud: str = Field(..., description="ID de la solicitud aprobada")
    dui_editor: str = Field(..., description="DUI del usuario que realiza la edición")

    # Campos editables de la misión (todos opcionales)
    kilometraje_inicial: Optional[int] = None
    # nombre_motorista: Optional[str] = None
    # marcador_tanque_inicial: Optional[float] = None
    # solicitante: Optional[str] = None
    # fecha_hora_salida: Optional[datetime] = None
    # kilometraje_final: Optional[float] = None
    # marcador_tanque_final: Optional[float] = None
    # fecha_hora_llegada: Optional[datetime] = None
    observacion_final: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id_solicitud": "550e8400-e29b-41d4-a716-446655440000",
                "dui_editor": "12345678-9",
                # "nombre_motorista": "Juan Perez",
                "kilometraje_inicial": 1500,
                # "marcador_tanque_inicial": 1.0,
                # "solicitante": "Pedro Rodriguez",
                # "fecha_hora_salida": "2023-11-01T08:00:00",
                # "kilometraje_final": 1550.0,
                # "marcador_tanque_final": 0.75,
                # "fecha_hora_llegada": "2023-11-01T16:00:00",
                "observacion_final": "Kilometraje corregido según boleta"
            }
        }

# ==================== MODELOS PARA FACTURAS ====================

class CuponSolicitud(BaseModel):
    """Modelo para cupones en solicitudes"""
    numero_cupon: str = Field(..., description="Número del cupón")


class SolicitarEdicionFactura(BaseModel):
    """Modelo para solicitar edición de una factura"""
    id_mision: str = Field(..., description="ID de la misión")
    id_factura: str = Field(..., description="ID de la factura a editar")
    dui_solicitante: str = Field(..., description="DUI del usuario que solicita la edición")
    descripcion: Optional[str] = Field(..., min_length=10, description="Descripción de los cambios solicitados")

    # Campos a modificar (opcionales)
    numero_factura: Optional[str] = None
    cantidad_galones: Optional[float] = None
    cantidad_dolares: Optional[float] = None
    cupones: Optional[List[CuponSolicitud]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id_mision": "ea4a724a-ecc4-4711-a3ac-950ab95ae922",
                "id_factura": "d214634b-d296-48b2-b334-2d663d833866",
                "dui_solicitante": "12345678-9",
                "descripcion": "Corrección de galones, monto total y actualización de cupones asociados a la factura",
                "numero_factura": "FAC-2026-000045",
                "cantidad_galones": 16.0,
                "cantidad_dolares": 4185.91,
                "cupones": [
                    {
                        "numero_cupon": "64354556"
                    },
                    {
                        "numero_cupon": "string123"
                    }
                ]
            }
        }


class SolicitarEliminacionFactura(BaseModel):
    """Modelo para solicitar eliminación de una factura"""
    id_mision: str = Field(..., description="ID de la misión")
    id_factura: str = Field(..., description="ID de la factura a eliminar")
    dui_solicitante: str = Field(..., description="DUI del usuario que solicita la eliminación")
    descripcion: str = Field(..., min_length=10, description="Motivo de la eliminación", alias="motivo")

    class Config:
        json_schema_extra = {
            "example": {
                "id_mision": "64c0935e-949f-48eb-bb2d-da6009e8fac4",
                "id_factura": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "dui_solicitante": "12345678-9",
                "motivo": "Factura duplicada registrada por error"
            }
        }


class EditarFacturaAprobada(BaseModel):
    """Modelo para editar una factura con solicitud aprobada"""
    id_solicitud: str = Field(..., description="ID de la solicitud aprobada")
    dui_editor: str = Field(..., description="DUI del usuario que realiza la edición")

    class Config:
        json_schema_extra = {
            "example": {
                "id_solicitud": "550e8400-e29b-41d4-a716-446655440000",
                "dui_editor": "12345678-9"
            }
        }


class EliminarFacturaAprobada(BaseModel):
    """Modelo para eliminar una factura con solicitud aprobada"""
    id_solicitud: str = Field(..., description="ID de la solicitud aprobada")
    dui_editor: str = Field(..., description="DUI del usuario que realiza la eliminación")

    class Config:
        json_schema_extra = {
            "example": {
                "id_solicitud": "550e8400-e29b-41d4-a716-446655440000",
                "dui_editor": "12345678-9"
            }
        }


class EstadisticasSolicitudesFiltro(BaseModel):
    """
    Modelo para los filtros del endpoint de estadísticas de solicitudes.

    Atributos:
        fecha_inicio: Fecha inicial del rango (opcional)
        fecha_fin: Fecha final del rango (opcional)
        tipo_solicitud: Tipo de solicitud a filtrar (opcional)
            - mision_edicion: Edición de misión
            - factura_edicion: Edición de factura
            - factura_eliminacion: Eliminación de factura
    """
    fecha_inicio: Optional[date] = Field(None, description="Fecha inicial del rango (YYYY-MM-DD)")
    fecha_fin: Optional[date] = Field(None, description="Fecha final del rango (YYYY-MM-DD)")
    tipo_solicitud: Optional[str] = Field(
        None,
        description="Tipo de solicitud: mision_edicion, factura_edicion, factura_eliminacion"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "fecha_inicio": "2026-01-01",
                "fecha_fin": "2026-01-31",
                "tipo_solicitud": "mision_edicion"
            }
        }
