import time
import json
from uuid import uuid4
from typing import Optional


class ObjectiveTracker:
    def __init__(self):
        self.goals: list[dict] = []
        self.changed = False

    def load(self, goals: list[dict]):
        self.goals = goals or []
        self.changed = False

    def detect_from_classification(self, classification: dict, telefono: str, nombre: Optional[str] = None) -> list[dict]:
        intent = classification.get("intencion_principal", "")
        entities = classification.get("entidades", {})
        new_goals = []

        needs_registration = True
        for g in self.goals:
            if g["goal_type"] == "REGISTRAR_CLIENTE" and g["status"] == "COMPLETED":
                needs_registration = False
                break

        if intent in ("COTIZACION", "AGENDAMIENTO", "QUEJA", "DIAGNOSTICO", "INFORMACION"):
            if needs_registration:
                g = self._create_goal("REGISTRAR_CLIENTE", priority=1,
                    input={"telefono": telefono, "nombre": nombre or ""})
                new_goals.append(g)
                reg_id = g["goal_id"]
            else:
                reg_id = None

            if intent == "COTIZACION":
                g2 = self._create_goal("COTIZAR_SERVICIO", priority=2,
                    input={
                        "servicio": entities.get("servicio_solicitado", ""),
                        "moto": entities.get("moto", ""),
                    },
                    dependencies=[reg_id] if reg_id else [])
                new_goals.append(g2)
                if entities.get("pregunta_disponibilidad"):
                    g3 = self._create_goal("CONSULTAR_DISPONIBILIDAD", priority=3,
                        input={
                            "fecha": entities.get("fecha_mencionada", "hoy"),
                            "servicio": entities.get("servicio_solicitado", ""),
                        },
                        dependencies=[g2["goal_id"]])
                    new_goals.append(g3)
                    g4 = self._create_goal("AGENDAR_CITA", priority=4,
                        input={
                            "servicio": entities.get("servicio_solicitado", ""),
                            "moto": entities.get("moto", ""),
                            "fecha": entities.get("fecha_mencionada", ""),
                        },
                        dependencies=[g3["goal_id"]])
                    new_goals.append(g4)

            elif intent == "AGENDAMIENTO":
                g2 = self._create_goal("CONSULTAR_DISPONIBILIDAD", priority=2,
                    input={
                        "fecha": entities.get("fecha_mencionada", "hoy"),
                        "servicio": entities.get("servicio_solicitado", ""),
                    },
                    dependencies=[reg_id] if reg_id else [])
                new_goals.append(g2)
                g3 = self._create_goal("AGENDAR_CITA", priority=3,
                    input={
                        "servicio": entities.get("servicio_solicitado", ""),
                        "moto": entities.get("moto", ""),
                        "fecha": entities.get("fecha_mencionada", ""),
                        "hora": entities.get("hora_mencionada", ""),
                    },
                    dependencies=[g2["goal_id"]])
                new_goals.append(g3)

            elif intent == "QUEJA":
                g2 = self._create_goal("RESOLVER_QUEJA", priority=2,
                    input={
                        "descripcion": entities.get("descripcion", ""),
                        "urgencia": entities.get("urgencia", "media"),
                    },
                    dependencies=[reg_id] if reg_id else [])
                new_goals.append(g2)

            elif intent == "DIAGNOSTICO":
                g2 = self._create_goal("DIAGNOSTICAR_FALLA", priority=2,
                    input={
                        "sintomas": entities.get("sintomas", ""),
                        "moto": entities.get("moto", ""),
                    })
                new_goals.append(g2)

        self.goals.extend(new_goals)
        self.changed = bool(new_goals)
        return new_goals

    def next_executable(self) -> Optional[dict]:
        ready = [g for g in self.goals
                 if g["status"] in ("ACTIVE", "CREATED")
                 and not self._is_blocked(g)]
        if not ready:
            return None
        return min(ready, key=lambda g: g.get("priority", 99))

    def on_tool_success(self, goal_id: str, result: dict):
        goal = self._find(goal_id)
        if goal:
            goal["status"] = "COMPLETED"
            goal["result"] = result
            goal["output"] = result
            goal["updated_at"] = int(time.time())
            self.changed = True
            self._unblock_dependents(goal_id)

    def on_tool_failure(self, goal_id: str, error: str):
        goal = self._find(goal_id)
        if goal:
            goal["retry_count"] = goal.get("retry_count", 0) + 1
            if goal["retry_count"] >= goal.get("max_retries", 2):
                goal["status"] = "FAILED"
                goal["error"] = error
            else:
                goal["status"] = "ACTIVE"
            goal["updated_at"] = int(time.time())
            self.changed = True

    def set_waiting_user(self, goal_id: str, pregunta: str):
        goal = self._find(goal_id)
        if goal:
            goal["status"] = "WAITING_USER"
            goal["pregunta"] = pregunta
            goal["updated_at"] = int(time.time())
            self.changed = True

    def on_user_response(self, goal_id: str, respuesta: dict):
        goal = self._find(goal_id)
        if goal:
            old_input = goal.get("input", {})
            old_input.update(respuesta)
            goal["input"] = old_input
            goal["status"] = "ACTIVE"
            goal["updated_at"] = int(time.time())
            self.changed = True

    def cancel_all(self):
        for g in self.goals:
            if g["status"] in ("ACTIVE", "CREATED", "WAITING_USER", "WAITING_TOOL", "BLOCKED"):
                g["status"] = "CANCELLED"
                g["updated_at"] = int(time.time())
        self.changed = True

    def cancel_goal(self, goal_id: str):
        g = self._find(goal_id)
        if g:
            g["status"] = "CANCELLED"
            g["updated_at"] = int(time.time())
            self.changed = True

    def get_active(self) -> list:
        return [g for g in self.goals
                if g["status"] in ("ACTIVE", "CREATED", "WAITING_USER", "WAITING_TOOL")]

    def get_pending(self) -> list:
        return [g for g in self.goals
                if g["status"] in ("ACTIVE", "CREATED") and not self._is_blocked(g)]

    def to_prompt_context(self) -> str:
        active = self.get_active()
        if not active:
            return ""
        lines = []
        for g in active:
            icon = {"COMPLETED": "✅", "ACTIVE": "▶️", "WAITING_USER": "❓",
                    "FAILED": "❌", "CANCELLED": "🚫", "BLOCKED": "🔒"}
            status_icon = icon.get(g["status"], "⏳")
            desc = self._describe(g)
            lines.append(f"{status_icon} {desc}")
        return "\n".join(lines)

    def get_summary(self) -> dict:
        counts = {"total": len(self.goals)}
        for g in self.goals:
            s = g["status"]
            counts[s] = counts.get(s, 0) + 1
        return counts

    def save_to_session(self) -> list[dict]:
        return self.goals

    def _create_goal(self, goal_type: str, priority: int, input: dict = None,
                     dependencies: list = None) -> dict:
        return {
            "goal_id": f"g_{uuid4().hex[:8]}",
            "goal_type": goal_type,
            "priority": priority,
            "status": "CREATED",
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
            "input": input or {},
            "output": None,
            "result": None,
            "dependencies": dependencies or [],
            "assigned_tool": None,
            "tool_params": {},
            "completion_conditions": {"type": "tool_success"},
            "max_retries": 2,
            "retry_count": 0,
            "error": None,
        }

    def _find(self, goal_id: str) -> Optional[dict]:
        for g in self.goals:
            if g["goal_id"] == goal_id:
                return g
        return None

    def _is_blocked(self, goal: dict) -> bool:
        for dep_id in goal.get("dependencies", []):
            dep = self._find(dep_id)
            if dep and dep["status"] != "COMPLETED":
                return True
        return False

    def _unblock_dependents(self, completed_id: str):
        for g in self.goals:
            if completed_id in g.get("dependencies", []) and g["status"] == "BLOCKED":
                g["status"] = "ACTIVE"
                g["updated_at"] = int(time.time())

    def _describe(self, goal: dict) -> str:
        t = goal["goal_type"]
        inp = goal.get("input", {})
        if t == "REGISTRAR_CLIENTE":
            return "Registrar datos del cliente"
        elif t == "COTIZAR_SERVICIO":
            return f"Cotizar {inp.get('servicio', 'servicio')}"
        elif t == "CONSULTAR_DISPONIBILIDAD":
            return f"Consultar disponibilidad para {inp.get('fecha', 'hoy')}"
        elif t == "AGENDAR_CITA":
            return f"Agendar cita para {inp.get('servicio', 'servicio')}"
        elif t == "RESOLVER_QUEJA":
            return "Resolver queja del cliente"
        elif t == "DIAGNOSTICAR_FALLA":
            return f"Diagnosticar falla: {inp.get('sintomas', '')[:50]}"
        return t
