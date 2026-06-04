-- =============================================================
-- MotoServicio Timón — Migración V1 → V2
-- =============================================================

-- 1. Migrar clientes: agregar columnas faltantes
ALTER TABLE clientes
  ADD COLUMN email VARCHAR(255) AFTER telefono,
  ADD COLUMN direccion TEXT AFTER email,
  ADD COLUMN motos_registradas JSON AFTER direccion,
  ADD COLUMN fuente VARCHAR(50) DEFAULT 'whatsapp' AFTER motos_registradas,
  ADD COLUMN notas TEXT AFTER fuente,
  ADD COLUMN ultima_interaccion TIMESTAMP AFTER notas,
  ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER ultima_interaccion,
  ADD COLUMN activo BOOLEAN DEFAULT TRUE AFTER updated_at,
  ADD INDEX idx_activo (activo),
  MODIFY fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Migrar fecha_registro → created_at
ALTER TABLE clientes
  CHANGE fecha_registro created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Actualizar cliente existente con datos mínimos
UPDATE clientes SET fuente = 'whatsapp', activo = TRUE WHERE fuente IS NULL;

-- 2. Crear tablas faltantes

CREATE TABLE IF NOT EXISTS conversaciones (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS mensajes (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS citas (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS servicios (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS quejas (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS perfiles_usuario (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS recordatorios (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS logs (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS metricas (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tipo VARCHAR(50) NOT NULL,
    valor DECIMAL(15,4) NOT NULL,
    tags JSON,
    periodo VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_tipo (tipo),
    INDEX idx_tipo_created (tipo, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
