# V2 — ARQUITECTURA DEL SISTEMA (Parte 4/4)

---

## PARTE 11 — PSEUDOCÓDIGO

### 11.1 Procesamiento de mensajes (Orquestador)

```python
# app/orchestrator/message_processor.py

import time, json, asyncio, logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class MessageRequest:
    telefono: str
    mensaje: str
    nombre: Optional[str] = None
    remote_jid: Optional[str] = None
    timestamp: Optional[int] = None

@dataclass
class MessageResponse:
    success: bool
    respuesta: Optional[str] = None
    categoria: Optional[str] = None
    conversacion_id: Optional[int] = None
    requiere_accion: Optional[str] = None
    error: Optional[str] = None
    codigo_error: Optional[str] = None

class MessageProcessor:
    def __init__(self, memory, rag, classifier, planner, tools, generator, reflector, persistence, rate_limiter):
        self.memory = memory
        self.rag = rag
        self.classifier = classifier
        self.planner = planner
        self.tools = tools
        self.generator = generator
        self.reflector = reflector
        self.persistence = persistence
        self.rate_limiter = rate_limiter

    async def process(self, request: MessageRequest) -> MessageResponse:
        start = time.monotonic()
        trace_id = f"trace_{request.telefono}_{int(start)}"

        logger.info("processing_message", extra={"telefono": request.telefono, "trace_id": trace_id})

        try:
            # Validar
            if err := self._validate(request):
                return MessageResponse(success=False, error=err, codigo_error="VALIDATION_ERROR")

            # Rate limit
            if err := await self.rate_limiter.check(request.telefono):
                return MessageResponse(success=False, error=err, codigo_error="RATE_LIMITED")

            # Working memory
            session = await self.memory.get_session(request.telefono)

            # Memoria episódica
            memoria = await self.memory.retrieve_episodic(request.telefono, request.mensaje, limite=5)

            # RAG
            rag = await self.rag.retrieve(request.mensaje, session.entidades if session else {}, limite=5)

            # Clasificar
            clasificacion = await self.classifier.classify(request.mensaje, session, memoria, rag)

            # Ambigüedad
            if clasificacion.confianza < 0.5:
                await self.persistence.save_messages(request.telefono, request.mensaje, clasificacion.intencion_principal)
                return MessageResponse(success=True, respuesta="¿Podrías darme más detalles?", categoria="ACLARACION")

            # Planificar
            plan = await self.planner.plan(clasificacion, rag, session)

            # Ejecutar tools
            resultados = []
            for paso in plan.pasos:
                try:
                    r = await asyncio.wait_for(
                        self.tools.execute(paso.accion, paso.parametros, trace_id),
                        timeout=10
                    )
                    resultados.append(r)
                    if not r["success"] and paso.critico:
                        break
                except Exception as e:
                    resultados.append({"success": False, "tool": paso.accion, "error": str(e)})
                    if paso.critico:
                        break

            # Replanificar si necesario
            if self._needs_replan(resultados, plan):
                plan = await self.planner.replan(plan, resultados, clasificacion)
                for paso in plan.pasos[len(resultados):]:
                    r = await self.tools.execute(paso.accion, paso.parametros, trace_id)
                    resultados.append(r)

            # Contexto final
            ctx = self._build_context(request, session, memoria, rag, clasificacion, plan, resultados)

            # Generar + Reflection
            respuesta_texto, meta = await self._generate_with_reflection(ctx, max_attempts=2)

            # Persistir
            conv_id = await self.persistence.save_conversation(
                request, respuesta_texto, clasificacion, resultados, meta, trace_id
            )

            # Actualizar working memory
            await self.memory.update_session(request.telefono, {
                "estado": meta.get("proximo_estado", "activa"),
                "conversacion_id": conv_id,
                "ultimo_tema": clasificacion.intencion_principal,
                "intenciones_pendientes": clasificacion.intenciones_secundarias,
                "entidades_extraidas": clasificacion.entidades,
                "resultados_herramientas": {r.get("tool"): r.get("data") for r in resultados if r.get("success")},
                "ultimo_mensaje": request.mensaje,
                "ultima_respuesta": respuesta_texto,
                "mensajes_en_sesion": (session.mensajes_en_sesion if session else 0) + 1
            })

            elapsed = (time.monotonic() - start) * 1000
            logger.info("message_processed", extra={
                "telefono": request.telefono, "categoria": clasificacion.intencion_principal,
                "tiempo_ms": elapsed, "trace_id": trace_id
            })

            return MessageResponse(
                success=True, respuesta=respuesta_texto,
                categoria=clasificacion.intencion_principal,
                conversacion_id=conv_id, requiere_accion=meta.get("requiere_accion")
            )

        except Exception as e:
            logger.critical("message_crash", extra={"telefono": request.telefono, "error": str(e), "trace_id": trace_id})
            return MessageResponse(success=False, error="Error interno", codigo_error="INTERNAL_ERROR")

    async def _generate_with_reflection(self, ctx: dict, max_attempts: int = 2):
        for i in range(max_attempts):
            resp = await self.generator.generate(ctx)
            ref = await self.reflector.evaluate(ctx["mensaje_original"], resp.text, ctx)
            if ref["decision"] == "APROBADA":
                return resp.text, {
                    "proximo_estado": resp.next_state, "requiere_accion": resp.requires_action,
                    "reflection_score": ref.get("puntaje_total")
                }
            ctx["feedback_reflection"] = ref.get("feedback", "")
        resp = await self.generator.generate(ctx)
        return resp.text, {"proximo_estado": resp.next_state, "requiere_accion": resp.requires_action}
```

