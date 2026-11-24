from __future__ import annotations

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
