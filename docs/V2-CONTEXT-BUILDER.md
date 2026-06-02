# CONTEXT BUILDER + PROMPT ORCHESTRATOR

## Diseño Técnico del Núcleo Cognitivo

---

## PARTE 1 — FLUJO DEL CONTEXT BUILDER

### Entrada
```json
{
  "mensaje": "Hola, ¿cuánto cuesta el cambio de aceite para mi Italika FT150 y puedo ir mañana?",
  "telefono": "521234567890",
  "session": { "estado": "NUEVA_CONSULTA" }
}
```

### Paso a paso

#### Fase A — Extracción en crudo (paralelo, sin filtros)

Se ejecutan 5 recuperaciones en paralelo. Cada una devuelve TODO lo que encuentra:

| Consulta | Origen | Límite |
|----------|--------|--------|
| A1. Memoria episódica | Qdrant `conversaciones` | top-10, threshold 0.60 |
| A2. RAG conocimiento | Qdrant `conocimiento` | top-15, threshold 0.60 |
| A3. Perfil cliente | MySQL `clientes` + `perfiles_usuario` | 1 fila |
| A4. Working session | Redis `session:{tel}` | 1 sesión |
| A5. Historial MySQL | MySQL `mensajes` WHERE cliente_id | últimos 20 mensajes |

**Límite de tiempo total para Fase A: 800ms**. Si alguno falla, se omite silenciosamente.

#### Fase B — Filtrado por relevancia

Cada conjunto pasa por un filtro independiente:

**B1. Memoria episódica:**
- Threshold sube a 0.75
- Si score < 0.75 → descartado
- Si score >= 0.75 pero es idéntico al mensaje actual → descartado
- Si score >= 0.75 pero es del mismo usuario y misma conversación hace < 5s → descartado
- Máximo 5 items retenidos

**B2. RAG conocimiento:**
- Threshold sube a 0.75
- Fusion RRF si hay múltiples queries (vectorial + filtro entidades)
- Re-ranking con Gemini: top-3
- Si score < 0.75 después de re-ranking → descartado
- Máximo 3 items retenidos

**B3. Perfil cliente:**
- Siempre se retiene si existe (es perfil, no tiene score)
- Se extraen solo campos relevantes: nombre, motos, frecuencia, preferencias
- Se descartan: embedding_id, created_at interno, total_gastado (se usa solo si relevante)

**B4. Working session:**
- Siempre se retiene si existe
- Se extraen: estado, intencion_actual, entidades_extraidas, resultados_herramientas
- Se descartan: mensajes_en_sesion (solo para rate limit, no para contexto)

**B5. Historial MySQL:**
- Se mantienen solo mensajes de la conversación activa (conversacion_id actual)
- Si no hay conversación activa → últimos 3 mensajes del cliente
- Máximo 10 items retenidos
- Se descartan mensajes con contenido vacío o "..."

#### Fase C — Compresión y deduplicación

**C1. Deduplicación cruzada:**
- Si un fragmento RAG y un mensaje episódico contienen la misma información (similitud coseno > 0.90) → se queda el de mayor score
- Si un mensaje del historial MySQL ya aparece en memoria episódica → se queda el episódico (tiene embedding)

**C2. Compresión de historial:**
- Si el historial tiene > 6 mensajes → los primeros se resumen
- Regla: mantener últimos 6 mensajes completos, resumir el resto a 1 oración por cada 3 mensajes antiguos
- Si la conversación tiene > 20 mensajes en total → resumen externo guardado en `conversaciones.resumen`

#### Fase D — Ensamblaje del contexto

```python
context = {
    "mensaje_actual": mensaje,
    "session": session_filtrada,
    "perfil": perfil_filtrado,
    "historial_reciente": historial_comprimido,
    "memoria_episodica": episodica_filtrada,
    "rag_fragments": rag_filtrado,
    "tool_results": session.get("resultados_herramientas", {}),
    "objetivos_activos": objetivos_activos,
}
```

#### Fase E — Construcción del Prompt

Se ensambla en orden estricto (ver Parte 6).

---

## PARTE 2 — JERARQUÍA DE CONTEXTO

### Prioridad absoluta (no negociable)

| Nivel | Componente | Peso | Razón |
|-------|-----------|------|-------|
| 1 | Mensaje actual del usuario | 100% | Es lo que hay que responder |
| 2 | Working session | 95% | Estado actual de la conversación, lo que está pasando ahora |
| 3 | Objetivos activos | 90% | Qué debe lograr esta interacción |
| 4 | Resultados de tools (esta sesión) | 85% | Datos concretos ya calculados (precios, horarios) |
| 5 | Mensajes recientes del historial | 80% | Últimos intercambios para coherencia inmediata |
| 6 | Memoria episódica relevante | 60% | Contexto de conversaciones anteriores relacionadas |
| 7 | Perfil del usuario | 50% | Quién es, qué moto tiene, preferencias |
| 8 | Fragmentos RAG | 40% | Conocimiento del taller necesario para responder |
| 9 | Personalidad | 30% | Tono, estilo, formalidad |

### Qué NO entra al contexto

- Mensajes con score < 0.75 en Qdrant
- Fragmentos RAG duplicados o contradictorios
- Información de otros clientes (filtro estricto por telefono)
- Logs internos
- Datos de rate limiting
- IDs internos (embedding_id, trace_id)
- Información de sesiones expiradas (> 30 min)
- Mensajes de más de 7 días si no son relevantes por embedding

### Regla de peso relativo

```
Si dos niveles entran en conflicto:
  Nivel superior gana SIEMPRE
  Pero si nivel 8 (RAG) contradice nivel 2 (session) → generar refutation en lugar de ignorar
  Ej: session dice "precio cotizado: $350" y RAG dice "$400" → incluir ambos con aclaración
```

---

## PARTE 3 — MEMORIA EPISÓDICA

### Estrategia de búsqueda

```python
def retrieve_episodic(telefono, mensaje, n=5):
    # 1. Embedding del mensaje actual
    query_vector = gemini.embed(mensaje)

    # 2. Búsqueda principal en Qdrant
    results = qdrant.search(
        collection="conversaciones",
        query_vector=query_vector,
        filter=Filter(must=[
            FieldCondition(key="telefono", match=MatchValue(telefono)),
        ]),
        limit=n * 3,        # sobremuestreo 3x
        score_threshold=0.60
    )

    # 3. Filtro temporal
    now = time.time()
    results = [r for r in results
               if (now - r.payload["timestamp"]) < 7 * 86400  # última semana
               or r.score > 0.85]                             # o muy relevante sin importar fecha

    # 4. Penalización por antigüedad
    for r in results:
        age_days = (now - r.payload["timestamp"]) / 86400
        if age_days > 7:
            r.score *= max(0.5, 1.0 - (age_days / 30) * 0.5)

    # 5. Top-N final
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:n]
```

### Categorías de recuperación prioritaria

| Categoría | Prioridad | Condición |
|-----------|-----------|-----------|
| `CITA_CONFIRMADA` | Alta | Si hay fecha/hora en payload |
| `QUEJA_ABIERTA` | Alta | Si estado queja = pendiente |
| `COTIZACION` | Media | Si servicio coincide con entidades actuales |
| `SERVICIO_REALIZADO` | Media | Si moto coincide |
| `GENERAL` | Baja | Sin match específico |

### Ventana temporal

- Últimas 24h: recuperación sin restricción (score 0.60+)
- 24h-7días: solo si score 0.75+
- 7-30 días: solo si score 0.85+
- > 30 días: solo si score 0.90+ y match exacto de entidad (servicio, moto)

### Ejemplo de payload recuperado

```json
{
  "id_mensaje": 1234,
  "rol": "assistant",
  "contenido": "El cambio de aceite para Italika FT150 cuesta entre $350 y $550. ¿Te gustaría agendar una cita?",
  "categoria": "COTIZACION",
  "timestamp": 1717171200,
  "entidades": { "servicio": "cambio de aceite", "moto": "Italika FT150" },
  "resuelto": true,
  "conversacion_id": 5
}
```

---

## PARTE 4 — MEMORIA SEMÁNTICA

### Qué se almacena

| Tabla | Campos | Propósito |
|-------|--------|-----------|
| `clientes.motos_registradas` | `["Italika FT150", "Honda CB190"]` | Saber qué moto(s) tiene |
| `perfiles_usuario.servicios_frecuentes` | `["cambio aceite", "frenos"]` | Saber qué servicios prefiere |
| `perfiles_usuario.frecuencia_visitas` | `"mensual"` | Saber cada cuánto va |
| `perfiles_usuario.preferencia_horario` | `"sabados"` | Saber cuándo prefiere ir |
| `perfiles_usuario.segmento` | `"frecuente"` | Saber tipo de cliente |
| `perfiles_usuario.gasto_promedio` | `450.00` | Saber cuánto gasta en promedio |
| `perfiles_usuario.satisfaccion_promedio` | `4.5` | Saber si está satisfecho |
| `clientes.notas` | `"Cliente prefiere aceite sintético"` | Notas internas del taller |

### Qué NO se almacena

- Conversaciones completas (eso es episódica)
- Mensajes individuales sueltos (eso es historial MySQL)
- Embeddings de conversaciones (eso es Qdrant)
- Datos de facturación detallada
- Información de otros clientes

### Cómo se indexa

La memoria semántica del usuario vive en **MySQL** (no en vectores), porque:

