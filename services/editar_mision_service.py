# services/mision_service.py - AGREGAR ESTA FUNCIÓN

import pytz
from datetime import datetime
from typing import Dict, Any
from fastapi import HTTPException
from database.verificador_mongo import ejecutar_query, update_document, ejecutar_query_V2, ejecutar_query_V4
from models.editar_mision_completa import EditarMisionCompleta
import logging

logger = logging.getLogger(__name__)

COLLECTION = "Misiones"


def editar_mision_completa(data: EditarMisionCompleta) -> Dict[str, Any]:
    """
    Edita una misión completa, incluyendo datos básicos y facturas con cupones.

    Permite:
    - Editar cualquier campo básico de la misión
    - Editar facturas existentes (número, galones, dólares, cupones)

    NO permite:
    - Agregar nuevas facturas (usar /factura/agregar)
    - Eliminar facturas (usar /factura/eliminar)

    Args:
        data: Datos de la misión a editar

    Returns:
        Dict con información detallada de los cambios realizados

    Raises:
        HTTPException: Si hay errores en validación o actualización
    """
    try:
        # 1. Verificar que la misión existe
        misiones = ejecutar_query(COLLECTION, {"NoMision": data.nomision})
        if not misiones:
            raise HTTPException(
                status_code=404,
                detail=f"Misión '{data.nomision}' no encontrada"
            )

        mision_actual = misiones[0]

        # 2. Preparar datos básicos para actualizar
        update_data = data.model_dump(
            exclude={"nomision", "facturas"},
            exclude_unset=True,
            exclude_none=True
        )

        # 3. Manejar edición de facturas
        facturas_editadas = 0
        facturas_no_encontradas = []

        if data.facturas:
            facturas_actuales = mision_actual.get("Facturas", [])

            if not facturas_actuales:
                raise HTTPException(
                    status_code=404,
                    detail="La misión no tiene facturas para editar"
                )

            # Editar cada factura especificada
            for factura_edicion in data.facturas:
                factura_encontrada = False

                for factura_actual in facturas_actuales:
                    if factura_actual.get("IdFactura") == factura_edicion.id_factura:
                        # Actualizar campos proporcionados
                        if factura_edicion.numero_factura is not None:
                            factura_actual["NumeroFactura"] = factura_edicion.numero_factura

                        if factura_edicion.cantidad_galones is not None:
                            factura_actual["CantidadGalones"] = factura_edicion.cantidad_galones

                        if factura_edicion.cantidad_dolares is not None:
                            factura_actual["CantidadDolares"] = factura_edicion.cantidad_dolares

                        if factura_edicion.cupones is not None:
                            factura_actual["Cupones"] = [
                                {"NumeroCupon": cupon.numero_cupon}
                                for cupon in factura_edicion.cupones
                            ]

                        # Agregar timestamp de edición
                        factura_actual["TimeStampEdicion"] = datetime.utcnow()

                        factura_encontrada = True
                        facturas_editadas += 1
                        logger.info(f"Factura '{factura_edicion.id_factura}' editada exitosamente")
                        break

                if not factura_encontrada:
                    facturas_no_encontradas.append(factura_edicion.id_factura)
                    logger.warning(f"Factura '{factura_edicion.id_factura}' no encontrada en la misión")

            # Agregar facturas actualizadas al update_data
            update_data["Facturas"] = facturas_actuales

        # 4. Verificar que hay algo que actualizar
        if not update_data:
            raise HTTPException(
                status_code=400,
                detail="No se enviaron campos para actualizar"
            )

        # 5. Agregar timestamp de actualización
        tz = pytz.timezone("America/El_Salvador")
        update_data["TimeStampActualizacion"] = datetime.now(tz)

        # 6. Actualizar en la base de datos
        updated_count = update_document(
            COLLECTION,
            {"NoMision": data.nomision},
            {"$set": update_data}
        )

        if updated_count == 0:
            raise HTTPException(
                status_code=500,
                detail="No se pudo actualizar la misión"
            )

        # 7. Preparar respuesta detallada
        respuesta = {
            "mision_actualizada": True,
            "no_mision": data.nomision,
            "campos_actualizados": [
                k for k in update_data.keys()
                if k not in ["TimeStampActualizacion", "Facturas"]
            ],
            "facturas": {
                "facturas_editadas": facturas_editadas,
                "facturas_no_encontradas": facturas_no_encontradas if facturas_no_encontradas else None
            },
            "timestamp": update_data["TimeStampActualizacion"]
        }

        logger.info(
            f"Misión '{data.nomision}' actualizada exitosamente. "
            f"Campos: {len(update_data)}, Facturas editadas: {facturas_editadas}"
        )

        return respuesta

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error editando misión completa: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error actualizando misión: {str(e)}"
        )


def obtener_detalle_mision_completo(nomision: str) -> Dict[str, Any]:
    """
    Obtiene el detalle completo de una misión con información de facturas.
    Útil para consultar antes de editar.

    Args:
        nomision: Número de la misión

    Returns:
        Dict con información completa de la misión
    """
    misiones = ejecutar_query_V4(COLLECTION, {"NoMision": nomision})

    if not misiones:
        raise HTTPException(
            status_code=404,
            detail=f"Misión '{nomision}' no encontrada"
        )

    mision = misiones[0]

    # Agregar resumen de facturas
    facturas = mision.get("Facturas", [])
    # mision["resumen_facturas"] = {
    #     "total_facturas": len(facturas),
    #     "total_galones": sum(f.get("CantidadGalones", 0) for f in facturas),
    #     "total_dolares": sum(f.get("CantidadDolares", 0) for f in facturas),
    #     "total_cupones": sum(len(f.get("Cupones", [])) for f in facturas),
    #     "detalle_facturas": [
    #         {
    #             "id_factura": f.get("IdFactura"),
    #             "numero_factura": f.get("NumeroFactura"),
    #             "galones": f.get("CantidadGalones"),
    #             "dolares": f.get("CantidadDolares"),
    #             "cantidad_cupones": len(f.get("Cupones", [])),
    #             "cupones": [c.get("NumeroCupon") for c in f.get("Cupones", [])]
    #         }
    #         for f in facturas
    #     ]
    # }

    return mision