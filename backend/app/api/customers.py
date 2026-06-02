import structlog
from fastapi import APIRouter, HTTPException

from app.models.schemas import CustomerProfile

logger = structlog.get_logger()
router = APIRouter()


@router.get("/customers/{telefono}", response_model=CustomerProfile)
async def get_customer(telefono: str):
    logger.info("customer_requested", telefono=telefono)
    # TODO: Fase 2 — conectar repositorio MySQL
    raise HTTPException(status_code=501, detail="CUSTOMER_SERVICE_NOT_IMPLEMENTED")
