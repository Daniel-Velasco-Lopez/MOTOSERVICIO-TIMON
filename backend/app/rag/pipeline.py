import logging
from typing import Optional

from app.rag.chunker import Chunker
from app.rag.reranker import rerank
from app.memory.working import session_manager
from app.services.gemini import gemini_service
from app.services.qdrant import qdrant_service

logger = logging.getLogger(__name__)


class RAGPipeline:
    def __init__(self, chunker: Chunker = None):
        self.chunker = chunker or Chunker()

    async def query(self, query_text: str, session_id: str = None, top_k: int = 3) -> str:
        results = []

        qdrant_results = await self._query_qdrant(query_text, top_k)
        if qdrant_results:
            results.extend(qdrant_results)

        session_results = await self._query_session(session_id, query_text)
        if session_results:
            results.extend(session_results)

        if not results:
            return ""

        if len(results) > top_k * 2:
            results = await rerank(query_text, results, top_k)

        return "\n\n".join(results[:top_k])

    async def index_message(self, session_id: str, mensaje: str, respuesta: str, telefono: str = None, metadata: dict = None):
        if not qdrant_service or not qdrant_service.client:
            return

        combined = f"Cliente: {mensaje}\nAsistente: {respuesta}"
        chunks = self.chunker.chunk_text(combined)

        for chunk in chunks:
            try:
                embedding = await gemini_service.embed(chunk)
                await qdrant_service.upsert(
                    collection="conversaciones",
                    point_id=f"{session_id}_{hash(chunk) % 100000}",
                    vector=embedding,
                    payload={
                        "text": chunk,
                        "session_id": session_id,
                        "telefono": telefono or "",
                        "timestamp": __import__("time").time(),
                        **(metadata or {}),
                    },
                )
            except Exception as e:
                logger.warning(f"Error indexing chunk: {e}")

    async def _query_qdrant(self, query_text: str, top_k: int) -> list[str]:
        if not qdrant_service or not qdrant_service.client:
            return []

        try:
            embedding = await gemini_service.embed(query_text)
            results = await qdrant_service.search(
                collection="conversaciones",
                vector=embedding,
                limit=top_k,
            )
            return [r.payload.get("text", "") for r in results if r.payload]
        except Exception as e:
            logger.warning(f"Qdrant query error: {e}")
            return []

    async def _query_session(self, session_id: str, query_text: str) -> list[str]:
        if not session_id:
            return []
        try:
            session = await session_manager.get_session(session_id)
            if not session:
                return []
            history = session.get("historial", [])
            if isinstance(history, str):
                import json
                history = json.loads(history)
            results = []
            for entry in history[-5:]:
                results.append(f"Cliente: {entry.get('mensaje', '')}")
                results.append(f"Asistente: {entry.get('respuesta', '')}")
            return results
        except Exception as e:
            logger.warning(f"Session query error: {e}")
            return []
