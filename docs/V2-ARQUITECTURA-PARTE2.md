# V2 — ARQUITECTURA DEL SISTEMA (Parte 2/4)

---

## PARTE 2 — FLUJO COMPLETO DE UN MENSAJE

### Ejemplo: "Hola, ¿cuánto cuesta el cambio de aceite para mi Italika FT150 y puedo ir mañana?"

### Paso 1: Recepción
```
Evolution API → POST → n8n
```
Payload Evolution API:
```json
{
  "data": {
    "key": { "remoteJid": "521234567890@s.whatsapp.net" },
    "pushName": "Daniel",
    "message": { "conversation": "Hola, ¿cuánto cuesta el cambio de aceite para mi Italika FT150 y puedo ir mañana?" }
  }
}
```

**n8n**: Extrae `telefono`, `mensaje`, `nombre`. Sanitiza (escapar SQL, validar UTF-8, < 4096 chars).
**n8n → FastAPI**:
```json
POST http://fastapi:8000/api/v1/messages
{
  "telefono": "521234567890",
  "mensaje": "Hola, ¿cuánto cuesta el cambio de aceite para mi Italika FT150 y puedo ir mañana?",
  "nombre": "Daniel",
  "remoteJid": "521234567890@s.whatsapp.net",
  "timestamp": 1717171200
}
```

### Paso 2: Validaciones (FastAPI Validation Layer)
- Teléfono: regex `^\d{10,15}$` ✓
- Mensaje: 1-4096 chars ✓
- Rate limit: Redis INCR `ratelimit:521234567890` < 10/min ✓
- Spam: mensaje duplicado en últimos 5s? No ✓
- Blacklist: teléfono en lista negra? No ✓

### Paso 3: Recuperar Working Memory
```
FastAPI → Redis GET session:521234567890
```
No existe → cliente nuevo. Crear sesión con estado `NUEVA_CONSULTA`.

### Paso 4: Recuperar Memoria Episódica
```
FastAPI → Qdrant search(collection=conversaciones, filter=telefono, limit=5, threshold=0.70)
```
No hay conversaciones previas → resultado vacío.

### Paso 5: Recuperar Conocimiento RAG
```
FastAPI → Qdrant search(collection=conocimiento, query=embedding, limit=5×3, threshold=0.65)
         → RRF fusion → Re-ranking with LLM → threshold 0.75
```
Resultado: 2 fragmentos relevantes (cambio de aceite, servicio general).

### Paso 6: Clasificar Intención
```
FastAPI → Gemini function calling (temperature=0.1)
```
```json
{
  "intencion_principal": "COTIZACION",
  "intenciones_secundarias": ["AGENDAMIENTO"],
  "confianza": 0.95,
  "entidades": {
    "servicio_solicitado": "cambio de aceite",
    "moto": "Italika FT150",
    "pregunta_disponibilidad": true,
    "fecha_mencionada": "mañana"
  }
}
```

### Paso 7: Planificar
```
FastAPI → Gemini Planner (temperature=0.2)
```
```json
{
  "objetivo": "Cotizar cambio de aceite para Italika FT150 y consultar disponibilidad para mañana",
  "pasos": [
    {"orden": 1, "accion": "consultar_precio", "parametros": {"servicio": "cambio de aceite", "moto": "Italika FT150"}, "critico": true},
    {"orden": 2, "accion": "registrar_cliente", "parametros": {"telefono": "521234567890", "nombre": "Daniel"}, "critico": true},
    {"orden": 3, "accion": "consultar_disponibilidad", "parametros": {"fecha": "mañana", "servicio": "cambio de aceite"}, "critico": false}
  ]
}
```

### Paso 8: Ejecutar Tools
```
FastAPI → Tool Executor
```
1. `consultar_precio(servicio="cambio de aceite", moto="Italika FT150")` → OK (precio: $350-$550)
2. `registrar_cliente(telefono="521234567890", nombre="Daniel")` → OK (cliente_id: 2)
3. `consultar_disponibilidad(fecha="mañana", servicio="cambio de aceite")` → OK (6 horarios)

### Paso 9: Construir Contexto Final
Fusión de: mensaje original + clasificación + RAG + resultados tools + personalidad.

