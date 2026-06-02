from celery import Celery
from app.config import settings

celery_app = Celery(
    "motoservicio",
    broker=settings.celery_broker_url,
    include=["tasks.embeddings"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Mexico_City",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
