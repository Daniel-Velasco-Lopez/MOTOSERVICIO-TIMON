# AGENT RUNTIME — EL CEREBRO REAL DEL SISTEMA

## Diseño Operativo del Núcleo Cognitivo para MotoServicio Timón

---

## PARTE 1 — AGENT RUNTIME COMPLETO

### Diagrama de ejecución

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. RECEPCIÓN                      ENTRADA: raw_message                  │
│    ├─ Validar estructura          SALIDA: validated_message             │
│    ├─ Rate limiter check                                                 │
│    └─ Sanitizar                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │ validated_message
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. CONTEXT BUILD (paralelo)      ENTRADA: validated_message + telefono  │
│    ├─ SessionLoader              SALIDA: ContextWindow                  │
│    ├─ ProfileLoader              2.1 session (Redis)                    │
│    ├─ EpisodicLoader             2.2 perfil (MySQL)                     │
│    ├─ RAGLoader                  2.3 episódica (Qdrant)                 │
│    └─ HistoryLoader              2.4 RAG (Qdrant)                      │
│                                  2.5 historial (MySQL)                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │ ContextWindow
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. CLASSIFY                        ENTRADA: ContextWindow               │
│    ├─ IntentClassifier            SALIDA: Classification                │
│    └─ EntityExtractor             3.1 intención principal               │
│                                   3.2 intenciones secundarias           │
│                                   3.3 entidades extraídas               │
│                                   3.4 confianza                         │
│                                   3.5 objetivos sugeridos               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │ Classification
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. GOAL MANAGER                    ENTRADA: Classification + Session    │
│    ├─ GoalDetector                SALIDA: ActiveGoals                   │
│    ├─ GoalResolver                4.1 detectar nuevos objetivos          │
│    └─ GoalPrioritizer            4.2 resolver objetivos previos         │
│                                   4.3 priorizar objetivos activos       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │ ActiveGoals
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 5. PLANNER                         ENTRADA: ActiveGoals + Context       │
│    ├─ PlanCreator                 SALIDA: ExecutionPlan                 │
│    └─ DependencyResolver          5.1 pasos ordenados                   │
│                                   5.2 dependencias                      │
│                                   5.3 herramientas requeridas            │
│                                   5.4 modo (secuencial/paralelo)        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │ ExecutionPlan
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 6. EXECUTOR                        ENTRADA: ExecutionPlan               │
│    ├─ ToolSelector                SALIDA: ToolResults                   │
│    ├─ ToolRunner                  6.1 seleccionar herramienta           │
│    ├─ ResultValidator             6.2 ejecutar (con timeout)            │
│    └─ FallbackHandler             6.3 validar resultado                 │
│                                   6.4 manejar errores                   │
│                                   6.5 actualizar objetivos              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │ ToolResults
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 7. CONTEXT REFRESH                ENTRADA: ContextWindow + ToolResults  │
│    ├─ RebuildContext              SALIDA: FinalContextWindow            │
│    └─ UpdateObjectives            7.1 mergear tool results en contexto  │
│                                   7.2 actualizar estado de objetivos    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │ FinalContextWindow
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 8. PROMPT ORCHESTRATOR            ENTRADA: FinalContextWindow           │
│    ├─ SectionBuilder              SALIDA: FinalPrompt                   │
│    ├─ TokenManager                8.1 ensamblar secciones en orden      │
│    └─ TokenBudgetValidator        8.2 verificar límite 3000 tokens      │
│                                   8.3 truncar si excede                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │ FinalPrompt
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 9. GENERATOR                       ENTRADA: FinalPrompt                 │
│    └─ LLM.generate()              SALIDA: RawResponse                   │
│                                   9.1 temperature 0.8                   │
│                                   9.2 respuesta en texto                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │ RawResponse
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 10. REFLECTION LOOP               ENTRADA: RawResponse + Context        │
│    ├─ ResponseValidator           SALIDA: ValidatedResponse             │
│    └─ Regenerator                 10.1 verificar alucinaciones          │
│                                   10.2 verificar coherencia             │
│                                   10.3 verificar completitud            │
│                                   10.4 si falla: regenerar + feedback   │
│                                   10.5 máximo 2 intentos                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │ ValidatedResponse
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 11. MEMORY WRITE (paralelo)      ENTRADA: ValidatedResponse + Session   │
│    ├─ HistoryWriter              SALIDA: (side effects)                 │
│    ├─ EmbeddingEnqueuer          11.1 guardar en MySQL mensajes         │
│    ├─ ProfileUpdater             11.2 encolar embeddings a Qdrant       │
│    ├─ SummaryChecker             11.3 actualizar perfil si cambió       │
│    └─ SessionUpdater             11.4 resumir si es momento             │
│                                   11.5 actualizar Redis session         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │ updated_session
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 12. RESPONDER                    ENTRADA: ValidatedResponse             │
│    └─ Return response             SALIDA: JSON a n8n                    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Consumo y producción de datos por etapa

| Etapa | Consume | Produce | Tiempo máximo |
|-------|---------|---------|--------------|
| 1. Recepción | `raw_message` (JSON de Evolution) | `validated_message` + telefono | 50ms |
| 2. Context Build | telefono + mensaje | `ContextWindow` (session, perfil, episódica, RAG, historial) | 800ms |
| 3. Classify | `ContextWindow` | `Classification` (intención, entidades, confianza, objetivos) | 500ms |
| 4. Goal Manager | `Classification` + `Session` | `ActiveGoals[]` | 50ms |
| 5. Planner | `ActiveGoals` + `Context` | `ExecutionPlan` (pasos[] con tool, params, dependencias) | 300ms |
| 6. Executor | `ExecutionPlan` | `ToolResults[]` (1 por tool ejecutada) | 10s total |
| 7. Context Refresh | `ContextWindow` + `ToolResults` | `FinalContextWindow` | 50ms |
| 8. Prompt Orchestrator | `FinalContextWindow` | `FinalPrompt` (< 3000 tokens) | 100ms |
| 9. Generator | `FinalPrompt` | `RawResponse` | 2s |
| 10. Reflection | `RawResponse` + `Context` | `ValidatedResponse` (o feedback + regenerate) | 1s |
| 11. Memory Write | `ValidatedResponse` + `Session` | Side effects (MySQL, Redis, Qdrant) | 200ms |

**Tiempo total síncrono máximo:** ~14s (usuario percibe respuesta en 3-5s con optimización).

---

## PARTE 2 — GOAL MANAGER

### ¿Qué es un objetivo?

Un objetivo es una **unidad atómica de trabajo conversacional** que el sistema debe completar para satisfacer la intención del usuario. A diferencia de las intenciones (qué quiere el usuario), los objetivos son **quién hace qué y en qué orden**.

### Tipos de objetivos

| Tipo | Propósito | Dependencias típicas |
|------|-----------|---------------------|
| `REGISTRAR_CLIENTE` | Crear o actualizar datos del cliente | Ninguna |
| `COTIZAR_SERVICIO` | Consultar precio de un servicio | `REGISTRAR_CLIENTE` |
| `CONSULTAR_DISPONIBILIDAD` | Verificar horarios disponibles | `COTIZAR_SERVICIO` |
| `AGENDAR_CITA` | Crear una cita en el calendario | `COTIZAR_SERVICIO` + `CONSULTAR_DISPONIBILIDAD` |
| `DIAGNOSTICAR_FALLA` | Identificar posible causa de una falla | `REGISTRAR_CLIENTE` |
| `RESOLVER_QUEJA` | Gestionar una queja del cliente | `REGISTRAR_CLIENTE` |
| `CONFIRMAR_CITA` | Obtener confirmación del usuario para agendar | `AGENDAR_CITA` |
| `ENVIAR_RECORDATORIO` | Programar recordatorio de cita | `CONFIRMAR_CITA` |
| `SEGUIMIENTO_POST` | Dar seguimiento post-servicio | `AGENDAR_CITA` + tiempo transcurrido |
| `CONSULTAR_HISTORIAL` | Recuperar historial del cliente | `REGISTRAR_CLIENTE` |

### Estructura completa

```json
{
  "goal_id": "g_abc12345",
  "goal_type": "COTIZAR_SERVICIO",
  "priority": 1,
  "status": "ACTIVE",
  "created_at": 1717171200,
  "updated_at": 1717171210,
  "session_id": "session:521234567890",
  "conversation_id": 5,
  "cliente_id": 2,
  "input": {
    "servicio": "cambio de aceite",
    "moto": "Italika FT150"
  },
  "output": null,
  "result": null,
  "dependencies": ["g_abc12344"],
  "blocked_by": null,
  "assigned_tool": "consultar_precio",
  "tool_params": {
    "servicio": "cambio de aceite",
    "moto": "Italika FT150"
  },
  "completion_conditions": {
    "type": "tool_success",
    "expected_keys": ["precio_min", "precio_max"]
  },
  "max_retries": 2,
  "retry_count": 0,
  "error": null,
  "metadata": {
    "source": "intent_classifier",
    "confianza": 0.95
  }
}
```

### Ciclo de vida

```
CREATED ──► ACTIVE ──► WAITING_TOOL ──► ACTIVE ──► COMPLETED
  │            │                            │
  │            ├──► WAITING_USER ────────► ACTIVE
  │            │       (pregunta al        (usuario respondió)
  │            │        usuario)
  │            │
  │            ├──► BLOCKED ──► ACTIVE
  │            │       (dependencia        (dependencia resuelta)
  │            │        no cumplida)
  │            │
  │            ├──► FAILED
  │            │       (tool error o
  │            │        retries agotados)
  │            │
  │            └──► CANCELLED
  │                    (usuario cambió
  │                     de tema)
  │
  └──────────────────────────────────────────────────► (murió aquí si no
              nunca se activó)                           se activó)
```

### Transiciones

