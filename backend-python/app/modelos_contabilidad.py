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


class TipoCuentaContable(str, Enum):
    ACTIVO = "ACTIVO"
    PASIVO = "PASIVO"
    PATRIMONIO = "PATRIMONIO"
    INGRESO = "INGRESO"
    COSTO = "COSTO"
    GASTO = "GASTO"


class PlanCuenta(Base):
    __tablename__ = "plan_cuentas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AsientoContable(Base):
    __tablename__ = "asientos_contables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    fecha: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    referencia: Mapped[str] = mapped_column(String(80), index=True, default="", nullable=False)
    modulo_origen: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    entidad_id: Mapped[str] = mapped_column(String(60), index=True, default="", nullable=False)
    descripcion: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    creado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    creado_por = relationship("Usuario")
    lineas = relationship(
        "AsientoLinea",
        back_populates="asiento",
        cascade="all, delete-orphan",
    )


class AsientoLinea(Base):
    __tablename__ = "asientos_lineas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asiento_id: Mapped[int] = mapped_column(
        ForeignKey("asientos_contables.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    cuenta_id: Mapped[int] = mapped_column(
        ForeignKey("plan_cuentas.id"), index=True, nullable=False
    )
    debe_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), nullable=False
    )
    haber_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), nullable=False
    )
    descripcion: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    asiento = relationship("AsientoContable", back_populates="lineas")
    cuenta = relationship("PlanCuenta")


class ComponenteInstaladoEquipo(Base):
    __tablename__ = "equipo_componentes_instalados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    equipo_id: Mapped[int] = mapped_column(
        ForeignKey("equipos.id"), index=True, nullable=False
    )
    articulo_id: Mapped[int] = mapped_column(
        ForeignKey("catalogo_articulos.id"), index=True, nullable=False
    )
    cantidad: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    costo_unitario_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    costo_total_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    nota: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    instalado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    equipo = relationship("Equipo")
    articulo = relationship("CatalogoArticulo")
    instalado_por = relationship("Usuario")


class Prestamo(Base):
    __tablename__ = "prestamos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    acreedor: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    monto_principal_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tasa_interes_anual_pct: Mapped[Decimal] = mapped_column(
        Numeric(7, 4), default=Decimal("0.0000"), nullable=False
    )
    plazo_meses: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), default="ACTIVO", index=True, nullable=False
    )  # ACTIVO | PAGADO | ANULADO
    instrumento_desembolso_id: Mapped[int | None] = mapped_column(
        ForeignKey("instrumentos_financieros.id"), nullable=True
    )
    notas: Mapped[str] = mapped_column(Text, default="", nullable=False)
    creado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    instrumento_desembolso = relationship("InstrumentoFinanciero")
    creado_por = relationship("Usuario")
    cuotas = relationship(
        "PrestamoCuota",
        back_populates="prestamo",
        cascade="all, delete-orphan",
        order_by="PrestamoCuota.nro_cuota",
    )


class PrestamoCuota(Base):
    __tablename__ = "prestamos_cuotas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    prestamo_id: Mapped[int] = mapped_column(
        ForeignKey("prestamos.id", ondelete="CASCADE"), index=True, nullable=False
    )
    nro_cuota: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_vencimiento: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    capital_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    interes_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cuota_total_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), default="PENDIENTE", index=True, nullable=False
    )  # PENDIENTE | PAGADA
    fecha_pago: Mapped[date | None] = mapped_column(Date, nullable=True)
    pago_egreso_id: Mapped[int | None] = mapped_column(
        ForeignKey("pagos.id"), nullable=True
    )
    instrumento_pago_id: Mapped[int | None] = mapped_column(
        ForeignKey("instrumentos_financieros.id"), nullable=True
    )
    referencia_pago: Mapped[str] = mapped_column(String(120), default="", nullable=False)

    prestamo = relationship("Prestamo", back_populates="cuotas")
    pago_egreso = relationship("Pago")
    instrumento_pago = relationship("InstrumentoFinanciero")


class Socio(Base):
    __tablename__ = "socios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    porcentaje_participacion: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RepartoUtilidad(Base):
    __tablename__ = "reparto_utilidades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    periodo_mes: Mapped[str] = mapped_column(String(10), index=True, nullable=False)  # YYYY-MM
    utilidad_neta_base_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    monto_distribuido_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    fecha_pago: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    instrumento_id: Mapped[int] = mapped_column(ForeignKey("instrumentos_financieros.id"), nullable=False)
    pago_egreso_id: Mapped[int | None] = mapped_column(ForeignKey("pagos.id"), nullable=True)
    notas: Mapped[str] = mapped_column(Text, default="", nullable=False)
    creado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    instrumento = relationship("InstrumentoFinanciero")
    pago_egreso = relationship("Pago")
    creado_por = relationship("Usuario")
    detalles = relationship(
        "RepartoUtilidadDetalle",
        back_populates="reparto",
        cascade="all, delete-orphan",
    )


class RepartoUtilidadDetalle(Base):
    __tablename__ = "reparto_utilidades_detalle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    reparto_id: Mapped[int] = mapped_column(
        ForeignKey("reparto_utilidades.id", ondelete="CASCADE"), index=True, nullable=False
    )
    socio_id: Mapped[int] = mapped_column(ForeignKey("socios.id"), index=True, nullable=False)
    porcentaje_aplicado: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    monto_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    referencia: Mapped[str] = mapped_column(String(120), default="", nullable=False)

    reparto = relationship("RepartoUtilidad", back_populates="detalles")
    socio = relationship("Socio")
