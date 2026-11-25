from __future__ import annotations

import calendar
import json
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.core.permisos import Permiso, require_permiso
from app.modelos import RolUsuario, Sucursal, TasaDiaria, Usuario
from app.modelos_admin_finanzas import (
    AuditoriaSistema,
    ConciliacionBancaria,
    DocumentoFiscal,
    GastoOperativo,
    NominaEmpleado,
    NominaPeriodo,
    NominaRecibo,
    ObligacionFiscal,
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
)
from app.modelos_logistica import Compra
from app.modelos_operaciones import LiquidacionComision, MovimientoTesoreria
from app.rutas.tasas import obtener_fecha_hoy
from app.rutas.ventas import generar_correlativo_corto, redondear_usd
from app.servicios.admin_finanzas_export import (
    confirmar_importacion_admin_atomica,
    generar_pdf_auditoria,
    generar_pdf_conciliacion,
    generar_pdf_estado_resultados,
    generar_pdf_libro_fiscal,
    generar_pdf_recibo_nomina,
    generar_plantilla_admin_xlsx,
    generar_xlsx_auditoria,
    generar_xlsx_estado_resultados,
    generar_xlsx_libro_fiscal,
    previsualizar_importacion_admin,
)
from app.servicios.auditoria_service import registrar_auditoria


enrutador = APIRouter(prefix="/api/finanzas", tags=["Administración, Contabilidad, Fiscal, Nómina y Auditoría"])


# =====================================================================
# ESQUEMAS PYDANTIC
# =====================================================================

class GastoCrearEntrada(BaseModel):
    fecha: date | None = None
    categoria: str = Field(min_length=2, max_length=40)
    sucursal_id: int | None = None
    proveedor: str = Field(default="", max_length=160)
    factura_comprobante: str = Field(default="", max_length=100)
    descripcion: str = Field(default="", max_length=500)
    moneda: str = Field(default="USD", pattern="^(USD|USDT|BS)$")
    monto_origen: Decimal = Field(gt=0)
    instrumento_id: int


class DocumentoFiscalCrearEntrada(BaseModel):
    tipo_libro: str = Field(pattern="^(COMPRA|VENTA)$")
    fecha: date | None = None
    numero_factura: str = Field(min_length=1, max_length=80)
    numero_control: str = Field(default="", max_length=80)
    rif_tercero: str = Field(min_length=3, max_length=40)
    nombre_tercero: str = Field(min_length=2, max_length=180)
    base_imponible: Decimal = Field(default=Decimal("0"), ge=0)
    monto_exento: Decimal = Field(default=Decimal("0"), ge=0)
    iva_pct: Decimal = Field(default=Decimal("16.00"), ge=0, le=100)
    igtf_pct: Decimal = Field(default=Decimal("0.00"), ge=0, le=100)
    retencion_iva_pct: Decimal = Field(default=Decimal("0.00"), ge=0, le=100)
    comprobante_ret_iva: str = Field(default="", max_length=80)
    retencion_islr_monto: Decimal = Field(default=Decimal("0.00"), ge=0)
    comprobante_ret_islr: str = Field(default="", max_length=80)
    moneda: str = Field(default="BS", pattern="^(USD|USDT|BS)$")
    notas: str = Field(default="", max_length=500)


class ObligacionFiscalCrearEntrada(BaseModel):
    tipo: str = Field(min_length=2, max_length=40)
    periodo: str = Field(min_length=2, max_length=40)
    descripcion: str = Field(default="", max_length=255)
    fecha_vencimiento: date
    monto_estimado_usd: Decimal = Field(default=Decimal("0"), ge=0)
    notas: str = Field(default="", max_length=500)


class ObligacionEstadoEntrada(BaseModel):
    estado: str = Field(pattern="^(PENDIENTE|DECLARADO|PAGADO)$")
    referencia_pago: str = Field(default="", max_length=100)


class NominaEmpleadoEntrada(BaseModel):
    usuario_id: int
    cedula: str = Field(default="", max_length=40)
    cargo: str = Field(default="", max_length=100)
    sucursal_id: int | None = None
    fecha_ingreso: date | None = None
    salario_base_usd: Decimal = Field(ge=0)
    bono_cestaticket_usd: Decimal = Field(default=Decimal("0"), ge=0)
    datos_bancarios: str = Field(default="", max_length=255)


class NominaReciboAjusteEntrada(BaseModel):
    empleado_id: int
    otros_ingresos_usd: Decimal = Field(default=Decimal("0"), ge=0)
    adelantos_usd: Decimal = Field(default=Decimal("0"), ge=0)
    deduccion_ivss_usd: Decimal = Field(default=Decimal("0"), ge=0)
    deduccion_faov_usd: Decimal = Field(default=Decimal("0"), ge=0)
    deduccion_rpe_usd: Decimal = Field(default=Decimal("0"), ge=0)
    otras_deducciones_usd: Decimal = Field(default=Decimal("0"), ge=0)
    notas: str = Field(default="", max_length=300)


class NominaPeriodoCrearEntrada(BaseModel):
    tipo_periodo: str = Field(default="QUINCENAL", pattern="^(QUINCENAL|MENSUAL)$")
    fecha_inicio: date
    fecha_fin: date
    porcentaje_ivss: Decimal = Field(default=Decimal("4.00"), ge=0, le=50)
    porcentaje_faov: Decimal = Field(default=Decimal("1.00"), ge=0, le=50)
    porcentaje_rpe: Decimal = Field(default=Decimal("0.50"), ge=0, le=50)
    ajustes: list[NominaReciboAjusteEntrada] = Field(default_factory=list)
    notas: str = Field(default="", max_length=500)


class NominaAprobarPagarEntrada(BaseModel):
    instrumento_id: int
    referencia_pago: str = Field(default="", max_length=120)
    notas: str = Field(default="", max_length=500)


class ConciliacionManualEntrada(BaseModel):
    pago_id: int | None = None
    tesoreria_id: int | None = None
    estado: str = Field(default="CONCILIADO", pattern="^(CONCILIADO|PENDIENTE_SISTEMA|EN_TRANSITO)$")


def _tasa_bcv_usdt(bd: Session, fecha_ref: date) -> tuple[Decimal, Decimal]:
    tasa = bd.query(TasaDiaria).filter(TasaDiaria.fecha <= fecha_ref).order_by(TasaDiaria.fecha.desc()).first()
    if tasa is None:
        return Decimal("0"), Decimal("0")
    return tasa.tasa_bcv, tasa.tasa_usdt


# =====================================================================
# 1. CONTABILIDAD: GASTOS OPERATIVOS Y ESTADO DE RESULTADOS (P&L)
# =====================================================================

