import structlog
from fastapi import APIRouter

from app.models.schemas import AppointmentRequest, AppointmentResponse

logger = structlog.get_logger()
router = APIRouter()


@router.post("/appointments", response_model=AppointmentResponse)
async def create_appointment(request: AppointmentRequest):
    logger.info(
        "appointment_requested",
        cliente_id=request.cliente_id,
        servicio=request.servicio,
        fecha=request.fecha,
    )
    # TODO: Fase 2 — conectar tool agendar_cita
    return AppointmentResponse(
        success=False, error="Servicio no implementado", codigo_error="NOT_IMPLEMENTED"
    )
