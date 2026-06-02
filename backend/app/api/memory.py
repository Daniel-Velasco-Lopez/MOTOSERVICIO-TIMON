import structlog
from fastapi import APIRouter

from app.models.schemas import MemoryRetrieveRequest, MemoryRetrieveResponse

logger = structlog.get_logger()
router = APIRouter()


@router.post("/memory/retrieve", response_model=MemoryRetrieveResponse)
async def retrieve_memory(request: MemoryRetrieveRequest):
    logger.info(
        "memory_retrieve_requested",
        telefono=request.telefono,
        limite=request.limite,
    )
    # TODO: Fase 3 — conectar MemoryService + RAG
    return MemoryRetrieveResponse(success=True, episodica=[], semantica=[], total=0)
