import json
import structlog
from typing import Optional
from redis.asyncio import Redis as AsyncRedis

from app.config import settings

logger = structlog.get_logger()


class RedisService:
    def __init__(self):
        self.client: Optional[AsyncRedis] = None

    async def connect(self):
        self.client = AsyncRedis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True,
        )
        await self.client.ping()
        logger.info("redis_connected", host=settings.redis_host, port=settings.redis_port)

    async def disconnect(self):
        if self.client:
            await self.client.aclose()
            logger.info("redis_disconnected")

    async def get(self, key: str) -> Optional[str]:
        return await self.client.get(key)

    async def set(self, key: str, value: str, ttl: Optional[int] = None):
        if ttl:
            await self.client.setex(key, ttl, value)
        else:
            await self.client.set(key, value)

    async def delete(self, key: str):
        await self.client.delete(key)

    async def expire(self, key: str, ttl: int):
        await self.client.expire(key, ttl)

    async def incr(self, key: str) -> int:
        return await self.client.incr(key)

    async def set_ttl(self, key: str, ttl: int):
        await self.client.expire(key, ttl)


redis_service = RedisService()
