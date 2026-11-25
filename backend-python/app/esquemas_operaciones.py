from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.modelos_operaciones import EstadoCotizacion, ModalidadCotizacion, TipoResolucionDevolucion


class DevolucionGarantiaCrearEntrada(BaseModel):
    venta_id: int
    equipo_origen_id: int | None = None
    equipo_destino_id: int | None = None
    tipo_resolucion: TipoResolucionDevolucion
    estado_reingreso_origen: Literal["LISTO", "POR_PREPARAR", "HOSPITAL"] = "POR_PREPARAR"
    # Para GARANTIA_COMPONENTE
    componente_afectado: str = Field(default="", max_length=160)
    articulo_repuesto_id: int | None = None
    cantidad_repuesto: int = Field(default=1, gt=0)
    # Para CAMBIO_UPGRADE / CAMBIO_DOWNGRADE / REEMBOLSO_TOTAL
    instrumento_id: int | None = None
    monto_pagado_origen: Decimal | None = Field(default=None, ge=0)
    referencia_pago: str = Field(default="", max_length=120)
    dejar_saldo_favor: bool = False
    motivo: str = Field(min_length=3, max_length=500)


class CotizacionItemEntrada(BaseModel):
    equipo_id: int | None = None
    articulo_id: int | None = None
    descripcion_libre: str = Field(default="", max_length=255)
    descripcion_servicio: str = Field(default="", max_length=500)
    cantidad: int = Field(default=1, gt=0)
    precio_pactado_usd: Decimal | None = Field(default=None, ge=0)


class CotizacionCrearEntrada(BaseModel):
    sucursal_id: int
    cliente_id: int | None = None
    asesor_id: int | None = None
    vigencia_horas: int = Field(default=48, ge=1, le=720)
    modalidad_precio: ModalidadCotizacion = ModalidadCotizacion.DIVISAS
    nota: str = Field(default="", max_length=1000)
    items: list[CotizacionItemEntrada] = Field(min_length=1)


class CotizacionEstadoEntrada(BaseModel):
    estado: EstadoCotizacion


class LiquidacionComisionCrearEntrada(BaseModel):
    usuario_id: int
    fecha_inicio: date
    fecha_fin: date
    instrumento_id: int
    referencia: str = Field(default="", max_length=120)
    notas: str = Field(default="", max_length=1000)


class CierreCajaCrearEntrada(BaseModel):
    fecha: date | None = None
    sucursal_id: int | None = None
    efectivo_declarado_usd: Decimal = Field(default=Decimal("0"), ge=0)
    observaciones: str = Field(default="", max_length=1000)


class LiquidacionAnularEntrada(BaseModel):
    motivo_anulacion: str = Field(min_length=3, max_length=500)


class TesoreriaCrearEntrada(BaseModel):
    tipo: str = Field(pattern="^(TRANSFERENCIA|CAMBIO_DIVISA)$")
    fecha: date | None = None
    instrumento_origen_id: int
    monto_origen: Decimal = Field(gt=0)
    instrumento_destino_id: int
    monto_destino: Decimal = Field(gt=0)
    tasa_pactada: Decimal = Field(default=Decimal("0"), ge=0)
    referencia: str = Field(default="", max_length=120)
    notas: str = Field(default="", max_length=1000)
