# models/models.py
from datetime import datetime, date

from fastapi import HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import List, Optional, Dict, Any
import re

# -------------------- Modelos para Movimientos -------------------- #
class UserManageRequest(BaseModel):
    action: str = Field(..., description="Acción a realizar: create/update/password/activate/deactivate")
    oni: str = Field(None, description="Numero de Oni")
    username: str = Field(None , description="Username del usuario")
    #verificar el dui tenga formato correcto
    dui: str = Field(None,
       description="DUI del usuario",
    )
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str]= None
    roles: Optional[List[str]] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("dui")
    @classmethod
    def validar_dui(cls, value):
        if not re.fullmatch(r"^\d{8}-\d$", value):
            # Lanzamos un error HTTP directo y limpio
            raise HTTPException(
                status_code=400,
                detail="El DUI debe tener el formato XXXXXXXX-X"
            )
        return value

    model_config = {
        "arbitrary_types_allowed": True
    }

# -------------------- Modelos para el catálogo de vehículos -------------------- #
class Vehiculo(BaseModel):
    placa: str
    clase: str
    marca: str
    modelo: str
    periodo: Optional[str] = None
    tipo_combustible: str
    unidad_distancia: Optional[str] = None
    capacidad_tanque: float
    dependencia: str
    ubicacion: str
    estado: str = "disponible"  # disponible, en_reparacion, ocupado, fuera_servicio
    observaciones: Optional[str] = None

    model_config = {
        "arbitrary_types_allowed": True
    }
#----------------------Modelo para editarmisiones-------------------#
class solicitudEdicion(BaseModel):
    NoMision: str
    requesby : str = Field(..., description="Dui del usuario que solicita la edicio")

class EditarMision(BaseModel):
    nomision: str
    KilometrajeInicial: Optional[int] = None
    MarcadorTanqueInicial: Optional[float] = None
    kilometraje_final: Optional[int] = None
    marcador_tanque_final: Optional[float] = None
    lugares_visitados: Optional[str] = None
    descripcion: Optional[str] = Field(
        None,
        description="Descripción de la edición directa (solo para SolicitudesEdicionMision)"
    )


    @field_validator("KilometrajeInicial")
    def validar_kilometraje_inicial(cls, value):
        if value is not None and value < 0:
            raise ValueError("El kilometraje inicial no puede ser negativo")
        return value

    @field_validator("kilometraje_final")
    def validar_kilometraje_final(cls, value):
        if value is not None and value < 0:
            raise ValueError("El kilometraje final no puede ser negativo")
        return value

    @field_validator("MarcadorTanqueInicial")
    def validar_marcador_tanque_inicial(cls, value):
        if value is not None and value < 0:
            raise ValueError("El marcador del tanque inicial no puede ser negativo")
        return value

    @field_validator("marcador_tanque_final")
    def validar_marcador_tanque_final(cls, value):
        if value is not None and value < 0:
            raise ValueError("El marcador del tanque final no puede ser negativo")
        return value

    model_config = {
        "arbitrary_types_allowed": True
    }

# -------------------- Modelo para el catálogo de Misiones -------------------- #
class CrearMision(BaseModel):
    dui: str
    placa: str
    fecha_hora_salida: datetime
    kilometraje_inicial: int
    nombre_motorista: str
    marcador_tanque_inicial: float
    solicitante: str
    lugares_visitados: str
    solicitud : int


    @field_validator("dui")
    @classmethod
    def validar_dui(cls, value):
        if not re.fullmatch(r"^\d{8}-\d$", value):
            raise HTTPException(
                status_code=400,
                detail="El DUI debe tener el formato XXXXXXXX-X"
            )
        return value

    model_config = {
        "arbitrary_types_allowed": True
    }

