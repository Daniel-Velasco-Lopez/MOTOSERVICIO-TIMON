import time
import structlog
from fastapi import APIRouter, HTTPException

from app.models.schemas import MessageRequest, MessageResponse
from app.config import settings

logger = structlog.get_logger()
router = APIRouter()


@router.post("/messages", response_model=MessageResponse)
async def process_message(request: MessageRequest):
    start = time.monotonic()
    trace_id = f"trace_{request.telefono}_{int(start)}"

    logger.info(
        "message_received",
        telefono=request.telefono,
        nombre=request.nombre,
        trace_id=trace_id,
    )

    # TODO: Fase 2 — conectar orquestador completo
    # Por ahora, respuesta placeholder

    elapsed = (time.monotonic() - start) * 1000

    logger.info(
        "message_processed",
        telefono=request.telefono,
        tiempo_ms=elapsed,
        trace_id=trace_id,
    )

    return MessageResponse(
        success=True,
        respuesta=f"Hola {request.nombre or 'amigo'}, gracias por tu mensaje. "
        f"Tu consulta será procesada por nuestro asistente.",
        categoria="GENERAL",
        conversacion_id=None,
        requiere_accion=None,
        tiempo_procesamiento_ms=int(elapsed),
    )
