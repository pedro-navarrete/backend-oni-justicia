# authentication/basic_auth_service.py
import os
from fastapi import HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from dotenv import load_dotenv

load_dotenv()

# Credenciales API desde .env
API_USER = os.getenv("API_USER")
API_PASSWORD = os.getenv("API_PASSWORD")

security = HTTPBasic()

class BasicAuthService:
    """ Verifica las credenciales de cliente usando Basic Auth"""

    @staticmethod
    def verify_client(credentials: HTTPBasicCredentials):
        """
        credentials: inyectado con Depends(security) en el endpoint
        """
        if credentials.username != API_USER or credentials.password != API_PASSWORD:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales de cliente inválidas",
                headers={"WWW-Authenticate": "Basic"},
            )
        return credentials.username
