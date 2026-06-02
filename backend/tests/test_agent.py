import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.agent.classifier import classify_message, _rule_based_fallback, _extract_entities
from app.agent.objective_tracker import ObjectiveTracker
from app.agent.state_machine import StateMachine
from app.agent.planner import Planner
from app.agent.generator import Generator
from app.agent.reflector import Reflector
from app.agent.prompt_orchestrator import PromptOrchestrator
from app.orchestrator.message_processor import MessageProcessor
from app.tools.executor import ToolExecutor, TOOL_REGISTRY, ToolRegistryBuilder
from app.rag.chunker import Chunker
from app.memory.service import MemoryService
from app.persistence.repository import Repository


# ============================================================
# CLASSIFIER TESTS
# ============================================================

class TestClassifier:
    def test_saludo_detectado(self):
        result = _rule_based_fallback("Hola buenos días")
        assert result["intencion_principal"] == "SALUDO"
        assert result["confianza"] >= 0.8

    def test_cotizacion_detectada(self):
        result = _rule_based_fallback("Cuánto cuesta el servicio de frenos")
        assert result["intencion_principal"] == "COTIZACION"
        assert result["confianza"] >= 0.8
        assert "servicio_solicitado" in result["entidades"]

    def test_agendamiento_detectado(self):
        result = _rule_based_fallback("Quiero agendar una cita para mantenimiento")
        assert result["intencion_principal"] == "AGENDAMIENTO"
        assert result["confianza"] >= 0.8

    def test_diagnostico_detectado(self):
        result = _rule_based_fallback("Mi moto hace un ruido extraño al acelerar")
        assert result["intencion_principal"] == "DIAGNOSTICO"
        assert result["confianza"] >= 0.8
        assert "sintomas" in result["entidades"]

    def test_queja_detectada(self):
        result = _rule_based_fallback("Estoy inconforme con el servicio que recibí")
        assert result["intencion_principal"] == "QUEJA"

    def test_despedida_detectada(self):
        result = _rule_based_fallback("Gracias, hasta luego")
        assert result["intencion_principal"] == "DESPEDIDA"

    def test_otro_detectado(self):
        result = _rule_based_fallback("El clima está muy bonito hoy")
        assert result["intencion_principal"] == "OTRO"
        assert result["confianza"] < 0.5

    def test_mensaje_vacio(self):
        result = _rule_based_fallback("")
        assert result["intencion_principal"] == "OTRO"

    def test_extract_entities_moto(self):
        entities = _extract_entities("mi honda tiene un problema")
        assert entities.get("moto") == "Honda"

    def test_extract_entities_fecha(self):
        entities = _extract_entities("para el 2024-12-25")
        assert "fecha_mencionada" in entities

    def test_extract_entities_hora(self):
        entities = _extract_entities("a las 14:30")
        assert entities.get("hora_mencionada") == "14:30"

    def test_extract_entities_disponibilidad(self):
        entities = _extract_entities("hay lugar para el sábado")
        assert entities.get("pregunta_disponibilidad") is True

    @pytest.mark.asyncio
    async def test_classify_message_no_gemini(self):
        with patch('app.agent.classifier.gemini_service', None):
            result = await classify_message("Cuánto cuesta el servicio")
            assert result["intencion_principal"] == "COTIZACION"
            assert result["confianza"] >= 0.8


# ============================================================
# OBJECTIVE TRACKER TESTS
# ============================================================

