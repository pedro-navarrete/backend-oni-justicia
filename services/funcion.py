import datetime
from fastapi import Depends
from starlette.responses import JSONResponse

def last_doc(filtro_principal, collection):
    documento = collection.find_one(filtro_principal)
    return documento

def update_doc_1(collection, documento, mov, ahora):
    try:
        collection.find_one_and_update(
            {"Dui": mov.Dui},
            {
                "$set": {
                    "LatitudAnt": documento.get("LatitudAct"),
                    "LongitudAnt": documento.get("LongitudAct"),
                    "FechaHoraAnt": documento.get("FechaHoraAct"),
                    "LatitudAct": mov.LatitudAct,
                    "LongitudAct": mov.LongitudAct,
                    "FechaHoraAct": mov.FechaHoraAct,
                    "Estado": mov.Estado,
                    "NivelBateria":mov.NivelBateria,
                    "TimeStamp": ahora
                }
            },
            return_document=ReturnDocument.AFTER
        )

        return True
    except Exception as e:
        print("Error producido en update: ", e)
        return False

async def registrar_movimientos(movimientos, client, MONGO_DB):
    #movimientos = sorted(payload.movimientos, key=lambda x: x.FechaHoraAct)
    ahora = datetime.utcnow()

    dui = movimientos[0].Dui

    if not movimientos:
        return JSONResponse(content={"msg": "Lista vacía", "status": 400}, status_code=400)

    #client = get_connexion()
    db = client[MONGO_DB]
    collection = db["UltimoMovs"]

    historico_ruta = []
    errores = []

    estado_valido = True
    cambio_conductor = None

    for i, mov in enumerate(movimientos):
        doc_actual = last_doc({"Dui": mov.Dui}, collection)
        operacion_exitosa = False

        # Validar cambio de DUI correctamente
        if i > 0:
            dui_anterior = movimientos[i - 1].Dui
            estado_anterior = movimientos[i - 1].Estado

            if mov.Dui != dui_anterior and mov.Estado == "inicio":
                if estado_anterior != "final":
                    estado_valido = False
                    break
                else:
                    cambio_conductor = i

    # Validación de cambio de DUI inválido
    if not estado_valido:
        client.close()
        return JSONResponse(
            content={"msg": "Cambio de DUI inválido: el anterior no tiene estado 'final'", "status": 400},
            status_code=400)

    for i, mov in enumerate(movimientos):
        doc_actual = last_doc({"Dui": mov.Dui}, collection)

        operacion_exitosa = False

        if doc_actual:
            if doc_actual["Dui"] == mov.Dui and doc_actual["Estado"] == "inicio" and (
                    mov.Estado == "enruta" or mov.Estado == "final"):
                operacion_exitosa = update_doc_1(collection, doc_actual, mov, ahora)
            elif doc_actual["Dui"] == mov.Dui and doc_actual["Estado"] == "enruta" and (
                    mov.Estado == "enruta" or mov.Estado == "final"):
                operacion_exitosa = update_doc_1(collection, doc_actual, mov, ahora)
            elif doc_actual["Dui"] == mov.Dui and doc_actual["Estado"] == "final" and mov.Estado == "inicio":
                operacion_exitosa = update_doc_1(collection, doc_actual, mov, ahora)
            # #--- Caso dui diferentes
            # elif doc_actual["Dui"] != mov.Dui and doc_actual["Estado"] == "inicio" and (mov.Estado == "enruta" or mov.Estado == "final"):
            #     operacion_exitosa = update_doc_2(collection, doc_actual, mov, ahora)
            # elif doc_actual["Dui"] != mov.Dui and doc_actual["Estado"] == "enruta" and (mov.Estado == "enruta" or mov.Estado == "final"):
            #     operacion_exitosa = update_doc_2(collection, doc_actual, mov, ahora)
            # elif doc_actual["Dui"] != mov.Dui and doc_actual["Estado"] == "final" and mov.Estado == "inicio":
            #     operacion_exitosa = update_doc_2(collection, doc_actual, mov, ahora)
        else:

            if mov.Estado == "inicio":
                print("Sea iniciado una nueva ruta: ", mov)
                operacion_exitosa = insert_doc(collection, mov, ahora)

        status_op = 200 if operacion_exitosa else 500
        entrada = {
            "LatitudAct": mov.LatitudAct,
            "LongitudAct": mov.LongitudAct,
            "FechaHoraAct": mov.FechaHoraAct,
            "Estado": mov.Estado,
            "StatusOperacion": status_op,
            "Dui": mov.Dui,
            "NivelBateria": mov.NivelBateria
        }

        historico_ruta.append(entrada)

        if status_op == 500:
            print("Error encontrado en:")
            print(mov)
            errores.append({
                "Dui": mov.Dui,
                "FechaHoraAct": mov.FechaHoraAct,
                "NivelBateria": mov.NivelBateria,
                "msg": "Error al procesar movimiento"
            })

    # Guardar en HistoriDiaMovs solo si todo fue exitoso
    try:
        client2 = get_connexion2()
        db2 = client2[MONGO_DB]
        historico_collection = db2["HistoriDiaMovs"]

        existe_doc = historico_collection.find_one({"Dui": dui})
        rutas_existentes = existe_doc.get("Rutas", []) if existe_doc else []
        numero_ruta_actual = rutas_existentes[-1]["Ruta"] if rutas_existentes else 0

        updates = []

        # Validar lógica especial si comienza con "inicio"
        if historico_ruta and historico_ruta[0].get("Estado") == "inicio":
            if rutas_existentes:
                ultima_ruta = rutas_existentes[-1]
                coordenadas_existentes = ultima_ruta.get("coordenadas", [])
                estado_ultimo_punto = coordenadas_existentes[-1].get("Estado") if coordenadas_existentes else None

                if estado_ultimo_punto != "final":
                    client2.close()
                    return JSONResponse(content={
                        "msg": "La última ruta existente no ha finalizado",
                        "status": 409,
                        "errores": historico_ruta
                    }, status_code=409)

            # Si no hay rutas existentes o terminó en "final", se crea una nueva ruta
            updates.append({
                "Ruta": numero_ruta_actual + 1,
                "coordenadas": historico_ruta
            })

            if existe_doc:
                historico_collection.update_one(
                    {"Dui": dui},
                    {
                        "$push": {"Rutas": {"$each": updates}},
                        "$set": {"TimeStamp": ahora}
                    }
                )
            else:
                historico_collection.insert_one({
                    "Dui": dui,
                    "Rutas": updates,
                    "TimeStamp": ahora
                })

        else:
            # Lógica normal cuando no comienza con Estado = "inicio"
            if cambio_conductor is not None:
                parte_1 = historico_ruta[:cambio_conductor]
                parte_2 = historico_ruta[cambio_conductor:]
            else:
                parte_1 = historico_ruta
                parte_2 = []

            if existe_doc:
                if parte_1:
                    if rutas_existentes:
                        historico_collection.update_one(
                            {"Dui": dui, "Rutas.Ruta": numero_ruta_actual},
                            {"$push": {"Rutas.$.coordenadas": {"$each": parte_1}}}
                        )
                    else:
                        updates.append({
                            "Ruta": 1,
                            "coordenadas": parte_1
                        })

                if parte_2:
                    updates.append({
                        "Ruta": numero_ruta_actual + 1 if rutas_existentes else 2,
                        "coordenadas": parte_2
                    })

                if updates:
                    historico_collection.update_one(
                        {"Dui": dui},
                        {
                            "$push": {"Rutas": {"$each": updates}},
                            "$set": {"TimeStamp": ahora}
                        }
                    )
                else:
                    historico_collection.update_one(
                        {"Dui": dui},
                        {
                            "$set": {"TimeStamp": ahora}
                        }
                    )
            else:
                rutas = []
                if parte_1:
                    rutas.append({
                        "Ruta": 1,
                        "coordenadas": parte_1
                    })
                if parte_2:
                    rutas.append({
                        "Ruta": 2,
                        "coordenadas": parte_2
                    })

                historico_collection.insert_one({
                    "Dui": dui,
                    "Rutas": rutas,
                    "TimeStamp": ahora
                })

        client2.close()

    except Exception as e:
        print("Error guardando en HistoriDiaMovs:", e)
        return JSONResponse(content={
            "msg": "No se pudo guardar el historial",
            "status": 500,
            "errores": historico_ruta
        }, status_code=500)

    finally:
        client.close()

    # Enviar el último punto por WebSocket
    ultimo_punto = historico_ruta[-1] if historico_ruta else None
    ultimo_punto = ultimo_punto | {"Dui": dui}
    if ultimo_punto:
        print("Enviando por WebSocket el ultimo punto regitrado.")
        asyncio.create_task(enviar_por_websocket(ultimo_punto))

    if errores:
        return JSONResponse(content={
            "msg": "Uno o más movimientos no se pudieron procesar",
            "status": 400,
            "errores": errores
        }, status_code=400)
    else:

        return JSONResponse(content={"msg": "Movimientos procesados correctamente", "status": 200}, status_code=200)
