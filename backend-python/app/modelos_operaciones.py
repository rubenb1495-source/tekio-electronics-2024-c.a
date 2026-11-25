from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.base_datos import Base


class TipoResolucionDevolucion(str, Enum):
    CAMBIO_IGUAL = "CAMBIO_IGUAL"
    GARANTIA_COMPONENTE = "GARANTIA_COMPONENTE"
    CAMBIO_UPGRADE = "CAMBIO_UPGRADE"
    CAMBIO_DOWNGRADE = "CAMBIO_DOWNGRADE"
    REEMBOLSO_TOTAL = "REEMBOLSO_TOTAL"


class EstadoCotizacion(str, Enum):
    VIGENTE = "VIGENTE"
    CONVERTIDA = "CONVERTIDA"
    VENCIDA = "VENCIDA"
    ANULADA = "ANULADA"


class ModalidadCotizacion(str, Enum):
    DIVISAS = "DIVISAS"
    REGULAR = "REGULAR"
    CASHEA = "CASHEA"


class DevolucionGarantia(Base):
    __tablename__ = "devoluciones_garantias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    numero_operacion: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    venta_id: Mapped[int] = mapped_column(ForeignKey("ventas.id"), index=True, nullable=False)
    equipo_origen_id: Mapped[int | None] = mapped_column(ForeignKey("equipos.id"), nullable=True)
    equipo_destino_id: Mapped[int | None] = mapped_column(ForeignKey("equipos.id"), nullable=True)
    caso_taller_id: Mapped[int | None] = mapped_column(ForeignKey("casos_postventa.id"), nullable=True)
    articulo_repuesto_id: Mapped[int | None] = mapped_column(ForeignKey("catalogo_articulos.id"), nullable=True)
    tipo_resolucion: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    estado_reingreso_origen: Mapped[str] = mapped_column(String(30), default="POR_PREPARAR", nullable=False)
    diferencia_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    diferencia_promo_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    costo_garantia_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    instrumento_id: Mapped[int | None] = mapped_column(ForeignKey("instrumentos_financieros.id"), nullable=True)
    dejar_saldo_favor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    referencia_pago: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    motivo: Mapped[str] = mapped_column(Text, default="", nullable=False)
    autorizado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    venta = relationship("Venta")
    equipo_origen = relationship("Equipo", foreign_keys=[equipo_origen_id])
    equipo_destino = relationship("Equipo", foreign_keys=[equipo_destino_id])
    caso_taller = relationship("CasoPostventa")
    articulo_repuesto = relationship("CatalogoArticulo")
    instrumento = relationship("InstrumentoFinanciero")
    autorizado_por = relationship("Usuario")


class Cotizacion(Base):
    __tablename__ = "cotizaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    numero_cotizacion: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    vigencia_horas: Mapped[int] = mapped_column(Integer, default=48, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default=EstadoCotizacion.VIGENTE.value, nullable=False, index=True)
    modalidad_precio: Mapped[str] = mapped_column(String(20), default=ModalidadCotizacion.DIVISAS.value, nullable=False)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("terceros.id"), nullable=True)
    asesor_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id"), index=True, nullable=False)
    venta_id: Mapped[int | None] = mapped_column(ForeignKey("ventas.id"), nullable=True)
    tasa_bcv_snapshot: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"), nullable=False)
    recargo_porcentaje_snapshot: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"), nullable=False)
    total_promo_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    total_regular_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    nota: Mapped[str] = mapped_column(Text, default="", nullable=False)
    creado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    cliente = relationship("Tercero")
    asesor = relationship("Usuario", foreign_keys=[asesor_id])
    sucursal = relationship("Sucursal")
    venta = relationship("Venta")
    creado_por = relationship("Usuario", foreign_keys=[creado_por_id])
    detalles = relationship("CotizacionDetalle", back_populates="cotizacion", cascade="all, delete-orphan")


class CotizacionDetalle(Base):
    __tablename__ = "cotizaciones_detalle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cotizacion_id: Mapped[int] = mapped_column(ForeignKey("cotizaciones.id"), index=True, nullable=False)
    equipo_id: Mapped[int | None] = mapped_column(ForeignKey("equipos.id"), nullable=True)
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("catalogo_articulos.id"), nullable=True)
    descripcion: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    descripcion_servicio: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    precio_promo_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    precio_regular_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    precio_pactado_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    cotizacion = relationship("Cotizacion", back_populates="detalles")
    equipo = relationship("Equipo")
    articulo = relationship("CatalogoArticulo")


class LiquidacionComision(Base):
    __tablename__ = "liquidaciones_comisiones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_pago: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    monto_total_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    instrumento_id: Mapped[int] = mapped_column(ForeignKey("instrumentos_financieros.id"), nullable=False)
    referencia: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    pago_egreso_id: Mapped[int | None] = mapped_column(ForeignKey("pagos.id"), nullable=True)
    autorizado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    notas: Mapped[str] = mapped_column(Text, default="", nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    usuario = relationship("Usuario", foreign_keys=[usuario_id])
    autorizado_por = relationship("Usuario", foreign_keys=[autorizado_por_id])
    instrumento = relationship("InstrumentoFinanciero")
    pago_egreso = relationship("Pago")
    detalles = relationship(
        "LiquidacionComisionDetalle",
        back_populates="liquidacion",
        cascade="all, delete-orphan",
    )


class LiquidacionComisionDetalle(Base):
    __tablename__ = "liquidaciones_comisiones_detalle"
    __table_args__ = (
        UniqueConstraint("venta_id", "usuario_id", "concepto", name="uq_liq_venta_usuario_concepto"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    liquidacion_id: Mapped[int] = mapped_column(ForeignKey("liquidaciones_comisiones.id"), index=True, nullable=False)
    venta_id: Mapped[int | None] = mapped_column(ForeignKey("ventas.id"), index=True, nullable=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=False)
    referencia_origen: Mapped[str] = mapped_column(String(60), default="", nullable=False, index=True)
    concepto: Mapped[str] = mapped_column(String(40), nullable=False)
    base_promo_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    monto_comision_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)

    liquidacion = relationship("LiquidacionComision", back_populates="detalles")
    venta = relationship("Venta")
    usuario = relationship("Usuario")


class CierreCaja(Base):
    __tablename__ = "cierres_caja"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    fecha: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    sucursal_id: Mapped[int | None] = mapped_column(ForeignKey("sucursales.id"), index=True, nullable=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    cantidad_ventas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cantidad_anulaciones: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_ventas_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    total_ingresos_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    total_ingresos_bs: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"), nullable=False)
    total_egresos_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    total_egresos_bs: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"), nullable=False)
    total_cashea_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    desglose_instrumentos_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    efectivo_esperado_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    efectivo_declarado_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    diferencia_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    observaciones: Mapped[str] = mapped_column(Text, default="", nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    sucursal = relationship("Sucursal")
    usuario = relationship("Usuario")