class TestObjectiveTracker:
    def test_init_empty(self):
        ot = ObjectiveTracker()
        assert ot.goals == []
        assert ot.changed is False

    def test_detect_from_cotizacion(self):
        ot = ObjectiveTracker()
        classification = {"intencion_principal": "COTIZACION", "entidades": {"servicio_solicitado": "frenos"}}
        new = ot.detect_from_classification(classification, "521234567890")
        assert len(new) == 2  # REGISTRAR_CLIENTE + COTIZAR_SERVICIO
        assert new[0]["goal_type"] == "REGISTRAR_CLIENTE"
        assert new[1]["goal_type"] == "COTIZAR_SERVICIO"

    def test_detect_from_agendamiento(self):
        ot = ObjectiveTracker()
        classification = {"intencion_principal": "AGENDAMIENTO", "entidades": {"fecha_mencionada": "2024-12-25"}}
        new = ot.detect_from_classification(classification, "521234567890")
        assert len(new) == 3
        assert new[2]["goal_type"] == "AGENDAR_CITA"

    def test_detect_from_queja(self):
        ot = ObjectiveTracker()
        classification = {"intencion_principal": "QUEJA", "entidades": {"descripcion": "mal servicio"}}
        new = ot.detect_from_classification(classification, "521234567890")
        assert len(new) == 2
        assert new[1]["goal_type"] == "RESOLVER_QUEJA"

    def test_detect_from_diagnostico(self):
        ot = ObjectiveTracker()
        classification = {"intencion_principal": "DIAGNOSTICO", "entidades": {"sintomas": "ruido motor"}}
        new = ot.detect_from_classification(classification, "521234567890")
        assert len(new) == 2
        assert new[1]["goal_type"] == "DIAGNOSTICAR_FALLA"

    def test_no_goals_for_saludo(self):
        ot = ObjectiveTracker()
        classification = {"intencion_principal": "SALUDO", "entidades": {}}
        new = ot.detect_from_classification(classification, "521234567890")
        assert len(new) == 0

    def test_next_executable_priority(self):
        ot = ObjectiveTracker()
        ot.goals = [
            {"goal_id": "g1", "goal_type": "A", "priority": 3, "status": "ACTIVE", "dependencies": []},
            {"goal_id": "g2", "goal_type": "B", "priority": 1, "status": "ACTIVE", "dependencies": []},
        ]
        next_g = ot.next_executable()
        assert next_g["goal_id"] == "g2"

    def test_blocked_by_dependency(self):
        ot = ObjectiveTracker()
        ot.goals = [
            {"goal_id": "g1", "goal_type": "A", "priority": 1, "status": "CREATED", "dependencies": []},
            {"goal_id": "g2", "goal_type": "B", "priority": 2, "status": "CREATED", "dependencies": ["g1"]},
        ]
        next_g = ot.next_executable()
        assert next_g["goal_id"] == "g1"

    def test_on_tool_success(self):
        ot = ObjectiveTracker()
        g = ot._create_goal("TEST", 1)
        gid = g["goal_id"]
        ot.goals = [g]
        ot.on_tool_success(gid, {"success": True})
        assert ot.goals[0]["status"] == "COMPLETED"

    def test_on_tool_failure_triggers_retry(self):
        ot = ObjectiveTracker()
        g = ot._create_goal("TEST", 1)
        gid = g["goal_id"]
        ot.goals = [g]
        ot.on_tool_failure(gid, "error")
        assert ot.goals[0]["retry_count"] == 1
        assert ot.goals[0]["status"] == "ACTIVE"

    def test_on_tool_failure_exhausts_retries(self):
        ot = ObjectiveTracker()
        g = ot._create_goal("TEST", 1)
        gid = g["goal_id"]
        g["retry_count"] = 1
        ot.goals = [g]
        ot.on_tool_failure(gid, "error")
        assert ot.goals[0]["status"] == "FAILED"

    def test_on_user_response_reactivates(self):
        ot = ObjectiveTracker()
        g = ot._create_goal("TEST", 1)
        gid = g["goal_id"]
        g["status"] = "WAITING_USER"
        g["input"] = {"telebono": "123"}
        ot.goals = [g]
        ot.on_user_response(gid, {"respuesta": "sí"})
        assert ot.goals[0]["status"] == "ACTIVE"
        assert ot.goals[0]["input"]["respuesta"] == "sí"

    def test_cancel_all(self):
        ot = ObjectiveTracker()
        ot.goals = [
            {"goal_id": "g1", "goal_type": "A", "priority": 1, "status": "ACTIVE", "dependencies": []},
            {"goal_id": "g2", "goal_type": "B", "priority": 2, "status": "COMPLETED", "dependencies": []},
        ]
        ot.cancel_all()
        assert ot.goals[0]["status"] == "CANCELLED"
        assert ot.goals[1]["status"] == "COMPLETED"

    def test_save_to_session(self):
        ot = ObjectiveTracker()
        g = ot._create_goal("TEST", 1)
        ot.goals = [g]
        saved = ot.save_to_session()
        assert len(saved) == 1
        assert saved[0]["goal_type"] == "TEST"


