# V2 — ARQUITECTURA DEL SISTEMA (Parte 3/4)

---

## PARTE 4 — DISEÑO DEL RAG

### Pipeline de Ingestión

```
Documentos fuente (servicios, procedimientos, políticas, FAQs)
        │
        ▼
┌───────────────────────┐
│ 1. Parseo             │
│    - Detectar tipo     │
│    - Extraer metadata  │
│    - Validar           │
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│ 2. Chunking           │
│    - Servicio: doc completo (< 200 tokens)    │
│    - Procedimiento: por sección (300-500 tok) │
│    - Política: por párrafo (200-400 tok)      │
│    - FAQ: pregunta-respuesta (< 200 tok)      │
│    - Manual: por tema (500-800, overlap 100)  │
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│ 3. Embedding          │
│    - Gemini text-embedding-004                │
│    - Dimensión: 768                           │
│    - Batch: 10 documentos                     │
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│ 4. Indexación         │
│    - Upsert a Qdrant (collection: conocimiento) │
│    - Payload: tipo, tags, metadata             │
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│ 5. Verificación       │
│    - Sample queries    │
│    - Evaluar recall@5  │
│    - Ajustar si < 0.85 │
└───────────────────────┘
```

### Al RAG (Knowledge Base)

| Qué va | Qué NO va |
|--------|-----------|
| Catálogo de servicios con precios | Conversaciones de clientes |
| Procedimientos de diagnóstico | Datos personales |
| Políticas del taller | Información temporal volátil |
| Preguntas frecuentes | Logs internos |
| Manuales técnicos | Sesiones activas |
| Horarios y reglas de negocio | |

### Estrategia de Recuperación

```python
1. Búsqueda vectorial primaria (3× sobremuestreo, threshold 0.65)
2. Búsqueda por filtros de entidades (servicio, categoría)
3. Fusión RRF (Reciprocal Rank Fusion, weights [0.6, 0.4])
4. Re-ranking con Gemini (combina score vectorial 40% + relevancia LLM 60%)
5. Filtro final threshold 0.75
```

### Anti-alucinación

1. **Source grounding**: cada respuesta cita fragmentos: `"El cambio de aceite cuesta $350-$550 [Fuente: Servicio #1]"`
2. **Threshold 0.75**: fragmentos con score menor no se usan
3. **Verificación en Reflection Loop**: el loop de reflexión chequea que números y afirmaciones coincidan con el contexto
4. **Fallback honesto**: si no hay información → "No tengo esa información, ¿quieres que te contacte con un asesor?"

---

## PARTE 8 — API DEL SISTEMA

### POST /api/v1/messages
Endpoint principal. n8n envía aquí los mensajes de WhatsApp.

**Request:**
```json
{
  "telefono": "521234567890",
  "mensaje": "Texto del mensaje",
  "nombre": "Daniel",
  "remoteJid": "...",
  "timestamp": 1717171200
}
```

**Response 200:**
```json
{
  "success": true,
  "respuesta": "¡Hola Daniel!...",
  "categoria": "COTIZACION",
  "conversacion_id": 5,
  "requiere_accion": "confirmacion_cita",
  "proximo_estado": "ESPERANDO_CONFIRMACION_CITA",
  "tiempo_procesamiento_ms": 2340
}
```

**Errores:**
| Código | HTTP | Causa |
|--------|------|-------|
| MSG_TOO_LONG | 400 | Mensaje > 4096 chars |
| INVALID_PHONE | 400 | Teléfono inválido |
| EMPTY_MESSAGE | 400 | Mensaje vacío |
| RATE_LIMITED | 429 | Rate limit excedido |
| BLACKLISTED | 403 | Teléfono bloqueado |
| INTERNAL_ERROR | 500 | Error interno |

### POST /api/v1/memory/retrieve
Recupera memoria episódica + semántica para un mensaje.

**Request:**
```json
{
  "telefono": "521234567890",
  "mensaje": "consulta",
  "limite": 5,
  "incluir_similares": true
}
```

### POST /api/v1/tools/execute
Ejecuta una herramienta específica (admin/testing).

**Request:**
```json
{ "tool": "consultar_precio", "parametros": { "servicio": "frenos", "moto": "Italika FT150" } }
```

### GET /api/v1/customers/{telefono}
Perfil completo de cliente con citas, conversaciones, quejas.

### POST /api/v1/appointments
Crear cita programáticamente.

