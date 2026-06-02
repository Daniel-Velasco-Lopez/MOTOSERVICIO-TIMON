import json
import structlog
from typing import Optional, Callable
from aio_pika import connect_robust, Message, DeliveryMode, ExchangeType
from aio_pika.abc import AbstractRobustConnection, AbstractChannel, AbstractExchange

from app.config import settings

logger = structlog.get_logger()


class RabbitMQService:
    def __init__(self):
        self.connection: Optional[AbstractRobustConnection] = None
        self.channel: Optional[AbstractChannel] = None
        self.exchanges: dict[str, AbstractExchange] = {}

    async def connect(self):
        self.connection = await connect_robust(
            host=settings.rabbitmq_host,
            port=settings.rabbitmq_port,
            login=settings.rabbitmq_user,
            password=settings.rabbitmq_password,
        )
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=10)
        logger.info("rabbitmq_connected", host=settings.rabbitmq_host)

    async def declare_exchange(self, name: str, exchange_type: str = "direct"):
        exchange = await self.channel.declare_exchange(
            name=name,
            type=ExchangeType(exchange_type),
            durable=True,
        )
        self.exchanges[name] = exchange
        return exchange

    async def declare_queue(self, name: str, exchange: str, routing_key: str):
        queue = await self.channel.declare_queue(name=name, durable=True)
        await queue.bind(
            exchange=self.exchanges[exchange],
            routing_key=routing_key,
        )
        return queue

    async def publish(self, exchange: str, routing_key: str, payload: dict, delay_ms: int = 0):
        message = Message(
            body=json.dumps(payload).encode(),
            delivery_mode=DeliveryMode.PERSISTENT,
        )
        if exchange in self.exchanges:
            await self.exchanges[exchange].publish(
                message=message,
                routing_key=routing_key,
            )

    async def consume(self, queue_name: str, callback: Callable):
        queue = await self.channel.declare_queue(name=queue_name, durable=True)
        await queue.consume(callback)

    async def disconnect(self):
        if self.connection:
            await self.connection.close()
            logger.info("rabbitmq_disconnected")


rabbitmq_service = RabbitMQService()