# ============================================================
# STATE MACHINE TESTS
# ============================================================

class TestStateMachine:
    def test_initial_state(self):
        sm = StateMachine("COTIZACION")
        assert sm.current == "USUARIO_PREGUNTA"

    def test_valid_transition(self):
        sm = StateMachine("COTIZACION")
        ok, action = sm.transition("CLASIFICAR")
        assert ok is True
        assert sm.current == "CLASIFICANDO"

    def test_invalid_transition(self):
        sm = StateMachine("COTIZACION")
        ok, action = sm.transition("INVALID_EVENT")
        assert ok is False

    def test_can_transition(self):
        sm = StateMachine("COTIZACION")
        assert sm.can_transition("CLASIFICAR") is True
        assert sm.can_transition("INVALID") is False

    def test_get_possible_events(self):
        sm = StateMachine("COTIZACION")
        events = sm.get_possible_events()
        assert "CLASIFICAR" in events

    def test_switch_domain(self):
        sm = StateMachine("COTIZACION")
        sm.switch_domain("AGENDAMIENTO")
        assert sm.domain == "AGENDAMIENTO"
        assert sm.current == "SOLICITANDO_DATOS"

    def test_to_dict(self):
        sm = StateMachine("COTIZACION")
        d = sm.to_dict()
        assert d["domain"] == "COTIZACION"
        assert d["current"] == "USUARIO_PREGUNTA"

    def test_from_dict(self):
        sm = StateMachine.from_dict({"domain": "QUEJA", "data": {"test": 1}})
        assert sm.domain == "QUEJA"
        assert sm.current == "USUARIO_REPORTA"

    def test_get_user_facing_state(self):
        sm = StateMachine("AGENDAMIENTO")
        assert sm.get_user_facing_state() == "ESPERANDO_USUARIO"

    def test_diagnostico_machine(self):
        sm = StateMachine("DIAGNOSTICO")
        assert sm.current == "USUARIO_DESCRIBE_FALLA"
        ok, _ = sm.transition("CLASIFICAR")
        assert ok is True
        assert sm.current == "CLASIFICANDO_SINTOMAS"

    def test_queja_machine(self):
        sm = StateMachine("QUEJA")
        ok, _ = sm.transition("CLASIFICAR")
        assert ok is True
        assert sm.current == "REGISTRANDO_QUEJA"

    def test_get_entry_action(self):
        sm = StateMachine("COTIZACION")
        sm.transition("CLASIFICAR")
        action = sm.get_entry_action()
        assert action == "clasificar_intencion"


# ============================================================
# PLANNER TESTS
# ============================================================

class TestPlanner:
    @pytest.mark.asyncio
    async def test_plan_with_active_goals(self):
        planner = Planner()
        context = {
            "goals": [
                {"goal_id": "g1", "goal_type": "REGISTRAR_CLIENTE", "status": "ACTIVE",
                 "priority": 1, "input": {"telefono": "521234567890"}},
                {"goal_id": "g2", "goal_type": "COTIZAR_SERVICIO", "status": "ACTIVE",
                 "priority": 2, "input": {"servicio": "frenos"}},
            ],
            "classification": {"intencion_principal": "COTIZACION"},
            "telefono": "521234567890",
        }
        plan = await planner.generate_plan(context)
        assert len(plan) == 2
        assert plan[0]["action"] == "tool_call"
        assert plan[1]["tool"] == "cotizar_servicio"

    @pytest.mark.asyncio
    async def test_plan_saludo(self):
        planner = Planner()
        context = {
            "classification": {"intencion_principal": "SALUDO"},
            "goals": [],
        }
        plan = await planner.generate_plan(context)
        assert len(plan) == 1
        assert plan[0]["action"] == "respond"

    @pytest.mark.asyncio
    async def test_plan_ask_clarification_when_missing_params(self):
        planner = Planner()
        context = {
            "goals": [
                {"goal_id": "g1", "goal_type": "COTIZAR_SERVICIO", "status": "ACTIVE",
                 "priority": 1, "input": {}},
            ],
            "classification": {"intencion_principal": "COTIZACION"},
            "telefono": "521234567890",
        }
        plan = await planner.generate_plan(context)
        assert len(plan) == 1
        assert plan[0]["action"] == "ask_clarification"

    def test_get_current_action(self):
        planner = Planner()
        planner.current_plan = [{"step": 1, "action": "tool_call", "tool": "test"}]
        planner.current_step = 0
        action = planner.get_current_action()
        assert action["tool"] == "test"

    def test_advance(self):
        planner = Planner()
        planner.current_plan = [{"step": 1}, {"step": 2}]
        assert planner.advance() is True
        assert planner.current_step == 1

    def test_reset(self):
        planner = Planner()
        planner.current_plan = [{"step": 1}]
        planner.current_step = 1
        planner.reset()
        assert planner.current_plan == []
        assert planner.current_step == 0


