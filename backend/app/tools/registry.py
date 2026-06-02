import json
from dataclasses import dataclass, field
from typing import Callable, Any, Optional


@dataclass
class ToolDefinition:
    name: str
    description: str
    category: str
    input_schema: dict
    output_schema: dict
    handler: Callable
    timeout: int = 30
    requires_confirmation: bool = False
    blocking: bool = True
    extra_validators: list[Callable] = field(default_factory=list)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def get_by_category(self, category: str) -> list[ToolDefinition]:
        return [t for t in self._tools.values() if t.category == category]

    def list(self) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "input_schema": t.input_schema,
                "output_schema": t.output_schema,
                "requires_confirmation": t.requires_confirmation,
                "blocking": t.blocking,
            }
            for t in self._tools.values()
        ]

    def resolve_for_goal(self, goal_type: str) -> Optional[str]:
        mapping = {
            "REGISTRAR_CLIENTE": "registrar_cliente",
            "COTIZAR_SERVICIO": "cotizar_servicio",
            "CONSULTAR_DISPONIBILIDAD": "consultar_disponibilidad",
            "AGENDAR_CITA": "agendar_cita",
            "RESOLVER_QUEJA": "registrar_queja",
            "DIAGNOSTICAR_FALLA": "diagnosticar_falla",
            "ENVIAR_MENSAJE": "enviar_mensaje_whatsapp",
            "CONSULTAR_HISTORIAL": "consultar_historial_cliente",
        }
        tool_name = mapping.get(goal_type)
        if tool_name and tool_name in self._tools:
            return tool_name
        return None

    def build_tool_context(self) -> str:
        lines = []
        for name, tool in self._tools.items():
            lines.append(f"- {name}: {tool.description}")
            lines.append(f"  Params: {json.dumps(tool.input_schema.get('properties', {}), ensure_ascii=False)}")
        return "\n".join(lines) if lines else "No hay herramientas disponibles."
