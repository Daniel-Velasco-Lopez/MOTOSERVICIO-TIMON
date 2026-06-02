import time
import structlog
from fastapi import APIRouter

from app.models.schemas import MessageRequest, MessageResponse
from app.orchestrator.message_processor import MessageProcessor
from app.memory.service import MemoryService
from app.rag.pipeline import RAGPipeline

logger = structlog.get_logger()
router = APIRouter()

memory_service = MemoryService()
rag_pipeline = RAGPipeline()
message_processor = MessageProcessor(memory_service=memory_service, rag_pipeline=rag_pipeline)


@router.post("/messages", response_model=MessageResponse)
async def process_message(request: MessageRequest):
    start = time.monotonic()
    trace_id = f"trace_{request.telefono}_{int(start)}"

    logger.info("message_received", telefono=request.telefono, nombre=request.nombre, trace_id=trace_id)

    try:
        result = await message_processor.process(
            mensaje=request.mensaje,
            session_id=request.telefono,
            telefono=request.telefono,
            nombre=request.nombre,
        )

        elapsed = (time.monotonic() - start) * 1000
        classification = result.get("classification", {})
        intent = classification.get("intencion_principal", "GENERAL")

        return MessageResponse(
            success=True,
            respuesta=result["respuesta"],
            categoria=intent,
            conversacion_id=None,
            requiere_accion=None,
            proximo_estado=result.get("state_machine", {}).get("current"),
            tiempo_procesamiento_ms=int(elapsed),
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        logger.error("message_error", telefono=request.telefono, error=str(e), trace_id=trace_id)

        return MessageResponse(
            success=False,
            respuesta="Lo siento, ocurrió un error al procesar tu mensaje. Por favor intenta de nuevo.",
            categoria="ERROR",
            tiempo_procesamiento_ms=int(elapsed),
            error=str(e),
            codigo_error="PROCESSING_ERROR",
        )