| Desde | Hasta | Evento | Quién lo hace |
|-------|-------|--------|---------------|
| CREATED | ACTIVE | Planner asigna el goal a un paso del plan | `GoalManager.activate()` |
| ACTIVE | WAITING_TOOL | Executor comienza a ejecutar la tool asociada | `Executor.execute()` |
| WAITING_TOOL | ACTIVE | Tool devuelve resultado exitoso | `Executor.on_success()` |
| WAITING_TOOL | FAILED | Tool devuelve error o timeout | `Executor.on_error()` |
| ACTIVE | WAITING_USER | Goal requiere input del usuario (confirmación) | `Planner.detect_user_input_needed()` |
| WAITING_USER | ACTIVE | Usuario responde con la información necesaria | `GoalManager.on_user_response()` |
| ACTIVE | BLOCKED | Dependencia no cumplida detectada | `GoalManager.check_dependencies()` |
| BLOCKED | ACTIVE | Dependencia se cumple | `GoalManager.on_dependency_completed()` |
| ACTIVE | COMPLETED | Goal alcanza sus `completion_conditions` | `GoalManager.complete()` |
| ACTIVE | FAILED | Retry count excede max_retries | `Executor.on_retry_exhausted()` |
| ANY | CANCELLED | Usuario cambia de tema radicalmente | `GoalManager.cancel_all()` o `cancel_goal()` |
| COMPLETED | — | Fin del ciclo de vida | N/A |

### GoalManager pseudocódigo

```python
class GoalManager:
    def __init__(self, session: dict):
        self.goals: list[dict] = session.get("objetivos", [])
        self.changed = False

    def detect_from_classification(self, classification: dict) -> list[dict]:
        intent = classification.get("intencion_principal")
        entities = classification.get("entidades", {})
        new_goals = []

        if intent in ("COTIZACION", "INFORMACION"):
            g = self._create_goal("REGISTRAR_CLIENTE", priority=1,
                input={"telefono": entities.get("telefono")})
            new_goals.append(g)

            g2 = self._create_goal("COTIZAR_SERVICIO", priority=2,
                input={"servicio": entities.get("servicio_solicitado"),
                       "moto": entities.get("moto")},
                dependencies=[g["goal_id"]])
            new_goals.append(g2)

            if entities.get("pregunta_disponibilidad"):
                g3 = self._create_goal("CONSULTAR_DISPONIBILIDAD", priority=3,
                    input={"fecha": entities.get("fecha_mencionada", "hoy"),
                           "servicio": entities.get("servicio_solicitado")},
                    dependencies=[g2["goal_id"]])
                new_goals.append(g3)

        elif intent == "AGENDAMIENTO":
            g = self._create_goal("REGISTRAR_CLIENTE", priority=1)
            new_goals.append(g)
            g2 = self._create_goal("AGENDAR_CITA", priority=2,
                input={"servicio": entities.get("servicio_solicitado"),
                       "fecha": entities.get("fecha_mencionada"),
                       "hora": entities.get("hora_mencionada"),
                       "moto": entities.get("moto")},
                dependencies=[g["goal_id"]])
            new_goals.append(g2)

        elif intent == "QUEJA":
            g = self._create_goal("REGISTRAR_CLIENTE", priority=1)
            new_goals.append(g)
            g2 = self._create_goal("RESOLVER_QUEJA", priority=2,
                input={"descripcion": entities.get("descripcion", ""),
                       "urgencia": entities.get("urgencia", "media")},
                dependencies=[g["goal_id"]])
            new_goals.append(g2)

        elif intent == "DIAGNOSTICO":
            g = self._create_goal("REGISTRAR_CLIENTE", priority=1)
            new_goals.append(g)
            g2 = self._create_goal("DIAGNOSTICAR_FALLA", priority=2,
                input={"sintomas": entities.get("sintomas", ""),
                       "moto": entities.get("moto", "")},
                dependencies=[g["goal_id"]])
            new_goals.append(g2)

        self.goals.extend(new_goals)
        self.changed = True
        return new_goals

    def next_executable(self) -> Optional[dict]:
        ready = [g for g in self.goals
                 if g["status"] == "ACTIVE"
                 and not self._is_blocked(g)]
        if not ready:
            return None
        return min(ready, key=lambda g: g["priority"])

    def _is_blocked(self, goal: dict) -> bool:
        for dep_id in goal.get("dependencies", []):
            dep = self._find(dep_id)
            if dep and dep["status"] != "COMPLETED":
                return True
        return False

    def on_tool_success(self, goal_id: str, result: dict):
        goal = self._find(goal_id)
        if goal:
            goal["status"] = "COMPLETED"
            goal["result"] = result
            goal["updated_at"] = int(time.time())
            self.changed = True
            self._unblock_dependents(goal_id)

    def on_tool_failure(self, goal_id: str, error: str):
        goal = self._find(goal_id)
        if goal:
            goal["retry_count"] += 1
            if goal["retry_count"] >= goal["max_retries"]:
                goal["status"] = "FAILED"
                goal["error"] = error
            else:
                goal["status"] = "ACTIVE"  # reintentar
            goal["updated_at"] = int(time.time())
            self.changed = True

    def save_to_session(self) -> list[dict]:
        return self.goals
```

---

## PARTE 3 — CONVERSATION STATE MACHINE

### Diseño general

Cada dominio tiene su propia máquina de estados. El `session.estado` refleja el estado de la máquina activa. Un usuario solo puede estar en **una máquina a la vez**, pero las máquinas pueden anidarse (e.g., dentro de COTIZACION puede dispararse AGENDAMIENTO).

### 3.1 — Cotizaciones

```
                ┌──────────────────────────────────────────────────────────────┐
                │                MÁQUINA DE COTIZACIONES                       │
                └──────────────────────────────────────────────────────────────┘

USUARIO_PREGUNTA ──► CLASIFICANDO ──► CONSULTANDO_PRECIO ──► PRECIO_ENTREGADO
                        │                    │                      │
                        │                    │                      ├──► [usuario agenda] ──► AGENDAMIENTO
                        │                    │                      │
                        │                    │                      └──► [usuario pregunta más] ──► PREGUNTA_ADICIONAL
                        │                    │                                         │
                        │                    │                                         └──► CONSULTANDO_PRECIO
                        │                    │                                                (loop)
                        │                    │
                        │                    └──► [error] ──► ERROR_COTIZACION ──► OFRECER_ALTERNATIVA
                        │                                                          │
                        │                                                          ├──► [usuario acepta] ──► CONSULTANDO_PRECIO
                        │                                                          └──► [usuario rechaza] ──► CERRADO
                        │
                        └──► [baja confianza] ──► PREGUNTAR_ACLARACION
                                                       │
                                                       └──► USUARIO_PREGUNTA (con más detalles)

Eventos que causan transiciones:
  USUARIO_PREGUNTA → CLASIFICANDO: llega mensaje del usuario
  CLASIFICANDO → CONSULTANDO_PRECIO: intent = COTIZACION, confianza > 0.6
  CLASIFICANDO → PREGUNTAR_ACLARACION: confianza < 0.6
  CONSULTANDO_PRECIO → PRECIO_ENTREGADO: tool consultar_precio ok
  CONSULTANDO_PRECIO → ERROR_COTIZACION: tool error
  PRECIO_ENTREGADO → AGENDAMIENTO: usuario quiere agendar
  PRECIO_ENTREGADO → PREGUNTA_ADICIONAL: usuario pregunta otro servicio
  PREGUNTA_ADICIONAL → CONSULTANDO_PRECIO: nuevo servicio detectado

Datos que se almacenan en sesión:
  cotizacion.servicio
  cotizacion.moto
  cotizacion.precio_min
  cotizacion.precio_max
  cotizacion.incluye
```

### 3.2 — Agendamiento

```
                ┌──────────────────────────────────────────────────────────────┐
                │               MÁQUINA DE AGENDAMIENTO                       │
                └──────────────────────────────────────────────────────────────┘

INICIAR_AGENDAMIENTO ──► SOLICITANDO_DATOS ──► DATOS_COMPLETOS
        │                      │                      │
        │                      ├──► [falta servicio] ──► ESPERANDO_SERVICIO
        │                      │         │                  │
        │                      │         └──────────────────┘ (usuario responde)
        │                      │
        │                      ├──► [falta fecha] ──► ESPERANDO_FECHA
        │                      │         │                  │
        │                      │         └──────────────────┘ (usuario responde)
        │                      │
        │                      └──► [falta hora] ──► ESPERANDO_HORA
        │                                │                  │
        │                                └──────────────────┘ (usuario responde)
        │
        └──► [datos incompletos] ──► PREGUNTAR_DATOS_FALTANTES
                                            │
                                            └──► SOLICITANDO_DATOS

DATOS_COMPLETOS ──► CONSULTANDO_DISPONIBILIDAD ──► HORARIOS_MOSTRADOS
                            │                              │
                            │                              ├──► ESPERANDO_SELECCION_HORARIO
                            │                              │         │
                            │                              │         ├──► [elige horario] ──► CONFIRMANDO_CITA
                            │                              │         │                          │
                            │                              │         │                          ├──► [confirma] ──► CITA_PROGRAMADA
                            │                              │         │                          │         │
                            │                              │         │                          │         ├──► [seguimiento] ──► SEGUIMIENTO
                            │                              │         │                          │         └──► [fin] ──► CERRADO
                            │                              │         │                          │
                            │                              │         │                          └──► [rechaza] ──► REPROGRAMAR
                            │                              │         │                                       │
                            │                              │         │                                       └──► ESPERANDO_SELECCION_HORARIO
                            │                              │         │
                            │                              │         └──► [ninguno gusta] ──► ESPERANDO_FECHA
                            │                              │
                            │                              └──► [no disponible] ──► NO_DISPONIBLE
                            │                                           │
                            │                                           └──► [ofrece otra fecha] ──► ESPERANDO_FECHA
                            │
                            └──► [error] ──► ERROR_DISPONIBILIDAD ──► OFRECER_ALTERNATIVA

Eventos que causan transiciones:
  INICIAR_AGENDAMIENTO → SOLICITANDO_DATOS: se detecta intención de agendar
  SOLICITANDO_DATOS → ESPERANDO_SERVICIO: falta servicio en entidades
  SOLICITANDO_DATOS → ESPERANDO_FECHA: falta fecha
  SOLICITANDO_DATOS → ESPERANDO_HORA: falta hora
  ESPERANDO_* → SOLICITANDO_DATOS: usuario provee dato faltante
  DATOS_COMPLETOS → CONSULTANDO_DISPONIBILIDAD: todos los datos presentes
  CONSULTANDO_DISPONIBILIDAD → HORARIOS_MOSTRADOS: tool ok
  CONSULTANDO_DISPONIBILIDAD → ERROR_DISPONIBILIDAD: tool error
  HORARIOS_MOSTRADOS → CONFIRMANDO_CITA: usuario elige horario
  CONFIRMANDO_CITA → CITA_PROGRAMADA: tool agendar_cita ok
  CONFIRMANDO_CITA → REPROGRAMAR: usuario no confirma

Datos almacenados en sesión:
  agendamiento.servicio
  agendamiento.moto
  agendamiento.fecha
  agendamiento.hora
  agendamiento.horarios_disponibles[]
```