# ============================================================
# GENERATOR TESTS
# ============================================================

class TestGenerator:
    def test_fallback_no_tool_saludo(self):
        gen = Generator()
        context = {"classification": {"intencion_principal": "SALUDO"}, "tool_results": {}}
        resp = gen._fallback_generate(context)
        assert "Hola" in resp or "hola" in resp

    def test_fallback_tool_cotizacion(self):
        gen = Generator()
        context = {
            "classification": {"intencion_principal": "COTIZACION"},
            "tool_results": {
                "cotizar_servicio": {
                    "success": True,
                    "data": {"precios": [{"servicio": "Frenos", "precio_min": "350", "precio_max": "450"}]},
                }
            },
        }
        resp = gen._fallback_generate(context)
        assert "Frenos" in resp

    def test_fallback_tool_cita(self):
        gen = Generator()
        context = {
            "classification": {"intencion_principal": "AGENDAMIENTO"},
            "tool_results": {
                "agendar_cita": {
                    "success": True,
                    "data": {"cita_id": 1, "fecha": "2024-12-25", "servicio": "Mantenimiento"},
                }
            },
        }
        resp = gen._fallback_generate(context)
        assert "Cita" in resp or "agendada" in resp

    def test_fallback_tool_error(self):
        gen = Generator()
        context = {
            "classification": {"intencion_principal": "COTIZACION"},
            "tool_results": {"cotizar_servicio": {"success": False, "error": "servicio no encontrado"}},
        }
        resp = gen._fallback_generate(context)
        assert "error" in resp or "Lo siento" in resp

    def test_fallback_tool_queja(self):
        gen = Generator()
        context = {
            "classification": {"intencion_principal": "QUEJA"},
            "tool_results": {
                "registrar_queja": {"success": True, "data": {"ticket": "QABCD1234"}}
            },
        }
        resp = gen._fallback_generate(context)
        assert "QABCD1234" in resp

    @pytest.mark.asyncio
    async def test_generate_response_no_gemini(self):
        gen = Generator()
        context = {
            "classification": {"intencion_principal": "SALUDO"},
            "tool_results": {},
            "mensaje": "Hola",
            "goals_context": "",
        }
        with patch('app.agent.generator.gemini_service', None):
            resp = await gen.generate_response(context)
            assert len(resp) > 0


# ============================================================
# REFLECTOR TESTS
# ============================================================

class TestReflector:
    def test_rule_validate_empty(self):
        ref = Reflector()
        result = ref._rule_based_validate({"classification": {"intencion_principal": "OTRO"}}, "Hola")
        assert result["puntaje"] < 100

    def test_rule_validate_cotizacion_sin_precio(self):
        ref = Reflector()
        result = ref._rule_based_validate(
            {"classification": {"intencion_principal": "COTIZACION"}},
            "Te podemos ayudar con eso"
        )
        assert "precio" in str(result["problemas"])

    def test_rule_validate_cotizacion_con_precio(self):
        ref = Reflector()
        result = ref._rule_based_validate(
            {"classification": {"intencion_principal": "COTIZACION"}},
            "El precio es $350. ¿Te gustaría agendar?"
        )
        assert result["puntaje"] >= 60

    def test_rule_validate_auto_referencia(self):
        ref = Reflector()
        result = ref._rule_based_validate(
            {"classification": {"intencion_principal": "INFORMACION"}},
            "Como asistente virtual, te recomiendo..."
        )
        assert "auto-referencia" in str(result["problemas"])

    def test_rule_validate_queja_sin_pregunta(self):
        ref = Reflector()
        result = ref._rule_based_validate(
            {"classification": {"intencion_principal": "QUEJA"}},
            "Lamento tu molestia"
        )
        assert "invita" in str(result["problemas"])

    @pytest.mark.asyncio
    async def test_validate_empty_response(self):
        ref = Reflector()
        result = await ref.validate({"classification": {}}, "")
        assert result["valida"] is False

    @pytest.mark.asyncio
    async def test_improve_no_problems(self):
        ref = Reflector()
        result = await ref.improve({}, "Hola", [])
        assert result == "Hola"