1. Es pequeña (1 fila por cliente)
2. Se recupera por `cliente_id`, no por similitud semántica
3. Cambia con poca frecuencia
4. Necesita joins con otras tablas

Se actualiza mediante triggers después de cada interacción:

```sql
-- Después de agendar: actualizar frecuencia
UPDATE perfiles_usuario
SET frecuencia_visitas = calcular_frecuencia(cliente_id),
    servicios_frecuentes = actualizar_servicios(cliente_id, '${servicio}')
WHERE cliente_id = ${id};

-- Después de completar servicio: actualizar gasto
UPDATE perfiles_usuario
SET total_gastado = total_gastado + ${monto},
    gasto_promedio = total_gastado / (SELECT COUNT(*) FROM citas WHERE estado = 'completada' AND cliente_id = ${id})
WHERE cliente_id = ${id};
```

### Cómo se recupera

```python
async def get_user_semantic_memory(cliente_id: int) -> dict:
    query = """
        SELECT
            c.nombre, c.telefono, c.motos_registradas, c.notas,
            p.frecuencia_visitas, p.servicios_frecuentes,
            p.preferencia_horario, p.segmento,
            p.gasto_promedio, p.total_gastado, p.satisfaccion_promedio
        FROM clientes c
        LEFT JOIN perfiles_usuario p ON p.cliente_id = c.id
        WHERE c.id = :cliente_id
    """
    return await db.fetch_one(query, {"cliente_id": cliente_id})
```

Siempre se recupera completa si existe. Ocupa < 1KB.

---

## PARTE 5 — RAG

### Qué va al RAG (colección `conocimiento`)

| Tipo | Fragmentación | Tamaño | Prioridad |
|------|-------------|--------|-----------|
| Catálogo de servicios (nombre, precio, descripción) | 1 servicio = 1 chunk | < 200 tokens | Alta |
| Procedimientos de diagnóstico (pasos, causas, síntomas) | Por sección | 300-500 tokens | Alta |
| Políticas del taller (garantías, cancelaciones, horarios) | Por política | 200-400 tokens | Alta |
| Preguntas frecuentes (pregunta + respuesta) | 1 FAQ = 1 chunk | < 200 tokens | Alta |
| Manuales técnicos (por sistema: frenos, motor, eléctrico) | Por tema con overlap 100 | 500-800 tokens | Media |
| Marcas y modelos compatibles | Por marca | < 300 tokens | Alta |
| Precios actualizados | Por categoría de servicio | < 200 tokens | Alta |

### Qué NO va al RAG

- Conversaciones de clientes (van a colección `conversaciones`)
- Datos personales (van a MySQL)
- Información temporal volátil (promociones semanales)
- Logs internos
- Sesiones activas
- Información de otros talleres
- Precios desactualizados (se marcan como `activo: false`)

### Chunking

```python
def chunk_document(doc: dict) -> list[dict]:
    tipo = doc["tipo"]

    if tipo == "servicio":
        # Un servicio completo es pequeño, no se subdivide
        return [doc]

    elif tipo == "procedimiento":
        sections = split_by_headers(doc["contenido"])
        chunks = []
        for section in sections:
            tokens = count_tokens(section)
            if tokens > 500:
                subchunks = split_by_paragraphs(section, max_tokens=500)
                chunks.extend(subchunks)
            else:
                chunks.append(section)
        return chunks

    elif tipo == "politica":
        paragraphs = split_by_paragraphs(doc["contenido"], max_tokens=400)
        return paragraphs

    elif tipo == "faq":
        return [{"pregunta": doc["pregunta"], "respuesta": doc["respuesta"]}]

    elif tipo == "manual":
        sections = split_by_topics(doc["contenido"], max_tokens=800, overlap=100)
        return sections
```

### Embeddings

- Modelo: `text-embedding-004` (Gemini)
- Dimensión: 768
- Batch: 10 documentos simultáneos
- Cache: embeddings de queries recurrentes (Redis, TTL 1h)

### Recuperación

```python
async def retrieve_rag(query: str, entidades: dict = None, top_k: int = 3):
    # 1. Embedding de la query
    query_vector = await gemini.embed(query)

    # 2. Búsqueda vectorial primaria (3x sobremuestreo)
    vector_results = await qdrant.search(
        collection="conocimiento",
        query_vector=query_vector,
        limit=top_k * 3,
        score_threshold=0.65,
    )

    # 3. Búsqueda por filtros de entidades
    filtered_results = []
    if entidades:
        filters = []
        if entidades.get("servicio"):
            filters.append(FieldCondition(key="tags", match=MatchValue(entidades["servicio"])))
        if entidades.get("categoria"):
            filters.append(FieldCondition(key="categoria", match=MatchValue(entidades["categoria"])))
        if filters:
            filtered_results = await qdrant.search(
                collection="conocimiento",
                query_vector=query_vector,
                query_filter=Filter(must=filters),
                limit=top_k * 2,
                score_threshold=0.70,
            )

    # 4. RRF Fusion
    fused = rrf_fusion([vector_results, filtered_results], weights=[0.6, 0.4])

    # 5. Re-ranking con LLM
    reranked = await reranker.rerank(query, fused[:top_k * 2], top_k=top_k)

    # 6. Threshold final
    return [r for r in reranked if r.score >= 0.75]
```

### Re-ranking

```python
async def rerank(query: str, candidates: list, top_k: int) -> list:
    if not candidates:
        return []

    prompt = f"""Evalúa la relevancia de cada fragmento para responder esta consulta.

CONSULTA: {query}

FRAGMENTOS:
{chr(10).join(f'[{i}] {c.payload["contenido"][:200]}' for i, c in enumerate(candidates))}

Responde SOLO un JSON con scores del 0.0 al 1.0:
{{"scores": [0.95, 0.30, 0.80, ...]}}"""

    response = await gemini.generate(prompt, temperature=0.1, response_mime_type="application/json")
    scores = json.loads(response).get("scores", [])

    for i, candidate in enumerate(candidates):
        if i < len(scores):
            score_llm = scores[i]
            candidate.score = (candidate.score * 0.4) + (score_llm * 0.6)

    candidates.sort(key=lambda r: r.score, reverse=True)
    return candidates[:top_k]
```

---

## PARTE 6 — CONSTRUCCIÓN DEL PROMPT

### Estructura del prompt final (orden exacto)

```
[SYSTEM PROMPT]           ← Personalidad + reglas de negocio + restricciones
                          ← (~500 tokens)

[CONTEXT: SESSION]        ← Estado actual de la conversación + objetivos activos
                          ← (~200 tokens)

[CONTEXT: USER PROFILE]   ← Quién es el usuario, su moto, preferencias
                          ← (~200 tokens)

[CONTEXT: TOOL RESULTS]   ← Resultados de herramientas ejecutadas en esta sesión
                          ← (~300 tokens)

[CONTEXT: RECENT HISTORY] ← Últimos mensajes del historial (comprimido si es largo)
                          ← (~500 tokens)

[CONTEXT: EPISODIC MEMORY]← Recuerdos relevantes de conversaciones pasadas
                          ← (~400 tokens)

[CONTEXT: RAG]            ← Fragmentos de conocimiento del taller
                          ← (~600 tokens)

[USER MESSAGE]            ← El mensaje actual del usuario
                          ← (~200 tokens)

[INSTRUCTION]             ← Qué debe hacer el LLM con todo lo anterior
                          ← (~100 tokens)
```

### Razón del orden

1. **System Prompt primero**: El modelo necesita conocer su rol y restricciones antes de leer cualquier contexto. Esto previene que el contexto contaminé su comportamiento.

2. **Session + Profile antes que memoria**: El modelo debe saber "dónde estamos ahora" antes de "qué pasó antes". Esto evita que recuerdos antiguos dominen la conversación actual.

3. **Tool Results antes que History**: Los datos concretos (precios, horarios) tienen prioridad sobre el historial conversacional. Si hay conflicto, los datos de herramientas ganan.

4. **Recent History antes que Episodic Memory**: Lo que acaba de pasar es más relevante que lo que pasó hace días.

5. **RAG al final del contexto**: El conocimiento general va después de la información específica del usuario. El modelo primero procesa "quién es el usuario" y luego "qué sabe el taller".

6. **User Message justo antes de Instruction**: El mensaje actual debe estar fresco en la atención del modelo.

7. **Instruction al final**: Instrucción explícita de qué hacer con todo el contexto.

### Límites de tokens por nivel

| Componente | Tokens | Si excede |
|-----------|--------|-----------|
| System Prompt | 500 | Se trunca desde el final (lo menos importante) |
| Session | 200 | Se trunca desde el medio (estado actual siempre) |
| Profile | 200 | Se trunca dejando solo nombre + moto + segmento |
| Tool Results | 300 | Se truncan los resultados menos recientes |
| History | 500 | Se comprime (ver Parte 7) |
| Episodic Memory | 400 | Se descartan los de menor score |
| RAG | 600 | Se descartan los de menor score |
| User Message | 200 | Se trunca a 4096 chars ya validado |
| Instruction | 100 | No negociable |

**Total máximo: 3000 tokens** (deja margen para la respuesta del modelo).

### Ejemplo real de prompt generado

