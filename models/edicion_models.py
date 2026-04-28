# models/edicion_models.py - Agregar estos modelos

from pydantic import BaseModel, Field
from datetime import date
from typing import Optional, Dict, Any, Literal, List
from datetime import datetime
from enum import Enum

class SolicitarEdicionMision(BaseModel):
    """Modelo para solicitar edición de una misión (formato estandarizado)"""
    no_mision: Optional[str] = Field(None, description="Número de misión")
    id_mision: Optional[str] = Field(None, description="ID de misión")
    dui_solicitante: str = Field(..., description="DUI del usuario que solicita la edición")
    kilometraje_inicial: int = Field(..., description="Kilometraje inicial del vehiculo")
    descripcion: Optional[str] = Field(None,min_length=10,description="Descripción del cambio solicitado")
    razon: Optional[str] = Field("correccion", description="Razón del cambio")
    origen: Optional[str] = Field("manual", description="Origen de la solicitud")
    flujo: Optional[str] = Field("completo", description="Flujo de aprobación")

    class Config:
        json_schema_extra = {
            "example": {
                "id_mision": "9700073k6-3a61-4441-a2fd-235576204093",
                "no_mision": "12345678-9.P001.1",
                "dui_solicitante": "12345678-9",
                "kilometraje_inicial": 1500,
                "descripcion": "Solicito corrección de kilometraje inicial de 1000 a 1500 km",
                "razon": "correccion",
                "origen": "manual",
                "flujo": "completo"
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





# ==================== ENUMS ====================

class TipoSolicitud(str, Enum):
    MISION_EDICION = "mision_edicion"
    FACTURA_EDICION = "factura_edicion"
    FACTURA_ELIMINACION = "factura_eliminacion"


class EstadoSolicitud(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    CANCELLED = "cancelled"


class OrigenSolicitud(str, Enum):
    MANUAL = "manual"
    AUTOMATICO = "automatico"
    DIRECTO = "directo"


class FlujoSolicitud(str, Enum):
    COMPLETO = "completo"  # Requiere aprobación
    SIMPLIFICADO = "simplificado"  # Edición directa


class RazonSolicitud(str, Enum):
    CORRECCION = "correccion"
    ERROR_SISTEMA = "error_sistema"
    DUPLICADO = "duplicado"
    ACTUALIZACION = "actualizacion"
    OTRO = "otro"


# ==================== MODELOS BASE ====================

class UsuarioInfo(BaseModel):
    """Información estándar de usuario"""
    dui: str
    name: str
    rol: Optional[str] = None


class MetadataSolicitud(BaseModel):
    """Metadata de la solicitud"""
    origen: OrigenSolicitud = OrigenSolicitud.MANUAL
    flujo: FlujoSolicitud = FlujoSolicitud.COMPLETO
    prioridad: Optional[Literal["normal", "alta", "urgente"]] = "normal"
    razon: Optional[RazonSolicitud] = RazonSolicitud.CORRECCION


class AuditoriaSolicitud(BaseModel):
    """Información de auditoría"""
    intentos_aprobacion: int = 0
    modificado_por: list = []
    ip_origen: Optional[str] = None
    dispositivo: Optional[Literal["web", "android", "api"]] = None


# ==================== MODELO BASE DE SOLICITUD ====================

class SolicitudBase(BaseModel):
    """Modelo base para todas las solicitudes"""
    # Identificación
    type: TipoSolicitud

    # Contexto de la misión
    no_mision: Optional[str] = Field(None, alias="NoMision")
    id_mision: Optional[str] = Field(None, alias="IdMision")
    placa: Optional[str] = None
    dui: Optional[str] = None

    # Contexto específico
    id_factura: Optional[str] = Field(None, description="Solo para solicitudes de facturas")

    # Metadata
    metadata: Optional[MetadataSolicitud] = Field(default_factory=MetadataSolicitud)

    # Datos del cambio
    datos_anteriores: Dict[str, Any] = Field(default_factory=dict)
    datos_solicitados: Dict[str, Any] = Field(default_factory=dict)

    # Descripción
    descripcion: Optional[str] = None
    observaciones_adicionales: Optional[str] = None

    # Flujo de aprobación
    status: EstadoSolicitud = EstadoSolicitud.PENDING
    applied: bool = False

    # Usuarios involucrados
    requested_by: UsuarioInfo
    reviewed_by: Optional[UsuarioInfo] = None
    applied_by: Optional[UsuarioInfo] = None

    # Observaciones
    review_observations: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None

    # Auditoría
    auditoria: Optional[AuditoriaSolicitud] = Field(default_factory=AuditoriaSolicitud)

    class Config:
        use_enum_values = True
        populate_by_name = True


# ==================== MODELOS ESPECÍFICOS PARA CREAR SOLICITUDES ====================

class SolicitarEdicionMisionV2(BaseModel):
    """Modelo para solicitar edición de una misión (versión estandarizada)"""
    # Identificación de la misión
    no_mision: Optional[str] = None
    id_mision: Optional[str] = None

    # Solicitante
    dui_solicitante: str

    # Cambios a realizar
    kilometraje_inicial: Optional[int] = None
    nombre_motorista: Optional[str] = None
    marcador_tanque_inicial: Optional[float] = None
    # Agregar más campos según necesites

    # Contexto
    descripcion: str = Field(..., min_length=10, description="Descripción del cambio")
    razon: RazonSolicitud = RazonSolicitud.CORRECCION

    # Metadata (opcional, se llena automáticamente si no se provee)
    origen: OrigenSolicitud = OrigenSolicitud.MANUAL
    flujo: FlujoSolicitud = FlujoSolicitud.COMPLETO

    class Config:
        json_schema_extra = {
            "example": {
                "no_mision": "12345678-9.P001.1",
                "dui_solicitante": "12345678-9",
                "kilometraje_inicial": 1500,
                "descripcion": "Corrección de kilometraje inicial según boleta de salida",
                "razon": "correccion",
                "origen": "manual"
            }
        }


class SolicitarEdicionFacturaV2(BaseModel):
    """Modelo para solicitar edición de una factura (versión estandarizada)"""
    # Identificación
    id_mision: str
    id_factura: str
    dui_solicitante: str

    # Cambios
    numero_factura: Optional[str] = None
    cantidad_galones: Optional[float] = None
    cantidad_dolares: Optional[float] = None
    cupones: Optional[list] = None

    # Contexto
    descripcion: str = Field(..., min_length=10)
    razon: RazonSolicitud = RazonSolicitud.CORRECCION

    # Metadata
    origen: OrigenSolicitud = OrigenSolicitud.MANUAL
    flujo: FlujoSolicitud = FlujoSolicitud.COMPLETO

    class Config:
        json_schema_extra = {
            "example": {
                "id_mision": "768c604b-cf14-468f-b3a5-fe3d16bd676e",
                "id_factura": "453216fd-3a83-4c30-b18b-ec4687f424aa",
                "dui_solicitante": "12345678-9",
                "numero_factura": "pm_02525555",
                "cantidad_galones": 39.0,
                "cantidad_dolares": 50.0,
                "descripcion": "Corrección de cantidad de galones por error de digitación",
                "razon": "correccion"
            }
        }


class SolicitarEliminacionFacturaV2(BaseModel):
    """Modelo para solicitar eliminación de una factura (versión estandarizada)"""
    # Identificación
    id_mision: str
    id_factura: str
    dui_solicitante: str

    # Contexto
    descripcion: str = Field(..., min_length=10, alias="motivo")
    razon: RazonSolicitud = RazonSolicitud.DUPLICADO

    # Metadata
    origen: OrigenSolicitud = OrigenSolicitud.MANUAL
    flujo: FlujoSolicitud = FlujoSolicitud.COMPLETO

    class Config:
        json_schema_extra = {
            "example": {
                "id_mision": "768c604b-cf14-468f-b3a5-fe3d16bd676e",
                "id_factura": "453216fd-3a83-4c30-b18b-ec4687f424aa",
                "dui_solicitante": "12345678-9",
                "motivo": "Factura duplicada registrada por error",
                "razon": "duplicado"
            }
        }