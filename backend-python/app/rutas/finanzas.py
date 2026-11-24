from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import extract
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.esquemas_finanzas import (
    AbonoCxcEntrada,
    CasheaLiquidarEntrada,
    CierreMensualEntrada,
    CruceManualEntrada,
    PagoConfirmarEntrada,
)
from app.modelos import RolUsuario, TasaDiaria, Usuario
from app.modelos_finanzas import (
    CierreMensual,
    CuentaPorCobrar,
    EstadoCuentaPorCobrar,
    EstadoVenta,
    EstadoVerificacionPago,
    ExtractoBancario,
    InstrumentoFinanciero,
    MonedaInstrumento,
    Pago,
    TipoCuentaPorCobrar,
    TipoDocumentoPago,
    TipoMovimientoPago,
    Venta,
)
from app.modelos_taller import (
    CasoPostventa,
    EstadoCasoPostventa,
    Preparacion,
    TipoCasoPostventa,
)
from app.rutas.logistica import _leer_filas_archivo
from app.rutas.tasas import obtener_fecha_hoy
from app.rutas.ventas import redondear_usd, verificar_mes_abierto
from app.seguridad import ROLES_ADMINISTRATIVOS, obtener_usuario_actual, requerir_roles


enrutador = APIRouter(prefix="/api/finanzas", tags=["Finanzas, Conciliación y Cierres"])


# ---------------- Instrumentos y Pagos ----------------

