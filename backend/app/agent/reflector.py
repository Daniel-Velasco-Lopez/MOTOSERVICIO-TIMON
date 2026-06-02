import json
import logging
from typing import Optional

from app.services.gemini import gemini_service

logger = logging.getLogger(__name__)


REFLECTION_PROMPT = """Eres un validador de calidad para el asistente de MotoServicio Timón.
Evalúa la respuesta generada y determina si es adecuada.

Contexto:
- Intención del cliente: {intencion}
- Mensaje del cliente: {mensaje_cliente}
- Respuesta generada: {respuesta}
- Resultados de herramientas: {tool_results}

Criterios de evaluación:
1. RELEVANCIA: ¿La respuesta aborda la intención del cliente?
2. COMPLETITUD: ¿Incluye toda la información necesaria?
3. TONO: ¿Es profesional y empático?
4. ACCIÓN: ¿Invita al siguiente paso (agendar, preguntar más, etc.)?

Responde SOLO con JSON:
{
  "valida": true/false,
  "puntaje": 0-100,
  "problemas": ["lista de problemas encontrados"],
  "sugerencia": "cómo mejorar la respuesta"
}"""


class Reflector:
    def __init__(self):
        self.threshold = 60

    async def validate(self, context: dict, response_text: str) -> dict:
        if not response_text or len(response_text.strip()) < 5:
            return {"valida": False, "puntaje": 0, "problemas": ["respuesta vacía o demasiado corta"], "sugerencia": "generar una respuesta más completa"}

        gemini_result = None
        if gemini_service and gemini_service.client:
            try:
                prompt = REFLECTION_PROMPT.format(
                    intencion=context.get("classification", {}).get("intencion_principal", "OTRO"),
                    mensaje_cliente=context.get("mensaje", ""),
                    respuesta=response_text,
                    tool_results=json.dumps(context.get("tool_results", {}), ensure_ascii=False),
                )
                raw = await gemini_service.generate(f"{prompt}\n\nRespuesta a evaluar: {response_text}", response_mime_type="application/json")
                if raw:
                    import json as json2
                    gemini_result = json2.loads(raw)
            except Exception as e:
                logger.warning(f"Gemini reflection failed: {e}")

        if gemini_result and isinstance(gemini_result, dict):
            result = {
                "valida": gemini_result.get("valida", True),
                "puntaje": int(gemini_result.get("puntaje", 80)),
                "problemas": gemini_result.get("problemas", []),
                "sugerencia": gemini_result.get("sugerencia", ""),
            }
        else:
            result = self._rule_based_validate(context, response_text)

        result["valida"] = result.get("puntaje", 0) >= self.threshold
        return result

    def _rule_based_validate(self, context: dict, response_text: str) -> dict:
        problemas = []
        puntaje = 100
        intent = context.get("classification", {}).get("intencion_principal", "OTRO")
        text_lower = response_text.lower()

        if len(response_text) < 20:
            problemas.append("respuesta muy corta")
            puntaje -= 30
        if len(response_text) > 1500:
            problemas.append("respuesta demasiado larga")
            puntaje -= 10
        if intent == "COTIZACION" and "$" not in response_text and "precio" not in text_lower:
            problemas.append("no incluye información de precio para cotización")
            puntaje -= 25
        if intent == "AGENDAMIENTO" and ("cuando" in text_lower or "fecha" in text_lower or "horario" not in text_lower):
            if "confirmad" not in text_lower and "agendad" not in text_lower:
                problemas.append("no hay confirmación de cita")
                puntaje -= 15
        if intent in ("QUEJA", "DIAGNOSTICO") and "?" not in response_text and "?" not in response_text:
            problemas.append("no invita al siguiente paso")
            puntaje -= 10
        if "como asistente" in text_lower or "como ia" in text_lower:
            problemas.append("usa auto-referencia como IA")
            puntaje -= 20

        return {
            "valida": puntaje >= self.threshold,
            "puntaje": max(0, puntaje),
            "problemas": problemas,
            "sugerencia": "revisar los problemas identificados" if problemas else "respuesta válida",
        }

    async def improve(self, context: dict, original: str, problemas: list[str]) -> str:
        if not problemas:
            return original

        if gemini_service:
            try:
                prompt = f"""Mejora la siguiente respuesta para el asistente de MotoServicio Timón.
Problemas identificados: {', '.join(problemas)}

Respuesta original: {original}

Genera una versión mejorada que resuelva estos problemas."""
                improved = await gemini_service.generate(original, system_instruction=prompt)
                if improved and len(improved) > 10:
                    return improved
            except Exception as e:
                logger.warning(f"Gemini improvement failed: {e}")

        return original