### 3.3 — Diagnóstico

```
                ┌──────────────────────────────────────────────────────────────┐
                │               MÁQUINA DE DIAGNÓSTICO                        │
                └──────────────────────────────────────────────────────────────┘

USUARIO_DESCRIBE_FALLA ──► CLASIFICANDO_SINTOMAS ──► SISTEMA_IDENTIFICADO
        │                          │                         │
        │                          │                         ├──► [tiene procedimiento] ──► PREGUNTAS_DIAGNOSTICO
        │                          │                         │            │
        │                          │                         │            └──► [usuario responde] ──► CAUSAS_POSIBLES
        │                          │                         │                              │
        │                          │                         │                              ├──► [solución simple] ──► RECOMENDACION
        │                          │                         │                              │         │
        │                          │                         │                              │         ├──► [quiere venir] ──► AGENDAMIENTO
        │                          │                         │                              │         └──► [fin] ──► CERRADO
        │                          │                         │                              │
        │                          │                         │                              └──► [requiere revisión] ──► SUGERIR_REVISION
        │                          │                         │                                           │
        │                          │                         │                                           └──► AGENDAMIENTO
        │                          │                         │
        │                          │                         └──► [sin procedimiento] ──► SUGERIR_REVISION
        │                          │                                              │
        │                          │                                              └──► AGENDAMIENTO
        │                          │
        │                          └──► [síntomas insuficientes] ──► PREGUNTAR_MAS_SINTOMAS
        │                                               │
        │                                               └──► USUARIO_DESCRIBE_FALLA (más datos)
        │
        └──► [error] ──► ERROR_DIAGNOSTICO ──► SUGERIR_REVISION

Datos almacenados en sesión:
  diagnostico.sintomas
  diagnostico.sistema_afectado
  diagnostico.causas_posibles[]
  diagnostico.urgencia
```

### 3.4 — Quejas

```
                ┌──────────────────────────────────────────────────────────────┐
                │               MÁQUINA DE QUEJAS                             │
                └──────────────────────────────────────────────────────────────┘

USUARIO_REPORTA_QUEJA ──► CLASIFICANDO_QUEJA ──► QUEJA_REGISTRADA
        │                        │                      │
        │                        │                      ├──► ESCALADO_A_TALLER
        │                        │                      │         │
        │                        │                      │         └──► [taller responde] ──► RESPUESTA_TALLER
        │                        │                      │                     │
        │                        │                      │                     ├──► [solución] ──► SOLUCION_PROPUESTA
        │                        │                      │                     │         │
        │                        │                      │                     │         ├──► [acepta] ──► CITA_REVISION
        │                        │                      │                     │         │         │
        │                        │                      │                     │         │         └──► AGENDAMIENTO
        │                        │                      │                     │         │
        │                        │                      │                     │         └──► [rechaza] ──► ESCALAR_A_GERENTE
        │                        │                      │                     │
        │                        │                      │                     └──► [no solución] ──► ESCALAR_A_GERENTE
        │                        │                      │
        │                        │                      └──► [urgencia alta] ──► NOTIFICAR_INMEDIATO
        │                        │                                   │
        │                        │                                   └──► ESCALADO_A_TALLER
        │                        │
        │                        └──► [no queja] ──► REDIRIGIR_A_DOMINO_APROPIADO
        │
        └──► [error] ──► ERROR_QUEJA ──► OFRECER_LLAMADA

Datos almacenados en sesión:
  queja.id
  queja.descripcion
  queja.urgencia
  queja.estado
  queja.cita_relacionada
```

### 3.5 — Seguimiento

```
                ┌──────────────────────────────────────────────────────────────┐
                │               MÁQUINA DE SEGUIMIENTO                        │
                └──────────────────────────────────────────────────────────────┘

CITA_COMPLETADA ──► ESPERANDO_VENTANA_SEGUIMIENTO ──► (pasan 3 días)
                               │
                               ▼
                    ENVIAR_MENSAJE_SEGUIMIENTO ──► ESPERANDO_RESPUESTA
                               │                        │
                               │                        ├──► [todo bien] ──► SATISFECHO ──► CERRADO
                               │                        │
                               │                        ├──► [problema] ──► QUEJA (derivar)
                               │                        │
                               │                        └──► [sin respuesta] ──► ESPERANDO_VENTANA_REINTENTO
                               │                                             │
                               │                                             └──► (24h) ──► ENVIAR_MENSAJE_SEGUIMIENTO
                               │                                                          (max 3 intentos)
                               │
                               └──► [error envío] ──► NOTIFICAR_ADMIN

Datos almacenados en sesión:
  seguimiento.cita_id
  seguimiento.intentos_restantes
  seguimiento.fecha_ultimo_envio
```

### Máquina de estado global (orquestador)

El `session.estado` general se compone de `{dominio}_{subestado}`:

```python
ESTADOS_GLOBALES = {
    "NUEVA_CONSULTA": "El usuario acaba de escribir por primera vez o después de >30 min",
    "CLASIFICANDO": "El sistema está determinando la intención",
    "COTIZACION_*": "El usuario está en flujo de cotización",
    "AGENDAMIENTO_*": "El usuario está en flujo de agendamiento",
    "DIAGNOSTICO_*": "El usuario está en flujo de diagnóstico",
    "QUEJA_*": "El usuario está en flujo de queja",
    "SEGUIMIENTO_*": "El sistema está dando seguimiento post-servicio",
    "ESPERANDO_USUARIO": "El sistema preguntó algo y espera respuesta",
    "CERRADA": "La conversación terminó",
}
```

---

## PARTE 4 — TOOL SELECTION ENGINE

### Arquitectura de decisión

El Tool Selection Engine no es un LLM prompt. Es un **motor de reglas + matching** que opera en 3 fases:

```
Entrada: ExecutionStep {
  goal_type: "COTIZAR_SERVICIO",
  input: { servicio: "cambio aceite", moto: "Italika FT150" }
}

Fase 1: MATCHING (reglas exactas)
  goal_type → tool_name mapping
  COTIZAR_SERVICIO → consultar_precio
  CONSULTAR_DISPONIBILIDAD → consultar_disponibilidad
  AGENDAR_CITA → agendar_cita
  ...

Fase 2: VALIDACIÓN (pre-condiciones)
  ¿El servicio existe en el catálogo?
  ¿La moto es compatible?
  ¿El cliente está registrado?
  Si falla → tool no disponible → error específico

Fase 3: RESOLUCIÓN DE PARÁMETROS
  Completar parámetros faltantes con datos de sesión/entidades
  Si falta un parámetro requerido → WAITING_USER
```

### Registry de herramientas

```python
TOOL_REGISTRY = {
    "consultar_precio": {
        "description": "Consulta el precio de un servicio para una moto específica",
        "input_schema": {
            "servicio": {"type": "string", "required": True},
            "moto": {"type": "string", "required": False},
        },
        "output_schema": {
            "precio_min": {"type": "number"},
            "precio_max": {"type": "number"},
            "incluye": {"type": "string"},
            "tiempo_estimado": {"type": "number"},
            "moneda": {"type": "string", "default": "MXN"},
        },
        "goal_types": ["COTIZAR_SERVICIO"],
        "timeout": 8,
        "retryable": True,
        "critical": True,
    },
    "consultar_disponibilidad": {
        "description": "Consulta horarios disponibles para una fecha y servicio",
        "input_schema": {
            "fecha": {"type": "string", "required": True},
            "servicio": {"type": "string", "required": False},
        },
        "output_schema": {
            "fecha": {"type": "string"},
            "horarios_disponibles": {"type": "array"},
            "slots_disponibles": {"type": "number"},
        },
        "goal_types": ["CONSULTAR_DISPONIBILIDAD", "AGENDAR_CITA"],
        "timeout": 8,
        "retryable": True,
        "critical": False,
    },
    "registrar_cliente": {
        "description": "Registra o actualiza un cliente en la base de datos",
        "input_schema": {
            "telefono": {"type": "string", "required": True},
            "nombre": {"type": "string", "required": True},
            "moto": {"type": "string", "required": False},
        },
        "output_schema": {
            "cliente_id": {"type": "number"},
            "creado": {"type": "boolean"},
            "actualizado": {"type": "boolean"},
        },
        "goal_types": ["REGISTRAR_CLIENTE"],
        "timeout": 5,
        "retryable": True,
        "critical": True,
    },
    "agendar_cita": {
        "description": "Crea una cita en el calendario del taller",
        "input_schema": {
            "cliente_id": {"type": "number", "required": True},
            "servicio": {"type": "string", "required": True},
            "fecha": {"type": "string", "required": True},
            "hora": {"type": "string", "required": True},
            "moto": {"type": "string", "required": False},
        },
        "output_schema": {
            "cita_id": {"type": "number"},
            "fecha": {"type": "string"},
            "hora": {"type": "string"},
            "estado": {"type": "string"},
            "recordatorio_programado": {"type": "boolean"},
        },
        "goal_types": ["AGENDAR_CITA"],
        "timeout": 5,
        "retryable": True,
        "critical": True,
    },
    "obtener_historial_cliente": {
        "description": "Obtiene el historial de citas y mensajes de un cliente",
        "input_schema": {
            "telefono": {"type": "string", "required": True},
            "limite": {"type": "number", "required": False},
        },
        "output_schema": {
            "cliente": {"type": "object"},
            "citas_recientes": {"type": "array"},
            "ultimos_mensajes": {"type": "array"},
        },
        "goal_types": ["CONSULTAR_HISTORIAL"],
        "timeout": 5,
        "retryable": False,
        "critical": False,
    },
    "registrar_queja": {
        "description": "Registra una queja en el sistema",
        "input_schema": {
            "cliente_id": {"type": "number", "required": True},
            "descripcion": {"type": "string", "required": True},
            "urgencia": {"type": "string", "required": False},
            "cita_relacionada_id": {"type": "number", "required": False},
        },
        "output_schema": {
            "queja_id": {"type": "number"},
            "estado": {"type": "string"},
            "urgencia": {"type": "string"},
        },
        "goal_types": ["RESOLVER_QUEJA"],
        "timeout": 5,
        "retryable": True,
        "critical": True,
    },
    "clasificar_diagnostico": {
        "description": "Clasifica una falla descrita por el usuario en sistema afectado",
        "input_schema": {
            "descripcion_falla": {"type": "string", "required": True},
            "moto": {"type": "string", "required": False},
        },
        "output_schema": {
            "sistema_afectado": {"type": "string"},
            "posibles_causas": {"type": "array"},
            "urgencia": {"type": "string"},
            "recomendacion": {"type": "string"},
        },
        "goal_types": ["DIAGNOSTICAR_FALLA"],
        "timeout": 8,
        "retryable": True,
        "critical": False,
    },
}
```

