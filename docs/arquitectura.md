# Arquitectura del Sistema

## Componentes

### WhatsApp
Canal principal de comunicación con los clientes.

### Evolution API
Intermediario entre WhatsApp y n8n. Recibe mensajes de WhatsApp y los reenvía como webhook a n8n. También recibe peticiones de n8n para enviar respuestas a los clientes.

### n8n
Motor de automatización y orquestador central. Alberga 6 workflows:

| Workflow | Archivo | Rol |
|---|---|---|
| **Recepción y Clasificación** | `principal-recepcion.json` | Webhook de entrada, clasificación con Gemini, enrutamiento |
| **Agendamiento de Citas** | `sub-agendamiento.json` | Gestión de citas (agendar, reprogramar, cancelar) |
| **Cotización** | `sub-cotizacion.json` | Precios de servicios y refacciones |
| **Diagnóstico de Fallas** | `sub-diagnostico.json` | Preguntas de diagnóstico asistido por IA |
| **Información General** | `sub-informacion.json` | Horarios, dirección, formas de pago |
| **Quejas y Soporte** | `sub-queja.json` | Registro de quejas con escalamiento |

### Gemini API (Google AI)
Clasificación de mensajes en 5 categorías y generación de respuestas inteligentes para diagnóstico de fallas.

### MySQL
Almacenamiento persistente de:
- Clientes (nombre, teléfono)
- Citas (fecha, hora, servicio, estado)
- Conversaciones (mensaje original, respuesta generada, fecha)

## Flujo de datos

```
WhatsApp (Cliente)
    ↓
Evolution API (webhook POST)
    ↓
n8n ── Workflow Principal ──────────────────┐
    ↓                                        │
Gemini API (clasifica mensaje)               │
    ↓                                        │
n8n Switch (AGENDAMIENTO | COTIZACION |      │
            DIAGNOSTICO | INFORMACION |       │
            QUEJA)                            │
    ↓                                        │
Sub-workflow específico (procesa y           │
  genera respuesta)                           │
    ↓                                        │
MySQL (guarda conversación)                  │
    ↓                                        │
Evolution API (envía respuesta)              │
    ↓                                        │
WhatsApp (Cliente recibe respuesta) ─────────┘
```

## Estructura de Workflows

### Workflow Principal (`principal-recepcion.json`)

```
[Webhook Evolution] → [Extraer Mensaje] → [Clasificar con Gemini] → [Switch Categoría]
                                                                         │
                    ┌──────────────────┬──────────────────┬──────────────┼──────────────┐
                    ▼                  ▼                  ▼              ▼              ▼
           [Agendamiento]     [Cotización]      [Diagnóstico]   [Información]    [Queja]
                    │                  │                  │              │              │
                    └──────────────────┴──────────────────┴──────────────┴──────────────┘
                                                                         │
                                                              [Registrar Conversación]
                                                                         │
                                                              [Enviar Respuesta WhatsApp]
                                                                         │
                                                                   [Responder Webhook]
```

**Nodos:**
1. **Webhook Evolution** — Recibe POST de Evolution API en `/webhook/whatsapp-webhook`
2. **Extraer Mensaje** — Código JS que extrae `telefono`, `mensaje` y `nombre` del payload
3. **Clasificar con Gemini** — HTTP Request a Gemini API para clasificar el mensaje
4. **Switch Categoría** — Enruta según la categoría devuelta por Gemini
5. **Agendamiento / Cotización / Diagnóstico / Información / Queja** — Ejecutan el sub-workflow correspondiente
6. **Registrar Conversación** — Inserta en MySQL tabla `conversaciones`
7. **Enviar Respuesta WhatsApp** — POST a Evolution API para enviar el mensaje
8. **Responder Webhook** — Confirma recepción al webhook

### Sub-workflow: Agendamiento (`sub-agendamiento.json`)

```
[Inicio] → [Buscar Cliente] → [Cliente Existe?]
                                   ├── Sí → [Consultar Citas Próximas] → [Generar Respuesta]
                                   └── No → [Registrar Cliente] → [Obtener ID] → [Generar Respuesta]
```

Detecta si el cliente quiere **agendar**, **reprogramar** o **cancelar** una cita. Consulta citas existentes y genera respuesta personalizada.

### Sub-workflow: Cotización (`sub-cotizacion.json`)

```
[Inicio] → [Generar Respuesta Cotización]
```

Busca palabras clave en el mensaje del cliente (aceite, frenos, llanta, etc.) y responde con precios de referencia. Si no detecta un servicio específico, muestra la lista completa de precios.

### Sub-workflow: Diagnóstico (`sub-diagnostico.json`)

```
[Inicio] → [Clasificar Tipo de Falla (Gemini)] → [Procesar Respuesta Diagnóstico]
```

Envía el mensaje del cliente a Gemini con un prompt especializado en diagnóstico de motocicletas. Gemini clasifica el sistema afectado (MOTOR, FRENOS, etc.) y genera preguntas para acotar la falla.

### Sub-workflow: Información (`sub-informacion.json`)

```
[Inicio] → [Generar Respuesta Información]
```

Detecta palabras clave en el mensaje para determinar si el cliente pregunta por:
- **Horarios** → Muestra horario de atención
- **Ubicación** → Muestra dirección y referencias
- **Formas de pago** → Lista métodos aceptados
- **Tiempos de servicio** → Muestra duración estimada por servicio
- **Servicios** → Lista completa de servicios ofrecidos
- **General** → Muestra toda la información del taller

### Sub-workflow: Queja (`sub-queja.json`)

```
[Inicio] → [Buscar Cliente] → [Obtener Últimas Citas] → [Generar Respuesta Queja]
```

Registra la queja, consulta el historial de citas del cliente para contexto, genera una respuesta de disculpa y escalamiento, e indica que un asesor contactará en 24 horas.

## Endpoints de Evolution API

| Acción | Método | Endpoint |
|---|---|---|
| Recibir mensaje (webhook) | POST | `http://localhost:5678/webhook/whatsapp-webhook` |
| Enviar mensaje | POST | `http://evolution:8080/message/sendText/motoservicio` |

## Variables de Entorno Requeridas

| Variable | Descripción |
|---|---|
| `MYSQL_ROOT_PASSWORD` | Contraseña root de MySQL |
| `AUTHENTICATION_API_KEY` | API Key de Evolution API |
| `GEMINI_API_KEY` | API Key de Google Gemini (configurar en n8n como environment variable) |
