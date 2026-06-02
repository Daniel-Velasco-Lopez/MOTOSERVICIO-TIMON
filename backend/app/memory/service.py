import json
import time
import logging
from typing import Optional

from app.memory.working import session_manager

logger = logging.getLogger(__name__)


class MemoryService:
    async def load(self, session_id: str, telefono: str) -> dict:
        session = await session_manager.get_session(telefono)
        if not session:
            return {"history": [], "episodic": [], "profile": {}}

        history_raw = session.get("historial", [])
        history = json.loads(history_raw) if isinstance(history_raw, str) else (history_raw or [])

        episodic = session.get("episodic_summaries", [])
        if isinstance(episodic, str):
            episodic = json.loads(episodic)

        profile = session.get("profile", {})
        if isinstance(profile, str):
            profile = json.loads(profile)

        goals = session.get("goals")
        if isinstance(goals, str):
            goals = json.loads(goals)

        state_machine = session.get("state_machine")
        if isinstance(state_machine, str):
            state_machine = json.loads(state_machine)

        return {
            "history": history,
            "episodic": episodic,
            "profile": profile,
            "goals": goals,
            "state_machine": state_machine,
        }

    async def save(
        self,
        session_id: str,
        telefono: str,
        mensaje: str,
        respuesta: str,
        classification: dict = None,
        tool_results: dict = None,
        goals: list = None,
        state_machine: dict = None,
    ):
        existing = await session_manager.get_session(telefono) or {"historial": [], "mensajes_en_sesion": 0}

        history = existing.get("historial", [])
        if isinstance(history, str):
            history = json.loads(history)

        entry = {
            "mensaje": mensaje,
            "respuesta": respuesta,
            "timestamp": int(time.time()),
            "classification": classification,
            "tools": list((tool_results or {}).keys()),
        }
        history.append(entry)
        max_history = 100
        if len(history) > max_history:
            history = history[-max_history:]

        updates = {
            "historial": json.dumps(history),
            "mensajes_en_sesion": existing.get("mensajes_en_sesion", 0) + 1,
            "ultima_interaccion": int(time.time()),
            "ultimo_tema": classification.get("intencion_principal") if classification else existing.get("ultimo_tema"),
        }

        if goals:
            updates["goals"] = json.dumps(goals)
        if state_machine:
            updates["state_machine"] = json.dumps(state_machine)

        await session_manager.update_session(telefono, updates)

    async def get_history(self, telefono: str, limit: int = 10) -> list:
        session = await session_manager.get_session(telefono)
        if not session:
            return []
        history = session.get("historial", [])
        if isinstance(history, str):
            history = json.loads(history)
        return history[-limit:]

    async def clear(self, telefono: str):
        await session_manager.delete_session(telefono)
