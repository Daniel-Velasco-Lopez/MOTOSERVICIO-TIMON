import json
import logging
from typing import Optional

from app.services.gemini import gemini_service

logger = logging.getLogger(__name__)

CLASSIFICATION_PROMPT = """Eres un clasificador de intenciones para un taller de motocicletas.
Analiza el mensaje del cliente y determina:
1. intencion_principal: una de [COTIZACION, AGENDAMIENTO, DIAGNOSTICO, QUEJA, INFORMACION, SALUDO, DESPEDIDA, OTRO]
2. confianza: 0.0 a 1.0
3. entidades: objeto con campos relevantes extraídos

Reglas:
- COTIZACION: el cliente pregunta precios, costos, cuánto cuesta
- AGENDAMIENTO: el cliente quiere agendar, apartar, reservar cita
- DIAGNOSTICO: describe fallas, ruidos, problemas, no enciende
- QUEJA: expresa inconformidad, queja, reclamo, mala experiencia
- INFORMACION: pregunta horarios, ubicación, servicios en general
- SALUDO: saludo inicial sin intención específica
- DESPEDIDA: se despide, termina conversación

Responde SOLO con JSON válido:
{
  "intencion_principal": "...",
  "confianza": 0.0,
  "entidades": {...}
}"""


async def classify_message(mensaje: str, history: list[dict] = None, fallback_key: str = None) -> dict:
    if not mensaje or not mensaje.strip():
        return _empty_classification("mensaje vacío")

    gemini_result = None
    if gemini_service and gemini_service.client:
        try:
            full_prompt = f"{CLASSIFICATION_PROMPT}\n\nMensaje del cliente: {mensaje}"
            if history:
                full_prompt += f"\n\nHistorial reciente: {str(history[-3:])}"
            raw = await gemini_service.generate(full_prompt, response_mime_type="application/json")
            if raw:
                import json
                gemini_result = json.loads(raw)
        except Exception as e:
            logger.warning(f"Gemini classification failed: {e}")

    if gemini_result and isinstance(gemini_result, dict) and gemini_result.get("intencion_principal"):
        return _normalize(gemini_result)

    return _rule_based_fallback(mensaje)


def _normalize(result: dict) -> dict:
    intent = result.get("intencion_principal", "").upper().strip()
    valid_intents = {"COTIZACION", "AGENDAMIENTO", "DIAGNOSTICO", "QUEJA", "INFORMACION", "SALUDO", "DESPEDIDA", "OTRO"}
    if intent not in valid_intents:
        intent = "OTRO"
    return {
        "intencion_principal": intent,
        "confianza": min(max(float(result.get("confianza", 0.5)), 0.0), 1.0),
        "entidades": result.get("entidades", {}),
        "raw": result,
    }


def _rule_based_fallback(mensaje: str) -> dict:
    msg_lower = mensaje.lower().strip()

    saludos = {"hola", "buenos días", "buenas tardes", "buenas noches", "qué tal", "hey", "buen día"}
    despedidas = {"gracias", "adiós", "chao", "bye", "hasta luego", "nos vemos", "que tenga buen día"}
    cotizacion_kw = {"cuánto cuesta", "precio", "cotización", "cuanto vale", "costo", "cuánto sale", "$"}
    agendamiento_kw = {"agendar", "cita", "apartar", "reserva", "horario", "puedo ir", "quiero llevar"}
    diagnostico_kw = {"falla", "problema", "ruido", "no enciende", "no prende", "descompuso", "daño", "fuga", "tronar"}
    queja_kw = {"queja", "mal servicio", "inconforme", "no me gustó", "pésimo", "deficiente"}
    informacion_kw = {"horario", "ubicación", "dirección", "dónde están", "teléfono", "abren", "cuándo abren"}

    for kw in saludos:
        if msg_lower.startswith(kw) or msg_lower == kw:
            return {"intencion_principal": "SALUDO", "confianza": 0.9, "entidades": {}}
    for kw in despedidas:
        if kw in msg_lower:
            return {"intencion_principal": "DESPEDIDA", "confianza": 0.9, "entidades": {}}
    for kw in cotizacion_kw:
        if kw in msg_lower:
            return {"intencion_principal": "COTIZACION", "confianza": 0.85, "entidades": _extract_entities(msg_lower)}
    for kw in queja_kw:
        if kw in msg_lower:
            return {"intencion_principal": "QUEJA", "confianza": 0.8, "entidades": {"descripcion": mensaje}}
    for kw in agendamiento_kw:
        if kw in msg_lower:
            return {"intencion_principal": "AGENDAMIENTO", "confianza": 0.85, "entidades": _extract_entities(msg_lower)}
    for kw in diagnostico_kw:
        if kw in msg_lower:
            return {"intencion_principal": "DIAGNOSTICO", "confianza": 0.8, "entidades": {"sintomas": mensaje}}
    for kw in informacion_kw:
        if kw in msg_lower:
            return {"intencion_principal": "INFORMACION", "confianza": 0.8, "entidades": {}}

    return {"intencion_principal": "OTRO", "confianza": 0.3, "entidades": {}}


def _extract_entities(text: str) -> dict:
    entities = {}
    motos = {"itálika", "vento", "honda", "yamaha", "suzuki", "bajaj", "hero", "akt"}
    for m in motos:
        if m in text:
            entities["moto"] = m.capitalize()
            break
    servicios = {"servicio", "mantenimiento", "afinación", "frenos", "llantas", "aceite", "cadena", "suspensión"}
    for s in servicios:
        if s in text:
            entities["servicio_solicitado"] = s.capitalize()
            break
    import re
    fecha_match = re.search(r'\b(\d{1,2} de \w+|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2})\b', text)
    if fecha_match:
        entities["fecha_mencionada"] = fecha_match.group(0)
    hora_match = re.search(r'\b(\d{1,2}:\d{2})\b', text)
    if hora_match:
        entities["hora_mencionada"] = hora_match.group(0)
    if "disponible" in text or "cupo" in text or "hay lugar" in text:
        entities["pregunta_disponibilidad"] = True
    return entities


def _empty_classification(reason: str) -> dict:
    return {"intencion_principal": "OTRO", "confianza": 0.0, "entidades": {}, "error": reason}
