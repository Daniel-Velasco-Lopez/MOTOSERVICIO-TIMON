import json
from datetime import datetime, time
from typing import Optional
from sqlalchemy import (
    create_engine, Column, Integer, BigInteger, String, Text, Float,
    Boolean, DateTime, Time, Date, Enum, JSON, ForeignKey, Index, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs

from app.config import settings


class Base(DeclarativeBase, AsyncAttrs):
    pass


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    telefono: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    direccion: Mapped[Optional[str]] = mapped_column(Text)
    motos_registradas: Mapped[Optional[dict]] = mapped_column(JSON)
    fuente: Mapped[str] = mapped_column(String(50), default="whatsapp")
    notas: Mapped[Optional[str]] = mapped_column(Text)
    ultima_interaccion: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())
    activo: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    conversaciones = relationship("Conversacion", back_populates="cliente")
    mensajes = relationship("Mensaje", back_populates="cliente")
    citas = relationship("Cita", back_populates="cliente")
    quejas = relationship("Queja", back_populates="cliente")
    perfil = relationship("PerfilUsuario", uselist=False, back_populates="cliente")
    recordatorios = relationship("Recordatorio", back_populates="cliente")


class Conversacion(Base):
    __tablename__ = "conversaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="RESTRICT"), nullable=False, index=True)
    canal: Mapped[str] = mapped_column(String(50), default="whatsapp")
    estado: Mapped[str] = mapped_column(String(50), default="activa", index=True)
    resumen: Mapped[Optional[str]] = mapped_column(Text)
    intencion_principal: Mapped[Optional[str]] = mapped_column(String(50))
    extra: Mapped[Optional[dict]] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())
    cerrada_en: Mapped[Optional[datetime]] = mapped_column(DateTime)

    cliente = relationship("Cliente", back_populates="conversaciones")
    mensajes = relationship("Mensaje", back_populates="conversacion", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_cliente_estado", "cliente_id", "estado"),
    )


class Mensaje(Base):
    __tablename__ = "mensajes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversacion_id: Mapped[int] = mapped_column(ForeignKey("conversaciones.id", ondelete="CASCADE"), nullable=False, index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="RESTRICT"), nullable=False, index=True)
    rol: Mapped[str] = mapped_column(Enum("user", "assistant", "system"), nullable=False)
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    contenido_resumido: Mapped[Optional[str]] = mapped_column(String(500))
    categoria: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    extra: Mapped[Optional[dict]] = mapped_column("metadata", JSON)
    token_count: Mapped[Optional[int]] = mapped_column(Integer)
    tiempo_procesamiento_ms: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(6), default=func.current_timestamp(6), index=True)

    conversacion = relationship("Conversacion", back_populates="mensajes")
    cliente = relationship("Cliente", back_populates="mensajes")

    __table_args__ = (
        Index("idx_contenido", "contenido", mysql_prefix="FULLTEXT"),
    )


class Cita(Base):
    __tablename__ = "citas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="RESTRICT"), nullable=False, index=True)
    servicio: Mapped[str] = mapped_column(String(150), nullable=False)
    moto: Mapped[Optional[str]] = mapped_column(String(150))
    fecha: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    hora: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    duracion_estimada: Mapped[int] = mapped_column(Integer, default=30)
    estado: Mapped[str] = mapped_column(
        Enum("pendiente", "confirmada", "en_proceso", "completada", "cancelada", "no_asistio"),
        default="pendiente", index=True,
    )
    notas: Mapped[Optional[str]] = mapped_column(Text)
    recordatorio_enviado: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())

    cliente = relationship("Cliente", back_populates="citas")
    quejas = relationship("Queja", back_populates="cita")
    recordatorios = relationship("Recordatorio", back_populates="cita")

    __table_args__ = (
        Index("idx_fecha_hora", "fecha", "hora", unique=True),
    )


class Servicio(Base):
    __tablename__ = "servicios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
    categoria: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    precio_min: Mapped[Optional[float]] = mapped_column(Float)
    precio_max: Mapped[Optional[float]] = mapped_column(Float)
    incluye: Mapped[Optional[str]] = mapped_column(Text)
    tiempo_estimado: Mapped[Optional[int]] = mapped_column(Integer)
    marcas_compatibles: Mapped[Optional[dict]] = mapped_column(JSON)
    cilindrajes_soportados: Mapped[Optional[dict]] = mapped_column(JSON)
    tags: Mapped[Optional[dict]] = mapped_column(JSON)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())

    __table_args__ = (
        Index("idx_nombre", "nombre", mysql_prefix="FULLTEXT"),
    )


