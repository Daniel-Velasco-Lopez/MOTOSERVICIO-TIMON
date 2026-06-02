import logging
from typing import Optional

from app.services.gemini import gemini_service

logger = logging.getLogger(__name__)


SUMMARIZER_PROMPT = """Resume la siguiente conversación entre un cliente y el asistente de MotoServicio Timón (taller de motos).

Mensajes:
{history}

El resumen debe:
1. Capturar la intención principal del cliente
2. Mencionar servicios cotizados o citas agendadas
3. Incluir información relevante del cliente (moto, falla, queja)
4. Ser conciso (máximo 3 oraciones)"""


async def summarize_conversation(history: list[dict]) -> str:
    if not history:
        return ""
    if len(history) <= 2:
        return _simple_summary(history)

    gemini_summary = None
    if gemini_service and gemini_service.client:
        try:
            formatted = "\n".join(f"Cliente: {h['mensaje']}\nAsistente: {h['respuesta']}" for h in history[-10:])
            prompt = SUMMARIZER_PROMPT.format(history=formatted)
            gemini_summary = await gemini_service.generate(prompt)
        except Exception as e:
            logger.warning(f"Gemini summarization failed: {e}")

    if gemini_summary and len(gemini_summary) > 20:
        return gemini_summary
    return _simple_summary(history)


def _simple_summary(history: list[dict]) -> str:
    if not history:
        return ""
    last = history[-1]
    intent = last.get("classification", {}).get("intencion_principal", "consulta")
    return f"Cliente hizo {intent.lower()}: \"{last.get('mensaje', '')[:100]}\". Se respondió con información relevante."
