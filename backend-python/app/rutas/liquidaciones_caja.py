from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.esquemas_operaciones import CierreCajaCrearEntrada, LiquidacionComisionCrearEntrada
from app.modelos import Sucursal, TasaDiaria, Usuario
from app.modelos_finanzas import (
    EstadoVenta,
    EstadoVerificacionPago,
    InstrumentoFinanciero,
    MonedaInstrumento,
    Pago,
    TipoDocumentoPago,
    TipoMovimientoPago,
    Venta,
)
from app.modelos_operaciones import (
    CierreCaja,
    LiquidacionComision,
    LiquidacionComisionDetalle,
)
from app.rutas.finanzas import calcular_reporte_comisiones_rango
from app.rutas.tasas import obtener_fecha_hoy
from app.rutas.ventas import generar_correlativo_corto, redondear_usd, verificar_mes_abierto
from app.seguridad import ROLES_ADMINISTRATIVOS, obtener_usuario_actual, requerir_roles
from app.servicios.pdf_documentos import (
    generar_pdf_cierre_caja,
    generar_pdf_liquidacion_comision,
)


enrutador = APIRouter(prefix="/api/finanzas", tags=["Liquidaciones y Cierre de Caja"])


def _serializar_liquidacion(liq: LiquidacionComision) -> dict[str, Any]:
    return {
        "id": liq.id,
        "codigo": liq.codigo,
        "usuario_id": liq.usuario_id,
        "usuario_nombre": liq.usuario.nombre if liq.usuario else "Colaborador",
        "usuario_rol": liq.usuario.rol if liq.usuario else "",
        "usuario_telefono": getattr(liq.usuario, "telefono", "") or "" if liq.usuario else "",
        "fecha_inicio": liq.fecha_inicio.isoformat(),
        "fecha_fin": liq.fecha_fin.isoformat(),
        "fecha_pago": liq.fecha_pago.isoformat(),
        "monto_total_usd": redondear_usd(liq.monto_total_usd),
        "instrumento_id": liq.instrumento_id,
        "instrumento": liq.instrumento.nombre if liq.instrumento else "",
        "referencia": liq.referencia,
        "pago_egreso_id": liq.pago_egreso_id,
        "autorizado_por": liq.autorizado_por.nombre if liq.autorizado_por else "",
        "notas": liq.notas,
        "cantidad_operaciones": len(liq.detalles),
        "notas_liquidadas": [d.referencia_origen for d in liq.detalles if d.referencia_origen],
        "creado_en": liq.creado_en.isoformat() if liq.creado_en else None,
    }


