from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.core.permisos import Permiso, require_permiso
from app.core.validacion import ModeloEntradaLimpio as BaseModel
from app.modelos import CatalogoArticulo, Sucursal, TasaDiaria, TipoArticulo, Usuario
from app.modelos_admin_finanzas import GastoOperativo, NominaPeriodo, ObligacionFiscal
from app.modelos_contabilidad import (
    AsientoContable,
    AsientoLinea,
    PlanCuenta,
    Prestamo,
    PrestamoCuota,
)
from app.modelos_finanzas import (
    CuentaPorCobrar,
    EstadoCuentaPorCobrar,
    EstadoVenta,
    EstadoVerificacionPago,
    InstrumentoFinanciero,
    MonedaInstrumento,
    Pago,
    TipoCuentaPorCobrar,
    TipoDocumentoPago,
    TipoMovimientoPago,
    Venta,
    VentaDetalle,
)
from app.modelos_logistica import Compra, Equipo, EstadoEquipo, MovimientoInventario
from app.modelos_operaciones import LiquidacionComision, MovimientoTesoreria
from app.rutas.tasas import obtener_fecha_hoy
from app.rutas.ventas import redondear_usd
from app.servicios.auditoria_service import registrar_auditoria
from app.servicios.contabilidad_service import asegurar_plan_cuentas, registrar_asiento
from app.servicios.estados_financieros_export import (
    generar_pdf_balance_general,
    generar_pdf_pl_escalonado,
    generar_xlsx_balance_general,
    generar_xlsx_pl_escalonado,
)


enrutador = APIRouter(prefix="/api/finanzas", tags=["Motor Contable, Préstamos y Estados Financieros"])


# =====================================================================
# ESQUEMAS PYDANTIC
# =====================================================================

class PrestamoCrearEntrada(BaseModel):
    acreedor: str = Field(min_length=2, max_length=160)
    monto_principal_usd: Decimal = Field(gt=0)
    tasa_interes_anual_pct: Decimal = Field(default=Decimal("0"), ge=0, le=200)
    plazo_meses: int = Field(ge=1, le=120)
    fecha_inicio: date | None = None
    instrumento_desembolso_id: int | None = None
    notas: str = Field(default="", max_length=1000)


class PrestamoCuotaPagarEntrada(BaseModel):
    instrumento_id: int
    fecha_pago: date | None = None
    referencia_pago: str = Field(default="", max_length=120)


def _sumar_meses(fecha_base: date, meses: int) -> date:
    total_meses = (fecha_base.month - 1) + meses
    anio = fecha_base.year + total_meses // 12
    mes = (total_meses % 12) + 1
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, min(fecha_base.day, ultimo_dia))


