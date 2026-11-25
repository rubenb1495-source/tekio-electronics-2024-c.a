from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

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


class GastoOperativo(Base):
    __tablename__ = "gastos_operativos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    categoria: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    sucursal_id: Mapped[int | None] = mapped_column(ForeignKey("sucursales.id"), index=True, nullable=True)
    proveedor: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    factura_comprobante: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, default="", nullable=False)
    moneda: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    monto_origen: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    tasa_bcv: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"), nullable=False)
    monto_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    instrumento_id: Mapped[int] = mapped_column(ForeignKey("instrumentos_financieros.id"), nullable=False)
    pago_egreso_id: Mapped[int | None] = mapped_column(ForeignKey("pagos.id"), nullable=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    sucursal = relationship("Sucursal")
    instrumento = relationship("InstrumentoFinanciero")
    pago_egreso = relationship("Pago")
    usuario = relationship("Usuario")


class DocumentoFiscal(Base):
    __tablename__ = "documentos_fiscales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tipo_libro: Mapped[str] = mapped_column(String(15), index=True, nullable=False)  # COMPRA | VENTA
    fecha: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    numero_factura: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    numero_control: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    rif_tercero: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    nombre_tercero: Mapped[str] = mapped_column(String(180), nullable=False)
    base_imponible: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"), nullable=False)
    monto_exento: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"), nullable=False)
    iva_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("16.00"), nullable=False)
    iva_monto: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"), nullable=False)
    igtf_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0.00"), nullable=False)
    igtf_monto: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"), nullable=False)
    total_documento: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"), nullable=False)
    retencion_iva_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0.00"), nullable=False)
    retencion_iva_monto: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"), nullable=False)
    comprobante_ret_iva: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    retencion_islr_monto: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"), nullable=False)
    comprobante_ret_islr: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    moneda: Mapped[str] = mapped_column(String(10), default="BS", nullable=False)
    tasa_bcv: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"), nullable=False)
    notas: Mapped[str] = mapped_column(Text, default="", nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    usuario = relationship("Usuario")


class ObligacionFiscal(Base):
    __tablename__ = "obligaciones_fiscales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tipo: Mapped[str] = mapped_column(String(40), index=True, nullable=False)  # IVA | ISLR | RETENCIONES | PATENTE_MUNICIPAL
    periodo: Mapped[str] = mapped_column(String(40), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    fecha_vencimiento: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    monto_estimado_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="PENDIENTE", index=True, nullable=False)  # PENDIENTE | DECLARADO | PAGADO
    referencia_pago: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    notas: Mapped[str] = mapped_column(Text, default="", nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NominaEmpleado(Base):
    __tablename__ = "nomina_empleados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), unique=True, index=True, nullable=False)
    cedula: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    cargo: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    sucursal_id: Mapped[int | None] = mapped_column(ForeignKey("sucursales.id"), nullable=True)
    fecha_ingreso: Mapped[date | None] = mapped_column(Date, nullable=True)
    salario_base_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    bono_cestaticket_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    datos_bancarios: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    usuario = relationship("Usuario")
    sucursal = relationship("Sucursal")


class NominaPeriodo(Base):
    __tablename__ = "nomina_periodos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    tipo_periodo: Mapped[str] = mapped_column(String(20), default="QUINCENAL", nullable=False)  # QUINCENAL | MENSUAL
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="BORRADOR", index=True, nullable=False)  # BORRADOR | PAGADA
    total_neto_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    instrumento_id: Mapped[int | None] = mapped_column(ForeignKey("instrumentos_financieros.id"), nullable=True)
    pago_egreso_id: Mapped[int | None] = mapped_column(ForeignKey("pagos.id"), nullable=True)
    referencia_pago: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    aprobado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    fecha_pago: Mapped[date | None] = mapped_column(Date, nullable=True)
    notas: Mapped[str] = mapped_column(Text, default="", nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    instrumento = relationship("InstrumentoFinanciero")
    pago_egreso = relationship("Pago")
    aprobado_por = relationship("Usuario")
    recibos = relationship(
        "NominaRecibo",
        back_populates="periodo",
        cascade="all, delete-orphan",
    )


class NominaRecibo(Base):
    __tablename__ = "nomina_recibos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("nomina_periodos.id"), index=True, nullable=False)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("nomina_empleados.id"), index=True, nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=False)
    salario_base_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    bonos_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    otros_ingresos_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    adelantos_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    deduccion_ivss_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    deduccion_faov_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    deduccion_rpe_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    otras_deducciones_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    neto_pagar_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    comisiones_informativas_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    notas: Mapped[str] = mapped_column(Text, default="", nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    periodo = relationship("NominaPeriodo", back_populates="recibos")
    empleado = relationship("NominaEmpleado")
    usuario = relationship("Usuario")


class ConciliacionBancaria(Base):
    __tablename__ = "conciliaciones_bancarias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    instrumento_id: Mapped[int] = mapped_column(ForeignKey("instrumentos_financieros.id"), index=True, nullable=False)
    lote_codigo: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    fecha_movimiento: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    referencia: Mapped[str] = mapped_column(String(120), default="", index=True, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    monto_banco: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    tipo_movimiento: Mapped[str] = mapped_column(String(20), default="CREDITO", nullable=False)  # CREDITO | DEBITO
    estado: Mapped[str] = mapped_column(String(25), default="PENDIENTE_SISTEMA", index=True, nullable=False)  # CONCILIADO | PENDIENTE_SISTEMA | EN_TRANSITO
    pago_id: Mapped[int | None] = mapped_column(ForeignKey("pagos.id"), nullable=True)
    tesoreria_id: Mapped[int | None] = mapped_column(ForeignKey("movimientos_tesoreria.id"), nullable=True)
    conciliado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    fecha_conciliacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    instrumento = relationship("InstrumentoFinanciero")
    pago = relationship("Pago")
    tesoreria = relationship("MovimientoTesoreria")
    conciliado_por = relationship("Usuario")


class AuditoriaSistema(Base):
    """Bitácora inmutable (solo inserción) de operaciones críticas del sistema."""

    __tablename__ = "auditoria_sistema"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=True)
    usuario_nombre: Mapped[str] = mapped_column(String(150), default="", nullable=False)
    usuario_rol: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    modulo: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    accion: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    entidad_id: Mapped[str] = mapped_column(String(60), default="", index=True, nullable=False)
    detalle_anterior_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    detalle_nuevo_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    usuario = relationship("Usuario")
