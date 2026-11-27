from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.base_datos import Base


class TipoTercero(str, Enum):
    PROVEEDOR = "PROVEEDOR"
    CLIENTE = "CLIENTE"
    AMBOS = "AMBOS"


class OrigenCompra(str, Enum):
    IMPORTACION = "IMPORTACION"
    INTERNACIONAL = "INTERNACIONAL"
    NACIONAL = "NACIONAL"
    CONSIGNACION = "CONSIGNACION"
    INVENTARIO_EXISTENTE = "INVENTARIO_EXISTENTE"
    PARTE_DE_PAGO = "PARTE_DE_PAGO"


class EstadoCompra(str, Enum):
    PENDIENTE = "PENDIENTE"
    RECIBIDA_PARCIAL = "RECIBIDA_PARCIAL"
    RECIBIDA = "RECIBIDA"


class ModalidadGuia(str, Enum):
    AEREO = "AEREO"
    MARITIMO = "MARITIMO"


class EstadoGuia(str, Enum):
    EN_TRANSITO = "EN_TRANSITO"
    RECIBIDA = "RECIBIDA"


class EstadoEquipo(str, Enum):
    EN_TRANSITO = "EN_TRANSITO"
    POR_PREPARAR = "POR_PREPARAR"
    EN_PREPARACION = "EN_PREPARACION"
    LISTO = "LISTO"
    HOSPITAL = "HOSPITAL"
    RESERVADO = "RESERVADO"
    CEMENTERIO = "CEMENTERIO"
    VENDIDO = "VENDIDO"


class TipoMovimientoInventario(str, Enum):
    COMPRA = "COMPRA"
    TRASLADO_SALIDA = "TRASLADO_SALIDA"
    TRASLADO_ENTRADA = "TRASLADO_ENTRADA"
    AJUSTE_POSITIVO = "AJUSTE_POSITIVO"
    AJUSTE_NEGATIVO = "AJUSTE_NEGATIVO"
    BAJA = "BAJA"
    TALLER = "TALLER"
    VENTA = "VENTA"


class EstadoTraslado(str, Enum):
    EN_TRANSITO = "EN_TRANSITO"
    RECIBIDO = "RECIBIDO"
    ANULADO = "ANULADO"


class TipoAjusteInventario(str, Enum):
    BAJA_EQUIPO = "BAJA_EQUIPO"
    CORRECCION_MAS = "CORRECCION_MAS"
    CORRECCION_MENOS = "CORRECCION_MENOS"


class EstadoAjusteInventario(str, Enum):
    PENDIENTE = "PENDIENTE"
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"


guias_compras = Table(
    "guias_compras",
    Base.metadata,
    Column("guia_id", ForeignKey("guias_importacion.id"), primary_key=True),
    Column("compra_id", ForeignKey("compras.id"), primary_key=True),
)


class TipoPersona(str, Enum):
    NATURAL = "NATURAL"
    JURIDICO = "JURIDICO"


class TipoDocumento(str, Enum):
    V = "V"
    E = "E"
    J = "J"
    G = "G"
    P = "P"


class Tercero(Base):
    __tablename__ = "terceros"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(20), default=TipoTercero.PROVEEDOR.value, nullable=False)
    tipo_persona: Mapped[str] = mapped_column(String(20), default=TipoPersona.NATURAL.value, nullable=False)
    tipo_documento: Mapped[str] = mapped_column(String(5), default="", nullable=False)
    documento: Mapped[str] = mapped_column(String(40), default="", nullable=False, index=True)
    rif_cedula: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    telefono: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    direccion: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    saldo_favor_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Compra(Base):
    __tablename__ = "compras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    numero_compra: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    origen: Mapped[str] = mapped_column(String(30), nullable=False)
    tipo_compra: Mapped[str] = mapped_column(String(20), default="NACIONAL", nullable=False)
    moneda: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("terceros.id"), nullable=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fecha_vencimiento: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    saldo_pendiente_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    factura_orden: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    numero_guia: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    monto_mercancia_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    envio_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    aduana_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    otros_gastos_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    llega_preparada: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cantidad_esperada: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estado: Mapped[str] = mapped_column(String(25), default=EstadoCompra.PENDIENTE.value, nullable=False)
    nota: Mapped[str] = mapped_column(Text, default="", nullable=False)
    creado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    proveedor = relationship("Tercero")
    creado_por = relationship("Usuario")
    guias = relationship("GuiaImportacion", secondary=guias_compras, back_populates="compras")
    equipos = relationship("Equipo", back_populates="compra")
    componentes = relationship("CompraComponente", back_populates="compra")
    trackings = relationship("CompraTracking", back_populates="compra", cascade="all, delete-orphan")