# -------------------- Actualizar Misión -------------------- #
class ActualizarMision(BaseModel):
    id_mision: str
    fecha_hora_entrada: Optional[datetime] = None
    kilometraje_final: Optional[int] = None
    marcador_tanque_final: Optional[float] = None
    lugares_visitados: Optional[str] = None
    solicitud: int
    # factura: Optional[str] = None
    # cantidad_galones: Optional[float] = None
    # cantidad_cupones: Optional[int] = None
    # cantidad_dolares: Optional[float] = None
    # correlativo_cupones_utilizados: Optional[str] = None

    @field_validator("kilometraje_final")
    def validar_kilometraje_final(cls, value):
        if value is not None and value < 0:
            raise ValueError("El kilometraje final no puede ser negativo")
        return value

    @field_validator("marcador_tanque_final")
    def validar_marcador_tanque_final(cls, value):
        if value is not None and value < 0:
            raise ValueError("El marcador del tanque final no puede ser negativo")
        return value

    model_config = {
        "arbitrary_types_allowed": True
    }

# -------------------- Modelo para Coordenadas -------------------- #
class Coordenada(BaseModel):
    id_mision: str
    dui: str
    placa: str
    latitud: float
    longitud: float
    fecha_hora: datetime
    estado: str  # inicio, enruta, final
    nivel_bateria: int
    velocidad: Optional[float] = None
    rumbo: Optional[float] = None
    altitud: Optional[float] = None
    precision: Optional[float] = None
    proveedor: Optional[str] = None  # gps , network o fused

    @field_validator("dui")
    @classmethod
    def validar_dui(cls, value):
        if not re.fullmatch(r"^\d{8}-\d$", value):
            # Lanzamos un error HTTP directo y limpio
            raise HTTPException(
                status_code=400,
                detail="El DUI debe tener el formato XXXXXXXX-X"
            )
        return value

    @field_validator("longitud")
    def validar_longitud(cls, value):
        if value < -180 or value > 180:
            raise ValueError("La longitud debe estar entre -180 y 180 grados")
        return value

    @field_validator("latitud")
    def validar_latitud(cls, value):
        if value < -90 or value > 90:
            raise ValueError("La latitud debe estar entre -90 y 90 grados")
        return value

    @field_validator("estado")
    def validar_estado(cls, value):
        estados_validos = {"inicio", "enruta", "final"}
        if value not in estados_validos:
            raise ValueError(f"El estado debe ser uno de: {', '.join(estados_validos)}")
        return value

    @field_validator("nivel_bateria")
    def validar_nivel_bateria(cls, value):
        if value < 0 or value > 100:
            raise ValueError("El nivel de batería debe estar entre 0 y 100")
        return value


    model_config = {
        "arbitrary_types_allowed": True
    }


class CoordenadaLote(BaseModel):
    latitud: float
    longitud: float
    fecha_hora: datetime
    estado: str  # inicio, enruta, final
    nivel_bateria: int
    velocidad: Optional[float] = None
    rumbo: Optional[float] = None
    altitud: Optional[float] = None
    precision: Optional[float] = None
    proveedor: Optional[str] = None  # gps , network o fused

    @field_validator("longitud")
    def validar_longitud(cls, value):
        if value < -180 or value > 180:
            raise ValueError("La longitud debe estar entre -180 y 180 grados")
        return value

    @field_validator("latitud")
    def validar_latitud(cls, value):
        if value < -90 or value > 90:
            raise ValueError("La latitud debe estar entre -90 y 90 grados")
        return value

    @field_validator("estado")
    def validar_estado(cls, value):
        estados_validos = {"inicio", "enruta", "final"}
        if value not in estados_validos:
            raise ValueError(f"El estado debe ser uno de: {', '.join(estados_validos)}")
        return value

    @field_validator("nivel_bateria")
    def validar_nivel_bateria(cls, value):
        if value < 0 or value > 100:
            raise ValueError("El nivel de batería debe estar entre 0 y 100")
        return value

    model_config = {
        "arbitrary_types_allowed": True
    }


class CoordenadasBatchRequest(BaseModel):
    id_mision: str
    coordenadas: List[CoordenadaLote] = Field(..., min_length=1, description="Lista de coordenadas a guardar")

    model_config = {
        "arbitrary_types_allowed": True
    }

# -------------------- Verificar DUI y PLACA request -------------------- #
class VerificarRequest(BaseModel):
    dui: str
    placa: str

    @field_validator("dui")
    @classmethod
    def validar_dui(cls, value):
        if not re.fullmatch(r"^\d{8}-\d$", value):
            # Lanzamos un error HTTP directo y limpio
            raise HTTPException(
                status_code=400,
                detail="El DUI debe tener el formato XXXXXXXX-X"
            )
        return value

    model_config = {
        "arbitrary_types_allowed": True
    }

