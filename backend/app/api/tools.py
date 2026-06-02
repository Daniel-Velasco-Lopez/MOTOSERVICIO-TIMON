import structlog
from fastapi import APIRouter

from app.models.schemas import ToolExecuteRequest, ToolExecuteResponse

logger = structlog.get_logger()
router = APIRouter()


@router.post("/tools/execute", response_model=ToolExecuteResponse)
async def execute_tool(request: ToolExecuteRequest):
    logger.info(
        "tool_execution_requested",
        tool=request.tool,
        parametros=request.parametros,
    )
    # TODO: Fase 2 — conectar ToolExecutor
    return ToolExecuteResponse(
        success=False,
        tool=request.tool,
        error=f"Tool '{request.tool}' no implementada",
    )