# ============================================================
# TOOL EXECUTOR TESTS
# ============================================================

class TestToolExecutor:
    def test_registry_has_all_tools(self):
        registry = ToolRegistryBuilder().registry
        tools = registry.list()
        names = [t["name"] for t in tools]
        assert "registrar_cliente" in names
        assert "cotizar_servicio" in names
        assert "consultar_disponibilidad" in names
        assert "agendar_cita" in names
        assert "registrar_queja" in names
        assert "diagnosticar_falla" in names
        assert "enviar_mensaje_whatsapp" in names
        assert "consultar_historial_cliente" in names

    def test_get_unknown_tool(self):
        registry = ToolRegistryBuilder().registry
        assert registry.get("non_existent") is None

    def test_get_by_category(self):
        registry = ToolRegistryBuilder().registry
        agenda = registry.get_by_category("agenda")
        assert len(agenda) == 2
        assert agenda[0].name == "consultar_disponibilidad"

    def test_resolve_for_goal(self):
        registry = ToolRegistryBuilder().registry
        assert registry.resolve_for_goal("COTIZAR_SERVICIO") == "cotizar_servicio"
        assert registry.resolve_for_goal("UNKNOWN") is None

    def test_validate_input(self):
        executor = ToolExecutor()
        tool = TOOL_REGISTRY.get("registrar_cliente")
        assert executor._validate_input(tool, {"telefono": "123"}) is True
        assert executor._validate_input(tool, {}) is False

    def test_get_result_summary_success(self):
        executor = ToolExecutor()
        summary = executor.get_result_summary({
            "success": True,
            "data": {"cita_id": 42}
        })
        assert "Cita" in summary and "42" in summary

    def test_get_result_summary_error(self):
        executor = ToolExecutor()
        summary = executor.get_result_summary({
            "success": False,
            "error": "algo falló"
        })
        assert "Error" in summary


# ============================================================
# CHUNKER TESTS
# ============================================================

class TestChunker:
    def test_empty_text(self):
        c = Chunker()
        assert c.chunk_text("") == []

    def test_short_text(self):
        c = Chunker()
        assert c.chunk_text("Hola mundo") == ["Hola mundo"]

    def test_long_text_chunked(self):
        c = Chunker(chunk_size=50, overlap=10)
        text = "a " * 100
        chunks = c.chunk_text(text)
        assert len(chunks) > 1
        assert all(len(ch) <= 50 for ch in chunks)

    def test_chunk_messages(self):
        c = Chunker()
        history = [{"mensaje": "Hola", "respuesta": "Buen día", "timestamp": 1000}]
        chunks = c.chunk_messages(history)
        assert len(chunks) == 1
        assert chunks[0]["text"] == "Hola Buen día"


# ============================================================
# STATE MACHINE INTEGRATION FLOWS
# ============================================================

