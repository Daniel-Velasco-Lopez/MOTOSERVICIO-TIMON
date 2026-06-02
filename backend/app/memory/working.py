import json
import time
import structlog
from typing import Optional

from app.services.redis import redis_service
from app.config import settings

logger = structlog.get_logger()

SESSION_PREFIX = "session:"
RATELIMIT_PREFIX = "ratelimit:"


class SessionManager:
    async def get_session(self, telefono: str) -> Optional[dict]:
        data = await redis_service.get(f"{SESSION_PREFIX}{telefono}")
        if data:
            session = json.loads(data)
            await redis_service.expire(f"{SESSION_PREFIX}{telefono}", settings.redis_session_ttl)
            return session
        return None

    async def create_session(self, telefono: str, initial_data: Optional[dict] = None) -> dict:
        session = {
            "telefono": telefono,
            "estado": "NUEVA_CONSULTA",
            "ultimo_tema": None,
            "intencion_actual": None,
            "intenciones_pendientes": [],
            "entidades_extraidas": {},
            "resultados_herramientas": {},
            "plan": None,
            "mensajes_en_sesion": 0,
            "iniciada": int(time.time()),
            "ultima_interaccion": int(time.time()),
        }
        if initial_data:
            session.update(initial_data)
        await redis_service.set(
            f"{SESSION_PREFIX}{telefono}",
            json.dumps(session),
            ttl=settings.redis_session_ttl,
        )
        return session

    async def update_session(self, telefono: str, updates: dict):
        existing = await self.get_session(telefono)
        if not existing:
            existing = await self.create_session(telefono)
        existing.update(updates)
        existing["ultima_interaccion"] = int(time.time())
        await redis_service.set(
            f"{SESSION_PREFIX}{telefono}",
            json.dumps(existing),
            ttl=settings.redis_session_ttl,
        )

    async def delete_session(self, telefono: str):
        await redis_service.delete(f"{SESSION_PREFIX}{telefono}")

    async def session_exists(self, telefono: str) -> bool:
        return await redis_service.get(f"{SESSION_PREFIX}{telefono}") is not None


class RateLimiter:
    async def check(self, telefono: str) -> Optional[str]:
        key = f"{RATELIMIT_PREFIX}{telefono}"
        count = await redis_service.incr(key)
        if count == 1:
            await redis_service.set_ttl(key, settings.rate_limit_window_seconds)
        if count > settings.rate_limit_max_requests:
            logger.warning("rate_limit_exceeded", telefono=telefono, count=count)
            return "Rate limit excedido. Intenta de nuevo en unos momentos."
        return None

    async def reset(self, telefono: str):
        await redis_service.delete(f"{RATELIMIT_PREFIX}{telefono}")


session_manager = SessionManager()
rate_limiter = RateLimiter()
