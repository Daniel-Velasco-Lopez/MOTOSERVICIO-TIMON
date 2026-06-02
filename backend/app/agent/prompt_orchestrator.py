from typing import Optional


class PromptOrchestrator:
    def __init__(self):
        self.tone_profile = {
            "default": "profesional pero cálido, usa un tono amigable",
            "queja": "empático, comprensivo, serio",
            "urgencia": "directo, claro, sin rodeos",
            "seguimiento": "cordal, recordatorio amable",
        }
        self.current_tone = "default"

    def set_tone(self, tone: str):
        if tone in self.tone_profile:
            self.current_tone = tone

    def build_system_prompt(self, context: dict) -> str:
        classification = context.get("classification", {})
        intent = classification.get("intencion_principal", "OTRO")
        tone = self._select_tone(intent)

        sections = []

        sections.append(f"""Eres Timón, el asistente virtual de MotoServicio Timón, un taller de motocicletas.
Tono: {tone}

INSTRUCCIONES:
1. Responde en español, directo y natural
2. No te refieras a ti mismo como "asistente virtual" o "IA"
3. Usa emojis 🏍️🔧 con moderación
4. Sé conciso — máximo 3 párrafos
5. Siempre termina con una pregunta o llamado a la acción""")

        goals_context = context.get("goals_context", "")
        if goals_context:
            sections.append(f"\nGOALS ACTIVOS:\n{goals_context}")

        tool_results = context.get("tool_results", {})
        if tool_results:
            sections.append(self._build_tool_context(tool_results))

        memory_context = context.get("memory_context", "")
        if memory_context:
            sections.append(f"\nCONTEXTO DE MEMORIA:\n{memory_context[:500]}")

        rag_context = context.get("rag_context", "")
        if rag_context:
            sections.append(f"\nINFORMACIÓN DE REFERENCIA:\n{rag_context[:800]}")

        sections.append(f"\nMENSAJE DEL CLIENTE:\n{context.get('mensaje', '')}")

        sections.append("\nResponde SOLO con el mensaje para el cliente, sin metadatos adicionales.")

        return "\n---\n".join(sections)

    def _select_tone(self, intent: str) -> str:
        if intent == "QUEJA":
            return self.tone_profile["queja"]
        return self.tone_profile["default"]

    def _build_tool_context(self, tool_results: dict) -> str:
        lines = []
        for tool_name, result in tool_results.items():
            if result.get("success"):
                lines.append(f"\nRESULTADO DE {tool_name.upper()}:")
                data = result.get("data", {})
                if "precios" in data:
                    for p in data["precios"]:
                        lines.append(f"- {p.get('servicio', '')}: ${float(p.get('precio', 0)):.2f}")
                elif "horarios" in data:
                    lines.append(f"Fecha: {data.get('fecha', '')}")
                    if data.get("hay_disponibilidad"):
                        lines.append(f"Horarios disponibles: {', '.join(data['horarios'][:5])}")
                    else:
                        lines.append("No hay disponibilidad para esta fecha")
                elif "cita_id" in data:
                    lines.append(f"Cita #{data['cita_id']} agendada para {data.get('fecha', '')} a las {data.get('hora', '')}")
                elif "diagnostico_gemini" in data:
                    lines.append(f"Diagnóstico: {data['diagnostico_gemini']}")
                elif "mensaje" in data:
                    lines.append(data["mensaje"])
            else:
                lines.append(f"\nERROR en {tool_name}: {result.get('error', 'desconocido')}")
        return "\n".join(lines)

    def build_tool_selection_prompt(self, context: dict, available_tools: str) -> str:
        return f"""Eres un selector de herramientas para el asistente de MotoServicio Timón.
Basado en el contexto y los goals activos, selecciona la herramienta adecuada.

INTENCIÓN: {context.get('classification', {}).get('intencion_principal', 'OTRO')}

GOALS ACTIVOS:
{context.get('goals_context', 'ninguno')}

HERRAMIENTAS DISPONIBLES:
{available_tools}

Responde SOLO con el nombre de la herramienta a ejecutar, o "ninguna" si no se requiere tool."""

    def build_planning_prompt(self, context: dict) -> str:
        classification = context.get("classification", {})
        goals = context.get("goals", [])
        active_goals = [g for g in goals if g.get("status") in ("ACTIVE", "CREATED")]

        goals_text = "\n".join(f"- {g['goal_type']}: {g.get('input', {})}" for g in active_goals) if active_goals else "No hay goals activos"

        return f"""Eres el planificador de MotoServicio Timón.
Genera un plan de acción basado en:

INTENCIÓN: {classification.get('intencion_principal', 'OTRO')}
CONFIANZA: {classification.get('confianza', 0)}

GOALS ACTIVOS:
{goals_text}

Reglas:
1. Si hay goals ACTIVOS, genera pasos para cumplirlos en orden
2. Si un goal necesita más datos, pide aclaración
3. Si no hay goals, genera una respuesta directa
4. Máximo 5 pasos en el plan

Formato de respuesta (JSON):
{{"plan": [{{"step": 1, "action": "tool_call|ask|respond", "tool": "...", "params": {{}}, "question": "..."}}], "razonamiento": "..."}}"""
