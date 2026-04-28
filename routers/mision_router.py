# routers/mision_router.py
import logging
from fastapi import APIRouter, HTTPException, Depends,Query
from services.mision_service import crear_mision, guardar_coordenadas_por_id_mision, actualizar_mision, get_misiones, \
    InicioFinalMision, editar_mision, get_kilometraje_misiones, \
    get_misiones_solicitadas_SQL_por_dui
from models.models import CrearMision, Coordenada, CoordenadasBatchRequest, ActualizarMision, MisionFiltro, EditarMision, solicitudEdicion
from routers.user_router import require_bearer_token
from services.verificar_service import verificar_placa, verificar_dui
from utils.role_dependencies import require_role_access
from models.models import AgregarFactura, EditarFactura, EliminarFactura
from services.mision_service import agregar_factura, editar_factura, obtener_facturas, eliminar_factura, \
    forzar_estado_final_por_no_mision

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mision", tags=["ONI Misión"])


# -------------------- Crear misión --------------------
@router.post(
    "/crear",
    summary="Crear una misión",
    description="Este endpoint permite crear una nueva misión con los datos proporcionados."
)
def api_crear_mision(
        payload: CrearMision,
        current_user: dict = Depends(require_bearer_token),        
        _: bool = Depends(require_role_access("/mision/crear"))
        ):
    try:
        # -------- Validar placa --------
        resp = verificar_placa(payload.placa)
        if resp:
            return resp

        # -------- Validar DUI --------
        resp = verificar_dui(payload.dui)
        if resp:
            return resp



        mision_id = crear_mision(payload)
        return {
            "status": 200,
            "message": "Misión creada con éxito",
            "id_mision": mision_id
        }
    except HTTPException as e:
        raise e  # dejamos pasar errores lanzados desde el service
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creando misión: {str(e)}")


