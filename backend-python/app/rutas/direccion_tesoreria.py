from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.core.permisos import Permiso, require_permiso
from app.esquemas_operaciones import TesoreriaCrearEntrada
from app.modelos import CatalogoArticulo, EstadoSucursal, Sucursal, TasaDiaria, TipoArticulo, Usuario
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
from app.modelos_logistica import (
    Compra,
    Equipo,
    EstadoEquipo,
    EstadoTraslado,
    MovimientoInventario,
    Traslado,
)
from app.modelos_admin_finanzas import ObligacionFiscal
from app.modelos_operaciones import MovimientoTesoreria
from app.rutas.finanzas import calcular_reporte_comisiones_rango
from app.rutas.tasas import obtener_fecha_hoy
from app.rutas.ventas import generar_correlativo_corto, redondear_usd
from app.servicios.auditoria_service import registrar_auditoria


enrutador = APIRouter(prefix="/api", tags=["Dirección, Tesorería y Alertas"])


def _obtener_tasas_vigentes(bd: Session, fecha_ref: date) -> tuple[Decimal, Decimal, Decimal]:
    tasa = (
        bd.query(TasaDiaria)
        .filter(TasaDiaria.fecha <= fecha_ref)
        .order_by(TasaDiaria.fecha.desc())
        .first()
    )
    if tasa is None:
        return Decimal("0"), Decimal("0"), Decimal("0")
    return tasa.tasa_bcv, tasa.tasa_usdt, tasa.recargo_porcentaje


