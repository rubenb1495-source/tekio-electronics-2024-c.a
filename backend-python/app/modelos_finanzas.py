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
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.base_datos import Base


class MonedaInstrumento(str, Enum):
    USD = "USD"
    USDT = "USDT"
    BS = "BS"


class TipoPrecioInstrumento(str, Enum):
    PROMO = "PROMO"
    REGULAR = "REGULAR"


class EstadoVenta(str, Enum):
    CUADRADA = "CUADRADA"
    CON_SALDO = "CON_SALDO"
    ANULADA = "ANULADA"
    DEVUELTA = "DEVUELTA"


class TipoMovimientoPago(str, Enum):
    INGRESO = "INGRESO"
    EGRESO = "EGRESO"
    TRASLADO = "TRASLADO"


class TipoDocumentoPago(str, Enum):
    VENTA = "VENTA"
    ABONO = "ABONO"
    CASHEA = "CASHEA"
    GASTO = "GASTO"
    COMPRA = "COMPRA"
    GUIA = "GUIA"
    PARTE_DE_PAGO = "PARTE_DE_PAGO"
    DEVOLUCION = "DEVOLUCION"
    LIQUIDACION_COMISION = "LIQUIDACION_COMISION"
    TESORERIA = "TESORERIA"
    CAMBIO_DIVISA = "CAMBIO_DIVISA"
    GASTO_OPERATIVO = "GASTO_OPERATIVO"
    NOMINA = "NOMINA"


class EstadoVerificacionPago(str, Enum):
    CONFIRMADO = "CONFIRMADO"
    PENDIENTE = "PENDIENTE"


class EstadoReingresoNC(str, Enum):
    POR_PREPARAR = "POR_PREPARAR"
    GARANTIA = "GARANTIA"
    LISTO = "LISTO"


class TipoCuentaPorCobrar(str, Enum):
    CLIENTE = "CLIENTE"
    CASHEA = "CASHEA"


class EstadoCuentaPorCobrar(str, Enum):
    PENDIENTE = "PENDIENTE"
    PAGADA = "PAGADA"
    ANULADA = "ANULADA"


class InstrumentoFinanciero(Base):
    __tablename__ = "instrumentos_financieros"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    moneda: Mapped[str] = mapped_column(String(10), nullable=False)
    tipo_precio: Mapped[str] = mapped_column(String(15), nullable=False)
    requiere_verificacion: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    liquida_en_bs: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    saldo_inicial: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Venta(Base):
    __tablename__ = "ventas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    numero_venta: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id"), index=True, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("terceros.id"), nullable=True)
    asesor_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    tecnico_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    canal_visita: Mapped[str] = mapped_column(String(60), default="Tienda", nullable=False)
    tipo_entrega: Mapped[str] = mapped_column(String(60), default="Tienda", nullable=False)
    datos_entrega_json: Mapped[str] = mapped_column(Text, default="", nullable=False)
    origen_equipo: Mapped[str] = mapped_column(String(60), default="Propio", nullable=False)
    tasa_bcv_snapshot: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"), nullable=False)
    tasa_usdt_snapshot: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"), nullable=False)
    recargo_porcentaje_snapshot: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"), nullable=False)
    recargo_especial_porcentaje: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    total_promo_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    total_regular_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    vuelto_caja_chica_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    es_factura: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    numero_control: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default=EstadoVenta.CUADRADA.value, nullable=False, index=True)
    motivo_anulacion: Mapped[str] = mapped_column(Text, default="", nullable=False)
    nota: Mapped[str] = mapped_column(Text, default="", nullable=False)
    creado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    sucursal = relationship("Sucursal")
    cliente = relationship("Tercero")
    asesor = relationship("Usuario", foreign_keys=[asesor_id])
    tecnico = relationship("Usuario", foreign_keys=[tecnico_id])
    creado_por = relationship("Usuario", foreign_keys=[creado_por_id])
    detalles = relationship("VentaDetalle", back_populates="venta", cascade="all, delete-orphan")
    pagos = relationship("Pago", back_populates="venta")
    cuentas_por_cobrar = relationship("CuentaPorCobrar", back_populates="venta")


