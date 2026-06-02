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
        self.objective_tracker = ObjectiveTracker()
        self.state_machine = StateMachine("COTIZACION")
        self.planner = Planner()
        self.generator = Generator()
        self.reflector = Reflector()
        self.prompt_builder = PromptOrchestrator()
        self.context_builder = ContextBuilder(memory_service, rag_pipeline)
        self.memory = memory_service

    async def process(self, mensaje: str, session_id: str, telefono: str, nombre: str = None) -> dict:
        logger.info(f"Processing message from {telefono} (session: {session_id}): {mensaje[:100]}")

        rate_error = await rate_limiter.check(telefono)
        if rate_error:
            return {
                "respuesta": "Estás enviando mensajes muy rápido. Por favor espera un momento antes de escribir de nuevo.",
                "session_id": session_id,
                "processed": True,
            }

        context = await self.context_builder.build_context(
            mensaje=mensaje,
            session_id=session_id,
            telefono=telefono,
            nombre=nombre,
            objective_tracker=self.objective_tracker,
            state_machine=self.state_machine,
        )

        classification = context["classification"]
        intent = classification.get("intencion_principal", "OTRO")

        plan = await self.planner.generate_plan(context)
        self.planner.current_plan = plan
        self.planner.current_step = 0

        tool_results = {}
        executed_tools = set()
        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            action = self.planner.get_current_action()

            if not action:
                break
            if action["action"] != "tool_call":
                break

            tool_name = action.get("tool")
            if tool_name in executed_tools:
                self.planner.advance()
                continue

            params = action.get("params", {})
            params["telefono"] = params.get("telefono", telefono)
            logger.info(f"Executing tool: {tool_name}")

            result = await self.tool_executor.execute(tool_name, params)

            tool_results[tool_name] = result
            executed_tools.add(tool_name)
            context["tool_results"] = tool_results

            if result.get("success"):
                goal_id = self._find_goal_for_tool(tool_name)
                if goal_id:
                    self.objective_tracker.on_tool_success(goal_id, result)
            else:
                goal_id = self._find_goal_for_tool(tool_name)
                if goal_id:
                    self.objective_tracker.on_tool_failure(goal_id, result.get("error", "unknown"))

            next_plan = await self.planner.generate_plan(context)
            if next_plan != plan:
                plan = next_plan
                self.planner.current_plan = plan
                self.planner.current_step = 0
            else:
                self.planner.advance()

        context["tool_results"] = tool_results
        context["goals_context"] = self.objective_tracker.to_prompt_context()

        response = await self.generator.generate_response(context)

        validation = await self.reflector.validate(context, response)
        if not validation.get("valida"):
            logger.warning(f"Response validation failed: {validation.get('problemas')}")
            improved = await self.reflector.improve(context, response, validation.get("problemas", []))
            if improved and len(improved) > 10:
                response = improved

        state_report = self.state_machine.to_dict() if self.state_machine else {}
        goals_summary = self.objective_tracker.get_summary() if self.objective_tracker else {}

        if self.memory:
            try:
                asyncio.create_task(self.memory.save(
                    session_id=session_id,
                    telefono=telefono,
                    mensaje=mensaje,
                    respuesta=response,
                    classification=classification,
                    tool_results=tool_results,
                    goals=self.objective_tracker.save_to_session(),
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

    def _find_goal_for_tool(self, tool_name: str) -> Optional[str]:
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
            for g in self.objective_tracker.goals:
                if g["goal_type"] == goal_type and g["status"] in ("ACTIVE", "CREATED"):
                    return g["goal_id"]
        return None
