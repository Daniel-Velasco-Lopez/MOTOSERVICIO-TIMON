import json
import asyncio
import logging
from typing import Optional

from app.orchestrator.context_builder import ContextBuilder
from app.agent.classifier import classify_message
from app.agent.objective_tracker import ObjectiveTracker
from app.agent.state_machine import StateMachine
from app.agent.planner import Planner
from app.agent.generator import Generator
from app.agent.reflector import Reflector
from app.agent.prompt_orchestrator import PromptOrchestrator
from app.tools.executor import ToolExecutor, TOOL_REGISTRY
from app.memory.service import MemoryService
from app.rag.pipeline import RAGPipeline
from app.memory.working import rate_limiter

logger = logging.getLogger(__name__)


class MessageProcessor:
    def __init__(self, memory_service: MemoryService = None, rag_pipeline: RAGPipeline = None):
        self.tool_executor = ToolExecutor(TOOL_REGISTRY)
        self.prompt_builder = PromptOrchestrator()
        self.generator = Generator(prompt_builder=self.prompt_builder)
        self.reflector = Reflector()
        self.context_builder = ContextBuilder(memory_service, rag_pipeline)
        self.memory = memory_service
        self._sessions: dict[str, dict] = {}

    async def _get_session_state(self, session_id: str) -> dict:
        if session_id not in self._sessions:
            ot = ObjectiveTracker()
            sm = StateMachine("COTIZACION")
            planner = Planner()

            if self.memory:
                try:
                    mem = await self.memory.load(session_id, session_id)
                    raw_goals = mem.get("goals")
                    raw_sm = mem.get("state_machine")
                    if raw_goals:
                        ot.load(raw_goals)
                    if raw_sm:
                        sm = StateMachine.from_dict(raw_sm)
                except Exception:
                    logger.warning(f"No se pudo restaurar estado de sesión {session_id}")

            self._sessions[session_id] = {
                "objective_tracker": ot,
                "state_machine": sm,
                "planner": planner,
            }

        return self._sessions[session_id]

    async def process(self, mensaje: str, session_id: str, telefono: str, nombre: str = None) -> dict:
        logger.info(f"Processing message from {telefono} (session: {session_id}): {mensaje[:100]}")

        rate_error = await rate_limiter.check(telefono)
        if rate_error:
            return {
                "respuesta": "Estás enviando mensajes muy rápido. Por favor espera un momento antes de escribir de nuevo.",
                "session_id": session_id,
                "processed": True,
            }

        session_state = await self._get_session_state(session_id)
        ot = session_state["objective_tracker"]
        sm = session_state["state_machine"]
        planner = session_state["planner"]

        context = await self.context_builder.build_context(
            mensaje=mensaje,
            session_id=session_id,
            telefono=telefono,
            nombre=nombre,
            objective_tracker=ot,
            state_machine=sm,
        )

        classification = context["classification"]
        intent = classification.get("intencion_principal", "OTRO")

        plan = await planner.generate_plan(context)
        planner.current_plan = plan
        planner.current_step = 0

        tool_results = {}
        executed_tools = set()
        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            action = planner.get_current_action()

            if not action:
                break
            if action["action"] != "tool_call":
                break

            tool_name = action.get("tool")
            if tool_name in executed_tools:
                planner.advance()
                continue

            params = action.get("params", {})
            params["telefono"] = params.get("telefono", telefono)
            logger.info(f"Executing tool: {tool_name}")

            result = await self.tool_executor.execute(tool_name, params)

            tool_results[tool_name] = result
            executed_tools.add(tool_name)
            context["tool_results"] = tool_results

            if result.get("success"):
                goal_id = self._find_goal_for_tool(tool_name, ot)
                if goal_id:
                    ot.on_tool_success(goal_id, result)
            else:
                goal_id = self._find_goal_for_tool(tool_name, ot)
                if goal_id:
                    ot.on_tool_failure(goal_id, result.get("error", "unknown"))

            next_plan = await planner.generate_plan(context)
            if next_plan != plan:
                plan = next_plan
                planner.current_plan = plan
                planner.current_step = 0
            else:
                planner.advance()

        context["tool_results"] = tool_results
        context["goals_context"] = ot.to_prompt_context()

        response = await self.generator.generate_response(context)

        validation = await self.reflector.validate(context, response)
        if not validation.get("valida"):
            logger.warning(f"Response validation failed: {validation.get('problemas')}")
            improved = await self.reflector.improve(context, response, validation.get("problemas", []))
            if improved and len(improved) > 10:
                response = improved

        state_report = sm.to_dict() if sm else {}
        goals_summary = ot.get_summary() if ot else {}

        if self.memory:
            try:
                asyncio.create_task(self.memory.save(
                    session_id=session_id,
                    telefono=telefono,
                    mensaje=mensaje,
                    respuesta=response,
                    classification=classification,
                    tool_results=tool_results,
                    goals=ot.save_to_session(),
                    state_machine=state_report,
                ))
            except Exception as e:
                logger.error(f"Memory save error: {e}")

        return {
            "respuesta": response,
            "session_id": session_id,
            "processed": True,
            "classification": classification,
            "goals": goals_summary,
            "state_machine": state_report,
            "tools_executed": list(executed_tools),
            "validation": validation,
        }

    def _find_goal_for_tool(self, tool_name: str, objective_tracker: ObjectiveTracker) -> Optional[str]:
        mapping = {
            "registrar_cliente": "REGISTRAR_CLIENTE",
            "cotizar_servicio": "COTIZAR_SERVICIO",
            "consultar_disponibilidad": "CONSULTAR_DISPONIBILIDAD",
            "agendar_cita": "AGENDAR_CITA",
            "registrar_queja": "RESOLVER_QUEJA",
            "diagnosticar_falla": "DIAGNOSTICAR_FALLA",
        }
        goal_type = mapping.get(tool_name)
        if goal_type:
            for g in objective_tracker.goals:
                if g["goal_type"] == goal_type and g["status"] in ("ACTIVE", "CREATED"):
                    return g["goal_id"]
        return None
