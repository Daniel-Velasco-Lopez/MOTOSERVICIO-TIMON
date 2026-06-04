import json
import logging
from typing import Optional

from app.services.gemini import gemini_service
from app.agent.prompt_orchestrator import PromptOrchestrator

logger = logging.getLogger(__name__)


RESPONSE_PROMPT = """Eres el asistente virtual de MotoServicio Timón, un taller de motocicletas.
Debes responder de forma natural, empática y profesional.

Contexto actual:
- Intención: {intencion}
- Goals activos: {goals_context}
- Resultado de herramientas: {tool_results}
- Mensaje del cliente: {mensaje}

Directrices:
1. Si la herramienta devolvió datos, PRESÉNTALOS de forma clara y amigable
2. Si no hay datos, haz una pregunta para obtener la información necesaria
3. Usa emojis relacionados con motos 🏍️🔧 ocasionalmente, no en exceso
4. Sé conciso pero completo
5. NUNCA digas "como asistente virtual" o "como IA"
6. Si es cotización, muestra el precio y pregunta si desea agendar
7. Si es agendamiento, confirma la fecha y ofrece opciones
8. Si es queja, muestra empatía y asegura que se resolverá
9. Si es diagnóstico, da la posible causa y recomienda acción

Responde SOLO con el texto del mensaje, sin metadatos adicionales."""