```
[SISTEMA]
Eres Timón, el asistente virtual de MotoServicio Timón, un taller de motos en
México especializado en servicio y reparación de motocicletas.

REGLAS DE CONDUCTA:
- Siempre hablas en español mexicano.
- Usas un tono amable pero profesional.
- NUNCA inventas precios. Siempre consultas la base de datos.
- NUNCA inventas horarios disponibles. Siempre consultas la base de datos.
- Si no sabes algo, dices "No tengo esa información, ¿quieres que te contacte con un asesor?"
- Proporcionas información basada únicamente en el contexto proporcionado.

PERSONALIDAD:
- Amable, paciente, servicial.
- Explicas las cosas claramente sin jerga técnica innecesaria.
- Siempre confirmas antes de agendar.
- Usas frases como "claro que sí", "con gusto", "déjame consultarlo".

[ESTADO ACTUAL]
- Sesión: activa desde hace 2 minutos
- Intención actual: COTIZACION + AGENDAMIENTO
- Pasos completados: consultar_precio ✓
- Esperando: confirmación del usuario para agendar

[PERFIL DEL USUARIO]
- Nombre: Daniel
- Moto principal: Italika FT150
- Segmento: cliente nuevo
- Historial: primera interacción

[RESULTADOS DE HERRAMIENTAS]
- consultar_precio(cambio aceite, Italika FT150):
  → Precio: $350 - $550
  → Incluye: 1L aceite 20W-50, filtro de aceite, mano de obra
  → Tiempo estimado: 30 minutos
- consultar_disponibilidad(mañana, cambio aceite):
  → Horarios: 9:00, 10:00, 11:00, 12:00, 13:00, 14:00
  → Nota: los sábados cerramos a las 14:00

[HISTORIAL RECIENTE]
Usuario: "Hola, ¿cuánto cuesta el cambio de aceite para mi Italika FT150?"
Asistente: "¡Hola Daniel! El cambio de aceite para tu Italika FT150 cuesta entre $350 y $550, e incluye aceite 20W-50, filtro y mano de obra. ¿Te gustaría agendar una cita?"
Usuario: "Sí, ¿puedo ir mañana?"

[MEMORIA EPISÓDICA RELEVANTE]
(No hay conversaciones previas — primera vez)

[INFORMACIÓN DEL TALLER]
- Cambio de aceite + filtro: servicio de mantenimiento básico.
- Incluye: drenado de aceite usado, reemplazo de filtro, llenado con aceite nuevo 20W-50.
- Tiempo: 30 minutos.
- Precio: $350 - $550 dependiendo de la marca de aceite.
- Válido para: Italika, Honda, Yamaha, Vento. Motos 4T.

[INSTRUCCIÓN]
Responde al usuario amablemente. Proporciona la información solicitada basada
en el contexto anterior. Confirma el servicio y el precio. Pregunta si desea
agendar en alguno de los horarios disponibles. Si el usuario quiere agendar,
confirma todos los detalles antes de proceder.
```

---

## PARTE 7 — GESTIÓN DE TOKENS

### Reglas concretas

#### Regla 1: Ventana de historial
```
SI la conversación activa tiene ≤ 6 mensajes:
  → Incluir TODOS completos

SI la conversación activa tiene 7-20 mensajes:
  → Incluir últimos 6 completos
  → Resumir mensajes 1..(N-6) en 1 bloque de ≤ 3 oraciones
  → Regla de resumen: "El usuario preguntó X. Se le informó Y. Se acordó Z."

SI la conversación activa tiene > 20 mensajes:
  → Usar resumen guardado en conversaciones.resumen (se actualiza cada 10 mensajes)
  → Incluir solo últimos 4 mensajes completos
  → Si no hay resumen guardado → generar resumen ahora y guardarlo
```

#### Regla 2: Compresión de memoria episódica
```
SI hay ≤ 3 items episódicos:
  → Incluir todos completos

SI hay 4-5 items:
  → Incluir top-3 completos
  → Item 4-5: solo 1 oración de resumen

SI hay > 5 items (no debería pasar, pero por si acaso):
  → Incluir top-3 con score > 0.80
  → Descartar el resto
```

#### Regla 3: Compresión de RAG
```
SI hay ≤ 2 fragmentos RAG:
  → Incluir completos

SI hay 3 fragmentos:
  → Incluir top-2 completos
  → Fragmento 3: solo metadata + primera oración

SI hay > 3 fragmentos:
  → Incluir top-2 completos
  → Descartar el resto
```

#### Regla 4: Cuándo resumir (trigger)
```
La conversación se resume automáticamente cuando:
  1. El mensaje actual es el #10, #20, #30... (cada 10 mensajes)
  2. Han pasado > 30 minutos desde el último mensaje (nueva sesión)
  3. El estado cambia a "cerrada"
  4. Se detecta un cambio de tema (intención_actual cambia)

El resumen se guarda en conversaciones.resumen y se actualiza incrementalmente:
  "Resumen anterior. + Nuevos mensajes: [resumen de los últimos 10 mensajes]"
```

#### Regla 5: Qué se conserva siempre
```
SIN EXCEPCIÓN:
  - Mensaje actual del usuario
  - Estado de la sesión actual
  - Objetivos activos
  - Resultados de herramientas de esta sesión
  - System prompt (personalidad + reglas)

CON EXCEPCIÓN (si hay espacio de tokens):
  - Últimos 2 mensajes del historial
  - Perfil del usuario (nombre + moto)
```

#### Regla 6: Qué se elimina primero
```
Orden de eliminación cuando se excede el límite de tokens:
  1. Fragmentos RAG de menor score
  2. Items de memoria episódica de menor score
  3. Historial comprimido (se comprime más agresivamente)
  4. Perfil del usuario (campos menos importantes primero)
```

### Cómo se resume

```python
async def summarize_conversation(messages: list[dict], existing_summary: str = None) -> str:
    if existing_summary:
        prompt = f"""Resumen anterior: {existing_summary}

Nuevos mensajes a agregar:
{chr(10).join(f'{m["rol"]}: {m["contenido"]}' for m in messages[-10:])}

Genera un resumen actualizado en 2-3 oraciones. Incluye: tema principal,
decisiones tomadas, siguiente paso acordado."""
    else:
        prompt = f"""Genera un resumen de esta conversación en 2-3 oraciones.
Incluye: tema principal, información intercambiada, decisiones tomadas.

Mensajes:
{chr(10).join(f'{m["rol"]}: {m["contenido"]}' for m in messages)}"""

    summary = await gemini.generate(prompt, temperature=0.2, max_tokens=150)
    return summary
```

---

## PARTE 8 — OBJETIVOS ACTIVOS

### Cómo se detectan

Los objetivos se detectan durante la clasificación de intención:

```json
// Salida del clasificador de intención
{
  "intencion_principal": "COTIZACION",
  "intenciones_secundarias": ["AGENDAMIENTO"],
  "confianza": 0.95,
  "objetivos": [
    {
      "id": "obj_001",
      "tipo": "COTIZAR_SERVICIO",
      "servicio": "cambio de aceite",
      "moto": "Italika FT150",
      "estado": "completado",
      "resultado": { "precio_min": 350, "precio_max": 550 }
    },
    {
      "id": "obj_002",
      "tipo": "AGENDAR_CITA",
      "servicio": "cambio de aceite",
      "fecha_sugerida": "mañana",
      "estado": "pendiente",
      "depende_de": "obj_001"
    }
  ]
}
```

### Cómo se almacenan

```python
# En working memory (Redis)
session["objetivos"] = [
    {
        "id": "obj_001",
        "tipo": "COTIZAR_SERVICIO",
        "servicio": "cambio de aceite",
        "estado": "completado",
        "resultado": {"precio_min": 350, "precio_max": 550},
    },
    {
        "id": "obj_002",
        "tipo": "AGENDAR_CITA",
        "servicio": "cambio de aceite",
        "estado": "pendiente",
        "fecha_sugerida": "mañana",
    }
]
```

### Estados de objetivo

| Estado | Significado |
|--------|-------------|
| `pendiente` | No se ha empezado a trabajar |
| `en_progreso` | Se está ejecutando |
| `completado` | Se ejecutó exitosamente |
| `fallido` | No se pudo completar (tool error) |
| `cancelado` | El usuario cambió de opinión |
| `bloqueado` | Depende de otro objetivo no completado |

### Cómo se actualizan

```python
class ObjectiveTracker:
    def __init__(self, session: dict):
        self.objectives = session.get("objetivos", [])

    def add(self, objective: dict):
        objective["id"] = f"obj_{uuid4().hex[:8]}"
        objective["creado"] = int(time.time())
        self.objectives.append(objective)

    def complete(self, obj_id: str, resultado: dict):
        for obj in self.objectives:
            if obj["id"] == obj_id:
                obj["estado"] = "completado"
                obj["resultado"] = resultado
                # Desbloquear dependientes
                for dep in self.objectives:
                    if dep.get("depende_de") == obj_id and dep["estado"] == "bloqueado":
                        dep["estado"] = "pendiente"
                break

    def fail(self, obj_id: str, error: str):
        for obj in self.objectives:
            if obj["id"] == obj_id:
                obj["estado"] = "fallido"
                obj["error"] = error
                break

    def cancel(self, obj_id: str):
        for obj in self.objectives:
            if obj["id"] == obj_id:
                obj["estado"] = "cancelado"
                break

    def get_active(self) -> list:
        return [o for o in self.objectives if o["estado"] in ("pendiente", "en_progreso")]

    def next_action(self) -> Optional[dict]:
        """Devuelve el siguiente objetivo no bloqueado que debe ejecutarse"""
        active = self.get_active()
        for obj in active:
            if obj.get("depende_de"):
                dep = next((o for o in self.objectives if o["id"] == obj["depende_de"]), None)
                if dep and dep["estado"] != "completado":
                    continue
            return obj
        return active[0] if active else None

    def to_prompt_context(self) -> str:
        active = self.get_active()
        if not active:
            return "No hay objetivos activos pendientes."
        lines = ["OBJETIVOS ACTIVOS:"]
        for obj in active:
            lines.append(f"- {self._describe(obj)}")
        return "\n".join(lines)

    def _describe(self, obj: dict) -> str:
        if obj["tipo"] == "COTIZAR_SERVICIO":
            return f"Consultar precio de {obj.get('servicio', 'servicio')} para {obj.get('moto', 'la moto')}"
        if obj["tipo"] == "AGENDAR_CITA":
            return f"Agendar cita para {obj.get('servicio', 'servicio')} (estado: {obj['estado']})"
        if obj["tipo"] == "REGISTRAR_CLIENTE":
            return f"Registrar datos del cliente"
        return f"{obj['tipo']}: {obj.get('estado', 'pendiente')}"
```

