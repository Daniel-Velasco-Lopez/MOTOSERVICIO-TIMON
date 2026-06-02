import json
import logging
from typing import Optional

from app.services.gemini import gemini_service

logger = logging.getLogger(__name__)


PLANNER_PROMPT = """Eres el planificador del agente de MotoServicio Timón.
Dado el contexto actual (intención, herramientas disponibles, historial), genera un plan de acción.

Formato de respuesta:
{
  "plan": [
    {"step": 1, "action": "tool_call", "tool": "nombre_tool", "params": {...}},
    {"step": 2, "action": "ask_clarification", "question": "..."},
    {"step": 3, "action": "respond", "message": "..."}
  ],
  "razonamiento": "breve explicación del plan"
}

Acciones disponibles:
- tool_call: ejecutar una herramienta del sistema
- ask_clarification: pedir más información al cliente
- respond: dar respuesta directa sin ejecutar herramientas
- wait: esperar respuesta del cliente"""


class Planner:
    def __init__(self):
        self.current_plan: list[dict] = []
        self.current_step = 0

    async def generate_plan(self, context: dict) -> list[dict]:
        goals = context.get("goals", [])
        classification = context.get("classification", {})
        active_goals = [g for g in goals if g.get("status") in ("ACTIVE", "CREATED")]

        if not active_goals:
            return await self._generate_freeform_plan(context)

        return await self._generate_goal_plan(active_goals, context)

    async def _generate_goal_plan(self, goals: list[dict], context: dict) -> list[dict]:
        plan = []
        step = 1
        for goal in goals:
            goal_type = goal["goal_type"]
            inp = goal.get("input", {})

            if goal_type == "REGISTRAR_CLIENTE":
                plan.append({"step": step, "action": "tool_call", "tool": "registrar_cliente", "params": {"telefono": inp.get("telefono", context.get("telefono", "")), "nombre": inp.get("nombre", "")}})
                step += 1

            elif goal_type == "COTIZAR_SERVICIO":
                if inp.get("servicio"):
                    plan.append({"step": step, "action": "tool_call", "tool": "cotizar_servicio", "params": {"servicio": inp["servicio"]}})
                    step += 1
                else:
                    plan.append({"step": step, "action": "ask_clarification", "question": "¿Qué servicio te gustaría cotizar?"})
                    step += 1

            elif goal_type == "CONSULTAR_DISPONIBILIDAD":
                plan.append({"step": step, "action": "tool_call", "tool": "consultar_disponibilidad", "params": {"fecha": inp.get("fecha", "hoy")}})
                step += 1

            elif goal_type == "AGENDAR_CITA":
                plan.append({"step": step, "action": "tool_call", "tool": "agendar_cita", "params": {"telefono": inp.get("telefono", context.get("telefono", "")), "servicio": inp.get("servicio", ""), "fecha": inp.get("fecha", ""), "hora": inp.get("hora", "")}})
                step += 1

            elif goal_type == "RESOLVER_QUEJA":
                plan.append({"step": step, "action": "tool_call", "tool": "registrar_queja", "params": {"telefono": inp.get("telefono", context.get("telefono", "")), "descripcion": inp.get("descripcion", ""), "urgencia": inp.get("urgencia", "media")}})
                step += 1

            elif goal_type == "DIAGNOSTICAR_FALLA":
                if inp.get("sintomas"):
                    plan.append({"step": step, "action": "tool_call", "tool": "diagnosticar_falla", "params": {"sintomas": inp["sintomas"]}})
                    step += 1
                else:
                    plan.append({"step": step, "action": "ask_clarification", "question": "¿Qué síntomas presenta tu moto?"})
                    step += 1

        return plan

    async def _generate_freeform_plan(self, context: dict) -> list[dict]:
        plan = []
        intent = context.get("classification", {}).get("intencion_principal", "OTRO")

        if intent == "SALUDO":
            plan.append({"step": 1, "action": "respond", "message": "¡Hola! Soy el asistente virtual de MotoServicio Timón. ¿En qué puedo ayudarte? Puedo cotizar servicios, agendar citas, diagnosticar fallas o atender quejas."})
        elif intent == "DESPEDIDA":
            plan.append({"step": 1, "action": "respond", "message": "¡Gracias por contactarnos! Que tengas un excelente día. 🏍️"})
        elif intent == "INFORMACION":
            plan.append({"step": 1, "action": "respond", "message": "Estamos en [dirección]. Nuestro horario es lunes a viernes de 9am a 6pm, sábados de 9am a 2pm. ¿Te gustaría cotizar algún servicio o agendar una cita?"})
        else:
            plan.append({"step": 1, "action": "respond", "message": "No estoy seguro de cómo ayudarte con eso. Puedo cotizar servicios, agendar citas, diagnosticar fallas o atender quejas. ¿Qué necesitas?"})

        return plan

    def get_current_action(self) -> Optional[dict]:
        if self.current_plan and self.current_step < len(self.current_plan):
            return self.current_plan[self.current_step]
        return None

    def advance(self) -> bool:
        self.current_step += 1
        return self.current_step < len(self.current_plan)

    def reset(self):
        self.current_plan = []
        self.current_step = 0
