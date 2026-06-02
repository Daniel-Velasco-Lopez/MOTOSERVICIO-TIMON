import json
from typing import Optional


STATE_MACHINES = {
    "COTIZACION": {
        "initial": "USUARIO_PREGUNTA",
        "states": {
            "USUARIO_PREGUNTA": {
                "on": {"CLASIFICAR": "CLASIFICANDO"},
                "actions": {},
            },
            "CLASIFICANDO": {
                "on": {
                    "ALTA_CONFIANZA": "CONSULTANDO_PRECIO",
                    "BAJA_CONFIANZA": "PREGUNTAR_ACLARACION",
                },
                "actions": {"entry": "clasificar_intencion"},
            },
            "CONSULTANDO_PRECIO": {
                "on": {"PRECIO_OBTENIDO": "PRECIO_ENTREGADO", "ERROR": "ERROR_COTIZACION"},
                "actions": {"entry": "consultar_precio"},
            },
            "PRECIO_ENTREGADO": {
                "on": {
                    "USUARIO_AGENDA": "AGENDAMIENTO",
                    "USUARIO_PREGUNTA_MAS": "PREGUNTA_ADICIONAL",
                    "USUARIO_FIN": "CERRADO",
                },
                "actions": {"entry": "entregar_precio"},
            },
            "PREGUNTA_ADICIONAL": {
                "on": {"CLASIFICAR": "CLASIFICANDO"},
                "actions": {},
            },
            "PREGUNTAR_ACLARACION": {
                "on": {"USUARIO_RESPONDE": "USUARIO_PREGUNTA"},
                "actions": {"entry": "preguntar_aclaracion"},
            },
            "ERROR_COTIZACION": {
                "on": {"REINTENTAR": "CONSULTANDO_PRECIO", "CANCELAR": "CERRADO"},
                "actions": {"entry": "ofrecer_alternativa"},
            },
            "AGENDAMIENTO": {
                "on": {},
                "actions": {},
                "submachine": "AGENDAMIENTO",
            },
            "CERRADO": {"on": {}, "actions": {}},
        },
    },
    "AGENDAMIENTO": {
        "initial": "SOLICITANDO_DATOS",
        "states": {
            "SOLICITANDO_DATOS": {
                "on": {
                    "DATOS_COMPLETOS": "CONSULTANDO_DISPONIBILIDAD",
                    "FALTA_SERVICIO": "ESPERANDO_SERVICIO",
                    "FALTA_FECHA": "ESPERANDO_FECHA",
                    "FALTA_HORA": "ESPERANDO_HORA",
                },
                "actions": {"entry": "solicitar_datos_faltantes"},
            },
            "ESPERANDO_SERVICIO": {
                "on": {"USUARIO_RESPONDE": "SOLICITANDO_DATOS"},
                "actions": {"entry": "preguntar_servicio"},
            },
            "ESPERANDO_FECHA": {
                "on": {"USUARIO_RESPONDE": "SOLICITANDO_DATOS"},
                "actions": {"entry": "preguntar_fecha"},
            },
            "ESPERANDO_HORA": {
                "on": {"USUARIO_RESPONDE": "SOLICITANDO_DATOS"},
                "actions": {"entry": "preguntar_hora"},
            },
            "CONSULTANDO_DISPONIBILIDAD": {
                "on": {
                    "HORARIOS_MOSTRADOS": "ESPERANDO_SELECCION",
                    "NO_DISPONIBLE": "NO_DISPONIBLE",
                    "ERROR": "ERROR_DISPONIBILIDAD",
                },
                "actions": {"entry": "consultar_disponibilidad"},
            },
            "ESPERANDO_SELECCION": {
                "on": {
                    "USUARIO_ELIGE": "CONFIRMANDO_CITA",
                    "USUARIO_RECHAZA": "SOLICITANDO_DATOS",
                },
                "actions": {"entry": "mostrar_horarios"},
            },
            "CONFIRMANDO_CITA": {
                "on": {
                    "CONFIRMADO": "CITA_PROGRAMADA",
                    "RECHAZADO": "SOLICITANDO_DATOS",
                },
                "actions": {"entry": "confirmar_cita"},
            },
            "CITA_PROGRAMADA": {
                "on": {"USUARIO_FIN": "CERRADO", "SEGUIMIENTO": "SEGUIMIENTO"},
                "actions": {"entry": "programar_cita"},
            },
            "NO_DISPONIBLE": {
                "on": {"USUARIO_OTRA_FECHA": "SOLICITANDO_DATOS", "CANCELAR": "CERRADO"},
                "actions": {"entry": "informar_no_disponible"},
            },
            "ERROR_DISPONIBILIDAD": {
                "on": {"REINTENTAR": "CONSULTANDO_DISPONIBILIDAD", "CANCELAR": "CERRADO"},
                "actions": {"entry": "ofrecer_alternativa"},
            },
            "CERRADO": {"on": {}, "actions": {}},
        },
    },
    "DIAGNOSTICO": {
        "initial": "USUARIO_DESCRIBE_FALLA",
        "states": {
            "USUARIO_DESCRIBE_FALLA": {
                "on": {"CLASIFICAR": "CLASIFICANDO_SINTOMAS"},
                "actions": {},
            },
            "CLASIFICANDO_SINTOMAS": {
                "on": {
                    "SISTEMA_IDENTIFICADO": "PREGUNTAS_DIAGNOSTICO",
                    "SINTOMAS_INSUFICIENTES": "PREGUNTAR_MAS_SINTOMAS",
                },
                "actions": {"entry": "clasificar_sintomas"},
            },
            "PREGUNTAS_DIAGNOSTICO": {
                "on": {"USUARIO_RESPONDE": "CAUSAS_POSIBLES"},
                "actions": {"entry": "hacer_preguntas_diagnostico"},
            },
            "CAUSAS_POSIBLES": {
                "on": {
                    "SOLUCION_SIMPLE": "RECOMENDACION",
                    "REQUIERE_REVISION": "SUGERIR_REVISION",
                },
                "actions": {"entry": "presentar_causas"},
            },
            "RECOMENDACION": {
                "on": {"USUARIO_AGENDA": "AGENDAMIENTO", "USUARIO_FIN": "CERRADO"},
                "actions": {"entry": "dar_recomendacion"},
            },
            "SUGERIR_REVISION": {
                "on": {"USUARIO_AGENDA": "AGENDAMIENTO", "USUARIO_FIN": "CERRADO"},
                "actions": {"entry": "sugerir_revision"},
            },
            "PREGUNTAR_MAS_SINTOMAS": {
                "on": {"USUARIO_RESPONDE": "USUARIO_DESCRIBE_FALLA"},
                "actions": {"entry": "preguntar_mas_sintomas"},
            },
            "CERRADO": {"on": {}, "actions": {}},
        },
    },
    "QUEJA": {
        "initial": "USUARIO_REPORTA",
        "states": {
            "USUARIO_REPORTA": {
                "on": {"CLASIFICAR": "REGISTRANDO_QUEJA"},
                "actions": {},
            },
            "REGISTRANDO_QUEJA": {
                "on": {
                    "QUEJA_REGISTRADA": "ESCALADO_A_TALLER",
                    "ERROR": "ERROR_QUEJA",
                },
                "actions": {"entry": "registrar_queja"},
            },
            "ESCALADO_A_TALLER": {
                "on": {"TALLER_RESPONDE": "RESPUESTA_TALLER"},
                "actions": {"entry": "escalar_a_taller"},
            },
            "RESPUESTA_TALLER": {
                "on": {"SOLUCION": "SOLUCION_PROPUESTA", "NO_SOLUCION": "ESCALAR_A_GERENTE"},
                "actions": {"entry": "recibir_respuesta_taller"},
            },
            "SOLUCION_PROPUESTA": {
                "on": {
                    "USUARIO_ACEPTA": "CITA_REVISION",
                    "USUARIO_RECHAZA": "ESCALAR_A_GERENTE",
                },
                "actions": {"entry": "presentar_solucion"},
            },
            "CITA_REVISION": {
                "on": {},
                "actions": {"entry": "derivar_a_agendamiento"},
            },
            "ESCALAR_A_GERENTE": {
                "on": {},
                "actions": {"entry": "escalar_a_gerente"},
            },
            "ERROR_QUEJA": {
                "on": {"REINTENTAR": "REGISTRANDO_QUEJA", "CANCELAR": "CERRADO"},
                "actions": {"entry": "ofrecer_llamada"},
            },
            "CERRADO": {"on": {}, "actions": {}},
        },
    },
    "SEGUIMIENTO": {
        "initial": "CITA_COMPLETADA",
        "states": {
            "CITA_COMPLETADA": {
                "on": {"INICIAR": "ESPERANDO_VENTANA"},
                "actions": {},
            },
            "ESPERANDO_VENTANA": {
                "on": {"PASARON_3_DIAS": "ENVIANDO_MENSAJE"},
                "actions": {},
            },
            "ENVIANDO_MENSAJE": {
                "on": {"ENVIADO": "ESPERANDO_RESPUESTA", "ERROR": "NOTIFICAR_ADMIN"},
                "actions": {"entry": "enviar_mensaje_seguimiento"},
            },
            "ESPERANDO_RESPUESTA": {
                "on": {
                    "TODO_BIEN": "SATISFECHO",
                    "PROBLEMA": "DERIVAR_A_QUEJA",
                    "SIN_RESPUESTA": "ESPERANDO_REINTENTO",
                },
                "actions": {},
            },
            "ESPERANDO_REINTENTO": {
                "on": {"PASARON_24H": "ENVIANDO_MENSAJE"},
                "actions": {},
            },
            "SATISFECHO": {"on": {}, "actions": {}},
            "DERIVAR_A_QUEJA": {"on": {}, "actions": {}},
            "NOTIFICAR_ADMIN": {"on": {}, "actions": {}},
        },
    },
}