### Cómo se recuperan en el Context Builder

```python
# En Fase D del Context Builder
objetivos_activos = objective_tracker.get_active()
context["objetivos_activos"] = {
    "hay_pendientes": len(objetivos_activos) > 0,
    "siguiente_paso": objective_tracker.next_action(),
    "descripcion": objective_tracker.to_prompt_context() if objetivos_activos else None,
}
```

---

## PARTE 9 — PERSONALIDAD

### Tono y estilo

```
TONO BASE:
- Amable pero profesional (no "wey", no "bro", no superlativos exagerados)
- Tranquilo y paciente, incluso si el usuario es insistente
- Respetuoso, tratando de "usted" implícito (usa "¿gustas?" en lugar de "¿quieres?")
- Mexicano neutro (no regionalismos extremos, pero sí modismos naturales)

ESTILO:
- Oraciones claras y directas
- Sin jerga técnica innecesaria
- Explicaciones con analogías simples cuando sea necesario
- Confirmaciones explícitas antes de acciones
- Uso de cortesía: "claro que sí", "con gusto", "déjame verificarlo", "por supuesto"

FORMALIDAD:
- Moderada. No es formal como un banco, no es informal como un amigo.
- Es como un mecánico de confianza: sabe del tema pero explica con paciencia.
- Se adapta al usuario: si el usuario es técnico, puede usar más jerga.
```

### System prompt de personalidad (fijo)

```
Eres Timón, el asistente virtual de MotoServicio Timón, un taller de motos en México.

PERSONALIDAD:
- Eres amable, paciente y servicial, como un mecánico de confianza.
- Explicas con claridad, sin jerga innecesaria.
- Usas frases como "claro que sí", "con gusto", "déjame consultarlo", "por supuesto".
- Siempre confirmas antes de tomar acciones (agendar, cotizar, etc.).
- Si el usuario no entiende, buscas otra forma de explicarlo.

REGLAS DE CONDUCTA:
- NUNCA inventes información. Si no la tienes en el contexto, di que no la sabes.
- NUNCA modifiques datos sin confirmación explícita del usuario.
- NUNCA compartas información de otros clientes.
- Siempre verificas precios y horarios en los datos disponibles.
- Si el usuario está molesto, mantén la calma y ofrece soluciones.
- Si no puedes resolver, ofrece contactar con un asesor humano.

IDIOMA:
- Siemrespondes en español mexicano.
- Usas "¿gustas?" para ofrecer opciones.
- Usas "déjame" para acciones que vas a realizar.
```

### Adaptación al usuario

```python
def get_personality_adjustment(user_profile: dict, session: dict) -> str:
    """Devuelve un ajuste de personalidad basado en el perfil del usuario."""
    adjustments = []

    frecuencia = user_profile.get("frecuencia_visitas", "desconocida")
    if frecuencia == "frecuente":
        adjustments.append("El usuario es cliente frecuente. Usa un tono más familiar.")
    elif frecuencia == "nuevo":
        adjustments.append("El usuario es nuevo. Sé más explicativo y paciente.")

    quejas_pendientes = session.get("quejas_pendientes", 0)
    if quejas_pendientes > 0:
        adjustments.append("El usuario tiene quejas pendientes. Sé especialmente cortés y resolutivo.")

    if user_profile.get("segmento") == "vip":
        adjustments.append("El usuario es cliente VIP. Ofrece atención prioritaria.")

    if not adjustments:
        return ""

    return "AJUSTE DE PERSONALIDAD:\n" + "\n".join(adjustments)
```

---

## PARTE 10 — ALUCINACIONES

### Mecanismos concretos

#### M1 — Validación previa (antes de generar)

```
REGLAS ESTRICTAS EN EL SYSTEM PROMPT:
  "NUNCA inventes precios. Usa SOLO la información de [RESULTADOS DE HERRAMIENTAS]
   o [INFORMACIÓN DEL TALLER]."
  "NUNCA inventes horarios disponibles. Usa SOLO la información de
   [RESULTADOS DE HERRAMIENTAS]."
  "Si no encuentras la información en el contexto, responde:
   'No tengo esa información, ¿quieres que te contacte con un asesor?'"
```

#### M2 — Source grounding obligatorio

```
REGLA EN EL PROMPT:
  "Cada vez que menciones un precio, horario, o dato concreto,
   indica su fuente entre corchetes. Ejemplo:
   'El cambio de aceite cuesta $350-$550 [Fuente: Catálogo de Servicios].'"
```

#### M3 — Validación posterior (reflection loop)

```python
async def validate_response(original_message: str, response: str, context: dict) -> dict:
    prompt = f"""Evalúa si la siguiente respuesta contiene información verificable
que NO está respaldada por el contexto proporcionado.

CONSULTA DEL USUARIO: {original_message}

RESPUESTA A EVALUAR: {response}

CONTEXTO DISPONIBLE:
PRECIOS EN CONTEXTO: {_extract_prices(context)}
HORARIOS EN CONTEXTO: {_extract_hours(context)}
FECHAS EN CONTEXTO: {_extract_dates(context)}

Responde JSON:
{{
  "decision": "APROBADA" | "RECHAZADA",
  "problemas": ["descripción de cada problema encontrado"],
  "puntaje": 0.0-1.0,
  "feedback": "qué corregir para la regeneración"
}}"""

    result = await gemini.generate(prompt, temperature=0.1, response_mime_type="application/json")
    evaluation = json.loads(result)

    return {
        "decision": evaluation.get("decision", "APROBADA"),
        "problemas": evaluation.get("problemas", []),
        "score": evaluation.get("puntaje", 1.0),
        "feedback": evaluation.get("feedback", ""),
    }
```

#### M4 — Verificación contra herramientas

```
ANTES DE RESPONDER:
  Si la respuesta menciona un precio → verificar que existe en tool_results
  Si la respuesta menciona un horario → verificar que existe en tool_results
  Si la respuesta agenda una cita → verificar que se ejecutó la tool agendar_cita

REGLAS:
  - Si la respuesta dice un precio que NO está en tool_results → RECHAZAR
  - Si la respuesta dice "te agendé" sin tool ejecutada → RECHAZAR
  - Si la respuesta dice "mañana abrimos" sin consultar disponibilidad → RECHAZAR
```

#### M5 — Fallback honesto

```python
FALLBACK_MESSAGE = (
    "No tengo esa información disponible en este momento. "
    "¿Quieres que te contacte con un asesor del taller "
    "para que pueda ayudarte mejor?"
)

# Se activa cuando:
# 1. Contexto vacío (no se recuperó nada relevante)
# 2. Score de contexto < 0.50
# 3. Reflection loop rechazó 2 veces seguidas
# 4. Error en Gemini (API down)
```

#### M6 — Restricciones de formato

```python
# En el system prompt, como instrucción explícita:
INSTRUCCIONES_ANTI_ALUCINACION = """
RESTRICCIONES:
1. NO puedes inventar precios. Si no están en el contexto, NO los menciones.
2. NO puedes inventar horarios. Si no están en el contexto, NO los menciones.
3. NO puedes confirmar citas sin ejecutar la herramienta agendar_cita.
4. NO puedes modificar información del usuario sin su consentimiento.
5. Si el contexto no tiene suficiente información, usa el mensaje de fallback.
6. Cada afirmación con datos concretos debe poder rastrearse al contexto.

FORMATO DE RESPUESTA:
- Respuestas cortas y directas (< 200 tokens idealmente)
- Si hay múltiples opciones, preséntalas como lista
- Siempre termina con una pregunta para avanzar la conversación
"""
```

---

## PARTE 11 — EJEMPLOS COMPLETOS

### Ejemplo 1: Cotización con cliente nuevo

**Usuario:** "Hola, ¿cuánto cuesta el cambio de aceite para mi Italika FT150?"

**Perfil:** No existe (nuevo cliente)

**Session:** `{"estado": "NUEVA_CONSULTA", "mensajes_en_sesion": 0}`

**Objetivos activos:** Ninguno

**Memoria episódica:** Vacía (sin historial)

**RAG recuperado:**
```
[score: 0.92] Servicio: Cambio de Aceite + Filtro
Precio: $350 - $550 | Incluye: aceite 20W-50, filtro, mano de obra
Tiempo: 30 min | Compatible: Italika, Honda, Yamaha
```

