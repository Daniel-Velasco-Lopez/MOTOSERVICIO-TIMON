import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.config import settings
from app.services.redis import redis_service
from app.services.gemini import gemini_service
from app.services.qdrant import qdrant_service
from app.api.messages import router as messages_router
from app.api.customers import router as customers_router
from app.api.appointments import router as appointments_router
from app.api.memory import router as memory_router
from app.api.tools import router as tools_router
from app.api.admin import router as admin_router
from app.models.schemas import ErrorResponse

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting_up", app=settings.app_name, version=settings.app_version)
    services = [
        ("redis", redis_service.connect),
        ("gemini", gemini_service.connect),
        ("qdrant", qdrant_service.connect),
    ]
    for name, connect_fn in services:
        try:
            await connect_fn()
            logger.info("service_connected", service=name)
        except Exception as e:
            logger.warning("service_connect_failed", service=name, error=str(e))
    yield
    await redis_service.disconnect()
    logger.info("shutting_down")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)


app.include_router(messages_router, prefix="/api/v1", tags=["messages"])
app.include_router(customers_router, prefix="/api/v1", tags=["customers"])
app.include_router(appointments_router, prefix="/api/v1", tags=["appointments"])
app.include_router(memory_router, prefix="/api/v1", tags=["memory"])
app.include_router(tools_router, prefix="/api/v1", tags=["tools"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    error_map = {
        "INVALID_PHONE": (400, "Número de teléfono inválido"),
        "EMPTY_MESSAGE": (400, "Mensaje vacío"),
        "MSG_TOO_LONG": (400, "Mensaje demasiado largo (máx 4096 caracteres)"),
    }
    code, msg = error_map.get(str(exc), (400, str(exc)))
    return JSONResponse(
        status_code=code,
        content=ErrorResponse(codigo=str(exc), mensaje=msg).model_dump(),
    )


@app.exception_handler(Exception)
async def general_error_handler(request: Request, exc: Exception):
    logger.error("unhandled_error", error=str(exc), path=str(request.url))
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            codigo="INTERNAL_ERROR", mensaje="Error interno del servidor"
        ).model_dump(),
    )
