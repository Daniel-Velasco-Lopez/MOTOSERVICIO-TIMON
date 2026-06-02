import structlog
from fastapi import APIRouter
from pydantic import BaseModel

logger = structlog.get_logger()
router = APIRouter()


class RAGRefreshResponse(BaseModel):
    success: bool
    mensaje: str


@router.post("/rag/refresh", response_model=RAGRefreshResponse)
async def refresh_rag():
    logger.info("rag_refresh_requested")
    # TODO: Fase 3 — conectar pipeline de ingestión RAG
    return RAGRefreshResponse(
        success=False, mensaje="RAG refresh no implementado"
    )


@router.get("/logs", response_model=dict)
async def get_logs(limit: int = 50, nivel: str = "INFO"):
    logger.info("logs_requested", limit=limit, nivel=nivel)
    # TODO: Fase 4 — conectar logs desde MySQL
    return {"logs": [], "total": 0}
