from tasks.celery_app import celery_app


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def process_embeddings(self, payload: dict):
    # TODO: Fase 3 — generar embedding y upsert a Qdrant
    telefono = payload.get("telefono")
    mensaje = payload.get("mensaje")
    conversacion_id = payload.get("conversacion_id")

    if not all([telefono, mensaje, conversacion_id]):
        raise ValueError("payload incompleto")

    return {
        "status": "pending",
        "telefono": telefono,
        "conversacion_id": conversacion_id,
    }