### Motor de selección

```python
class ToolSelector:
    def __init__(self):
        self.registry = TOOL_REGISTRY

    def select(self, goal: dict, context: ContextWindow) -> tuple[str, dict]:
        """Selecciona la herramienta adecuada para un goal.
        Retorna: (tool_name, params)"""
        goal_type = goal["goal_type"]

        # Fase 1: Matching por goal_type
        candidates = [
            (name, spec) for name, spec in self.registry.items()
            if goal_type in spec["goal_types"]
        ]

        if not candidates:
            raise ToolSelectionError(f"No tool found for goal type {goal_type}")

        # Tomar la primera (goal_type → tool es 1:1)
        tool_name, spec = candidates[0]

        # Fase 2: Resolver parámetros
        params = self._resolve_params(spec["input_schema"], goal, context)

        # Fase 3: Verificar pre-condiciones
        missing = [k for k, v in spec["input_schema"].items()
                   if v.get("required") and k not in params]
        if missing:
            raise MissingParamsError(f"Missing required params: {missing}")

        return tool_name, params

    def _resolve_params(self, schema: dict, goal: dict, context: ContextWindow) -> dict:
        params = {}

        # 1. Del goal.input
        params.update(goal.get("input", {}))

        # 2. De entidades de la sesión
        entities = context.session.get("entidades_extraidas", {})
        for key, value in entities.items():
            key_mapping = {
                "servicio_solicitado": "servicio",
                "moto": "moto",
                "fecha_mencionada": "fecha",
                "hora_mencionada": "hora",
                "telefono": "telefono",
                "nombre": "nombre",
            }
            mapped = key_mapping.get(key, key)
            if mapped in schema and mapped not in params:
                params[mapped] = value

        # 3. Del perfil del usuario
        if context.perfil:
            if "cliente_id" not in params and context.perfil.get("cliente_id"):
                params["cliente_id"] = context.perfil["cliente_id"]
            if "telefono" not in params and context.session.get("telefono"):
                params["telefono"] = context.session["telefono"]

        return params

    def can_execute(self, tool_name: str, params: dict) -> tuple[bool, Optional[str]]:
        """Verifica si una herramienta puede ejecutarse con los parámetros dados."""
        spec = self.registry.get(tool_name)
        if not spec:
            return False, f"Tool '{tool_name}' no encontrada"

        missing = []
        for key, meta in spec["input_schema"].items():
            if meta.get("required") and key not in params:
                missing.append(key)

        if missing:
            return False, f"Faltan parámetros: {', '.join(missing)}"

        # Validaciones de dominio
        if tool_name == "consultar_disponibilidad":
            if params.get("fecha"):
                from datetime import datetime
                try:
                    datetime.strptime(params["fecha"], "%Y-%m-%d")
                except:
                    return False, "Formato de fecha inválido (YYYY-MM-DD)"

        return True, None
```

### ¿Por qué selecciona una tool y descarta otras?

| Goal | Tool seleccionada | ¿Por qué esta y no otra? |
|------|------------------|-------------------------|
| `COTIZAR_SERVICIO` | `consultar_precio` | Es la única que devuelve precios. `consultar_disponibilidad` no tiene precio. `agendar_cita` requiere cita. |
| `CONSULTAR_DISPONIBILIDAD` | `consultar_disponibilidad` | Es la única que devuelve horarios. `consultar_precio` solo tiene precios. |
| `AGENDAR_CITA` | `agendar_cita` | Es la única que crea registros en la tabla citas. `registrar_cliente` no agenda. |
| `REGISTRAR_CLIENTE` | `registrar_cliente` | Es la única que escribe en la tabla clientes. Todas las demás requieren cliente_id. |
| `RESOLVER_QUEJA` | `registrar_queja` | Es la única que escribe en la tabla quejas. |
| `DIAGNOSTICAR_FALLA` | `clasificar_diagnostico` | Es la única que clasifica síntomas en sistemas. |
| `CONSULTAR_HISTORIAL` | `obtener_historial_cliente` | Es la única que recupera historial completo. |

---

## PARTE 5 — PLANNER

### ¿Qué produce el planner?

```json
{
  "plan_id": "plan_a1b2c3",
  "goal_id": "g_abc12345",
  "reasoning": "El usuario quiere cotizar cambio de aceite y saber disponibilidad para mañana. Primero necesito registrar al cliente, luego consultar precio, luego ver disponibilidad.",
  "pasos": [
    {
      "orden": 1,
      "goal_id": "g_reg_001",
      "goal_type": "REGISTRAR_CLIENTE",
      "tool": "registrar_cliente",
      "params": { "telefono": "521234567890", "nombre": "Daniel" },
      "critico": true,
      "modo": "sincrono"
    },
    {
      "orden": 2,
      "goal_id": "g_cot_001",
      "goal_type": "COTIZAR_SERVICIO",
      "tool": "consultar_precio",
      "params": { "servicio": "cambio de aceite", "moto": "Italika FT150" },
      "critico": true,
      "depende_de": ["g_reg_001"],
      "modo": "sincrono"
    },
    {
      "orden": 3,
      "goal_id": "g_dis_001",
      "goal_type": "CONSULTAR_DISPONIBILIDAD",
      "tool": "consultar_disponibilidad",
      "params": { "fecha": "mañana", "servicio": "cambio de aceite" },
      "critico": false,
      "depende_de": ["g_cot_001"],
      "modo": "sincrono"
    }
  ],
  "total_pasos": 3,
  "completados": 0,
  "status": "ACTIVE"
}
```

### PlanCreator pseudocódigo

```python
class Planner:
    def __init__(self, llm, tool_selector: ToolSelector, goal_manager: GoalManager):
        self.llm = llm
        self.tool_selector = tool_selector
        self.goal_manager = goal_manager

    async def create_plan(self, goals: list[dict], context: ContextWindow) -> dict:
        if not goals:
            return {"pasos": [], "status": "NO_GOALS"}

        # Extraer goals activos y ordenables
        executable = [g for g in goals if g["status"] == "ACTIVE" and not self._is_blocked(g, goals)]
        executable.sort(key=lambda g: g["priority"])

        pasos = []
        for i, goal in enumerate(executable):
            try:
                tool_name, params = self.tool_selector.select(goal, context)
            except MissingParamsError as e:
                # Si faltan parámetros, crear goal WAITING_USER
                goal["status"] = "WAITING_USER"
                missing_info = self._whats_missing(goal)
                pasos.append({
                    "orden": i + 1,
                    "goal_id": goal["goal_id"],
                    "goal_type": goal["goal_type"],
                    "tool": None,
                    "params": {},
                    "critico": True,
                    "modo": "esperar_usuario",
                    "preguntar": missing_info,
                })
                continue

            paso = {
                "orden": i + 1,
                "goal_id": goal["goal_id"],
                "goal_type": goal["goal_type"],
                "tool": tool_name,
                "params": params,
                "critico": self.tool_selector.registry[tool_name]["critical"],
                "modo": "sincrono",
                "timeout": self.tool_selector.registry[tool_name]["timeout"],
            }

            # Detectar dependencias entre pasos
            for prev in pasos:
                if prev["goal_id"] in goal.get("dependencies", []):
                    if "depende_de" not in paso:
                        paso["depende_de"] = []
                    paso["depende_de"].append(prev["goal_id"])

            pasos.append(paso)

        plan = {
            "plan_id": f"plan_{uuid4().hex[:8]}",
            "reasoning": self._generate_reasoning(goals, context),
            "pasos": pasos,
            "total_pasos": len(pasos),
            "completados": 0,
            "status": "ACTIVE",
        }

        return plan

    async def replan(self, plan: dict, failed_step: dict, error: str, context: ContextWindow) -> dict:
        """Replanifica cuando un paso falla."""
        plan["status"] = "REPLANNING"

        if failed_step.get("critico"):
            # No se puede continuar — abortar plan
            plan["status"] = "FAILED"
            plan["error"] = f"Paso crítico falló: {error}"
            return plan

        # Replanificar desde el paso fallido
        failed_idx = next(i for i, p in enumerate(plan["pasos"]) if p["goal_id"] == failed_step["goal_id"])
        remaining = plan["pasos"][failed_idx + 1:]

        # Intentar de nuevo el paso fallido (si retryable)
        if self.tool_selector.registry.get(failed_step.get("tool", ""), {}).get("retryable"):
            failed_step["retry_count"] = failed_step.get("retry_count", 0) + 1
            if failed_step["retry_count"] <= 2:
                plan["pasos"] = plan["pasos"][:failed_idx] + [failed_step] + remaining
                plan["status"] = "ACTIVE"
                return plan

        # No retryable — saltar paso (si no crítico) y continuar
        plan["pasos"] = plan["pasos"][:failed_idx] + remaining
        plan["status"] = "ACTIVE"
        plan["warning"] = f"Paso {failed_step['goal_id']} omitido por error: {error}"
        return plan

    def _is_blocked(self, goal: dict, all_goals: list) -> bool:
        for dep_id in goal.get("dependencies", []):
            dep = next((g for g in all_goals if g["goal_id"] == dep_id), None)
            if dep and dep["status"] != "COMPLETED":
                return True
        return False

    def _whats_missing(self, goal: dict) -> str:
        """Determina qué información preguntar al usuario."""
        mapping = {
            "REGISTRAR_CLIENTE": "¿Podrías decirme tu nombre para registrarte?",
            "COTIZAR_SERVICIO": "¿Qué servicio te gustaría cotizar?",
            "AGENDAR_CITA": "¿Para qué fecha y hora te gustaría agendar?",
            "CONSULTAR_DISPONIBILIDAD": "¿Para qué fecha quieres consultar disponibilidad?",
        }
        return mapping.get(goal["goal_type"], "¿Podrías proporcionarme más detalles?")

    def _generate_reasoning(self, goals: list, context: ContextWindow) -> str:
        descs = [f"{g['goal_type']}({json.dumps(g.get('input', {}))})" for g in goals]
        return f"Plan para {len(goals)} objetivo(s): {' → '.join(descs)}"
```

