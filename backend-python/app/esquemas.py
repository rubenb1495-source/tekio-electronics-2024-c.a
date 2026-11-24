from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modelos import EstadoSucursal, OrigenTasa, RolUsuario, TipoArticulo


def normalizar_sku(valor: str) -> str:
    """Normaliza SKU: elimina espacios extremos, convierte a MAYÚSCULAS y reemplaza espacios internos por guiones."""
    limpio = re.sub(r"\s+", "-", valor.strip()).upper()
    if not limpio:
        raise ValueError("El SKU no puede estar vacío.")
    return limpio


# ---------------- Sucursales ----------------

class SucursalSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    direccion: str
    estado: EstadoSucursal
    fecha_cierre: date | None = None


# ---------------- Autenticación y Usuarios ----------------

class LoginEntrada(BaseModel):
    correo: EmailStr
    clave: str = Field(min_length=1)


class UsuarioSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    correo: str
    rol: RolUsuario
    activo: bool
    motivo_estado: str | None = None
    creado_en: datetime
    sucursal: SucursalSalida | None = None


class LoginSalida(BaseModel):
    token: str
    usuario: UsuarioSalida


class UsuarioCrearEntrada(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    correo: EmailStr
    clave: str = Field(min_length=6, max_length=128)
    rol: RolUsuario
    sucursal_id: int | None = None

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, valor: str) -> str:
        limpio = valor.strip()
        if len(limpio) < 2:
            raise ValueError("El nombre debe tener al menos 2 caracteres.")
        return limpio


class UsuarioEstadoEntrada(BaseModel):
    activo: bool
    motivo: str = Field(min_length=3, max_length=255)

    @field_validator("motivo")
    @classmethod
    def limpiar_motivo(cls, valor: str) -> str:
        limpio = valor.strip()
        if len(limpio) < 3:
            raise ValueError("Debes indicar un motivo de al menos 3 caracteres.")
        return limpio


# ---------------- Tasas Diarias ----------------

class TasaCrearEntrada(BaseModel):
    fecha: date
    tasa_bcv: Decimal = Field(gt=0)
    tasa_usdt: Decimal = Field(gt=0)
    recargo_porcentaje: Decimal | None = Field(default=None, ge=0, le=500)
    nota: str = Field(default="", max_length=500)


class TasaActualizarHoyEntrada(BaseModel):
    tasa_bcv: Decimal | None = Field(default=None, gt=0)
    tasa_usdt: Decimal | None = Field(default=None, gt=0)
    recargo_porcentaje: Decimal | None = Field(default=None, ge=0, le=500)
    nota: str | None = Field(default=None, max_length=500)


class TasaSalida(BaseModel):
    id: int
    fecha: date
    tasa_bcv: float
    tasa_usdt: float
    recargo_porcentaje: float
    brecha_porcentaje: float
    origen: OrigenTasa
    nota: str
    publicado_por: str | None = None
    actualizado_en: datetime


class TasaHoySalida(BaseModel):
    fecha: date
    permite_bolivares: bool
    alerta: str | None = None
    tasa_bcv: float | None = None
    tasa_usdt: float | None = None
    recargo_porcentaje: float | None = None
    brecha_porcentaje: float | None = None
    origen: OrigenTasa | None = None
    nota: str = ""
    actualizado_en: datetime | None = None


class TasasPaginadasSalida(BaseModel):
    elementos: list[TasaSalida]
    total: int
    pagina: int
    por_pagina: int


# ---------------- Catálogo y Precios ----------------

class ArticuloCrearEntrada(BaseModel):
    sku: str = Field(min_length=2, max_length=80)
    descripcion: str = Field(min_length=2, max_length=255)
    tipo: TipoArticulo
    categoria: str = Field(default="General", min_length=1, max_length=100)
    precio_promo_usd: Decimal = Field(ge=0)
    precio_regular_fijo_usd: Decimal | None = Field(default=None, ge=0)
    costo_referencia_usd: Decimal | None = Field(default=None, ge=0)
    fecha_vigencia: date | None = None

    @field_validator("sku")
    @classmethod
    def validar_sku(cls, valor: str) -> str:
        return normalizar_sku(valor)

    @field_validator("descripcion", "categoria")
    @classmethod
    def limpiar_texto(cls, valor: str) -> str:
        return valor.strip()


class PrecioCrearEntrada(BaseModel):
    precio_promo_usd: Decimal = Field(ge=0)
    precio_regular_fijo_usd: Decimal | None = Field(default=None, ge=0)
    costo_referencia_usd: Decimal | None = Field(default=None, ge=0)
    fecha_vigencia: date


class ArticuloEstadoEntrada(BaseModel):
    activo: bool


class PrecioHistorialPublicoSalida(BaseModel):
    id: int
    precio_promo_usd: float
    precio_regular_fijo_usd: float | None = None
    fecha_vigencia: date
    creado_por: str | None = None
    creado_en: datetime


class PrecioHistorialConCostoSalida(PrecioHistorialPublicoSalida):
    costo_referencia_usd: float | None = None


class ArticuloCatalogoPublicoSalida(BaseModel):
    id: int
    sku: str
    descripcion: str
    tipo: TipoArticulo
    categoria: str
    activo: bool
    precio_promo_usd: float
    precio_regular_fijo_usd: float | None = None
    precio_regular_usd: float
    precio_regular_bs: float | None = None
    fecha_vigencia: date | None = None
    creado_en: datetime


class ArticuloCatalogoConCostoSalida(ArticuloCatalogoPublicoSalida):
    costo_referencia_usd: float | None = None


class CatalogoPaginadoPublicoSalida(BaseModel):
    elementos: list[ArticuloCatalogoPublicoSalida]
    total: int
    pagina: int
    por_pagina: int
    recargo_aplicado_porcentaje: float
    tasa_bcv_aplicada: float | None = None


class CatalogoPaginadoConCostoSalida(BaseModel):
    elementos: list[ArticuloCatalogoConCostoSalida]
    total: int
    pagina: int
    por_pagina: int
    recargo_aplicado_porcentaje: float
    tasa_bcv_aplicada: float | None = None