**Tool results:** (no ejecutadas aún)

**Prompt final:**
```
[SISTEMA]
Eres Timón, el asistente virtual de MotoServicio Timón...

[ESTADO ACTUAL]
- Sesión: nueva, primer mensaje
- Intención: COTIZACION
- Cliente: no registrado aún

[PERFIL DEL USUARIO]
No hay perfil disponible — cliente nuevo.

[RESULTADOS DE HERRAMIENTAS]
(Ninguna ejecutada aún)

[HISTORIAL RECIENTE]
(No hay historial previo)

[MEMORIA EPISÓDICA RELEVANTE]
(No hay conversaciones previas)

[INFORMACIÓN DEL TALLER]
- Cambio de Aceite + Filtro: servicio de mantenimiento básico.
- Incluye: drenado de aceite usado, reemplazo de filtro, llenado con aceite nuevo 20W-50.
- Tiempo: 30 minutos.
- Precio: $350 - $550 dependiendo de la marca de aceite.
- Válido para: Italika, Honda, Yamaha, Vento. Motos 4T.

[INSTRUCCIÓN]
Responde amablemente. Proporciona el precio del cambio de aceite.
Pregunta si desea agendar una cita. Como es cliente nuevo,
ofrece registrar sus datos.
```

---

### Ejemplo 2: Agendamiento después de cotización

**Usuario:** "Sí, agéndame para mañana a las 10"

**Perfil:**
```json
{"nombre": "Daniel", "moto": "Italika FT150", "frecuencia": "nuevo"}
```

**Session:**
```json
{
  "estado": "ESPERANDO_CONFIRMACION_CITA",
  "entidades": {"servicio": "cambio de aceite", "moto": "Italika FT150"},
  "objetivos": [
    {"id": "obj_001", "tipo": "COTIZAR_SERVICIO", "estado": "completado"},
    {"id": "obj_002", "tipo": "REGISTRAR_CLIENTE", "estado": "completado"},
    {"id": "obj_003", "tipo": "AGENDAR_CITA", "servicio": "cambio de aceite",
     "fecha": "mañana", "estado": "pendiente"}
  ]
}
```

**Tool results:**
```json
{
  "consultar_precio": {"precio_min": 350, "precio_max": 550},
  "registrar_cliente": {"cliente_id": 2, "creado": true},
  "consultar_disponibilidad": {"horarios": ["9:00","10:00","11:00","12:00","13:00","14:00"]}
}
```

**Prompt final:**
```
[SISTEMA]
Eres Timón...

[ESTADO ACTUAL]
- Sesión: cliente registrado (ID: 2)
- Intención: AGENDAMIENTO
- Objetivo activo: Agendar cita para cambio de aceite mañana a las 10

[PERFIL DEL USUARIO]
- Nombre: Daniel
- Moto: Italika FT150
- Segmento: nuevo cliente

[RESULTADOS DE HERRAMIENTAS]
- Precio cotizado: $350-$550
- Cliente registrado: ID 2
- Disponibilidad mañana: 9:00, 10:00, 11:00, 12:00, 13:00, 14:00

[HISTORIAL RECIENTE]
Usuario: "Hola, ¿cuánto cuesta el cambio de aceite para mi Italika FT150?"
Asistente: "¡Hola Daniel! El cambio de aceite para tu Italika FT150...
 ¿Te gustaría agendar una cita?"
Usuario: "Sí, agéndame para mañana a las 10"
Asistente: (esta es la respuesta que vamos a generar)

[MEMORIA EPISÓDICA RELEVANTE]
(No hay)

[INSTRUCCIÓN]
El usuario confirmó que quiere agendar. Antes de proceder:
1. Confirma todos los detalles: servicio, fecha, hora, precio.
2. Pregunta si está de acuerdo con agendar.
3. Espera confirmación final antes de ejecutar.
No ejecutes la herramienta agendar_cita todavía — primero confirma.
```

---

### Ejemplo 3: Usuario recurrente con queja

**Usuario:** "Hola, vine la semana pasada y todavía tengo el mismo problema con el freno"

**Perfil:**
```json
{
  "nombre": "Carlos",
  "moto": "Honda CB190",
  "frecuencia": "frecuente",
  "servicios_frecuentes": ["cambio aceite", "frenos"],
  "quejas_pendientes": 1
}
```

**Memoria episódica recuperada:**
```
[score: 0.91, timestamp: hace 7 días]
Usuario: "El freno delantero sigue haciendo ruido después del servicio"
Asistente: "Lo sentimos, agendamos revisión para el jueves"
Categoría: QUEJA

[score: 0.85, timestamp: hace 5 días]
Usuario: "Ya vinimos pero el problema continúa"
Asistente: "Vamos a escalar tu caso con el mecánico jefe"
Categoría: QUEJA
```

**RAG recuperado:**
```
[score: 0.88] Procedimiento: Diagnóstico de frenos
Posibles causas: pastillas desgastadas, disco deformado,
líquido de frenos contaminado, caliper atascado
```

**Session:**
```json
{
  "estado": "ATENDIENDO_QUEJA",
  "queja_id": 5,
  "objetivos": [
    {"id": "obj_001", "tipo": "RESOLVER_QUEJA", "estado": "pendiente"}
  ]
}
```

**Prompt final:**
```
[SISTEMA]
Eres Timón...

[ESTADO ACTUAL]
- Cliente: Carlos (frecuente, cliente de confianza)
- Intención: QUEJA
- Objetivo activo: Resolver queja de frenos
- Historial de quejas: 1 pendiente

[PERFIL DEL USUARIO]
- Nombre: Carlos
- Moto: Honda CB190
- Frecuencia: frecuente
- Servicios previos: cambio aceite, frenos
- NOTA: Tiene una queja abierta. Sé especialmente atento.

[RESULTADOS DE HERRAMIENTAS]
(Ninguna ejecutada aún — necesita diagnóstico)

[HISTORIAL RECIENTE]
(Conversación nueva — pero hay memoria episódica)

[MEMORIA EPISÓDICA]
- Hace 7 días: Reportó ruido en freno delantero después de servicio.
  Se agendó revisión.
- Hace 5 días: Reportó que el problema continúa después de la revisión.
  Se escaló al mecánico jefe.
- Hoy: Reporta que el problema persiste.

[INFORMACIÓN DEL TALLER]
Diagnóstico de frenos:
- Posibles causas: pastillas desgastadas, disco deformado,
  líquido de frenos contaminado, caliper atascado
- Recomendación: revisión completa del sistema de frenos

[INSTRUCCIÓN]
El usuario tiene una queja activa. Es cliente frecuente.
Escucha su problema con empatía. Reconoce que el servicio anterior
no resolvió el problema. Ofrece una solución clara:
- Sugiere una revisión de diagnóstico más profunda
- Ofrece agendar con el mecánico jefe directamente
- NO ofrezcas descuentos sin autorización (debes consultar al taller)
- Pregunta si prefiere venir hoy o agendar una cita
```

---

### Ejemplo 4: Consulta de diagnóstico

**Usuario:** "Mi moto no enciende, solo hace clic clic cuando le doy arranque"

**Perfil:** Cliente existente, Italika FT150

**Session:** `{"estado": "NUEVA_CONSULTA", "intencion_actual": "DIAGNOSTICO"}`

**RAG recuperado:**
```
[score: 0.89] Diagnóstico: Moto no enciende - Solo clic clic
Sistema afectado: Sistema eléctrico / Motor de arranque
Posibles causas:
1. Batería descargada (más común)
2. Motor de arranque dañado
3. Relay de arranque defectuoso
4. Conexiones sueltas en la batería

[score: 0.82] Procedimiento: Verificar batería
1. Medir voltaje con multímetro (>12.4V = OK, <12V = descargada)
2. Verificar bornes limpios y apretados
3. Intentar arranque con pasacorriente
```

**Prompt final:**
```
[SISTEMA]
Eres Timón...

[ESTADO ACTUAL]
- Intención: DIAGNOSTICO
- Cliente: registrado

[PERFIL DEL USUARIO]
- Moto: Italika FT150

[MEMORIA EPISÓDICA]
(No hay diagnósticos previos)

[INFORMACIÓN DEL TALLER]
Diagnóstico: Moto no enciende - Solo clic clic
- Sistema afectado: Sistema eléctrico / Motor de arranque
- Posibles causas:
  1. Batería descargada (más común en Italika FT150)
  2. Motor de arranque dañado
  3. Relay de arranque defectuoso
  4. Conexiones sueltas

[INSTRUCCIÓN]
El usuario describe un problema de arranque. Basado en la información
del taller, sugiere las causas más probables ordenadas por frecuencia.
Pregunta si quiere agendar un diagnóstico para confirmar la causa exacta.
NO des diagnósticos definitivos — solo posibles causas.
Sugiere que un mecánico revise la moto para confirmar.
```

---

### Ejemplo 5: Cambio de tema mid-conversación

**Usuario:** "¿A qué hora cierran los sábados?"

**Contexto previo:** El usuario estaba en medio de una cotización de cambio de aceite

**Session:**
```json
{
  "estado": "EN_COTIZACION",
  "objetivos": [
    {"id": "obj_001", "tipo": "COTIZAR_SERVICIO", "estado": "completado"},
    {"id": "obj_002", "tipo": "AGENDAR_CITA", "estado": "pendiente"}
  ],
  "ultimo_tema": "COTIZACION"
}
```