### Ejemplos reales de planes

**Ejemplo 1: Cotización + disponibilidad**
```
Input: "¿Cuánto cuesta cambio de aceite para mi FT150 y hay espacio mañana?"
Plan:
  1. REGISTRAR_CLIENTE(tel=521234567890, nombre=Daniel) → crítico
  2. COTIZAR_SERVICIO(servicio=cambio aceite, moto=Italika FT150) → crítico
  3. CONSULTAR_DISPONIBILIDAD(fecha=mañana, servicio=cambio aceite) → no crítico
Razonamiento: Necesito registrar al cliente primero. Luego cotizar.
  La disponibilidad es opcional (si falla, aún puedo responder el precio).
```

**Ejemplo 2: Queja con cita relacionada**
```
Input: "La semana pasada vinieron a cambiar frenos y siguen haciendo ruido"
Plan:
  1. REGISTRAR_CLIENTE(tel=521234567890) → crítico
  2. OBTENER_HISTORIAL(tel=521234567890) → crítico
  3. REGISTRAR_QUEJA(cliente_id=2, descripcion=..., cita_id=5) → crítico
(No depende de disponibilidad ni precio)
```

**Ejemplo 3: Diagnóstico simple**
```
Input: "Mi moto no enciende, hace clic clic"
Plan:
  1. REGISTRAR_CLIENTE(tel=521234567890) → crítico
  2. DIAGNOSTICAR_FALLA(sintomas=no enciende clic clic, moto=Italika FT150)
     → no crítico (puede responder con RAG si falla tool)
Razonamiento: El diagnóstico con tool es ideal, pero si falla,
  el RAG tiene información sobre diagnóstico de batería.
```

---

## PARTE 6 — EXECUTOR

### Arquitectura del Executor

```python
class Executor:
    def __init__(self, tool_selector: ToolSelector, tools_registry: dict):
        self.selector = tool_selector
        self.tools = self._load_tools(tools_registry)

    async def execute_plan(self, plan: dict, context: ContextWindow) -> list[dict]:
        results = []

        for paso in plan.get("pasos", []):
            if paso.get("modo") == "esperar_usuario":
                # No ejecutar, solo actualizar estado del goal
                results.append({
                    "paso": paso["orden"],
                    "goal_id": paso["goal_id"],
                    "type": "user_input_needed",
                    "pregunta": paso.get("preguntar", ""),
                    "success": True,
                })
                continue

            # Validar dependencias
            if not self._dependencies_met(paso, results):
                plan = await self.replan(plan, paso, "Dependencias no cumplidas", context)
                continue

            # Determinar modo de ejecución
            if paso.get("modo") == "paralelo":
                result = await self._execute_parallel(paso)
            else:
                result = await self._execute_single(paso)

            results.append(result)

            if not result["success"] and paso.get("critico"):
                plan["status"] = "FAILED"
                break

        plan["completados"] = sum(1 for r in results if r.get("success"))
        return results

    async def _execute_single(self, paso: dict) -> dict:
        tool_name = paso.get("tool")
        params = paso.get("params", {})
        timeout = paso.get("timeout", 10)

        if not tool_name or tool_name not in self.tools:
            return {
                "paso": paso["orden"],
                "goal_id": paso["goal_id"],
                "tool": tool_name,
                "success": False,
                "error": f"Tool '{tool_name}' no encontrada",
            }

        try:
            result = await asyncio.wait_for(
                self.tools[tool_name](**params),
                timeout=timeout,
            )
            return {
                "paso": paso["orden"],
                "goal_id": paso["goal_id"],
                "tool": tool_name,
                "success": True,
                "data": result.get("data", result),
            }
        except asyncio.TimeoutError:
            return {
                "paso": paso["orden"],
                "goal_id": paso["goal_id"],
                "tool": tool_name,
                "success": False,
                "error": f"Timeout ({timeout}s)",
            }
        except Exception as e:
            return {
                "paso": paso["orden"],
                "goal_id": paso["goal_id"],
                "tool": tool_name,
                "success": False,
                "error": str(e),
            }

    async def _execute_parallel(self, paso: dict) -> dict:
        """Ejecuta herramientas independientes en paralelo."""
        tools = paso.get("tools", [])
        tasks = [self._execute_single(t) for t in tools]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successes = [r for r in results if isinstance(r, dict) and r.get("success")]
        failures = [r for r in results if isinstance(r, dict) and not r.get("success")]

        return {
            "paso": paso["orden"],
            "goal_id": paso["goal_id"],
            "tool": "parallel",
            "success": len(failures) == 0,
            "sub_results": successes,
            "errors": [f.get("error") for f in failures],
        }

    def _dependencies_met(self, paso: dict, previous_results: list) -> bool:
        deps = paso.get("depende_de", [])
        if not deps:
            return True
        completed = {r.get("goal_id") for r in previous_results if r.get("success")}
        return all(d in completed for d in deps)

    def _load_tools(self, registry: dict) -> dict:
        """Carga las funciones reales de las herramientas."""
        # Esto se conecta con las implementaciones reales en app/tools/definitions.py
        return {}
```

### Manejo de errores

| Situación | Comportamiento |
|-----------|---------------|
| **Tool timeout** (excede timeout) | Si es crítico → FAILED plan. Si no → skip paso, warning. |
| **Tool retornó datos inconsistentes** (e.g., precio negativo) | Se detecta en `ResultValidator`. Se marca como FAILED. Se reintenta si retryable. |
| **Tool no encontrada** (typo, no registrada) | Se salta el paso. Warning en log. No es crítico. |
| **Tool requiere params faltantes** | Goal pasa a WAITING_USER. El LLM genera pregunta para el usuario. |
| **Tool devuelve error 500 (BD caída)** | Se reintenta 2 veces con backoff de 1s/3s. Si persiste → FAILED. |
| **Dependencia no cumplida** | El paso se salta. Se replanifica. |
| **Red caída (Gemini API down)** | Ejecutor detecta en Fase 3 (Classify). Se salta clasificación. Se usa fallback. |
| **Múltiples tools independientes** | Se ejecutan en paralelo con `asyncio.gather`. |
| **Tool crítica falla + no retryable** | Plan completo FAILED. Se notifica al usuario que no se puede completar. |

### ResultValidator

```python
class ResultValidator:
    def validate(self, tool_name: str, result: dict) -> tuple[bool, Optional[str]]:
        validators = {
            "consultar_precio": self._validate_price,
            "consultar_disponibilidad": self._validate_availability,
            "registrar_cliente": self._validate_client,
            "agendar_cita": self._validate_appointment,
        }

        validator = validators.get(tool_name)
        if validator:
            return validator(result)
        return True, None

    def _validate_price(self, result: dict) -> tuple[bool, Optional[str]]:
        data = result.get("data", result)
        if "precio_min" in data and "precio_max" in data:
            if data["precio_min"] <= 0:
                return False, "precio_min debe ser > 0"
            if data["precio_min"] > data["precio_max"]:
                return False, "precio_min no puede ser mayor a precio_max"
        return True, None

    def _validate_availability(self, result: dict) -> tuple[bool, Optional[str]]:
        data = result.get("data", result)
        if "horarios_disponibles" in data:
            if not isinstance(data["horarios_disponibles"], list):
                return False, "horarios_disponibles debe ser una lista"
        return True, None

    def _validate_client(self, result: dict) -> tuple[bool, Optional[str]]:
        data = result.get("data", result)
        if "cliente_id" in data and data["cliente_id"] <= 0:
            return False, "cliente_id inválido"
        return True, None

    def _validate_appointment(self, result: dict) -> tuple[bool, Optional[str]]:
        data = result.get("data", result)
        if "cita_id" in data and data["cita_id"] <= 0:
            return False, "cita_id inválido"
        if "estado" in data and data["estado"] not in ("pendiente", "confirmada"):
            return False, f"Estado de cita inválido: {data['estado']}"
        return True, None
```

---

## PARTE 7 — REFLECTION Y SELF-CORRECTION

### Cuándo se activa

La reflexión se activa SIEMPRE después de cada generación de respuesta. No es opcional.

### Qué evalúa

