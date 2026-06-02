import pytest
from pydantic import ValidationError
from app.models.schemas import (
    MessageRequest,
    MessageResponse,
    MemoryRetrieveRequest,
    ToolExecuteRequest,
    AppointmentRequest,
)


class TestMessageRequest:
    def test_valid_message(self):
        req = MessageRequest(telefono="521234567890", mensaje="Hola", nombre="Daniel")
        assert req.telefono == "521234567890"
        assert req.mensaje == "Hola"
        assert req.nombre == "Daniel"

    def test_cleans_telefono(self):
        req = MessageRequest(telefono="+52 (123) 456-7890", mensaje="test")
        assert req.telefono == "521234567890"

    def test_rejects_short_telefono(self):
        with pytest.raises(ValidationError, match="INVALID_PHONE"):
            MessageRequest(telefono="123", mensaje="test")

    def test_rejects_empty_message(self):
        with pytest.raises(ValidationError, match="EMPTY_MESSAGE"):
            MessageRequest(telefono="521234567890", mensaje="   ")

    def test_rejects_long_message(self):
        with pytest.raises(ValidationError, match="MSG_TOO_LONG"):
            MessageRequest(telefono="521234567890", mensaje="x" * 5000)

    def test_optional_fields(self):
        req = MessageRequest(telefono="521234567890", mensaje="test")
        assert req.nombre is None
        assert req.remoteJid is None
        assert req.timestamp is None


class TestMessageResponse:
    def test_success_response(self):
        resp = MessageResponse(
            success=True,
            respuesta="Hola",
            categoria="COTIZACION",
            conversacion_id=1,
            requiere_accion="confirmar_cita",
            tiempo_procesamiento_ms=100,
        )
        assert resp.success is True
        assert resp.categoria == "COTIZACION"

    def test_error_response(self):
        resp = MessageResponse(
            success=False,
            error="Rate limit excedido",
            codigo_error="RATE_LIMITED",
        )
        assert resp.success is False
        assert resp.codigo_error == "RATE_LIMITED"


class TestMemoryRetrieveRequest:
    def test_valid(self):
        req = MemoryRetrieveRequest(telefono="521234567890", mensaje="consulta")
        assert req.limite == 5
        assert req.incluir_similares is True

    def test_custom_limits(self):
        req = MemoryRetrieveRequest(
            telefono="521234567890",
            mensaje="consulta",
            limite=10,
            incluir_similares=False,
        )
        assert req.limite == 10
        assert req.incluir_similares is False


class TestToolExecuteRequest:
    def test_valid(self):
        req = ToolExecuteRequest(
            tool="consultar_precio",
            parametros={"servicio": "cambio de aceite", "moto": "Italika FT150"},
        )
        assert req.tool == "consultar_precio"
        assert req.parametros["servicio"] == "cambio de aceite"

    def test_empty_params(self):
        req = ToolExecuteRequest(tool="listar_tools")
        assert req.parametros == {}


class TestAppointmentRequest:
    def test_valid(self):
        req = AppointmentRequest(
            cliente_id=1,
            servicio="Cambio de aceite",
            fecha="2026-06-05",
            hora="10:00",
        )
        assert req.cliente_id == 1
        assert req.servicio == "Cambio de aceite"

    def test_with_moto(self):
        req = AppointmentRequest(
            cliente_id=1,
            servicio="Cambio de aceite",
            fecha="2026-06-05",
            hora="10:00",
            moto="Italika FT150",
        )
        assert req.moto == "Italika FT150"
