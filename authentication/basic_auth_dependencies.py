# authentication/basic_auth_dependencies.py
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from authentication.basic_auth_service import BasicAuthService
import logging

# Configurar logger global para authentication
logger = logging.getLogger("auth_dependencies")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

security = HTTPBasic()

def require_basic_auth(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Dependencia global para Basic Auth.
    Se puede usar en cualquier router mediante Depends(require_basic_auth)
    """
    try:
        client_username = BasicAuthService.verify_client(credentials)
        logger.info(f"Basic Auth válido para cliente: {client_username}")
        return client_username
    except HTTPException as e:
        logger.warning(f"Basic Auth inválido: {e.detail}")
        raise