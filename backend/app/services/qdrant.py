import structlog
from typing import Optional
from qdrant_client import QdrantClient as SyncQdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

from app.config import settings

logger = structlog.get_logger()


class QdrantService:
    def __init__(self):
        self.client: Optional[SyncQdrantClient] = None

    async def connect(self):
        self.client = SyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )
        await self._ensure_collections()
        logger.info("qdrant_connected", host=settings.qdrant_host, port=settings.qdrant_port)

    async def _ensure_collections(self):
        collections = [c.name for c in self.client.get_collections().collections]

        if settings.qdrant_conversaciones_collection not in collections:
            self.client.create_collection(
                collection_name=settings.qdrant_conversaciones_collection,
                vectors_config=models.VectorParams(
                    size=settings.qdrant_vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info("qdrant_collection_created", collection=settings.qdrant_conversaciones_collection)

        if settings.qdrant_conocimiento_collection not in collections:
            self.client.create_collection(
                collection_name=settings.qdrant_conocimiento_collection,
                vectors_config=models.VectorParams(
                    size=settings.qdrant_vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info("qdrant_collection_created", collection=settings.qdrant_conocimiento_collection)

    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
        score_threshold: Optional[float] = None,
        query_filter: Optional[Filter] = None,
        with_payload: bool = True,
    ) -> list[models.ScoredPoint]:
        if not self.client:
            raise RuntimeError("Qdrant no conectado")

        kwargs = dict(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit,
            with_payload=with_payload,
        )
        if score_threshold is not None:
            kwargs["score_threshold"] = score_threshold
        if query_filter is not None:
            kwargs["query_filter"] = query_filter

        return self.client.search(**kwargs)

    async def upsert(self, collection_name: str, points: list[models.PointStruct]):
        if not self.client:
            raise RuntimeError("Qdrant no conectado")
        self.client.upsert(collection_name=collection_name, points=points)

    async def delete_points(self, collection_name: str, point_ids: list[str]):
        if not self.client:
            raise RuntimeError("Qdrant no conectado")
        self.client.delete(
            collection_name=collection_name,
            points_selector=models.PointIdsList(points=point_ids),
        )


qdrant_service = QdrantService()