@enrutador.get("/liquidaciones")
def listar_liquidaciones(
    usuario_id: int | None = Query(default=None),
    _usuario: Usuario = Depends(requerir_roles(*ROLES_ADMINISTRATIVOS)),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    consulta = (
        bd.query(LiquidacionComision)
        .options(
            joinedload(LiquidacionComision.usuario),
            joinedload(LiquidacionComision.autorizado_por),
            joinedload(LiquidacionComision.instrumento),
            joinedload(LiquidacionComision.detalles),
        )
        .order_by(LiquidacionComision.id.desc())
    )
    if usuario_id is not None:
        consulta = consulta.filter(LiquidacionComision.usuario_id == usuario_id)
    return [_serializar_liquidacion(liq) for liq in consulta.all()]


@enrutador.post("/liquidaciones", status_code=status.HTTP_201_CREATED)
def crear_liquidacion_comisiones(
    datos: LiquidacionComisionCrearEntrada,
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_ADMINISTRATIVOS)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    fecha_pago = obtener_fecha_hoy()
    verificar_mes_abierto(bd, fecha_pago)

    colaborador = bd.query(Usuario).filter(Usuario.id == datos.usuario_id).first()
    if colaborador is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Colaborador no encontrado.")

    instrumento = (
        bd.query(InstrumentoFinanciero)
        .filter(InstrumentoFinanciero.id == datos.instrumento_id)
        .first()
    )
    if instrumento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instrumento financiero no encontrado.",
        )

    f_ini, f_fin = datos.fecha_inicio, datos.fecha_fin
    if f_ini > f_fin:
        f_ini, f_fin = f_fin, f_ini

    # Obtener únicamente operaciones PENDIENTES del colaborador en el rango
    _, operaciones = calcular_reporte_comisiones_rango(
        bd,
        fecha_inicio=f_ini,
        fecha_fin=f_fin,
        usuario_id=datos.usuario_id,
        estado="PENDIENTE",
    )
    pendientes = [op for op in operaciones if op.get("estado_comision") == "PENDIENTE"]
    if not pendientes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No existen comisiones pendientes por liquidar para este colaborador en el rango indicado.",
        )

    monto_total = sum(
        (Decimal(str(op["comision_usd"])) for op in pendientes),
        Decimal("0"),
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if monto_total <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El monto neto pendiente por liquidar debe ser mayor a $0.00.",
        )

    tasa = (
        bd.query(TasaDiaria)
        .filter(TasaDiaria.fecha <= fecha_pago)
        .order_by(TasaDiaria.fecha.desc())
        .first()
    )
    tasa_bcv = tasa.tasa_bcv if tasa else Decimal("0")
    tasa_usdt = tasa.tasa_usdt if tasa else Decimal("0")

    if instrumento.moneda == MonedaInstrumento.BS.value:
        if tasa_bcv <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No existe tasa BCV registrada para registrar el egreso en bolívares.",
            )
        monto_origen = (monto_total * tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        usd_real = (
            (monto_origen / tasa_usdt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if tasa_usdt > 0
            else monto_total
        )
    else:
        monto_origen = monto_total
        usd_real = monto_total

    codigo = generar_correlativo_corto(bd, LiquidacionComision, LiquidacionComision.codigo, "LIQ")

    pago_egreso = Pago(
        venta_id=None,
        instrumento_id=instrumento.id,
        fecha=fecha_pago,
        tipo_movimiento=TipoMovimientoPago.EGRESO.value,
        tipo_documento=TipoDocumentoPago.GASTO.value,
        monto_moneda_origen=monto_origen,
        moneda=instrumento.moneda,
        tasa_bcv_dia=tasa_bcv,
        tasa_usdt_dia=tasa_usdt,
        usd_nominal=monto_total,
        usd_real=usd_real,
        cubre_promo_usd=monto_total,
        referencia=datos.referencia.strip() or codigo,
        estado_verificacion=EstadoVerificacionPago.CONFIRMADO.value,
        nota=f"Liquidación de comisiones {codigo} · {colaborador.nombre} ({f_ini.isoformat()} al {f_fin.isoformat()})",
    )
    bd.add(pago_egreso)
    bd.flush()

    liq = LiquidacionComision(
        codigo=codigo,
        usuario_id=colaborador.id,
        fecha_inicio=f_ini,
        fecha_fin=f_fin,
        fecha_pago=fecha_pago,
        monto_total_usd=monto_total,
        instrumento_id=instrumento.id,
        referencia=datos.referencia.strip(),
        pago_egreso_id=pago_egreso.id,
        autorizado_por_id=usuario_actual.id,
        notas=datos.notas.strip(),
    )
    bd.add(liq)
    bd.flush()

    for op in pendientes:
        bd.add(
            LiquidacionComisionDetalle(
                liquidacion_id=liq.id,
                venta_id=op.get("venta_id"),
                usuario_id=colaborador.id,
                referencia_origen=str(op.get("numero_nota") or ""),
                concepto=str(op.get("tipo") or "COMISION"),
                base_promo_usd=Decimal(str(op.get("base_promo_usd") or 0)),
                monto_comision_usd=Decimal(str(op.get("comision_usd") or 0)),
            )
        )

    bd.commit()

    liq_completa = (
        bd.query(LiquidacionComision)
        .options(
            joinedload(LiquidacionComision.usuario),
            joinedload(LiquidacionComision.autorizado_por),
            joinedload(LiquidacionComision.instrumento),
            joinedload(LiquidacionComision.detalles),
        )
        .filter(LiquidacionComision.id == liq.id)
        .first()
    )
    return _serializar_liquidacion(liq_completa)


@enrutador.get("/liquidaciones/{liq_id}/pdf")
def descargar_pdf_liquidacion(
    liq_id: int,
    _usuario: Usuario = Depends(requerir_roles(*ROLES_ADMINISTRATIVOS)),
    bd: Session = Depends(obtener_bd),
) -> Response:
    liq = (
        bd.query(LiquidacionComision)
        .options(
            joinedload(LiquidacionComision.usuario),
            joinedload(LiquidacionComision.autorizado_por),
            joinedload(LiquidacionComision.instrumento),
            joinedload(LiquidacionComision.detalles),
        )
        .filter(LiquidacionComision.id == liq_id)
        .first()
    )
    if liq is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Liquidación no encontrada.")

    pdf_bytes = generar_pdf_liquidacion_comision(liq)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="liquidacion-{liq.codigo}.pdf"'},
    )


# =====================================================================
# CIERRE DE CAJA DIARIO
# =====================================================================


def _calcular_preview_cierre_caja(
    bd: Session,
    fecha_op: date,
    sucursal_id: int | None = None,
) -> dict[str, Any]:
    sucursal_nombre = "Todas las sucursales"
    if sucursal_id is not None:
        suc = bd.query(Sucursal).filter(Sucursal.id == sucursal_id).first()
        if suc:
            sucursal_nombre = suc.nombre

    q_ventas = bd.query(Venta).filter(Venta.fecha == fecha_op)
    if sucursal_id is not None:
        q_ventas = q_ventas.filter(Venta.sucursal_id == sucursal_id)
    ventas_dia = q_ventas.all()

    ventas_activas = [
        v for v in ventas_dia if v.estado not in (EstadoVenta.ANULADA.value, EstadoVenta.DEVUELTA.value)
    ]
    anulaciones = [
        v for v in ventas_dia if v.estado in (EstadoVenta.ANULADA.value, EstadoVenta.DEVUELTA.value)
    ]
    total_ventas_usd = sum((v.total_promo_usd for v in ventas_activas), Decimal("0"))

    # Movimientos financieros del día (ingresos de ventas/abonos + egresos de liquidaciones/reembolsos/gastos)
    q_pagos = (
        bd.query(Pago)
        .options(joinedload(Pago.instrumento), joinedload(Pago.venta))
        .filter(Pago.fecha == fecha_op, Pago.anulado.is_(False))
    )
    pagos_dia = q_pagos.all()
    if sucursal_id is not None:
        pagos_dia = [
            p for p in pagos_dia if (p.venta is None or p.venta.sucursal_id == sucursal_id)
        ]

    total_ingresos_usd = Decimal("0")
    total_ingresos_bs = Decimal("0")
    total_egresos_usd = Decimal("0")
    total_egresos_bs = Decimal("0")
    total_cashea_usd = Decimal("0")
    efectivo_esperado_usd = Decimal("0")

    por_inst: dict[int, dict[str, Any]] = {}

    for p in pagos_dia:
        inst = p.instrumento
        inst_id = inst.id if inst else 0
        inst_nom = inst.nombre if inst else "Otro instrumento"
        mon = p.moneda
        es_cashea = "cashea" in inst_nom.lower()
        es_efectivo_usd = ("efectivo" in inst_nom.lower() or "caja" in inst_nom.lower()) and mon == MonedaInstrumento.USD.value

        if inst_id not in por_inst:
            por_inst[inst_id] = {
                "instrumento_id": inst_id,
                "instrumento": inst_nom,
                "moneda": mon,
                "ingresos_origen": Decimal("0"),
                "egresos_origen": Decimal("0"),
                "ingresos_usd": Decimal("0"),
                "egresos_usd": Decimal("0"),
                "cantidad_movimientos": 0,
            }

        entry = por_inst[inst_id]
        entry["cantidad_movimientos"] += 1

        if p.tipo_movimiento == TipoMovimientoPago.EGRESO.value:
            entry["egresos_origen"] += p.monto_moneda_origen
            entry["egresos_usd"] += p.usd_nominal
            if mon == MonedaInstrumento.BS.value:
                total_egresos_bs += p.monto_moneda_origen
            total_egresos_usd += p.usd_nominal
            if es_efectivo_usd:
                efectivo_esperado_usd -= p.usd_nominal
        else:
            entry["ingresos_origen"] += p.monto_moneda_origen
            entry["ingresos_usd"] += p.usd_nominal
            if es_cashea:
                total_cashea_usd += p.usd_nominal
            else:
                if mon == MonedaInstrumento.BS.value:
                    total_ingresos_bs += p.monto_moneda_origen
                total_ingresos_usd += p.usd_nominal
                if es_efectivo_usd:
                    efectivo_esperado_usd += p.usd_nominal

    desglose = [
        {
            "instrumento_id": d["instrumento_id"],
            "instrumento": d["instrumento"],
            "moneda": d["moneda"],
            "ingresos_origen": redondear_usd(d["ingresos_origen"]),
            "egresos_origen": redondear_usd(d["egresos_origen"]),
            "neto_origen": redondear_usd(d["ingresos_origen"] - d["egresos_origen"]),
            "ingresos_usd": redondear_usd(d["ingresos_usd"]),
            "egresos_usd": redondear_usd(d["egresos_usd"]),
            "neto_usd": redondear_usd(d["ingresos_usd"] - d["egresos_usd"]),
            "cantidad_movimientos": d["cantidad_movimientos"],
        }
        for d in sorted(por_inst.values(), key=lambda x: x["instrumento"])
    ]

    return {
        "fecha": fecha_op.isoformat(),
        "sucursal_id": sucursal_id,
        "sucursal": sucursal_nombre,
        "cantidad_ventas": len(ventas_activas),
        "cantidad_anulaciones": len(anulaciones),
        "total_ventas_usd": redondear_usd(total_ventas_usd),
        "total_ingresos_usd": redondear_usd(total_ingresos_usd),
        "total_ingresos_bs": redondear_usd(total_ingresos_bs),
        "total_egresos_usd": redondear_usd(total_egresos_usd),
        "total_egresos_bs": redondear_usd(total_egresos_bs),
        "total_cashea_usd": redondear_usd(total_cashea_usd),
        "efectivo_esperado_usd": redondear_usd(max(Decimal("0"), efectivo_esperado_usd)),
        "saldo_neto_esperado_usd": redondear_usd(total_ingresos_usd - total_egresos_usd),
        "desglose_instrumentos": desglose,
    }


def _serializar_cierre_caja(cierre: CierreCaja) -> dict[str, Any]:
    try:
        desglose = json.loads(cierre.desglose_instrumentos_json or "[]")
    except Exception:
        desglose = []
    return {
        "id": cierre.id,
        "fecha": cierre.fecha.isoformat(),
        "sucursal_id": cierre.sucursal_id,
        "sucursal": cierre.sucursal.nombre if cierre.sucursal else "Todas las sucursales",
        "usuario": cierre.usuario.nombre if cierre.usuario else "",
        "cantidad_ventas": cierre.cantidad_ventas,
        "cantidad_anulaciones": cierre.cantidad_anulaciones,
        "total_ventas_usd": redondear_usd(cierre.total_ventas_usd),
        "total_ingresos_usd": redondear_usd(cierre.total_ingresos_usd),
        "total_ingresos_bs": redondear_usd(cierre.total_ingresos_bs),
        "total_egresos_usd": redondear_usd(cierre.total_egresos_usd),
        "total_egresos_bs": redondear_usd(cierre.total_egresos_bs),
        "total_cashea_usd": redondear_usd(cierre.total_cashea_usd),
        "efectivo_esperado_usd": redondear_usd(cierre.efectivo_esperado_usd),
        "efectivo_declarado_usd": redondear_usd(cierre.efectivo_declarado_usd),
        "diferencia_usd": redondear_usd(cierre.diferencia_usd),
        "observaciones": cierre.observaciones,
        "desglose_instrumentos": desglose,
        "creado_en": cierre.creado_en.isoformat() if cierre.creado_en else None,
    }


@enrutador.get("/cierre-caja/preview")
def preview_cierre_caja(
    fecha: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    fecha_op = fecha or obtener_fecha_hoy()
    return _calcular_preview_cierre_caja(bd, fecha_op=fecha_op, sucursal_id=sucursal_id)


@enrutador.get("/cierre-caja")
def listar_cierres_caja(
    sucursal_id: int | None = Query(default=None),
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    consulta = (
        bd.query(CierreCaja)
        .options(joinedload(CierreCaja.sucursal), joinedload(CierreCaja.usuario))
        .order_by(CierreCaja.fecha.desc(), CierreCaja.id.desc())
    )
    if sucursal_id is not None:
        consulta = consulta.filter(CierreCaja.sucursal_id == sucursal_id)
    return [_serializar_cierre_caja(c) for c in consulta.all()]


@enrutador.post("/cierre-caja", status_code=status.HTTP_201_CREATED)
def guardar_cierre_caja(
    datos: CierreCajaCrearEntrada,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    fecha_op = datos.fecha or obtener_fecha_hoy()
    preview = _calcular_preview_cierre_caja(bd, fecha_op=fecha_op, sucursal_id=datos.sucursal_id)

    esperado = Decimal(str(preview["efectivo_esperado_usd"]))
    declarado = datos.efectivo_declarado_usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    diferencia = (declarado - esperado).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    cierre = CierreCaja(
        fecha=fecha_op,
        sucursal_id=datos.sucursal_id,
        usuario_id=usuario_actual.id,
        cantidad_ventas=preview["cantidad_ventas"],
        cantidad_anulaciones=preview["cantidad_anulaciones"],
        total_ventas_usd=Decimal(str(preview["total_ventas_usd"])),
        total_ingresos_usd=Decimal(str(preview["total_ingresos_usd"])),
        total_ingresos_bs=Decimal(str(preview["total_ingresos_bs"])),
        total_egresos_usd=Decimal(str(preview["total_egresos_usd"])),
        total_egresos_bs=Decimal(str(preview["total_egresos_bs"])),
        total_cashea_usd=Decimal(str(preview["total_cashea_usd"])),
        desglose_instrumentos_json=json.dumps(preview["desglose_instrumentos"], ensure_ascii=False),
        efectivo_esperado_usd=esperado,
        efectivo_declarado_usd=declarado,
        diferencia_usd=diferencia,
        observaciones=datos.observaciones.strip(),
    )
    bd.add(cierre)
    bd.commit()

    cierre_completo = (
        bd.query(CierreCaja)
        .options(joinedload(CierreCaja.sucursal), joinedload(CierreCaja.usuario))
        .filter(CierreCaja.id == cierre.id)
        .first()
    )
    return _serializar_cierre_caja(cierre_completo)


@enrutador.get("/cierre-caja/{cierre_id}/pdf")
def descargar_pdf_cierre_caja(
    cierre_id: int,
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> Response:
    cierre = (
        bd.query(CierreCaja)
        .options(joinedload(CierreCaja.sucursal), joinedload(CierreCaja.usuario))
        .filter(CierreCaja.id == cierre_id)
        .first()
    )
    if cierre is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cierre de caja no encontrado.")

    pdf_bytes = generar_pdf_cierre_caja(cierre)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="cierre-caja-{cierre.fecha.isoformat()}-{cierre.id}.pdf"'},
    )
