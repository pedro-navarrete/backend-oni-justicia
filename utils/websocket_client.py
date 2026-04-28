import json
import os
import logging
from datetime import datetime, date
from typing import Any, Dict

import websockets

logger = logging.getLogger(__name__)


def json_serializer(obj: Any):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Tipo no serializable: {type(obj)}")


async def enviar_por_websocket(category: str, data: Dict[str, Any]):
    """
    Envía un mensaje estructurado por WebSocket.

    Estructura:
    {
        "category": "<category>",
        "data": { ... }
    }
    """
    websocket_url = os.getenv("WEBSOCKET_URL")
    websocket_token = os.getenv("WEBSOCKET_TOKEN")

    if not websocket_url or not websocket_token:
        raise RuntimeError("WEBSOCKET_URL o WEBSOCKET_TOKEN no están configurados en el entorno")

    payload = {"category": category, "data": data}
    ws_url = f"{websocket_url}?token={websocket_token}"

    try:
        logger.info("Conectando a WebSocket: %s", ws_url)
        async with websockets.connect(ws_url) as websocket:
            await websocket.send(json.dumps(payload, default=json_serializer))

        logger.info("Mensaje WebSocket enviado | category=%s", category)

    except Exception:
        logger.exception("Error enviando mensaje por WebSocket")
        raise