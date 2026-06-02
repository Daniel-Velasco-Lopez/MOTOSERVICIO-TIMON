# V2 — ARQUITECTURA DEL SISTEMA (Parte 1/4)

## Diseño Técnico Ejecutable

---

## PARTE 1 — ARQUITECTURA GENERAL DEFINITIVA

### Diagrama de Arquitectura

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                              CLIENTES                                                │
│                                                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                                           │
│  │ WhatsApp │  │   Web    │  │ Facebook │                                           │
│  └─────┬────┘  └────┬─────┘  └────┬─────┘                                           │
│        │            │             │                                                  │
└────────┼────────────┼─────────────┼──────────────────────────────────────────────────┘
         │            │             │
    ┌────▼────────────▼─────────────▼────┐
    │         EVOLUTION API             │
    │  Gateway WhatsApp, recibe y envía │
    └──────────────────┬────────────────┘
                       │ POST /webhook/whatsapp-webhook
                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    n8n (GATEWAY LIGERO)                                  │
│                                                                          │
│  Rol ÚNICO: Recibir webhook → validar → reenviar a FastAPI              │
│              Recibir respuesta de FastAPI → reenviar a Evolution API    │
│                                                                          │
│  ┌──────────────┐   ┌──────────────┐   ┌─────────────────────────┐      │
│  │ Webhook In   │──▶│ Sanitizar    │──▶│ POST /api/v1/messages   │      │
│  │ (Evolution)  │   │ (escapar,    │   │ → FastAPI:8000           │      │
│  │              │   │  validar)    │   │                         │      │
│  └──────────────┘   └──────────────┘   └──────────┬──────────────┘      │
│                                                    │                     │
│  ┌──────────────────────────────────────────────┐ │                     │
│  │ Enviar Respuesta WhatsApp                     │ │                     │
│  │ (POST a Evolution API con {number, text})     │ │                     │
│  └──────────────────────────────────────────────┘ │                     │
└───────────────────────────────────────────────────┼─────────────────────┘
                                                    │ HTTP (red interna)
                                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│              MICROSERVICIO FASTAPI (Python 3.12)                        │
│                                                                          │
│  Workers: 4 uvicorn  │  Puerto: 8000 (solo interno)                     │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │                    ORCHESTRATOR                                │     │
│  │  1. Validar + Rate Limit                                      │     │
│  │  2. Recuperar Working Memory (Redis)                         │     │
│  │  3. Recuperar Memoria Episódica (Qdrant)                     │     │
│  │  4. Recuperar Conocimiento RAG (Qdrant)                      │     │
│  │  5. Clasificar Intención (Gemini function calling)           │     │
│  │  6. Manejar Ambigüedad si confianza baja                     │     │
│  │  7. Generar Plan de Acción (Gemini Planner)                  │     │
│  │  8. Ejecutar Tools secuencialmente (Tool Executor)           │     │
│  │  9. Replanificar si es necesario                              │     │
│  │ 10. Construir Contexto Final                                  │     │
│  │ 11. Generar Respuesta (Gemini, temp 0.8)                     │     │
│  │ 12. Reflection Loop (autoevaluación)                         │     │
│  │ 13. Persistir en MySQL                                       │     │
│  │ 14. Actualizar Working Memory (Redis)                        │     │
│  │ 15. Encolar Embeddings (RabbitMQ → Qdrant)                   │     │
│  │ 16. Devolver respuesta a n8n                                  │     │
│  └────────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────────┐
          │                         │                             │
          ▼                         ▼                             ▼
