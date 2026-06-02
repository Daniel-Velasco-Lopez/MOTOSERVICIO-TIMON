import uuid
import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AsyncSessionLocal, Cliente, Cita, Servicio, Queja, DiagnosticoFalla

logger = logging.getLogger(__name__)


class Repository:
    async def upsert_cliente(self, telefono: str, nombre: str = "") -> Optional[Cliente]:
        async with AsyncSessionLocal() as session:
            try:
                result = await session.execute(select(Cliente).where(Cliente.telefono == telefono))
                cliente = result.scalar_one_or_none()
                if cliente:
                    if nombre and cliente.nombre != nombre:
                        cliente.nombre = nombre
                        await session.commit()
                    return cliente
                cliente = Cliente(telefono=telefono, nombre=nombre or "Cliente")
                session.add(cliente)
                await session.commit()
                await session.refresh(cliente)
                return cliente
            except Exception as e:
                await session.rollback()
                logger.error(f"Error upsert_cliente: {e}")
                return None

    async def buscar_cliente_por_telefono(self, telefono: str) -> Optional[Cliente]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Cliente).where(Cliente.telefono == telefono))
            return result.scalar_one_or_none()

    async def obtener_precios(self, servicio: str) -> list:
        async with AsyncSessionLocal() as session:
            pattern = f"%{servicio}%"
            result = await session.execute(
                select(Servicio).where(Servicio.nombre.ilike(pattern), Servicio.activo == True)
            )
            return list(result.scalars().all())

    async def suggest_servicios(self, query: str) -> list:
        async with AsyncSessionLocal() as session:
            pattern = f"%{query}%"
            result = await session.execute(
                select(Servicio).where(Servicio.nombre.ilike(pattern), Servicio.activo == True).limit(5)
            )
            return list(result.scalars().all())

    async def obtener_horarios_disponibles(self, fecha: date) -> list:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Cita.hora).where(Cita.fecha == fecha, Cita.estado != "cancelada")
            )
            occupied = {r[0] for r in result.all()}
            all_slots = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"]
            return [h for h in all_slots if h not in occupied]

    async def crear_cita(self, cliente_id: int, servicio: str, fecha_str: str, hora_str: str = "") -> Optional[Cita]:
        async with AsyncSessionLocal() as session:
            try:
                fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else date.today()
                hora_obj = datetime.strptime(hora_str or "09:00", "%H:%M").time()
                cita = Cita(
                    cliente_id=cliente_id,
                    servicio=servicio,
                    fecha=fecha,
                    hora=hora_obj,
                    estado="pendiente",
                )
                session.add(cita)
                await session.commit()
                await session.refresh(cita)
                return cita
            except Exception as e:
                await session.rollback()
                logger.error(f"Error crear_cita: {e}")
                return None

    async def crear_queja(self, cliente_id: int, descripcion: str, urgencia: str = "media") -> Optional[Queja]:
        async with AsyncSessionLocal() as session:
            try:
                ticket = f"Q{uuid.uuid4().hex[:8].upper()}"
                queja = Queja(
                    cliente_id=cliente_id,
                    descripcion=descripcion,
                    urgencia=urgencia,
                    estado="pendiente",
                )
                session.add(queja)
                await session.commit()
                await session.refresh(queja)
                queja.ticket = ticket
                await session.commit()
                return queja
            except Exception as e:
                await session.rollback()
                logger.error(f"Error crear_queja: {e}")
                return None

    async def obtener_fallas_por_sintomas(self, sintomas: str) -> list:
        async with AsyncSessionLocal() as session:
            pattern = f"%{sintomas}%"
            result = await session.execute(
                select(DiagnosticoFalla).where(
                    DiagnosticoFalla.sintomas.ilike(pattern),
                    DiagnosticoFalla.activo == True,
                )
            )
            return list(result.scalars().all())

    async def obtener_historial_cliente(self, cliente_id: int) -> dict:
        async with AsyncSessionLocal() as session:
            citas_result = await session.execute(
                select(Cita).where(Cita.cliente_id == cliente_id).order_by(Cita.fecha.desc()).limit(10)
            )
            citas = list(citas_result.scalars().all())

            quejas_result = await session.execute(
                select(Queja).where(Queja.cliente_id == cliente_id).order_by(Queja.created_at.desc()).limit(10)
            )
            quejas = list(quejas_result.scalars().all())

            return {
                "citas": [
                    {"id": c.id, "servicio": c.servicio, "fecha": str(c.fecha), "estado": c.estado}
                    for c in citas
                ],
                "quejas": [
                    {"id": q.id, "ticket": getattr(q, 'ticket', None), "urgencia": q.urgencia, "estado": q.estado}
                    for q in quejas
                ],
            }
