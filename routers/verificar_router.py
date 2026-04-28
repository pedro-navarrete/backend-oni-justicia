# routers/verificar_router.py
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from services.verificar_service import verificar_dui_placa
from routers.user_router import require_bearer_token
from models.models import VerificarRequest
from utils.role_dependencies import require_role_access

router = APIRouter(prefix="/verificar", tags=["ONI Verificar"])


# -------------------- Endpoint seguro --------------------
@router.post("/duiyplaca")
def api_verificar(payload: VerificarRequest,
                  current_user: dict = Depends(require_bearer_token),
                  _: bool = Depends(require_role_access("/verificar/duiyplaca"))
                  ):
    """
    Verifica si el DUI y la placa existen en sus respectivas colecciones.
    Requiere Bearer Token válido.
    """
    try:
        valido = verificar_dui_placa(payload.dui, payload.placa)
        return {
            "status" : 200,
            "is_valid": valido
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {e}")