def _calcular_alertas_internas(bd: Session, hoy: date) -> dict[str, Any]:
    """Calcula alertas de Stock Bajo y CxP vencidas / próximas a vencer (7 días)."""
    # 1. Stock Bajo
    articulos = (
        bd.query(CatalogoArticulo)
        .filter(
            CatalogoArticulo.activo.is_(True),
            CatalogoArticulo.tipo != TipoArticulo.SERVICIO.value,
        )
        .order_by(CatalogoArticulo.sku.asc())
        .all()
    )

    # Conteo de equipos LISTO por articulo_id
    conteo_equipos: dict[int, int] = {
        int(art_id): int(cnt)
        for art_id, cnt in (
            bd.query(Equipo.articulo_id, func.count(Equipo.id))
            .filter(
                Equipo.estado == EstadoEquipo.LISTO.value,
                Equipo.articulo_id.isnot(None),
            )
            .group_by(Equipo.articulo_id)
            .all()
        )
    }

    # Stock de componentes/accesorios por articulo_id
    conteo_comp: dict[int, int] = {
        int(art_id): int(stock or 0)
        for art_id, stock in (
            bd.query(
                MovimientoInventario.articulo_id,
                func.coalesce(func.sum(MovimientoInventario.cantidad), 0),
            )
            .filter(
                MovimientoInventario.equipo_id.is_(None),
                MovimientoInventario.articulo_id.isnot(None),
            )
            .group_by(MovimientoInventario.articulo_id)
            .all()
        )
    }

    stock_bajo: list[dict[str, Any]] = []
    for art in articulos:
        minimo = int(getattr(art, "stock_minimo", 2) or 0)
        if art.tipo == TipoArticulo.EQUIPO.value:
            actual = conteo_equipos.get(art.id, 0)
        else:
            actual = max(0, conteo_comp.get(art.id, 0))
        if actual <= minimo:
            stock_bajo.append(
                {
                    "articulo_id": art.id,
                    "sku": art.sku,
                    "descripcion": art.descripcion,
                    "tipo": art.tipo,
                    "categoria": art.categoria,
                    "stock_actual": actual,
                    "stock_minimo": minimo,
                    "criticidad": "AGOTADO" if actual == 0 else "BAJO",
                }
            )

    # 2. Cuentas por Pagar (CxP) vencidas o por vencer en <= 7 días
    limite_7d = hoy + timedelta(days=7)
    compras_cxp = (
        bd.query(Compra)
        .options(joinedload(Compra.proveedor))
        .filter(
            Compra.saldo_pendiente_usd > Decimal("0"),
            Compra.fecha_vencimiento.isnot(None),
            Compra.fecha_vencimiento <= limite_7d,
        )
        .order_by(Compra.fecha_vencimiento.asc())
        .all()
    )

    cxp_alertas: list[dict[str, Any]] = []
    for c in compras_cxp:
        dias_rest = (c.fecha_vencimiento - hoy).days if c.fecha_vencimiento else 0
        cxp_alertas.append(
            {
                "compra_id": c.id,
                "numero_compra": c.numero_compra,
                "factura_orden": c.factura_orden or c.numero_compra,
                "proveedor": c.proveedor.nombre if c.proveedor else "Proveedor",
                "origen": c.origen,
                "fecha_vencimiento": c.fecha_vencimiento.isoformat() if c.fecha_vencimiento else None,
                "dias_restantes": dias_rest,
                "saldo_pendiente_usd": redondear_usd(c.saldo_pendiente_usd),
                "estado": "VENCIDA" if dias_rest < 0 else "POR_VENCER",
            }
        )

    # 3. Obligaciones Fiscales vencidas o por vencer en <= 7 días
    obligaciones_pend = (
        bd.query(ObligacionFiscal)
        .filter(
            ObligacionFiscal.estado == "PENDIENTE",
            ObligacionFiscal.fecha_vencimiento <= limite_7d,
        )
        .order_by(ObligacionFiscal.fecha_vencimiento.asc())
        .all()
    )
    for ob in obligaciones_pend:
        dias_rest = (ob.fecha_vencimiento - hoy).days
        cxp_alertas.append(
            {
                "compra_id": 100000 + ob.id,
                "numero_compra": f"FISCAL-{ob.id}",
                "factura_orden": f"{ob.tipo} ({ob.periodo})",
                "proveedor": "SENIAT / Fiscal",
                "origen": "FISCAL",
                "fecha_vencimiento": ob.fecha_vencimiento.isoformat(),
                "dias_restantes": dias_rest,
                "saldo_pendiente_usd": redondear_usd(ob.monto_estimado_usd),
                "estado": "VENCIDA" if dias_rest < 0 else "POR_VENCER",
            }
        )

    return {
        "fecha_corte": hoy.isoformat(),
        "total_alertas": len(stock_bajo) + len(cxp_alertas),
        "total_stock_bajo": len(stock_bajo),
        "total_cxp": len(cxp_alertas),
        "stock_bajo": stock_bajo,
        "cxp_por_vencer": cxp_alertas,
    }


