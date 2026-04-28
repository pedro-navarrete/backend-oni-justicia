# routers/vehiculo_router.py
from fastapi import APIRouter, HTTPException, Depends
from enum import Enum
from typing import Optional
from pydantic import BaseModel
from models.models import Vehiculo, ActualizarVehiculoRequest, GetVehiculoInfo
from services.vehiculo_service import crear_vehiculo, obtener_datos_vehiculo, actualizar_vehiculo, eliminar_vehiculo, \
    listar_vehiculos, EstadoVehiculo
from routers.user_router import require_bearer_token
from utils.role_dependencies import require_role_access

router = APIRouter(prefix="/vehiculos", tags=["Vehiculos"])


class VehiculoAccion(str, Enum):
    crear = "crear"
    actualizar = "actualizar"
    eliminar = "eliminar"
    obtener = "obtener"
    listar = "listar"


class VehiculoRequest(BaseModel):
    accion: VehiculoAccion
    placa: Optional[str] = None
    data: Optional[dict] = None  # <-- Cambiado a dict


@router.post("/manage")
def vehiculo_crud(request: VehiculoRequest,
                  current_user: dict = Depends(require_bearer_token),
                  _: bool = Depends(require_role_access("/vehiculos/manage"))
                  ):

    if request.accion == VehiculoAccion.crear:
        if not request.data:
            raise HTTPException(400, "Datos del vehículo requeridos")
        resultado = crear_vehiculo(Vehiculo(**request.data))
        if resultado["status"] != 200:
            raise HTTPException(resultado["status"], resultado["msg"])
        return resultado

    elif request.accion == VehiculoAccion.actualizar:
        if not request.placa or not request.data:
            raise HTTPException(400, "Placa y datos requeridos")

        # Convertimos dict a ActualizarVehiculoRequest
        data_update = ActualizarVehiculoRequest(placa=request.placa, **request.data)
        resultado = actualizar_vehiculo(data_update)
        if not resultado:
            raise HTTPException(404, "No se pudo actualizar el vehículo")
        return {"status": 200, "msg": "Vehículo actualizado correctamente"}

    elif request.accion == VehiculoAccion.eliminar:
        if not request.placa:
            raise HTTPException(400, "Placa requerida")
        deleted = eliminar_vehiculo(request.placa)
        if not deleted:
            raise HTTPException(404, "Vehículo no encontrado")
        return {"status": 200, "msg": "Vehículo eliminado correctamente"}

    elif request.accion == VehiculoAccion.obtener:
        if not request.placa:
            raise HTTPException(400, "Placa requerida")
        vehiculo = obtener_datos_vehiculo(request.placa)
        if not vehiculo:
            raise HTTPException(404, "Vehículo no encontrado")
        return vehiculo

    elif request.accion == VehiculoAccion.listar:
        return listar_vehiculos()


@router.post("/status")
def api_verificar_estado(payload: GetVehiculoInfo, current_user: dict = Depends(require_bearer_token),
                         _: bool = Depends(require_role_access("/vehiculos/status"))
                        ):
    try:
        estado = EstadoVehiculo(payload.placa)
        return {"placa": payload.placa, "estado": estado}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error verificando estado: {str(e)}")
