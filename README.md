# Agente Inteligente - Moto Servicios TIMÓN

## Descripción
Sistema automatizado de atención al cliente desarrollado con Docker y n8n.

## Objetivo
Automatizar:
- Atención al cliente
- Gestión de citas
- Seguimiento de servicios
- Respuestas automáticas por WhatsApp

## Tecnologías
- Docker
- n8n
- MySQL
- Evolution API
- Gemini API

## Arquitectura

WhatsApp
↓
Evolution API
↓
n8n
↓
IA
↓
MySQL

## Estado actual
- Planeación de arquitectura
- Diseño de workflows
- Diseño de base de datos

---

## Bitácora de cambios
 
### 2026-05-12 13 - 14 hrs
- **Configuración del asistente**: Se indicó que todas las respuestas deben ser en español de manera permanente.
- **Estructura del proyecto**: Se crearon las carpetas `database/`, `workflows/`, `prompts/`, `docs/`, `screenshots/` y los archivos `docker-compose.yml`, `.env`, `README.md`, `database/tablas.sql`.
- **Base de datos** (`database/tablas.sql`):
  - Versión inicial: tablas `clientes`, `citas` y `conversaciones` con campos básicos pero sin restricciones de integridad.
  - Se identificó que al usar WhatsApp como canal de comunicación, el número telefónico es el identificador principal del cliente. Se agregó `UNIQUE NOT NULL` en `clientes.telefono` para evitar duplicados y garantizar que cada conversación se asocie al cliente correcto.
  - Se agregaron Foreign Keys (`FOREIGN KEY`) con `ON DELETE RESTRICT` en `citas.cliente_id` y `conversaciones.cliente_id` hacia `clientes(id)` para:
    - Evitar datos huérfanos (ej: una cita sin cliente).
    - Impedir el borrado accidental de un cliente que tenga citas o conversaciones registradas.
    - Mantener la integridad referencial a nivel de base de datos, sin depender únicamente de la lógica de la aplicación.
  - Se agregó `NOT NULL` en los campos `cliente_id` de ambas tablas, ya que una cita o conversación no tiene sentido sin un cliente asociado.
  - El diseño considera que un cliente puede tener múltiples citas (relación 1 a N), por lo que el `UNIQUE` en teléfono no interfiere con la reasignación de fechas.
- **Documentación**:
  - Se creó `docs/arquitectura.md` describiendo los componentes del sistema: **WhatsApp** (canal de comunicación), **Evolution API** (intermediario), **n8n** (motor de automatización), **Gemini API** (clasificación e interpretación de mensajes) y **MySQL** (almacenamiento).
  - Se documentó el flujo de datos: WhatsApp → Evolution API → n8n → Gemini API → MySQL.
- **Prompts** (`prompts/clasificador.txt`):
  - Se creó el primer prompt del sistema: un **clasificador de mensajes** para Gemini API.
  - **Objetivo**: Recibe un mensaje de WhatsApp del cliente y lo clasifica en una única categoría para determinar la intención del cliente y enrutar la conversación al flujo correcto dentro de n8n.
  - **Categorías definidas**:
    - `AGENDAMIENTO`: El cliente quiere agendar, reprogramar o cancelar una cita. Ej: "Quiero agendar mi servicio", "¿Puedo pasar mañana?", "Cambiar mi cita del jueves".
    - `COTIZACION`: El cliente solicita precios de servicios, refacciones o mano de obra. Ej: "¿Cuánto cuesta el cambio de aceite?", "Precio de una llanta trasera".
    - `DIAGNOSTICO`: El cliente describe una falla o ruido extraño y quiere saber qué puede ser. Ej: "Mi moto hace un ruido al frenar", "No enciende por las mañanas".
    - `INFORMACION`: El cliente pregunta sobre horarios, dirección, tiempos de entrega, formas de pago o cualquier información general. Ej: "¿A qué hora abren?", "¿Aceptan tarjeta?".
    - `QUEJA`: El cliente reporta un problema con un servicio previo, un mal servicio o una inconformidad. Ej: "Arreglaron mal mi freno", "Me dejaron esperando mucho tiempo".
  - **Formato**: El prompt usa el placeholder `{{mensaje}}` que n8n reemplaza dinámicamente con el texto real enviado por el cliente desde WhatsApp. Gemini devuelve únicamente la etiqueta de la categoría (una sola palabra en mayúsculas) para que n8n pueda procesarla sin ruido.
  - **Integración con n8n**: Una vez clasificado el mensaje, n8n utilizará la categoría para:
    - `AGENDAMIENTO` → Consultar disponibilidad en MySQL y agendar/reprogramar citas.
    - `COTIZACION` → Buscar precios en el catálogo y responder con la cotización.
    - `DIAGNOSTICO` → Enviar a un flujo de preguntas adicionales para acotar la falla y sugerir una revisión.
    - `INFORMACION` → Responder con datos generales del taller (horarios, dirección, etc.).
    - `QUEJA` → Escalar a un administrador o generar un ticket de atención.
  - **Consideraciones**: Se eligió una clasificación única (no múltiple) para evitar ambigüedades en el enrutamiento. Si un mensaje pudiera pertenecer a dos categorías (ej: "¿Cuánto cuesta una revisión y puedo ir mañana?"), se definió que el prompt debe priorizar la primera intención detectada.