┌──────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│     MySQL 8       │   │   Qdrant (vectores)  │   │    Redis 7            │
│  Tablas:          │   │  Colecciones:        │   │  Working Memory      │
│  clientes         │   │  conversaciones      │   │  Rate Limit          │
│  conversaciones   │   │  conocimiento        │   │  Cache               │
│  mensajes         │   │  perfiles            │   │  TTL: 30 min         │
│  citas            │   │                      │   │                      │
│  servicios        │   │  Dimensión: 768      │   │  ┌──────────────┐   │
│  quejas           │   │  (text-embedding-004) │   │  │ RabbitMQ    │   │
│  perfiles_usuario │   │  Distancia: Cosine   │   │  │ Colas:      │   │
│  recordatorios    │   │                      │   │  │ embeddings  │   │
│  logs             │   │                      │   │  │ reminders   │   │
│  metricas         │   │                      │   │  │ notif.      │   │
└──────────────────┘   └──────────────────────┘   │  │ logs        │   │
                                                  │  └──────────────┘   │
                                                  └──────────────────────┘
```

### Responsabilidades

| Componente | Hace | No hace | Comunicación |
|-----------|------|---------|-------------|
| Evolution API | Gateway WhatsApp | Lógica de negocio | Webhooks |
| n8n | Router + forward | Clasificar, generar, memorizar | HTTP a FastAPI |
| FastAPI | Cerebro cognitivo | Conexión directa con WhatsApp | HTTP + Redis + Qdrant + MySQL |
| MySQL | Datos relacionales | Búsqueda semántica | SQL |
| Qdrant | Vectores + búsqueda semántica | Datos relacionales | HTTP/gRPC |
| Redis | Sesiones + rate limit + caché | Persistencia larga | TCP |
| RabbitMQ | Colas async | Procesamiento síncrono | AMQP |

---

## PARTE 3 — DISEÑO DE MEMORIA

### 3.1 Working Memory (Redis)

```json
Key: session:{telefono}
TTL: 1800 segundos (30 min)
Estructura:
{
  "conversacion_id": 5,
  "cliente_id": 2,
  "telefono": "521234567890",
  "estado": "ESPERANDO_CONFIRMACION_CITA",
  "ultimo_tema": "COTIZACION",
  "intencion_actual": "COTIZACION",
  "intenciones_pendientes": ["AGENDAMIENTO"],
  "entidades_extraidas": {
    "servicio": "cambio de aceite",
    "moto": "Italika FT150"
  },
  "resultados_herramientas": {
    "consultar_precio": { "precio_min": 350, "precio_max": 550 }
  },
  "plan": {
    "pasos": [{"paso": 1, "accion": "consultar_precio", "completado": true}],
    "paso_actual": 3,
    "completado": true
  },
  "mensajes_en_sesion": 2,
  "iniciada": 1717171200,
  "ultima_interaccion": 1717171210
}
```

### 3.2 Memoria Episódica (Qdrant)

```
Collection: conversaciones
Vector size: 768 (text-embedding-004)
Distance: Cosine

Payload por mensaje:
{
  "id_mensaje": 1234,
  "id_conversacion": 5,
  "id_cliente": 2,
  "telefono": "521234567890",
  "rol": "user" | "assistant",
  "contenido": "texto completo",
  "categoria": "COTIZACION",
  "timestamp": "2026-05-29T10:00:00Z",
  "entidades": { "servicios": ["cambio de aceite"], "motos": ["Italika FT150"] },
  "sentimiento": "neutral",
  "resuelto": true
}
```

Recuperación: query vector + filtro por telefono. Threshold 0.70. Límite 5.
Batch upsert async via RabbitMQ (no bloquear flujo síncrono).

### 3.3 Memoria Semántica (Qdrant)

```
Collection: conocimiento
Vector size: 768
Distance: Cosine