@enrutador.get("/alertas")
def obtener_alertas_inteligentes(
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    hoy = obtener_fecha_hoy()
    return _calcular_alertas_internas(bd, hoy)


# =====================================================================
# PANEL EJECUTIVO DE DIRECCIÓN
# =====================================================================

@enrutador.get("/direccion/resumen")
def obtener_resumen_direccion(
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    hoy = obtener_fecha_hoy()
    inicio_mes = date(hoy.year, hoy.month, 1)
    tasa_bcv, tasa_usdt, recargo_pct = _obtener_tasas_vigentes(bd, hoy)
    tasa_conv_bs = tasa_usdt if tasa_usdt > 0 else tasa_bcv

    # 1. Cajas y Bancos en vivo
    instrumentos = (
        bd.query(InstrumentoFinanciero)
        .filter(InstrumentoFinanciero.activo.is_(True))
        .order_by(InstrumentoFinanciero.id.asc())
        .all()
    )
    pagos_activos = (
        bd.query(Pago)
        .filter(Pago.anulado.is_(False))
        .all()
    )
    saldos_por_inst: dict[int, Decimal] = {}
    for p in pagos_activos:
        signo = Decimal("-1") if p.tipo_movimiento == TipoMovimientoPago.EGRESO.value else Decimal("1")
        saldos_por_inst[p.instrumento_id] = saldos_por_inst.get(p.instrumento_id, Decimal("0")) + (
            signo * p.monto_moneda_origen
        )

    cajas_bancos: list[dict[str, Any]] = []
    total_disponible_usd = Decimal("0")
    for inst in instrumentos:
        saldo_orig = saldos_por_inst.get(inst.id, Decimal("0"))
        if inst.moneda == MonedaInstrumento.BS.value:
            equiv_usd = (
                (saldo_orig / tasa_conv_bs).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if tasa_conv_bs > 0
                else Decimal("0")
            )
        else:
            equiv_usd = saldo_orig.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_disponible_usd += equiv_usd
        cajas_bancos.append(
            {
                "instrumento_id": inst.id,
                "nombre": inst.nombre,
                "moneda": inst.moneda,
                "saldo_origen": redondear_usd(saldo_orig),
                "equivalente_usd": redondear_usd(equiv_usd),
            }
        )

    # 2. Inventario Físico y en Tránsito
    equipos_activos = (
        bd.query(Equipo)
        .options(joinedload(Equipo.ubicacion))
        .filter(Equipo.estado.notin_([EstadoEquipo.VENDIDO.value, EstadoEquipo.CEMENTERIO.value]))
        .all()
    )
    valor_costo_usd = Decimal("0")
    valor_promo_usd = Decimal("0")
    por_sucursal_listo: dict[str, int] = {}
    cnt_listo = 0
    cnt_por_preparar = 0
    cnt_hospital = 0
    cnt_transito = 0
    cnt_consignacion = 0

    for eq in equipos_activos:
        if not getattr(eq, "es_consignacion", False):
            valor_costo_usd += eq.costo_compra_usd + eq.costo_flete_usd + eq.costo_taller_usd
        else:
            cnt_consignacion += 1
        valor_promo_usd += eq.precio_promo_usd
        if eq.estado == EstadoEquipo.LISTO.value:
            cnt_listo += 1
            suc_nom = eq.ubicacion.nombre if eq.ubicacion else "Sin sucursal"
            por_sucursal_listo[suc_nom] = por_sucursal_listo.get(suc_nom, 0) + 1
        elif eq.estado == EstadoEquipo.POR_PREPARAR.value:
            cnt_por_preparar += 1
        elif eq.estado == EstadoEquipo.HOSPITAL.value:
            cnt_hospital += 1
        elif eq.estado == EstadoEquipo.EN_TRANSITO.value:
            cnt_transito += 1

    traslados_pendientes = (
        bd.query(Traslado)
        .filter(Traslado.estado == EstadoTraslado.EN_TRANSITO.value)
        .count()
    )

    # 3. Cuentas por Cobrar (CxC) y Cuentas por Pagar (CxP)
    cxcs = (
        bd.query(CuentaPorCobrar)
        .filter(
            CuentaPorCobrar.estado == EstadoCuentaPorCobrar.PENDIENTE.value,
            CuentaPorCobrar.saldo_pendiente_usd > Decimal("0"),
        )
        .all()
    )
    cxc_clientes_usd = sum(
        (c.saldo_pendiente_usd for c in cxcs if c.tipo != TipoCuentaPorCobrar.CASHEA.value),
        Decimal("0"),
    )
    cxc_cashea_usd = sum(
        (c.saldo_pendiente_usd for c in cxcs if c.tipo == TipoCuentaPorCobrar.CASHEA.value),
        Decimal("0"),
    )

    compras_pend = (
        bd.query(Compra)
        .filter(Compra.saldo_pendiente_usd > Decimal("0"))
        .all()
    )
    cxp_total_usd = sum((c.saldo_pendiente_usd for c in compras_pend), Decimal("0"))
    cxp_vencidas_usd = sum(
        (
            c.saldo_pendiente_usd
            for c in compras_pend
            if c.fecha_vencimiento is not None and c.fecha_vencimiento < hoy
        ),
        Decimal("0"),
    )
    cxp_proximas_7d_usd = sum(
        (
            c.saldo_pendiente_usd
            for c in compras_pend
            if c.fecha_vencimiento is not None and hoy <= c.fecha_vencimiento <= (hoy + timedelta(days=7))
        ),
        Decimal("0"),
    )

    # 4. Pulso Comercial del Día y del Mes + Comparativo por Sucursal
    ventas_mes = (
        bd.query(Venta)
        .options(joinedload(Venta.detalles), joinedload(Venta.sucursal))
        .filter(
            Venta.fecha >= inicio_mes,
            Venta.fecha <= hoy,
            Venta.estado.notin_([EstadoVenta.ANULADA.value, EstadoVenta.DEVUELTA.value]),
        )
        .all()
    )
    ventas_dia_usd = Decimal("0")
    ventas_dia_cant = 0
    utilidad_dia_usd = Decimal("0")
    ventas_mes_usd = Decimal("0")
    utilidad_mes_usd = Decimal("0")
    por_sucursal_ventas: dict[str, dict[str, Any]] = {}

    for v in ventas_mes:
        costo_v = sum((d.costo_total_snapshot_usd for d in v.detalles), Decimal("0"))
        util_v = v.total_promo_usd - costo_v
        ventas_mes_usd += v.total_promo_usd
        utilidad_mes_usd += util_v
        if v.fecha == hoy:
            ventas_dia_usd += v.total_promo_usd
            ventas_dia_cant += 1
            utilidad_dia_usd += util_v
        s_nom = v.sucursal.nombre if v.sucursal else "Sin sucursal"
        if s_nom not in por_sucursal_ventas:
            por_sucursal_ventas[s_nom] = {
                "sucursal": s_nom,
                "ventas_mes_cant": 0,
                "ventas_mes_usd": Decimal("0"),
                "ventas_dia_usd": Decimal("0"),
                "utilidad_mes_usd": Decimal("0"),
            }
        por_sucursal_ventas[s_nom]["ventas_mes_cant"] += 1
        por_sucursal_ventas[s_nom]["ventas_mes_usd"] += v.total_promo_usd
        por_sucursal_ventas[s_nom]["utilidad_mes_usd"] += util_v
        if v.fecha == hoy:
            por_sucursal_ventas[s_nom]["ventas_dia_usd"] += v.total_promo_usd

    com_pend_rep, _ = calcular_reporte_comisiones_rango(
        bd,
        fecha_inicio=inicio_mes,
        fecha_fin=hoy,
        estado="PENDIENTE",
    )
    comisiones_pendientes_usd = sum(
        (Decimal(str(c.get("monto_pendiente_usd", c.get("total_comision_usd", 0)))) for c in com_pend_rep),
        Decimal("0"),
    )

    alertas = _calcular_alertas_internas(bd, hoy)

    return {
        "fecha": hoy.isoformat(),
        "tasas": {
            "tasa_bcv": redondear_usd(tasa_bcv),
            "tasa_usdt": redondear_usd(tasa_usdt),
            "recargo_porcentaje": redondear_usd(recargo_pct),
        },
        "tesoreria": {
            "total_disponible_usd": redondear_usd(total_disponible_usd),
            "cuentas": cajas_bancos,
        },
        "inventario": {
            "valor_costo_usd": redondear_usd(valor_costo_usd),
            "valor_promo_usd": redondear_usd(valor_promo_usd),
            "utilidad_potencial_usd": redondear_usd(valor_promo_usd - valor_costo_usd),
            "unidades_listo": cnt_listo,
            "unidades_por_preparar": cnt_por_preparar,
            "unidades_hospital": cnt_hospital,
            "unidades_en_transito": cnt_transito,
            "unidades_consignacion": cnt_consignacion,
            "traslados_pendientes": traslados_pendientes,
            "listo_por_sucursal": [
                {"sucursal": k, "unidades": v}
                for k, v in sorted(por_sucursal_listo.items())
            ],
        },
        "cartera": {
            "cxc_clientes_usd": redondear_usd(cxc_clientes_usd),
            "cxc_cashea_usd": redondear_usd(cxc_cashea_usd),
            "cxc_total_usd": redondear_usd(cxc_clientes_usd + cxc_cashea_usd),
            "cxp_total_usd": redondear_usd(cxp_total_usd),
            "cxp_vencidas_usd": redondear_usd(cxp_vencidas_usd),
            "cxp_proximas_7d_usd": redondear_usd(cxp_proximas_7d_usd),
        },
        "pulso_comercial": {
            "ventas_dia_cant": ventas_dia_cant,
            "ventas_dia_usd": redondear_usd(ventas_dia_usd),
            "utilidad_dia_usd": redondear_usd(utilidad_dia_usd),
            "ventas_mes_cant": len(ventas_mes),
            "ventas_mes_usd": redondear_usd(ventas_mes_usd),
            "utilidad_mes_usd": redondear_usd(utilidad_mes_usd),
            "comisiones_pendientes_usd": redondear_usd(comisiones_pendientes_usd),
            "comparativo_sucursales": [
                {
                    "sucursal": d["sucursal"],
                    "ventas_mes_cant": d["ventas_mes_cant"],
                    "ventas_mes_usd": redondear_usd(d["ventas_mes_usd"]),
                    "ventas_dia_usd": redondear_usd(d["ventas_dia_usd"]),
                    "utilidad_mes_usd": redondear_usd(d["utilidad_mes_usd"]),
                }
                for d in sorted(
                    por_sucursal_ventas.values(),
                    key=lambda x: x["ventas_mes_usd"],
                    reverse=True,
                )
            ],
        },
        "alertas": alertas,
    }


# =====================================================================
# TESORERÍA: TRANSFERENCIAS Y CAMBIOS DE DIVISA
# =====================================================================

def _serializar_tesoreria(mov: MovimientoTesoreria) -> dict[str, Any]:
    return {
        "id": mov.id,
        "codigo": mov.codigo,
        "tipo": mov.tipo,
        "fecha": mov.fecha.isoformat(),
        "instrumento_origen_id": mov.instrumento_origen_id,
        "instrumento_origen": mov.instrumento_origen.nombre if mov.instrumento_origen else "",
        "monto_origen": redondear_usd(mov.monto_origen),
        "moneda_origen": mov.moneda_origen,
        "instrumento_destino_id": mov.instrumento_destino_id,
        "instrumento_destino": mov.instrumento_destino.nombre if mov.instrumento_destino else "",
        "monto_destino": redondear_usd(mov.monto_destino),
        "moneda_destino": mov.moneda_destino,
        "tasa_pactada": float(mov.tasa_pactada),
        "tasa_referencia_bcv": float(mov.tasa_referencia_bcv),
        "tasa_referencia_usdt": float(mov.tasa_referencia_usdt),
        "diferencia_usd": redondear_usd(mov.diferencia_usd),
        "diferencia_pct": float(mov.diferencia_pct),
        "referencia": mov.referencia,
        "notas": mov.notas,
        "pago_egreso_id": mov.pago_egreso_id,
        "pago_ingreso_id": mov.pago_ingreso_id,
        "usuario": mov.usuario.nombre if mov.usuario else "",
        "creado_en": mov.creado_en.isoformat() if mov.creado_en else None,
    }


@enrutador.get("/finanzas/tesoreria")
def listar_movimientos_tesoreria(
    tipo: str | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    consulta = (
        bd.query(MovimientoTesoreria)
        .options(
            joinedload(MovimientoTesoreria.instrumento_origen),
            joinedload(MovimientoTesoreria.instrumento_destino),
            joinedload(MovimientoTesoreria.usuario),
        )
        .order_by(MovimientoTesoreria.fecha.desc(), MovimientoTesoreria.id.desc())
    )
    if tipo:
        consulta = consulta.filter(MovimientoTesoreria.tipo == tipo.upper())
    return [_serializar_tesoreria(m) for m in consulta.limit(150).all()]


@enrutador.post("/finanzas/tesoreria", status_code=status.HTTP_201_CREATED)
def registrar_movimiento_tesoreria(
    datos: TesoreriaCrearEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    if datos.instrumento_origen_id == datos.instrumento_destino_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La cuenta de origen y la cuenta de destino deben ser distintas.",
        )

    inst_orig = (
        bd.query(InstrumentoFinanciero)
        .filter(InstrumentoFinanciero.id == datos.instrumento_origen_id)
        .first()
    )
    inst_dest = (
        bd.query(InstrumentoFinanciero)
        .filter(InstrumentoFinanciero.id == datos.instrumento_destino_id)
        .first()
    )
    if inst_orig is None or inst_dest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instrumento financiero de origen o destino no encontrado.",
        )

    fecha_op = datos.fecha or obtener_fecha_hoy()
    tasa_bcv, tasa_usdt, _ = _obtener_tasas_vigentes(bd, fecha_op)
    tasa_ref = tasa_usdt if tasa_usdt > 0 else tasa_bcv

    mon_orig = inst_orig.moneda
    mon_dest = inst_dest.moneda
    es_bs_orig = mon_orig == MonedaInstrumento.BS.value
    es_bs_dest = mon_dest == MonedaInstrumento.BS.value

    if datos.tipo == "TRANSFERENCIA":
        if es_bs_orig != es_bs_dest:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Para trasladar entre Bs y USD/USDT utiliza el tipo CAMBIO_DIVISA.",
            )
        diferencia_usd = Decimal("0.00")
        diferencia_pct = Decimal("0.00")
        tasa_pactada = Decimal("1.0000")
    else:
        # CAMBIO_DIVISA: cálculo automático de ganancia/pérdida cambiaria
        if es_bs_orig and not es_bs_dest:
            # Comprando USD/USDT con Bs
            tasa_pactada = (
                datos.tasa_pactada
                if datos.tasa_pactada > 0
                else (datos.monto_origen / datos.monto_destino).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            )
            if tasa_ref > 0:
                entregado_usd = datos.monto_origen / tasa_ref
                recibido_usd = datos.monto_destino
                diferencia_usd = (recibido_usd - entregado_usd).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                diferencia_pct = (
                    ((diferencia_usd / entregado_usd) * Decimal("100")).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    if entregado_usd > 0
                    else Decimal("0.00")
                )
            else:
                diferencia_usd = Decimal("0.00")
                diferencia_pct = Decimal("0.00")
        elif not es_bs_orig and es_bs_dest:
            # Vendiendo USD/USDT a Bs
            tasa_pactada = (
                datos.tasa_pactada
                if datos.tasa_pactada > 0
                else (datos.monto_destino / datos.monto_origen).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            )
            if tasa_ref > 0:
                entregado_usd = datos.monto_origen
                recibido_usd = datos.monto_destino / tasa_ref
                diferencia_usd = (recibido_usd - entregado_usd).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                diferencia_pct = (
                    ((diferencia_usd / entregado_usd) * Decimal("100")).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    if entregado_usd > 0
                    else Decimal("0.00")
                )
            else:
                diferencia_usd = Decimal("0.00")
                diferencia_pct = Decimal("0.00")
        else:
            # Cambio entre dos cuentas USD/USDT (ej. Efectivo USD <-> Binance USDT)
            tasa_pactada = (
                datos.tasa_pactada
                if datos.tasa_pactada > 0
                else (datos.monto_destino / datos.monto_origen).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            )
            diferencia_usd = (datos.monto_destino - datos.monto_origen).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            diferencia_pct = (
                ((diferencia_usd / datos.monto_origen) * Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                if datos.monto_origen > 0
                else Decimal("0.00")
            )

    codigo = generar_correlativo_corto(bd, MovimientoTesoreria, MovimientoTesoreria.codigo, "TES")
    tipo_doc = (
        TipoDocumentoPago.CAMBIO_DIVISA.value
        if datos.tipo == "CAMBIO_DIVISA"
        else TipoDocumentoPago.TESORERIA.value
    )

    def _a_usd(monto: Decimal, es_bs: bool) -> tuple[Decimal, Decimal]:
        if not es_bs:
            m = monto.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return m, m
        nom = (monto / tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if tasa_bcv > 0 else Decimal("0")
        real = (monto / tasa_ref).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if tasa_ref > 0 else nom
        return nom, real

    orig_nom, orig_real = _a_usd(datos.monto_origen, es_bs_orig)
    dest_nom, dest_real = _a_usd(datos.monto_destino, es_bs_dest)

    pago_egreso = Pago(
        venta_id=None,
        instrumento_id=inst_orig.id,
        fecha=fecha_op,
        tipo_movimiento=TipoMovimientoPago.EGRESO.value,
        tipo_documento=tipo_doc,
        monto_moneda_origen=datos.monto_origen,
        moneda=mon_orig,
        usd_nominal=orig_nom,
        usd_real=orig_real,
        referencia=datos.referencia.strip() or codigo,
        estado_verificacion=EstadoVerificacionPago.CONFIRMADO.value,
        verificado_por_id=usuario_actual.id,
        nota=f"{codigo} · Salida hacia {inst_dest.nombre}. {datos.notas.strip()}".strip(),
    )
    pago_ingreso = Pago(
        venta_id=None,
        instrumento_id=inst_dest.id,
        fecha=fecha_op,
        tipo_movimiento=TipoMovimientoPago.INGRESO.value,
        tipo_documento=tipo_doc,
        monto_moneda_origen=datos.monto_destino,
        moneda=mon_dest,
        usd_nominal=dest_nom,
        usd_real=dest_real,
        referencia=datos.referencia.strip() or codigo,
        estado_verificacion=EstadoVerificacionPago.CONFIRMADO.value,
        verificado_por_id=usuario_actual.id,
        nota=f"{codigo} · Entrada desde {inst_orig.nombre}. {datos.notas.strip()}".strip(),
    )
    bd.add(pago_egreso)
    bd.add(pago_ingreso)
    bd.flush()

    mov = MovimientoTesoreria(
        codigo=codigo,
        tipo=datos.tipo,
        fecha=fecha_op,
        instrumento_origen_id=inst_orig.id,
        monto_origen=datos.monto_origen,
        moneda_origen=mon_orig,
        instrumento_destino_id=inst_dest.id,
        monto_destino=datos.monto_destino,
        moneda_destino=mon_dest,
        tasa_pactada=tasa_pactada,
        tasa_referencia_bcv=tasa_bcv,
        tasa_referencia_usdt=tasa_usdt,
        diferencia_usd=diferencia_usd,
        diferencia_pct=diferencia_pct,
        referencia=datos.referencia.strip(),
        notas=datos.notas.strip(),
        pago_egreso_id=pago_egreso.id,
        pago_ingreso_id=pago_ingreso.id,
        usuario_id=usuario_actual.id,
    )
    bd.add(mov)
    registrar_auditoria(
        bd,
        usuario_actual,
        "TESORERIA",
        datos.tipo,
        codigo,
        {},
        {
            "origen": inst_orig.nombre,
            "monto_origen": float(datos.monto_origen),
            "destino": inst_dest.nombre,
            "monto_destino": float(datos.monto_destino),
            "diferencia_usd": float(diferencia_usd),
        },
    )
    bd.commit()

    mov_completo = (
        bd.query(MovimientoTesoreria)
        .options(
            joinedload(MovimientoTesoreria.instrumento_origen),
            joinedload(MovimientoTesoreria.instrumento_destino),
            joinedload(MovimientoTesoreria.usuario),
        )
        .filter(MovimientoTesoreria.id == mov.id)
        .first()
    )
    return _serializar_tesoreria(mov_completo)
