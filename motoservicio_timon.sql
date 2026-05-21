USE motoservicio_timon;

CREATE TABLE clientes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100),
    telefono VARCHAR(20) UNIQUE NOT NULL,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE citas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cliente_id INT NOT NULL,
    fecha DATE,
    hora TIME,
    servicio VARCHAR(100),
    estado VARCHAR(50),
    FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE RESTRICT
);

CREATE TABLE conversaciones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cliente_id INT NOT NULL,
    mensaje TEXT,
    respuesta TEXT,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE RESTRICT
);



INSERT INTO clientes (nombre, telefono)
VALUES ('Daniel', '9535563732');

INSERT INTO citas (cliente_id, fecha, hora, servicio, estado)
VALUES (
1,
'2026-05-20',
'10:00:00',
'Cambio de aceite',
'Pendiente'
);

INSERT INTO conversaciones (cliente_id, mensaje, respuesta)
VALUES (
1,
'Quiero una cita',
'Tenemos disponibilidad mañana a las 10 AM'
);


SELECT * FROM clientes;
SELECT * FROM citas;
SELECT * FROM conversaciones;