- **Docker Compose** (`docker-compose.yml` y `.env`):
  - Se implementaron dos servicios: `n8n` (motor de automatización) y `mysql` (base de datos).
  - **Riesgos detectados y corregidos**:
    1. **Falta de persistencia**: Se agregaron volúmenes nombrados (`n8n_data` y `mysql_data`) para que los workflows, credenciales y datos de la BD sobrevivan al reinicio de contenedores.
    2. **Contraseña hardcodeada**: Se movió `MYSQL_ROOT_PASSWORD` al archivo `.env` como variable de entorno (`${MYSQL_ROOT_PASSWORD}`), evitando exponer credenciales en el código.
    3. **Base de datos inicial ausente**: Se agregó `MYSQL_DATABASE: motoservicio` para que MySQL cree automáticamente la BD del proyecto al iniciar. Además, n8n usará su propia BD llamada `n8n` para no mezclar datos.
    4. **Sin restart policy**: Se agregó `restart: unless-stopped` en ambos servicios para que se reinicien automáticamente si fallan o al reiniciar el servidor.
    5. **n8n usando SQLite en lugar de MySQL**: Se configuraron las variables `DB_TYPE=mysql`, `DB_MYSQLDB_HOST=mysql`, `DB_MYSQLDB_PORT=3306`, `DB_MYSQLDB_DATABASE=n8n`, `DB_MYSQLDB_USER=root` y `DB_MYSQLDB_PASSWORD` para que n8n persista sus datos en MySQL en lugar de SQLite, centralizando el almacenamiento.
  - **Puertos expuestos**:
    - n8n: `5678` (interfaz web y API).
    - MySQL: `3307` (mapeado al puerto interno 3306 del contenedor, para conectarse con MySQL Workbench y ejecutar `tablas.sql`).
  - **Dependencia**: n8n tiene `depends_on` a mysql para arrancar después de que MySQL esté disponible.
  - **Red interna**: Ambos servicios se comunican por la red interna de Docker Compose usando los nombres de servicio (`mysql` como hostname), sin necesidad de exponer MySQL al exterior salvo el puerto 3306 para administración externa.
  - **Estado de las credenciales**:

    | Servicio | Usuario | Contraseña | Dónde está |
    |---|---|---|---|
    | MySQL | `root` | `root` | `.env` |
    | n8n | *Sin configurar* | *Sin configurar* | Se definirá al primer acceso en `http://localhost:5678` |
    | Sistema web (PrayectoP) | *Sin definir* | *Sin definir* | *Pendiente* |  


## Avances realizados 14/05/2026
## Avances actuales

### Base de datos implementada
Se implementó correctamente la base de datos del sistema utilizando MySQL.

### Tablas creadas
- clientes
- citas
- conversaciones

### Relaciones implementadas
- Relación entre clientes y citas
- Relación entre clientes y conversaciones

### Datos de prueba
Se realizaron inserciones y consultas exitosas.

### Corrección de puerto MySQL (3306 → 3307)
- **Problema**: El `docker-compose.yml` mapeaba el puerto `3306:3306`, pero el usuario tiene su MySQL local corriendo en el puerto `3307`.
- **Solución**: Se cambió el mapeo de puertos del host a `3307:3306` (el contenedor sigue usando el puerto interno 3306, pero se accede desde el host por el 3307).
- **Nota**: La variable `DB_MYSQLDB_PORT` en n8n se mantiene en `3306` porque n8n se conecta directamente al contenedor `mysql` por la red interna de Docker, no desde el host.

### 2026-05-18 - Implementación de Workflows n8n
- **Workflow Principal** (`workflows/principal-recepcion.json`):
  - Webhook para recibir mensajes de Evolution API en `POST /webhook/whatsapp-webhook`
  - Nodo Code para extraer mensaje, teléfono y nombre del payload de Evolution API
  - HTTP Request a Gemini API para clasificar el mensaje en 5 categorías
  - Switch para enrutar al sub-workflow correspondiente
  - MySQL para registrar la conversación en la tabla `conversaciones`
  - HTTP Request a Evolution API para enviar la respuesta al cliente
  - Respond to Webhook para confirmar la recepción
- **Sub-workflow Agendamiento** (`workflows/sub-agendamiento.json`):
  - Busca al cliente por teléfono en MySQL, lo crea si no existe
  - Consulta citas próximas del cliente
  - Detecta si el mensaje es para agendar, reprogramar o cancelar
  - Genera respuesta personalizada con la información de citas
- **Sub-workflow Cotización** (`workflows/sub-cotizacion.json`):
  - Detecta el servicio solicitado mediante palabras clave
  - Responde con precios de referencia para el servicio específico
  - Muestra lista completa de precios si no se detecta un servicio en particular
- **Sub-workflow Diagnóstico** (`workflows/sub-diagnostico.json`):
  - Envía el mensaje a Gemini con prompt especializado en diagnóstico de motocicletas
  - Gemini clasifica el sistema afectado (MOTOR, FRENOS, SUSPENSIÓN, etc.)
  - Genera preguntas clave para acotar la falla
- **Sub-workflow Información** (`workflows/sub-informacion.json`):
  - Detecta si el cliente pregunta por horarios, ubicación, pagos, tiempos o servicios
  - Responde con la información específica solicitada o un resumen completo
- **Sub-workflow Queja** (`workflows/sub-queja.json`):
  - Busca al cliente y consulta su historial de citas recientes
  - Genera respuesta de disculpa y escalamiento
  - Indica que un asesor contactará en 24 horas hábiles
- **Documentación**: Se actualizó `docs/arquitectura.md` con diagramas de flujo detallados para cada workflow, la estructura de nodos, endpoints y variables de entorno requeridas.
- **Variables de entorno**: Se agregó `GEMINI_API_KEY` como variable requerida (configurar en las environment variables de n8n).