**RAG recuperado:**
```
[score: 0.95] Política: Horarios del taller
Lunes a viernes: 9:00 - 18:00
Sábados: 9:00 - 14:00
Domingos: Cerrado
```

**Prompt final:**
```
[SISTEMA]
Eres Timón...

[ESTADO ACTUAL]
- Intención: PREGUNTA_HORARIO (cambio de tema)
- Objetivos pendientes: agendar cita para cambio de aceite
- NOTA: El usuario cambió de tema temporalmente.
  Responde su pregunta pero mantén el objetivo activo.

[PERFIL DEL USUARIO]
- Nombre: Daniel
- Moto: Italika FT150

[RESULTADOS DE HERRAMIENTAS]
- Precio cambio aceite: $350-$550
- Disponibilidad mañana: 9:00, 10:00, 11:00, 12:00, 13:00, 14:00

[HISTORIAL RECIENTE]
Usuario: "Hola, ¿cuánto cuesta el cambio de aceite para mi Italika FT150?"
Asistente: "El cambio de aceite cuesta entre $350 y $550..."
Asistente: "¿Te gustaría agendar una cita?"
Usuario: "¿A qué hora cierran los sábados?"

[INFORMACIÓN DEL TALLER]
Horarios:
- Lunes a viernes: 9:00 - 18:00
- Sábados: 9:00 - 14:00
- Domingos: Cerrado

[INSTRUCCIÓN]
El usuario preguntó sobre horarios después de una cotización.
Responde su pregunta directamente. Luego, retoma suavemente el objetivo
pendiente: "Aprovechando, ¿te gustaría agendar para mañana?"
No seas insistente — si solo quería información, respeta eso.
```

---

## PARTE 12 — PSEUDOCÓDIGO

### 12.1 Context Builder

```python
# app/orchestrator/context_builder.py

import time
import json
import asyncio
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ContextWindow:
    mensaje_actual: str
    session: dict = field(default_factory=dict)
    perfil: dict = field(default_factory=dict)
    historial: list = field(default_factory=list)
    episodica: list = field(default_factory=list)
    rag: list = field(default_factory=list)
    tool_results: dict = field(default_factory=dict)
    objetivos: dict = field(default_factory=dict)
    token_estimate: int = 0


class ContextBuilder:
    def __init__(self, memory_service, rag_service, profile_service, objective_tracker, summarizer):
        self.memory = memory_service
        self.rag = rag_service
        self.profile = profile_service
        self.objectives = objective_tracker
        self.summarizer = summarizer

    async def build(self, telefono: str, mensaje: str, cliente_id: Optional[int] = None) -> ContextWindow:
        start = time.monotonic()
        ctx = ContextWindow(mensaje_actual=mensaje)

        # Fase A: Recuperación paralela
        session_task = self.memory.get_session(telefono)
        perfil_task = self.profile.get_profile(cliente_id) if cliente_id else None
        historial_task = self._get_recent_history(cliente_id, telefono)
        episodica_task = self.memory.retrieve_episodic(telefono, mensaje)
        rag_task = self.rag.retrieve(mensaje, limit=3)

        session = await session_task
        ctx.session = session or {"estado": "NUEVA_CONSULTA"}

        if perfil_task:
            ctx.perfil = await perfil_task or {}

        ctx.historial = await historial_task or []

        episodica_raw = await episodica_task
        ctx.episodica = episodica_raw if episodica_raw else []

        ctx.rag = await rag_task or []

        # Extraer tool_results de session
        ctx.tool_results = ctx.session.get("resultados_herramientas", {})

        # Cargar objetivos activos
        self.objectives.load(ctx.session.get("objetivos", []))
        ctx.objetivos = {
            "hay_pendientes": len(self.objectives.get_active()) > 0,
            "siguiente_paso": self.objectives.next_action(),
        }

        elapsed = (time.monotonic() - start) * 1000
        logger.debug("context_retrieved", telefono=telefono, tiempo_ms=elapsed,
                      items={"session": 1, "perfil": 1 if ctx.perfil else 0,
                             "historial": len(ctx.historial), "episodica": len(ctx.episodica),
                             "rag": len(ctx.rag)})

        # Fase B: Filtrado
        await self._filter_context(ctx)

        # Fase C: Compresión
        await self._compress_context(ctx)

        # Fase D: Estimar tokens
        ctx.token_estimate = self._estimate_tokens(ctx)

        return ctx

    async def _filter_context(self, ctx: ContextWindow):
        """Filtra información irrelevante del contexto."""
        # Filtrar episódica por threshold
        ctx.episodica = [e for e in ctx.episodica if e.get("score", 0) >= 0.75][:5]

        # Filtrar RAG por threshold
        ctx.rag = [r for r in ctx.rag if r.get("score", 0) >= 0.75][:3]

        # Filtrar historial: solo conversación activa
        conv_id = ctx.session.get("conversacion_id")
        if conv_id:
            ctx.historial = [m for m in ctx.historial
                            if m.get("conversacion_id") == conv_id]

    async def _compress_context(self, ctx: ContextWindow):
        """Comprime el historial si es necesario."""
        n_mensajes = len(ctx.historial)

        if n_mensajes > 20:
            # Usar resumen guardado + últimos 4
            resumen = ctx.session.get("resumen_conversacion")
            if not resumen:
                resumen = await self.summarizer.summarize(ctx.historial[:-4])
            ctx.historial = [
                {"tipo": "resumen", "contenido": f"[Resumen de la conversación: {resumen}]"}
            ] + ctx.historial[-4:]

        elif n_mensajes > 6:
            # Resumir los primeros N-6
            resumen = await self.summarizer.summarize(ctx.historial[:-6])
            ctx.historial = [
                {"tipo": "resumen", "contenido": f"[Historial anterior: {resumen}]"}
            ] + ctx.historial[-6:]

    def _estimate_tokens(self, ctx: ContextWindow) -> int:
        """Estimación rápida de tokens (4 chars ≈ 1 token para español)."""
        total = 0
        total += len(ctx.mensaje_actual) // 4
        total += len(json.dumps(ctx.session)) // 4
        total += len(json.dumps(ctx.perfil)) // 4
        total += sum(len(m.get("contenido", "")) // 4 for m in ctx.historial)
        total += sum(len(e.get("contenido", "")) // 4 for e in ctx.episodica)
        total += sum(len(r.get("contenido", "")) // 4 for r in ctx.rag)
        total += len(json.dumps(ctx.tool_results)) // 4
        total += 500  # system prompt fijo
        total += 100  # instruction fijo
        return total


class ContextCompressor:
    """Compresión extra si se excede el límite de tokens."""

    MAX_TOKENS = 3000

    @classmethod
    def compress(cls, ctx: ContextWindow) -> ContextWindow:
        if ctx.token_estimate <= cls.MAX_TOKENS:
            return ctx

        # Orden de sacrificio: RAG > Episódica > Historial > Perfil
        while ctx.token_estimate > cls.MAX_TOKENS and len(ctx.rag) > 1:
            ctx.rag.pop()
            ctx.token_estimate = cls._estimate_tokens(ctx)

        while ctx.token_estimate > cls.MAX_TOKENS and len(ctx.episodica) > 2:
            ctx.episodica.pop()
            ctx.token_estimate = cls._estimate_tokens(ctx)

        while ctx.token_estimate > cls.MAX_TOKENS and len(ctx.historial) > 4:
            ctx.historial.pop(1)  # mantener primero (resumen) y últimos
            ctx.token_estimate = cls._estimate_tokens(ctx)

        while ctx.token_estimate > cls.MAX_TOKENS and ctx.perfil:
            # Reducir perfil a solo nombre y moto
            ctx.perfil = {k: v for k, v in ctx.perfil.items()
                         if k in ("nombre", "motos_registradas")}
            ctx.token_estimate = cls._estimate_tokens(ctx)

        return ctx
```

### 12.2 Prompt Orchestrator

