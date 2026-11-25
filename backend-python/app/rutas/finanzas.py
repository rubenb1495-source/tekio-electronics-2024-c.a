from __future__ import annotations

import calendar
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
from app.modelos import RolUsuario, TasaDiaria, TipoArticulo, Usuario
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
    VentaDetalle,
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
from app.core.permisos import (
    Permiso,
    es_rol_admin,
    require_permiso,
    validar_sucursal_permitida,
)
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
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
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
    usuario_actual: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
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
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
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
    resultado: list[dict[str, Any]] = []
    for c in filas:
        v = c.venta
        total_reg = v.total_regular_usd if v else c.monto_original_usd
        precio_reg_bs = (
            v.precio_regular_bs
            if v and getattr(v, "precio_regular_bs", Decimal("0")) > 0
            else (
                (total_reg * v.tasa_bcv_snapshot).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if v and v.tasa_bcv_snapshot > 0
                else Decimal("0.00")
            )
        )
        com_tot = (
            v.comision_cashea_venta_total_usd
            if v and getattr(v, "comision_cashea_venta_total_usd", Decimal("0")) > 0
            else (total_reg * Decimal("0.04")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
        com_fin = (
            v.comision_cashea_financiado_usd
            if v and getattr(v, "comision_cashea_financiado_usd", Decimal("0")) > 0
            else (c.monto_original_usd * Decimal("0.04")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
        iva_c = (
            v.iva_cashea_usd
            if v and getattr(v, "iva_cashea_usd", Decimal("0")) > 0
            else (com_tot * Decimal("0.16")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
        islr_c = (
            v.islr_cashea_usd
            if v and getattr(v, "islr_cashea_usd", Decimal("0")) > 0
            else (com_tot * Decimal("0.02")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
        tot_ded = (com_tot + com_fin + iva_c + islr_c).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        neto_esp = max(Decimal("0.00"), (c.saldo_pendiente_usd - tot_ded).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        resultado.append(
            {
                "id": c.id,
                "venta_id": c.venta_id,
                "numero_venta": v.numero_venta if v else None,
                "sucursal": v.sucursal.nombre if v and v.sucursal else None,
                "fecha_venta": v.fecha.isoformat() if v else None,
                "tipo": c.tipo,
                "cliente": c.cliente.nombre if c.cliente else "Cliente general",
                "monto_original_usd": redondear_usd(c.monto_original_usd),
                "saldo_pendiente_usd": redondear_usd(c.saldo_pendiente_usd),
                "total_regular_usd": redondear_usd(total_reg),
                "precio_regular_bs": redondear_usd(precio_reg_bs),
                "comision_cashea_venta_total_usd": redondear_usd(com_tot),
                "comision_cashea_financiado_usd": redondear_usd(com_fin),
                "iva_cashea_usd": redondear_usd(iva_c),
                "islr_cashea_usd": redondear_usd(islr_c),
                "total_deducciones_cashea_usd": redondear_usd(tot_ded),
                "neto_esperado_cashea_usd": redondear_usd(neto_esp),
                "estado": c.estado,
            }
        )
    return resultado


@enrutador.post("/cuentas-por-cobrar/{cxc_id}/abono")
def registrar_abono_cxc(
    cxc_id: int,
    datos: AbonoCxcEntrada,
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
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

    if usd_nominal > Decimal("0.00"):
        from app.servicios.contabilidad_service import registrar_asiento

        cta_cxc = "1.1.03" if cxc.tipo == TipoCuentaPorCobrar.CASHEA.value else "1.1.02"
        registrar_asiento(
            bd,
            fecha=fecha_op,
            referencia=datos.referencia.strip() or f"CXC-{cxc.id}",
            modulo_origen="COBROS",
            entidad_id=cxc.id,
            descripcion=f"Abono a cuenta por cobrar #{cxc.id} ({cxc.tipo})",
            lineas=[
                {"codigo_cuenta": "1.1.01", "debe_usd": usd_nominal, "descripcion": f"Ingreso por {inst.nombre}"},
                {"codigo_cuenta": cta_cxc, "haber_usd": usd_nominal, "descripcion": f"Cancelación CxC #{cxc.id}"},
            ],
            creado_por_id=_usuario.id,
        )

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

def calcular_reporte_comisiones_rango(
    bd: Session,
    fecha_inicio: date,
    fecha_fin: date,
    sucursal_id: int | None = None,
    usuario_id: int | None = None,
    estado: str = "TODAS",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    usuarios = bd.query(Usuario).filter(Usuario.activo.is_(True)).all()
    usuarios_map = {u.id: u for u in usuarios}

    consulta_ventas_globales = (
        bd.query(Venta)
        .options(
            joinedload(Venta.cliente),
            joinedload(Venta.sucursal),
            joinedload(Venta.asesor),
            joinedload(Venta.tecnico),
            joinedload(Venta.detalles).joinedload(VentaDetalle.articulo),
        )
        .filter(
            Venta.estado.notin_([EstadoVenta.ANULADA.value, EstadoVenta.DEVUELTA.value]),
            Venta.fecha >= fecha_inicio,
            Venta.fecha <= fecha_fin,
        )
        .order_by(Venta.fecha.desc(), Venta.id.desc())
    )
    ventas_globales = consulta_ventas_globales.all()
    ventas = (
        [v for v in ventas_globales if v.sucursal_id == sucursal_id]
        if sucursal_id is not None
        else ventas_globales
    )

    # Todas las comisiones se calculan estrictamente sobre Precio Promo USD pactado:
    # - Productos/equipos/componentes -> 1% al asesor_id (0% si Tienda; obsequios $0 -> $0 comisión).
    # - Asesor Líder (multi-tienda) -> 1% propio + 0.5% de todos los demás asesores en TODAS las sucursales (excluyendo ST).
    # - Servicio Técnico / Mano de Obra (TipoArticulo.SERVICIO) -> 50% al tecnico_id (excluido de 1% asesor y 0.5% líder).
    ventas_por_asesor: dict[int, Decimal] = {}
    ventas_globales_por_asesor: dict[int, Decimal] = {}
    cantidad_ventas_asesor: dict[int, int] = {}
    cantidad_ops_usuario: dict[int, int] = {}
    notas_por_usuario: dict[int, list[str]] = {}
    total_ventas_con_asesor_global = Decimal("0")
    st_por_tecnico: dict[int, Decimal] = {}
    operaciones_detalle: list[dict[str, Any]] = []

    def _registrar_nota(uid: int, numero: str) -> None:
        lista = notas_por_usuario.setdefault(uid, [])
        if numero and numero not in lista:
            lista.append(numero)

    for v in ventas_globales:
        if not v.detalles:
            if v.asesor_id is not None:
                ventas_globales_por_asesor[v.asesor_id] = (
                    ventas_globales_por_asesor.get(v.asesor_id, Decimal("0")) + v.total_promo_usd
                )
                total_ventas_con_asesor_global += v.total_promo_usd
            continue

        for det in v.detalles:
            subtotal_promo = det.precio_promo_usd * Decimal(det.cantidad)
            es_servicio = det.articulo is not None and det.articulo.tipo == TipoArticulo.SERVICIO.value
            if not es_servicio and v.asesor_id is not None:
                ventas_globales_por_asesor[v.asesor_id] = (
                    ventas_globales_por_asesor.get(v.asesor_id, Decimal("0")) + subtotal_promo
                )
                total_ventas_con_asesor_global += subtotal_promo

    for v in ventas:
        cliente_nom = v.cliente.nombre if v.cliente else "Cliente general"
        suc_nom = v.sucursal.nombre if v.sucursal else ""

        if not v.detalles:
            if v.asesor_id is not None and v.total_promo_usd > 0:
                ventas_por_asesor[v.asesor_id] = (
                    ventas_por_asesor.get(v.asesor_id, Decimal("0")) + v.total_promo_usd
                )
                cantidad_ventas_asesor[v.asesor_id] = cantidad_ventas_asesor.get(v.asesor_id, 0) + 1
                cantidad_ops_usuario[v.asesor_id] = cantidad_ops_usuario.get(v.asesor_id, 0) + 1
                _registrar_nota(v.asesor_id, v.numero_venta)
                com_v = (v.total_promo_usd * Decimal("0.01")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                u_as = usuarios_map.get(v.asesor_id)
                operaciones_detalle.append(
                    {
                        "venta_id": v.id,
                        "numero_nota": v.numero_venta,
                        "fecha": v.fecha.isoformat(),
                        "cliente": cliente_nom,
                        "sucursal": suc_nom,
                        "usuario_id": v.asesor_id,
                        "usuario_nombre": u_as.nombre if u_as else (v.asesor.nombre if v.asesor else "Asesor"),
                        "rol": u_as.rol if u_as else "",
                        "tipo": "VENTA_1%",
                        "base_promo_usd": redondear_usd(v.total_promo_usd),
                        "comision_usd": redondear_usd(com_v),
                    }
                )
            continue

        base_prod_venta = Decimal("0")
        base_st_venta = Decimal("0")
        for det in v.detalles:
            subtotal_promo = det.precio_promo_usd * Decimal(det.cantidad)
            es_servicio = det.articulo is not None and det.articulo.tipo == TipoArticulo.SERVICIO.value
            if es_servicio:
                base_st_venta += subtotal_promo
            else:
                base_prod_venta += subtotal_promo

        if base_prod_venta > 0 and v.asesor_id is not None:
            ventas_por_asesor[v.asesor_id] = (
                ventas_por_asesor.get(v.asesor_id, Decimal("0")) + base_prod_venta
            )
            cantidad_ventas_asesor[v.asesor_id] = cantidad_ventas_asesor.get(v.asesor_id, 0) + 1
            cantidad_ops_usuario[v.asesor_id] = cantidad_ops_usuario.get(v.asesor_id, 0) + 1
            _registrar_nota(v.asesor_id, v.numero_venta)
            com_v = (base_prod_venta * Decimal("0.01")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            u_as = usuarios_map.get(v.asesor_id)
            operaciones_detalle.append(
                {
                    "venta_id": v.id,
                    "numero_nota": v.numero_venta,
                    "fecha": v.fecha.isoformat(),
                    "cliente": cliente_nom,
                    "sucursal": suc_nom,
                    "usuario_id": v.asesor_id,
                    "usuario_nombre": u_as.nombre if u_as else (v.asesor.nombre if v.asesor else "Asesor"),
                    "rol": u_as.rol if u_as else "",
                    "tipo": "VENTA_1%",
                    "base_promo_usd": redondear_usd(base_prod_venta),
                    "comision_usd": redondear_usd(com_v),
                }
            )

        if base_st_venta > 0 and v.tecnico_id is not None:
            com_50 = (base_st_venta * Decimal("0.50")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            st_por_tecnico[v.tecnico_id] = st_por_tecnico.get(v.tecnico_id, Decimal("0")) + com_50
            cantidad_ops_usuario[v.tecnico_id] = cantidad_ops_usuario.get(v.tecnico_id, 0) + 1
            _registrar_nota(v.tecnico_id, v.numero_venta)
            u_tec = usuarios_map.get(v.tecnico_id)
            operaciones_detalle.append(
                {
                    "venta_id": v.id,
                    "numero_nota": v.numero_venta,
                    "fecha": v.fecha.isoformat(),
                    "cliente": cliente_nom,
                    "sucursal": suc_nom,
                    "usuario_id": v.tecnico_id,
                    "usuario_nombre": u_tec.nombre if u_tec else (v.tecnico.nombre if v.tecnico else "Técnico"),
                    "rol": u_tec.rol if u_tec else "",
                    "tipo": "SERVICIO_TECNICO_50%",
                    "base_promo_usd": redondear_usd(base_st_venta),
                    "comision_usd": redondear_usd(com_50),
                }
            )

    # Ajustes de comisión por cambios Upgrade (+) y Downgrade (-) del período
    from app.modelos_operaciones import DevolucionGarantia, TipoResolucionDevolucion

    ajustes_dev = (
        bd.query(DevolucionGarantia)
        .options(
            joinedload(DevolucionGarantia.venta).joinedload(Venta.cliente),
            joinedload(DevolucionGarantia.venta).joinedload(Venta.sucursal),
        )
        .filter(
            DevolucionGarantia.tipo_resolucion.in_(
                [
                    TipoResolucionDevolucion.CAMBIO_UPGRADE.value,
                    TipoResolucionDevolucion.CAMBIO_DOWNGRADE.value,
                ]
            ),
            DevolucionGarantia.fecha >= fecha_inicio,
            DevolucionGarantia.fecha <= fecha_fin,
        )
        .all()
    )
    for dev in ajustes_dev:
        vta = dev.venta
        if vta is None or vta.asesor_id is None:
            continue
        if vta.estado in (EstadoVenta.ANULADA.value, EstadoVenta.DEVUELTA.value):
            continue
        dif = dev.diferencia_promo_usd or Decimal("0")
        ventas_globales_por_asesor[vta.asesor_id] = max(
            Decimal("0"),
            ventas_globales_por_asesor.get(vta.asesor_id, Decimal("0")) + dif,
        )
        total_ventas_con_asesor_global = max(Decimal("0"), total_ventas_con_asesor_global + dif)
        if sucursal_id is None or vta.sucursal_id == sucursal_id:
            ventas_por_asesor[vta.asesor_id] = max(
                Decimal("0"),
                ventas_por_asesor.get(vta.asesor_id, Decimal("0")) + dif,
            )
            cantidad_ops_usuario[vta.asesor_id] = cantidad_ops_usuario.get(vta.asesor_id, 0) + 1
            _registrar_nota(vta.asesor_id, dev.numero_operacion)
            com_dif = (dif * Decimal("0.01")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            u_as = usuarios_map.get(vta.asesor_id)
            operaciones_detalle.append(
                {
                    "numero_nota": dev.numero_operacion,
                    "fecha": dev.fecha.isoformat(),
                    "cliente": vta.cliente.nombre if vta.cliente else "Cliente general",
                    "sucursal": vta.sucursal.nombre if vta.sucursal else "",
                    "usuario_id": vta.asesor_id,
                    "usuario_nombre": u_as.nombre if u_as else "Asesor",
                    "rol": u_as.rol if u_as else "",
                    "tipo": "UPGRADE_1%" if dif >= 0 else "DOWNGRADE_1%",
                    "base_promo_usd": redondear_usd(dif),
                    "comision_usd": redondear_usd(com_dif),
                }
            )

    # Preparaciones y servicios técnicos del período
    preparaciones = (
        bd.query(Preparacion)
        .options(joinedload(Preparacion.equipo))
        .filter(
            Preparacion.fecha >= fecha_inicio,
            Preparacion.fecha <= fecha_fin,
        )
        .all()
    )
    prep_por_tecnico: dict[int, Decimal] = {}
    for p in preparaciones:
        prep_por_tecnico[p.tecnico_id] = prep_por_tecnico.get(p.tecnico_id, Decimal("0")) + p.pago_tecnico_usd
        cantidad_ops_usuario[p.tecnico_id] = cantidad_ops_usuario.get(p.tecnico_id, 0) + 1
        u_tec = usuarios_map.get(p.tecnico_id)
        serial_txt = p.equipo.serial if p.equipo else f"PREP-{p.id}"
        operaciones_detalle.append(
            {
                "numero_nota": f"PREP-{p.id}",
                "fecha": p.fecha.isoformat(),
                "cliente": f"Preparación ({serial_txt})",
                "sucursal": "",
                "usuario_id": p.tecnico_id,
                "usuario_nombre": u_tec.nombre if u_tec else "Técnico",
                "rol": u_tec.rol if u_tec else "",
                "tipo": "PREPARACION",
                "base_promo_usd": redondear_usd(p.pago_tecnico_usd),
                "comision_usd": redondear_usd(p.pago_tecnico_usd),
            }
        )

    estados_st = {
        EstadoCasoPostventa.TERMINADO.value,
        EstadoCasoPostventa.LISTO_PARA_ENTREGAR.value,
        EstadoCasoPostventa.ENTREGADO.value,
    }
    casos_st = (
        bd.query(CasoPostventa)
        .options(
            joinedload(CasoPostventa.presupuestos),
            joinedload(CasoPostventa.cliente),
            joinedload(CasoPostventa.sucursal),
        )
        .filter(
            CasoPostventa.tipo == TipoCasoPostventa.SERVICIO.value,
            CasoPostventa.estado.in_(estados_st),
        )
        .all()
    )
    for c in casos_st:
        if c.tecnico_id is None or c.fecha_ingreso is None:
            continue
        fecha_caso = c.fecha_ingreso.date()
        if fecha_caso < fecha_inicio or fecha_caso > fecha_fin:
            continue
        if sucursal_id is not None and c.sucursal_id != sucursal_id:
            continue
        pres_aprob = next((pr for pr in c.presupuestos if pr.aprobado_cliente is True), None)
        if pres_aprob is not None:
            com_50 = (pres_aprob.mano_obra_usd * Decimal("0.50")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            st_por_tecnico[c.tecnico_id] = st_por_tecnico.get(c.tecnico_id, Decimal("0")) + com_50
            cantidad_ops_usuario[c.tecnico_id] = cantidad_ops_usuario.get(c.tecnico_id, 0) + 1
            _registrar_nota(c.tecnico_id, c.numero_caso)
            u_tec = usuarios_map.get(c.tecnico_id)
            operaciones_detalle.append(
                {
                    "numero_nota": c.numero_caso,
                    "fecha": fecha_caso.isoformat(),
                    "cliente": c.cliente.nombre if c.cliente else "Cliente Taller",
                    "sucursal": c.sucursal.nombre if c.sucursal else "",
                    "usuario_id": c.tecnico_id,
                    "usuario_nombre": u_tec.nombre if u_tec else "Técnico",
                    "rol": u_tec.rol if u_tec else "",
                    "tipo": "SERVICIO_TECNICO_50%",
                    "base_promo_usd": redondear_usd(pres_aprob.mano_obra_usd),
                    "comision_usd": redondear_usd(com_50),
                }
            )

    # Cruzar contra liquidaciones_comisiones_detalle para marcar PENDIENTE vs PAGADA (anti-duplicados)
    from app.modelos_operaciones import LiquidacionComision, LiquidacionComisionDetalle

    detalles_liq = (
        bd.query(LiquidacionComisionDetalle)
        .options(joinedload(LiquidacionComisionDetalle.liquidacion))
        .all()
    )
    pagadas_por_venta: dict[tuple[int, int, str], str] = {}
    pagadas_por_ref: dict[tuple[str, int, str], str] = {}
    for dl in detalles_liq:
        cod_liq = dl.liquidacion.codigo if dl.liquidacion else f"LIQ-{dl.liquidacion_id}"
        if dl.venta_id is not None:
            pagadas_por_venta[(dl.venta_id, dl.usuario_id, dl.concepto)] = cod_liq
        if dl.referencia_origen:
            pagadas_por_ref[(dl.referencia_origen, dl.usuario_id, dl.concepto)] = cod_liq

    # Agregar líneas de 0,5% multi-tienda para los Líderes en las operaciones liquidables
    lideres = [u for u in usuarios_map.values() if u.rol == RolUsuario.LIDER.value]
    if lideres:
        for v in ventas_globales:
            if v.asesor_id is None:
                continue
            base_equipo_v = Decimal("0")
            if not v.detalles:
                base_equipo_v = v.total_promo_usd
            else:
                for det in v.detalles:
                    es_srv = det.articulo is not None and det.articulo.tipo == TipoArticulo.SERVICIO.value
                    if not es_srv:
                        base_equipo_v += det.precio_promo_usd * Decimal(det.cantidad)
            if base_equipo_v <= 0:
                continue
            com_05_v = (base_equipo_v * Decimal("0.005")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            for lid in lideres:
                if v.asesor_id == lid.id:
                    continue
                operaciones_detalle.append(
                    {
                        "venta_id": v.id,
                        "numero_nota": v.numero_venta,
                        "fecha": v.fecha.isoformat(),
                        "cliente": v.cliente.nombre if v.cliente else "Cliente general",
                        "sucursal": v.sucursal.nombre if v.sucursal else "",
                        "usuario_id": lid.id,
                        "usuario_nombre": lid.nombre,
                        "rol": lid.rol,
                        "tipo": "LIDER_0.5%",
                        "base_promo_usd": redondear_usd(base_equipo_v),
                        "comision_usd": redondear_usd(com_05_v),
                    }
                )

    pendiente_por_usuario: dict[int, Decimal] = {}
    pagado_por_usuario: dict[int, Decimal] = {}
    for op in operaciones_detalle:
        vid = op.get("venta_id")
        uid_op = int(op["usuario_id"])
        tipo_op = str(op["tipo"])
        ref_op = str(op.get("numero_nota") or "")
        cod_liq = (
            pagadas_por_venta.get((vid, uid_op, tipo_op))
            if vid is not None
            else None
        ) or pagadas_por_ref.get((ref_op, uid_op, tipo_op))
        if cod_liq:
            op["estado_comision"] = "PAGADA"
            op["liquidacion_codigo"] = cod_liq
            pagado_por_usuario[uid_op] = pagado_por_usuario.get(uid_op, Decimal("0")) + Decimal(str(op["comision_usd"]))
        else:
            op["estado_comision"] = "PENDIENTE"
            op["liquidacion_codigo"] = None
            pendiente_por_usuario[uid_op] = pendiente_por_usuario.get(uid_op, Decimal("0")) + Decimal(str(op["comision_usd"]))

    estado_norm = (estado or "TODAS").strip().upper()
    if estado_norm in ("PENDIENTE", "PAGADA"):
        operaciones_detalle = [op for op in operaciones_detalle if op["estado_comision"] == estado_norm]

    reporte: list[dict[str, Any]] = []
    for uid, u in usuarios_map.items():
        if usuario_id is not None and uid != usuario_id:
            continue
        ventas_propias = ventas_por_asesor.get(uid, Decimal("0"))
        com_ventas_1 = (ventas_propias * Decimal("0.01")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        com_lider_05 = Decimal("0")
        ventas_equipo_resto = Decimal("0")
        if u.rol == RolUsuario.LIDER.value:
            ventas_propias_global = ventas_globales_por_asesor.get(uid, Decimal("0"))
            ventas_equipo_resto = max(Decimal("0"), total_ventas_con_asesor_global - ventas_propias_global)
            com_lider_05 = (ventas_equipo_resto * Decimal("0.005")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

        com_servicios = st_por_tecnico.get(uid, Decimal("0"))
        pago_preps = prep_por_tecnico.get(uid, Decimal("0"))
        total_persona = com_ventas_1 + com_lider_05 + com_servicios + pago_preps
        monto_pend = max(Decimal("0"), pendiente_por_usuario.get(uid, Decimal("0")))
        monto_pag = max(Decimal("0"), pagado_por_usuario.get(uid, Decimal("0")))
        estado_u = "PAGADA" if (monto_pend <= 0 and monto_pag > 0) else "PENDIENTE"

        if estado_norm == "PENDIENTE" and monto_pend <= 0 and usuario_id is None:
            continue
        if estado_norm == "PAGADA" and monto_pag <= 0 and usuario_id is None:
            continue

        if (
            usuario_id is not None
            or total_persona > 0
            or u.rol
            in (
                RolUsuario.ASESORA.value,
                RolUsuario.LIDER.value,
                RolUsuario.TECNICO.value,
            )
        ):
            reporte.append(
                {
                    "usuario_id": uid,
                    "nombre": u.nombre,
                    "rol": u.rol,
                    "telefono": getattr(u, "telefono", "") or "",
                    "cantidad_ventas": cantidad_ventas_asesor.get(uid, 0),
                    "cantidad_operaciones": cantidad_ops_usuario.get(uid, 0),
                    "ventas_promo_usd": redondear_usd(ventas_propias),
                    "ventas_equipo_lider_usd": redondear_usd(ventas_equipo_resto),
                    "comision_ventas_1_usd": redondear_usd(com_ventas_1),
                    "comision_lider_05_usd": redondear_usd(com_lider_05),
                    "comision_servicios_50_usd": redondear_usd(com_servicios),
                    "pago_preparaciones_usd": redondear_usd(pago_preps),
                    "total_comision_usd": redondear_usd(total_persona),
                    "monto_pendiente_usd": redondear_usd(monto_pend),
                    "monto_pagado_usd": redondear_usd(monto_pag),
                    "estado_comision": estado_u,
                    "notas": notas_por_usuario.get(uid, []),
                }
            )

    if usuario_id is not None:
        operaciones_detalle = [op for op in operaciones_detalle if op["usuario_id"] == usuario_id]

    operaciones_detalle.sort(key=lambda x: (x["fecha"], x["numero_nota"]), reverse=True)
    return reporte, operaciones_detalle


def calcular_reporte_comisiones(
    bd: Session, mes: int, anio: int, sucursal_id: int | None = None
) -> list[dict[str, Any]]:
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    reporte, _ = calcular_reporte_comisiones_rango(
        bd,
        fecha_inicio=date(anio, mes, 1),
        fecha_fin=date(anio, mes, ultimo_dia),
        sucursal_id=sucursal_id,
    )
    return reporte


@enrutador.get("/comisiones")
def obtener_comisiones(
    mes: int | None = Query(default=None, ge=1, le=12),
    anio: int | None = Query(default=None, ge=2020, le=2100),
    fecha_inicio: date | None = Query(default=None),
    fecha_fin: date | None = Query(default=None),
    usuario_id: int | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    estado: str = Query(default="TODAS"),
    usuario_actual: Usuario = Depends(require_permiso(Permiso.VER_COMISIONES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    sucursal_efectiva = sucursal_id
    usuario_efectivo = usuario_id
    if not es_rol_admin(usuario_actual.rol):
        if usuario_actual.sucursal_id is not None:
            sucursal_efectiva = validar_sucursal_permitida(
                usuario_actual,
                sucursal_id,
                contexto="consultar comisiones de otra sucursal",
            )
        else:
            usuario_efectivo = usuario_actual.id

    hoy = obtener_fecha_hoy()
    if fecha_inicio is not None or fecha_fin is not None:
        f_inicio = fecha_inicio or fecha_fin or date(hoy.year, hoy.month, 1)
        f_fin = fecha_fin or fecha_inicio or hoy
        if f_inicio > f_fin:
            f_inicio, f_fin = f_fin, f_inicio
        mes_obj = f_inicio.month
        anio_obj = f_inicio.year
    else:
        mes_obj = mes or hoy.month
        anio_obj = anio or hoy.year
        ultimo_dia = calendar.monthrange(anio_obj, mes_obj)[1]
        f_inicio = date(anio_obj, mes_obj, 1)
        f_fin = date(anio_obj, mes_obj, ultimo_dia)

    reporte, operaciones = calcular_reporte_comisiones_rango(
        bd,
        fecha_inicio=f_inicio,
        fecha_fin=f_fin,
        sucursal_id=sucursal_efectiva,
        usuario_id=usuario_efectivo,
        estado=estado,
    )
    cierre = (
        bd.query(CierreMensual)
        .filter(CierreMensual.anio == anio_obj, CierreMensual.mes == mes_obj)
        .first()
    )

    total_base_promo = sum(
        (Decimal(str(c["ventas_promo_usd"])) for c in reporte),
        Decimal("0"),
    )
    total_comisiones = sum(
        (Decimal(str(c["total_comision_usd"])) for c in reporte),
        Decimal("0"),
    )

    return {
        "fecha_inicio": f_inicio.isoformat(),
        "fecha_fin": f_fin.isoformat(),
        "mes": mes_obj,
        "anio": anio_obj,
        "mes_cerrado": bool(cierre and cierre.bloqueado),
        "resumen": {
            "total_base_promo_usd": redondear_usd(total_base_promo),
            "total_comisiones_usd": redondear_usd(total_comisiones),
            "cantidad_operaciones": len(operaciones),
        },
        "comisiones": reporte,
        "operaciones": operaciones,
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
            Venta.estado.notin_([EstadoVenta.ANULADA.value, EstadoVenta.DEVUELTA.value]),
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


# ---------------- Tasas Automáticas y Recargo Diario Obligatorio ----------------

from pydantic import BaseModel as _PydanticBaseModel, Field as _PydanticField
from app.modelos import OrigenTasa as _OrigenTasa
from app.rutas.tasas import calcular_brecha_porcentaje as _calcular_brecha_pct
from app.servicios.tasas_service import sincronizar_tasas_dia as _sincronizar_tasas_dia


class RecargoDiarioEntrada(_PydanticBaseModel):
    porcentaje_recargo: Decimal = _PydanticField(ge=0, le=100)
    tasa_bcv: Decimal | None = _PydanticField(default=None, gt=0)
    tasa_usdt: Decimal | None = _PydanticField(default=None, gt=0)


def _serializar_tasa_automatica(tasa: TasaDiaria | None, hoy: date) -> dict[str, Any]:
    if tasa is None:
        return {
            "fecha": hoy.isoformat(),
            "tasa_bcv": None,
            "tasa_usdt": None,
            "porcentaje_recargo": None,
            "recargo_porcentaje": None,
            "recargo_confirmado_hoy": False,
            "permite_bolivares": False,
            "alerta": "Sin tasa del día — Confirma el recargo diario y las tasas",
            "brecha_porcentaje": None,
            "fuente": "sin_conexion",
            "actualizado_en": None,
        }
    return {
        "fecha": tasa.fecha.isoformat(),
        "tasa_bcv": float(tasa.tasa_bcv),
        "tasa_usdt": float(tasa.tasa_usdt),
        "porcentaje_recargo": float(tasa.recargo_porcentaje),
        "recargo_porcentaje": float(tasa.recargo_porcentaje),
        "recargo_confirmado_hoy": bool(tasa.recargo_confirmado_hoy),
        "permite_bolivares": bool(tasa.tasa_bcv and tasa.tasa_bcv > 0),
        "alerta": (
            None
            if tasa.recargo_confirmado_hoy
            else "Pendiente confirmar porcentaje de recargo del día"
        ),
        "brecha_porcentaje": _calcular_brecha_pct(tasa.tasa_bcv, tasa.tasa_usdt),
        "fuente": getattr(tasa, "fuente", "manual") or "manual",
        "actualizado_en": tasa.actualizado_en.isoformat() if tasa.actualizado_en else None,
    }


@enrutador.get("/tasas/hoy")
def obtener_tasa_hoy_automatica(
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    hoy = obtener_fecha_hoy()
    tasa = _sincronizar_tasas_dia(bd, forzar=False)
    return _serializar_tasa_automatica(tasa, hoy)


@enrutador.post("/tasas/sincronizar")
def sincronizar_tasa_ahora(
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    hoy = obtener_fecha_hoy()
    tasa = _sincronizar_tasas_dia(bd, forzar=True)
    return _serializar_tasa_automatica(tasa, hoy)


@enrutador.post("/tasas/recargo-diario")
def confirmar_recargo_diario(
    datos: RecargoDiarioEntrada,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    hoy = obtener_fecha_hoy()
    tasa = _sincronizar_tasas_dia(bd, forzar=False)

    quiere_ajuste_manual = datos.tasa_bcv is not None or datos.tasa_usdt is not None
    if quiere_ajuste_manual and usuario_actual.rol not in ROLES_ADMINISTRATIVOS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo Dirección o Administración pueden ajustar manualmente las tasas BCV/USDT.",
        )

    if tasa is None:
        if datos.tasa_bcv is None or datos.tasa_usdt is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se pudieron obtener las tasas automáticamente. Dirección o Administración debe ingresar BCV y USDT manualmente.",
            )
        tasa = TasaDiaria(
            fecha=hoy,
            tasa_bcv=datos.tasa_bcv,
            tasa_usdt=datos.tasa_usdt,
            recargo_porcentaje=datos.porcentaje_recargo,
            recargo_confirmado_hoy=True,
            origen=_OrigenTasa.MANUAL.value,
            fuente="manual_emergencia",
            publicado_por_id=usuario_actual.id,
            nota="Recargo diario y tasas confirmadas manualmente",
        )
        bd.add(tasa)
    else:
        tasa.recargo_porcentaje = datos.porcentaje_recargo
        tasa.recargo_confirmado_hoy = True
        tasa.publicado_por_id = usuario_actual.id
        if datos.tasa_bcv is not None:
            tasa.tasa_bcv = datos.tasa_bcv
            tasa.fuente = "manual_emergencia"
        if datos.tasa_usdt is not None:
            tasa.tasa_usdt = datos.tasa_usdt
            tasa.fuente = "manual_emergencia"

    bd.commit()
    bd.refresh(tasa)
    return _serializar_tasa_automatica(tasa, hoy)