class CompraTracking(Base):
    __tablename__ = "compras_trackings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    compra_id: Mapped[int] = mapped_column(ForeignKey("compras.id", ondelete="CASCADE"), index=True, nullable=False)
    numero_tracking: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    courier: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    estado: Mapped[str] = mapped_column(String(30), default="EN_ORIGEN", index=True, nullable=False)
    peso_lb: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"), nullable=False)
    fecha_estimada: Mapped[date | None] = mapped_column(Date, nullable=True)
    notas: Mapped[str] = mapped_column(Text, default="", nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    compra = relationship("Compra", back_populates="trackings")


class CompraComponente(Base):
    __tablename__ = "compras_componentes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    compra_id: Mapped[int] = mapped_column(ForeignKey("compras.id"), index=True, nullable=False)
    articulo_id: Mapped[int] = mapped_column(ForeignKey("catalogo_articulos.id"), nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    cantidad_recibida: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    costo_unitario_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    costo_flete_unitario_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)

    compra = relationship("Compra", back_populates="componentes")
    articulo = relationship("CatalogoArticulo")


class GuiaImportacion(Base):
    __tablename__ = "guias_importacion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    numero_guia: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    casillero: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    modalidad: Mapped[str] = mapped_column(String(20), default=ModalidadGuia.AEREO.value, nullable=False)
    fecha_salida: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_llegada_estimada: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_llegada_real: Mapped[date | None] = mapped_column(Date, nullable=True)
    flete_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    otros_gastos_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default=EstadoGuia.EN_TRANSITO.value, nullable=False)
    nota: Mapped[str] = mapped_column(Text, default="", nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    compras = relationship("Compra", secondary=guias_compras, back_populates="guias")


class Equipo(Base):
    __tablename__ = "equipos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    serial: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("catalogo_articulos.id"), nullable=True)
    compra_id: Mapped[int | None] = mapped_column(ForeignKey("compras.id"), index=True, nullable=True)
    guia_id: Mapped[int | None] = mapped_column(ForeignKey("guias_importacion.id"), index=True, nullable=True)
    modelo: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    configuracion: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    categoria: Mapped[str] = mapped_column(String(100), default="Laptop", nullable=False)
    ubicacion_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id"), index=True, nullable=False)
    estado: Mapped[str] = mapped_column(String(25), default=EstadoEquipo.EN_TRANSITO.value, nullable=False, index=True)
    estado_previo_traslado: Mapped[str | None] = mapped_column(String(25), nullable=True)
    costo_compra_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    costo_flete_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    costo_taller_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    precio_promo_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    es_consignacion: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    proveedor_consignacion_id: Mapped[int | None] = mapped_column(ForeignKey("terceros.id"), nullable=True)
    recibido_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    verificado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    fecha_recepcion: Mapped[date | None] = mapped_column(Date, nullable=True)
    condicion_llegada: Mapped[str] = mapped_column(String(30), default="BUENO", nullable=False)
    incluye_cargador: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    observaciones_llegada: Mapped[str] = mapped_column(Text, default="", nullable=False)
    nota: Mapped[str] = mapped_column(Text, default="", nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    articulo = relationship("CatalogoArticulo")
    compra = relationship("Compra", back_populates="equipos")
    guia = relationship("GuiaImportacion")
    ubicacion = relationship("Sucursal")
    proveedor_consignacion = relationship("Tercero", foreign_keys=[proveedor_consignacion_id])
    recibido_por = relationship("Usuario", foreign_keys=[recibido_por_id])
    verificado_por = relationship("Usuario", foreign_keys=[verificado_por_id])


class MovimientoInventario(Base):
    __tablename__ = "movimientos_inventario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("catalogo_articulos.id"), index=True, nullable=True)
    equipo_id: Mapped[int | None] = mapped_column(ForeignKey("equipos.id"), index=True, nullable=True)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id"), index=True, nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    costo_unitario_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    documento_ref: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    motivo: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)

    articulo = relationship("CatalogoArticulo")
    equipo = relationship("Equipo")
    sucursal = relationship("Sucursal")
    usuario = relationship("Usuario")


class Traslado(Base):
    __tablename__ = "traslados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    numero_traslado: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    origen_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id"), nullable=False)
    destino_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id"), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default=EstadoTraslado.EN_TRANSITO.value, nullable=False, index=True)
    enviado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    recibido_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    fecha_envio: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    fecha_recepcion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    nota: Mapped[str] = mapped_column(Text, default="", nullable=False)
    nota_recepcion: Mapped[str] = mapped_column(Text, default="", nullable=False)
    motivo_anulacion: Mapped[str] = mapped_column(Text, default="", nullable=False)

    origen = relationship("Sucursal", foreign_keys=[origen_id])
    destino = relationship("Sucursal", foreign_keys=[destino_id])
    enviado_por = relationship("Usuario", foreign_keys=[enviado_por_id])
    recibido_por = relationship("Usuario", foreign_keys=[recibido_por_id])
    detalles = relationship("TrasladoDetalle", back_populates="traslado", cascade="all, delete-orphan")


class TrasladoDetalle(Base):
    __tablename__ = "traslados_detalle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    traslado_id: Mapped[int] = mapped_column(ForeignKey("traslados.id"), index=True, nullable=False)
    equipo_id: Mapped[int | None] = mapped_column(ForeignKey("equipos.id"), nullable=True)
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("catalogo_articulos.id"), nullable=True)
    cantidad: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    traslado = relationship("Traslado", back_populates="detalles")
    equipo = relationship("Equipo")
    articulo = relationship("CatalogoArticulo")


class AjusteInventario(Base):
    __tablename__ = "ajustes_inventario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    numero_ajuste: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(25), nullable=False)
    equipo_id: Mapped[int | None] = mapped_column(ForeignKey("equipos.id"), nullable=True)
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("catalogo_articulos.id"), nullable=True)
    cantidad: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    motivo: Mapped[str] = mapped_column(String(255), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default=EstadoAjusteInventario.PENDIENTE.value, nullable=False, index=True)
    solicitado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    revisado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    fecha_revision: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comentario_revision: Mapped[str] = mapped_column(Text, default="", nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    sucursal = relationship("Sucursal")
    equipo = relationship("Equipo")
    articulo = relationship("CatalogoArticulo")
    solicitado_por = relationship("Usuario", foreign_keys=[solicitado_por_id])
    revisado_por = relationship("Usuario", foreign_keys=[revisado_por_id])
