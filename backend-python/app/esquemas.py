from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.validacion import ModeloEntradaLimpio
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
    telefono: str = ""
    tipo: str = "TIENDA"
    estado: EstadoSucursal
    fecha_cierre: date | None = None


# ---------------- Autenticación y Usuarios ----------------

class LoginEntrada(ModeloEntradaLimpio):
    identificador: str | None = Field(default=None, max_length=180)
    usuario: str | None = Field(default=None, max_length=180)
    correo: str | None = Field(default=None, max_length=180)
    email: str | None = Field(default=None, max_length=180)
    username: str | None = Field(default=None, max_length=180)
    clave: str | None = Field(default=None, min_length=1)
    password: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validar_identificador(self) -> "LoginEntrada":
        ident = (
            self.usuario
            or self.identificador
            or self.username
            or self.correo
            or self.email
            or ""
        ).strip()
        if not ident:
            raise ValueError("Debes ingresar tu nombre de usuario o correo electrónico.")
        pwd = self.clave or self.password or ""
        if not pwd:
            raise ValueError("Debes ingresar tu contraseña.")
        self.identificador = ident.lower()
        self.clave = pwd
        return self


class CambiarPasswordEntrada(ModeloEntradaLimpio):
    clave_actual: str | None = Field(default=None, min_length=1)
    password_actual: str | None = Field(default=None, min_length=1)
    clave_nueva: str | None = Field(default=None, max_length=128)
    nueva_clave: str | None = Field(default=None, max_length=128)
    password_nuevo: str | None = Field(default=None, max_length=128)
    confirmar_clave: str | None = Field(default=None, max_length=128)
    confirmar_password: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validar_claves(self) -> "CambiarPasswordEntrada":
        actual = self.clave_actual or self.password_actual or ""
        if not actual:
            raise ValueError("Debes ingresar tu contraseña actual.")
        nueva = self.nueva_clave or self.clave_nueva or self.password_nuevo or ""
        if len(nueva) < 8:
            raise ValueError("La nueva contraseña debe tener al menos 8 caracteres.")
        confirmacion = (
            self.confirmar_clave
            if self.confirmar_clave is not None
            else self.confirmar_password
        )
        if confirmacion is not None and nueva != confirmacion:
            raise ValueError("La confirmación no coincide con la nueva contraseña.")
        self.clave_actual = actual
        self.clave_nueva = nueva
        return self


class DesbloquearUsuarioEntrada(ModeloEntradaLimpio):
    nueva_clave_temporal: str | None = Field(default=None, min_length=6, max_length=128)


class AccesoTemporalSalida(BaseModel):
    usuario_id: int
    nombre: str
    username: str
    email: str | None = None
    rol: RolUsuario
    sucursal: str
    telefono: str = ""
    password_temporal: str
    url_app: str


class UsuarioSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    username: str | None = None
    correo: str | None = None
    rol: RolUsuario
    modalidad: str = "PRESENCIAL"
    telefono: str = ""
    cedula: str = ""
    tiene_acceso: bool = True
    tiene_acceso_sistema: bool = True
    intentos_fallidos_login: int = 0
    cuenta_bloqueada: bool = False
    bloqueado_hasta: datetime | None = None
    bloqueado_en: datetime | None = None
    activo: bool
    motivo_estado: str | None = None
    creado_en: datetime
    sucursal: SucursalSalida | None = None
    acceso_compartir: AccesoTemporalSalida | None = None


class LoginSalida(BaseModel):
    token: str
    usuario: UsuarioSalida


