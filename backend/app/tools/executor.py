import json
import time
import logging
from typing import Optional

from app.tools.registry import ToolRegistry
from app.tools.definitions import TOOL_HANDLERS
from app.tools.registry import ToolDefinition

logger = logging.getLogger(__name__)


class ToolRegistryBuilder:
    def __init__(self):
        self.registry = ToolRegistry()
        self._load_builtin()

    def _load_builtin(self):
        self.registry.register(ToolDefinition(
            name="registrar_cliente",
            description="Registra un nuevo cliente en el sistema o actualiza sus datos si ya existe.",
            category="clientes",
            input_schema={
                "type": "object",
                "properties": {
                    "telefono": {"type": "string", "description": "Número de WhatsApp del cliente"},
                    "nombre": {"type": "string", "description": "Nombre del cliente"},
                },
                "required": ["telefono"],
            },
            output_schema={"type": "object", "properties": {"cliente_id": {"type": "integer"}, "nombre": {"type": "string"}}},
            handler=TOOL_HANDLERS["registrar_cliente"],
        ))
        self.registry.register(ToolDefinition(
            name="cotizar_servicio",
            description="Obtiene el precio de un servicio específico (mantenimiento, reparación, etc.)",
            category="servicios",
            input_schema={
                "type": "object",
                "properties": {
                    "servicio": {"type": "string", "description": "Nombre del servicio a cotizar"},
                },
                "required": ["servicio"],
            },
            output_schema={"type": "object", "properties": {"precios": {"type": "array"}}},
            handler=TOOL_HANDLERS["cotizar_servicio"],
        ))
        self.registry.register(ToolDefinition(
            name="consultar_disponibilidad",
            description="Consulta horarios disponibles para agendar una cita en una fecha específica.",
            category="agenda",
            input_schema={
                "type": "object",
                "properties": {
                    "fecha": {"type": "string", "description": "Fecha en formato YYYY-MM-DD"},
                    "servicio": {"type": "string", "description": "Tipo de servicio"},
                },
                "required": ["fecha"],
            },
            output_schema={"type": "object", "properties": {"horarios": {"type": "array"}, "hay_disponibilidad": {"type": "boolean"}}},
            handler=TOOL_HANDLERS["consultar_disponibilidad"],
        ))
        self.registry.register(ToolDefinition(
            name="agendar_cita",
            description="Agenda una cita de servicio para un cliente en una fecha y hora específicas.",
            category="agenda",
            input_schema={
                "type": "object",
                "properties": {
                    "telefono": {"type": "string", "description": "WhatsApp del cliente"},
                    "servicio": {"type": "string", "description": "Servicio solicitado"},
                    "fecha": {"type": "string", "description": "Fecha en formato YYYY-MM-DD"},
                    "hora": {"type": "string", "description": "Hora en formato HH:MM"},
                },
                "required": ["telefono", "servicio", "fecha"],
            },
            output_schema={"type": "object", "properties": {"cita_id": {"type": "integer"}, "fecha": {"type": "string"}}},
            handler=TOOL_HANDLERS["agendar_cita"],
        ))
        self.registry.register(ToolDefinition(
            name="registrar_queja",
            description="Registra una queja o inconformidad de un cliente.",
            category="clientes",
            input_schema={
                "type": "object",
                "properties": {
                    "telefono": {"type": "string", "description": "WhatsApp del cliente"},
                    "descripcion": {"type": "string", "description": "Descripción de la queja"},
                    "urgencia": {"type": "string", "enum": ["baja", "media", "alta"]},
                },
                "required": ["telefono", "descripcion"],
            },
            output_schema={"type": "object", "properties": {"queja_id": {"type": "integer"}, "ticket": {"type": "string"}}},
            handler=TOOL_HANDLERS["registrar_queja"],
        ))
        self.registry.register(ToolDefinition(
            name="diagnosticar_falla",
            description="Diagnostica una posible falla basada en los síntomas descritos.",
            category="servicios",
            input_schema={
                "type": "object",
                "properties": {
                    "sintomas": {"type": "string", "description": "Síntomas descritos por el cliente"},
                },
                "required": ["sintomas"],
            },
            output_schema={"type": "object", "properties": {"diagnostico": {"type": "string"}, "causas": {"type": "array"}}},
            handler=TOOL_HANDLERS["diagnosticar_falla"],
        ))
        self.registry.register(ToolDefinition(
            name="enviar_mensaje_whatsapp",
            description="Envía un mensaje de WhatsApp al cliente.",
            category="comunicacion",
            input_schema={
                "type": "object",
                "properties": {
                    "telefono": {"type": "string", "description": "Número destino"},
                    "mensaje": {"type": "string", "description": "Contenido del mensaje"},
                },
                "required": ["telefono", "mensaje"],
            },
            output_schema={"type": "object", "properties": {"status": {"type": "string"}}},
            handler=TOOL_HANDLERS["enviar_mensaje_whatsapp"],
            blocking=False,
        ))
        self.registry.register(ToolDefinition(
            name="consultar_historial_cliente",
            description="Obtiene el historial de citas y quejas de un cliente.",
            category="clientes",
            input_schema={
                "type": "object",
                "properties": {
                    "telefono": {"type": "string", "description": "WhatsApp del cliente"},
                },
                "required": ["telefono"],
            },
            output_schema={"type": "object", "properties": {"citas": {"type": "array"}, "quejas": {"type": "array"}}},
            handler=TOOL_HANDLERS["consultar_historial_cliente"],
        ))


TOOL_REGISTRY = ToolRegistryBuilder().registry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry = None):
        self.registry = registry or TOOL_REGISTRY

    async def execute(self, tool_name: str, params: dict, timeout: int = None) -> dict:
        tool = self.registry.get(tool_name)
        if not tool:
            return {"success": False, "error": f"Tool '{tool_name}' no encontrada"}

        if not self._validate_input(tool, params):
            return {"success": False, "error": f"Parámetros inválidos para {tool_name}"}

        logger.info(f"Ejecutando tool: {tool_name} params={params}")
        start = time.time()

        try:
            result = await tool.handler(params)
            elapsed = time.time() - start
            result["_execution_time_ms"] = int(elapsed * 1000)
            result["_tool_name"] = tool_name
            result["_tool_category"] = tool.category
            return result
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"Tool {tool_name} failed after {elapsed:.2f}s: {e}")
            return {"success": False, "error": str(e), "_execution_time_ms": int(elapsed * 1000), "_tool_name": tool_name}

    def _validate_input(self, tool: ToolDefinition, params: dict) -> bool:
        required = tool.input_schema.get("required", [])
        for field in required:
            if field not in params or params[field] is None or params[field] == "":
                logger.warning(f"Validación falló para {tool.name}: falta campo requerido '{field}'")
                return False
        return True

    def get_result_summary(self, result: dict) -> str:
        if not result.get("success"):
            return f"Error: {result.get('error', 'desconocido')}"
        data = result.get("data", {})
        if "mensaje" in data:
            return data["mensaje"]
        if "precios" in data:
            precios = data["precios"]
            if precios:
                return " | ".join(f"{p['servicio']}: ${p.get('precio_min', 0)}-${p.get('precio_max', 0)}" for p in precios[:3])
        if "horarios" in data:
            horarios = data["horarios"]
            return f"{len(horarios)} horarios disponibles"
        if "cita_id" in data:
            return f"Cita #{data['cita_id']} agendada"
        if "queja_id" in data:
            return f"Queja #{data['queja_id']} registrada"
        if "diagnostico_gemini" in data:
            return str(data["diagnostico_gemini"])[:200]
        return "Completado"
