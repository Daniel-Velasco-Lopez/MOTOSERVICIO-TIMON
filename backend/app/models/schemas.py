from pydantic import BaseModel, Field, field_validator
from typing import Optional
import re


class MessageRequest(BaseModel):
    telefono: str = Field(..., description="Número de teléfono del cliente")
    mensaje: str = Field(..., description="Texto del mensaje")
    nombre: Optional[str] = None
    remoteJid: Optional[str] = None
    timestamp: Optional[int] = None

    @field_validator("telefono")
    @classmethod
    def validate_telefono(cls, v: str) -> str:
        cleaned = re.sub(r"[^\d]", "", v)
        if len(cleaned) < 10 or len(cleaned) > 15:
            raise ValueError("INVALID_PHONE")
        return cleaned

    @field_validator("mensaje")
    @classmethod
    def validate_mensaje(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("EMPTY_MESSAGE")
        if len(v) > 4096:
            raise ValueError("MSG_TOO_LONG")
        return v


class MessageResponse(BaseModel):
    success: bool
    respuesta: Optional[str] = None
    categoria: Optional[str] = None
    conversacion_id: Optional[int] = None
    requiere_accion: Optional[str] = None
    proximo_estado: Optional[str] = None
    tiempo_procesamiento_ms: Optional[int] = None
    error: Optional[str] = None
    codigo_error: Optional[str] = None


class MemoryRetrieveRequest(BaseModel):
    telefono: str
    mensaje: str
    limite: int = 5
    incluir_similares: bool = True


class MemoryRetrieveResponse(BaseModel):
    success: bool
    episodica: list = []
    semantica: list = []
    total: int = 0


class ToolExecuteRequest(BaseModel):
    tool: str
    parametros: dict = {}


class ToolExecuteResponse(BaseModel):
    success: bool
    tool: str
    data: Optional[dict] = None
    error: Optional[str] = None


class CustomerProfile(BaseModel):
    id: int
    nombre: str
    telefono: str
    email: Optional[str] = None
    motos_registradas: list = []
    citas_recientes: list = []
    ultimos_mensajes: list = []
    total_gastado: float = 0


class AppointmentRequest(BaseModel):
    cliente_id: int
    servicio: str
    fecha: str
    hora: str
    moto: Optional[str] = None


class AppointmentResponse(BaseModel):
    success: bool
    cita_id: Optional[int] = None
    servicio: Optional[str] = None
    fecha: Optional[str] = None
    hora: Optional[str] = None
    estado: Optional[str] = None
    error: Optional[str] = None
    codigo_error: Optional[str] = None


class ErrorResponse(BaseModel):
    codigo: str
    mensaje: str
    detalle: Optional[str] = None