Payload:
{
  "id": "serv_001",
  "tipo": "servicio" | "procedimiento" | "politica" | "faq",
  "nombre": "Cambio de aceite + filtro",
  "categoria": "mantenimiento",
  "tags": ["aceite", "filtro", "4T"],
  "contenido": "texto completo del chunk",
  "precio_min": 350,
  "precio_max": 550,
  "tiempo_estimado": "30 min",
  "marcas_compatibles": ["Italika", "Honda", "Yamaha"],
  "activo": true
}
```

Hybrid Search: vectorial (sobre-muestreo 3x) + filtros de payload + RRF fusion + re-ranking con LLM + threshold 0.75.

### 3.4 Memoria Procedimental

Tabla `procedimientos` en MySQL con pasos JSON configurables. Actualización manual vía API/administración.

---

## PARTE 7 — DISEÑO DE BASE DE DATOS

### Tablas principales

```sql
-- Clientes
CREATE TABLE clientes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    telefono VARCHAR(20) NOT NULL UNIQUE,
    email VARCHAR(255),
    direccion TEXT,
    motos_registradas JSON,
    fuente VARCHAR(50) DEFAULT 'whatsapp',
    notas TEXT,
    ultima_interaccion TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    activo BOOLEAN DEFAULT TRUE,
    INDEX idx_telefono (telefono),
    INDEX idx_activo (activo)
);

-- Conversaciones
CREATE TABLE conversaciones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cliente_id INT NOT NULL,
    canal VARCHAR(50) DEFAULT 'whatsapp',
    estado VARCHAR(50) DEFAULT 'activa',
    resumen TEXT,
    intencion_principal VARCHAR(50),
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    cerrada_en TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE RESTRICT,
    INDEX idx_cliente (cliente_id),
    INDEX idx_estado (estado),
    INDEX idx_cliente_estado (cliente_id, estado)
);

-- Mensajes
CREATE TABLE mensajes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversacion_id INT NOT NULL,
    cliente_id INT NOT NULL,
    rol ENUM('user', 'assistant', 'system') NOT NULL,
    contenido TEXT NOT NULL,
    contenido_resumido VARCHAR(500),
    categoria VARCHAR(50),
    metadata JSON,
    token_count INT,
    tiempo_procesamiento_ms INT,
    created_at TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
    FOREIGN KEY (conversacion_id) REFERENCES conversaciones(id) ON DELETE CASCADE,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE RESTRICT,
    INDEX idx_conversacion (conversacion_id),
    INDEX idx_cliente (cliente_id),
    INDEX idx_categoria (categoria),
    INDEX idx_created (created_at),
    FULLTEXT INDEX idx_contenido (contenido)
);

-- Citas
CREATE TABLE citas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cliente_id INT NOT NULL,
    servicio VARCHAR(150) NOT NULL,
    moto VARCHAR(150),
    fecha DATE NOT NULL,
    hora TIME NOT NULL,
    duracion_estimada INT DEFAULT 30,
    estado ENUM('pendiente','confirmada','en_proceso','completada','cancelada','no_asistio') DEFAULT 'pendiente',
    notas TEXT,
    recordatorio_enviado BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE RESTRICT,
    INDEX idx_cliente (cliente_id),
    INDEX idx_fecha (fecha),
    INDEX idx_estado (estado),
    UNIQUE INDEX idx_fecha_hora (fecha, hora)
);

-- Servicios (catálogo)
CREATE TABLE servicios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    descripcion TEXT,
    categoria VARCHAR(50),
    precio_min DECIMAL(10,2),
    precio_max DECIMAL(10,2),
    incluye TEXT,
    tiempo_estimado INT,
    marcas_compatibles JSON,
    cilindrajes_soportados JSON,
    tags JSON,
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_categoria (categoria),
    FULLTEXT INDEX idx_nombre (nombre)
);

-- Quejas
CREATE TABLE quejas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cliente_id INT NOT NULL,
    cita_id INT,
    descripcion TEXT NOT NULL,
    urgencia ENUM('baja','media','alta') DEFAULT 'media',
    estado ENUM('pendiente','en_proceso','resuelta','cerrada') DEFAULT 'pendiente',
    solucion TEXT,
    notificado_cliente BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE RESTRICT,
    FOREIGN KEY (cita_id) REFERENCES citas(id) ON DELETE SET NULL,
    INDEX idx_estado (estado),
    INDEX idx_urgencia (urgencia)
);