```python
class ReflectionValidator:
    def __init__(self, llm):
        self.llm = llm

    async def evaluate(self, original_message: str, response: str, context: FinalContextWindow) -> dict:
        metrics = {}

        # 1. Verificar alucinaciones
        metrics["alucinaciones"] = await self._check_hallucinations(response, context)

        # 2. Verificar completitud del objetivo
        metrics["completitud"] = self._check_completeness(response, context)

        # 3. Verificar coherencia con el historial
        metrics["coherencia"] = self._check_coherence(response, context)

        # 4. Verificar uso correcto de datos de herramientas
        metrics["tool_usage"] = self._check_tool_usage(response, context)

        # 5. Verificar llamado a acción
        metrics["call_to_action"] = self._check_call_to_action(response, context)

        # 6. Verificar personalidad
        metrics["personalidad"] = self._check_personality(response)

        # Calcular puntaje total
        score = (
            metrics.get("alucinaciones", {}).get("score", 1.0) * 0.35 +
            metrics.get("completitud", {}).get("score", 1.0) * 0.20 +
            metrics.get("coherencia", {}).get("score", 1.0) * 0.15 +
            metrics.get("tool_usage", {}).get("score", 1.0) * 0.15 +
            metrics.get("call_to_action", {}).get("score", 1.0) * 0.10 +
            metrics.get("personalidad", {}).get("score", 1.0) * 0.05
        )

        decision = "APROBADA" if score >= 0.70 else "RECHAZADA"

        return {
            "decision": decision,
            "puntaje_total": score,
            "metricas": metrics,
            "feedback": self._build_feedback(metrics) if decision == "RECHAZADA" else None,
        }

    async def _check_hallucinations(self, response: str, context: FinalContextWindow) -> dict:
        """Verifica que la respuesta no contenga información no respaldada."""
        prompt = f"""Evalúa si la siguiente respuesta contiene información NO respaldada por el contexto.

RESPUESTA: {response}

DATOS VERIFICABLES EN CONTEXTO:
Precios: {context.tool_results.get('consultar_precio', {})}
Horarios: {context.tool_results.get('consultar_disponibilidad', {})}
Fragmentos RAG: {[r.get('contenido','')[:200] for r in context.rag[:2]]}

Responde SOLO JSON:
{{"problemas": ["lista de afirmaciones no respaldadas"],
  "score": 0.0-1.0,
  "alucinaciones_detectadas": 0}}"""

        result = await self.llm.generate(prompt, temperature=0.1, response_mime_type="application/json")
        data = json.loads(result)

        return {
            "score": data.get("score", 1.0),
            "problemas": data.get("problemas", []),
            "alucinaciones": data.get("alucinaciones_detectadas", 0),
        }

    def _check_completeness(self, response: str, context: FinalContextWindow) -> dict:
        """Verifica que la respuesta cubra lo necesario para los objetivos activos."""
        objectives = context.objetivos.get("hay_pendientes", False)
        if not objectives:
            return {"score": 1.0, "problemas": []}

        problems = []
        next_step = context.objetivos.get("siguiente_paso", {})
        if next_step:
            tipo = next_step.get("tipo", "")
            keywords = {
                "AGENDAR_CITA": ["agendar", "cita", "cuándo", "gustaría"],
                "COTIZAR_SERVICIO": ["precio", "cuesta", "cotización"],
                "RESOLVER_QUEJA": ["queja", "problema", "solución"],
            }
            expected = keywords.get(tipo, [])
            if not any(kw in response.lower() for kw in expected):
                problems.append(f"No avanza hacia el objetivo {tipo}")

        score = max(0.3, 1.0 - (len(problems) * 0.3))
        return {"score": score, "problemas": problems}

    def _check_coherence(self, response: str, context: FinalContextWindow) -> dict:
        """Verifica coherencia con el historial reciente."""
        if not context.historial:
            return {"score": 1.0, "problemas": []}

        problems = []
        last_user_msg = None
        for msg in reversed(context.historial):
            if msg.get("rol") == "user":
                last_user_msg = msg.get("contenido", "")
                break

        if last_user_msg:
            # Verificar que la respuesta sea sobre el mismo tema
            last_keywords = set(last_user_msg.lower().split()[:10])
            response_keywords = set(response.lower().split()[:10])
            overlap = last_keywords & response_keywords
            if len(overlap) < 2 and len(response) > 50:
                problems.append("Respuesta parece no relacionada con el último mensaje")

        score = max(0.5, 1.0 - (len(problems) * 0.25))
        return {"score": score, "problemas": problems}

    def _check_tool_usage(self, response: str, context: FinalContextWindow) -> dict:
        """Verifica que los datos de herramientas se usen correctamente."""
        problems = []

        for tool_name, data in context.tool_results.items():
            if tool_name == "consultar_precio":
                if "precio_min" in data:
                    precio = f"${data['precio_min']}"
                    if precio in response:
                        pass  # Bien, lo está usando
                    # Si no menciona precio pero tool se ejecutó, no es necesariamente error
            if tool_name == "agendar_cita":
                if "cita_id" in data:
                    if "cita" not in response.lower() and "agend" not in response.lower():
                        problems.append(f"Tool {tool_name} se ejecutó pero respuesta no lo refleja")

        score = max(0.5, 1.0 - (len(problems) * 0.2))
        return {"score": score, "problemas": problems}

    def _check_call_to_action(self, response: str, context: FinalContextWindow) -> dict:
        """Verifica que la respuesta incluya un siguiente paso."""
        has_question = "?" in response
        has_cta_keywords = any(kw in response.lower()
                               for kw in ["gustaría", "quieres", "podemos", "te parece",
                                         "avísame", "confirmas", "dime"])
        if has_question or has_cta_keywords:
            return {"score": 1.0, "problemas": []}
        return {"score": 0.6, "problemas": ["No hay llamado a la acción"]}

    def _check_personality(self, response: str) -> dict:
        """Verifica que el tono sea consistente con la personalidad."""
        problems = []
        prohibited = ["wey", "bro", "amigo", "carnal", "vale"]
        for word in prohibited:
            if word in response.lower():
                problems.append(f"Tono inapropiado: '{word}'")

        required_courtesy = ["gracias", "por favor", "gusto", "claro"]
        if not any(cw in response.lower() for cw in required_courtesy) and len(response) > 100:
            problems.append("Falta cortesía")

        score = max(0.5, 1.0 - (len(problems) * 0.25))
        return {"score": score, "problemas": problems}

    def _build_feedback(self, metrics: dict) -> str:
        feedback = []
        for metric, data in metrics.items():
            for p in data.get("problemas", []):
                feedback.append(f"[{metric}] {p}")
        return "\n".join(feedback) if feedback else ""
```

### Ciclo de regeneración

```python
async def generate_with_reflection(
    self,
    prompt: str,
    context: FinalContextWindow,
    max_attempts: int = 2
) -> tuple[str, dict]:
    feedback_history = []

    for attempt in range(max_attempts):
        # Generar respuesta
        response = await self.generator.generate(prompt, temperature=0.8)

        # Evaluar
        evaluation = await self.reflector.evaluate(
            context.mensaje_actual, response, context
        )

        if evaluation["decision"] == "APROBADA":
            return response, {
                "attempts": attempt + 1,
                "reflection_score": evaluation["puntaje_total"],
                "decision": "APROBADA",
            }

        # Si no, regenerar con feedback
        feedback = evaluation.get("feedback", "Respuesta incorrecta, corrígela.")
        feedback_history.append(feedback)

        prompt += f"\n\n[FEEDBACK DE CORRECCIÓN (intento {attempt + 1})]\n{feedback}\nCorrige la respuesta anterior."

    # Último intento sin importar el score
    response = await self.generator.generate(prompt, temperature=0.8)
    return response, {
        "attempts": max_attempts,
        "reflection_score": 0.0,
        "decision": "FORZADA",
        "warnings": feedback_history,
    }
```

### Métricas de reflexión

| Métrica | Peso | Cálculo |
|---------|------|---------|
| Alucinaciones | 35% | 1.0 - (alucinaciones_detectadas * 0.3) |
| Completitud | 20% | 1.0 si avanza objetivo, 0.3 si no |
| Coherencia | 15% | 1.0 si relacionada, 0.5 si no |
| Tool usage | 15% | 1.0 si refleja tools, 0.5 si no |
| Call to action | 10% | 1.0 si tiene pregunta/CTA, 0.6 si no |
| Personalidad | 5% | 1.0 si tono correcto, 0.5 si no |

---

## PARTE 8 — MEMORIA OPERATIVA

### Timeline exacto de operaciones de memoria

```
FLUJO: Cada interacción completa

1. PRE-CONTEXTO (800ms antes de clasificar)
   ┌─────────────────────────────────────────────────────────────┐
   │ CONSULTA: Session (Redis)                                   │
   │ CONSULTA: Perfil (MySQL)                                    │
   │ CONSULTA: Episódica (Qdrant, top-5, threshold 0.60)        │
   │ CONSULTA: RAG (Qdrant, top-3, threshold 0.65)              │
   │ CONSULTA: Historial (MySQL, últimos 20, conversación activa)│
   └─────────────────────────────────────────────────────────────┘

2. POST-RESPUESTA (200ms después de generar, en paralelo)
   ┌─────────────────────────────────────────────────────────────┐
   │ ESCRITURA: Mensaje usuario → MySQL mensajes                 │
   │ ESCRITURA: Mensaje assistant → MySQL mensajes               │
   │ ESCRITURA: Actualizar ultima_interaccion en clientes        │
   │ ENCOLAR: Embedding del mensaje usuario → RabbitMQ           │
   │ ENCOLAR: Embedding de la respuesta → RabbitMQ               │
   │ ACTUALIZAR: Working session → Redis (TTL renovado)          │
   └─────────────────────────────────────────────────────────────┘

3. POST-RESPUESTA (asíncrono, RabbitMQ/Celery)
   ┌─────────────────────────────────────────────────────────────┐
   │ [Celery] Generar embedding user → upsert Qdrant             │
   │ [Celery] Generar embedding assistant → upsert Qdrant        │
   │ [Celery] Si es momento: resumir conversación → MySQL        │
   │ [Celery] Si cambiaron datos: actualizar perfil → MySQL      │
   └─────────────────────────────────────────────────────────────┘

4. POST-SESIÓN (cuando estado cambia a CERRADA)
   ┌─────────────────────────────────────────────────────────────┐
   │ Resumir conversación completa → MySQL conversaciones         │
   │ Actualizar perfil (frecuencia, servicios, gasto) → MySQL     │
   │ Limpiar sessions expiradas → Redis (automático por TTL)     │
   │ Marcar conversación como cerrada → MySQL                    │
   └─────────────────────────────────────────────────────────────┘

5. CADA 10 MENSAJES (trigger dentro del flujo post-respuesta)
   ┌─────────────────────────────────────────────────────────────┐
   │ Generar/actualizar resumen incremental → MySQL conversaciones│
   │ Si hay resumen anterior, hacer merge incremental             │
   └─────────────────────────────────────────────────────────────┘

6. CADA 30 MINUTOS DE INACTIVIDAD (trigger en pre-contexto)
   ┌─────────────────────────────────────────────────────────────┐
   │ Nueva sesión detectada → limpiar estado anterior             │
   │ Si conversación anterior no estaba cerrada → cerrar          │
   │ Recuperar últimos mensajes para contexto                     │
   └─────────────────────────────────────────────────────────────┘
```

### Reglas de eliminación

| Cuándo | Qué se elimina | Quién |
|--------|---------------|-------|
| TTL expira (30 min) | Session de Redis | Redis automático |
| Score < 0.75 (queries) | Resultados de búsqueda | ContextBuilder |
| Score < 0.60 (upsert) | Embeddings nunca se insertan | Embedding enqueue |
| > 30 días + score < 0.85 | Episódica no se recupera | MemoryService |
| > 30 días (historial MySQL) | Se resumen, no se eliminan | Summarizer |
| Conversación cerrada | Session de Redis se elimina | SessionManager |
| Mensajes > 20 por conv | Se resumen en bloque | Summarizer |

---

## PARTE 9 — MODELO DE DATOS