class TestConversationFlows:
    """Escenario 1: saludo → cotización → disponibilidad → agendar cita"""

    def test_flow_saludo(self):
        ot = ObjectiveTracker()
        classification = {"intencion_principal": "SALUDO", "confianza": 0.9, "entidades": {}}
        new = ot.detect_from_classification(classification, "521234567890")
        assert len(new) == 0  # SALUDO no genera goals

    def test_flow_cotizacion_generates_goals(self):
        ot = ObjectiveTracker()
        classification = {"intencion_principal": "COTIZACION", "confianza": 0.9,
                          "entidades": {"servicio_solicitado": "frenos", "pregunta_disponibilidad": True}}
        new = ot.detect_from_classification(classification, "521234567890")
        # REGISTRAR_CLIENTE → COTIZAR_SERVICIO → CONSULTAR_DISPONIBILIDAD → AGENDAR_CITA
        assert len(new) == 4
        assert [g["goal_type"] for g in new] == [
            "REGISTRAR_CLIENTE", "COTIZAR_SERVICIO", "CONSULTAR_DISPONIBILIDAD", "AGENDAR_CITA"
        ]

    def test_flow_goal_dependencies_block(self):
        ot = ObjectiveTracker()
        classification = {"intencion_principal": "COTIZACION", "confianza": 0.9,
                          "entidades": {"servicio_solicitado": "frenos"}}
        new = ot.detect_from_classification(classification, "521234567890")
        # g1 = REGISTRAR, g2 = COTIZAR (depends on g1)
        g1_id = new[0]["goal_id"]
        g2_id = new[1]["goal_id"]
        assert g2_id in [g["goal_id"] for g in ot.goals]

        # Antes de completar g1, g2 está bloqueado
        next_g = ot.next_executable()
        assert next_g["goal_id"] == g1_id

        # Completar g1 → g2 se desbloquea
        ot.on_tool_success(g1_id, {"success": True})
        next_g = ot.next_executable()
        assert next_g["goal_id"] == g2_id

    def test_flow_cotizacion_to_agendamiento_state_machine(self):
        sm = StateMachine("COTIZACION")
        assert sm.current == "USUARIO_PREGUNTA"
        sm.transition("CLASIFICAR")
        assert sm.current == "CLASIFICANDO"
        sm.transition("ALTA_CONFIANZA")
        assert sm.current == "CONSULTANDO_PRECIO"
        sm.transition("PRECIO_OBTENIDO")
        assert sm.current == "PRECIO_ENTREGADO"
        sm.transition("USUARIO_AGENDA")
        # AGENDAMIENTO es estado terminal con submachine reference
        assert sm.current == "AGENDAMIENTO"

    def test_flow_agendamiento_completo(self):
        sm = StateMachine("AGENDAMIENTO")
        assert sm.current == "SOLICITANDO_DATOS"
        sm.transition("DATOS_COMPLETOS")
        assert sm.current == "CONSULTANDO_DISPONIBILIDAD"
        sm.transition("HORARIOS_MOSTRADOS")
        assert sm.current == "ESPERANDO_SELECCION"
        ok, _ = sm.transition("USUARIO_ELIGE")
        assert ok is True
        assert sm.current == "CONFIRMANDO_CITA"
        sm.transition("CONFIRMADO")
        assert sm.current == "CITA_PROGRAMADA"

    def test_flow_diagnostico_completo(self):
        sm = StateMachine("DIAGNOSTICO")
        sm.transition("CLASIFICAR")
        assert sm.current == "CLASIFICANDO_SINTOMAS"
        sm.transition("SISTEMA_IDENTIFICADO")
        assert sm.current == "PREGUNTAS_DIAGNOSTICO"
        sm.transition("USUARIO_RESPONDE")
        assert sm.current == "CAUSAS_POSIBLES"
        sm.transition("REQUIERE_REVISION")
        assert sm.current == "SUGERIR_REVISION"

    def test_flow_queja_completo(self):
        sm = StateMachine("QUEJA")
        sm.transition("CLASIFICAR")
        assert sm.current == "REGISTRANDO_QUEJA"
        sm.transition("QUEJA_REGISTRADA")
        assert sm.current == "ESCALADO_A_TALLER"
        sm.transition("TALLER_RESPONDE")
        assert sm.current == "RESPUESTA_TALLER"
        sm.transition("SOLUCION")
        assert sm.current == "SOLUCION_PROPUESTA"
        ok, _ = sm.transition("USUARIO_ACEPTA")
        assert ok is True
        assert sm.current == "CITA_REVISION"

    def test_flow_seguimiento(self):
        sm = StateMachine("SEGUIMIENTO")
        sm.transition("INICIAR")
        assert sm.current == "ESPERANDO_VENTANA"
        sm.transition("PASARON_3_DIAS")
        assert sm.current == "ENVIANDO_MENSAJE"
        sm.transition("ENVIADO")
        assert sm.current == "ESPERANDO_RESPUESTA"