### 11.2 Recuperación de memoria

```python
# app/memory/service.py

class MemoryService:
    def __init__(self, redis, qdrant, embeddings):
        self.redis = redis
        self.qdrant = qdrant
        self.embeddings = embeddings
        self.session_ttl = 1800

    async def get_session(self, telefono: str):
        data = await self.redis.get(f"session:{telefono}")
        if data:
            session = json.loads(data)
            await self.redis.expire(f"session:{telefono}", self.session_ttl)
            return session
        return None

    async def update_session(self, telefono: str, data: dict):
        existing = await self.get_session(telefono) or {}
        existing.update(data)
        await self.redis.setex(f"session:{telefono}", self.session_ttl, json.dumps(existing))

    async def retrieve_episodic(self, telefono: str, query: str, limite: int = 5):
        embedding = await self.embeddings.generate(query)
        resultados = await self.qdrant.search(
            collection_name="conversaciones",
            query_vector=embedding,
            query_filter=Filter(must=[FieldCondition(key="telefono", match=MatchValue(value=telefono))]),
            limit=limite, with_payload=True, score_threshold=0.70
        )
        return resultados
```

### 11.3 RAG Pipeline

```python
# app/rag/pipeline.py

class RAGPipeline:
    def __init__(self, qdrant, embeddings, reranker):
        self.qdrant = qdrant
        self.embeddings = embeddings
        self.reranker = reranker

    async def retrieve(self, query: str, entidades: dict = None, limite: int = 5):
        embedding = await self.embeddings.generate(query)
        vector_results = await self.qdrant.search(
            collection_name="conocimiento", query_vector=embedding,
            limit=limite * 3, with_payload=True, score_threshold=0.65
        )
        filtered_results = []
        if entidades:
            filters = []
            if entidades.get("servicio"):
                filters.append(FieldCondition(key="tags", match=MatchValue(value=entidades["servicio"])))
            if filters:
                filtered_results = await self.qdrant.search(
                    collection_name="conocimiento", query_vector=embedding,
                    query_filter=Filter(must=filters), limit=limite, with_payload=True
                )
        fused = self._rrf_fusion([vector_results, filtered_results], weights=[0.6, 0.4])
        reranked = await self.reranker.rerank(query, fused[:limite * 2], top_k=limite)
        relevant = [r for r in reranked if r.score >= 0.75]
        return {"fragments": relevant, "sources": list(set(r.payload.get("tipo") for r in relevant))}

    def _rrf_fusion(self, result_sets, weights=None, k=60):
        scores = {}
        weights = weights or [1.0 / len(result_sets)] * len(result_sets)
        for i, results in enumerate(result_sets):
            for rank, r in enumerate(results):
                sid = r.id
                if sid not in scores:
                    scores[sid] = {"result": r, "score": 0.0}
                scores[sid]["score"] += weights[i] / (k + rank + 1)
        sorted_r = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
        return [r["result"] for r in sorted_r]
```

