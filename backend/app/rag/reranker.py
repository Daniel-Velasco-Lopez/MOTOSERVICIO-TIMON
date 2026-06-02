import logging
from typing import Optional

from app.services.gemini import gemini_service

logger = logging.getLogger(__name__)


RE_RANK_PROMPT = """Dada la consulta del cliente y una lista de fragmentos de información, selecciona y ordena los fragmentos más relevantes.

Consulta del cliente: {query}

Fragmentos:
{chunks}

Instrucciones:
1. Evalúa qué fragmentos son más relevantes para responder la consulta
2. Reordena por relevancia (más relevante primero)
3. Ignora fragmentos irrelevantes

Responde SOLO con JSON:
{
  "indices_relevantes": [0, 2, ...],
  "razonamiento": "breve explicación"
}"""


async def rerank(query: str, chunks: list[str], top_k: int = 3) -> list[str]:
    if not chunks:
        return []
    if len(chunks) <= top_k:
        return chunks

    gemini_result = None
    if gemini_service and gemini_service.client:
        try:
            formatted = "\n".join(f"[{i}] {c[:200]}" for i, c in enumerate(chunks))
            prompt = RE_RANK_PROMPT.format(query=query, chunks=formatted)
            raw = await gemini_service.generate(prompt, response_mime_type="application/json")
            if raw:
                import json
                result = json.loads(raw)
                indices = result.get("indices_relevantes", [])
                if indices:
                    return [chunks[i] for i in indices[:top_k] if i < len(chunks)]
        except Exception as e:
            logger.warning(f"Gemini rerank failed: {e}")

    return chunks[:top_k]
