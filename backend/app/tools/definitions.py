import json
import logging
from datetime import datetime, date
from typing import Optional

from app.services.gemini import gemini_service
from app.persistence.repository import Repository

logger = logging.getLogger(__name__)


async def handle_registrar_cliente(params: dict) -> dict:
    repo = Repository()
    try:
        telefono = params.get("telefono")
        if not telefono:
            return {"success": False, "error": "teléfono requerido"}
        nombre = params.get("nombre", "")
        cliente = await repo.upsert_cliente(telefono, nombre)
        if cliente:
            return {"success": True, "data": {"cliente_id": cliente.id, "nombre": cliente.nombre, "telefono": cliente.telefono}}
        return {"success": False, "error": "no se pudo crear el cliente"}
    except Exception as e:
        logger.error(f"Error registrar_cliente: {e}")
        return {"success": False, "error": str(e)}


async def handle_cotizar_servicio(params: dict) -> dict:
    repo = Repository()
    try:
        servicio = params.get("servicio", "")
        if not servicio:
            return {"success": False, "error": "servicio requerido"}
        precios = await repo.obtener_precios(servicio)
        if precios:
            lines = [f"💰 *{p.nombre}*: ${float(p.precio_min or 0):.2f} - ${float(p.precio_max or 0):.2f}" for p in precios]
            return {"success": True, "data": {"precios": [{"servicio": p.nombre, "precio_min": str(p.precio_min), "precio_max": str(p.precio_max), "descripcion": p.descripcion} for p in precios], "mensaje": "\n".join(lines)}}
        suggestions = await repo.suggest_servicios(servicio)
        if suggestions:
            return {"success": True, "data": {"sugerencias": [s.nombre for s in suggestions], "mensaje": f"No encontré exactamente '{servicio}'. Estos son los servicios disponibles:\n" + "\n".join(f"- {s.nombre}" for s in suggestions)}}
        return {"success": True, "data": {"precios": [], "mensaje": f"No encontré el servicio '{servicio}'."}}
    except Exception as e:
        logger.error(f"Error cotizar_servicio: {e}")
        return {"success": False, "error": str(e)}


async def handle_consultar_disponibilidad(params: dict) -> dict:
    repo = Repository()
    try:
        fecha_str = params.get("fecha", "")
        fecha = None
        if fecha_str and fecha_str != "hoy":
            try:
                fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        if not fecha:
            fecha = date.today()
        horarios = await repo.obtener_horarios_disponibles(fecha)
        return {"success": True, "data": {"fecha": fecha.isoformat(), "horarios": [h if isinstance(h, str) else h.isoformat() for h in horarios], "hay_disponibilidad": bool(horarios)}}
    except Exception as e:
        logger.error(f"Error consultar_disponibilidad: {e}")
        return {"success": False, "error": str(e)}


async def handle_agendar_cita(params: dict) -> dict:
    repo = Repository()
    try:
        telefono = params.get("telefono")
        servicio = params.get("servicio")
        fecha_str = params.get("fecha")
        hora_str = params.get("hora", "")
        if not all([telefono, servicio, fecha_str]):
            return {"success": False, "error": "faltan datos: telefono, servicio, fecha"}
        cliente = await repo.upsert_cliente(telefono)
        if not cliente:
            return {"success": False, "error": "cliente no encontrado"}
        cita = await repo.crear_cita(cliente.id, servicio, fecha_str, hora_str)
        if cita:
            return {"success": True, "data": {"cita_id": cita.id, "fecha": fecha_str, "hora": hora_str or "por confirmar", "servicio": servicio}}
        return {"success": False, "error": "no se pudo crear la cita"}
    except Exception as e:
        logger.error(f"Error agendar_cita: {e}")
        return {"success": False, "error": str(e)}