### 11.4 Planning Agent

```python
# app/agent/planner.py

class PlanningAgent:
    def __init__(self, llm, tools_registry):
        self.llm = llm
        self.tools = tools_registry

    async def plan(self, intencion, contexto_rag, session=None):
        prompt = f"""INTENCIÓN: {intencion.intencion_principal}
        ENTIDADES: {json.dumps(intencion.entidades)}
        HERRAMIENTAS: {self.tools.list_tools()}
        Genera plan JSON con: objetivo, razonamiento, pasos[]"""
        resp = await self.llm.generate(prompt, temperature=0.2, response_mime_type="application/json")
        plan_data = json.loads(resp.text)
        return Plan(pasos=[PlanStep(**p) for p in plan_data.get("pasos", [])])

    async def replan(self, original_plan, resultados, intencion):
        prompt = f"Plan falló. Pasos fallidos: {[r for r in resultados if not r['success']]}"
        resp = await self.llm.generate(prompt, temperature=0.2)
        return Plan(pasos=[PlanStep(**p) for p in json.loads(resp.text).get("pasos", [])])
```

### 11.5 Tool Executor

```python
# app/agent/tools/executor.py

class ToolExecutor:
    def __init__(self):
        self._registry = {}

    def register(self, name, fn, description, parameters_schema):
        self._registry[name] = {"fn": fn, "description": description, "schema": parameters_schema}

    def list_tools(self):
        return list(self._registry.keys())

    async def execute(self, tool_name, parameters, trace_id=None):
        if tool_name not in self._registry:
            return {"success": False, "tool": tool_name, "error": f"Tool '{tool_name}' not found"}
        tool = self._registry[tool_name]
        result = await asyncio.wait_for(tool["fn"](**parameters), timeout=10)
        return {"success": True, "tool": tool_name, "data": result.get("data")}
```

### 11.6 Actualización de memoria (async)

```python
# app/tasks/embeddings.py (Celery task)

@celery.task
def process_embeddings(payload: dict):
    telefono = payload["telefono"]
    mensaje = payload["mensaje"]
    respuesta = payload.get("respuesta", "")
    timestamp = payload["timestamp"]

    # Generar embedding del mensaje del usuario
    embedding_user = generate_embedding(mensaje)

    # Upsert a Qdrant (conversaciones)
    qdrant_client.upsert(
        collection_name="conversaciones",
        points=[PointStruct(
            id=f"msg_{payload['conversacion_id']}_user",
            vector=embedding_user,
            payload={
                "telefono": telefono,
                "rol": "user",
                "contenido": mensaje,
                "categoria": payload.get("categoria", "GENERAL"),
                "timestamp": timestamp,
                "id_conversacion": payload["conversacion_id"],
                "id_cliente": payload.get("cliente_id")
            }
        )]
    )

    # Si hay respuesta, generar embedding
    if respuesta:
        embedding_assistant = generate_embedding(respuesta)
        qdrant_client.upsert(
            collection_name="conversaciones",
            points=[PointStruct(
                id=f"msg_{payload['conversacion_id']}_assistant",
                vector=embedding_assistant,
                payload={
                    "telefono": telefono,
                    "rol": "assistant",
                    "contenido": respuesta,
                    "categoria": payload.get("categoria", "GENERAL"),
                    "timestamp": timestamp,
                    "id_conversacion": payload["conversacion_id"],
                    "id_cliente": payload.get("cliente_id")
                }
            )]
        )
```

---

## RESUMEN DE LA V2

### Cambios fundamentales vs V1