@enrutador.get("/instrumentos")
def listar_instrumentos(
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    filas = (
        bd.query(InstrumentoFinanciero)
        .filter(InstrumentoFinanciero.activo.is_(True))
        .order_by(InstrumentoFinanciero.id.asc())
        .all()
    )
    return [
        {
            "id": i.id,
            "nombre": i.nombre,
            "moneda": i.moneda,
            "tipo_precio": i.tipo_precio,
            "requiere_verificacion": i.requiere_verificacion,
            "liquida_en_bs": i.liquida_en_bs,
        }
        for i in filas
    ]


@enrutador.get("/pagos")
def listar_pagos(
    estado_verificacion: EstadoVerificacionPago | None = Query(default=None),
    instrumento_id: int | None = Query(default=None),
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    consulta = (
        bd.query(Pago)
        .options(
            joinedload(Pago.instrumento),
            joinedload(Pago.venta),
            joinedload(Pago.verificado_por),
        )
        .filter(Pago.anulado.is_(False))
    )
    if estado_verificacion is not None:
        consulta = consulta.filter(Pago.estado_verificacion == estado_verificacion.value)
    if instrumento_id is not None:
        consulta = consulta.filter(Pago.instrumento_id == instrumento_id)

    pagos = consulta.order_by(Pago.id.desc()).limit(150).all()
    return [
        {
            "id": p.id,
            "venta_id": p.venta_id,
            "numero_venta": p.venta.numero_venta if p.venta else None,
            "instrumento_id": p.instrumento_id,
            "instrumento": p.instrumento.nombre if p.instrumento else None,
            "fecha": p.fecha.isoformat(),
            "tipo_documento": p.tipo_documento,
            "monto_moneda_origen": redondear_usd(p.monto_moneda_origen),
            "moneda": p.moneda,
            "usd_nominal": redondear_usd(p.usd_nominal),
            "usd_real": redondear_usd(p.usd_real),
            "referencia": p.referencia,
            "estado_verificacion": p.estado_verificacion,
            "verificado_por": p.verificado_por.nombre if p.verificado_por else None,
            "conciliado": p.conciliado,
            "nota": p.nota,
        }
        for p in pagos
    ]


@enrutador.patch("/pagos/{pago_id}/confirmar")
def confirmar_pago_digital(
    pago_id: int,
    datos: PagoConfirmarEntrada,
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_ADMINISTRATIVOS)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    pago = bd.query(Pago).filter(Pago.id == pago_id).first()
    if pago is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pago no encontrado.")

    verificar_mes_abierto(bd, pago.fecha)

    pago.estado_verificacion = (
        EstadoVerificacionPago.CONFIRMADO.value
        if datos.aprobado
        else EstadoVerificacionPago.PENDIENTE.value
    )
    pago.verificado_por_id = usuario_actual.id
    if datos.nota.strip():
        pago.nota = datos.nota.strip()
    bd.commit()

    return {
        "id": pago.id,
        "estado_verificacion": pago.estado_verificacion,
        "verificado_por": usuario_actual.nombre,
    }


# ---------------- Cuentas por Cobrar y Cashea ----------------

@enrutador.get("/cuentas-por-cobrar")
def listar_cuentas_por_cobrar(
    tipo: TipoCuentaPorCobrar | None = Query(default=None),
    estado: EstadoCuentaPorCobrar | None = Query(default=None),
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    consulta = bd.query(CuentaPorCobrar).options(
        joinedload(CuentaPorCobrar.venta).joinedload(Venta.sucursal),
        joinedload(CuentaPorCobrar.cliente),
    )
    if tipo is not None:
        consulta = consulta.filter(CuentaPorCobrar.tipo == tipo.value)
    if estado is not None:
        consulta = consulta.filter(CuentaPorCobrar.estado == estado.value)

    filas = consulta.order_by(CuentaPorCobrar.id.desc()).all()
    return [
        {
            "id": c.id,
            "venta_id": c.venta_id,
            "numero_venta": c.venta.numero_venta if c.venta else None,
            "sucursal": c.venta.sucursal.nombre if c.venta and c.venta.sucursal else None,
            "fecha_venta": c.venta.fecha.isoformat() if c.venta else None,
            "tipo": c.tipo,
            "cliente": c.cliente.nombre if c.cliente else "Cliente general",
            "monto_original_usd": redondear_usd(c.monto_original_usd),
            "saldo_pendiente_usd": redondear_usd(c.saldo_pendiente_usd),
            "estado": c.estado,
        }
        for c in filas
    ]


@enrutador.post("/cuentas-por-cobrar/{cxc_id}/abono")
def registrar_abono_cxc(
    cxc_id: int,
    datos: AbonoCxcEntrada,
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    fecha_op = datos.fecha or obtener_fecha_hoy()
    verificar_mes_abierto(bd, fecha_op)

    cxc = bd.query(CuentaPorCobrar).filter(CuentaPorCobrar.id == cxc_id).first()
    if cxc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta por cobrar no encontrada.")
    if cxc.estado != EstadoCuentaPorCobrar.PENDIENTE.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Esta cuenta ya no está pendiente.")

    inst = bd.query(InstrumentoFinanciero).filter(InstrumentoFinanciero.id == datos.instrumento_id).first()
    if inst is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instrumento no encontrado.")

    tasa = bd.query(TasaDiaria).filter(TasaDiaria.fecha == fecha_op).first()
    if inst.moneda == MonedaInstrumento.BS.value and tasa is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No existe tasa del día para registrar abonos en bolívares.",
        )

    tasa_bcv = tasa.tasa_bcv if tasa else Decimal("0")
    tasa_usdt = tasa.tasa_usdt if tasa else Decimal("0")

    if inst.moneda == MonedaInstrumento.BS.value:
        usd_nominal = (datos.monto_moneda_origen / tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        usd_real = (datos.monto_moneda_origen / tasa_usdt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if tasa_usdt > 0 else usd_nominal
    else:
        usd_nominal = datos.monto_moneda_origen
        usd_real = datos.monto_moneda_origen

    bd.add(
        Pago(
            venta_id=cxc.venta_id,
            instrumento_id=inst.id,
            fecha=fecha_op,
            tipo_movimiento=TipoMovimientoPago.INGRESO.value,
            tipo_documento=TipoDocumentoPago.ABONO.value,
            monto_moneda_origen=datos.monto_moneda_origen,
            moneda=inst.moneda,
            tasa_bcv_dia=tasa_bcv,
            tasa_usdt_dia=tasa_usdt,
            usd_nominal=usd_nominal,
            usd_real=usd_real,
            cubre_promo_usd=usd_nominal,
            referencia=datos.referencia.strip(),
            estado_verificacion=(
                EstadoVerificacionPago.PENDIENTE.value
                if inst.requiere_verificacion
                else EstadoVerificacionPago.CONFIRMADO.value
            ),
        )
    )

    cxc.saldo_pendiente_usd = max(Decimal("0"), cxc.saldo_pendiente_usd - usd_nominal)
    if cxc.saldo_pendiente_usd <= Decimal("0.50"):
        cxc.saldo_pendiente_usd = Decimal("0")
        cxc.estado = EstadoCuentaPorCobrar.PAGADA.value
        venta = bd.query(Venta).filter(Venta.id == cxc.venta_id).first()
        if venta and venta.estado == EstadoVenta.CON_SALDO.value:
            venta.estado = EstadoVenta.CUADRADA.value

    bd.commit()
    return {
        "id": cxc.id,
        "saldo_pendiente_usd": redondear_usd(cxc.saldo_pendiente_usd),
        "estado": cxc.estado,
    }


@enrutador.post("/cashea/liquidar")
def liquidar_cashea(
    datos: CasheaLiquidarEntrada,
    _usuario: Usuario = Depends(requerir_roles(*ROLES_ADMINISTRATIVOS)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    verificar_mes_abierto(bd, datos.fecha_pago)

    tasa = bd.query(TasaDiaria).filter(TasaDiaria.fecha == datos.fecha_pago).first()
    if tasa is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No existe tasa BCV registrada para la fecha de pago de Cashea.",
        )

    destino = (
        bd.query(InstrumentoFinanciero)
        .filter(InstrumentoFinanciero.id == datos.instrumento_destino_id)
        .first()
    )
    if destino is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instrumento destino no encontrado.")

    cuentas = (
        bd.query(CuentaPorCobrar)
        .filter(
            CuentaPorCobrar.id.in_(datos.cuentas_cashea_ids),
            CuentaPorCobrar.tipo == TipoCuentaPorCobrar.CASHEA.value,
            CuentaPorCobrar.estado == EstadoCuentaPorCobrar.PENDIENTE.value,
        )
        .all()
    )
    if not cuentas:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontraron cuentas Cashea pendientes con los IDs indicados.",
        )

    total_bruto_usd = sum((c.saldo_pendiente_usd for c in cuentas), Decimal("0"))
    neto_usd = max(Decimal("0"), total_bruto_usd - datos.comision_usd - datos.impuestos_usd)

    if destino.moneda == MonedaInstrumento.BS.value:
        monto_origen = (neto_usd * tasa.tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        usd_real = (monto_origen / tasa.tasa_usdt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if tasa.tasa_usdt > 0 else neto_usd
    else:
        monto_origen = neto_usd
        usd_real = neto_usd

    bd.add(
        Pago(
            venta_id=None,
            instrumento_id=destino.id,
            fecha=datos.fecha_pago,
            tipo_movimiento=TipoMovimientoPago.TRASLADO.value,
            tipo_documento=TipoDocumentoPago.CASHEA.value,
            monto_moneda_origen=monto_origen,
            moneda=destino.moneda,
            tasa_bcv_dia=tasa.tasa_bcv,
            tasa_usdt_dia=tasa.tasa_usdt,
            usd_nominal=neto_usd,
            usd_real=usd_real,
            cubre_promo_usd=neto_usd,
            referencia=datos.referencia.strip(),
            estado_verificacion=EstadoVerificacionPago.CONFIRMADO.value,
            nota=(
                f"Liquidación Cashea ({len(cuentas)} notas) · Bruto ${redondear_usd(total_bruto_usd):.2f} "
                f"- Com ${redondear_usd(datos.comision_usd):.2f} - Imp ${redondear_usd(datos.impuestos_usd):.2f}"
            ),
        )
    )

    for c in cuentas:
        c.saldo_pendiente_usd = Decimal("0")
        c.estado = EstadoCuentaPorCobrar.PAGADA.value

    bd.commit()
    return {
        "cuentas_liquidadas": len(cuentas),
        "total_bruto_usd": redondear_usd(total_bruto_usd),
        "neto_depositado_usd": redondear_usd(neto_usd),
        "monto_moneda_destino": redondear_usd(monto_origen),
        "moneda_destino": destino.moneda,
    }


# ---------------- Conciliación Bancaria (CSV / Excel) ----------------

@enrutador.post("/conciliacion/importar")
async def importar_conciliacion(
    instrumento_id: int = Form(...),
    archivo: UploadFile = File(...),
    _usuario: Usuario = Depends(requerir_roles(*ROLES_ADMINISTRATIVOS)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    inst = bd.query(InstrumentoFinanciero).filter(InstrumentoFinanciero.id == instrumento_id).first()
    if inst is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instrumento no encontrado.")

    contenido = await archivo.read()
    filas = _leer_filas_archivo(archivo.filename or "extracto.csv", contenido)

    extractos_creados: list[ExtractoBancario] = []
    for fila in filas:
        raw_fecha = fila.get("fecha") or obtener_fecha_hoy().isoformat()
        try:
            fecha_ext = date.fromisoformat(raw_fecha[:10])
        except ValueError:
            fecha_ext = obtener_fecha_hoy()

        raw_monto = fila.get("monto_con_signo") or fila.get("monto") or fila.get("credito") or "0"
        try:
            monto_dec = Decimal(raw_monto.replace(",", ".")).quantize(Decimal("0.01"))
        except Exception:
            monto_dec = Decimal("0")

        ext = ExtractoBancario(
            instrumento_id=instrumento_id,
            fecha=fecha_ext,
            referencia=(fila.get("referencia") or fila.get("ref") or "").strip(),
            descripcion=(fila.get("descripcion") or fila.get("concepto") or "").strip(),
            monto_con_signo=monto_dec,
            conciliado=False,
        )
        bd.add(ext)
        bd.flush()
        extractos_creados.append(ext)

    # Cruce automático por instrumento + referencia + monto exacto
    pagos_pendientes = (
        bd.query(Pago)
        .filter(
            Pago.instrumento_id == instrumento_id,
            Pago.anulado.is_(False),
            Pago.conciliado.is_(False),
        )
        .all()
    )

    cuadrados = []
    for ext in extractos_creados:
        if not ext.referencia:
            continue
        match = next(
            (
                p
                for p in pagos_pendientes
                if not p.conciliado
                and p.referencia.strip().lower() == ext.referencia.strip().lower()
                and abs(p.monto_moneda_origen - abs(ext.monto_con_signo)) <= Decimal("0.05")
            ),
            None,
        )
        if match is not None:
            match.conciliado = True
            match.extracto_id = ext.id
            ext.conciliado = True
            cuadrados.append(
                {
                    "pago_id": match.id,
                    "extracto_id": ext.id,
                    "referencia": ext.referencia,
                    "monto": redondear_usd(match.monto_moneda_origen),
                }
            )

    bd.commit()

    sin_banco = [
        {
            "pago_id": p.id,
            "fecha": p.fecha.isoformat(),
            "referencia": p.referencia,
            "monto": redondear_usd(p.monto_moneda_origen),
        }
        for p in pagos_pendientes
        if not p.conciliado
    ]
    sin_sistema = [
        {
            "extracto_id": e.id,
            "fecha": e.fecha.isoformat(),
            "referencia": e.referencia,
            "descripcion": e.descripcion,
            "monto": redondear_usd(e.monto_con_signo),
        }
        for e in extractos_creados
        if not e.conciliado
    ]

    return {
        "cuadrados": cuadrados,
        "registrados_sin_banco": sin_banco,
        "en_banco_sin_registrar": sin_sistema,
    }


@enrutador.post("/conciliacion/cruzar-manual")
def cruzar_conciliacion_manual(
    datos: CruceManualEntrada,
    _usuario: Usuario = Depends(requerir_roles(*ROLES_ADMINISTRATIVOS)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    pago = bd.query(Pago).filter(Pago.id == datos.pago_id).first()
    extracto = bd.query(ExtractoBancario).filter(ExtractoBancario.id == datos.extracto_id).first()
    if pago is None or extracto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pago o extracto no encontrado.")

    pago.conciliado = True
    pago.extracto_id = extracto.id
    extracto.conciliado = True
    bd.commit()
    return {"pago_id": pago.id, "extracto_id": extracto.id, "conciliado": True}


# ---------------- Comisiones, Tablero y Cierre Mensual ----------------

def calcular_reporte_comisiones(
    bd: Session, mes: int, anio: int, sucursal_id: int | None = None
) -> list[dict[str, Any]]:
    usuarios = bd.query(Usuario).filter(Usuario.activo.is_(True)).all()
    usuarios_map = {u.id: u for u in usuarios}

    consulta_ventas = bd.query(Venta).filter(
        Venta.estado != EstadoVenta.ANULADA.value,
        extract("month", Venta.fecha) == mes,
        extract("year", Venta.fecha) == anio,
    )
    if sucursal_id is not None:
        consulta_ventas = consulta_ventas.filter(Venta.sucursal_id == sucursal_id)
    ventas = consulta_ventas.all()

    ventas_por_asesor: dict[int, Decimal] = {}
    total_ventas_con_asesor = Decimal("0")
    for v in ventas:
        if v.asesor_id is not None:
            ventas_por_asesor[v.asesor_id] = ventas_por_asesor.get(v.asesor_id, Decimal("0")) + v.total_promo_usd
            total_ventas_con_asesor += v.total_promo_usd

    # Preparaciones y servicios técnicos del mes
    preparaciones = (
        bd.query(Preparacion)
        .filter(
            extract("month", Preparacion.fecha) == mes,
            extract("year", Preparacion.fecha) == anio,
        )
        .all()
    )
    prep_por_tecnico: dict[int, Decimal] = {}
    for p in preparaciones:
        prep_por_tecnico[p.tecnico_id] = prep_por_tecnico.get(p.tecnico_id, Decimal("0")) + p.pago_tecnico_usd

    estados_st = {
        EstadoCasoPostventa.TERMINADO.value,
        EstadoCasoPostventa.LISTO_PARA_ENTREGAR.value,
        EstadoCasoPostventa.ENTREGADO.value,
    }
    casos_st = (
        bd.query(CasoPostventa)
        .options(joinedload(CasoPostventa.presupuestos))
        .filter(
            CasoPostventa.tipo == TipoCasoPostventa.SERVICIO.value,
            CasoPostventa.estado.in_(estados_st),
            extract("month", CasoPostventa.fecha_ingreso) == mes,
            extract("year", CasoPostventa.fecha_ingreso) == anio,
        )
        .all()
    )
    st_por_tecnico: dict[int, Decimal] = {}
    for c in casos_st:
        if c.tecnico_id is None:
            continue
        pres_aprob = next((pr for pr in c.presupuestos if pr.aprobado_cliente is True), None)
        if pres_aprob is not None:
            com_50 = (pres_aprob.mano_obra_usd * Decimal("0.50")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            st_por_tecnico[c.tecnico_id] = st_por_tecnico.get(c.tecnico_id, Decimal("0")) + com_50

    reporte: list[dict[str, Any]] = []
    for uid, u in usuarios_map.items():
        ventas_propias = ventas_por_asesor.get(uid, Decimal("0"))
        com_ventas_1 = (ventas_propias * Decimal("0.01")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        com_lider_05 = Decimal("0")
        if u.rol == RolUsuario.LIDER.value:
            ventas_equipo_resto = max(Decimal("0"), total_ventas_con_asesor - ventas_propias)
            com_lider_05 = (ventas_equipo_resto * Decimal("0.005")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

        com_servicios = st_por_tecnico.get(uid, Decimal("0"))
        pago_preps = prep_por_tecnico.get(uid, Decimal("0"))
        total_persona = com_ventas_1 + com_lider_05 + com_servicios + pago_preps

        if total_persona > 0 or u.rol in (
            RolUsuario.ASESORA.value,
            RolUsuario.LIDER.value,
            RolUsuario.TECNICO.value,
        ):
            reporte.append(
                {
                    "usuario_id": uid,
                    "nombre": u.nombre,
                    "rol": u.rol,
                    "ventas_promo_usd": redondear_usd(ventas_propias),
                    "comision_ventas_1_usd": redondear_usd(com_ventas_1),
                    "comision_lider_05_usd": redondear_usd(com_lider_05),
                    "comision_servicios_50_usd": redondear_usd(com_servicios),
                    "pago_preparaciones_usd": redondear_usd(pago_preps),
                    "total_comision_usd": redondear_usd(total_persona),
                }
            )

    return reporte


@enrutador.get("/comisiones")
def obtener_comisiones(
    mes: int | None = Query(default=None, ge=1, le=12),
    anio: int | None = Query(default=None, ge=2020, le=2100),
    sucursal_id: int | None = Query(default=None),
    _usuario: Usuario = Depends(requerir_roles(*ROLES_ADMINISTRATIVOS)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    hoy = obtener_fecha_hoy()
    mes_obj = mes or hoy.month
    anio_obj = anio or hoy.year
    reporte = calcular_reporte_comisiones(bd, mes_obj, anio_obj, sucursal_id)
    cierre = (
        bd.query(CierreMensual)
        .filter(CierreMensual.anio == anio_obj, CierreMensual.mes == mes_obj)
        .first()
    )
    return {
        "mes": mes_obj,
        "anio": anio_obj,
        "mes_cerrado": bool(cierre and cierre.bloqueado),
        "comisiones": reporte,
    }


@enrutador.get("/tablero")
def obtener_tablero_financiero(
    desde: date | None = Query(default=None),
    hasta: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    _usuario: Usuario = Depends(requerir_roles(*ROLES_ADMINISTRATIVOS)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    hoy = obtener_fecha_hoy()
    f_desde = desde or date(hoy.year, hoy.month, 1)
    f_hasta = hasta or hoy

    consulta_ventas = (
        bd.query(Venta)
        .options(joinedload(Venta.detalles), joinedload(Venta.pagos))
        .filter(
            Venta.estado != EstadoVenta.ANULADA.value,
            Venta.fecha >= f_desde,
            Venta.fecha <= f_hasta,
        )
    )
    if sucursal_id is not None:
        consulta_ventas = consulta_ventas.filter(Venta.sucursal_id == sucursal_id)
    ventas = consulta_ventas.all()

    venta_promo = sum((v.total_promo_usd for v in ventas), Decimal("0"))
    usd_nominal = Decimal("0")
    usd_real = Decimal("0")
    costo_total = Decimal("0")

    for v in ventas:
        for d in v.detalles:
            costo_total += d.costo_total_snapshot_usd
        for p in v.pagos:
            if not p.anulado:
                usd_nominal += p.usd_nominal
                usd_real += p.usd_real

    diferencial = usd_nominal - usd_real
    utilidad_real = usd_real - costo_total

    cashea_pendiente = sum(
        (
            c.saldo_pendiente_usd
            for c in bd.query(CuentaPorCobrar)
            .filter(
                CuentaPorCobrar.tipo == TipoCuentaPorCobrar.CASHEA.value,
                CuentaPorCobrar.estado == EstadoCuentaPorCobrar.PENDIENTE.value,
            )
            .all()
        ),
        Decimal("0"),
    )

    return {
        "desde": f_desde.isoformat(),
        "hasta": f_hasta.isoformat(),
        "cantidad_ventas": len(ventas),
        "venta_promo_usd": redondear_usd(venta_promo),
        "usd_nominal": redondear_usd(usd_nominal),
        "usd_real": redondear_usd(usd_real),
        "diferencial_cambiario_usd": redondear_usd(diferencial),
        "cashea_por_cobrar_usd": redondear_usd(cashea_pendiente),
        "costo_total_usd": redondear_usd(costo_total),
        "utilidad_real_neta_usd": redondear_usd(utilidad_real),
    }


@enrutador.post("/cierres-mensuales", status_code=status.HTTP_201_CREATED)
def cerrar_mes(
    datos: CierreMensualEntrada,
    usuario_actual: Usuario = Depends(requerir_roles(RolUsuario.DIRECCION.value)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    existente = (
        bd.query(CierreMensual)
        .filter(CierreMensual.anio == datos.anio, CierreMensual.mes == datos.mes)
        .first()
    )
    if existente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El mes {datos.mes:02d}/{datos.anio} ya fue cerrado.",
        )

    comisiones = calcular_reporte_comisiones(bd, datos.mes, datos.anio)
    resumen = {
        "mes": datos.mes,
        "anio": datos.anio,
        "comisiones": comisiones,
    }
    cierre = CierreMensual(
        anio=datos.anio,
        mes=datos.mes,
        cerrado_por_id=usuario_actual.id,
        resumen_json=json.dumps(resumen, ensure_ascii=False),
        bloqueado=True,
    )
    bd.add(cierre)
    bd.commit()
    bd.refresh(cierre)
    return {
        "id": cierre.id,
        "anio": cierre.anio,
        "mes": cierre.mes,
        "bloqueado": cierre.bloqueado,
        "cerrado_por": usuario_actual.nombre,
    }
