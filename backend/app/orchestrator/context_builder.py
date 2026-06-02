from typing import Optional

from app.agent.classifier import classify_message
from app.agent.objective_tracker import ObjectiveTracker
from app.agent.state_machine import StateMachine
from app.memory.service import MemoryService
from app.rag.pipeline import RAGPipeline
from app.tools.executor import TOOL_REGISTRY


class ContextBuilder:
    def __init__(self, memory_service: MemoryService = None, rag_pipeline: RAGPipeline = None):
        self.memory = memory_service
        self.rag = rag_pipeline

    async def build_context(
        self,
        mensaje: str,
        session_id: str,
        telefono: str,
        nombre: str = None,
        objective_tracker: ObjectiveTracker = None,
        state_machine: StateMachine = None,
    ) -> dict:
        classification = await classify_message(mensaje)

        mem = None
        if self.memory:
            mem = await self.memory.load(session_id, telefono)

        session_history = (mem or {}).get("history", [])
        episodic = (mem or {}).get("episodic", [])
        profile = (mem or {}).get("profile", {})

        rag_context = ""
        if self.rag:
            try:
                rag_context = await self.rag.query(mensaje, session_id, top_k=3)
            except Exception:
                rag_context = ""

        if objective_tracker:
            if classification.get("intencion_principal") not in ("SALUDO", "DESPEDIDA", "OTRO"):
                new_goals = objective_tracker.detect_from_classification(classification, telefono, nombre)
                if classification.get("intencion_principal") == "COTIZACION":
                    if state_machine and state_machine.domain != "COTIZACION":
                        state_machine.switch_domain("COTIZACION")

        goals = objective_tracker.goals if objective_tracker else []
        active_goals = [g for g in goals if g.get("status") in ("ACTIVE", "CREATED")]

        goals_context = ""
        if objective_tracker:
            goals_context = objective_tracker.to_prompt_context()

        sm_context = {}
        if state_machine:
            sm_context = state_machine.to_dict()

        return {
            "mensaje": mensaje,
            "session_id": session_id,
            "telefono": telefono,
            "nombre": nombre or "",
            "classification": classification,
            "goals": goals,
            "active_goals": active_goals,
            "goals_context": goals_context,
            "state_machine": sm_context,
            "memory_context": episodic[:3] if episodic else [],
            "rag_context": rag_context,
            "profile": profile,
            "history": session_history[-10:] if session_history else [],
            "tool_results": {},
            "tool_context": TOOL_REGISTRY.build_tool_context() if TOOL_REGISTRY else "",
        }