| Aspecto | V1 (actual) | V2 (objetivo) |
|---------|------------|--------------|
| **Rol de n8n** | Cerebro del sistema | Gateway ligero |
| **Backend cognitivo** | No existe | FastAPI microservicio |
| **Memoria** | 0 (solo INSERT) | 4 niveles (working, episódica, semántica, procedural) |
| **RAG** | No existe | Qdrant + embeddings + re-ranking |
| **Clasificación** | 1 prompt para todo | Function calling dedicado |
| **Planificación** | No existe | ReAct Planner |
| **Tools** | Hardcodeadas en JS | 9 herramientas Python registradas |
| **Respuestas** | Templates fijos en JS | Generación con LLM (temp 0.8) |
| **Reflection** | No existe | Auto-evaluación + regeneración |
| **Persistencia** | 3 tablas | 10 tablas normalizadas |
| **Rate limit** | No existe | Redis token bucket |
| **Observabilidad** | No existe | OpenTelemetry + Grafana |
| **Queue async** | No existe | RabbitMQ + Celery |
| **Diagnóstico** | Precios en JS | Function calling + RAG |

### Archivos V2 a crear

```
backend/
├── app/
│   ├── main.py                     # FastAPI app + endpoints
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   └── message_processor.py    # Orquestador principal
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── classifier.py           # Intent classifier
│   │   ├── planner.py              # Planning agent
│   │   ├── generator.py            # Response generator
│   │   └── reflector.py            # Reflection loop
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── service.py              # Memory retrieval + persistence
│   │   ├── working.py              # Redis working memory
│   │   └── summarizer.py           # Conversation summarizer
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── pipeline.py             # RAG retrieval
│   │   ├── chunker.py              # Document chunking
│   │   └── reranker.py             # LLM re-ranking
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py             # Tool registry
│   │   ├── executor.py             # Tool executor
│   │   └── definitions.py          # All tool definitions
│   ├── models/
│   │   ├── __init__.py
│   │   ├── database.py             # SQLAlchemy models
│   │   └── schemas.py              # Pydantic schemas
│   ├── services/
│   │   ├── __init__.py
│   │   ├── gemini.py               # Gemini client
│   │   ├── redis.py                # Redis client
│   │   ├── qdrant.py               # Qdrant client
│   │   └── rabbitmq.py             # RabbitMQ client
│   ├── api/
│   │   ├── __init__.py
│   │   ├── messages.py             # POST /messages endpoint
│   │   ├── customers.py            # GET /customers endpoint
│   │   ├── appointments.py         # POST /appointments
│   │   ├── memory.py               # POST /memory/retrieve
│   │   ├── tools.py                # POST /tools/execute
│   │   └── admin.py                # Admin endpoints
│   ├── persistence/
│   │   ├── __init__.py
│   │   └── repository.py           # MySQL persistence layer
│   └── config.py                   # Settings + env vars
├── tasks/
│   ├── __init__.py
│   ├── celery_app.py               # Celery configuration
│   └── embeddings.py               # Async embedding processing
├── Dockerfile
├── requirements.txt
└── pyproject.toml
```

### Orden de implementación recomendado

```
Día 1:  scaffold + endpoints + config + Dockerfile
Día 2:  MySQL models + migrations + repository
Día 3:  Redis service + session management + rate limiter
Día 4:  Gemini client + Qdrant service
Día 5:  Classifier (function calling)
Día 6:  Entity Extractor + validación
Día 7:  Tool definitions + executor
Día 8:  Planner (ReAct prompt)
Día 9:  Generator (responses con temp 0.8)
Día 10: RAG pipeline + re-ranking
Día 11: Context builder + orchestrator (sin reflection)
Día 12: Reflection loop + regeneración
Día 13-14: Flujo completo integrado y probado
Día 15: RabbitMQ + Celery + embeddings async
Día 16: Conversation summarizer
Día 17: Monitoreo + logging
Día 18: Tests + documentación
Día 19: Deploy
Día 20: Pruebas de carga + ajustes
```
