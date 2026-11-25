from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modelos_logistica import (
    EstadoAjusteInventario,
    EstadoCompra,
    EstadoEquipo,
    EstadoGuia,
    EstadoTraslado,
    ModalidadGuia,
    OrigenCompra,
    TipoAjusteInventario,
    TipoDocumento,
    TipoPersona,
    TipoTercero,
)


def normalizar_serial(valor: str) -> str:
    """Normaliza serial a MAYÚSCULAS sin espacios."""
    limpio = re.sub(r"\s+", "", valor.strip()).upper()
    if not limpio:
        raise ValueError("El número de serial no puede estar vacío.")
    return limpio


def normalizar_documento(valor: str) -> str:
    """Normaliza cédula o RIF sin espacios y en mayúsculas."""
    limpio = re.sub(r"\s+", "", valor.strip()).upper()
    limpio = re.sub(r"^[VEJGP]-?", "", limpio)
    return limpio


# ---------------- Terceros ----------------

class TerceroCrearEntrada(BaseModel):
    nombre: str = Field(min_length=2, max_length=160)
    tipo: TipoTercero = TipoTercero.PROVEEDOR
    tipo_persona: TipoPersona = TipoPersona.NATURAL
    tipo_documento: TipoDocumento | None = None
    documento: str = Field(default="", max_length=40)
    rif_cedula: str = Field(default="", max_length=40)
    telefono: str = Field(default="", max_length=40)
    direccion: str = Field(default="", max_length=255)


class ClienteRapidoCrearEntrada(BaseModel):
    tipo_persona: TipoPersona = TipoPersona.NATURAL
    tipo_documento: TipoDocumento
    documento: str = Field(min_length=4, max_length=40)
    nombre: str = Field(min_length=2, max_length=160)
    telefono: str = Field(default="", max_length=40)
    direccion: str = Field(default="", max_length=255)

    @field_validator("documento")
    @classmethod
    def limpiar_documento(cls, valor: str) -> str:
        limpio = normalizar_documento(valor)
        if len(limpio) < 4:
            raise ValueError("El número de cédula o RIF debe tener al menos 4 caracteres.")
        return limpio


class TerceroSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    tipo: TipoTercero
    tipo_persona: str = "NATURAL"
    tipo_documento: str = ""
    documento: str = ""
    rif_cedula: str
    telefono: str
    direccion: str = ""
    activo: bool


# ---------------- Compras ----------------

class EquipoCompraEntrada(BaseModel):
    serial: str = Field(min_length=2, max_length=100)
    articulo_id: int | None = None
    modelo: str = Field(default="", max_length=160)
    configuracion: str = Field(default="", max_length=255)
    categoria: str = Field(default="Laptop", max_length=100)
    ubicacion_id: int | None = None
    estado: EstadoEquipo | None = None
    costo_compra_usd: Decimal | None = Field(default=None, ge=0)
    precio_promo_usd: Decimal = Field(default=Decimal("0"), ge=0)
    nota: str = Field(default="", max_length=500)

    @field_validator("serial")
    @classmethod
    def limpiar_serial(cls, valor: str) -> str:
        return normalizar_serial(valor)


class ComponenteCompraEntrada(BaseModel):
    articulo_id: int
    cantidad: int = Field(gt=0)
    costo_unitario_usd: Decimal | None = Field(default=None, ge=0)
    ubicacion_id: int | None = None


class CompraCrearEntrada(BaseModel):
    origen: OrigenCompra
    tipo_compra: str | None = Field(default=None, max_length=20)
    moneda: str = Field(default="USD", max_length=10)
    proveedor_id: int | None = None
    fecha: date
    factura_orden: str = Field(default="", max_length=100)
    numero_guia: str = Field(default="", max_length=100)
    monto_mercancia_usd: Decimal = Field(default=Decimal("0"), ge=0)
    envio_usd: Decimal = Field(default=Decimal("0"), ge=0)
    aduana_usd: Decimal = Field(default=Decimal("0"), ge=0)
    otros_gastos_usd: Decimal = Field(default=Decimal("0"), ge=0)
    llega_preparada: bool = False
    es_consignacion: bool = False
    nota: str = Field(default="", max_length=1000)
    equipos: list[EquipoCompraEntrada] = Field(default_factory=list)
    componentes: list[ComponenteCompraEntrada] = Field(default_factory=list)