class Queja(Base):
    __tablename__ = "quejas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="RESTRICT"), nullable=False)
    cita_id: Mapped[Optional[int]] = mapped_column(ForeignKey("citas.id", ondelete="SET NULL"))
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    ticket: Mapped[Optional[str]] = mapped_column(String(20))
    urgencia: Mapped[str] = mapped_column(Enum("baja", "media", "alta"), default="media", index=True)
    estado: Mapped[str] = mapped_column(Enum("pendiente", "en_proceso", "resuelta", "cerrada"), default="pendiente", index=True)
    solucion: Mapped[Optional[str]] = mapped_column(Text)
    notificado_cliente: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())

    cliente = relationship("Cliente", back_populates="quejas")
    cita = relationship("Cita", back_populates="quejas")


class PerfilUsuario(Base):
    __tablename__ = "perfiles_usuario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), unique=True, nullable=False)
    frecuencia_visitas: Mapped[str] = mapped_column(String(50), default="desconocida")
    servicios_frecuentes: Mapped[Optional[dict]] = mapped_column(JSON)
    preferencia_horario: Mapped[Optional[str]] = mapped_column(String(20))
    segmento: Mapped[str] = mapped_column(String(50), default="general")
    gasto_promedio: Mapped[Optional[float]] = mapped_column(Float)
    total_gastado: Mapped[float] = mapped_column(Float, default=0)
    satisfaccion_promedio: Mapped[Optional[float]] = mapped_column(Float)
    embedding_id: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())

    cliente = relationship("Cliente", back_populates="perfil")


class DiagnosticoFalla(Base):
    __tablename__ = "diagnosticos_fallas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sintomas: Mapped[str] = mapped_column(Text, nullable=False)
    causa: Mapped[str] = mapped_column(Text, nullable=False)
    solucion: Mapped[str] = mapped_column(Text, nullable=False)
    sistema: Mapped[Optional[str]] = mapped_column(String(100))
    urgencia: Mapped[str] = mapped_column(String(20), default="media")
    keywords: Mapped[Optional[dict]] = mapped_column(JSON)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())


class Recordatorio(Base):
    __tablename__ = "recordatorios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False)
    cita_id: Mapped[Optional[int]] = mapped_column(ForeignKey("citas.id", ondelete="SET NULL"))
    telefono: Mapped[str] = mapped_column(String(20), nullable=False)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[str] = mapped_column(Enum("cita", "seguimiento", "promocion", "recordatorio_general"), default="cita")
    fecha_programada: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fecha_enviado: Mapped[Optional[datetime]] = mapped_column(DateTime)
    estado: Mapped[str] = mapped_column(Enum("pendiente", "enviado", "fallido", "cancelado"), default="pendiente")

    cliente = relationship("Cliente", back_populates="recordatorios")
    cita = relationship("Cita", back_populates="recordatorios")

    __table_args__ = (
        Index("idx_pendientes", "estado", "fecha_programada", postgresql_where="estado = 'pendiente'"),
    )


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nivel: Mapped[str] = mapped_column(Enum("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"), default="INFO", index=True)
    componente: Mapped[str] = mapped_column(String(100), nullable=False)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    extra: Mapped[Optional[dict]] = mapped_column("metadata", JSON)
    trace_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    cliente_id: Mapped[Optional[int]] = mapped_column(Integer)
    telefono: Mapped[Optional[str]] = mapped_column(String(20))
    tiempo_ms: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(3), default=func.current_timestamp(3), index=True)

    __table_args__ = (
        Index("idx_nivel_created", "nivel", "created_at"),
    )


class Metrica(Base):
    __tablename__ = "metricas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    tags: Mapped[Optional[dict]] = mapped_column(JSON)
    periodo: Mapped[Optional[str]] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.current_timestamp())

    __table_args__ = (
        Index("idx_tipo_created", "tipo", "created_at"),
    )


# -- Engine factory --

def get_database_url() -> str:
    return (
        f"mysql+aiomysql://{settings.mysql_user}:{settings.mysql_password}"
        f"@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
    )


engine = create_async_engine(get_database_url(), echo=settings.debug, pool_size=5, max_overflow=10)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
