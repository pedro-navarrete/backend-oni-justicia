"""
Servicio CRUD completo para EstadoVehiculo
Adaptado a tabla:
Id
Codigo (UNIQUE)
Nombre
Descripcion
PermiteAsignacion
Eliminado
FechaHoraCreacion
FechaHoraActualizacion
FechaHoraEliminacion
"""

import logging
from typing import Optional, Dict
from datetime import datetime
from database.verificador_sqlserver import VerificadorSQL

logger = logging.getLogger(__name__)


class EstadoVehiculoService:

    TABLA = "EstadoVehiculo"

    def __init__(self, prefix: str = "MSSQL"):
        self.db = VerificadorSQL(prefix=prefix)

    # ---------------------------------------------------
    # Helpers
    # ---------------------------------------------------

    def _to_tuple(self, params):
        if params is None:
            return ()
        if isinstance(params, tuple):
            return params
        if isinstance(params, list):
            return tuple(params)
        return (params,)

    def select(self, query: str, params=None):
        return self.db.ejecutar_querySQL(
            query, tipo="SELECT", params=self._to_tuple(params)
        )

    def ejecutar(self, query: str, params=None):
        return self.db.ejecutar_querySQL(
            query, tipo="OTHER", params=self._to_tuple(params)
        )

    def _serializar_fila(self, fila: Dict) -> Dict:
        if not fila:
            return {}

        def _to_iso(v):
            if hasattr(v, "isoformat"):
                return v.isoformat()
            return v

        return {
            "id": fila.get("Id"),
            "codigo": fila.get("Codigo"),
            "nombre": fila.get("Nombre"),
            "descripcion": fila.get("Descripcion"),
            "permiteAsignacion": bool(fila.get("PermiteAsignacion")),
            "eliminado": bool(fila.get("Eliminado")),
            "fechaHoraCreacion": _to_iso(fila.get("FechaHoraCreacion")),
            "fechaHoraActualizacion": _to_iso(fila.get("FechaHoraActualizacion")),
        }

    # ---------------------------------------------------
    # VALIDACIONES
    # ---------------------------------------------------

    def _validar_codigo_unico(self, codigo: str, excluir_id: Optional[int] = None):

        query = f"SELECT Id, Eliminado FROM {self.TABLA} WHERE Codigo = %s"
        params = [codigo]

        if excluir_id:
            query += " AND Id != %s"
            params.append(excluir_id)

        resultado = self.select(query, params)

        if not resultado:
            return {"disponible": True}

        registro = resultado[0]

        if registro.get("Eliminado"):
            return {"disponible": False, "eliminado_id": registro.get("Id")}
        else:
            return {
                "disponible": False,
                "error": f"Ya existe un estado con el código '{codigo}'"
            }

    def _validar_existencia(self, id_registro: int):

        query = f"""
            SELECT *
            FROM {self.TABLA}
            WHERE Id = %s AND Eliminado = 0
        """

        resultado = self.select(query, (id_registro,))
        return self._serializar_fila(resultado[0]) if resultado else None

    # ---------------------------------------------------
    # CREAR
    # ---------------------------------------------------

    def crear(self, datos: Dict):

        try:
            codigo = datos.get("codigo", "").strip().upper()
            nombre = datos.get("nombre", "").strip()
            descripcion = datos.get("descripcion")
            permite_asignacion = bool(datos.get("permiteAsignacion", False))

            if not codigo:
                return {"error": "El código es obligatorio", "status": 400}

            resultado_codigo = self._validar_codigo_unico(codigo)

            if not resultado_codigo.get("disponible"):

                if "error" in resultado_codigo:
                    return {"error": resultado_codigo["error"], "status": 409}

                if "eliminado_id" in resultado_codigo:
                    return self._reactivar_registro(
                        resultado_codigo["eliminado_id"],
                        datos
                    )

            ahora = datetime.now()

            query = f"""
                INSERT INTO {self.TABLA}
                (Codigo, Nombre, Descripcion, PermiteAsignacion,
                 Eliminado, FechaHoraCreacion, FechaHoraActualizacion)
                VALUES (%s, %s, %s, %s, 0, %s, %s)
            """

            self.ejecutar(query, (
                codigo,
                nombre,
                descripcion,
                permite_asignacion,
                ahora,
                ahora
            ))

            id_nuevo = self.select(
                f"SELECT MAX(Id) AS NuevoId FROM {self.TABLA} WHERE Codigo = %s",
                (codigo,)
            )[0]["NuevoId"]

            return {"data": self._validar_existencia(id_nuevo)}

        except Exception as e:
            logger.error(f"Error al crear EstadoVehiculo: {e}")
            return {"error": str(e), "status": 500}

    # ---------------------------------------------------
    # OBTENER POR ID
    # ---------------------------------------------------

    def obtener_por_id(self, id_registro: int):

        registro = self._validar_existencia(id_registro)

        if not registro:
            return {
                "error": f"EstadoVehiculo con Id {id_registro} no encontrado",
                "status": 404
            }

        return {"data": registro}

    # ---------------------------------------------------
    # LISTAR
    # ---------------------------------------------------

    def listar(self, pagina=1, por_pagina=10, busqueda=None):

        if pagina < 1:
            pagina = 1

        if por_pagina < 1:
            por_pagina = 10

        if por_pagina > 100:
            por_pagina = 100

        where = "WHERE Eliminado = 0"
        params = []

        if busqueda:
            where += " AND (Codigo LIKE %s OR Nombre LIKE %s)"
            termino = f"%{busqueda}%"
            params.extend([termino, termino])

        total = self.select(
            f"SELECT COUNT(*) AS Total FROM {self.TABLA} {where}",
            params
        )[0]["Total"]

        offset = (pagina - 1) * por_pagina

        query = f"""
            SELECT *
            FROM {self.TABLA}
            {where}
            ORDER BY Nombre ASC
            OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
        """

        registros = self.select(query, params + [offset, por_pagina])

        return {
            "data": {
                "total": total,
                "pagina": pagina,
                "porPagina": por_pagina,
                "registros": [self._serializar_fila(r) for r in registros]
            }
        }

    # ---------------------------------------------------
    # ACTUALIZAR
    # ---------------------------------------------------

    def actualizar(self, id_registro: int, datos: Dict):

        existente = self._validar_existencia(id_registro)

        if not existente:
            return {"error": "Registro no encontrado", "status": 404}

        campos = []
        params = []

        if "codigo" in datos:
            nuevo_codigo = datos["codigo"].strip().upper()

            validacion = self._validar_codigo_unico(
                nuevo_codigo,
                excluir_id=id_registro
            )

            if not validacion.get("disponible") and "error" in validacion:
                return {"error": validacion["error"], "status": 409}

            campos.append("Codigo = %s")
            params.append(nuevo_codigo)

        if "nombre" in datos:
            campos.append("Nombre = %s")
            params.append(datos["nombre"].strip())

        if "descripcion" in datos:
            campos.append("Descripcion = %s")
            params.append(datos["descripcion"])

        if "permiteAsignacion" in datos:
            campos.append("PermiteAsignacion = %s")
            params.append(bool(datos["permiteAsignacion"]))

        if not campos:
            return {"error": "No hay campos para actualizar", "status": 400}

        campos.append("FechaHoraActualizacion = %s")
        params.append(datetime.now())
        params.append(id_registro)

        query = f"""
            UPDATE {self.TABLA}
            SET {', '.join(campos)}
            WHERE Id = %s AND Eliminado = 0
        """

        self.ejecutar(query, params)

        return {"data": self._validar_existencia(id_registro)}

    # ---------------------------------------------------
    # ELIMINAR (SOFT DELETE)
    # ---------------------------------------------------

    def eliminar(self, id_registro: int):

        existente = self._validar_existencia(id_registro)

        if not existente:
            return {"error": "Registro no encontrado", "status": 404}

        ahora = datetime.now()

        query = f"""
            UPDATE {self.TABLA}
            SET Eliminado = 1,
                FechaHoraEliminacion = %s,
                FechaHoraActualizacion = %s
            WHERE Id = %s AND Eliminado = 0
        """

        self.ejecutar(query, (ahora, ahora, id_registro))

        return {
            "data": {
                "mensaje": f"EstadoVehiculo '{existente['nombre']}' eliminado correctamente"
            }
        }

    # ---------------------------------------------------
    # REACTIVAR (INTERNO)
    # ---------------------------------------------------

    def _reactivar_registro(self, id_registro: int, datos: Dict):

        ahora = datetime.now()

        query = f"""
            UPDATE {self.TABLA}
            SET Nombre = %s,
                Descripcion = %s,
                PermiteAsignacion = %s,
                Eliminado = 0,
                FechaHoraEliminacion = NULL,
                FechaHoraActualizacion = %s
            WHERE Id = %s
        """

        self.ejecutar(query, (
            datos.get("nombre"),
            datos.get("descripcion"),
            bool(datos.get("permiteAsignacion", False)),
            ahora,
            id_registro
        ))

        return {"data": self._validar_existencia(id_registro)}


    def listar_todos(
        self,
        codigo: Optional[str] = None,
        nombre: Optional[str] = None,
        permite_asignacion: Optional[bool] = None,
        busqueda: Optional[str] = None
    ) -> Dict:
        """Lista todos los estados de vehículo activos sin paginación"""
        try:
            where_clauses = ["Eliminado = 0"]
            params = []

            if codigo:
                where_clauses.append("Codigo LIKE %s")
                params.append(f"%{codigo}%")

            if nombre:
                where_clauses.append("Nombre LIKE %s")
                params.append(f"%{nombre}%")

            if permite_asignacion is not None:
                where_clauses.append("PermiteAsignacion = %s")
                params.append(permite_asignacion)

            if busqueda:
                where_clauses.append(
                    "(Codigo LIKE %s OR Nombre LIKE %s OR Descripcion LIKE %s)"
                )
                termino = f"%{busqueda}%"
                params.extend([termino, termino, termino])

            where_sql = " AND ".join(where_clauses)

            query = f"""
                SELECT Id, Codigo, Nombre, Descripcion, PermiteAsignacion,
                       Eliminado, FechaHoraCreacion, FechaHoraActualizacion
                FROM EstadoVehiculo
                WHERE {where_sql}
                ORDER BY Nombre ASC
            """

            try:
                registros = self.select(query, tuple(params))
            except Exception as e:
                # Si la tabla no tiene la columna Eliminado en esta BD, reintentar sin esa condición
                txt = str(e).lower()
                if 'invalid column name' in txt and 'eliminado' in txt or "eliminado" in txt and '207' in txt:
                    logger.warning(f"Columna 'Eliminado' no encontrada en EstadoVehiculo: reintentando sin filtro. Error: {e}")
                    # Construir query sin la columna Eliminado y sin su condición en where_sql
                    # Eliminamos posibles 'Eliminado = 0' si está en where_clauses
                    where_clauses_sin_elim = [c for c in where_clauses if 'eliminado' not in c.lower()]
                    where_sql_sin_elim = ' AND '.join(where_clauses_sin_elim) if where_clauses_sin_elim else '1=1'
                    query2 = f"""
                        SELECT Id, Codigo, Nombre, Descripcion, PermiteAsignacion,
                               FechaHoraCreacion, FechaHoraActualizacion
                        FROM EstadoVehiculo
                        WHERE {where_sql_sin_elim}
                        ORDER BY Nombre ASC
                    """
                    registros = self.select(query2, tuple([p for p in params if p is not None]))
                else:
                    raise

            return {
                "data": [self._serializar_fila(r) for r in registros] if registros else []
            }

        except Exception as e:
            logger.error(f"Error al listar todos EstadoVehiculo: {e}")
            return {"error": f"Error interno al listar registros: {str(e)}", "status": 500}