```python
# app/orchestrator/prompt_orchestrator.py

from dataclasses import dataclass
from typing import Optional


class PromptOrchestrator:
    """Ensambla el prompt final según la jerarquía de contexto."""

    SYSTEM_PROMPT = """Eres Timón, el asistente virtual de MotoServicio Timón, un taller de motos en México especializado en servicio y reparación de motocicletas.

PERSONALIDAD:
- Eres amable, paciente y servicial, como un mecánico de confianza.
- Explicas con claridad, sin jerga innecesaria.
- Usas frases como "claro que sí", "con gusto", "déjame consultarlo", "por supuesto".
- Siempre confirmas antes de tomar acciones (agendar, cotizar, etc.).
- Si el usuario no entiende, buscas otra forma de explicarlo.

REGLAS DE CONDUCTA:
- NUNCA inventes información. Si no la tienes en el contexto, di que no la sabes.
- NUNCA modifiques datos sin confirmación explícita del usuario.
- NUNCA compartas información de otros clientes.
- Siempre verificas precios y horarios en los datos disponibles.
- Si el usuario está molesto, mantén la calma y ofrece soluciones.
- Si no puedes resolver, ofrece contactar con un asesor humano.

RESTRICCIONES ANTI-ALUCINACIÓN:
1. NO puedes inventar precios. Si no están en el contexto, NO los menciones.
2. NO puedes inventar horarios. Si no están en el contexto, NO los menciones.
3. NO puedes confirmar citas sin ejecutar la herramienta agendar_cita.
4. NO puedes modificar información del usuario sin su consentimiento.
5. Cada afirmación con datos concretos debe poder rastrearse al contexto.
6. Si no encuentras la información en el contexto, responde exactamente:
   "No tengo esa información disponible, ¿quieres que te contacte con un asesor?"
"""

    def __init__(self):
        self.sections = []

    def build(self, ctx: ContextWindow, adjustment: str = "") -> str:
        self.sections = []

        # Siempre system prompt primero
        self.add_section("SISTEMA", self.SYSTEM_PROMPT_fixed(ctx))

        # Session + Estado actual
        self.add_session(ctx)

        # Perfil del usuario
        self.add_profile(ctx)

        # Tool results
        self.add_tool_results(ctx)

        # Historial reciente
        self.add_history(ctx)

        # Memoria episódica
        self.add_episodic(ctx)

        # RAG
        self.add_rag(ctx)

        # Mensaje actual
        self.add_user_message(ctx)

        # Instrucción final
        self.add_instruction(ctx)

        # Ajuste de personalidad
        if adjustment:
            self.sections.append(adjustment)

        return "\n\n".join(self.sections)

    def SYSTEM_PROMPT_fixed(self, ctx) -> str:
        return self.SYSTEM_PROMPT

    def add_session(self, ctx):
        lines = ["[ESTADO ACTUAL]"]
        session = ctx.session
        lines.append(f"- Sesión: {'nueva' if session.get('estado') == 'NUEVA_CONSULTA' else 'activa'}")
        if session.get("intencion_actual"):
            lines.append(f"- Intención actual: {session['intencion_actual']}")
        if session.get("estado") and session["estado"] != "NUEVA_CONSULTA":
            lines.append(f"- Estado: {session['estado']}")
        if ctx.objetivos.get("siguiente_paso"):
            lines.append(f"- Siguiente paso: {self._describe_next_step(ctx.objetivos['siguiente_paso'])}")
        if ctx.objetivos.get("hay_pendientes"):
            lines.append("- ⚠️ Hay objetivos pendientes por completar")
        self.sections.append("\n".join(lines))

    def add_profile(self, ctx):
        if not ctx.perfil:
            return
        lines = ["[PERFIL DEL USUARIO]"]
        if ctx.perfil.get("nombre"):
            lines.append(f"- Nombre: {ctx.perfil['nombre']}")
        if ctx.perfil.get("motos_registradas"):
            motos = ctx.perfil["motos_registradas"]
            if isinstance(motos, list):
                lines.append(f"- Moto(s): {', '.join(motos)}")
            else:
                lines.append(f"- Moto: {motos}")
        if ctx.perfil.get("frecuencia_visitas"):
            lines.append(f"- Frecuencia: {ctx.perfil['frecuencia_visitas']}")
        if ctx.perfil.get("segmento") == "vip":
            lines.append("- ⭐ Cliente VIP")
        if ctx.perfil.get("quejas_pendientes", 0) > 0:
            lines.append(f"- ⚠️ Tiene {ctx.perfil['quejas_pendientes']} queja(s) pendiente(s)")
        self.sections.append("\n".join(lines))

    def add_tool_results(self, ctx):
        if not ctx.tool_results:
            return
        lines = ["[RESULTADOS DE HERRAMIENTAS]"]
        for tool_name, data in ctx.tool_results.items():
            if isinstance(data, dict):
                lines.append(f"- {tool_name}:")
                for k, v in data.items():
                    lines.append(f"  → {k}: {v}")
            else:
                lines.append(f"- {tool_name}: {data}")
        self.sections.append("\n".join(lines))

    def add_history(self, ctx):
        if not ctx.historial:
            return
        lines = ["[HISTORIAL RECIENTE]"]
        for msg in ctx.historial:
            if msg.get("tipo") == "resumen":
                lines.append(f"[{msg['contenido']}]")
            else:
                rol = "Usuario" if msg.get("rol") == "user" else "Asistente"
                lines.append(f"{rol}: {msg.get('contenido', '')}")
        self.sections.append("\n".join(lines))

    def add_episodic(self, ctx):
        if not ctx.episodica:
            return
        lines = ["[MEMORIA EPISÓDICA RELEVANTE]"]
        for item in ctx.episodica:
            score = item.get("score", 0)
            contenido = item.get("contenido", "")[:200]
            categoria = item.get("categoria", "GENERAL")
            lines.append(f"- [{categoria} | relevancia: {score:.0%}] {contenido}")
        self.sections.append("\n".join(lines))

    def add_rag(self, ctx):
        if not ctx.rag:
            return
        lines = ["[INFORMACIÓN DEL TALLER]"]
        for item in ctx.rag:
            contenido = item.get("contenido", "")
            fuente = item.get("tipo", "conocimiento general")
            lines.append(f"- [{fuente}] {contenido}")
        self.sections.append("\n".join(lines))

    def add_user_message(self, ctx):
        self.sections.append(f"[MENSAJE DEL USUARIO]\n{ctx.mensaje_actual}")

    def add_instruction(self, ctx):
        instruction = """[INSTRUCCIÓN]
Responde al usuario basándote únicamente en el contexto proporcionado arriba.
- Sé amable y directo.
- Usa la información de herramientas y RAG para datos concretos.
- Si el contexto no tiene suficiente información, usa el mensaje de fallback.
- Termina con una pregunta relevante para avanzar la conversación.
- NO ejecutes herramientas — eso lo hace el sistema automáticamente.
"""
        if ctx.objetivos.get("hay_pendientes"):
            instruction += (
                "- RECUERDA: Hay objetivos pendientes. "
                "Si el usuario está de acuerdo, avanza hacia completarlos.\n"
            )
        self.sections.append(instruction)

    def _describe_next_step(self, step: dict) -> str:
        if step.get("tipo") == "COTIZAR_SERVICIO":
            return f"Cotizar {step.get('servicio', 'servicio')}"
        if step.get("tipo") == "AGENDAR_CITA":
            return f"Agendar cita para {step.get('servicio', 'servicio')}"
        if step.get("tipo") == "RESOLVER_QUEJA":
            return "Resolver queja del usuario"
        if step.get("tipo") == "REGISTRAR_CLIENTE":
            return "Registrar datos del cliente"
        return str(step.get("tipo", "desconocido"))
```

### 12.3 Memory Retriever

```python
# app/memory/service.py (versión extendida)

class MemoryService:
    def __init__(self, redis, qdrant, embeddings):
        self.redis = redis
        self.qdrant = qdrant
        self.embeddings = embeddings

    async def get_session(self, telefono: str) -> Optional[dict]:
        data = await self.redis.get(f"session:{telefono}")
        if data:
            session = json.loads(data)
            session["tiempo_activo"] = int(time.time()) - session.get("iniciada", 0)
            await self.redis.expire(f"session:{telefono}", 1800)
            return session
        return None

    async def create_session(self, telefono: str, datos_iniciales: dict = None) -> dict:
        session = {
            "telefono": telefono,
            "estado": "NUEVA_CONSULTA",
            "entidades_extraidas": {},
            "resultados_herramientas": {},
            "objetivos": [],
            "mensajes_en_sesion": 0,
            "iniciada": int(time.time()),
            "ultima_interaccion": int(time.time()),
        }
        if datos_iniciales:
            session.update(datos_iniciales)
        await self.redis.set(f"session:{telefono}", json.dumps(session), ex=1800)
        return session

    async def retrieve_episodic(self, telefono: str, query: str, limit: int = 5) -> list:
        embedding = await self.embeddings.generate(query)
        now = time.time()

        results = await self.qdrant.search(
            collection_name="conversaciones",
            query_vector=embedding,
            query_filter=Filter(must=[
                FieldCondition(key="telefono", match=MatchValue(telefono)),
            ]),
            limit=limit * 3,
            with_payload=True,
            score_threshold=0.60,
        )

        # Aplicar decay temporal
        for r in results:
            age_days = (now - r.payload.get("timestamp", now)) / 86400
            if age_days > 7:
                r.score *= max(0.5, 1.0 - (age_days / 30) * 0.5)

        results.sort(key=lambda r: r.score, reverse=True)
        return [
            {
                "score": r.score,
                "contenido": r.payload.get("contenido", ""),
                "rol": r.payload.get("rol", ""),
                "categoria": r.payload.get("categoria", "GENERAL"),
                "timestamp": r.payload.get("timestamp", 0),
                "entidades": r.payload.get("entidades", {}),
                "conversacion_id": r.payload.get("id_conversacion"),
            }
            for r in results[:limit]
            if r.score >= 0.75
        ]

    async def update_session(self, telefono: str, updates: dict):
        existing = await self.get_session(telefono)
        if not existing:
            existing = await self.create_session(telefono)
        existing.update(updates)
        existing["ultima_interaccion"] = int(time.time())
        if "mensajes_en_sesion" not in updates:
            existing["mensajes_en_sesion"] = existing.get("mensajes_en_sesion", 0) + 1
        await self.redis.set(f"session:{telefono}", json.dumps(existing), ex=1800)
        return existing
```

### 12.4 RAG Retriever

