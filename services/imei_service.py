# services/imei_service.py
import requests
import logging
from fastapi import HTTPException
from services.soti_service import SotiTokenManager

logger = logging.getLogger(__name__)

class DispositivoService:
    def __init__(self):
        self.token_manager = SotiTokenManager()
        #self.base_url = "https://a0029961.mobicontrol.cloud/MobiControl/api/devices"
        self.base_url = "https://a0029961.mobicontrol.cloud/MobiControl/api/devices/search?groupPath=referenceId:0cdfdc3d-6474-4496-8138-b90179fe244b&includeSubgroups=false&verifyAndSync=true"

    def obtener_por_imei(self, imei: str):
        """
        Busca un dispositivo comparando IMEI con DeviceId y
        retorna NOMBRE y TELEFONO desde CustomAttributes.
        """
        token = self.token_manager.get_token()
        if not token:
            raise HTTPException(
                status_code=401,
                detail="No se pudo obtener token válido de SOTI"
            )

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        try:
            response = requests.get(
                self.base_url,
                headers=headers,
                timeout=20
            )
        except requests.RequestException as e:
            logger.exception("Error de conexión con SOTI")
            raise HTTPException(
                status_code=502,
                detail=f"Error al conectar con SOTI: {e}"
            )

        if response.status_code != 200:
            logger.error(
                f"Error SOTI {response.status_code}: {response.text}"
            )
            raise HTTPException(
                status_code=500,
                detail="Error al consultar dispositivos en SOTI"
            )

        dispositivos = response.json()

        if not isinstance(dispositivos, list):
            raise HTTPException(
                status_code=500,
                detail="Formato inesperado de respuesta de SOTI"
            )

        for device in dispositivos:
            if str(device.get("DeviceId")) == str(imei):

                nombre = None
                telefono = None

                for attr in device.get("CustomAttributes", []):
                    if attr.get("Name") == "NOMBRE":
                        nombre = attr.get("Value")
                    elif attr.get("Name") == "TELEFONO":
                        telefono = attr.get("Value")

                return {
                    "imei": imei,
                    "nombre": nombre,
                    "telefono": telefono
                }

        raise HTTPException(
            status_code=404,
            detail=f"No se encontró dispositivo con IMEI {imei}"
        )
