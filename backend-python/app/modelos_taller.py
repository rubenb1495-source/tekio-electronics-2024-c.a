from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.base_datos import Base


class TipoPreparacion(str, Enum):
    ESTANDAR = "ESTANDAR"
    ESPECIAL = "ESPECIAL"


class ResultadoPreparacion(str, Enum):
    LISTO = "LISTO"
    HOSPITAL = "HOSPITAL"
    CEMENTERIO = "CEMENTERIO"


class OrigenRepuestoSolicitado(str, Enum):
    HOSPITAL = "HOSPITAL"
    CASO_TECNICO = "CASO_TECNICO"


class EstadoRepuestoSolicitado(str, Enum):
    PENDIENTE = "PENDIENTE"
    COMPRADO = "COMPRADO"
    RECIBIDO = "RECIBIDO"
    CANCELADO = "CANCELADO"


class TipoCasoPostventa(str, Enum):
    GARANTIA = "GARANTIA"
    SERVICIO = "SERVICIO"


class EstadoCasoPostventa(str, Enum):
    RECIBIDO = "RECIBIDO"
    EN_DIAGNOSTICO = "EN_DIAGNOSTICO"
    ESPERANDO_PRESUPUESTO = "ESPERANDO_PRESUPUESTO"
    ESPERANDO_APROBACION = "ESPERANDO_APROBACION"
    AUTORIZADO = "AUTORIZADO"
    ESPERANDO_REPUESTO = "ESPERANDO_REPUESTO"
    TERMINADO = "TERMINADO"
    LISTO_PARA_ENTREGAR = "LISTO_PARA_ENTREGAR"
    ENTREGADO = "ENTREGADO"
    RECHAZADO = "RECHAZADO"


class Preparacion(Base):
    __tablename__ = "preparaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    equipo_id: Mapped[int] = mapped_column(ForeignKey("equipos.id"), index=True, nullable=False)
    tecnico_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), default=TipoPreparacion.ESTANDAR.value, nullable=False)
    pago_tecnico_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("1.00"), nullable=False)
    resultado: Mapped[str] = mapped_column(String(20), nullable=False)
    nota: Mapped[str] = mapped_column(Text, default="", nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    equipo = relationship("Equipo")
    tecnico = relationship("Usuario")
    componentes = relationship(
        "PreparacionComponente",
        back_populates="preparacion",
        cascade="all, delete-orphan",
    )


class PreparacionComponente(Base):
    __tablename__ = "preparaciones_componentes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    preparacion_id: Mapped[int] = mapped_column(ForeignKey("preparaciones.id"), index=True, nullable=False)
    articulo_id: Mapped[int] = mapped_column(ForeignKey("catalogo_articulos.id"), nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    costo_unitario_snapshot_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )

    preparacion = relationship("Preparacion", back_populates="componentes")
    articulo = relationship("CatalogoArticulo")


class RepuestoSolicitado(Base):
    __tablename__ = "repuestos_solicitados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    origen: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    equipo_id: Mapped[int | None] = mapped_column(ForeignKey("equipos.id"), index=True, nullable=True)
    caso_id: Mapped[int | None] = mapped_column(ForeignKey("casos_postventa.id"), index=True, nullable=True)
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("catalogo_articulos.id"), nullable=True)
    descripcion_repuesto: Mapped[str] = mapped_column(String(255), nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), default=EstadoRepuestoSolicitado.PENDIENTE.value, nullable=False, index=True
    )
    solicitado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    fecha_solicitud: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    fecha_recepcion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notificado_tecnico: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    equipo = relationship("Equipo")
    caso = relationship("CasoPostventa")
    articulo = relationship("CatalogoArticulo")
    solicitado_por = relationship("Usuario")


class CasoPostventa(Base):
    __tablename__ = "casos_postventa"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    numero_caso: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id"), nullable=False)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("terceros.id"), nullable=True)
    equipo_id: Mapped[int | None] = mapped_column(ForeignKey("equipos.id"), nullable=True)
    serial_o_codigo: Mapped[str] = mapped_column(String(100), default="", nullable=False, index=True)
    descripcion_equipo: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo_marca_color: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    accesorios_recibidos: Mapped[str] = mapped_column(Text, default="", nullable=False)
    estado_fisico: Mapped[str] = mapped_column(Text, default="", nullable=False)
    clave_equipo: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    falla_reportada: Mapped[str] = mapped_column(Text, nullable=False)
    tecnico_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    diagnostico: Mapped[str] = mapped_column(Text, default="", nullable=False)
    trabajo_realizado: Mapped[str] = mapped_column(Text, default="", nullable=False)
    estado: Mapped[str] = mapped_column(
        String(30), default=EstadoCasoPostventa.RECIBIDO.value, nullable=False, index=True
    )
    alerta_garantia: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fecha_ingreso: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sucursal = relationship("Sucursal")
    cliente = relationship("Tercero")
    equipo = relationship("Equipo")
    tecnico = relationship("Usuario")
    presupuestos = relationship(
        "CasoPresupuesto",
        back_populates="caso",
        order_by="desc(CasoPresupuesto.id)",
        cascade="all, delete-orphan",
    )
    repuestos_usados = relationship(
        "CasoRepuestoUsado",
        back_populates="caso",
        cascade="all, delete-orphan",
    )


class CasoPresupuesto(Base):
    __tablename__ = "casos_presupuestos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    caso_id: Mapped[int] = mapped_column(ForeignKey("casos_postventa.id"), index=True, nullable=False)
    mano_obra_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    repuestos_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    total_promo_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    aprobado_cliente: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    fecha_envio: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    fecha_respuesta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    nota_cliente: Mapped[str] = mapped_column(Text, default="", nullable=False)

    caso = relationship("CasoPostventa", back_populates="presupuestos")


class CasoRepuestoUsado(Base):
    __tablename__ = "casos_repuestos_usados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    caso_id: Mapped[int] = mapped_column(ForeignKey("casos_postventa.id"), index=True, nullable=False)
    articulo_id: Mapped[int] = mapped_column(ForeignKey("catalogo_articulos.id"), nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    costo_unitario_snapshot_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    caso = relationship("CasoPostventa", back_populates="repuestos_usados")
    articulo = relationship("CatalogoArticulo")
