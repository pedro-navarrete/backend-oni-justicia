import os
import requests
import json
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

class SotiTokenManager:
    def __init__(self):
        """
        Inicializa el administrador de tokens leyendo los datos del entorno (.env)
        """
        self.tenant = os.getenv("SOTI_TENANT", "default_tenant")
        self.token_url = os.getenv("SOTI_TOKEN_URL")
        self.client_id = os.getenv("SOTI_CLIENT_ID")
        self.client_secret = os.getenv("SOTI_CLIENT_SECRET")
        self.username = os.getenv("SOTI_USERNAME")
        self.password = os.getenv("SOTI_PASSWORD")

        # Validar variables requeridas
        required = {
            "SOTI_TOKEN_URL": self.token_url,
            "SOTI_CLIENT_ID": self.client_id,
            "SOTI_CLIENT_SECRET": self.client_secret,
            "SOTI_USERNAME": self.username,
            "SOTI_PASSWORD": self.password,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Variables de entorno faltantes para SOTI: {', '.join(missing)}")

        # Carpeta para guardar tokens
        self.token_dir = "tokens"
        os.makedirs(self.token_dir, exist_ok=True)
        self.token_file = os.path.join(self.token_dir, f"token_{self.tenant}.json")

        self.token_soti = None
        self.refresh_token_soti = None
        self.token_type = "bearer"
        self.token_expiration_soti = None

        self._cargar_token()

    def _cargar_token(self):
        """Carga el token desde archivo si existe"""
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, "r") as f:
                    token_data = json.load(f)
                self.token_soti = token_data.get("access_token")
                self.refresh_token_soti = token_data.get("refresh_token")
                self.token_type = token_data.get("token_type", "bearer")
                expiration_str = token_data.get("token_expiration")
                self.token_expiration_soti = datetime.fromisoformat(expiration_str) if expiration_str else None
                logger.info(f"[{self.tenant}] Token cargado desde archivo.")
            except Exception as e:
                logger.exception(f"[{self.tenant}] Error al leer token: {e}")

    def get_token(self):
        """Obtiene un token válido (usa refresh si es posible)"""
        # Token aún válido
        if self.token_soti and self.token_expiration_soti:
            if datetime.now(timezone.utc) < self.token_expiration_soti:
                logger.info(f"[{self.tenant}] Token aún válido.")
                return self.token_soti

        # Intentar refrescar
        if self.refresh_token_soti:
            logger.info(f"[{self.tenant}] Intentando refrescar token...")
            refresh_data = {
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token_soti
            }
            try:
                response = requests.post(self.token_url, data=refresh_data)
                if response.status_code == 200:
                    return self._guardar_token(response.json(), "refresh_token")
                else:
                    logger.warning(f"[{self.tenant}] Fallo al refrescar token: {response.status_code} - {response.text}")
            except requests.RequestException as e:
                logger.exception(f"[{self.tenant}] Excepción al refrescar token: {e}")

        # Solicitar nuevo token
        logger.info(f"[{self.tenant}] Solicitando nuevo token con credenciales.")
        data = {
            "grant_type": "password",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "username": self.username,
            "password": self.password
        }
        try:
            response = requests.post(self.token_url, data=data)
            if response.status_code == 200:
                return self._guardar_token(response.json(), "nuevo_token")
            else:
                logger.error(f"[{self.tenant}] Error al obtener token: {response.status_code} - {response.text}")
        except requests.RequestException as e:
            logger.exception(f"[{self.tenant}] Excepción al obtener token: {e}")

        return None

    def _guardar_token(self, response_json, contexto):
        """Guarda el token en memoria y en archivo"""
        self.token_soti = response_json.get("access_token")
        self.refresh_token_soti = response_json.get("refresh_token")
        self.token_type = response_json.get("token_type", "bearer")
        expires_in = response_json.get("expires_in", 3600)
        self.token_expiration_soti = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)

        try:
            token_data = {
                "access_token": self.token_soti,
                "refresh_token": self.refresh_token_soti,
                "token_type": self.token_type,
                "token_expiration": self.token_expiration_soti.isoformat()
            }
            with open(self.token_file, "w") as f:
                json.dump(token_data, f)
            logger.info(f"[{self.tenant}] Token guardado correctamente ({contexto}).")
        except Exception as e:
            logger.exception(f"[{self.tenant}] Error al guardar token: {e}")

        return self.token_soti