@enrutador.get("/gastos")
def listar_gastos_operativos(
    fecha_inicio: date | None = Query(default=None),
    fecha_fin: date | None = Query(default=None),
    categoria: str | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    q = (
        bd.query(GastoOperativo)
        .options(
            joinedload(GastoOperativo.sucursal),
            joinedload(GastoOperativo.instrumento),
            joinedload(GastoOperativo.usuario),
        )
        .order_by(GastoOperativo.fecha.desc(), GastoOperativo.id.desc())
    )
    if fecha_inicio:
        q = q.filter(GastoOperativo.fecha >= fecha_inicio)
    if fecha_fin:
        q = q.filter(GastoOperativo.fecha <= fecha_fin)
    if categoria:
        q = q.filter(GastoOperativo.categoria == categoria.upper())
    if sucursal_id is not None:
        q = q.filter(GastoOperativo.sucursal_id == sucursal_id)
    return [
        {
            "id": g.id,
            "codigo": g.codigo,
            "fecha": g.fecha.isoformat(),
            "categoria": g.categoria,
            "sucursal_id": g.sucursal_id,
            "sucursal": g.sucursal.nombre if g.sucursal else "General",
            "proveedor": g.proveedor,
            "factura_comprobante": g.factura_comprobante,
            "descripcion": g.descripcion,
            "moneda": g.moneda,
            "monto_origen": redondear_usd(g.monto_origen),
            "tasa_bcv": float(g.tasa_bcv),
            "monto_usd": redondear_usd(g.monto_usd),
            "instrumento_id": g.instrumento_id,
            "instrumento": g.instrumento.nombre if g.instrumento else "",
            "pago_egreso_id": g.pago_egreso_id,
            "usuario": g.usuario.nombre if g.usuario else "",
        }
        for g in q.limit(300).all()
    ]


@enrutador.post("/gastos", status_code=status.HTTP_201_CREATED)
def crear_gasto_operativo(
    datos: GastoCrearEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    inst = bd.query(InstrumentoFinanciero).filter(InstrumentoFinanciero.id == datos.instrumento_id).first()
    if inst is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instrumento/banco no encontrado.")

    fecha_op = datos.fecha or obtener_fecha_hoy()
    tasa_bcv, tasa_usdt = _tasa_bcv_usdt(bd, fecha_op)
    if datos.moneda == "BS":
        if tasa_bcv <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No hay tasa BCV registrada para convertir el gasto en Bs.",
            )
        monto_usd = (datos.monto_origen / tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        usd_real = (
            (datos.monto_origen / tasa_usdt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if tasa_usdt > 0
            else monto_usd
        )
    else:
        monto_usd = datos.monto_origen.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        usd_real = monto_usd

    codigo = generar_correlativo_corto(bd, GastoOperativo, GastoOperativo.codigo, "GAS")
    pago = Pago(
        venta_id=None,
        instrumento_id=inst.id,
        fecha=fecha_op,
        tipo_movimiento=TipoMovimientoPago.EGRESO.value,
        tipo_documento=TipoDocumentoPago.GASTO_OPERATIVO.value,
        monto_moneda_origen=datos.monto_origen,
        moneda=datos.moneda,
        usd_nominal=monto_usd,
        usd_real=usd_real,
        referencia=datos.factura_comprobante.strip() or codigo,
        estado_verificacion=EstadoVerificacionPago.CONFIRMADO.value,
        verificado_por_id=usuario_actual.id,
        nota=f"{codigo} · {datos.categoria.upper()} · {datos.descripcion.strip()}",
    )
    bd.add(pago)
    bd.flush()

    gasto = GastoOperativo(
        codigo=codigo,
        fecha=fecha_op,
        categoria=datos.categoria.strip().upper(),
        sucursal_id=datos.sucursal_id,
        proveedor=datos.proveedor.strip(),
        factura_comprobante=datos.factura_comprobante.strip(),
        descripcion=datos.descripcion.strip(),
        moneda=datos.moneda,
        monto_origen=datos.monto_origen,
        tasa_bcv=tasa_bcv,
        monto_usd=monto_usd,
        instrumento_id=inst.id,
        pago_egreso_id=pago.id,
        usuario_id=usuario_actual.id,
    )
    bd.add(gasto)
    registrar_auditoria(
        bd,
        usuario_actual,
        "CONTABILIDAD",
        "REGISTRAR_GASTO",
        codigo,
        {},
        {"categoria": gasto.categoria, "monto_usd": float(monto_usd), "instrumento": inst.nombre},
    )
    bd.commit()
    return {
        "id": gasto.id,
        "codigo": gasto.codigo,
        "fecha": gasto.fecha.isoformat(),
        "categoria": gasto.categoria,
        "monto_usd": redondear_usd(gasto.monto_usd),
        "pago_egreso_id": pago.id,
    }


def _calcular_pyl(
    bd: Session,
    *,
    fecha_inicio: date,
    fecha_fin: date,
    sucursal_id: int | None = None,
) -> dict[str, Any]:
    suc_nom = "Todas las sucursales"
    if sucursal_id is not None:
        suc = bd.query(Sucursal).filter(Sucursal.id == sucursal_id).first()
        if suc:
            suc_nom = suc.nombre

    q_v = (
        bd.query(Venta)
        .options(joinedload(Venta.detalles))
        .filter(
            Venta.fecha >= fecha_inicio,
            Venta.fecha <= fecha_fin,
            Venta.estado.notin_([EstadoVenta.ANULADA.value, EstadoVenta.DEVUELTA.value]),
        )
    )
    if sucursal_id is not None:
        q_v = q_v.filter(Venta.sucursal_id == sucursal_id)
    ventas = q_v.all()

    ingresos_ventas = sum((v.total_promo_usd for v in ventas), Decimal("0"))
    costo_mercancia = sum(
        (sum((d.costo_total_snapshot_usd for d in v.detalles), Decimal("0")) for v in ventas),
        Decimal("0"),
    )
    utilidad_bruta = ingresos_ventas - costo_mercancia

    q_g = bd.query(GastoOperativo).filter(
        GastoOperativo.fecha >= fecha_inicio,
        GastoOperativo.fecha <= fecha_fin,
    )
    if sucursal_id is not None:
        q_g = q_g.filter(
            (GastoOperativo.sucursal_id == sucursal_id) | (GastoOperativo.sucursal_id.is_(None))
        )
    gastos = q_g.all()
    gastos_total = sum((g.monto_usd for g in gastos), Decimal("0"))
    por_cat: dict[str, dict[str, Any]] = {}
    for g in gastos:
        if g.categoria not in por_cat:
            por_cat[g.categoria] = {"categoria": g.categoria, "cantidad": 0, "total_usd": Decimal("0")}
        por_cat[g.categoria]["cantidad"] += 1
        por_cat[g.categoria]["total_usd"] += g.monto_usd

    liqs = (
        bd.query(LiquidacionComision)
        .filter(
            LiquidacionComision.fecha_pago >= fecha_inicio,
            LiquidacionComision.fecha_pago <= fecha_fin,
            LiquidacionComision.estado != "ANULADA",
        )
        .all()
    )
    comisiones_liq = sum((l.monto_total_usd for l in liqs), Decimal("0"))

    nominas = (
        bd.query(NominaPeriodo)
        .filter(
            NominaPeriodo.estado == "PAGADA",
            NominaPeriodo.fecha_pago >= fecha_inicio,
            NominaPeriodo.fecha_pago <= fecha_fin,
        )
        .all()
    )
    nomina_pagada = sum((n.total_neto_usd for n in nominas), Decimal("0"))

    movs_tes = (
        bd.query(MovimientoTesoreria)
        .filter(
            MovimientoTesoreria.fecha >= fecha_inicio,
            MovimientoTesoreria.fecha <= fecha_fin,
            MovimientoTesoreria.tipo == "CAMBIO_DIVISA",
        )
        .all()
    )
    dif_cambiario = sum((m.diferencia_usd for m in movs_tes), Decimal("0"))

    utilidad_neta = utilidad_bruta - gastos_total - comisiones_liq - nomina_pagada + dif_cambiario

    return {
        "fecha_inicio": fecha_inicio.isoformat(),
        "fecha_fin": fecha_fin.isoformat(),
        "sucursal_id": sucursal_id,
        "sucursal": suc_nom,
        "cantidad_ventas": len(ventas),
        "ingresos_ventas_usd": redondear_usd(ingresos_ventas),
        "costo_mercancia_usd": redondear_usd(costo_mercancia),
        "utilidad_bruta_usd": redondear_usd(utilidad_bruta),
        "gastos_operativos_usd": redondear_usd(gastos_total),
        "comisiones_liquidadas_usd": redondear_usd(comisiones_liq),
        "nomina_pagada_usd": redondear_usd(nomina_pagada),
        "diferencial_cambiario_usd": redondear_usd(dif_cambiario),
        "utilidad_neta_usd": redondear_usd(utilidad_neta),
        "gastos_por_categoria": [
            {
                "categoria": c["categoria"],
                "cantidad": c["cantidad"],
                "total_usd": redondear_usd(c["total_usd"]),
            }
            for c in sorted(por_cat.values(), key=lambda x: x["total_usd"], reverse=True)
        ],
    }


@enrutador.get("/estado-resultados")
def obtener_estado_resultados(
    fecha_inicio: date | None = Query(default=None),
    fecha_fin: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    hoy = obtener_fecha_hoy()
    f_ini = fecha_inicio or date(hoy.year, hoy.month, 1)
    f_fin = fecha_fin or hoy
    return _calcular_pyl(bd, fecha_inicio=f_ini, fecha_fin=f_fin, sucursal_id=sucursal_id)


@enrutador.get("/estado-resultados/pdf")
def descargar_pdf_estado_resultados(
    fecha_inicio: date | None = Query(default=None),
    fecha_fin: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> Response:
    hoy = obtener_fecha_hoy()
    pyl = _calcular_pyl(bd, fecha_inicio=fecha_inicio or date(hoy.year, hoy.month, 1), fecha_fin=fecha_fin or hoy, sucursal_id=sucursal_id)
    return Response(
        content=generar_pdf_estado_resultados(pyl),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Estado_Resultados_{pyl["fecha_inicio"]}_{pyl["fecha_fin"]}.pdf"'},
    )


@enrutador.get("/estado-resultados/xlsx")
def descargar_xlsx_estado_resultados(
    fecha_inicio: date | None = Query(default=None),
    fecha_fin: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> Response:
    hoy = obtener_fecha_hoy()
    pyl = _calcular_pyl(bd, fecha_inicio=fecha_inicio or date(hoy.year, hoy.month, 1), fecha_fin=fecha_fin or hoy, sucursal_id=sucursal_id)
    return Response(
        content=generar_xlsx_estado_resultados(pyl),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Estado_Resultados_{pyl["fecha_inicio"]}_{pyl["fecha_fin"]}.xlsx"'},
    )


@enrutador.get("/estado-resultados/resumen-ejecutivo")
def obtener_resumen_ejecutivo_pl(
    mes: str | None = Query(default=None, description="Formato YYYY-MM"),
    sucursal_id: int | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    hoy = obtener_fecha_hoy()
    if mes and mes.strip():
        try:
            anio_str, mes_str = mes.strip().split("-")
            anio_obj = int(anio_str)
            mes_obj = int(mes_str)
            if not (1 <= mes_obj <= 12):
                raise ValueError
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El parámetro 'mes' debe tener formato YYYY-MM.",
            ) from exc
    else:
        anio_obj, mes_obj = hoy.year, hoy.month

    ultimo_dia = calendar.monthrange(anio_obj, mes_obj)[1]
    f_ini = date(anio_obj, mes_obj, 1)
    f_fin = date(anio_obj, mes_obj, ultimo_dia)

    # Mes anterior para comparativo automático
    if mes_obj == 1:
        anio_ant, mes_ant = anio_obj - 1, 12
    else:
        anio_ant, mes_ant = anio_obj, mes_obj - 1
    f_ini_ant = date(anio_ant, mes_ant, 1)
    f_fin_ant = date(anio_ant, mes_ant, calendar.monthrange(anio_ant, mes_ant)[1])

    pyl_actual = _calcular_pyl(bd, fecha_inicio=f_ini, fecha_fin=f_fin, sucursal_id=sucursal_id)
    pyl_ant = _calcular_pyl(bd, fecha_inicio=f_ini_ant, fecha_fin=f_fin_ant, sucursal_id=sucursal_id)

    ing = Decimal(str(pyl_actual["ingresos_ventas_usd"]))
    ub = Decimal(str(pyl_actual["utilidad_bruta_usd"]))
    un = Decimal(str(pyl_actual["utilidad_neta_usd"]))
    un_ant = Decimal(str(pyl_ant["utilidad_neta_usd"]))

    margen_bruto_pct = float(((ub / ing) * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)) if ing > 0 else 0.0
    margen_neto_pct = float(((un / ing) * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)) if ing > 0 else 0.0
    if un_ant != 0:
        variacion_neta_pct = float(
            (((un - un_ant) / abs(un_ant)) * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        )
    else:
        variacion_neta_pct = 100.0 if un > 0 else (-100.0 if un < 0 else 0.0)

    # Desglose rápido por sucursal (excluyendo ANULADA y DEVUELTA)
    q_v_suc = (
        bd.query(Venta)
        .options(joinedload(Venta.detalles), joinedload(Venta.sucursal))
        .filter(
            Venta.fecha >= f_ini,
            Venta.fecha <= f_fin,
            Venta.estado.notin_([EstadoVenta.ANULADA.value, EstadoVenta.DEVUELTA.value]),
        )
    )
    if sucursal_id is not None:
        q_v_suc = q_v_suc.filter(Venta.sucursal_id == sucursal_id)
    por_suc: dict[str, dict[str, Any]] = {}
    for v in q_v_suc.all():
        s_nom = v.sucursal.nombre if v.sucursal else "Sin sucursal"
        if s_nom not in por_suc:
            por_suc[s_nom] = {"sucursal": s_nom, "cantidad_ventas": 0, "ventas_usd": Decimal("0"), "contribucion_usd": Decimal("0")}
        costo_v = sum((d.costo_total_snapshot_usd for d in v.detalles), Decimal("0"))
        por_suc[s_nom]["cantidad_ventas"] += 1
        por_suc[s_nom]["ventas_usd"] += v.total_promo_usd
        por_suc[s_nom]["contribucion_usd"] += (v.total_promo_usd - costo_v)

    desglose_sucursales = [
        {
            "sucursal": d["sucursal"],
            "cantidad_ventas": d["cantidad_ventas"],
            "ventas_usd": redondear_usd(d["ventas_usd"]),
            "contribucion_usd": redondear_usd(d["contribucion_usd"]),
        }
        for d in sorted(por_suc.values(), key=lambda x: x["ventas_usd"], reverse=True)
    ]

    # Salud de caja al cierre: liquidez consolidada USD, CxC (clientes + Cashea) y CxP
    tasa_bcv, tasa_usdt = _tasa_bcv_usdt(bd, hoy)
    tasa_conv = tasa_usdt if tasa_usdt > 0 else tasa_bcv
    insts = bd.query(InstrumentoFinanciero).filter(InstrumentoFinanciero.activo.is_(True)).all()
    pagos_ok = bd.query(Pago).filter(Pago.anulado.is_(False)).all()
    saldos_inst: dict[int, Decimal] = {}
    for p in pagos_ok:
        sig = Decimal("-1") if p.tipo_movimiento == TipoMovimientoPago.EGRESO.value else Decimal("1")
        saldos_inst[p.instrumento_id] = saldos_inst.get(p.instrumento_id, Decimal("0")) + (sig * p.monto_moneda_origen)
    liquidez_usd = Decimal("0")
    for inst in insts:
        s_orig = saldos_inst.get(inst.id, Decimal("0"))
        if inst.moneda == MonedaInstrumento.BS.value:
            liquidez_usd += (s_orig / tasa_conv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if tasa_conv > 0 else Decimal("0")
        else:
            liquidez_usd += s_orig.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    cxcs = (
        bd.query(CuentaPorCobrar)
        .filter(
            CuentaPorCobrar.estado == EstadoCuentaPorCobrar.PENDIENTE.value,
            CuentaPorCobrar.saldo_pendiente_usd > Decimal("0"),
        )
        .all()
    )
    cxc_clientes = sum((c.saldo_pendiente_usd for c in cxcs if c.tipo != TipoCuentaPorCobrar.CASHEA.value), Decimal("0"))
    cxc_cashea = sum((c.saldo_pendiente_usd for c in cxcs if c.tipo == TipoCuentaPorCobrar.CASHEA.value), Decimal("0"))
    cxp_total = sum(
        (c.saldo_pendiente_usd for c in bd.query(Compra).filter(Compra.saldo_pendiente_usd > Decimal("0")).all()),
        Decimal("0"),
    )

    # Destinatarios Directores con teléfono
    directores_db = (
        bd.query(Usuario)
        .filter(
            Usuario.activo.is_(True),
            Usuario.rol == RolUsuario.DIRECCION.value,
        )
        .order_by(Usuario.nombre.asc())
        .all()
    )
    directores = [
        {"id": u.id, "nombre": u.nombre, "telefono": (u.telefono or "").strip()}
        for u in directores_db
        if (u.telefono or "").strip()
    ]

    ahora_ccs = datetime.now(ZoneInfo("America/Caracas")).strftime("%d/%m/%Y %H:%M")

    return {
        "mes": f"{anio_obj:04d}-{mes_obj:02d}",
        "mes_anterior": f"{anio_ant:04d}-{mes_ant:02d}",
        "fecha_inicio": f_ini.isoformat(),
        "fecha_fin": f_fin.isoformat(),
        "sucursal_id": sucursal_id,
        "sucursal": pyl_actual["sucursal"],
        "emitido_en": ahora_ccs,
        "resultados": {
            **pyl_actual,
            "margen_bruto_pct": margen_bruto_pct,
            "margen_neto_pct": margen_neto_pct,
            "utilidad_neta_mes_anterior_usd": redondear_usd(un_ant),
            "variacion_neta_pct": variacion_neta_pct,
            "top_gastos": pyl_actual["gastos_por_categoria"][:3],
        },
        "desglose_sucursales": desglose_sucursales,
        "salud_caja": {
            "liquidez_total_usd": redondear_usd(liquidez_usd),
            "cxc_clientes_usd": redondear_usd(cxc_clientes),
            "cxc_cashea_usd": redondear_usd(cxc_cashea),
            "cxc_total_usd": redondear_usd(cxc_clientes + cxc_cashea),
            "cxp_total_usd": redondear_usd(cxp_total),
        },
        "directores": directores,
    }


# =====================================================================
# 2. GESTIÓN FISCAL — VENEZUELA / SENIAT
# =====================================================================

@enrutador.get("/fiscal/documentos")
def listar_documentos_fiscales(
    tipo_libro: str | None = Query(default=None),
    fecha_inicio: date | None = Query(default=None),
    fecha_fin: date | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    q = bd.query(DocumentoFiscal).order_by(DocumentoFiscal.fecha.desc(), DocumentoFiscal.id.desc())
    if tipo_libro:
        q = q.filter(DocumentoFiscal.tipo_libro == tipo_libro.upper())
    if fecha_inicio:
        q = q.filter(DocumentoFiscal.fecha >= fecha_inicio)
    if fecha_fin:
        q = q.filter(DocumentoFiscal.fecha <= fecha_fin)
    return [
        {
            "id": d.id,
            "tipo_libro": d.tipo_libro,
            "fecha": d.fecha.isoformat(),
            "numero_factura": d.numero_factura,
            "numero_control": d.numero_control,
            "rif_tercero": d.rif_tercero,
            "nombre_tercero": d.nombre_tercero,
            "base_imponible": redondear_usd(d.base_imponible),
            "monto_exento": redondear_usd(d.monto_exento),
            "iva_pct": float(d.iva_pct),
            "iva_monto": redondear_usd(d.iva_monto),
            "igtf_pct": float(d.igtf_pct),
            "igtf_monto": redondear_usd(d.igtf_monto),
            "total_documento": redondear_usd(d.total_documento),
            "retencion_iva_pct": float(d.retencion_iva_pct),
            "retencion_iva_monto": redondear_usd(d.retencion_iva_monto),
            "comprobante_ret_iva": d.comprobante_ret_iva,
            "retencion_islr_monto": redondear_usd(d.retencion_islr_monto),
            "comprobante_ret_islr": d.comprobante_ret_islr,
            "moneda": d.moneda,
            "tasa_bcv": float(d.tasa_bcv),
            "notas": d.notas,
        }
        for d in q.limit(300).all()
    ]


@enrutador.post("/fiscal/documentos", status_code=status.HTTP_201_CREATED)
def crear_documento_fiscal(
    datos: DocumentoFiscalCrearEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    fecha_op = datos.fecha or obtener_fecha_hoy()
    tasa_bcv, _ = _tasa_bcv_usdt(bd, fecha_op)
    iva_monto = (datos.base_imponible * datos.iva_pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    subtotal = datos.base_imponible + datos.monto_exento + iva_monto
    igtf_monto = (subtotal * datos.igtf_pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_doc = (subtotal + igtf_monto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    ret_iva_monto = (iva_monto * datos.retencion_iva_pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    doc = DocumentoFiscal(
        tipo_libro=datos.tipo_libro,
        fecha=fecha_op,
        numero_factura=datos.numero_factura.strip(),
        numero_control=datos.numero_control.strip(),
        rif_tercero=datos.rif_tercero.strip().upper(),
        nombre_tercero=datos.nombre_tercero.strip(),
        base_imponible=datos.base_imponible,
        monto_exento=datos.monto_exento,
        iva_pct=datos.iva_pct,
        iva_monto=iva_monto,
        igtf_pct=datos.igtf_pct,
        igtf_monto=igtf_monto,
        total_documento=total_doc,
        retencion_iva_pct=datos.retencion_iva_pct,
        retencion_iva_monto=ret_iva_monto,
        comprobante_ret_iva=datos.comprobante_ret_iva.strip(),
        retencion_islr_monto=datos.retencion_islr_monto,
        comprobante_ret_islr=datos.comprobante_ret_islr.strip(),
        moneda=datos.moneda,
        tasa_bcv=tasa_bcv,
        notas=datos.notas.strip(),
        usuario_id=usuario_actual.id,
    )
    bd.add(doc)
    bd.commit()
    return {
        "id": doc.id,
        "tipo_libro": doc.tipo_libro,
        "numero_factura": doc.numero_factura,
        "iva_monto": redondear_usd(iva_monto),
        "igtf_monto": redondear_usd(igtf_monto),
        "total_documento": redondear_usd(total_doc),
        "retencion_iva_monto": redondear_usd(ret_iva_monto),
    }


@enrutador.get("/fiscal/libro/{tipo_libro}/{formato}")
def exportar_libro_fiscal(
    tipo_libro: str,
    formato: str,
    fecha_inicio: date | None = Query(default=None),
    fecha_fin: date | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> Response:
    tipo_norm = tipo_libro.upper()
    if tipo_norm not in {"COMPRA", "VENTA"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tipo_libro debe ser COMPRA o VENTA.")
    hoy = obtener_fecha_hoy()
    f_ini = fecha_inicio or date(hoy.year, hoy.month, 1)
    f_fin = fecha_fin or hoy
    docs = (
        bd.query(DocumentoFiscal)
        .filter(
            DocumentoFiscal.tipo_libro == tipo_norm,
            DocumentoFiscal.fecha >= f_ini,
            DocumentoFiscal.fecha <= f_fin,
        )
        .order_by(DocumentoFiscal.fecha.asc(), DocumentoFiscal.id.asc())
        .all()
    )
    periodo_txt = f"{f_ini.isoformat()} al {f_fin.isoformat()}"
    if formato.lower() == "xlsx":
        return Response(
            content=generar_xlsx_libro_fiscal(tipo_norm, docs),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="Libro_{tipo_norm}_{f_ini.isoformat()}.xlsx"'},
        )
    if formato.lower() == "pdf":
        return Response(
            content=generar_pdf_libro_fiscal(tipo_norm, docs, periodo_txt),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="Libro_{tipo_norm}_{f_ini.isoformat()}.pdf"'},
        )
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Formato debe ser xlsx o pdf.")


@enrutador.get("/fiscal/obligaciones")
def listar_obligaciones_fiscales(
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    filas = bd.query(ObligacionFiscal).order_by(ObligacionFiscal.fecha_vencimiento.asc()).all()
    return [
        {
            "id": o.id,
            "tipo": o.tipo,
            "periodo": o.periodo,
            "descripcion": o.descripcion,
            "fecha_vencimiento": o.fecha_vencimiento.isoformat(),
            "monto_estimado_usd": redondear_usd(o.monto_estimado_usd),
            "estado": o.estado,
            "referencia_pago": o.referencia_pago,
            "notas": o.notas,
        }
        for o in filas
    ]


@enrutador.post("/fiscal/obligaciones", status_code=status.HTTP_201_CREATED)
def crear_obligacion_fiscal(
    datos: ObligacionFiscalCrearEntrada,
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    ob = ObligacionFiscal(
        tipo=datos.tipo.strip().upper(),
        periodo=datos.periodo.strip(),
        descripcion=datos.descripcion.strip(),
        fecha_vencimiento=datos.fecha_vencimiento,
        monto_estimado_usd=datos.monto_estimado_usd,
        estado="PENDIENTE",
        notas=datos.notas.strip(),
    )
    bd.add(ob)
    bd.commit()
    return {"id": ob.id, "tipo": ob.tipo, "estado": ob.estado}


@enrutador.patch("/fiscal/obligaciones/{ob_id}/estado")
def actualizar_estado_obligacion(
    ob_id: int,
    datos: ObligacionEstadoEntrada,
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    ob = bd.query(ObligacionFiscal).filter(ObligacionFiscal.id == ob_id).first()
    if ob is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligación fiscal no encontrada.")
    ob.estado = datos.estado
    if datos.referencia_pago.strip():
        ob.referencia_pago = datos.referencia_pago.strip()
    bd.commit()
    return {"id": ob.id, "estado": ob.estado, "referencia_pago": ob.referencia_pago}


# =====================================================================
# 3. GESTIÓN LABORAL Y NÓMINA
# =====================================================================

@enrutador.get("/nomina/empleados")
def listar_nomina_empleados(
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    filas = (
        bd.query(NominaEmpleado)
        .options(joinedload(NominaEmpleado.usuario), joinedload(NominaEmpleado.sucursal))
        .order_by(NominaEmpleado.id.asc())
        .all()
    )
    return [
        {
            "id": e.id,
            "usuario_id": e.usuario_id,
            "usuario_nombre": e.usuario.nombre if e.usuario else "",
            "usuario_rol": e.usuario.rol if e.usuario else "",
            "usuario_telefono": getattr(e.usuario, "telefono", "") or "" if e.usuario else "",
            "cedula": e.cedula,
            "cargo": e.cargo,
            "sucursal_id": e.sucursal_id,
            "sucursal": e.sucursal.nombre if e.sucursal else "General",
            "fecha_ingreso": e.fecha_ingreso.isoformat() if e.fecha_ingreso else None,
            "salario_base_usd": redondear_usd(e.salario_base_usd),
            "bono_cestaticket_usd": redondear_usd(e.bono_cestaticket_usd),
            "datos_bancarios": e.datos_bancarios,
            "activo": e.activo,
        }
        for e in filas
    ]


@enrutador.post("/nomina/empleados", status_code=status.HTTP_201_CREATED)
def guardar_ficha_laboral(
    datos: NominaEmpleadoEntrada,
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    usr = bd.query(Usuario).filter(Usuario.id == datos.usuario_id).first()
    if usr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario/personal no encontrado.")
    emp = bd.query(NominaEmpleado).filter(NominaEmpleado.usuario_id == datos.usuario_id).first()
    if emp is None:
        emp = NominaEmpleado(usuario_id=datos.usuario_id)
        bd.add(emp)
    emp.cedula = datos.cedula.strip()
    emp.cargo = datos.cargo.strip() or usr.rol
    emp.sucursal_id = datos.sucursal_id if datos.sucursal_id is not None else usr.sucursal_id
    emp.fecha_ingreso = datos.fecha_ingreso
    emp.salario_base_usd = datos.salario_base_usd
    emp.bono_cestaticket_usd = datos.bono_cestaticket_usd
    emp.datos_bancarios = datos.datos_bancarios.strip()
    emp.activo = True
    bd.commit()
    return {"id": emp.id, "usuario_id": emp.usuario_id, "salario_base_usd": redondear_usd(emp.salario_base_usd)}


@enrutador.get("/nomina/periodos")
def listar_periodos_nomina(
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    periodos = (
        bd.query(NominaPeriodo)
        .options(
            joinedload(NominaPeriodo.instrumento),
            joinedload(NominaPeriodo.aprobado_por),
            joinedload(NominaPeriodo.recibos).joinedload(NominaRecibo.usuario),
            joinedload(NominaPeriodo.recibos).joinedload(NominaRecibo.empleado),
        )
        .order_by(NominaPeriodo.id.desc())
        .all()
    )
    return [
        {
            "id": p.id,
            "codigo": p.codigo,
            "tipo_periodo": p.tipo_periodo,
            "fecha_inicio": p.fecha_inicio.isoformat(),
            "fecha_fin": p.fecha_fin.isoformat(),
            "estado": p.estado,
            "total_neto_usd": redondear_usd(p.total_neto_usd),
            "instrumento": p.instrumento.nombre if p.instrumento else "",
            "pago_egreso_id": p.pago_egreso_id,
            "referencia_pago": p.referencia_pago,
            "aprobado_por": p.aprobado_por.nombre if p.aprobado_por else None,
            "fecha_pago": p.fecha_pago.isoformat() if p.fecha_pago else None,
            "recibos": [
                {
                    "id": r.id,
                    "empleado_id": r.empleado_id,
                    "usuario_id": r.usuario_id,
                    "usuario_nombre": r.usuario.nombre if r.usuario else "",
                    "usuario_telefono": getattr(r.usuario, "telefono", "") or "" if r.usuario else "",
                    "cargo": r.empleado.cargo if r.empleado else "",
                    "salario_base_usd": redondear_usd(r.salario_base_usd),
                    "bonos_usd": redondear_usd(r.bonos_usd),
                    "otros_ingresos_usd": redondear_usd(r.otros_ingresos_usd),
                    "adelantos_usd": redondear_usd(r.adelantos_usd),
                    "deduccion_ivss_usd": redondear_usd(r.deduccion_ivss_usd),
                    "deduccion_faov_usd": redondear_usd(r.deduccion_faov_usd),
                    "deduccion_rpe_usd": redondear_usd(r.deduccion_rpe_usd),
                    "otras_deducciones_usd": redondear_usd(r.otras_deducciones_usd),
                    "neto_pagar_usd": redondear_usd(r.neto_pagar_usd),
                    "comisiones_informativas_usd": redondear_usd(r.comisiones_informativas_usd),
                }
                for r in p.recibos
            ],
        }
        for p in periodos
    ]


@enrutador.post("/nomina/periodos", status_code=status.HTTP_201_CREATED)
def generar_periodo_nomina(
    datos: NominaPeriodoCrearEntrada,
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    empleados = (
        bd.query(NominaEmpleado)
        .options(joinedload(NominaEmpleado.usuario))
        .filter(NominaEmpleado.activo.is_(True))
        .all()
    )
    if not empleados:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No existen empleados activos registrados en la ficha laboral.",
        )

    ajustes_map = {a.empleado_id: a for a in datos.ajustes}
    factor = Decimal("0.5") if datos.tipo_periodo == "QUINCENAL" else Decimal("1.0")
    codigo = generar_correlativo_corto(bd, NominaPeriodo, NominaPeriodo.codigo, "NOM")

    periodo = NominaPeriodo(
        codigo=codigo,
        tipo_periodo=datos.tipo_periodo,
        fecha_inicio=datos.fecha_inicio,
        fecha_fin=datos.fecha_fin,
        estado="BORRADOR",
        notas=datos.notas.strip(),
    )
    bd.add(periodo)
    bd.flush()

    total_neto = Decimal("0")
    for emp in empleados:
        sal_base = (emp.salario_base_usd * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        bonos = (emp.bono_cestaticket_usd * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        aj = ajustes_map.get(emp.id)
        otros_ing = aj.otros_ingresos_usd if aj else Decimal("0")
        adelantos = aj.adelantos_usd if aj else Decimal("0")
        ivss = (
            aj.deduccion_ivss_usd
            if (aj and aj.deduccion_ivss_usd > 0)
            else (sal_base * datos.porcentaje_ivss / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
        faov = (
            aj.deduccion_faov_usd
            if (aj and aj.deduccion_faov_usd > 0)
            else (sal_base * datos.porcentaje_faov / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
        rpe = (
            aj.deduccion_rpe_usd
            if (aj and aj.deduccion_rpe_usd > 0)
            else (sal_base * datos.porcentaje_rpe / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
        otras_ded = aj.otras_deducciones_usd if aj else Decimal("0")
        neto = max(
            Decimal("0"),
            (sal_base + bonos + otros_ing - adelantos - ivss - faov - rpe - otras_ded).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
        )

        # Comisiones liquidadas en el período (solo informativo, no duplica pago)
        com_info = sum(
            (
                l.monto_total_usd
                for l in bd.query(LiquidacionComision)
                .filter(
                    LiquidacionComision.usuario_id == emp.usuario_id,
                    LiquidacionComision.estado != "ANULADA",
                    LiquidacionComision.fecha_pago >= datos.fecha_inicio,
                    LiquidacionComision.fecha_pago <= datos.fecha_fin,
                )
                .all()
            ),
            Decimal("0"),
        )

        bd.add(
            NominaRecibo(
                periodo_id=periodo.id,
                empleado_id=emp.id,
                usuario_id=emp.usuario_id,
                salario_base_usd=sal_base,
                bonos_usd=bonos,
                otros_ingresos_usd=otros_ing,
                adelantos_usd=adelantos,
                deduccion_ivss_usd=ivss,
                deduccion_faov_usd=faov,
                deduccion_rpe_usd=rpe,
                otras_deducciones_usd=otras_ded,
                neto_pagar_usd=neto,
                comisiones_informativas_usd=com_info,
                notas=aj.notas.strip() if aj else "",
            )
        )
        total_neto += neto

    periodo.total_neto_usd = total_neto.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    bd.commit()
    return {
        "id": periodo.id,
        "codigo": periodo.codigo,
        "estado": periodo.estado,
        "total_neto_usd": redondear_usd(periodo.total_neto_usd),
        "cantidad_recibos": len(empleados),
    }


@enrutador.post("/nomina/periodos/{periodo_id}/pagar")
def aprobar_y_pagar_nomina(
    periodo_id: int,
    datos: NominaAprobarPagarEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    periodo = bd.query(NominaPeriodo).filter(NominaPeriodo.id == periodo_id).first()
    if periodo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Período de nómina no encontrado.")
    if periodo.estado == "PAGADA":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"La nómina {periodo.codigo} ya fue pagada.")

    inst = bd.query(InstrumentoFinanciero).filter(InstrumentoFinanciero.id == datos.instrumento_id).first()
    if inst is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instrumento/banco no encontrado.")

    hoy = obtener_fecha_hoy()
    tasa_bcv, tasa_usdt = _tasa_bcv_usdt(bd, hoy)
    if inst.moneda == MonedaInstrumento.BS.value:
        monto_orig = (periodo.total_neto_usd * tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if tasa_bcv > 0 else periodo.total_neto_usd
        usd_real = (monto_orig / tasa_usdt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if tasa_usdt > 0 else periodo.total_neto_usd
    else:
        monto_orig = periodo.total_neto_usd
        usd_real = periodo.total_neto_usd

    pago = Pago(
        venta_id=None,
        instrumento_id=inst.id,
        fecha=hoy,
        tipo_movimiento=TipoMovimientoPago.EGRESO.value,
        tipo_documento=TipoDocumentoPago.NOMINA.value,
        monto_moneda_origen=monto_orig,
        moneda=inst.moneda,
        usd_nominal=periodo.total_neto_usd,
        usd_real=usd_real,
        referencia=datos.referencia_pago.strip() or periodo.codigo,
        estado_verificacion=EstadoVerificacionPago.CONFIRMADO.value,
        verificado_por_id=usuario_actual.id,
        nota=f"Pago Nómina {periodo.codigo} ({periodo.fecha_inicio} al {periodo.fecha_fin}). {datos.notas.strip()}".strip(),
    )
    bd.add(pago)
    bd.flush()

    periodo.estado = "PAGADA"
    periodo.instrumento_id = inst.id
    periodo.pago_egreso_id = pago.id
    periodo.referencia_pago = datos.referencia_pago.strip() or periodo.codigo
    periodo.aprobado_por_id = usuario_actual.id
    periodo.fecha_pago = hoy

    registrar_auditoria(
        bd,
        usuario_actual,
        "NOMINA",
        "APROBAR_PAGAR_NOMINA",
        periodo.codigo,
        {"estado": "BORRADOR"},
        {"estado": "PAGADA", "total_neto_usd": float(periodo.total_neto_usd), "pago_egreso_id": pago.id},
    )
    bd.commit()
    return {
        "id": periodo.id,
        "codigo": periodo.codigo,
        "estado": periodo.estado,
        "total_neto_usd": redondear_usd(periodo.total_neto_usd),
        "pago_egreso_id": pago.id,
    }


@enrutador.get("/nomina/recibos/{recibo_id}/pdf")
def descargar_pdf_recibo_nomina(
    recibo_id: int,
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> Response:
    recibo = (
        bd.query(NominaRecibo)
        .options(
            joinedload(NominaRecibo.periodo),
            joinedload(NominaRecibo.empleado),
            joinedload(NominaRecibo.usuario),
        )
        .filter(NominaRecibo.id == recibo_id)
        .first()
    )
    if recibo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recibo de nómina no encontrado.")
    pdf_bytes = generar_pdf_recibo_nomina(recibo, recibo.periodo, recibo.empleado)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Recibo_{recibo.periodo.codigo}_{recibo.id}.pdf"'},
    )


# =====================================================================
# 4. CONCILIACIÓN BANCARIA AVANZADA
# =====================================================================

@enrutador.get("/conciliacion/partidas")
def listar_partidas_conciliacion(
    instrumento_id: int | None = Query(default=None),
    estado: str | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    q = (
        bd.query(ConciliacionBancaria)
        .options(joinedload(ConciliacionBancaria.instrumento), joinedload(ConciliacionBancaria.conciliado_por))
        .order_by(ConciliacionBancaria.fecha_movimiento.desc(), ConciliacionBancaria.id.desc())
    )
    if instrumento_id is not None:
        q = q.filter(ConciliacionBancaria.instrumento_id == instrumento_id)
    if estado:
        q = q.filter(ConciliacionBancaria.estado == estado.upper())
    partidas = q.limit(300).all()

    # Detectar partidas EN_TRANSITO (están en pagos del sistema sin conciliar para ese instrumento)
    q_tr = bd.query(Pago).filter(Pago.anulado.is_(False), Pago.conciliado.is_(False))
    if instrumento_id is not None:
        q_tr = q_tr.filter(Pago.instrumento_id == instrumento_id)
    en_transito = q_tr.order_by(Pago.fecha.desc()).limit(100).all()

    return {
        "partidas": [
            {
                "id": p.id,
                "lote_codigo": p.lote_codigo,
                "instrumento_id": p.instrumento_id,
                "instrumento": p.instrumento.nombre if p.instrumento else "",
                "fecha_movimiento": p.fecha_movimiento.isoformat(),
                "referencia": p.referencia,
                "descripcion": p.descripcion,
                "monto_banco": redondear_usd(p.monto_banco),
                "tipo_movimiento": p.tipo_movimiento,
                "estado": p.estado,
                "pago_id": p.pago_id,
                "tesoreria_id": p.tesoreria_id,
                "conciliado_por": p.conciliado_por.nombre if p.conciliado_por else None,
            }
            for p in partidas
        ],
        "en_transito": [
            {
                "pago_id": pg.id,
                "fecha": pg.fecha.isoformat(),
                "referencia": pg.referencia,
                "tipo_movimiento": pg.tipo_movimiento,
                "monto_moneda_origen": redondear_usd(pg.monto_moneda_origen),
                "moneda": pg.moneda,
                "nota": pg.nota,
            }
            for pg in en_transito
        ],
    }


@enrutador.patch("/conciliacion/partidas/{partida_id}")
def conciliar_partida_manual(
    partida_id: int,
    datos: ConciliacionManualEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    partida = bd.query(ConciliacionBancaria).filter(ConciliacionBancaria.id == partida_id).first()
    if partida is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partida de conciliación no encontrada.")
    partida.estado = datos.estado
    if datos.pago_id is not None:
        pago = bd.query(Pago).filter(Pago.id == datos.pago_id).first()
        if pago:
            pago.conciliado = datos.estado == "CONCILIADO"
            partida.pago_id = pago.id
    if datos.tesoreria_id is not None:
        partida.tesoreria_id = datos.tesoreria_id
    partida.conciliado_por_id = usuario_actual.id
    partida.fecha_conciliacion = datetime.now(timezone.utc)
    bd.commit()
    return {"id": partida.id, "estado": partida.estado, "pago_id": partida.pago_id}


@enrutador.get("/conciliacion/pdf")
def descargar_pdf_conciliacion(
    instrumento_id: int | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> Response:
    q = bd.query(ConciliacionBancaria).order_by(ConciliacionBancaria.fecha_movimiento.desc())
    inst_nom = "Todas las cuentas"
    if instrumento_id is not None:
        q = q.filter(ConciliacionBancaria.instrumento_id == instrumento_id)
        inst = bd.query(InstrumentoFinanciero).filter(InstrumentoFinanciero.id == instrumento_id).first()
        if inst:
            inst_nom = inst.nombre
    partidas = q.limit(300).all()
    return Response(
        content=generar_pdf_conciliacion(partidas, inst_nom),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="Reporte_Conciliacion_Bancaria.pdf"'},
    )


# =====================================================================
# 5. AUDITORÍA INTERNA INMUTABLE
# =====================================================================

@enrutador.get("/auditoria")
def listar_auditoria(
    fecha_inicio: date | None = Query(default=None),
    fecha_fin: date | None = Query(default=None),
    modulo: str | None = Query(default=None),
    accion: str | None = Query(default=None),
    usuario_id: int | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    q = bd.query(AuditoriaSistema).order_by(AuditoriaSistema.id.desc())
    if modulo:
        q = q.filter(AuditoriaSistema.modulo == modulo.upper())
    if accion:
        q = q.filter(AuditoriaSistema.accion.ilike(f"%{accion.strip()}%"))
    if usuario_id is not None:
        q = q.filter(AuditoriaSistema.usuario_id == usuario_id)
    filas = q.limit(400).all()
    res = []
    for r in filas:
        f_reg = r.fecha.date() if r.fecha else None
        if fecha_inicio and f_reg and f_reg < fecha_inicio:
            continue
        if fecha_fin and f_reg and f_reg > fecha_fin:
            continue
        try:
            ant = json.loads(r.detalle_anterior_json or "{}")
        except Exception:
            ant = {}
        try:
            nvo = json.loads(r.detalle_nuevo_json or "{}")
        except Exception:
            nvo = {}
        res.append(
            {
                "id": r.id,
                "fecha": r.fecha.isoformat() if r.fecha else "",
                "usuario_id": r.usuario_id,
                "usuario_nombre": r.usuario_nombre,
                "usuario_rol": r.usuario_rol,
                "modulo": r.modulo,
                "accion": r.accion,
                "entidad_id": r.entidad_id,
                "detalle_anterior": ant,
                "detalle_nuevo": nvo,
            }
        )
    return res


@enrutador.get("/auditoria/exportar/{formato}")
def exportar_auditoria(
    formato: str,
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> Response:
    filas = bd.query(AuditoriaSistema).order_by(AuditoriaSistema.id.desc()).limit(500).all()
    if formato.lower() == "xlsx":
        return Response(
            content=generar_xlsx_auditoria(filas),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="Auditoria_Sistema_Tekio.xlsx"'},
        )
    if formato.lower() == "pdf":
        return Response(
            content=generar_pdf_auditoria(filas),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="Auditoria_Sistema_Tekio.pdf"'},
        )
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Formato debe ser xlsx o pdf.")


# =====================================================================
# 6. CARGA MASIVA ADMINISTRATIVA (.XLSX / .CSV)
# =====================================================================

@enrutador.get("/admin-plantillas/{flujo}")
def descargar_plantilla_admin(
    flujo: str,
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
) -> Response:
    contenido = generar_plantilla_admin_xlsx(flujo)
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="plantilla_admin_{flujo}.xlsx"'},
    )


@enrutador.post("/admin-importar/preview")
async def preview_importacion_admin_endpoint(
    flujo: str = Form(...),
    instrumento_id: int | None = Form(default=None),
    archivo: UploadFile = File(...),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    contenido = await archivo.read()
    return previsualizar_importacion_admin(
        bd,
        flujo=flujo,
        contenido=contenido,
        nombre_archivo=archivo.filename or "archivo.xlsx",
        instrumento_id=instrumento_id,
    )


@enrutador.post("/admin-importar/confirmar", status_code=status.HTTP_201_CREATED)
async def confirmar_importacion_admin_endpoint(
    flujo: str = Form(...),
    instrumento_id: int | None = Form(default=None),
    archivo: UploadFile = File(...),
    usuario_actual: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    contenido = await archivo.read()
    return confirmar_importacion_admin_atomica(
        bd,
        flujo=flujo,
        contenido=contenido,
        nombre_archivo=archivo.filename or "archivo.xlsx",
        usuario=usuario_actual,
        instrumento_id=instrumento_id,
    )