class StateMachine:
    def __init__(self, domain: str = "COTIZACION"):
        self.domain = domain
        self.config = STATE_MACHINES.get(domain, STATE_MACHINES["COTIZACION"])
        self.current = self.config["initial"]
        self.previous = None
        self.data = {}

    def transition(self, event: str) -> tuple[bool, Optional[str]]:
        state_config = self.config["states"].get(self.current)
        if not state_config:
            return False, f"Estado '{self.current}' no encontrado en {self.domain}"

        transitions = state_config.get("on", {})
        if event not in transitions:
            return False, f"Evento '{event}' no válido desde estado '{self.current}' en {self.domain}"

        next_state = transitions[event]

        if isinstance(next_state, str):
            self.previous = self.current
            self.current = next_state

            entry_action = self.config["states"].get(self.current, {}).get("actions", {}).get("entry")
            return True, entry_action

        if isinstance(next_state, dict):
            self.previous = self.current
            self.current = next_state.get("state", self.current)
            self.data.update(next_state.get("data", {}))

            entry_action = self.config["states"].get(self.current, {}).get("actions", {}).get("entry")
            return True, entry_action

        return False, None

    def can_transition(self, event: str) -> bool:
        state_config = self.config["states"].get(self.current)
        if not state_config:
            return False
        return event in state_config.get("on", {})

    def get_possible_events(self) -> list[str]:
        state_config = self.config["states"].get(self.current)
        if not state_config:
            return []
        return list(state_config.get("on", {}).keys())

    def get_entry_action(self) -> Optional[str]:
        return self.config["states"].get(self.current, {}).get("actions", {}).get("entry")

    def switch_domain(self, domain: str):
        if domain in STATE_MACHINES:
            self.domain = domain
            self.config = STATE_MACHINES[domain]
            self.current = self.config["initial"]
            self.previous = None
            self.data = {}

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "current": self.current,
            "previous": self.previous,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StateMachine":
        sm = cls(data.get("domain", "COTIZACION"))
        sm.current = data.get("current", sm.config["initial"])
        sm.previous = data.get("previous")
        sm.data = data.get("data", {})
        return sm

    def get_user_facing_state(self) -> str:
        friendly = {
            "NUEVA_CONSULTA": "NUEVA_CONSULTA",
            "USUARIO_PREGUNTA": "CLASIFICANDO",
            "CLASIFICANDO": "CLASIFICANDO",
            "CONSULTANDO_PRECIO": "CONSULTANDO",
            "PRECIO_ENTREGADO": "RESPONDIENDO",
            "PREGUNTA_ADICIONAL": "CLASIFICANDO",
            "PREGUNTAR_ACLARACION": "ESPERANDO_USUARIO",
            "SOLICITANDO_DATOS": "ESPERANDO_USUARIO",
            "ESPERANDO_SERVICIO": "ESPERANDO_USUARIO",
            "ESPERANDO_FECHA": "ESPERANDO_USUARIO",
            "ESPERANDO_HORA": "ESPERANDO_USUARIO",
            "CONSULTANDO_DISPONIBILIDAD": "CONSULTANDO",
            "ESPERANDO_SELECCION": "ESPERANDO_USUARIO",
            "CONFIRMANDO_CITA": "ESPERANDO_USUARIO",
            "CITA_PROGRAMADA": "RESPONDIENDO",
            "CERRADO": "CERRADA",
        }
        return friendly.get(self.current, self.current)
