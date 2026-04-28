import os
import logging
import psycopg2
import pymssql
from contextlib import contextmanager
from dotenv import load_dotenv

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Cargar variables del .env
load_dotenv()


class VerificadorSQL:
    """Clase robusta para conectarse a SQL Server o PostgreSQL sin ORM ni ODBC."""

    def __init__(self, prefix: str = "MSSQL"):
        self.prefix = prefix.upper()
        self.engine = os.getenv(f"{self.prefix}_ENGINE")
        self.server = os.getenv(f"{self.prefix}_HOST")
        self.port = os.getenv(f"{self.prefix}_PORT")
        self.database = os.getenv(f"{self.prefix}_NAME")
        self.username = os.getenv(f"{self.prefix}_USER")
        self.password = os.getenv(f"{self.prefix}_PASSWORD")
        self._validar_variables()

    def _validar_variables(self):
        missing = [
            var for var, val in {
                f'{self.prefix}_ENGINE': self.engine,
                f'{self.prefix}_HOST': self.server,
                f'{self.prefix}_PORT': self.port,
                f'{self.prefix}_NAME': self.database,
                f'{self.prefix}_USER': self.username,
                f'{self.prefix}_PASSWORD': self.password
            }.items() if not val
        ]

        if missing:
            raise EnvironmentError(f"Faltan variables en .env: {', '.join(missing)}")

        if self.engine not in ("mssql", "postgres"):
            raise ValueError(f"{self.prefix}_ENGINE debe ser 'mssql' o 'postgres'.")

    @contextmanager
    def conexionDB(self):
        conn = None
        try:
            if self.engine == "mssql":
                conn = pymssql.connect(
                    server=self.server,
                    port=int(self.port),
                    user=self.username,
                    password=self.password,
                    database=self.database,
                    login_timeout=30,
                    timeout=30,
                    charset="UTF-8"
                )

            elif self.engine == "postgres":
                conn = psycopg2.connect(
                    host=self.server,
                    port=int(self.port),
                    user=self.username,
                    password=self.password,
                    dbname=self.database,
                    connect_timeout=30
                )

            logging.info(
                f"[{self.prefix}] Conectado a {self.engine.upper()} {self.server}:{self.port}/{self.database}"
            )
            yield conn

        except Exception as e:
            logging.error(f"[{self.prefix}] Error de conexión: {e}")
            raise

        finally:
            if conn:
                try:
                    conn.close()
                    logging.info(f"[{self.prefix}] Conexión cerrada")
                except Exception as e:
                    logging.error(f"[{self.prefix}] Error cerrando conexión: {e}")

    def ejecutar_querySQL(self, query: str, tipo: str = "SELECT", params: tuple = None):
        """
        Ejecuta cualquier query SQL.
        SELECT  -> list[dict]
        INSERT/UPDATE/DELETE -> int (filas afectadas)
        """
        conn = None
        try:
            with self.conexionDB() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params or ())

                if tipo.upper() == "SELECT":
                    columnas = [col[0] for col in cursor.description]
                    filas = cursor.fetchall()
                    resultado = [dict(zip(columnas, fila)) for fila in filas]

                    logging.info(
                        f"[{self.prefix}] SELECT OK - filas: {len(resultado)}"
                    )
                    return resultado

                else:
                    conn.commit()
                    filas_afectadas = cursor.rowcount
                    logging.info(
                        f"[{self.prefix}] {tipo.upper()} OK - filas afectadas: {filas_afectadas}"
                    )
                    return filas_afectadas

        except Exception as e:
            logging.error(f"[{self.prefix}] Error ejecutando query: {e}")

            if conn:
                try:
                    conn.rollback()
                    logging.warning(f"[{self.prefix}] Rollback ejecutado")
                except Exception as rb_err:
                    logging.error(f"[{self.prefix}] Error en rollback: {rb_err}")

            raise