### goals

```sql
CREATE TABLE goals (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    goal_id VARCHAR(50) NOT NULL UNIQUE,
    goal_type VARCHAR(50) NOT NULL,
    priority INT DEFAULT 1,
    status ENUM('CREATED','ACTIVE','WAITING_USER','WAITING_TOOL','BLOCKED',
                'COMPLETED','FAILED','CANCELLED') DEFAULT 'CREATED',
    session_id VARCHAR(100),
    conversation_id INT,
    cliente_id INT,
    input JSON,
    output JSON,
    result JSON,
    dependencies JSON,
    assigned_tool VARCHAR(100),
    tool_params JSON,
    completion_conditions JSON,
    max_retries INT DEFAULT 2,
    retry_count INT DEFAULT 0,
    error TEXT,
    metadata JSON,
    created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

    INDEX idx_goal_id (goal_id),
    INDEX idx_session (session_id),
    INDEX idx_status (status),
    INDEX idx_conversation (conversation_id),
    INDEX idx_cliente (cliente_id),
    INDEX idx_type_status (goal_type, status),
    FOREIGN KEY (conversation_id) REFERENCES conversaciones(id) ON DELETE CASCADE,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
);
```

**Justificación:**
- `goal_id` único para referenciar desde sesiones y planes.
- `session_id` para recuperar goals activos de una sesión.
- `input` y `output` separados para rastrear qué se pidió vs qué se obtuvo.
- `dependencies` como JSON array de goal_ids para resolver dependencias.
- `completion_conditions` para determinar cuándo un goal está completo (no solo tool success).
- `metadata` para almacenar origen (clasificador, humano, sistema).

### conversation_states

```sql
CREATE TABLE conversation_states (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id INT NOT NULL UNIQUE,
    current_state VARCHAR(100) NOT NULL DEFAULT 'NUEVA_CONSULTA',
    previous_state VARCHAR(100),
    domain VARCHAR(50) NOT NULL,
    state_data JSON,
    entered_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

    INDEX idx_conversation (conversation_id),
    INDEX idx_state (current_state),
    INDEX idx_domain_state (domain, current_state),
    FOREIGN KEY (conversation_id) REFERENCES conversaciones(id) ON DELETE CASCADE
);
```

**Justificación:**
- `current_state` y `previous_state` para rastrear transiciones.
- `domain` para saber qué máquina de estados aplicar (COTIZACION, AGENDAMIENTO, etc.).
- `state_data` para datos específicos del dominio (ej: `{"servicio": "cambio aceite"}`).
- Única por conversación (UNIQUE conversation_id) porque solo hay un estado activo.

### user_profiles (extensión de perfiles_usuario)

```sql
-- Esta tabla ya existe como perfiles_usuario, se agregan campos:
ALTER TABLE perfiles_usuario ADD COLUMN (
    last_goal_completed VARCHAR(50),
    last_goal_completed_at TIMESTAMP,
    preferred_contact_time VARCHAR(20),     -- 'mañana', 'tarde'
    communication_style VARCHAR(50),         -- 'formal', 'normal', 'informal'
    total_interactions INT DEFAULT 0,
    satisfaction_trend DECIMAL(2,1),        -- promedio móvil de satisfacción
    notes_embedding_id VARCHAR(100),         -- embedding de notas para búsqueda
    INDEX idx_segment (segmento),
    INDEX idx_frecuencia (frecuencia_visitas)
);
```

### conversation_summaries

```sql
CREATE TABLE conversation_summaries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id INT NOT NULL UNIQUE,
    summary_text TEXT NOT NULL,
    summary_type ENUM('incremental','final') DEFAULT 'incremental',
    message_count INT DEFAULT 0,
    last_message_id BIGINT,
    version INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_conversation (conversation_id),
    INDEX idx_type (summary_type),
    FOREIGN KEY (conversation_id) REFERENCES conversaciones(id) ON DELETE CASCADE
);
```

**Justificación:**
- `summary_type`: `incremental` (cada 10 mensajes) vs `final` (conversación cerrada).
- `message_count`: cuántos mensajes cubre el resumen.
- `last_message_id`: último mensaje incluido en el resumen (para saber si toca actualizar).
- `version`: cuántas veces se ha actualizado.

### tool_executions

```sql
CREATE TABLE tool_executions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tool_name VARCHAR(100) NOT NULL,
    goal_id VARCHAR(50),
    plan_id VARCHAR(50),
    conversation_id INT,
    input_params JSON,
    output_data JSON,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    execution_time_ms INT,
    retry_count INT DEFAULT 0,
    trace_id VARCHAR(100),
    executed_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),

    INDEX idx_goal (goal_id),
    INDEX idx_plan (plan_id),
    INDEX idx_tool (tool_name),
    INDEX idx_success (success),
    INDEX idx_conversation (conversation_id),
    INDEX idx_executed (executed_at),
    FOREIGN KEY (conversation_id) REFERENCES conversaciones(id) ON DELETE CASCADE
);
```

**Justificación:**
- Registro de auditoría completo para cada ejecución de herramienta.
- `input_params` y `output_data` para depuración y replay.
- `execution_time_ms` para monitoreo de rendimiento.
- `trace_id` para correlacionar con logs de OpenTelemetry.

### planner_runs

```sql
CREATE TABLE planner_runs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    plan_id VARCHAR(50) NOT NULL UNIQUE,
    conversation_id INT,
    goals_included JSON,
    total_steps INT,
    completed_steps INT DEFAULT 0,
    status ENUM('ACTIVE','COMPLETED','FAILED','REPLANNING','CANCELLED') DEFAULT 'ACTIVE',
    reasoning TEXT,
    error TEXT,
    warning TEXT,
    created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

    INDEX idx_plan_id (plan_id),
    INDEX idx_conversation (conversation_id),
    INDEX idx_status (status),
    FOREIGN KEY (conversation_id) REFERENCES conversaciones(id) ON DELETE CASCADE
);
```

**Justificación:**
- `goals_included`: JSON array de goal_ids que componen el plan.
- `total_steps` vs `completed_steps`: progreso del plan.
- `status` con REPLANNING para cuando se modifica el plan en medio de la ejecución.
- `reasoning`: cadena de razonamiento del planner (para depuración).

### memory_entries

```sql
CREATE TABLE memory_entries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    cliente_id INT NOT NULL,
    memory_type ENUM('episodic','semantic','procedural') NOT NULL,
    content TEXT NOT NULL,
    embedding_id VARCHAR(100),
    metadata JSON,
    source VARCHAR(50),           -- 'conversation', 'profile', 'rag', 'system'
    relevance_score DECIMAL(3,2),
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_cliente (cliente_id),
    INDEX idx_type (memory_type),
    INDEX idx_source (source),
    INDEX idx_expires (expires_at),
    INDEX idx_cliente_type (cliente_id, memory_type),
    FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
);
```

**Justificación:**
- `memory_type`: separa los 3 tipos de memoria para consultas diferenciadas.
- `embedding_id`: referencia al punto en Qdrant (para limpieza).
- `expires_at`: fecha de expiración del recuerdo (memoria episódica expira, semántica no).
- `relevance_score`: score de relevancia al momento de creación.

### Relaciones entre tablas

```
conversaciones ──┬── 1:N ── mensajes
                 ├── 1:1 ── conversation_states
                 ├── 1:1 ── conversation_summaries
                 ├── 1:N ── goals (session_id → conversacion_id)
                 ├── 1:N ── tool_executions
                 └── 1:N ── planner_runs

clientes ──┬── 1:N ── conversaciones
           ├── 1:N ── mensajes
           ├── 1:N ── goals
           ├── 1:N ── memory_entries
           └── 1:1 ── perfiles_usuario
```

---

## PARTE 10 — IMPLEMENTACIÓN REAL

### Dónde vive cada componente

| Componente | Tecnología | Archivo/Ubicación | Razón |
|-----------|-----------|-------------------|-------|
| **Receiver** (validación + sanitize) | FastAPI + Pydantic | `app/api/messages.py` | Validación de entrada, rate limit, respuesta inmediata |
| **ContextBuilder** | FastAPI (Python) | `app/orchestrator/context_builder.py` | Necesita async I/O pesado (Redis, Qdrant, MySQL) |
| **SessionLoader** | Redis (con Python) | `app/memory/working.py` (SessionManager) | Redis es perfecto para sesiones TTL |
| **ProfileLoader** | MySQL (con Python) | `app/persistence/repository.py` | Datos relacionales del cliente |
| **EpisodicLoader** | Qdrant + Python | `app/memory/service.py` | Búsqueda vectorial con filtros |
| **RAGLoader** | Qdrant + Python | `app/rag/pipeline.py` | Búsqueda vectorial + re-ranking |
| **HistoryLoader** | MySQL (con Python) | `app/persistence/repository.py` | Historial conversacional secuencial |
| **IntentClassifier** | Gemini (function calling) + Python | `app/agent/classifier.py` | LLM con temperature 0.1, function calling nativo |
| **GoalManager** | Python (en memoria → Redis) | `app/agent/objective_tracker.py` | Ligero, opera sobre session en Redis |
| **Planner** | Gemini + Python | `app/agent/planner.py` | Necesita LLM para razonar dependencias |
| **ToolSelector** | Python (reglas + registry) | `app/tools/registry.py` | 100% reglas, NO LLM. Rápido y determinista |
| **Executor** | Python (asyncio) | `app/tools/executor.py` | Ejecuta tools con timeout, maneja errores |
| **ResultValidator** | Python (reglas) | `app/tools/executor.py` (inner class) | Validación post-ejecución, determinista |
| **PromptOrchestrator** | Python | `app/orchestrator/prompt_orchestrator.py` | Ensamblaje de texto, sin I/O |
| **Generator** | Gemini + Python | `app/agent/generator.py` | LLM con temperature 0.8 |
| **ReflectionValidator** | Gemini + Python | `app/agent/reflector.py` | LLM con temperature 0.1 para evaluar |
| **HistoryWriter** | MySQL (con Python) | `app/persistence/repository.py` | INSERT de mensajes |
| **EmbeddingEnqueuer** | RabbitMQ + Python | `app/services/rabbitmq.py` → `tasks/embeddings.py` | Async, no bloquear flujo síncrono |
| **ProfileUpdater** | MySQL (con Python) | `app/persistence/repository.py` | UPDATE post-interacción |
| **SummaryChecker** | MySQL + Python | `app/memory/summarizer.py` | Trigger cada 10 mensajes |
| **StateMachine** | Python (en memoria) | `app/agent/state_machine.py` | Máquina de estados pura, sin I/O |
| **ConversationState** | MySQL | `app/persistence/repository.py` | Persistencia de la máquina de estados |
| **Goal persistence** | MySQL (tabla goals) | `app/persistence/repository.py` | Auditoría y recuperación ante caídas |
| **Tool execution log** | MySQL (tabla tool_executions) | `app/persistence/repository.py` | Auditoría y depuración |
| **Planner log** | MySQL (tabla planner_runs) | `app/persistence/repository.py` | Auditoría de planes |