class UsuarioCrearEntrada(ModeloEntradaLimpio):
    nombre: str = Field(min_length=2, max_length=150)
    username: str | None = Field(default=None, max_length=80)
    rol: RolUsuario
    modalidad: Literal["PRESENCIAL", "ONLINE"] = "PRESENCIAL"
    telefono: str = Field(default="", max_length=40)
    cedula: str = Field(default="", max_length=40)
    tiene_acceso: bool | None = None
    tiene_acceso_sistema: bool | None = None
    correo: EmailStr | None = None
    email: EmailStr | None = None
    clave: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=128)
    sucursal_id: int | None = None

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, valor: str) -> str:
        limpio = valor.strip()
        if len(limpio) < 2:
            raise ValueError("El nombre debe tener al menos 2 caracteres.")
        return limpio

    @field_validator("correo", "email", mode="before")
    @classmethod
    def vacio_a_none_correo(cls, valor: object) -> object:
        if isinstance(valor, str) and not valor.strip():
            return None
        return valor

    @field_validator("clave", "password", mode="before")
    @classmethod
    def vacio_a_none_clave(cls, valor: object) -> object:
        if isinstance(valor, str) and not valor.strip():
            return None
        return valor

    @model_validator(mode="after")
    def validar_acceso_sistema(self) -> "UsuarioCrearEntrada":
        if self.correo is None and self.email is not None:
            self.correo = self.email
        if self.clave is None and self.password is not None:
            self.clave = self.password
        acceso_explicito = (
            self.tiene_acceso
            if self.tiene_acceso is not None
            else self.tiene_acceso_sistema
        )
        # Compatibilidad: si no se envía bandera, se infiere True cuando envían correo/clave y False si no.
        acceso = (
            acceso_explicito
            if acceso_explicito is not None
            else bool(self.correo or self.clave)
        )
        self.tiene_acceso = acceso
        self.tiene_acceso_sistema = acceso
        if acceso:
            if not self.correo and not self.username:
                raise ValueError("Debes indicar un nombre de usuario o correo electrónico cuando el colaborador tiene acceso al sistema.")
            if not self.clave or len(self.clave) < 6:
                raise ValueError("La contraseña es obligatoria (mínimo 6 caracteres) cuando tiene acceso al sistema.")
        else:
            self.username = None
            self.correo = None
            self.clave = None
        return self


class UsuarioActualizarEntrada(ModeloEntradaLimpio):
    nombre: str = Field(min_length=2, max_length=150)
    username: str | None = Field(default=None, max_length=80)
    rol: RolUsuario
    modalidad: Literal["PRESENCIAL", "ONLINE"] = "PRESENCIAL"
    telefono: str = Field(default="", max_length=40)
    cedula: str = Field(default="", max_length=40)
    tiene_acceso: bool | None = None
    tiene_acceso_sistema: bool | None = None
    correo: EmailStr | None = None
    email: EmailStr | None = None
    clave: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=128)
    sucursal_id: int | None = None

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, valor: str) -> str:
        limpio = valor.strip()
        if len(limpio) < 2:
            raise ValueError("El nombre debe tener al menos 2 caracteres.")
        return limpio

    @field_validator("correo", "email", mode="before")
    @classmethod
    def vacio_a_none_correo(cls, valor: object) -> object:
        if isinstance(valor, str) and not valor.strip():
            return None
        return valor

    @field_validator("clave", "password", mode="before")
    @classmethod
    def vacio_a_none_clave(cls, valor: object) -> object:
        if isinstance(valor, str) and not valor.strip():
            return None
        return valor

    @model_validator(mode="after")
    def validar_acceso_edicion(self) -> "UsuarioActualizarEntrada":
        if self.correo is None and self.email is not None:
            self.correo = self.email
        if self.clave is None and self.password is not None:
            self.clave = self.password
        acceso = (
            self.tiene_acceso
            if self.tiene_acceso is not None
            else (self.tiene_acceso_sistema if self.tiene_acceso_sistema is not None else False)
        )
        self.tiene_acceso = acceso
        self.tiene_acceso_sistema = acceso
        if acceso:
            if not self.correo and not self.username:
                raise ValueError("Debes indicar un nombre de usuario o correo electrónico cuando el colaborador tiene acceso al sistema.")
            if self.clave is not None and len(self.clave) < 6:
                raise ValueError("La contraseña debe tener al menos 6 caracteres.")
        else:
            self.username = None
            self.correo = None
            self.clave = None
        return self


class UsuarioEstadoEntrada(ModeloEntradaLimpio):
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

class TasaCrearEntrada(ModeloEntradaLimpio):
    fecha: date
    tasa_bcv: Decimal = Field(gt=0)
    tasa_usdt: Decimal = Field(gt=0)
    recargo_porcentaje: Decimal | None = Field(default=None, ge=0, le=500)
    nota: str = Field(default="", max_length=500)


class TasaActualizarHoyEntrada(ModeloEntradaLimpio):
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

class ArticuloCrearEntrada(ModeloEntradaLimpio):
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


class PrecioCrearEntrada(ModeloEntradaLimpio):
    precio_promo_usd: Decimal = Field(ge=0)
    precio_regular_fijo_usd: Decimal | None = Field(default=None, ge=0)
    costo_referencia_usd: Decimal | None = Field(default=None, ge=0)
    fecha_vigencia: date


class ArticuloEstadoEntrada(ModeloEntradaLimpio):
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