class Generator:
    def __init__(self, prompt_builder: Optional[PromptOrchestrator] = None):
        self.prompt_builder = prompt_builder

    async def generate_response(self, context: dict) -> str:
        classification = context.get("classification", {})
        intent = classification.get("intencion_principal", "OTRO")
        tool_results = context.get("tool_results", {})
        mensaje = context.get("mensaje", "")
        goals_context = context.get("goals_context", "")

        gemini_response = None
        if gemini_service:
            try:
                if self.prompt_builder:
                    prompt = self.prompt_builder.build_system_prompt(context)
                else:
                    prompt = RESPONSE_PROMPT.format(
                        intencion=intent,
                        goals_context=goals_context or "ninguno",
                        tool_results=json.dumps(tool_results, ensure_ascii=False, indent=2) if tool_results else "ninguno",
                        mensaje=mensaje,
                    )
                gemini_response = await gemini_service.generate(mensaje, system_instruction=prompt)
            except Exception as e:
                logger.warning(f"Gemini generation failed: {e}")

        if gemini_response and isinstance(gemini_response, str) and len(gemini_response) > 10:
            return gemini_response

        return self._fallback_generate(context)

    def _fallback_generate(self, context: dict) -> str:
        classification = context.get("classification", {})
        intent = classification.get("intencion_principal", "OTRO")
        tool_results = context.get("tool_results", {})

        if not tool_results:
            mensaje = context.get("mensaje", "")
            return self._no_tool_response(intent, mensaje)

        tool_data = list(tool_results.values())[0] if tool_results else {}
        if not tool_data.get("success"):
            error = tool_data.get("error", "ocurrió un error")
            return f"Lo siento, {error}. ¿Podrías intentarlo de nuevo o prefieres que te ayude con otra cosa?"

        data = tool_data.get("data", {})
        return self._format_tool_result(intent, data)

    def _no_tool_response(self, intent: str, mensaje: str = "") -> str:
        responses = {
            "SALUDO": "¡Hola! 🏍️ Bienvenido a MotoServicio Timón. Estamos en Benito Juárez #123, Col. Centro. Horario: Lun-Vie 9:00-18:00, Sáb 9:00-14:00. ¿En qué puedo ayudarte?",
            "DESPEDIDA": "¡Gracias por contactarnos! Que tengas un excelente día. No dudes en escribirnos si necesitas algo más 🏍️",
            "COTIZACION": "Claro, puedo ayudarte con una cotización. ¿Qué servicio te gustaría cotizar? Tenemos varios como cambio de aceite, afinación, frenos, llantas, baterías, kit de transmisión, suspensión, entre otros.",
            "AGENDAMIENTO": "Con gusto te ayudo a agendar una cita. ¿Qué servicio necesitas y para qué día te gustaría agendar?",
            "DIAGNOSTICO": "Cuéntame más sobre el problema que presenta tu moto. ¿Qué síntomas has notado?",
            "QUEJA": "Lamento mucho que hayas tenido una mala experiencia. Voy a registrar tu reporte para que lo revisen. ¿Me puedes dar más detalles de lo que pasó?",
            "INFORMACION": """🏍️ *MotoServicio Timón* 🏍️

📍 *Ubicación:* Benito Juárez #123, Col. Centro
🕐 *Horario:* Lun-Vie 9:00-18:00, Sáb 9:00-14:00

*Servicios disponibles:*
• Cambio de aceite + filtro: $350-$550
• Afinación menor (hasta 250cc): $350-$530
• Afinación mayor (250cc+): $530-$800
• Servicio general 4T: $530-$800
• Frenos (balatas): $200-$400 c/u
• Llantas: desde $800 c/u + instalación
• Baterías: desde $500
• Kit de transmisión (cadena/sprockets): $600-$1,500
• Suspensión (horquillas/amortiguadores): $500-$1,200
• Diagnóstico por escáner: $200-$400
• Revisión de sistema eléctrico
• Servicio mayor (10,000-20,000km): consultar

Trabajamos TODAS las marcas (Honda, Yamaha, Suzuki, Kawasaki, BMW, Ducati, KTM, Italika, Bajaj, Vento). ¿Cuál te interesa o qué servicio necesitas?""",
        }

        if intent == "INFORMACION" and mensaje:
            msg_lower = mensaje.lower()
            if "horario" in msg_lower or "abren" in msg_lower or "cierran" in msg_lower:
                return "🕐 Horario: Lun-Vie 9:00-18:00, Sáb 9:00-14:00. Domingo cerrado."
            if "dónde" in msg_lower or "donde" in msg_lower or "ubicación" in msg_lower or "ubicacion" in msg_lower or "dirección" in msg_lower or "direccion" in msg_lower:
                return "📍 Estamos en Benito Juárez #123, Col. Centro."

        return responses.get(intent, "¿En qué puedo ayudarte? Puedo cotizar servicios, agendar citas o ayudarte con un diagnóstico.")

    def _format_tool_result(self, intent: str, data: dict) -> str:
        if intent == "COTIZACION":
            precios = data.get("precios", [])
            if precios:
                lines = [f"💰 *{p['servicio']}*: ${float(p.get('precio_min', 0)):.2f} - ${float(p.get('precio_max', 0)):.2f}" for p in precios]
                lines.append("\n¿Te gustaría agendar una cita para este servicio?")
                return "\n".join(lines)
            sugerencias = data.get("sugerencias", [])
            if sugerencias:
                return f"No encontré exactamente ese servicio. Estos son los disponibles:\n" + "\n".join(f"- {s}" for s in sugerencias)
            return data.get("mensaje", "No encontré información sobre ese servicio.")

        elif intent == "AGENDAMIENTO":
            horarios = data.get("horarios", [])
            cita_id = data.get("cita_id")
            if cita_id:
                return f"✅ ¡Cita agendada exitosamente! El {data.get('fecha', '')} para {data.get('servicio', '')}. Te esperamos 🏍️"
            if not horarios:
                return "Lo siento, no hay horarios disponibles para esa fecha. ¿Te gustaría intentar con otra fecha?"
            horas_str = ", ".join(horarios[:5])
            return f"Estos son los horarios disponibles:\n{horas_str}\n\n¿Cuál prefieres?"

        elif intent == "QUEJA":
            ticket = data.get("ticket", "")
            if ticket:
                return f"He registrado tu queja con el folio *{ticket}*. Te contactaremos pronto para resolverlo. Lamento las molestias."
            return "Tu queja ha sido registrada. Te contactaremos pronto."

        elif intent == "DIAGNOSTICO":
            gemini_diag = data.get("diagnostico_gemini")
            if gemini_diag:
                return f"Basado en los síntomas que me describes:\n\n{gemini_diag}\n\n¿Te gustaría agendar una revisión para confirmar?"
            fallas = data.get("fallas_bd", [])
            if fallas:
                f = fallas[0]
                return f"Posible causa: {f.get('causa', '')}\nSolución sugerida: {f.get('solucion', '')}\n\n¿Te gustaría agendar una cita para revisarlo?"
            if data.get("requiere_revision"):
                return "Por los síntomas que mencionas, recomiendo que un mecánico revise la moto. ¿Te gustaría agendar una cita?"
            return data.get("mensaje", "Gracias por la información.")

        elif intent == "INFORMACION":
            servicios = data.get("servicios", [])
            if servicios:
                lines = ["🏍️ *Servicios disponibles:*"]
                for s in servicios:
                    precio = f"${float(s.get('precio', 0)):.2f}" if s.get("precio") else "consultar"
                    lines.append(f"• {s.get('nombre', '')}: {precio}")
                lines.append("\n¿Cuál te interesa?")
                return "\n".join(lines)
            return self._no_tool_response("INFORMACION")

        return "Gracias. ¿Hay algo más en lo que pueda ayudarte? Puedo cotizar servicios, agendar citas o ayudarte con un diagnóstico."
