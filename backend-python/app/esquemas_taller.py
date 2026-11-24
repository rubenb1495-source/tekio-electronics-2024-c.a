from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.modelos_taller import (
    EstadoCasoPostventa,
    ResultadoPreparacion,
    TipoCasoPostventa,
    TipoPreparacion,
)


class ComponenteUsadoEntrada(BaseModel):
    articulo_id: int
    cantidad: int = Field(gt=0)


class RepuestoFaltanteEntrada(BaseModel):
    articulo_id: int | None = None
    descripcion: str = Field(min_length=2, max_length=255)
    cantidad: int = Field(default=1, gt=0)


class PreparacionCrearEntrada(BaseModel):
    equipo_id: int
    tipo: TipoPreparacion = TipoPreparacion.ESTANDAR
    pago_tecnico_usd: Decimal | None = Field(default=None, ge=0)
    componentes_usados: list[ComponenteUsadoEntrada] = Field(default_factory=list)
    resultado: ResultadoPreparacion
    repuestos_faltantes: list[RepuestoFaltanteEntrada] = Field(default_factory=list)
    nota: str = Field(default="", max_length=1000)


class RepuestoEstadoEntrada(BaseModel):
    estado: Literal["COMPRADO", "RECIBIDO", "CANCELADO"]


class CasoCrearEntrada(BaseModel):
    tipo: TipoCasoPostventa
    sucursal_id: int
    cliente_id: int | None = None
    serial_o_codigo: str = Field(default="", max_length=100)
    descripcion_equipo: str = Field(min_length=2, max_length=255)
    tipo_marca_color: str = Field(default="", max_length=160)
    accesorios_recibidos: str = Field(default="", max_length=500)
    estado_fisico: str = Field(default="", max_length=500)
    clave_equipo: str = Field(default="", max_length=100)
    falla_reportada: str = Field(min_length=3, max_length=1000)


class RepuestoPresupuestoEntrada(BaseModel):
    articulo_id: int | None = None
    descripcion: str = Field(min_length=2, max_length=255)
    cantidad: int = Field(default=1, gt=0)
    precio_promo_usd: Decimal = Field(ge=0)


class PresupuestoCrearEntrada(BaseModel):
    mano_obra_usd: Decimal = Field(ge=0)
    repuestos: list[RepuestoPresupuestoEntrada] = Field(default_factory=list)


class PresupuestoAprobarEntrada(BaseModel):
    aprobado: bool
    nota_cliente: str = Field(default="", max_length=500)


class CasoActualizarEntrada(BaseModel):
    tecnico_id: int | None = None
    diagnostico: str = Field(default="", max_length=1500)
    trabajo_realizado: str = Field(default="", max_length=1500)
    resultado_estado: EstadoCasoPostventa
    repuestos_usados: list[ComponenteUsadoEntrada] = Field(default_factory=list)
    repuestos_faltantes: list[RepuestoFaltanteEntrada] = Field(default_factory=list)