def _generar_tabla_amortizacion(
    monto_principal: Decimal,
    tasa_anual_pct: Decimal,
    plazo_meses: int,
    fecha_inicio: date,
) -> list[dict[str, Any]]:
    """Calcula tabla de amortización francesa (o cuota fija de capital si tasa == 0)."""
    cuotas: list[dict[str, Any]] = []
    saldo = monto_principal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if tasa_anual_pct <= Decimal("0"):
        capital_base = (monto_principal / Decimal(plazo_meses)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        for n in range(1, plazo_meses + 1):
            cap = saldo if n == plazo_meses else min(saldo, capital_base)
            saldo = (saldo - cap).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cuotas.append(
                {
                    "nro_cuota": n,
                    "fecha_vencimiento": _sumar_meses(fecha_inicio, n),
                    "capital_usd": cap,
                    "interes_usd": Decimal("0.00"),
                    "cuota_total_usd": cap,
                }
            )
        return cuotas

    tasa_mensual = float(tasa_anual_pct) / 100.0 / 12.0
    factor = (1.0 + tasa_mensual) ** plazo_meses
    cuota_fija = Decimal(
        str(float(monto_principal) * (tasa_mensual * factor) / (factor - 1.0))
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    for n in range(1, plazo_meses + 1):
        interes = (saldo * Decimal(str(tasa_mensual))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if n == plazo_meses:
            capital = saldo
            total_c = (capital + interes).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            capital = max(Decimal("0.00"), (cuota_fija - interes).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            if capital > saldo:
                capital = saldo
            total_c = (capital + interes).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        saldo = (saldo - capital).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cuotas.append(
            {
                "nro_cuota": n,
                "fecha_vencimiento": _sumar_meses(fecha_inicio, n),
                "capital_usd": capital,
                "interes_usd": interes,
                "cuota_total_usd": total_c,
            }
        )
    return cuotas


def _tasa_bcv_usdt_corte(bd: Session, fecha_ref: date) -> tuple[Decimal, Decimal]:
    tasa = (
        bd.query(TasaDiaria)
        .filter(TasaDiaria.fecha <= fecha_ref)
        .order_by(TasaDiaria.fecha.desc())
        .first()
    )
    if tasa is None:
        return Decimal("0"), Decimal("0")
    return tasa.tasa_bcv, tasa.tasa_usdt


# =====================================================================
# 1. PLAN DE CUENTAS Y LIBRO DIARIO (ASIENTOS)
# =====================================================================

@enrutador.get("/contabilidad/plan-cuentas")
def listar_plan_cuentas(
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    asegurar_plan_cuentas(bd)
    bd.commit()
    cuentas = bd.query(PlanCuenta).order_by(PlanCuenta.codigo.asc()).all()
    return [
        {
            "id": c.id,
            "codigo": c.codigo,
            "nombre": c.nombre,
            "tipo": c.tipo,
            "activa": c.activa,
        }
        for c in cuentas
    ]


@enrutador.get("/contabilidad/asientos")
def listar_asientos_contables(
    fecha_inicio: date | None = Query(default=None),
    fecha_fin: date | None = Query(default=None),
    modulo: str | None = Query(default=None),
    limite: int = Query(default=100, ge=1, le=500),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    q = (
        bd.query(AsientoContable)
        .options(
            joinedload(AsientoContable.lineas).joinedload(AsientoLinea.cuenta),
            joinedload(AsientoContable.creado_por),
        )
        .order_by(AsientoContable.fecha.desc(), AsientoContable.id.desc())
    )
    if fecha_inicio:
        q = q.filter(AsientoContable.fecha >= fecha_inicio)
    if fecha_fin:
        q = q.filter(AsientoContable.fecha <= fecha_fin)
    if modulo and modulo.strip():
        q = q.filter(AsientoContable.modulo_origen == modulo.strip().upper())

    asientos = q.limit(limite).all()
    salida: list[dict[str, Any]] = []
    for a in asientos:
        tot_debe = sum((l.debe_usd for l in a.lineas), Decimal("0.00"))
        tot_haber = sum((l.haber_usd for l in a.lineas), Decimal("0.00"))
        salida.append(
            {
                "id": a.id,
                "fecha": a.fecha.isoformat(),
                "referencia": a.referencia,
                "modulo_origen": a.modulo_origen,
                "entidad_id": a.entidad_id,
                "descripcion": a.descripcion,
                "creado_por": a.creado_por.nombre if a.creado_por else "Sistema",
                "total_debe_usd": redondear_usd(tot_debe),
                "total_haber_usd": redondear_usd(tot_haber),
                "cuadrado": tot_debe == tot_haber,
                "lineas": [
                    {
                        "id": l.id,
                        "cuenta_codigo": l.cuenta.codigo if l.cuenta else "",
                        "cuenta_nombre": l.cuenta.nombre if l.cuenta else "",
                        "cuenta_tipo": l.cuenta.tipo if l.cuenta else "",
                        "debe_usd": redondear_usd(l.debe_usd),
                        "haber_usd": redondear_usd(l.haber_usd),
                        "descripcion": l.descripcion,
                    }
                    for l in a.lineas
                ],
            }
        )
    return salida


# =====================================================================
# 2. MÓDULO DE PRÉSTAMOS Y TABLA DE AMORTIZACIÓN
# =====================================================================

def _serializar_prestamo(p: Prestamo) -> dict[str, Any]:
    capital_pagado = sum(
        (c.capital_usd for c in p.cuotas if c.estado == "PAGADA"), Decimal("0.00")
    )
    intereses_pagados = sum(
        (c.interes_usd for c in p.cuotas if c.estado == "PAGADA"), Decimal("0.00")
    )
    saldo_capital = max(Decimal("0.00"), p.monto_principal_usd - capital_pagado)
    proxima = next((c for c in p.cuotas if c.estado == "PENDIENTE"), None)
    return {
        "id": p.id,
        "acreedor": p.acreedor,
        "monto_principal_usd": redondear_usd(p.monto_principal_usd),
        "tasa_interes_anual_pct": float(p.tasa_interes_anual_pct),
        "plazo_meses": p.plazo_meses,
        "fecha_inicio": p.fecha_inicio.isoformat(),
        "estado": p.estado,
        "instrumento_desembolso_id": p.instrumento_desembolso_id,
        "instrumento_desembolso": p.instrumento_desembolso.nombre if p.instrumento_desembolso else None,
        "notas": p.notas,
        "capital_pagado_usd": redondear_usd(capital_pagado),
        "intereses_pagados_usd": redondear_usd(intereses_pagados),
        "saldo_capital_usd": redondear_usd(saldo_capital),
        "cuotas_pagadas": sum(1 for c in p.cuotas if c.estado == "PAGADA"),
        "cuotas_totales": len(p.cuotas),
        "proxima_cuota": (
            {
                "id": proxima.id,
                "nro_cuota": proxima.nro_cuota,
                "fecha_vencimiento": proxima.fecha_vencimiento.isoformat(),
                "cuota_total_usd": redondear_usd(proxima.cuota_total_usd),
            }
            if proxima
            else None
        ),
        "cuotas": [
            {
                "id": c.id,
                "nro_cuota": c.nro_cuota,
                "fecha_vencimiento": c.fecha_vencimiento.isoformat(),
                "capital_usd": redondear_usd(c.capital_usd),
                "interes_usd": redondear_usd(c.interes_usd),
                "cuota_total_usd": redondear_usd(c.cuota_total_usd),
                "estado": c.estado,
                "fecha_pago": c.fecha_pago.isoformat() if c.fecha_pago else None,
                "pago_egreso_id": c.pago_egreso_id,
                "referencia_pago": c.referencia_pago,
            }
            for c in p.cuotas
        ],
    }


@enrutador.get("/prestamos")
def listar_prestamos(
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    prestamos = (
        bd.query(Prestamo)
        .options(
            joinedload(Prestamo.cuotas),
            joinedload(Prestamo.instrumento_desembolso),
        )
        .order_by(Prestamo.id.desc())
        .all()
    )
    return [_serializar_prestamo(p) for p in prestamos]


@enrutador.post("/prestamos", status_code=status.HTTP_201_CREATED)
def crear_prestamo(
    datos: PrestamoCrearEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    fecha_ini = datos.fecha_inicio or obtener_fecha_hoy()
    inst: InstrumentoFinanciero | None = None
    if datos.instrumento_desembolso_id is not None:
        inst = (
            bd.query(InstrumentoFinanciero)
            .filter(InstrumentoFinanciero.id == datos.instrumento_desembolso_id)
            .first()
        )
        if inst is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Instrumento de desembolso no encontrado.",
            )

    prestamo = Prestamo(
        acreedor=datos.acreedor.strip(),
        monto_principal_usd=datos.monto_principal_usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        tasa_interes_anual_pct=datos.tasa_interes_anual_pct,
        plazo_meses=datos.plazo_meses,
        fecha_inicio=fecha_ini,
        estado="ACTIVO",
        instrumento_desembolso_id=inst.id if inst else None,
        notas=datos.notas.strip(),
        creado_por_id=usuario_actual.id,
    )
    bd.add(prestamo)
    bd.flush()

    tabla = _generar_tabla_amortizacion(
        monto_principal=prestamo.monto_principal_usd,
        tasa_anual_pct=prestamo.tasa_interes_anual_pct,
        plazo_meses=prestamo.plazo_meses,
        fecha_inicio=fecha_ini,
    )
    for fila in tabla:
        bd.add(
            PrestamoCuota(
                prestamo_id=prestamo.id,
                nro_cuota=fila["nro_cuota"],
                fecha_vencimiento=fila["fecha_vencimiento"],
                capital_usd=fila["capital_usd"],
                interes_usd=fila["interes_usd"],
                cuota_total_usd=fila["cuota_total_usd"],
                estado="PENDIENTE",
            )
        )

    if inst is not None:
        tasa_bcv, tasa_usdt = _tasa_bcv_usdt_corte(bd, fecha_ini)
        if inst.moneda == MonedaInstrumento.BS.value and tasa_bcv > 0:
            monto_orig = (prestamo.monto_principal_usd * tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            usd_real = (monto_orig / tasa_usdt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if tasa_usdt > 0 else prestamo.monto_principal_usd
        else:
            monto_orig = prestamo.monto_principal_usd
            usd_real = prestamo.monto_principal_usd
        bd.add(
            Pago(
                venta_id=None,
                instrumento_id=inst.id,
                fecha=fecha_ini,
                tipo_movimiento=TipoMovimientoPago.INGRESO.value,
                tipo_documento="PRESTAMO_DESEMBOLSO",
                monto_moneda_origen=monto_orig,
                moneda=inst.moneda,
                tasa_bcv_dia=tasa_bcv,
                tasa_usdt_dia=tasa_usdt,
                usd_nominal=prestamo.monto_principal_usd,
                usd_real=usd_real,
                referencia=f"PREST-{prestamo.id}",
                estado_verificacion=EstadoVerificacionPago.CONFIRMADO.value,
                verificado_por_id=usuario_actual.id,
                nota=f"Desembolso de préstamo #{prestamo.id} · {prestamo.acreedor}",
            )
        )

    registrar_asiento(
        bd,
        fecha=fecha_ini,
        referencia=f"PREST-{prestamo.id}",
        modulo_origen="PRESTAMOS",
        entidad_id=prestamo.id,
        descripcion=f"Registro de préstamo #{prestamo.id} con {prestamo.acreedor}",
        lineas=[
            {
                "codigo_cuenta": "1.1.01",
                "debe_usd": prestamo.monto_principal_usd,
                "descripcion": f"Ingreso desembolso préstamo #{prestamo.id}",
            },
            {
                "codigo_cuenta": "2.1.03",
                "haber_usd": prestamo.monto_principal_usd,
                "descripcion": f"Obligación préstamo {prestamo.acreedor}",
            },
        ],
        creado_por_id=usuario_actual.id,
    )
    registrar_auditoria(
        bd,
        usuario_actual,
        "PRESTAMOS",
        "CREAR_PRESTAMO",
        f"PREST-{prestamo.id}",
        {},
        {
            "acreedor": prestamo.acreedor,
            "monto_principal_usd": float(prestamo.monto_principal_usd),
            "plazo_meses": prestamo.plazo_meses,
        },
    )
    bd.commit()

    prestamo_full = (
        bd.query(Prestamo)
        .options(
            joinedload(Prestamo.cuotas),
            joinedload(Prestamo.instrumento_desembolso),
        )
        .filter(Prestamo.id == prestamo.id)
        .first()
    )
    return _serializar_prestamo(prestamo_full)


@enrutador.post("/prestamos/{prestamo_id}/cuotas/{cuota_id}/pagar")
def pagar_cuota_prestamo(
    prestamo_id: int,
    cuota_id: int,
    datos: PrestamoCuotaPagarEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    cuota = (
        bd.query(PrestamoCuota)
        .options(joinedload(PrestamoCuota.prestamo))
        .filter(
            PrestamoCuota.id == cuota_id,
            PrestamoCuota.prestamo_id == prestamo_id,
        )
        .first()
    )
    if cuota is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuota de préstamo no encontrada.",
        )
    if cuota.estado == "PAGADA":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La cuota #{cuota.nro_cuota} ya fue pagada.",
        )

    inst = (
        bd.query(InstrumentoFinanciero)
        .filter(InstrumentoFinanciero.id == datos.instrumento_id)
        .first()
    )
    if inst is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instrumento/banco no encontrado.",
        )

    fecha_pago = datos.fecha_pago or obtener_fecha_hoy()
    tasa_bcv, tasa_usdt = _tasa_bcv_usdt_corte(bd, fecha_pago)
    if inst.moneda == MonedaInstrumento.BS.value and tasa_bcv > 0:
        monto_orig = (cuota.cuota_total_usd * tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        usd_real = (monto_orig / tasa_usdt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if tasa_usdt > 0 else cuota.cuota_total_usd
    else:
        monto_orig = cuota.cuota_total_usd
        usd_real = cuota.cuota_total_usd

    ref = datos.referencia_pago.strip() or f"PREST-{prestamo_id}-C{cuota.nro_cuota}"
    pago = Pago(
        venta_id=None,
        instrumento_id=inst.id,
        fecha=fecha_pago,
        tipo_movimiento=TipoMovimientoPago.EGRESO.value,
        tipo_documento="PRESTAMO_CUOTA",
        monto_moneda_origen=monto_orig,
        moneda=inst.moneda,
        tasa_bcv_dia=tasa_bcv,
        tasa_usdt_dia=tasa_usdt,
        usd_nominal=cuota.cuota_total_usd,
        usd_real=usd_real,
        referencia=ref,
        estado_verificacion=EstadoVerificacionPago.CONFIRMADO.value,
        verificado_por_id=usuario_actual.id,
        nota=f"Pago cuota #{cuota.nro_cuota} préstamo {cuota.prestamo.acreedor}",
    )
    bd.add(pago)
    bd.flush()

    cuota.estado = "PAGADA"
    cuota.fecha_pago = fecha_pago
    cuota.pago_egreso_id = pago.id
    cuota.instrumento_pago_id = inst.id
    cuota.referencia_pago = ref

    # Asiento automático: Debe Préstamos por Pagar (capital) + Intereses Financieros (interés) / Haber Caja y Bancos
    lineas_pago: list[dict[str, Any]] = []
    if cuota.capital_usd > Decimal("0.00"):
        lineas_pago.append(
            {
                "codigo_cuenta": "2.1.03",
                "debe_usd": cuota.capital_usd,
                "descripcion": f"Amortización capital cuota #{cuota.nro_cuota} ({cuota.prestamo.acreedor})",
            }
        )
    if cuota.interes_usd > Decimal("0.00"):
        lineas_pago.append(
            {
                "codigo_cuenta": "6.3.01",
                "debe_usd": cuota.interes_usd,
                "descripcion": f"Intereses cuota #{cuota.nro_cuota} ({cuota.prestamo.acreedor})",
            }
        )
    lineas_pago.append(
        {
            "codigo_cuenta": "1.1.01",
            "haber_usd": cuota.cuota_total_usd,
            "descripcion": f"Egreso desde {inst.nombre} ({ref})",
        }
    )
    registrar_asiento(
        bd,
        fecha=fecha_pago,
        referencia=ref,
        modulo_origen="PRESTAMOS_PAGO",
        entidad_id=cuota.id,
        descripcion=f"Pago cuota #{cuota.nro_cuota} préstamo #{prestamo_id} ({cuota.prestamo.acreedor})",
        lineas=lineas_pago,
        creado_por_id=usuario_actual.id,
    )

    pendientes_restantes = (
        bd.query(PrestamoCuota)
        .filter(
            PrestamoCuota.prestamo_id == prestamo_id,
            PrestamoCuota.estado == "PENDIENTE",
        )
        .count()
    )
    if pendientes_restantes == 0:
        cuota.prestamo.estado = "PAGADO"

    registrar_auditoria(
        bd,
        usuario_actual,
        "PRESTAMOS",
        "PAGAR_CUOTA",
        ref,
        {"estado": "PENDIENTE"},
        {
            "estado": "PAGADA",
            "capital_usd": float(cuota.capital_usd),
            "interes_usd": float(cuota.interes_usd),
            "pago_egreso_id": pago.id,
        },
    )
    bd.commit()

    prestamo_full = (
        bd.query(Prestamo)
        .options(
            joinedload(Prestamo.cuotas),
            joinedload(Prestamo.instrumento_desembolso),
        )
        .filter(Prestamo.id == prestamo_id)
        .first()
    )
    return _serializar_prestamo(prestamo_full)


# =====================================================================
# 3. ESTADO DE RESULTADOS (P&L) ESCALONADO Y BALANCE GENERAL
# =====================================================================

def _calcular_pl_escalonado(
    bd: Session,
    *,
    fecha_inicio: date,
    fecha_fin: date,
    sucursal_id: int | None = None,
) -> dict[str, Any]:
    suc_nom = "Consolidado (Todas las sucursales)"
    if sucursal_id is not None:
        suc = bd.query(Sucursal).filter(Sucursal.id == sucursal_id).first()
        if suc:
            suc_nom = suc.nombre

    q_ventas = (
        bd.query(Venta)
        .options(joinedload(Venta.detalles).joinedload(VentaDetalle.articulo))
        .filter(
            Venta.fecha >= fecha_inicio,
            Venta.fecha <= fecha_fin,
            Venta.estado.notin_([EstadoVenta.ANULADA.value, EstadoVenta.DEVUELTA.value]),
        )
    )
    if sucursal_id is not None:
        q_ventas = q_ventas.filter(Venta.sucursal_id == sucursal_id)
    ventas = q_ventas.all()

    ing_equipos_comp = Decimal("0.00")
    ing_servicios = Decimal("0.00")
    costo_ventas = Decimal("0.00")
    comisiones_devengadas = Decimal("0.00")

    for v in ventas:
        base_com = Decimal("0.00")
        base_serv = Decimal("0.00")
        for d in v.detalles:
            sub = (d.precio_promo_usd * d.cantidad).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            costo_ventas += (d.costo_total_snapshot_usd * d.cantidad).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if d.articulo is not None and d.articulo.tipo == TipoArticulo.SERVICIO.value:
                ing_servicios += sub
                base_serv += sub
            else:
                ing_equipos_comp += sub
                base_com += sub
        if v.asesor_id is not None:
            comisiones_devengadas += (base_com * Decimal("0.01")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        comisiones_devengadas += (base_com * Decimal("0.005")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if v.tecnico_id is not None:
            comisiones_devengadas += (base_serv * Decimal("0.50")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    ingresos_netos = (ing_equipos_comp + ing_servicios).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    utilidad_bruta = (ingresos_netos - costo_ventas).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Comisiones: usar el mayor entre liquidadas y devengadas para reflejar impacto real de ventas
    comisiones_liquidadas = sum(
        (
            l.monto_total_usd
            for l in bd.query(LiquidacionComision)
            .filter(
                LiquidacionComision.estado != "ANULADA",
                LiquidacionComision.fecha_pago >= fecha_inicio,
                LiquidacionComision.fecha_pago <= fecha_fin,
            )
            .all()
        ),
        Decimal("0.00"),
    )
    comisiones_venta = max(comisiones_devengadas, comisiones_liquidadas).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    q_gastos = bd.query(GastoOperativo).filter(
        GastoOperativo.fecha >= fecha_inicio,
        GastoOperativo.fecha <= fecha_fin,
    )
    if sucursal_id is not None:
        q_gastos = q_gastos.filter(
            (GastoOperativo.sucursal_id == sucursal_id) | (GastoOperativo.sucursal_id.is_(None))
        )
    gastos_operativos = sum((g.monto_usd for g in q_gastos.all()), Decimal("0.00")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    gastos_nomina = sum(
        (
            p.total_neto_usd
            for p in bd.query(NominaPeriodo)
            .filter(
                NominaPeriodo.estado == "PAGADA",
                NominaPeriodo.fecha_pago >= fecha_inicio,
                NominaPeriodo.fecha_pago <= fecha_fin,
            )
            .all()
        ),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    utilidad_operativa = (
        utilidad_bruta - comisiones_venta - gastos_operativos - gastos_nomina
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    diferencial_cambiario = sum(
        (
            m.diferencia_usd
            for m in bd.query(MovimientoTesoreria)
            .filter(
                MovimientoTesoreria.tipo == "CAMBIO_DIVISA",
                MovimientoTesoreria.fecha >= fecha_inicio,
                MovimientoTesoreria.fecha <= fecha_fin,
            )
            .all()
        ),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    intereses_prestamos = sum(
        (
            c.interes_usd
            for c in bd.query(PrestamoCuota)
            .filter(
                PrestamoCuota.estado == "PAGADA",
                PrestamoCuota.fecha_pago >= fecha_inicio,
                PrestamoCuota.fecha_pago <= fecha_fin,
            )
            .all()
        ),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    utilidad_neta = (
        utilidad_operativa + diferencial_cambiario - intereses_prestamos
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _pct(num: Decimal) -> float:
        if ingresos_netos <= Decimal("0.00"):
            return 0.0
        return float((num / ingresos_netos * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    return {
        "fecha_inicio": fecha_inicio.isoformat(),
        "fecha_fin": fecha_fin.isoformat(),
        "sucursal_id": sucursal_id,
        "sucursal": suc_nom,
        "cantidad_ventas": len(ventas),
        "ingresos_equipos_componentes_usd": redondear_usd(ing_equipos_comp),
        "ingresos_servicios_usd": redondear_usd(ing_servicios),
        "ingresos_netos_usd": redondear_usd(ingresos_netos),
        "costo_ventas_usd": redondear_usd(costo_ventas),
        "utilidad_bruta_usd": redondear_usd(utilidad_bruta),
        "margen_bruto_pct": _pct(utilidad_bruta),
        "comisiones_venta_usd": redondear_usd(comisiones_venta),
        "gastos_operativos_usd": redondear_usd(gastos_operativos),
        "gastos_nomina_usd": redondear_usd(gastos_nomina),
        "utilidad_operativa_ebit_usd": redondear_usd(utilidad_operativa),
        "margen_operativo_pct": _pct(utilidad_operativa),
        "diferencial_cambiario_usd": redondear_usd(diferencial_cambiario),
        "intereses_prestamos_usd": redondear_usd(intereses_prestamos),
        "utilidad_neta_usd": redondear_usd(utilidad_neta),
        "margen_neto_pct": _pct(utilidad_neta),
    }


def _calcular_balance_general(bd: Session, fecha_corte: date) -> dict[str, Any]:
    tasa_bcv, tasa_usdt = _tasa_bcv_usdt_corte(bd, fecha_corte)
    tasa_conv = tasa_usdt if tasa_usdt > 0 else tasa_bcv

    # 1. Cajas y Bancos (equivalente USD a fecha de corte)
    instrumentos = bd.query(InstrumentoFinanciero).filter(InstrumentoFinanciero.activo.is_(True)).all()
    pagos = (
        bd.query(Pago)
        .filter(Pago.anulado.is_(False), Pago.fecha <= fecha_corte)
        .all()
    )
    saldos_inst: dict[int, Decimal] = {i.id: Decimal("0.00") for i in instrumentos}
    for p in pagos:
        if p.instrumento_id not in saldos_inst:
            continue
        signo = Decimal("1") if p.tipo_movimiento == TipoMovimientoPago.INGRESO.value else Decimal("-1")
        saldos_inst[p.instrumento_id] += signo * p.monto_moneda_origen

    cajas_bancos = Decimal("0.00")
    for inst in instrumentos:
        s_orig = saldos_inst.get(inst.id, Decimal("0.00"))
        if inst.moneda == MonedaInstrumento.BS.value:
            equiv = (s_orig / tasa_conv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if tasa_conv > 0 else Decimal("0.00")
        else:
            equiv = s_orig.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cajas_bancos += equiv

    # 2. CxC Clientes y Cashea por Cobrar
    cxcs = (
        bd.query(CuentaPorCobrar)
        .filter(
            CuentaPorCobrar.estado == EstadoCuentaPorCobrar.PENDIENTE.value,
            CuentaPorCobrar.saldo_pendiente_usd > Decimal("0"),
        )
        .all()
    )
    cxc_clientes = sum(
        (c.saldo_pendiente_usd for c in cxcs if c.tipo != TipoCuentaPorCobrar.CASHEA.value),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    cashea_cobrar = sum(
        (c.saldo_pendiente_usd for c in cxcs if c.tipo == TipoCuentaPorCobrar.CASHEA.value),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 3. Inventario de Equipos (propios, no vendidos ni cementerio)
    equipos_activos = (
        bd.query(Equipo)
        .filter(
            Equipo.estado.notin_([EstadoEquipo.VENDIDO.value, EstadoEquipo.CEMENTERIO.value]),
            Equipo.es_consignacion.is_(False),
        )
        .all()
    )
    inv_equipos = sum(
        (e.costo_compra_usd + e.costo_flete_usd + e.costo_taller_usd for e in equipos_activos),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 4. Inventario de Componentes (saldo neto por artículo * último costo positivo)
    saldos_comp = (
        bd.query(
            MovimientoInventario.articulo_id,
            func.sum(MovimientoInventario.cantidad).label("stock"),
        )
        .filter(MovimientoInventario.articulo_id.isnot(None))
        .group_by(MovimientoInventario.articulo_id)
        .all()
    )
    inv_componentes = Decimal("0.00")
    for art_id, stock in saldos_comp:
        cant = int(stock or 0)
        if cant <= 0 or art_id is None:
            continue
        ultimo = (
            bd.query(MovimientoInventario.costo_unitario_usd)
            .filter(
                MovimientoInventario.articulo_id == art_id,
                MovimientoInventario.cantidad > 0,
                MovimientoInventario.costo_unitario_usd > Decimal("0"),
            )
            .order_by(MovimientoInventario.id.desc())
            .first()
        )
        costo_u = ultimo[0] if ultimo else Decimal("0.00")
        inv_componentes += (costo_u * cant).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    total_activos = (
        cajas_bancos + cxc_clientes + cashea_cobrar + inv_equipos + inv_componentes
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 5. Pasivos: CxP Proveedores + Préstamos por Pagar + Obligaciones Fiscales
    cxp_proveedores = sum(
        (
            c.saldo_pendiente_usd
            for c in bd.query(Compra)
            .filter(Compra.saldo_pendiente_usd > Decimal("0"), Compra.fecha <= fecha_corte)
            .all()
        ),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    prestamos_pagar = sum(
        (
            cu.capital_usd
            for cu in bd.query(PrestamoCuota)
            .join(Prestamo, Prestamo.id == PrestamoCuota.prestamo_id)
            .filter(
                Prestamo.estado == "ACTIVO",
                Prestamo.fecha_inicio <= fecha_corte,
                PrestamoCuota.estado == "PENDIENTE",
            )
            .all()
        ),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    obligaciones_fiscales = sum(
        (
            o.monto_estimado_usd
            for o in bd.query(ObligacionFiscal)
            .filter(ObligacionFiscal.estado != "PAGADO")
            .all()
        ),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    total_pasivos = (cxp_proveedores + prestamos_pagar + obligaciones_fiscales).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # 6. Patrimonio: Resultado del Ejercicio (YTD) + Capital Social y Resultados Acumulados
    inicio_anio = date(fecha_corte.year, 1, 1)
    pl_ytd = _calcular_pl_escalonado(bd, fecha_inicio=inicio_anio, fecha_fin=fecha_corte)
    resultado_ejercicio = Decimal(str(pl_ytd["utilidad_neta_usd"])).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    capital_y_reservas = (total_activos - total_pasivos - resultado_ejercicio).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    total_patrimonio = (capital_y_reservas + resultado_ejercicio).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    total_pasivo_patrimonio = (total_pasivos + total_patrimonio).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    diferencia = (total_activos - total_pasivo_patrimonio).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    return {
        "fecha_corte": fecha_corte.isoformat(),
        "activos": {
            "cajas_bancos_usd": redondear_usd(cajas_bancos),
            "cxc_clientes_usd": redondear_usd(cxc_clientes),
            "cashea_por_cobrar_usd": redondear_usd(cashea_cobrar),
            "inventario_equipos_usd": redondear_usd(inv_equipos),
            "inventario_componentes_usd": redondear_usd(inv_componentes),
            "total_activos_usd": redondear_usd(total_activos),
        },
        "pasivos": {
            "cxp_proveedores_usd": redondear_usd(cxp_proveedores),
            "prestamos_por_pagar_usd": redondear_usd(prestamos_pagar),
            "obligaciones_fiscales_usd": redondear_usd(obligaciones_fiscales),
            "total_pasivos_usd": redondear_usd(total_pasivos),
        },
        "patrimonio": {
            "capital_social_y_reservas_usd": redondear_usd(capital_y_reservas),
            "resultado_ejercicio_usd": redondear_usd(resultado_ejercicio),
            "total_patrimonio_usd": redondear_usd(total_patrimonio),
        },
        "total_pasivo_mas_patrimonio_usd": redondear_usd(total_pasivo_patrimonio),
        "diferencia_cuadre_usd": redondear_usd(diferencia),
        "cuadrado": abs(diferencia) <= Decimal("0.01"),
    }


@enrutador.get("/estados/pl-escalonado")
def obtener_pl_escalonado(
    fecha_inicio: date | None = Query(default=None),
    fecha_fin: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    hoy = obtener_fecha_hoy()
    f_ini = fecha_inicio or date(hoy.year, hoy.month, 1)
    f_fin = fecha_fin or hoy
    return _calcular_pl_escalonado(
        bd, fecha_inicio=f_ini, fecha_fin=f_fin, sucursal_id=sucursal_id
    )


@enrutador.get("/estados/pl-escalonado/export")
def exportar_pl_escalonado(
    formato: str = Query(default="pdf", pattern="^(pdf|xlsx)$"),
    fecha_inicio: date | None = Query(default=None),
    fecha_fin: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> Response:
    hoy = obtener_fecha_hoy()
    f_ini = fecha_inicio or date(hoy.year, hoy.month, 1)
    f_fin = fecha_fin or hoy
    pl = _calcular_pl_escalonado(bd, fecha_inicio=f_ini, fecha_fin=f_fin, sucursal_id=sucursal_id)
    if formato == "xlsx":
        return Response(
            content=generar_xlsx_pl_escalonado(pl),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="tekio_pl_escalonado_{f_ini}_{f_fin}.xlsx"'},
        )
    return Response(
        content=generar_pdf_pl_escalonado(pl),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="tekio_pl_escalonado_{f_ini}_{f_fin}.pdf"'},
    )


@enrutador.get("/estados/balance-general")
def obtener_balance_general(
    fecha_corte: date | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    corte = fecha_corte or obtener_fecha_hoy()
    return _calcular_balance_general(bd, corte)


@enrutador.get("/estados/balance-general/export")
def exportar_balance_general(
    formato: str = Query(default="pdf", pattern="^(pdf|xlsx)$"),
    fecha_corte: date | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> Response:
    corte = fecha_corte or obtener_fecha_hoy()
    bal = _calcular_balance_general(bd, corte)
    if formato == "xlsx":
        return Response(
            content=generar_xlsx_balance_general(bal),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="tekio_balance_general_{corte}.xlsx"'},
        )
    return Response(
        content=generar_pdf_balance_general(bal),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="tekio_balance_general_{corte}.pdf"'},
    )