# -------------------- Guardar coordenada --------------------
@router.post(
    "/coordenada",
    summary="Guardar coordenadas de una misión",
    description="Este endpoint permite guardar una o varias coordenadas asociadas a una misión."
)
def api_guardar_coordenada(
        payload: CoordenadasBatchRequest,
        current_user: dict = Depends(require_bearer_token),
        _: bool = Depends(require_role_access("/mision/coordenada"))
        ):
    try:
        resultado = guardar_coordenadas_por_id_mision(payload)
        return {
            "status": 200,
            "message": "Coordenadas guardadas con éxito",
            "data": resultado
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error guardando coordenada: {str(e)}")


#------------------------Iniciar/Finalizar Mision-------------------
@router.post(
    "/inicio-final",
    summary="Registrar inicio o final de misión",
    description="Este endpoint permite registrar la coordenada de inicio o finalización de una misión."
)
def api_inicio_final(
        payload: Coordenada,
        current_user: dict = Depends(require_bearer_token),        
        _: bool = Depends(require_role_access("/mision/inicio-final"))
        ):

    try:
        InicioFinalMision(payload)
        return {
            "status": 200,
            "message": "Coordenada guardada con éxito"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error guardando coordenada: {str(e)}")


# -------------------- Actualizar misión --------------------
@router.put(
    "/actualizar",
    summary="Finalizar la información de la Mision",
    description="Este endpoint permite Finalizar los datos de la mision"
)
def api_actualizar_mision(
        payload: ActualizarMision,
        current_user: dict = Depends(require_bearer_token),        
        _: bool = Depends(require_role_access("/mision/actualizar"))
        ):
    try:
        actualizado = actualizar_mision(payload)
        if not actualizado:
            raise HTTPException(status_code=404, detail="Misión no encontrada o no actualizada")
        return {
            "status": 200,
            "message": "Misión actualizada con éxito"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error actualizando misión: {str(e)}")

#----------------Editar Mision-------------------
@router.put(
    "/editar",
    summary="Editar la información de la misión",
    description="Este endpoint permite editar los datos de una misión existente."
)
def api_editar_mision(
        payload: EditarMision,
        current_user: dict = Depends(require_bearer_token),        
        _: bool = Depends(require_role_access("/mision/editar"))
        ):

    try:
        actualizado = editar_mision(payload, current_user=current_user)
        if not actualizado:
            raise HTTPException(status_code=404, detail="Misión no encontrada o no actualizada")
        return {
            "status": 200,
            "message": "Misión editada con éxito"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error editando misión: {str(e)}")

#-------------------------Obtener Mision-------------------
@router.get(
    "/get",
    summary="Obtener misiones filtradas",
    description="Este endpoint permite obtener misiones aplicando filtros y paginación."
)
def get_mision(filtro: MisionFiltro = Depends(),
        current_user: dict = Depends(require_bearer_token),        
        _: bool = Depends(require_role_access("/mision/get"))
    ):
    """
    Obtiene misiones filtradas por placa, DUI, NoMision y rango de fechas.
    Devuelve resultados paginados (por defecto 20 por página).
    """
    return get_misiones(filtro.placa,
                        filtro.dui, filtro.mision,
                        filtro.solicitante,
                        filtro.estado,
                        filtro.fecha_inicio,
                        filtro.fecha_fin,
                        filtro.page,
                        filtro.limit)


# python
@router.get(
    "/get-kilometraje",
    summary="Obtener kilometraje de una misión",
    description="Este endpoint permite consultar el kilometraje inicial de una misión por su identificador."
)
def api_get_kilometraje(
        IdMision: str = Query(None, alias="IdMision"),
        current_user: dict = Depends(require_bearer_token),        
        _: bool = Depends(require_role_access("/mision/get-kilometraje"))
    ):
    try:
        kilometraje = get_kilometraje_misiones(IdMision)
        return {
            "status": 200,
            "KilometrajeInicial": kilometraje
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo kilometraje: {str(e)}")


@router.get(
    "/misiones_solicitadas",
    summary="Obtener la última misión por DUI",
    description="Este endpoint permite obtener la última misión asociada a un motorista según su DUI."
)
def get_misiones_solicitadas(
        dui: str = Query(..., description="Dui del motorista (obligatoria)"),
        current_user: dict = Depends(require_bearer_token),
        _: bool = Depends(require_role_access("/mision/misiones_solicitadas"))
):
    """
    Endpoint que devuelve la última misión de un motorista según su DUI.
    Solo devuelve el vehículo y motorista correspondiente al lado donde fue encontrado el DUI.
    """
    try:
        mision = get_misiones_solicitadas_SQL_por_dui(dui)

        if not mision:
            raise HTTPException(
                status_code=404,
                detail="No se encontró ninguna misión para ese motorista"
            )

        tipo = mision.get("tipo_motorista")  # 'salida' o 'entrada'

        # Seleccionar solo el vehiculo y motorista del lado correcto
        if tipo == "salida":
            vehiculo_data = {
                "id": mision["idVehiculoSalida"],
                "placa": mision["placaSalida"],
                "marca": mision["marcaSalida"],
                "modelo": mision["modeloSalida"],
                "color": mision["colorSalida"]
            } if mision.get("idVehiculoSalida") else None

            motorista_data = {
                "id": mision["idMotoristaSalida"],
                "nombre": mision["nombreSalida"],
                "apellido": mision["apellidoSalida"],
                "dui": mision["duiSalida"],
                "telefono": mision["telefonoSalida"]
            } if mision.get("idMotoristaSalida") else None

        elif tipo == "entrada":
            vehiculo_data = {
                "id": mision["idVehiculoEntrada"],
                "placa": mision["placaEntrada"],
                "marca": mision["marcaEntrada"],
                "modelo": mision["modeloEntrada"],
                "color": mision["colorEntrada"]
            } if mision.get("idVehiculoEntrada") else None

            motorista_data = {
                "id": mision["idMotoristaEntrada"],
                "nombre": mision["nombreEntrada"],
                "apellido": mision["apellidoEntrada"],
                "dui": mision["duiEntrada"],
                "telefono": mision["telefonoEntrada"]
            } if mision.get("idMotoristaEntrada") else None

        else:
            vehiculo_data = None
            motorista_data = None

        return {
            "status": 200,
            "message": "Misión obtenida correctamente",
            "data": {
                "solicitud": mision["idSolicitud"],
                "codigo": mision["codSolicitud"],
                "fecha_solicitud": mision["fechSolicitud"],
                "fecha_aprobacion": mision["fechAprobacion"],
                "departamento": mision["nombDepto"],
                "tipo_motorista": tipo,

                "solicitante": {
                    "nombre": mision["nombSoli"],
                    "apellido": mision["apeSoli"],
                    "cargo": mision["cargoSoli"],
                    "email": mision["emailSoli"]
                } if mision.get("nombSoli") else None,

                "vehiculo": vehiculo_data,
                "motorista": motorista_data,

                "fecha": mision["fecha"],
                "hora": mision["hora"],
                "lugares": mision["lugares"],
                "estado": mision["estado"]
            }
        }

    except HTTPException:
        raise

    except Exception as e:
        print("=" * 60)
        print("ERROR EN ENDPOINT:")
        print(type(e).__name__)
        print(str(e))
        import traceback
        traceback.print_exc()
        print("=" * 60)
        raise HTTPException(
            status_code=500,
            detail=f"Error interno: {str(e)}"
        )

# -------------------- Endpoints para Facturas -------------------- #
@router.post(
    "/factura/agregar",
    summary="Agregar factura a una misión",
    description="Este endpoint permite agregar una factura con cupones a una misión existente."
)
def api_agregar_factura(
        payload: AgregarFactura,
        current_user: dict = Depends(require_bearer_token),        
        _: bool = Depends(require_role_access("/mision/factura/agregar"))
):
    """
    Agrega una nueva factura con cupones a una misión existente.

    **Parámetros:**
    - id_mision: ID único de la misión
    - numero_factura: Número de la factura
    - cantidad_galones: Cantidad de galones comprados
    - cantidad_dolares: Monto total en dólares
    - cupones: Lista de cupones utilizados (cada uno con numero_cupon)

    **Retorna:**
    - id_factura: UUID de la factura creada
    """
    try:
        id_factura = agregar_factura(payload)
        return {
            "status": 200,
            "message": "Factura agregada exitosamente",
            "id_factura": id_factura
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error agregando factura: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error agregando factura: {str(e)}")


@router.put(
    "/factura/editar",
    summary="Editar factura de una misión",
    description="Este endpoint permite editar una factura existente asociada a una misión."
)
def api_editar_factura(
        payload: EditarFactura,
        current_user: dict = Depends(require_bearer_token),        
        _: bool = Depends(require_role_access("/mision/factura/editar"))
):
    """
    Edita una factura existente en una misión.

    **Parámetros:**
    - id_mision: ID único de la misión
    - id_factura: ID único de la factura a editar
    - numero_factura: (Opcional) Nuevo número de factura
    - cantidad_galones: (Opcional) Nueva cantidad de galones
    - cantidad_dolares: (Opcional) Nuevo monto en dólares
    - cupones: (Opcional) Nueva lista de cupones (reemplaza la existente)

    **Retorna:**
    - Mensaje de éxito
    """
    try:
        editado = editar_factura(payload, current_user=current_user)
        if not editado:
            raise HTTPException(status_code=404, detail="Factura no encontrada o no actualizada")
        return {
            "status": 200,
            "message": "Factura editada exitosamente"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error editando factura: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error editando factura: {str(e)}")


@router.get(
    "/facturas",
    summary="Obtener facturas de una misión",
    description="Este endpoint permite obtener todas las facturas registradas para una misión específica."
)
def api_obtener_facturas(
        id_mision: str = Query(..., description="ID de la misión"),
        include_deleted: bool = Query(False, description="Include invoices marked as deleted"),
        current_user: dict = Depends(require_bearer_token),        
        _: bool = Depends(require_role_access("/mision/facturas"))
):
    """
    Obtiene todas las facturas de una misión específica.

    **Parámetros:**
    - id_mision: ID único de la misión

    **Retorna:**
    - Información de la misión con todas sus facturas
    - Totales agregados (galones, dólares, cupones)
    """
    try:
        facturas_info = obtener_facturas(id_mision, include_deleted=include_deleted)
        return {
            "status": 200,
            "message": "Facturas obtenidas exitosamente",
            "data": facturas_info
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error obteniendo facturas: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error obteniendo facturas: {str(e)}")


@router.delete(
    "/factura/eliminar",
    summary="Eliminar factura de una misión",
    description="Este endpoint permite eliminar una factura asociada a una misión."
)
def api_eliminar_factura(
        payload: EliminarFactura,
        current_user: dict = Depends(require_bearer_token),        
        _: bool = Depends(require_role_access("/mision/factura/eliminar"))
):
    """
    Elimina una factura de una misión.

    **Parámetros:**
    - id_mision: ID único de la misión
    - id_factura: ID único de la factura a eliminar

    **Retorna:**
    - Mensaje de éxito
    """
    try:
        eliminado = eliminar_factura(payload)
        if not eliminado:
            raise HTTPException(status_code=404, detail="Factura no encontrada o no eliminada")
        return {
            "status": 200,
            "message": "Factura eliminada exitosamente"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error eliminando factura: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error eliminando factura: {str(e)}")


# -------------------- Forzar final por NoMision --------------------
@router.put(
    "/forzar-final",
    summary="Forzar estado final de una misión",
    description="Este endpoint permite forzar el estado final de una misión usando su número de misión."
)
def api_forzar_estado_final(
        NoMision: str = Query(..., alias="NoMision", description="Numero de mision (NoMision)"),
        current_user: dict = Depends(require_bearer_token),
        _: bool = Depends(require_role_access("/mision/forzar-final"))
):
    try:
        resultado = forzar_estado_final_por_no_mision(NoMision)
        return {
            "status": 200,
            "message": "Estado final forzado con exito",
            "data": resultado
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error forzando estado final: {str(e)}")