### Lo que NO se implementa

| Componente | Razón | Alternativa |
|-----------|-------|-------------|
| n8n como planificador | Ya se decidió que n8n es solo gateway | FastAPI toma todo el procesamiento cognitivo |
| n8n como ejecutor de tools | n8n no tiene manejo nativo de timeouts/retry | FastAPI Executor con asyncio |
| Redis como BD principal | Redis no es persistente, no tiene queries complejas | MySQL para persistencia, Redis solo para sesión/cache |
| Qdrant como BD de perfil | Qdrant no es bueno para datos relacionales pequeños | MySQL para perfil, Qdrant solo para vectores |
| Embeddings síncronos | Bloquearía la respuesta del agente | RabbitMQ + Celery para async |

### Orden de implementación (priorizado)

```
Semana 1-2 (DÍAS 1-10):
  Día 1: GoalManager + ObjectiveTracker (sin persistencia MySQL)
  Día 2: ToolSelector + Tool Registry (reglas puras)
  Día 3: Executor (single tool, con timeout y retry)
  Día 4: StateMachine (las 5 máquinas de estado)
  Día 5: Planner (versión reglas, sin LLM)
  Día 6: ContextBuilder (versión completa con filtros)
  Día 7: PromptOrchestrator (estructura de 9 secciones)
  Día 8: Generator + ReflectionValidator
  Día 9: Memory write pipeline (MySQL + RabbitMQ enqueue)
  Día 10: Integración orquestador completo

Semana 3-4 (DÍAS 11-20):
  Día 11: Tablas goals, tool_executions, planner_runs, memory_entries
  Día 12: ConversationSummarizer (incremental + final)
  Día 13: Celery worker para embeddings
  Día 14: ProfileUpdater (triggers post-interacción)
  Día 15: State persistence (conversation_states)
  Día 16: Planificación con LLM (replanificar)
  Día 17: Manejo de errores completo
  Día 18: Tests de integración
  Día 19: Pruebas de carga
  Día 20: Ajustes y deploy
```

---

## PARTE 11 — VEREDICTO FINAL

### ¿Qué le falta a la arquitectura V2 para convertirse en un agente conversacional real?

**Lo que ya tiene:**
- Memoria en 4 niveles (working, episódica, semántica, procedural) ✓
- RAG con re-ranking ✓
- Context Builder con jerarquía ✓
- Prompt Orchestrator con 9 secciones ✓
- Reflection Loop ✓
- Tool calling con registry ✓
- Máquinas de estado por dominio ✓
- Goal manager con ciclo de vida ✓

**Lo que AÚN falta:**

1. **Evaluación continua (online learning).** El sistema no aprende de sus errores. Cada conversación debería alimentar un dataset de fine-tuning. Sin esto, el sistema nunca mejora solo.

2. **Detección de intención negativa.** El sistema sabe clasificar "quiero cotizar" pero no "esto es muy caro" o "no estoy de acuerdo". Detectar objeciones requiere un clasificador específico que no está diseñado.

3. **Personalización adaptativa.** El sistema tiene perfil de usuario pero no adapta su comportamiento en tiempo real. Si un usuario siempre agenda los sábados, el sistema debería ofrecer sábados primero. Esto requiere ML predictivo.

4. **Handoff a humano sin pérdida de contexto.** Si el sistema deriva a un humano, el humano debe recibir el contexto completo de la conversación. No hay interfaz humana diseñada.

5. **Manejo de múltiples canales simultáneos.** El diseño asume WhatsApp como canal único. Si el usuario escribe por WhatsApp y luego por web, el sistema no sabe que es la misma persona.

6. **Detección de emergencias.** "Mi moto se incendió" debería activar un protocolo de emergencia (notificar al taller inmediatamente). No hay clasificador de urgencia crítica.

### Riesgos vigentes

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| **Gemini API Key sin cuota** (ya pasó) | Alta | Crítico | Implementar fallback local (respuestas template clasificadas por intención) |
| **Evolution API desconectado** (ya pasó) | Alta | Crítico | Script reconnect_evolution.py creado, probar en deploy |
| **Re-ranking con LLM añade 1-2s de latencia** | Media | Alto | Cache de re-ranking (Redis, TTL 5 min, key = hash(query + top_k)) |
| **Embeddings síncronos bloquean respuesta** | Baja (ya es async) | Medio | RabbitMQ + Celery ya diseñado, asegurar cola persistente |
| **Reflection loop duplica tiempo de respuesta** | Alta | Alto | Máximo 2 intentos, timeout total de 3s para reflection |
| **Planificador con LLM puede alucinar pasos** | Media | Alto | ToolSelector (reglas) valida cada paso antes de ejecutar |
| **SQL injection en queries concatenadas** | Baja (ya se usa SQLAlchemy) | Crítico | Verificar que NO haya queries raw en la implementación |
| **Redis se llena de sesiones huérfanas** | Alta | Bajo | TTL de 30 min, monitorear keyspace con `INFO keyspace` |
| **Qdrant colecciones sin mantenimiento** | Media | Medio | Cleanup job semanal: eliminar puntos con score promedio < 0.50 |

### Partes demasiado complejas

1. **Máquinas de estado por dominio (Parte 3).** Son 5 máquinas con ~10 estados cada una. En la práctica, se puede simplificar a una máquina genérica parametrizada por dominio, con transiciones definidas en JSON. Esto reduce código repetido.

2. **Re-ranking con LLM (Parte 5 del documento anterior).** Llamar a Gemini para re-rankear 6 fragmentos es caro y lento. Alternativa: re-ranking con cross-encoder pequeño (ej: `mxbai-embed-large-v1` con reranker) que corre localmente. Se puede implementar como fase 2 opcional.

3. **Reflection loop con 6 métricas.** Evaluar 6 métricas con LLM es caro. Simplificar: solo evaluar alucinaciones (la métrica más crítica). Las otras 5 métricas pueden ser reglas Python simples (regex, keyword matching).

4. **Goal Manager con dependencias entre goals.** En la práctica, las dependencias son siempre lineales: A → B → C. Rara vez hay bifurcaciones. Simplificar: asumir orden secuencial por prioridad.

### Partes que pueden simplificarse

1. **MemoryEntries table.** No es necesaria. La memoria episódica ya vive en Qdrant, la semántica en MySQL (perfiles), la procedural en RAG. La tabla `memory_entries` es redundante si ya tenemos esos orígenes.

2. **PlannerRuns table.** No es necesaria para el funcionamiento del agente. Solo para depuración. Se puede reemplazar con logs estructurados en la tabla `logs`.

3. **StateMachine como código.** Se simplifica a un archivo JSON de configuración:
```json
{
  "COTIZACION": {
    "initial": "USUARIO_PREGUNTA",
    "states": {
      "USUARIO_PREGUNTA": {
        "on": {
          "CLASIFICAR": "CLASIFICANDO"
        }
      },
      "CLASIFICANDO": {
        "on": {
          "ALTA_CONFIANZA": "CONSULTANDO_PRECIO",
          "BAJA_CONFIANZA": "PREGUNTAR_ACLARACION"
        }
      },
      ...
    }
  }
}
```

4. **PromptOrchestrator como 9 secciones.** Se simplifica a 5:
   - System (personalidad + reglas)
   - Context (sesión + perfil + tools + historial)
   - Knowledge (episódica + RAG, fusionados)
   - User Message
   - Instruction

### ¿Qué implementarías primero si solo hubiera 30 días?

**Sprint de 30 días: prioridad absoluta**

| Semana | Qué | Por qué |
|--------|-----|---------|
| **Semana 1** | GoalManager + ToolSelector + Executor + las 5 máquinas de estado en JSON | Sin goals y tools, el agente no hace nada. Son el 80% del valor. |
| **Semana 2** | ContextBuilder (sin episódica, solo sesión + perfil + historial) + PromptOrchestrator simplificado (5 secciones) | Necesita construir contexto para que el LLM responda. Episódica y RAG se agregan después. |
| **Semana 3** | Generator + Reflection (solo anti-alucinación) + Memory write pipeline (MySQL + RabbitMQ) | Sin generación, no hay respuesta. Sin reflection, el agente alucina. Sin memoria, no aprende. |
| **Semana 4** | RAG pipeline (sin re-ranking), Episodic loader simple (top-3, sin decay), ConversationSummarizer | Completar los niveles de memoria. RAG sin re-ranking es más rápido y 80% efectivo. |

**Lo que NO entra en 30 días:**
- Re-ranking con LLM (se agrega después)
- ProfileUpdater completo (solo campos básicos)
- StateMachine persistente en MySQL (solo en Redis)
- Tablas de auditoría (goals, tool_executions — solo logs básicos)
- Handoff a humano
- Detección de emergencias
- Personalización adaptativa

**Evidencia de auditorías previas que respaldan esta decisión:**
- Auditoría inicial encontró: 0% de procesamiento cognitivo real, 0% de memoria, 0% de RAG. El sistema V1 nunca procesó un mensaje real.
- REAS requiere: cotización, agendamiento, diagnóstico, quejas — las 5 máquinas de estado cubren exactamente esos dominios.
- El diseño V2 anterior encontró: SQL injection activo en n8n (línea 202), prompts hardcodeados, temperatura 0.1. Priorizar GoalManager + ToolSelector elimina la necesidad de prompts en n8n y centraliza la lógica en Python donde es mantenible.
- La reflection loop es crítica porque las respuestas actuales son templates JS sin validación. Sin reflection, el LLM generaría información no verificada.
- Qdrant + Embeddings pueden esperar porque sin RAG el sistema puede responder con datos de MySQL (precios, horarios) — eso ya es una mejora significativa vs V1.