# -------------------- GetVehiculoInfo -------------------- #
class GetVehiculoInfo(BaseModel):
    placa: str

    model_config = {
        "arbitrary_types_allowed": True
    }

# -------------------- Actualizar Vehículo -------------------- #
class ActualizarVehiculoRequest(BaseModel):
    placa: str
    clase: Optional[str] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    periodo: Optional[str] = None
    tipo_combustible: Optional[str] = None
    unidad_distancia: Optional[str] = None
    capacidad_tanque: Optional[float] = None
    dependencia: Optional[str] = None
    ubicacion: Optional[str] = None
    estado: Optional[str] = None
    disponible: Optional[bool] = None
    observaciones: Optional[str] = None

    model_config = {
        "arbitrary_types_allowed": True
    }

#-------------------------modelo para filtro de Getmision-------------------
class MisionFiltro(BaseModel):
    placa: Optional[str] = Field(None, description="Placa del vehículo")
    dui: Optional[str] = Field(None, description="DUI del usuario")
    mision: Optional[str] = Field(None, description="Número de misión")
    solicitante: Optional[str] = Field(None, description="Nombre del solicitante")
    estado: Optional[str] = Field(None, description="Estado de la última coordenada")
    fecha_inicio: Optional[date] = Field(None, description="Fecha de inicio")
    fecha_fin: Optional[date] = Field(None, description="Fecha de fin")
    page: int = Field(1, ge=1)
    limit: int = Field(20, ge=1, le=100)



# -------------------- Modelos para Facturas y Cupones -------------------- #

class Cupon(BaseModel):
    """Modelo para un cupón individual"""
    numero_cupon: str = Field(..., description="Número del cupón")

    model_config = {
        "arbitrary_types_allowed": True
    }


class AgregarFactura(BaseModel):
    """Modelo para agregar una nueva factura a una misión"""
    id_mision: str = Field(..., description="ID de la misión")
    numero_factura: str = Field(..., description="Número de factura")
    cantidad_galones: float = Field(..., gt=0, description="Cantidad de galones")
    cantidad_dolares: float = Field(..., gt=0, description="Monto total en dólares")
    cupones: List[Cupon] = Field(default_factory=list, description="Lista de cupones")

    @field_validator("cantidad_galones")
    @classmethod
    def validar_galones(cls, value):
        if value <= 0:
            raise ValueError("La cantidad de galones debe ser mayor a 0")
        return value

    @field_validator("cantidad_dolares")
    @classmethod
    def validar_dolares(cls, value):
        if value <= 0:
            raise ValueError("La cantidad de dólares debe ser mayor a 0")
        return value

    model_config = {
        "arbitrary_types_allowed": True
    }


class EditarFactura(BaseModel):
    """Modelo para editar una factura existente"""
    id_mision: str = Field(..., description="ID de la misión")
    id_factura: str = Field(..., description="ID de la factura a editar")
    numero_factura: Optional[str] = Field(None, description="Número de factura")
    cantidad_galones: Optional[float] = Field(None, gt=0, description="Cantidad de galones")
    cantidad_dolares: Optional[float] = Field(None, gt=0, description="Monto total en dólares")
    cupones: Optional[List[Cupon]] = Field(None, description="Lista de cupones (reemplaza la lista existente)")
    descripcion: Optional[str] = Field(
        None,
        description="Descripción de la edición directa (solo para SolicitudesEdicionMision)"
    )
    review_observations: Optional[str] = Field(
        None,
        description="Observaciones de revisión/aplicación (solo para SolicitudesEdicionMision)"
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

    model_config = {
        "arbitrary_types_allowed": True
    }


class EliminarFactura(BaseModel):
    """Modelo para eliminar una factura"""
    id_mision: str = Field(..., description="ID de la misión")
    id_factura: str = Field(..., description="ID de la factura a eliminar")

    model_config = {
        "arbitrary_types_allowed": True
    }