```python
# app/rag/pipeline.py (versión extendida)

class RAGRetriever:
    def __init__(self, qdrant, embeddings, reranker):
        self.qdrant = qdrant
        self.embeddings = embeddings
        self.reranker = reranker

    async def retrieve(self, query: str, entidades: dict = None, limit: int = 3) -> list:
        embedding = await self.embeddings.generate(query)

        # Búsqueda vectorial
        vector_results = await self.qdrant.search(
            collection_name="conocimiento",
            query_vector=embedding,
            limit=limit * 3,
            with_payload=True,
            score_threshold=0.65,
        )

        # Búsqueda por filtros
        filtered_results = []
        if entidades:
            filters = self._build_filters(entidades)
            if filters:
                filtered_results = await self.qdrant.search(
                    collection_name="conocimiento",
                    query_vector=embedding,
                    query_filter=Filter(must=filters),
                    limit=limit * 2,
                    with_payload=True,
                    score_threshold=0.70,
                )

        # RRF Fusion
        fused = self._rrf_fusion(
            [vector_results, filtered_results],
            weights=[0.6, 0.4],
        )

        # Re-ranking
        reranked = await self.reranker.rerank(query, fused[:limit * 2], top_k=limit)

        # Formatear respuesta
        return [
            {
                "score": r.score,
                "contenido": r.payload.get("contenido", ""),
                "tipo": r.payload.get("tipo", "general"),
                "nombre": r.payload.get("nombre", ""),
                "tags": r.payload.get("tags", []),
                "fuente_id": r.payload.get("id", ""),
            }
            for r in reranked
            if r.score >= 0.75
        ]

    def _build_filters(self, entidades: dict) -> list:
        filters = []
        if entidades.get("servicio"):
            filters.append(
                FieldCondition(key="tags", match=MatchValue(entidades["servicio"]))
            )
        if entidades.get("categoria"):
            filters.append(
                FieldCondition(key="categoria", match=MatchValue(entidades["categoria"]))
            )
        if entidades.get("moto"):
            filters.append(
                FieldCondition(key="marcas_compatibles", match=MatchValue(entidades["moto"]))
            )
        return filters

    def _rrf_fusion(self, result_sets, weights=None, k=60):
        scores = {}
        weights = weights or [1.0 / len(result_sets)] * len(result_sets)
        for i, results in enumerate(result_sets):
            if not results:
                continue
            for rank, r in enumerate(results):
                sid = r.id
                if sid not in scores:
                    scores[sid] = {"result": r, "score": 0.0}
                scores[sid]["score"] += weights[i] / (k + rank + 1)
        sorted_r = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
        return [r["result"] for r in sorted_r]
```

### 12.5 Objective Tracker

```python
# app/agent/objective_tracker.py

from uuid import uuid4
from typing import Optional


class ObjectiveTracker:
    def __init__(self):
        self.objectives = []

    def load(self, objectives: list):
        self.objectives = objectives or []

    def add(self, tipo: str, **params):
        obj = {
            "id": f"obj_{uuid4().hex[:8]}",
            "tipo": tipo,
            "estado": "pendiente",
            "creado": int(time.time()),
            **params,
        }
        self.objectives.append(obj)
        return obj

    def get(self, obj_id: str) -> Optional[dict]:
        for obj in self.objectives:
            if obj["id"] == obj_id:
                return obj
        return None

    def complete(self, obj_id: str, resultado: dict = None):
        obj = self.get(obj_id)
        if obj:
            obj["estado"] = "completado"
            if resultado:
                obj["resultado"] = resultado
            # Desbloquear dependientes
            for dep in self.objectives:
                if dep.get("depende_de") == obj_id and dep["estado"] == "bloqueado":
                    dep["estado"] = "pendiente"

    def fail(self, obj_id: str, error: str = None):
        obj = self.get(obj_id)
        if obj:
            obj["estado"] = "fallido"
            if error:
                obj["error"] = error

    def cancel(self, obj_id: str):
        obj = self.get(obj_id)
        if obj:
            obj["estado"] = "cancelado"

    def block(self, obj_id: str):
        obj = self.get(obj_id)
        if obj:
            obj["estado"] = "bloqueado"

    def get_active(self) -> list:
        return [o for o in self.objectives
                if o["estado"] in ("pendiente", "en_progreso")]

    def next_action(self) -> Optional[dict]:
        for obj in self.get_active():
            if obj.get("depende_de"):
                dep = self.get(obj["depende_de"])
                if dep and dep["estado"] != "completado":
                    continue
            return obj
        return self.get_active()[0] if self.get_active() else None

    def detect_from_classification(self, clasificacion: dict, session: dict):
        """Crea objetivos basados en la clasificación de intención."""
        intent = clasificacion.get("intencion_principal")
        entities = clasificacion.get("entidades", {})

        if intent == "COTIZACION":
            self.add("COTIZAR_SERVICIO",
                     servicio=entities.get("servicio_solicitado", ""),
                     moto=entities.get("moto", ""))
            if entities.get("pregunta_disponibilidad"):
                self.add("AGENDAR_CITA",
                         servicio=entities.get("servicio_solicitado", ""),
                         fecha=entities.get("fecha_mencionada", ""),
                         depende_de=self.get_active()[-1]["id"] if self.get_active() else None)

        elif intent == "AGENDAMIENTO":
            self.add("AGENDAR_CITA",
                     servicio=entities.get("servicio_solicitado", ""),
                     fecha=entities.get("fecha_mencionada", ""))

        elif intent == "QUEJA":
            self.add("RESOLVER_QUEJA",
                     descripcion=entities.get("descripcion", ""))

        elif intent == "DIAGNOSTICO":
            self.add("DIAGNOSTICAR_FALLA",
                     sintomas=entities.get("sintomas", ""),
                     moto=entities.get("moto", ""))
```

### 12.6 Conversation Summarizer

```python
# app/memory/summarizer.py

class ConversationSummarizer:
    def __init__(self, gemini):
        self.gemini = gemini

    async def summarize(self, messages: list, existing_summary: str = None) -> str:
        if not messages:
            return ""

        if existing_summary:
            return await self._incremental_summary(messages[-10:], existing_summary)
        return await self._full_summary(messages)

    async def _full_summary(self, messages: list) -> str:
        prompt = f"""Genera un resumen de esta conversación en 2-3 oraciones.
Incluye: tema principal, información intercambiada, decisiones tomadas, siguiente paso.

Mensajes:
{chr(10).join(f'{\"Usuario\" if m[\"rol\"] == \"user\" else \"Asistente\"}: {m[\"contenido\"][:300]}' for m in messages[-20:])}

Resumen:"""

        return await self.gemini.generate(prompt, temperature=0.2, max_tokens=150)

    async def _incremental_summary(self, new_messages: list, existing: str) -> str:
        prompt = f"""Resumen anterior: {existing}

Nuevos mensajes:
{chr(10).join(f'{\"Usuario\" if m[\"rol\"] == \"user\" else \"Asistente\"}: {m[\"contenido\"][:300]}' for m in new_messages)}

Genera un resumen actualizado en 2-3 oraciones que combine el resumen anterior
con los nuevos mensajes. Mantén la información importante del resumen anterior.
Resumen actualizado:"""

        return await self.gemini.generate(prompt, temperature=0.2, max_tokens=150)

    async def should_summarize(self, session: dict, conversation: dict) -> bool:
        """Determina si es momento de resumir la conversación."""
        n_mensajes = conversation.get("total_mensajes", 0)
        if n_mensajes > 0 and n_mensajes % 10 == 0:
            return True
        if session.get("estado") == "cerrada":
            return True
        ultimo = session.get("ultima_interaccion", 0)
        if time.time() - ultimo > 1800:
            return True
        return False
```

---

## RESUMEN

| Componente | Propósito | Archivo propuesto |
|-----------|-----------|-------------------|
| ContextBuilder | Recupera, filtra, comprime y ensambla el contexto | `app/orchestrator/context_builder.py` |
| PromptOrchestrator | Construye el prompt final en orden jerárquico | `app/orchestrator/prompt_orchestrator.py` |
| ContextCompressor | Comprime contexto si excede 3000 tokens | `app/orchestrator/context_builder.py` |
| ObjectiveTracker | Gestiona objetivos activos (detectar, almacenar, actualizar) | `app/agent/objective_tracker.py` |
| ConversationSummarizer | Resume conversaciones largas | `app/memory/summarizer.py` |
| RAGRetriever | Recuperación + re-ranking de conocimiento | `app/rag/pipeline.py` |
| MemoryService | Recuperación de sesión + memoria episódica | `app/memory/service.py` |
| ReflectionValidator | Reflection loop anti-alucinación | `app/agent/reflector.py` |

### Flujo completo integrado

```
MessageProcessor.process()
  ├── RateLimiter.check()
  ├── SessionManager.get_session()
  ├── ContextBuilder.build()
  │     ├── MemoryService.retrieve_episodic()
  │     ├── RAGRetriever.retrieve()
  │     ├── ProfileService.get_profile()
  │     ├── _get_recent_history()
  │     ├── ObjectiveTracker.load()
  │     ├── _filter_context()
  │     ├── _compress_context()
  │     └── ContextCompressor.compress()
  ├── IntentClassifier.classify()
  ├── ObjectiveTracker.detect_from_classification()
  ├── PlanningAgent.plan()
  ├── ToolExecutor.execute()
  ├── ObjectiveTracker.complete() / fail()
  ├── ContextBuilder.build()  ← segunda llamada con resultados de tools
  ├── PromptOrchestrator.build(ctx)
  ├── Generator.generate(prompt_final)
  ├── ReflectionValidator.validate()
  └── (si rechazado) Generator.generate(prompt_final + feedback)
```