### Paso 10: Generar Respuesta
```
FastAPI → Gemini (temperature=0.8)
```
Respuesta generada explicando precio + opciones de horario. Pregunta si desea agendar.

### Paso 11: Reflection Loop
Evaluación de respuesta. Score > 7 → APROBADA.

### Paso 12: Persistir
- INSERT en `mensajes` (user + assistant)
- Crear/actualizar `conversaciones`
- Actualizar `perfiles_usuario`

### Paso 13: Actualizar Working Memory
```
Redis SET session:521234567890 (TTL 30 min)
```
Estado: `ESPERANDO_CONFIRMACION_CITA`

### Paso 14: Encolar Embeddings (async)
```
RabbitMQ → embeddings queue → Celery worker → Qdrant upsert
```

### Paso 15: Responder
```
FastAPI → n8n → Evolution API → WhatsApp
```

---

## PARTE 5 — DISEÑO DE TOOLS

### Contratos de herramientas

#### consultar_precio
```
Params: {servicio: str, moto?: str}
Returns: {success, data: {servicio, precio_min, precio_max, incluye, tiempo_estimado}}
Errors: servicio_no_encontrado, moto_no_compatible
```

#### consultar_disponibilidad
```
Params: {fecha: str (YYYY-MM-DD|"mañana"), servicio?: str}
Returns: {success, data: {fecha, horarios_disponibles: string[], slots_disponibles: int}}
Errors: domingo_cerrado, sabado_medio_dia, fecha_pasada
```

#### registrar_cliente
```
Params: {telefono: str (^\d{10,15}$), nombre: str, moto?: str}
Returns: {success, data: {cliente_id, creado: bool, actualizado: bool}}
Errors: telefono_invalido
```

#### agendar_cita
```
Params: {cliente_id: int, servicio: str, fecha: str, hora: str, moto?: str}
Returns: {success, data: {cita_id, servicio, fecha, hora, estado, recordatorio_programado}}
Errors: horario_no_disponible, cliente_no_encontrado, fecha_invalida
```

#### obtener_historial_cliente
```
Params: {telefono: str, limite?: int}
Returns: {success, data: {cliente, citas_recientes[], ultimos_mensajes[]}}
Errors: cliente_no_encontrado
```

#### registrar_queja
```
Params: {cliente_id: int, descripcion: str, urgencia: str, cita_relacionada_id?: int}
Returns: {success, data: {queja_id, estado, urgencia, notificado}}
Errors: cliente_no_encontrado
```

#### notificar_personal
```
Params: {tipo: str, mensaje: str, prioridad?: str}
Returns: {success, data: {notificado: true, canal: "queue"}}
```

#### enviar_recordatorio
```
Params: {cliente_id: int, telefono: str, mensaje: str, fecha_envio: str (ISO8601), tipo?: str}
Returns: {success, data: {programado: true, fecha_envio}}
Errors: fecha_en_pasado
```

#### clasificar_diagnostico
```
Params: {descripcion_falla: str, moto?: str}
Returns: {success, data: {sistema_afectado, posibles_causas[], preguntas[], urgencia, recomendacion}}
```

---

## PARTE 6 — DISEÑO DEL AGENTE

### Ciclo Cognitivo (ReAct)

```
1. OBSERVAR  → mensaje + working memory + memoria episódica + RAG
       │
2. RAZONAR   → clasificar intención + extraer entidades
       │
3. PLANIFICAR → determinar secuencia de tools
       │
4. ACTUAR    → ejecutar herramientas (0..N pasos)
       │
5. OBSERVAR  → resultados de herramientas
       │
6. EVALUAR   → objetivo cumplido?
       │
   ┌───SÍ────┐
   │         │
7. GENERAR   → 8. REPLANIFICAR
   respuesta     │
                 └──→ volver a 3
```

### Manejo de Ambigüedad

Si confianza < 0.6: responder con "¿Podrías darme más detalles?"
Si múltiples intenciones: plan prioriza principal, pregunta por secundarias después.
Máximo 5 ciclos agente por mensaje (evitar loops infinitos).

### Manejo de Errores

- Tool timeout (10s): si crítica → abortar, si no → continuar
- Tool no encontrada → omitir paso, ajustar plan
- Error BD → notificar admin, responder fallback
- Gemini error → responder con disculpa + ofrecer asesor humano