class FilaValidacionArchivo(BaseModel):
    fila: int
    serial: str | None = None
    sku: str | None = None
    modelo: str = ""
    configuracion: str = ""
    categoria: str = "Laptop"
    cantidad: int = 1
    costo_compra_usd: float | None = None
    precio_promo_usd: float = 0.0
    ubicacion: str | None = None
    estado: str | None = None
    valida: bool
    errores: list[str] = Field(default_factory=list)


class ValidacionArchivoSalida(BaseModel):
    nombre_archivo: str
    total_filas: int
    filas_validas: int
    filas_con_error: int
    puede_confirmar: bool
    filas: list[FilaValidacionArchivo]


# ---------------- Guías y Recepción ----------------

class GuiaCrearEntrada(BaseModel):
    numero_guia: str = Field(min_length=2, max_length=80)
    casillero: str = Field(default="", max_length=100)
    modalidad: ModalidadGuia = ModalidadGuia.AEREO
    fecha_salida: date | None = None
    fecha_llegada_estimada: date | None = None
    flete_usd: Decimal = Field(default=Decimal("0"), ge=0)
    otros_gastos_usd: Decimal = Field(default=Decimal("0"), ge=0)
    compras_ids: list[int] = Field(min_length=1)
    nota: str = Field(default="", max_length=1000)

    @field_validator("numero_guia")
    @classmethod
    def limpiar_numero_guia(cls, valor: str) -> str:
        return valor.strip().upper()


class ComponenteRecibidoEntrada(BaseModel):
    articulo_id: int
    cantidad: int = Field(gt=0)


class GuiaRecibirEntrada(BaseModel):
    fecha_llegada_real: date
    verificado_por_id: int
    seriales_recibidos: list[str] = Field(default_factory=list)
    componentes_recibidos: list[ComponenteRecibidoEntrada] = Field(default_factory=list)

    @field_validator("seriales_recibidos")
    @classmethod
    def limpiar_seriales(cls, valores: list[str]) -> list[str]:
        return [normalizar_serial(s) for s in valores if s and s.strip()]


# ---------------- Traslados ----------------

class ComponenteTrasladoEntrada(BaseModel):
    articulo_id: int
    cantidad: int = Field(gt=0)


class TrasladoCrearEntrada(BaseModel):
    origen_id: int
    destino_id: int
    equipos_ids: list[int] = Field(default_factory=list)
    componentes: list[ComponenteTrasladoEntrada] = Field(default_factory=list)
    nota: str = Field(default="", max_length=1000)


class TrasladoConfirmarEntrada(BaseModel):
    nota_recepcion: str = Field(default="", max_length=500)


class TrasladoAnularEntrada(BaseModel):
    motivo: str = Field(min_length=3, max_length=500)


# ---------------- Ajustes ----------------

class AjusteCrearEntrada(BaseModel):
    sucursal_id: int
    tipo: TipoAjusteInventario
    equipo_id: int | None = None
    articulo_id: int | None = None
    cantidad: int = Field(default=1, gt=0)
    motivo: str = Field(min_length=3, max_length=255)


class AjusteRevisarEntrada(BaseModel):
    decision: Literal["APROBADO", "RECHAZADO"]
    comentario: str = Field(default="", max_length=500)


class EquipoEstadoMasivoEntrada(BaseModel):
    equipo_ids: list[int] = Field(min_length=1)
    nuevo_estado: EstadoEquipo
    motivo: str = Field(default="", max_length=300)
