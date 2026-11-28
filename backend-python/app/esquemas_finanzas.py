from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import Field

from app.core.validacion import ModeloEntradaLimpio as BaseModel
from app.modelos_finanzas import EstadoReingresoNC


class ItemVentaEntrada(BaseModel):
    equipo_id: int | None = None
    articulo_id: int | None = None
    cantidad: int = Field(default=1, gt=0)
    precio_pactado_usd: Decimal | None = Field(default=None, ge=0)
    descripcion_servicio: str = Field(default="", max_length=500)


class PagoVentaEntrada(BaseModel):
    instrumento_id: int
    monto_moneda_origen: Decimal = Field(gt=0)
    referencia: str = Field(default="", max_length=120)
    # Obligatorios solo cuando el instrumento es "Equipo como parte de pago"
    parte_pago_serial: str | None = None
    parte_pago_modelo: str | None = None


class VentaSimularEntrada(BaseModel):
    sucursal_id: int
    items: list[ItemVentaEntrada] = Field(min_length=1)
    pagos: list[PagoVentaEntrada] = Field(default_factory=list)
    recargo_especial: Decimal | None = Field(default=None, ge=0, le=500)
    vuelto_usd: Decimal = Field(default=Decimal("0"), ge=0)


class VentaCrearEntrada(BaseModel):
    sucursal_id: int
    fecha: date | None = None
    cliente_id: int | None = None
    asesor_id: int | None = None
    tecnico_id: int | None = None
    canal_visita: str = Field(default="Tienda", max_length=60)
    entrega: str = Field(default="RETIRO_TIENDA", max_length=60)
    datos_entrega: dict[str, Any] | None = None
    envio_destinatario_nombre: str | None = Field(default=None, max_length=180)
    envio_destinatario_documento: str | None = Field(default=None, max_length=60)
    envio_destinatario_telefono: str | None = Field(default=None, max_length=60)
    envio_agencia_courier: str | None = Field(default=None, max_length=100)
    envio_direccion_o_agencia: str | None = Field(default=None, max_length=500)
    envio_ciudad_estado: str | None = Field(default=None, max_length=140)
    envio_referencia: str | None = Field(default=None, max_length=255)
    envio_modalidad_pago: str | None = Field(default=None, max_length=40)
    envio_notas: str | None = Field(default=None, max_length=500)
    origen_equipo: str = Field(default="Propio", max_length=60)
    es_factura: bool = False
    numero_control: str = Field(default="", max_length=60)
    recargo_especial: Decimal | None = Field(default=None, ge=0, le=500)
    items: list[ItemVentaEntrada] = Field(min_length=1)
    pagos: list[PagoVentaEntrada] = Field(default_factory=list)
    vuelto_usd: Decimal = Field(default=Decimal("0"), ge=0)
    queda_con_saldo: bool = False
    cashea_numero_orden: str | None = Field(default=None, max_length=64)
    sin_cargador: bool = False
    motivo_sin_cargador: str = Field(default="", max_length=255)
    nota: str = Field(default="", max_length=1000)
    cotizacion_id: int | None = None


class VentaAnularEntrada(BaseModel):
    motivo: str = Field(min_length=3, max_length=500)


class DevolucionCrearEntrada(BaseModel):
    venta_original_id: int
    equipo_id: int | None = None
    articulo_id: int | None = None
    cantidad: int = Field(default=1, gt=0)
    motivo: str = Field(min_length=3, max_length=255)
    estado_reingreso: EstadoReingresoNC = EstadoReingresoNC.POR_PREPARAR


class PagoConfirmarEntrada(BaseModel):
    aprobado: bool
    nota: str = Field(default="", max_length=300)


class AbonoCxcEntrada(BaseModel):
    instrumento_id: int
    monto_moneda_origen: Decimal = Field(gt=0)
    referencia: str = Field(default="", max_length=120)
    fecha: date | None = None


class CasheaLiquidarEntrada(BaseModel):
    cuentas_cashea_ids: list[int] = Field(min_length=1)
    instrumento_destino_id: int
    fecha_pago: date
    comision_usd: Decimal = Field(default=Decimal("0"), ge=0)
    impuestos_usd: Decimal = Field(default=Decimal("0"), ge=0)
    referencia: str = Field(default="", max_length=120)


class CruceManualEntrada(BaseModel):
    pago_id: int
    extracto_id: int


class CierreMensualEntrada(BaseModel):
    anio: int = Field(ge=2020, le=2100)
    mes: int = Field(ge=1, le=12)


class CasheaOrdenActualizarEntrada(BaseModel):
    cashea_numero_orden: str = Field(min_length=1, max_length=64)


class CasheaConfirmarOrdenItem(BaseModel):
    venta_id: int
    cashea_numero_orden: str = Field(min_length=1, max_length=64)
    monto_pagado_real_usd: Decimal = Field(ge=0)
    descuento_real_usd: Decimal = Field(default=Decimal("0"), ge=0)


class CasheaImportarConfirmarEntrada(BaseModel):
    nombre_archivo: str = Field(default="reporte_cashea.xlsx", max_length=255)
    instrumento_destino_id: int
    fecha_deposito: date
    referencia_bancaria: str = Field(default="", max_length=120)
    tasa_bcv_dia: Decimal | None = Field(default=None, gt=0)
    ordenes: list[CasheaConfirmarOrdenItem] = Field(min_length=1)