### POST /api/v1/admin/rag/refresh
Refresca la base de conocimiento del RAG.

---

## PARTE 9 — PLAN DE IMPLEMENTACIÓN

### FASE 1: Fundación (Semanas 1-2, 10 días)

| Día | Entregable | Dependencia | Riesgo |
|-----|-----------|-------------|--------|
| 1 | FastAPI scaffold + endpoints base | Ninguna | Bajo |
| 2 | MySQL schema completo + migraciones | FastAPI | Bajo |
| 3 | Redis: conexión + sesiones + rate limit | FastAPI | Bajo |
| 4 | Qdrant: colecciones + conexión | FastAPI | Medio |
| 5-6 | n8n: reducir rol a gateway + comunicación FastAPI | Docker Compose | Medio |
| 7 | Evolution API: reconectar WhatsApp | Docker | Alto |
| 8 | Prueba integración: WhatsApp → FastAPI → MySQL | Todo lo anterior | Alto |

### FASE 2: Cerebro del Agente (Semanas 3-4, 10 días)

| Día | Entregable | Dependencia | Riesgo |
|-----|-----------|-------------|--------|
| 9-10 | Intent Classifier (function calling) | Fase 1 | Medio |
| 11-12 | Entity Extractor | Classifier | Medio |
| 13-14 | Planning Agent (ReAct) | Classifier | Alto |
| 15-16 | Tool Executor | Todas las tools | Alto |
| 17-18 | Response Generator (temp 0.8) | Todo anterior | Alto |
| 19 | Flujo completo sin reflection | Todo anterior | Alto |
| 20 | Reflection Loop + Regeneration | Generator | Alto |

### FASE 3: Memoria y RAG (Semanas 5-6, 10 días)

| Día | Entregable | Dependencia | Riesgo |
|-----|-----------|-------------|--------|
| 21-22 | Pipeline embeddings + upsert Qdrant | Fase 1 (Qdrant) | Medio |
| 23-24 | RAG retrieval + filtros + fusión | Pipeline | Medio |
| 25 | Re-ranking con LLM | RAG | Alto |
| 26 | Context Builder | Fase 2 + RAG | Medio |
| 27 | Conversation Summarizer | Fase 1 | Medio |
| 28 | Persistencia completa | Todo anterior | Bajo |
| 29 | RabbitMQ + Celery workers | Fase 1 | Medio |
| 30 | Prueba integración con memoria | Todo | Alto |

### FASE 4: Pulido y Producción (Semanas 7-8, 8 días)

| Día | Entregable | Dependencia | Riesgo |
|-----|-----------|-------------|--------|
| 31 | OpenTelemetry tracing | Fase 1-3 | Medio |
| 32 | Grafana dashboard | OTel | Bajo |
| 33 | Rate limiting avanzado | Fase 1 | Bajo |
| 34 | Logging + alertas | Fase 1 | Bajo |
| 35 | Tests unitarios + integración | Fase 1-3 | Medio |
| 36 | Optimización: caché Redis, batch embeddings | Fase 1-3 | Bajo |
| 37 | Documentación + runbook | Todo | Bajo |
| 38 | Deploy + pruebas de carga | Todo | Alto |

### docker-compose.yml final (servicios nuevos)

```yaml
services:
  # YA EXISTEN (se quedan):
  n8n:              # Rol reducido a gateway
  postgres:         # BD de n8n
  evolution-pg:     # BD de Evolution API
  evolution:        # Gateway WhatsApp
  mysql:            # BD del negocio (nuevas tablas)

  # NUEVOS:
  fastapi:
    build: ./backend
    ports: ["8000:8000"]
    depends_on: [mysql, redis, qdrant, rabbitmq]
    environment:
      MYSQL_*, REDIS_*, QDRANT_*, RABBITMQ_*, GEMINI_API_KEY

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  qdrant:
    image: qdrant/qdrant
    ports: ["6333:6333"]
    volumes: [qdrant_data:/qdrant/storage]

  rabbitmq:
    image: rabbitmq:3.13-management
    ports: ["5672:5672", "15672:15672"]

  celery-worker:
    build: ./backend
    command: celery -A tasks worker -l info
    depends_on: [rabbitmq, qdrant]

  prometheus:
    image: prom/prometheus
    ports: ["9090:9090"]

  grafana:
    image: grafana/grafana
    ports: ["3000:3000"]
```

Volúmenes nuevos: `qdrant_data`, `rabbitmq_data`, `prometheus_data`, `grafana_data`.
