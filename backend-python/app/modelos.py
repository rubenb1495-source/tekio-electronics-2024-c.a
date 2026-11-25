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


class EstadoSucursal(str, Enum):
    ACTIVA = "ACTIVA"
    CERRADA = "CERRADA"


class RolUsuario(str, Enum):
    DIRECCION = "DIRECCION"
    ADMINISTRACION = "ADMINISTRACION"
    LOGISTICA = "LOGISTICA"
    LIDER = "LIDER"
    ASESORA = "ASESORA"
    TECNICO = "TECNICO"


class OrigenTasa(str, Enum):
    AUTOMATICO = "AUTOMATICO"
    MANUAL = "MANUAL"


class TipoArticulo(str, Enum):
    EQUIPO = "EQUIPO"
    COMPONENTE = "COMPONENTE"
    ACCESORIO = "ACCESORIO"
    SERVICIO = "SERVICIO"


class Sucursal(Base):
    __tablename__ = "sucursales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    direccion: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default=EstadoSucursal.ACTIVA.value, nullable=False)
    fecha_cierre: Mapped[date | None] = mapped_column(Date, nullable=True)

    usuarios: Mapped[list["Usuario"]] = relationship("Usuario", back_populates="sucursal")


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    correo: Mapped[str | None] = mapped_column(String(180), unique=True, index=True, nullable=True)
    clave_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rol: Mapped[str] = mapped_column(String(30), nullable=False)
    modalidad: Mapped[str] = mapped_column(String(20), default="PRESENCIAL", nullable=False)
    telefono: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    cedula: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    tiene_acceso: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sucursal_id: Mapped[int | None] = mapped_column(ForeignKey("sucursales.id"), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    motivo_estado: Mapped[str | None] = mapped_column(String(255), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    sucursal: Mapped[Sucursal | None] = relationship("Sucursal", back_populates="usuarios")


class TasaDiaria(Base):
    __tablename__ = "tasas_diarias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    fecha: Mapped[date] = mapped_column(Date, unique=True, index=True, nullable=False)
    tasa_bcv: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    tasa_usdt: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    recargo_porcentaje: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    origen: Mapped[str] = mapped_column(String(20), default=OrigenTasa.MANUAL.value, nullable=False)
    publicado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    nota: Mapped[str] = mapped_column(Text, default="", nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    publicado_por: Mapped[Usuario | None] = relationship("Usuario")


class CatalogoArticulo(Base):
    __tablename__ = "catalogo_articulos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sku: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    categoria: Mapped[str] = mapped_column(String(100), default="General", nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    precios: Mapped[list["CatalogoPrecio"]] = relationship(
        "CatalogoPrecio",
        back_populates="articulo",
        order_by="desc(CatalogoPrecio.fecha_vigencia), desc(CatalogoPrecio.id)",
    )


class CatalogoPrecio(Base):
    __tablename__ = "catalogo_precios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    articulo_id: Mapped[int] = mapped_column(ForeignKey("catalogo_articulos.id"), index=True, nullable=False)
    precio_promo_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    precio_regular_fijo_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    costo_referencia_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    fecha_vigencia: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    creado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    articulo: Mapped[CatalogoArticulo] = relationship("CatalogoArticulo", back_populates="precios")
    creado_por: Mapped[Usuario | None] = relationship("Usuario")