async def handle_registrar_queja(params: dict) -> dict:
    repo = Repository()
    try:
        telefono = params.get("telefono")
        descripcion = params.get("descripcion", "")
        urgencia = params.get("urgencia", "media")
        if not telefono:
            return {"success": False, "error": "teléfono requerido"}
        cliente = await repo.upsert_cliente(telefono)
        queja = await repo.crear_queja(cliente.id, descripcion, urgencia)
        if queja:
            return {"success": True, "data": {"queja_id": queja.id, "urgencia": urgencia, "ticket": queja.ticket}}
        return {"success": False, "error": "no se pudo registrar la queja"}
    except Exception as e:
        logger.error(f"Error registrar_queja: {e}")
        return {"success": False, "error": str(e)}


async def handle_diagnosticar_falla(params: dict) -> dict:
    repo = Repository()
    try:
        sintomas = params.get("sintomas", "")
        if not sintomas:
            return {"success": False, "error": "síntomas requeridos"}

        gemini_result = None
        if gemini_service and gemini_service.client:
            try:
                diag_prompt = f"Diagnostica la posible falla de moto basado en estos síntomas: {sintomas}\nResponde en español, indica causa probable y solución sugerida."
                gemini_result = await gemini_service.generate(diag_prompt)
            except Exception:
                pass

        fallas = await repo.obtener_fallas_por_sintomas(sintomas)
        if gemini_result:
            return {"success": True, "data": {"diagnostico_gemini": gemini_result, "fallas_bd": [{"causa": f.causa, "solucion": f.solucion} for f in fallas]}}
        if fallas:
            return {"success": True, "data": {"fallas_bd": [{"causa": f.causa, "solucion": f.solucion} for f in fallas]}}
        return {"success": True, "data": {"mensaje": "No encontré una falla específica en la base de datos. Recomiendo agendar una revisión.", "requiere_revision": True}}
    except Exception as e:
        logger.error(f"Error diagnosticar_falla: {e}")
        return {"success": False, "error": str(e)}


async def handle_enviar_mensaje_whatsapp(params: dict) -> dict:
    try:
        telefono = params.get("telefono")
        mensaje = params.get("mensaje")
        if not telefono or not mensaje:
            return {"success": False, "error": "teléfono y mensaje requeridos"}
        try:
            from app.services.evolution_client import evolution_service
            result = await evolution_service.send_text(telefono, mensaje)
            if result:
                return {"success": True, "data": {"status": "sent"}}
        except ImportError:
            logger.warning("evolution_client no disponible, mensaje no enviado")
        return {"success": False, "error": "Evolution API no conectado"}
    except Exception as e:
        logger.error(f"Error enviar_mensaje_whatsapp: {e}")
        return {"success": False, "error": str(e)}


async def handle_consultar_historial_cliente(params: dict) -> dict:
    repo = Repository()
    try:
        telefono = params.get("telefono")
        if not telefono:
            return {"success": False, "error": "teléfono requerido"}
        cliente = await repo.buscar_cliente_por_telefono(telefono)
        if not cliente:
            return {"success": False, "error": "cliente no encontrado"}
        historial = await repo.obtener_historial_cliente(cliente.id)
        return {"success": True, "data": {"cliente_id": cliente.id, "citas": historial.get("citas", []), "quejas": historial.get("quejas", [])}}
    except Exception as e:
        logger.error(f"Error consultar_historial_cliente: {e}")
        return {"success": False, "error": str(e)}


TOOL_HANDLERS = {
    "registrar_cliente": handle_registrar_cliente,
    "cotizar_servicio": handle_cotizar_servicio,
    "consultar_disponibilidad": handle_consultar_disponibilidad,
    "agendar_cita": handle_agendar_cita,
    "registrar_queja": handle_registrar_queja,
    "diagnosticar_falla": handle_diagnosticar_falla,
    "enviar_mensaje_whatsapp": handle_enviar_mensaje_whatsapp,
    "consultar_historial_cliente": handle_consultar_historial_cliente,
}