-- Perfiles de usuario
CREATE TABLE perfiles_usuario (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cliente_id INT NOT NULL UNIQUE,
    frecuencia_visitas VARCHAR(50) DEFAULT 'desconocida',
    servicios_frecuentes JSON,
    preferencia_horario VARCHAR(20),
    segmento VARCHAR(50) DEFAULT 'general',
    gasto_promedio DECIMAL(10,2),
    total_gastado DECIMAL(10,2) DEFAULT 0,
    satisfaccion_promedio DECIMAL(2,1),
    embedding_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
);

-- Recordatorios
CREATE TABLE recordatorios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cliente_id INT NOT NULL,
    cita_id INT,
    telefono VARCHAR(20) NOT NULL,
    mensaje TEXT NOT NULL,
    tipo ENUM('cita','seguimiento','promocion','recordatorio_general') DEFAULT 'cita',
    fecha_programada TIMESTAMP NOT NULL,
    fecha_enviado TIMESTAMP,
    estado ENUM('pendiente','enviado','fallido','cancelado') DEFAULT 'pendiente',
    FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE CASCADE,
    FOREIGN KEY (cita_id) REFERENCES citas(id) ON DELETE SET NULL,
    INDEX idx_pendientes (estado, fecha_programada) WHERE estado = 'pendiente'
);

-- Logs estructurados
CREATE TABLE logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    nivel ENUM('DEBUG','INFO','WARNING','ERROR','CRITICAL') NOT NULL DEFAULT 'INFO',
    componente VARCHAR(100) NOT NULL,
    mensaje TEXT NOT NULL,
    metadata JSON,
    trace_id VARCHAR(100),
    cliente_id INT,
    telefono VARCHAR(20),
    tiempo_ms INT,
    created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_nivel (nivel),
    INDEX idx_trace (trace_id),
    INDEX idx_created (created_at),
    INDEX idx_nivel_created (nivel, created_at)
);

-- Métricas de rendimiento
CREATE TABLE metricas (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tipo VARCHAR(50) NOT NULL,
    valor DECIMAL(15,4) NOT NULL,
    tags JSON,
    periodo VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_tipo (tipo),
    INDEX idx_tipo_created (tipo, created_at)
);
```

---

## PARTE 10 — STACK TECNOLÓGICO

| Componente | Tecnología | Versión | Razón |
|-----------|-----------|---------|-------|
| Backend | **FastAPI** | 0.111+ | Async nativo, OpenAPI, Pydantic v2 |
| Runtime | **Python** | 3.12+ | Async maduro, ecosistema ML/LLM |
| API Gateway | **n8n** | 2.3.7+ | Ya existe, solo reducir rol |
| WhatsApp | **Evolution API** | 2.3.7+ | Ya existe |
| DB primaria | **MySQL 8** | 8.4+ | Ya existe, ACID |
| Cache/Sesión | **Redis 7** | 7.2+ | En memoria, TTL, rate limit |
| Vector DB | **Qdrant** | 1.9+ | Cosine, filtros, payload, Docker |
| Queue | **RabbitMQ** | 3.13+ | Delayed queues, persistente |
| LLM | **Gemini 2.5 Flash** | API | Ya se usa, function calling nativo |
| Embeddings | **text-embedding-004** | API | 768 dims, optimizado recuperación |
| Observabilidad | **OpenTelemetry** | latest | Vendor-neutral, trazas |
| Dashboard | **Grafana** | 10+ | Dashboards + alertas |
| Time Series | **Prometheus** | 2.53+ | Métricas, integración OTel |
| ASGI | **Uvicorn** | 0.29+ | Workers, rendimiento |
| Async tasks | **Celery** | 5.4+ | Embeddings batch, recordatorios |
| Testing | **pytest** | 8+ | Async tests, fixtures |
| Logging | **structlog** | 24+ | Logs estructurados JSON |
| HTTP Client | **httpx** | 0.27+ | Async, HTTP/2, timeouts |