class VentaDetalle(Base):
    __tablename__ = "ventas_detalle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("ventas.id"), index=True, nullable=False)
    equipo_id: Mapped[int | None] = mapped_column(ForeignKey("equipos.id"), nullable=True)
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("catalogo_articulos.id"), nullable=True)
    descripcion: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    descripcion_servicio: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    precio_promo_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    precio_regular_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    precio_pactado_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    costo_total_snapshot_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)

    venta = relationship("Venta", back_populates="detalles")
    equipo = relationship("Equipo")
    articulo = relationship("CatalogoArticulo")


class ExtractoBancario(Base):
    __tablename__ = "extractos_bancarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    instrumento_id: Mapped[int] = mapped_column(ForeignKey("instrumentos_financieros.id"), index=True, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    referencia: Mapped[str] = mapped_column(String(120), default="", nullable=False, index=True)
    descripcion: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    monto_con_signo: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    conciliado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    instrumento = relationship("InstrumentoFinanciero")


class Pago(Base):
    __tablename__ = "pagos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    venta_id: Mapped[int | None] = mapped_column(ForeignKey("ventas.id"), index=True, nullable=True)
    instrumento_id: Mapped[int] = mapped_column(ForeignKey("instrumentos_financieros.id"), index=True, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    tipo_movimiento: Mapped[str] = mapped_column(String(20), default=TipoMovimientoPago.INGRESO.value, nullable=False)
    tipo_documento: Mapped[str] = mapped_column(String(20), default=TipoDocumentoPago.VENTA.value, nullable=False)
    monto_moneda_origen: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(10), nullable=False)
    tasa_bcv_dia: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"), nullable=False)
    tasa_usdt_dia: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"), nullable=False)
    usd_nominal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    usd_real: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    cubre_promo_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    referencia: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    estado_verificacion: Mapped[str] = mapped_column(String(20), default=EstadoVerificacionPago.CONFIRMADO.value, nullable=False, index=True)
    verificado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    conciliado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extracto_id: Mapped[int | None] = mapped_column(ForeignKey("extractos_bancarios.id"), nullable=True)
    anulado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    nota: Mapped[str] = mapped_column(Text, default="", nullable=False)

    venta = relationship("Venta", back_populates="pagos")
    instrumento = relationship("InstrumentoFinanciero")
    verificado_por = relationship("Usuario")
    extracto = relationship("ExtractoBancario")


class NotaCredito(Base):
    __tablename__ = "notas_credito"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    numero_nc: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    venta_original_id: Mapped[int] = mapped_column(ForeignKey("ventas.id"), index=True, nullable=False)
    equipo_id: Mapped[int | None] = mapped_column(ForeignKey("equipos.id"), nullable=True)
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("catalogo_articulos.id"), nullable=True)
    cantidad: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    monto_reconocido_promo_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    motivo: Mapped[str] = mapped_column(String(255), nullable=False)
    estado_reingreso: Mapped[str] = mapped_column(String(20), default=EstadoReingresoNC.POR_PREPARAR.value, nullable=False)
    autorizado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)

    venta_original = relationship("Venta")
    equipo = relationship("Equipo")
    articulo = relationship("CatalogoArticulo")
    autorizado_por = relationship("Usuario")


class CuentaPorCobrar(Base):
    __tablename__ = "cuentas_por_cobrar"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("ventas.id"), index=True, nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("terceros.id"), nullable=True)
    monto_original_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    saldo_pendiente_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default=EstadoCuentaPorCobrar.PENDIENTE.value, nullable=False, index=True)

    venta = relationship("Venta", back_populates="cuentas_por_cobrar")
    cliente = relationship("Tercero")


class CierreMensual(Base):
    __tablename__ = "cierres_mensuales"
    __table_args__ = (UniqueConstraint("anio", "mes", name="uq_cierre_anio_mes"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    mes: Mapped[int] = mapped_column(Integer, nullable=False)
    cerrado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    fecha_cierre: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resumen_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    bloqueado: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    cerrado_por = relationship("Usuario")
