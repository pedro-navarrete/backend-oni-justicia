import os
import json
import logging

WEBSOCKET_URL = os.getenv('WEBSOCKET_URL')
WEBSOCKET_TOKEN = os.getenv('WEBSOCKET_TOKEN')

if WEBSOCKET_URL is None or WEBSOCKET_TOKEN is None:
    raise RuntimeError('WEBSOCKET_URL and WEBSOCKET_TOKEN must be set as environment variables')

logger = logging.getLogger(__name__)

def json_serializer(data):
    try:
        return json.dumps(data)
    except (TypeError, ValueError) as e:
        logger.error("Failed to serialize data: %s", e)
        raise


def enviar_por_websocket(data):
    serialized_data = json_serializer(data)
    # Logic to send the serialized data over websocket...
    logger.info('Data sent over websocket: %s', serialized_data)