# ============================================================
# PLANNER FLOW INTEGRATION TESTS
# ============================================================

class TestPlannerFlows:
    @pytest.mark.asyncio
    async def test_full_cotizacion_plan(self):
        planner = Planner()
        context = {
            "goals": [
                {"goal_id": "g1", "goal_type": "REGISTRAR_CLIENTE", "status": "ACTIVE",
                 "priority": 1, "input": {"telefono": "521234567890"}},
                {"goal_id": "g2", "goal_type": "COTIZAR_SERVICIO", "status": "ACTIVE",
                 "priority": 2, "input": {"servicio": "frenos"}, "dependencies": ["g1"]},
            ],
            "classification": {"intencion_principal": "COTIZACION"},
            "telefono": "521234567890",
        }
        plan = await planner.generate_plan(context)
        steps = [s["tool"] for s in plan if s["action"] == "tool_call"]
        assert steps == ["registrar_cliente", "cotizar_servicio"]

    @pytest.mark.asyncio
    async def test_full_agendamiento_plan(self):
        planner = Planner()
        context = {
            "goals": [
                {"goal_id": "g1", "goal_type": "REGISTRAR_CLIENTE", "status": "ACTIVE",
                 "priority": 1, "input": {"telefono": "521234567890"}},
                {"goal_id": "g2", "goal_type": "CONSULTAR_DISPONIBILIDAD", "status": "ACTIVE",
                 "priority": 2, "input": {"fecha": "2024-12-25"}, "dependencies": ["g1"]},
                {"goal_id": "g3", "goal_type": "AGENDAR_CITA", "status": "ACTIVE",
                 "priority": 3, "input": {"telefono": "521234567890", "servicio": "frenos",
                                           "fecha": "2024-12-25"}, "dependencies": ["g2"]},
            ],
            "classification": {"intencion_principal": "AGENDAMIENTO"},
            "telefono": "521234567890",
        }
        plan = await planner.generate_plan(context)
        steps = [s["tool"] for s in plan if s["action"] == "tool_call"]
        assert steps == ["registrar_cliente", "consultar_disponibilidad", "agendar_cita"]

    @pytest.mark.asyncio
    async def test_flow_multiturn_simulation(self):
        """Simula: saludo → cotización → agendar"""
        ot = ObjectiveTracker()
        sm = StateMachine("COTIZACION")
        planner = Planner()

        # Turno 1: Saludo
        c1 = {"intencion_principal": "SALUDO", "confianza": 0.9, "entidades": {}}
        ot.detect_from_classification(c1, "521234567890")
        assert len(ot.goals) == 0

        # Turno 2: Cotización
        c2 = {"intencion_principal": "COTIZACION", "confianza": 0.9,
              "entidades": {"servicio_solicitado": "frenos"}}
        new = ot.detect_from_classification(c2, "521234567890")
        assert len(new) == 2  # REGISTRAR + COTIZAR

        # Turno 3: Después de ejecutar herramientas
        g1 = new[0]
        ot.on_tool_success(g1["goal_id"], {"success": True, "data": {"cliente_id": 1}})
        g2 = new[1]
        ot.on_tool_success(g2["goal_id"], {"success": True, "data": {"precios": [{"servicio": "Frenos", "precio_min": "350"}]}})

        assert all(g["status"] == "COMPLETED" for g in ot.goals)


# ============================================================
# MESSAGE PROCESSOR INITIALIZATION TESTS
# ============================================================

class TestMessageProcessorInit:
    def test_instantiation_no_exception(self):
        mp = MessageProcessor()
        assert mp is not None

    def test_generator_has_prompt_builder(self):
        mp = MessageProcessor()
        assert mp.generator.prompt_builder is not None

    def test_prompt_builder_is_prompt_orchestrator(self):
        mp = MessageProcessor()
        assert isinstance(mp.generator.prompt_builder, PromptOrchestrator)

    def test_prompt_builder_is_shared_instance(self):
        mp = MessageProcessor()
        assert mp.prompt_builder is mp.generator.prompt_builder
