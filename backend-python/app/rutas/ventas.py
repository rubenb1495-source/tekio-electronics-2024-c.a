from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.esquemas_finanzas import (
    DevolucionCrearEntrada,
    VentaAnularEntrada,
    VentaCrearEntrada,
    VentaSimularEntrada,
)
from app.esquemas_logistica import ClienteRapidoCrearEntrada, TerceroSalida, normalizar_serial
from app.modelos import (
    CatalogoArticulo,
    CatalogoPrecio,
    EstadoSucursal,
    RolUsuario,
    Sucursal,
    TasaDiaria,
    TipoArticulo,
    Usuario,
)
from app.modelos_finanzas import (
    CierreMensual,
    CuentaPorCobrar,
    EstadoCuentaPorCobrar,
    EstadoVenta,
    EstadoVerificacionPago,
    InstrumentoFinanciero,
    MonedaInstrumento,
    NotaCredito,
    Pago,
    TipoCuentaPorCobrar,
    TipoDocumentoPago,
    TipoMovimientoPago,
    TipoPrecioInstrumento,
    Venta,
    VentaDetalle,
)
from app.modelos_logistica import (
    Compra,
    Equipo,
    EstadoCompra,
    EstadoEquipo,
    MovimientoInventario,
    OrigenCompra,
    Tercero,
    TipoMovimientoInventario,
    TipoPersona,
    TipoTercero,
)
from app.rutas.logistica import calcular_stock_componente, generar_correlativo
from app.rutas.tasas import obtener_fecha_hoy
from app.core.permisos import Permiso, require_permiso, sanear_respuesta_costos
from app.seguridad import obtener_usuario_actual, puede_ver_costos
from app.servicios.auditoria_service import registrar_auditoria
from app.servicios.pdf_nota import generar_pdf_nota_entrega


enrutador = APIRouter(prefix="/api", tags=["Ventas y Devoluciones"])


def redondear_usd(valor: Decimal) -> float:
    return float(valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def verificar_mes_abierto(bd: Session, fecha_op: date) -> None:
    cierre = (
        bd.query(CierreMensual)
        .filter(
            CierreMensual.anio == fecha_op.year,
            CierreMensual.mes == fecha_op.month,
            CierreMensual.bloqueado.is_(True),
        )
        .first()
    )
    if cierre is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"El período {fecha_op.month:02d}/{fecha_op.year} está cerrado y bloqueado. No se permiten cambios.",
        )


def generar_correlativo_corto(bd: Session, modelo: type, columna: Any, prefijo: str) -> str:
    cantidad = bd.query(func.count(modelo.id)).scalar() or 0
    secuencia = int(cantidad) + 1
    while True:
        candidato = f"{prefijo}-{secuencia:04d}"
        if not bd.query(modelo.id).filter(columna == candidato).first():
            return candidato
        secuencia += 1


def obtener_precio_y_costo_articulo(
    bd: Session, articulo_id: int, fecha_ref: date
) -> tuple[Decimal, Decimal | None, Decimal]:
    precio = (
        bd.query(CatalogoPrecio)
        .filter(
            CatalogoPrecio.articulo_id == articulo_id,
            CatalogoPrecio.fecha_vigencia <= fecha_ref,
        )
        .order_by(CatalogoPrecio.fecha_vigencia.desc(), CatalogoPrecio.id.desc())
        .first()
    )
    if precio is None:
        return Decimal("0"), None, Decimal("0")
    return (
        precio.precio_promo_usd,
        precio.precio_regular_fijo_usd,
        precio.costo_referencia_usd or Decimal("0"),
    )


def evaluar_venta(
    bd: Session,
    sucursal_id: int,
    fecha_op: date,
    items: list[Any],
    pagos: list[Any],
    recargo_especial: Decimal | None,
    vuelto_usd: Decimal,
    validar_disponibilidad: bool,
) -> dict[str, Any]:
    sucursal = bd.query(Sucursal).filter(Sucursal.id == sucursal_id).first()
    if sucursal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada.")
    if sucursal.estado != EstadoSucursal.ACTIVA.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"La sucursal '{sucursal.nombre}' está CERRADA. No se permiten nuevas ventas.",
        )

    tasa_dia = bd.query(TasaDiaria).filter(TasaDiaria.fecha == fecha_op).first()
    ultima_tasa = bd.query(TasaDiaria).order_by(TasaDiaria.fecha.desc()).first()

    tasa_bcv = tasa_dia.tasa_bcv if tasa_dia else Decimal("0")
    tasa_usdt = tasa_dia.tasa_usdt if tasa_dia else Decimal("0")
    recargo_base = (
        tasa_dia.recargo_porcentaje
        if tasa_dia
        else (ultima_tasa.recargo_porcentaje if ultima_tasa else Decimal("0"))
    )
    recargo_pct = recargo_especial if recargo_especial is not None else recargo_base
    factor_regular = Decimal("1") + (recargo_pct / Decimal("100"))

    # Resolver instrumentos de pagos
    instrumentos_ids = [p.instrumento_id for p in pagos]
    instrumentos_map = (
        {
            i.id: i
            for i in bd.query(InstrumentoFinanciero)
            .filter(InstrumentoFinanciero.id.in_(instrumentos_ids))
            .all()
        }
        if instrumentos_ids
        else {}
    )

    usa_bs_o_cashea = False
    usa_cashea = False
    for p in pagos:
        inst = instrumentos_map.get(p.instrumento_id)
        if inst is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Instrumento financiero ID {p.instrumento_id} no encontrado.",
            )
        if inst.moneda == MonedaInstrumento.BS.value or "cashea" in inst.nombre.lower():
            usa_bs_o_cashea = True
        if "cashea" in inst.nombre.lower():
            usa_cashea = True

    if usa_bs_o_cashea and tasa_dia is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No existe tasa del día registrada. Los cobros en bolívares y Cashea están bloqueados.",
        )
    if usa_bs_o_cashea and tasa_dia is not None and not getattr(tasa_dia, "recargo_confirmado_hoy", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes confirmar el porcentaje de recargo del día antes de emitir ventas a Precio Regular (Bs o Cashea).",
        )

    # Evaluar ítems
    detalles_calc: list[dict[str, Any]] = []
    total_promo = Decimal("0")
    total_regular = Decimal("0")
    tiene_servicio_tecnico = False

    for it in items:
        if it.equipo_id is not None:
            equipo = bd.query(Equipo).filter(Equipo.id == it.equipo_id).first()
            if equipo is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Equipo ID {it.equipo_id} no encontrado.",
                )
            if validar_disponibilidad:
                if equipo.estado != EstadoEquipo.LISTO.value:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"El serial '{equipo.serial}' no está disponible para venta (estado actual: {equipo.estado}).",
                    )
                if equipo.ubicacion_id != sucursal_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"El serial '{equipo.serial}' pertenece a otra sucursal y no puede venderse aquí.",
                    )
            promo_unit = it.precio_pactado_usd if it.precio_pactado_usd is not None else equipo.precio_promo_usd
            reg_unit = (promo_unit * factor_regular).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            costo_total = (
                Decimal("0")
                if getattr(equipo, "es_consignacion", False)
                else equipo.costo_compra_usd + equipo.costo_flete_usd + equipo.costo_taller_usd
            )
            detalles_calc.append(
                {
                    "equipo": equipo,
                    "articulo": None,
                    "articulo_id": equipo.articulo_id,
                    "descripcion": equipo.modelo or equipo.serial,
                    "descripcion_servicio": (getattr(it, "descripcion_servicio", "") or "").strip(),
                    "cantidad": 1,
                    "precio_promo_usd": promo_unit,
                    "precio_regular_usd": reg_unit,
                    "precio_pactado_usd": it.precio_pactado_usd,
                    "costo_total_snapshot_usd": costo_total,
                }
            )
            total_promo += promo_unit
            total_regular += reg_unit
        elif it.articulo_id is not None:
            art = bd.query(CatalogoArticulo).filter(CatalogoArticulo.id == it.articulo_id).first()
            if art is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Artículo ID {it.articulo_id} no encontrado en catálogo.",
                )
            if art.tipo == TipoArticulo.SERVICIO.value:
                tiene_servicio_tecnico = True
            if validar_disponibilidad and art.tipo != TipoArticulo.SERVICIO.value:
                stock = calcular_stock_componente(bd, art.id, sucursal_id)
                if stock < it.cantidad:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Stock insuficiente de '{art.sku}' en esta sucursal (disponible: {stock}).",
                    )
            promo_cat, reg_fijo, costo_ref = obtener_precio_y_costo_articulo(bd, art.id, fecha_op)
            promo_unit = it.precio_pactado_usd if it.precio_pactado_usd is not None else promo_cat
            reg_unit = (
                reg_fijo
                if (reg_fijo is not None and it.precio_pactado_usd is None)
                else (promo_unit * factor_regular).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            )
            detalles_calc.append(
                {
                    "equipo": None,
                    "articulo": art,
                    "articulo_id": art.id,
                    "descripcion": f"{art.sku} - {art.descripcion}",
                    "descripcion_servicio": (getattr(it, "descripcion_servicio", "") or "").strip(),
                    "cantidad": it.cantidad,
                    "precio_promo_usd": promo_unit,
                    "precio_regular_usd": reg_unit,
                    "precio_pactado_usd": it.precio_pactado_usd,
                    "costo_total_snapshot_usd": costo_ref * Decimal(it.cantidad),
                    "costo_unitario_kardex_usd": costo_ref,
                }
            )
            total_promo += promo_unit * Decimal(it.cantidad)
            total_regular += reg_unit * Decimal(it.cantidad)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cada ítem debe indicar equipo_id o articulo_id.",
            )

    # Imputación de costo de obsequios ($0) al equipo principal sin duplicar costos en utilidad total
    lineas_equipo = [d for d in detalles_calc if d["equipo"] is not None]
    lineas_obsequio = [
        d
        for d in detalles_calc
        if d["equipo"] is None
        and d["articulo"] is not None
        and d["articulo"].tipo != TipoArticulo.SERVICIO.value
        and d["precio_promo_usd"] == Decimal("0")
    ]
    if lineas_equipo and lineas_obsequio:
        costo_total_obsequios = sum(
            (d["costo_total_snapshot_usd"] for d in lineas_obsequio), Decimal("0")
        )
        if costo_total_obsequios > 0:
            cantidad_equipos = len(lineas_equipo)
            cuota_base = (costo_total_obsequios / Decimal(cantidad_equipos)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            acumulado = Decimal("0")
            for idx_eq, det_eq in enumerate(lineas_equipo):
                if idx_eq == cantidad_equipos - 1:
                    ajuste = costo_total_obsequios - acumulado
                else:
                    ajuste = cuota_base
                    acumulado += cuota_base
                det_eq["costo_total_snapshot_usd"] = (
                    det_eq["costo_total_snapshot_usd"] + ajuste
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        for det_obs in lineas_obsequio:
            det_obs["costo_total_snapshot_usd"] = Decimal("0")

    # Evaluar pagos mixtos
    pagos_calc: list[dict[str, Any]] = []
    cubierto_promo = Decimal("0")
    cubierto_regular = Decimal("0")
    iniciales_regular_usd = Decimal("0")
    total_cashea_usd = Decimal("0")

    for p in pagos:
        inst = instrumentos_map[p.instrumento_id]
        monto = p.monto_moneda_origen
        es_cashea_fila = "cashea" in inst.nombre.lower()

        if es_cashea_fila:
            # Cashea se registra en USD Regular (monto financiado) y se liquida en Bs a tasa BCV
            usd_nominal = monto.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            usd_real = (
                ((usd_nominal * tasa_bcv) / tasa_usdt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if (tasa_bcv > 0 and tasa_usdt > 0)
                else usd_nominal
            )
            cubre_promo = (usd_nominal / factor_regular).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        elif inst.moneda == MonedaInstrumento.BS.value:
            usd_nominal = (monto / tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            usd_real = (
                (monto / tasa_usdt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if tasa_usdt > 0
                else usd_nominal
            )
            cubre_promo = (usd_nominal / factor_regular).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            usd_nominal = monto.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            usd_real = usd_nominal
            if usa_cashea or inst.tipo_precio == TipoPrecioInstrumento.REGULAR.value:
                cubre_promo = (usd_nominal / factor_regular).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                cubre_promo = usd_nominal

        if es_cashea_fila:
            total_cashea_usd += usd_nominal
        else:
            iniciales_regular_usd += usd_nominal

        cubierto_promo += cubre_promo
        cubierto_regular += usd_nominal
        pagos_calc.append(
            {
                "entrada": p,
                "instrumento": inst,
                "usd_nominal": usd_nominal,
                "usd_real": usd_real,
                "cubre_promo_usd": cubre_promo,
            }
        )

    if usa_cashea:
        # Regla estricta Cashea: toda la venta se calcula exclusivamente a Precio Regular,
        # sin importar el método de la inicial (divisas/USDT descuentan 1:1 y Bs a tasa BCV sobre Total Regular).
        cubierto_regular_neto = cubierto_regular - vuelto_usd
        diferencia_regular = total_regular - cubierto_regular_neto
        falta_regular = max(Decimal("0"), diferencia_regular).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        sobra_regular = max(Decimal("0"), -diferencia_regular).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        falta_promo = falta_regular
        sobra_promo = sobra_regular
        cubierto_neto = (
            (cubierto_regular_neto / factor_regular).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if factor_regular > 0
            else cubierto_regular_neto
        )
        falta_bs = (
            (falta_regular * tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if tasa_bcv > 0
            else None
        )
        cashea_sugerido_usd = max(
            Decimal("0"), total_regular - (iniciales_regular_usd - vuelto_usd)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cashea_sugerido_bs = (
            (cashea_sugerido_usd * tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if tasa_bcv > 0
            else None
        )
        estado = (
            EstadoVenta.CUADRADA.value
            if falta_regular <= Decimal("0.50")
            else EstadoVenta.CON_SALDO.value
        )
    else:
        cubierto_neto = cubierto_promo - vuelto_usd
        cubierto_regular_neto = cubierto_regular - vuelto_usd
        diferencia = total_promo - cubierto_neto
        falta_promo = max(Decimal("0"), diferencia).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        sobra_promo = max(Decimal("0"), -diferencia).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        falta_regular = (falta_promo * factor_regular).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        falta_bs = (
            (falta_regular * tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if tasa_bcv > 0
            else None
        )
        cashea_sugerido_usd = Decimal("0")
        cashea_sugerido_bs = None
        estado = (
            EstadoVenta.CUADRADA.value
            if falta_promo <= Decimal("0.50")
            else EstadoVenta.CON_SALDO.value
        )

    precio_regular_bs = (
        (total_regular * tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if tasa_bcv > 0
        else Decimal("0.00")
    )
    if usa_cashea and total_cashea_usd > Decimal("0.00"):
        com_cashea_venta_total = (total_regular * Decimal("0.04")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        com_cashea_financiado = (total_cashea_usd * Decimal("0.04")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        iva_cashea = (com_cashea_venta_total * Decimal("0.16")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        islr_cashea = (com_cashea_venta_total * Decimal("0.02")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total_deducciones_cashea = (
            com_cashea_venta_total + com_cashea_financiado + iva_cashea + islr_cashea
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        neto_esperado_cashea = max(
            Decimal("0.00"),
            (total_cashea_usd - total_deducciones_cashea).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
        )
    else:
        com_cashea_venta_total = Decimal("0.00")
        com_cashea_financiado = Decimal("0.00")
        iva_cashea = Decimal("0.00")
        islr_cashea = Decimal("0.00")
        total_deducciones_cashea = Decimal("0.00")
        neto_esperado_cashea = Decimal("0.00")

    return {
        "sucursal": sucursal,
        "tasa_bcv": tasa_bcv,
        "tasa_usdt": tasa_usdt,
        "recargo_pct": recargo_pct,
        "usa_cashea": usa_cashea,
        "total_promo_usd": total_promo,
        "total_regular_usd": total_regular,
        "precio_regular_bs": precio_regular_bs,
        "cubierto_promo_usd": cubierto_neto,
        "cubierto_regular_usd": cubierto_regular_neto,
        "falta_usd_promo": falta_promo,
        "sobra_usd_promo": sobra_promo,
        "falta_usd_regular": falta_regular,
        "falta_bs": falta_bs,
        "total_cashea_usd": total_cashea_usd,
        "comision_cashea_venta_total_usd": com_cashea_venta_total,
        "comision_cashea_financiado_usd": com_cashea_financiado,
        "iva_cashea_usd": iva_cashea,
        "islr_cashea_usd": islr_cashea,
        "total_deducciones_cashea_usd": total_deducciones_cashea,
        "neto_esperado_cashea_usd": neto_esperado_cashea,
        "cashea_financiado_sugerido_usd": cashea_sugerido_usd,
        "cashea_financiado_sugerido_bs": cashea_sugerido_bs,
        "tiene_servicio_tecnico": tiene_servicio_tecnico,
        "estado": estado,
        "detalles": detalles_calc,
        "pagos": pagos_calc,
    }


def serializar_venta(venta: Venta, incluir_costos: bool) -> dict[str, Any]:
    datos: dict[str, Any] = {
        "id": venta.id,
        "numero_venta": venta.numero_venta,
        "sucursal_id": venta.sucursal_id,
        "sucursal": venta.sucursal.nombre if venta.sucursal else None,
        "fecha": venta.fecha.isoformat(),
        "cliente_id": venta.cliente_id,
        "cliente": venta.cliente.nombre if venta.cliente else "Cliente general",
        "cliente_rif": (
            f"{venta.cliente.tipo_documento}-{venta.cliente.documento}"
            if venta.cliente and venta.cliente.tipo_documento and venta.cliente.documento
            else (venta.cliente.rif_cedula if venta.cliente and venta.cliente.rif_cedula else "")
        ),
        "cliente_telefono": venta.cliente.telefono if venta.cliente and venta.cliente.telefono else "",
        "cliente_direccion": venta.cliente.direccion if venta.cliente and venta.cliente.direccion else "",
        "cliente_tipo_persona": (
            venta.cliente.tipo_persona
            if venta.cliente and getattr(venta.cliente, "tipo_persona", None)
            else "NATURAL"
        ),
        "asesor_id": venta.asesor_id,
        "asesor": venta.asesor.nombre if venta.asesor else "Tienda",
        "tecnico_id": venta.tecnico_id,
        "tecnico": venta.tecnico.nombre if venta.tecnico else None,
        "canal_visita": venta.canal_visita,
        "tipo_entrega": venta.tipo_entrega,
        "datos_entrega": (
            json.loads(venta.datos_entrega_json)
            if getattr(venta, "datos_entrega_json", "")
            else None
        ),
        "tasa_bcv_snapshot": float(venta.tasa_bcv_snapshot),
        "tasa_usdt_snapshot": float(venta.tasa_usdt_snapshot),
        "recargo_porcentaje_snapshot": float(venta.recargo_porcentaje_snapshot),
        "total_promo_usd": redondear_usd(venta.total_promo_usd),
        "total_regular_usd": redondear_usd(venta.total_regular_usd),
        "vuelto_caja_chica_usd": redondear_usd(venta.vuelto_caja_chica_usd),
        "creado_en": venta.creado_en.isoformat() if venta.creado_en else None,
        "estado": venta.estado,
        "motivo_anulacion": venta.motivo_anulacion,
        "nota": venta.nota,
        "detalles": [
            {
                "id": d.id,
                "equipo_id": d.equipo_id,
                "serial": d.equipo.serial if d.equipo else None,
                "articulo_id": d.articulo_id,
                "descripcion": d.descripcion,
                "descripcion_servicio": d.descripcion_servicio or "",
                "es_servicio_tecnico": bool(d.articulo and d.articulo.tipo == TipoArticulo.SERVICIO.value),
                "cantidad": d.cantidad,
                "precio_promo_usd": redondear_usd(d.precio_promo_usd),
                "precio_regular_usd": redondear_usd(d.precio_regular_usd),
                **(
                    {"costo_total_snapshot_usd": redondear_usd(d.costo_total_snapshot_usd)}
                    if incluir_costos
                    else {}
                ),
            }
            for d in venta.detalles
        ],
        "pagos": [
            {
                "id": p.id,
                "instrumento": p.instrumento.nombre if p.instrumento else None,
                "monto_moneda_origen": redondear_usd(p.monto_moneda_origen),
                "moneda": p.moneda,
                "usd_nominal": redondear_usd(p.usd_nominal),
                "usd_real": redondear_usd(p.usd_real),
                "cubre_promo_usd": redondear_usd(p.cubre_promo_usd),
                "referencia": p.referencia,
                "estado_verificacion": p.estado_verificacion,
                "anulado": p.anulado,
            }
            for p in venta.pagos
        ],
    }
    if incluir_costos:
        total_costo = sum((d.costo_total_snapshot_usd for d in venta.detalles), Decimal("0"))
        total_real = sum((p.usd_real for p in venta.pagos if not p.anulado), Decimal("0"))

        base_comercial = Decimal("0")
        base_servicios = Decimal("0")
        for d in venta.detalles:
            sub = (d.precio_promo_usd * d.cantidad).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if d.articulo is not None and d.articulo.tipo == TipoArticulo.SERVICIO.value:
                base_servicios += sub
            else:
                base_comercial += sub

        com_asesor = (
            (base_comercial * Decimal("0.01")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if venta.asesor_id is not None
            else Decimal("0.00")
        )
        com_lider = (base_comercial * Decimal("0.005")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        com_tecnico = (
            (base_servicios * Decimal("0.50")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if venta.tecnico_id is not None
            else Decimal("0.00")
        )
        comision_total = (com_asesor + com_lider + com_tecnico).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        precio_neto = venta.total_promo_usd
        margen_neto_real = (precio_neto - total_costo - comision_total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        margen_pct = (
            float((margen_neto_real / precio_neto * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            if precio_neto > Decimal("0")
            else 0.0
        )

        datos["costo_total_usd"] = redondear_usd(total_costo)
        datos["costo_equipo_final_usd"] = redondear_usd(total_costo)
        datos["comision_total_venta_usd"] = redondear_usd(comision_total)
        datos["margen_neto_real_usd"] = redondear_usd(margen_neto_real)
        datos["margen_neto_real_pct"] = margen_pct
        datos["utilidad_real_usd"] = redondear_usd(total_real - total_costo)
        datos["precio_regular_bs"] = redondear_usd(getattr(venta, "precio_regular_bs", Decimal("0")) or Decimal("0"))
        datos["monto_financiado_cashea_usd"] = redondear_usd(getattr(venta, "monto_financiado_cashea_usd", Decimal("0")) or Decimal("0"))
        datos["comision_cashea_venta_total_usd"] = redondear_usd(getattr(venta, "comision_cashea_venta_total_usd", Decimal("0")) or Decimal("0"))
        datos["comision_cashea_financiado_usd"] = redondear_usd(getattr(venta, "comision_cashea_financiado_usd", Decimal("0")) or Decimal("0"))
        datos["iva_cashea_usd"] = redondear_usd(getattr(venta, "iva_cashea_usd", Decimal("0")) or Decimal("0"))
        datos["islr_cashea_usd"] = redondear_usd(getattr(venta, "islr_cashea_usd", Decimal("0")) or Decimal("0"))
        datos["total_deducciones_cashea_usd"] = redondear_usd(getattr(venta, "total_deducciones_cashea_usd", Decimal("0")) or Decimal("0"))
        datos["neto_esperado_cashea_usd"] = redondear_usd(getattr(venta, "neto_esperado_cashea_usd", Decimal("0")) or Decimal("0"))
    return datos


@enrutador.get("/clientes", response_model=list[TerceroSalida])
def listar_clientes(
    busqueda: str | None = Query(default=None),
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[TerceroSalida]:
    """Lista clientes activos (accesible para todos los roles del POS)."""
    consulta = bd.query(Tercero).filter(
        Tercero.activo.is_(True),
        Tercero.tipo == TipoTercero.CLIENTE.value,
    )
    if busqueda and busqueda.strip():
        patron = f"%{busqueda.strip()}%"
        consulta = consulta.filter(
            Tercero.nombre.ilike(patron)
            | Tercero.documento.ilike(patron)
            | Tercero.rif_cedula.ilike(patron)
            | Tercero.telefono.ilike(patron)
        )
    filas = consulta.order_by(Tercero.nombre.asc()).all()
    return [TerceroSalida.model_validate(f) for f in filas]


def _registrar_cliente_rapido(
    datos: ClienteRapidoCrearEntrada,
    bd: Session,
) -> TerceroSalida:
    tipo_persona = datos.tipo_persona.value
    tipo_doc = datos.tipo_documento.value
    doc_limpio = datos.documento

    if tipo_persona == TipoPersona.NATURAL.value and tipo_doc not in ("V", "E", "P"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Para Persona Natural el tipo de documento debe ser V, E o P.",
        )
    if tipo_persona == TipoPersona.JURIDICO.value and tipo_doc not in ("J", "G"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Para Persona Jurídica el tipo de documento debe ser J o G.",
        )

    rif_completo = f"{tipo_doc}-{doc_limpio}"
    existente = (
        bd.query(Tercero)
        .filter(
            Tercero.tipo == TipoTercero.CLIENTE.value,
            (
                ((Tercero.tipo_documento == tipo_doc) & (Tercero.documento == doc_limpio))
                | (Tercero.rif_cedula == rif_completo)
            ),
        )
        .first()
    )
    if existente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un cliente registrado con el documento {rif_completo}: '{existente.nombre}'.",
        )

    nuevo = Tercero(
        nombre=datos.nombre.strip(),
        tipo=TipoTercero.CLIENTE.value,
        tipo_persona=tipo_persona,
        tipo_documento=tipo_doc,
        documento=doc_limpio,
        rif_cedula=rif_completo,
        telefono=datos.telefono.strip(),
        direccion=datos.direccion.strip(),
        activo=True,
    )
    bd.add(nuevo)
    bd.commit()
    bd.refresh(nuevo)
    return TerceroSalida.model_validate(nuevo)


@enrutador.post("/clientes", response_model=TerceroSalida, status_code=status.HTTP_201_CREATED)
@enrutador.post("/terceros", response_model=TerceroSalida, status_code=status.HTTP_201_CREATED)
def crear_cliente_rapido(
    datos: ClienteRapidoCrearEntrada,
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> TerceroSalida:
    """Crea un cliente Natural o Jurídico desde el POS (accesible para ASESORA, LIDER, TECNICO, LOGISTICA, ADMIN y DIRECCION)."""
    return _registrar_cliente_rapido(datos, bd)


@enrutador.post("/ventas/simular")
def simular_venta(
    datos: VentaSimularEntrada,
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    hoy = obtener_fecha_hoy()
    calc = evaluar_venta(
        bd=bd,
        sucursal_id=datos.sucursal_id,
        fecha_op=hoy,
        items=datos.items,
        pagos=datos.pagos,
        recargo_especial=datos.recargo_especial,
        vuelto_usd=datos.vuelto_usd,
        validar_disponibilidad=False,
    )
    return {
        "total_promo_usd": redondear_usd(calc["total_promo_usd"]),
        "total_regular_usd": redondear_usd(calc["total_regular_usd"]),
        "cubierto_promo_usd": redondear_usd(calc["cubierto_promo_usd"]),
        "cubierto_regular_usd": redondear_usd(calc["cubierto_regular_usd"]),
        "falta_usd_promo": redondear_usd(calc["falta_usd_promo"]),
        "sobra_usd_promo": redondear_usd(calc["sobra_usd_promo"]),
        "falta_usd_regular": redondear_usd(calc["falta_usd_regular"]),
        "falta_bs": redondear_usd(calc["falta_bs"]) if calc["falta_bs"] is not None else None,
        "cashea_financiado_sugerido_usd": redondear_usd(calc["cashea_financiado_sugerido_usd"]),
        "cashea_financiado_sugerido_bs": (
            redondear_usd(calc["cashea_financiado_sugerido_bs"])
            if calc["cashea_financiado_sugerido_bs"] is not None
            else None
        ),
        "usa_cashea": calc["usa_cashea"],
        "tasa_bcv": float(calc["tasa_bcv"]),
        "recargo_porcentaje": float(calc["recargo_pct"]),
        "estado": calc["estado"],
    }


@enrutador.get("/ventas")
def listar_ventas(
    sucursal_id: int | None = Query(default=None),
    estado: EstadoVenta | None = Query(default=None),
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    incluir_costos = puede_ver_costos(usuario_actual.rol)
    consulta = bd.query(Venta).options(
        joinedload(Venta.sucursal),
        joinedload(Venta.cliente),
        joinedload(Venta.asesor),
        joinedload(Venta.tecnico),
        joinedload(Venta.detalles).joinedload(VentaDetalle.equipo),
        joinedload(Venta.detalles).joinedload(VentaDetalle.articulo),
        joinedload(Venta.pagos).joinedload(Pago.instrumento),
    )
    if sucursal_id is not None:
        consulta = consulta.filter(Venta.sucursal_id == sucursal_id)
    if estado is not None:
        consulta = consulta.filter(Venta.estado == estado.value)

    ventas = consulta.order_by(Venta.id.desc()).limit(100).all()
    return sanear_respuesta_costos(
        [serializar_venta(v, incluir_costos) for v in ventas],
        usuario_actual.rol,
    )


@enrutador.post("/ventas", status_code=status.HTTP_201_CREATED)
def crear_venta(
    datos: VentaCrearEntrada,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    fecha_op = datos.fecha or obtener_fecha_hoy()
    verificar_mes_abierto(bd, fecha_op)

    calc = evaluar_venta(
        bd=bd,
        sucursal_id=datos.sucursal_id,
        fecha_op=fecha_op,
        items=datos.items,
        pagos=datos.pagos,
        recargo_especial=datos.recargo_especial,
        vuelto_usd=datos.vuelto_usd,
        validar_disponibilidad=True,
    )

    if calc["tiene_servicio_tecnico"]:
        if datos.tecnico_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes seleccionar un Técnico responsable cuando la venta incluye Servicio Técnico / Mano de Obra.",
            )
        tecnico_obj = (
            bd.query(Usuario)
            .filter(Usuario.id == datos.tecnico_id, Usuario.activo.is_(True))
            .first()
        )
        if tecnico_obj is None or tecnico_obj.rol != RolUsuario.TECNICO.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El técnico seleccionado no existe o no tiene rol TECNICO activo.",
            )

    if calc["estado"] == EstadoVenta.CON_SALDO.value and not datos.queda_con_saldo:
        if calc["usa_cashea"]:
            mensaje_faltante = (
                f"Faltan ${redondear_usd(calc['falta_usd_regular']):.2f} USD Regular para cuadrar la venta con Cashea. "
                "Completa el pago o marca 'queda_con_saldo: true'."
            )
        else:
            mensaje_faltante = (
                f"Faltan ${redondear_usd(calc['falta_usd_promo']):.2f} USD Promo para cuadrar la venta. "
                "Completa el pago o marca 'queda_con_saldo: true'."
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=mensaje_faltante,
        )

    numero_venta = generar_correlativo_corto(bd, Venta, Venta.numero_venta, "N")
    venta = Venta(
        numero_venta=numero_venta,
        sucursal_id=datos.sucursal_id,
        fecha=fecha_op,
        cliente_id=datos.cliente_id,
        asesor_id=datos.asesor_id,
        tecnico_id=datos.tecnico_id,
        canal_visita=datos.canal_visita.strip(),
        tipo_entrega=datos.entrega.strip(),
        datos_entrega_json=(
            json.dumps(datos.datos_entrega, ensure_ascii=False)
            if datos.datos_entrega
            else ""
        ),
        origen_equipo=datos.origen_equipo.strip(),
        tasa_bcv_snapshot=calc["tasa_bcv"],
        tasa_usdt_snapshot=calc["tasa_usdt"],
        recargo_porcentaje_snapshot=calc["recargo_pct"],
        recargo_especial_porcentaje=datos.recargo_especial,
        total_promo_usd=calc["total_promo_usd"],
        total_regular_usd=calc["total_regular_usd"],
        precio_regular_bs=calc["precio_regular_bs"],
        monto_financiado_cashea_usd=calc["total_cashea_usd"],
        comision_cashea_venta_total_usd=calc["comision_cashea_venta_total_usd"],
        comision_cashea_financiado_usd=calc["comision_cashea_financiado_usd"],
        iva_cashea_usd=calc["iva_cashea_usd"],
        islr_cashea_usd=calc["islr_cashea_usd"],
        total_deducciones_cashea_usd=calc["total_deducciones_cashea_usd"],
        neto_esperado_cashea_usd=calc["neto_esperado_cashea_usd"],
        vuelto_caja_chica_usd=datos.vuelto_usd,
        es_factura=datos.es_factura,
        numero_control=datos.numero_control.strip(),
        estado=calc["estado"],
        nota=datos.nota.strip(),
        creado_por_id=usuario_actual.id,
    )
    bd.add(venta)
    bd.flush()

    for det in calc["detalles"]:
        bd.add(
            VentaDetalle(
                venta_id=venta.id,
                equipo_id=det["equipo"].id if det["equipo"] else None,
                articulo_id=det["articulo_id"],
                descripcion=det["descripcion"],
                descripcion_servicio=det["descripcion_servicio"],
                cantidad=det["cantidad"],
                precio_promo_usd=det["precio_promo_usd"],
                precio_regular_usd=det["precio_regular_usd"],
                precio_pactado_usd=det["precio_pactado_usd"],
                costo_total_snapshot_usd=det["costo_total_snapshot_usd"],
            )
        )
        if det["equipo"] is not None:
            eq = det["equipo"]
            eq.estado = EstadoEquipo.VENDIDO.value
            bd.add(
                MovimientoInventario(
                    tipo=TipoMovimientoInventario.VENTA.value,
                    articulo_id=eq.articulo_id,
                    equipo_id=eq.id,
                    sucursal_id=datos.sucursal_id,
                    cantidad=-1,
                    costo_unitario_usd=det["costo_total_snapshot_usd"],
                    documento_ref=numero_venta,
                    motivo=f"Venta {numero_venta}",
                    usuario_id=usuario_actual.id,
                )
            )
        elif det["articulo"] is not None and det["articulo"].tipo != TipoArticulo.SERVICIO.value:
            bd.add(
                MovimientoInventario(
                    tipo=TipoMovimientoInventario.VENTA.value,
                    articulo_id=det["articulo"].id,
                    equipo_id=None,
                    sucursal_id=datos.sucursal_id,
                    cantidad=-det["cantidad"],
                    costo_unitario_usd=det.get("costo_unitario_kardex_usd", det["costo_total_snapshot_usd"]),
                    documento_ref=numero_venta,
                    motivo=f"Venta {numero_venta}" + (" (Obsequio)" if det["precio_promo_usd"] == Decimal("0") else ""),
                    usuario_id=usuario_actual.id,
                )
            )

    for p_calc in calc["pagos"]:
        inst: InstrumentoFinanciero = p_calc["instrumento"]
        ent = p_calc["entrada"]
        es_parte_pago = "parte de pago" in inst.nombre.lower()

        if es_parte_pago:
            if not ent.parte_pago_serial or not ent.parte_pago_modelo:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Para 'Equipo como parte de pago' debes indicar parte_pago_serial y parte_pago_modelo.",
                )
            serial_pp = normalizar_serial(ent.parte_pago_serial)
            if bd.query(Equipo.id).filter(Equipo.serial == serial_pp).first():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"El serial de parte de pago '{serial_pp}' ya existe en el inventario.",
                )
            num_cmp = generar_correlativo(bd, Compra, Compra.numero_compra, "CMP")
            compra_pp = Compra(
                numero_compra=num_cmp,
                origen=OrigenCompra.PARTE_DE_PAGO.value,
                fecha=fecha_op,
                factura_orden=numero_venta,
                monto_mercancia_usd=p_calc["usd_nominal"],
                estado=EstadoCompra.RECIBIDA.value,
                nota=f"Equipo recibido como parte de pago en {numero_venta}",
                creado_por_id=usuario_actual.id,
            )
            bd.add(compra_pp)
            bd.flush()

            eq_pp = Equipo(
                serial=serial_pp,
                compra_id=compra_pp.id,
                modelo=ent.parte_pago_modelo.strip(),
                ubicacion_id=datos.sucursal_id,
                estado=EstadoEquipo.POR_PREPARAR.value,
                costo_compra_usd=p_calc["usd_nominal"],
                recibido_por_id=usuario_actual.id,
                fecha_recepcion=fecha_op,
            )
            bd.add(eq_pp)
            bd.flush()
            bd.add(
                MovimientoInventario(
                    tipo=TipoMovimientoInventario.COMPRA.value,
                    equipo_id=eq_pp.id,
                    sucursal_id=datos.sucursal_id,
                    cantidad=1,
                    costo_unitario_usd=p_calc["usd_nominal"],
                    documento_ref=numero_venta,
                    motivo=f"Ingreso por parte de pago ({numero_venta})",
                    usuario_id=usuario_actual.id,
                )
            )

        estado_verif = (
            EstadoVerificacionPago.PENDIENTE.value
            if inst.requiere_verificacion
            else EstadoVerificacionPago.CONFIRMADO.value
        )
        tipo_doc = (
            TipoDocumentoPago.PARTE_DE_PAGO.value
            if es_parte_pago
            else (TipoDocumentoPago.CASHEA.value if "cashea" in inst.nombre.lower() else TipoDocumentoPago.VENTA.value)
        )
        bd.add(
            Pago(
                venta_id=venta.id,
                instrumento_id=inst.id,
                fecha=fecha_op,
                tipo_movimiento=TipoMovimientoPago.INGRESO.value,
                tipo_documento=tipo_doc,
                monto_moneda_origen=ent.monto_moneda_origen,
                moneda=inst.moneda,
                tasa_bcv_dia=calc["tasa_bcv"],
                tasa_usdt_dia=calc["tasa_usdt"],
                usd_nominal=p_calc["usd_nominal"],
                usd_real=p_calc["usd_real"],
                cubre_promo_usd=p_calc["cubre_promo_usd"],
                referencia=ent.referencia.strip(),
                estado_verificacion=estado_verif,
            )
        )

    if calc["total_cashea_usd"] > 0:
        bd.add(
            CuentaPorCobrar(
                venta_id=venta.id,
                tipo=TipoCuentaPorCobrar.CASHEA.value,
                cliente_id=datos.cliente_id,
                monto_original_usd=calc["total_cashea_usd"],
                saldo_pendiente_usd=calc["total_cashea_usd"],
                estado=EstadoCuentaPorCobrar.PENDIENTE.value,
            )
        )

    if calc["estado"] == EstadoVenta.CON_SALDO.value and calc["falta_usd_promo"] > 0:
        bd.add(
            CuentaPorCobrar(
                venta_id=venta.id,
                tipo=TipoCuentaPorCobrar.CLIENTE.value,
                cliente_id=datos.cliente_id,
                monto_original_usd=calc["falta_usd_promo"],
                saldo_pendiente_usd=calc["falta_usd_promo"],
                estado=EstadoCuentaPorCobrar.PENDIENTE.value,
            )
        )

    if datos.cotizacion_id is not None:
        from app.modelos_operaciones import Cotizacion, EstadoCotizacion

        cot_origen = bd.query(Cotizacion).filter(Cotizacion.id == datos.cotizacion_id).first()
        if cot_origen is not None:
            cot_origen.estado = EstadoCotizacion.CONVERTIDA.value
            cot_origen.venta_id = venta.id

    # Asientos automáticos por partida doble (Venta POS: Ingreso + Costo de Ventas)
    from app.servicios.contabilidad_service import registrar_asiento

    ing_equipos_comp = Decimal("0.00")
    ing_servicios = Decimal("0.00")
    cogs_equipos = Decimal("0.00")
    cogs_componentes = Decimal("0.00")
    for det in calc["detalles"]:
        es_serv = det["articulo"] is not None and det["articulo"].tipo == TipoArticulo.SERVICIO.value
        sub_ing = (det["precio_promo_usd"] * det["cantidad"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if es_serv:
            ing_servicios += sub_ing
        else:
            ing_equipos_comp += sub_ing
            if det["equipo"] is not None:
                cogs_equipos += det["costo_total_snapshot_usd"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            elif det["articulo"] is not None:
                cogs_componentes += (
                    det.get("costo_unitario_kardex_usd", det["costo_total_snapshot_usd"]) * det["cantidad"]
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    total_ing_asiento = (ing_equipos_comp + ing_servicios).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if total_ing_asiento > Decimal("0.00"):
        cashea_asiento = min(total_ing_asiento, calc["total_cashea_usd"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        cxc_asiento = (
            min(
                (total_ing_asiento - cashea_asiento).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                calc["falta_usd_promo"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            )
            if calc["estado"] == EstadoVenta.CON_SALDO.value and calc["falta_usd_promo"] > 0
            else Decimal("0.00")
        )
        caja_asiento = (total_ing_asiento - cashea_asiento - cxc_asiento).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        lineas_vta: list[dict[str, Any]] = []
        if caja_asiento > Decimal("0.00"):
            lineas_vta.append({"codigo_cuenta": "1.1.01", "debe_usd": caja_asiento, "descripcion": f"Cobro POS {numero_venta}"})
        if cashea_asiento > Decimal("0.00"):
            lineas_vta.append({"codigo_cuenta": "1.1.03", "debe_usd": cashea_asiento, "descripcion": f"Cashea por cobrar {numero_venta}"})
        if cxc_asiento > Decimal("0.00"):
            lineas_vta.append({"codigo_cuenta": "1.1.02", "debe_usd": cxc_asiento, "descripcion": f"CxC cliente {numero_venta}"})
        if ing_equipos_comp > Decimal("0.00"):
            lineas_vta.append({"codigo_cuenta": "4.1.01", "haber_usd": ing_equipos_comp, "descripcion": f"Ingreso equipos/comp {numero_venta}"})
        if ing_servicios > Decimal("0.00"):
            lineas_vta.append({"codigo_cuenta": "4.1.02", "haber_usd": ing_servicios, "descripcion": f"Ingreso servicios {numero_venta}"})
        if len(lineas_vta) >= 2:
            registrar_asiento(
                bd,
                fecha=fecha_op,
                referencia=numero_venta,
                modulo_origen="VENTAS",
                entidad_id=venta.id,
                descripcion=f"Venta POS {numero_venta}",
                lineas=lineas_vta,
                creado_por_id=usuario_actual.id,
            )

    total_cogs = (cogs_equipos + cogs_componentes).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if total_cogs > Decimal("0.00"):
        lineas_cogs: list[dict[str, Any]] = [
            {"codigo_cuenta": "5.1.01", "debe_usd": total_cogs, "descripcion": f"Costo de ventas {numero_venta}"}
        ]
        if cogs_equipos > Decimal("0.00"):
            lineas_cogs.append({"codigo_cuenta": "1.1.04", "haber_usd": cogs_equipos, "descripcion": f"Descarga equipos {numero_venta}"})
        if cogs_componentes > Decimal("0.00"):
            lineas_cogs.append({"codigo_cuenta": "1.1.05", "haber_usd": cogs_componentes, "descripcion": f"Descarga componentes {numero_venta}"})
        registrar_asiento(
            bd,
            fecha=fecha_op,
            referencia=numero_venta,
            modulo_origen="VENTAS_COGS",
            entidad_id=venta.id,
            descripcion=f"Descarga de inventario a costo de ventas {numero_venta}",
            lineas=lineas_cogs,
            creado_por_id=usuario_actual.id,
        )

    if calc["total_deducciones_cashea_usd"] > Decimal("0.00"):
        registrar_asiento(
            bd,
            fecha=fecha_op,
            referencia=numero_venta,
            modulo_origen="CASHEA_DEDUCCIONES",
            entidad_id=venta.id,
            descripcion=(
                f"Deducciones financieras Cashea {numero_venta} "
                f"(4% total + 4% financiado + 16% IVA + 2% ISLR)"
            ),
            lineas=[
                {
                    "codigo_cuenta": "6.3.03",
                    "debe_usd": calc["total_deducciones_cashea_usd"],
                    "descripcion": f"Comisión/Impuestos Cashea {numero_venta}",
                },
                {
                    "codigo_cuenta": "1.1.03",
                    "haber_usd": calc["total_deducciones_cashea_usd"],
                    "descripcion": f"Ajuste neto Cashea por cobrar {numero_venta}",
                },
            ],
            creado_por_id=usuario_actual.id,
        )

    bd.commit()

    venta_completa = (
        bd.query(Venta)
        .options(
            joinedload(Venta.sucursal),
            joinedload(Venta.cliente),
            joinedload(Venta.asesor),
            joinedload(Venta.tecnico),
            joinedload(Venta.detalles).joinedload(VentaDetalle.equipo),
            joinedload(Venta.detalles).joinedload(VentaDetalle.articulo),
            joinedload(Venta.pagos).joinedload(Pago.instrumento),
        )
        .filter(Venta.id == venta.id)
        .first()
    )
    return sanear_respuesta_costos(
        serializar_venta(venta_completa, puede_ver_costos(usuario_actual.rol)),
        usuario_actual.rol,
    )


@enrutador.get("/ventas/{venta_id}/nota-pdf")
def descargar_nota_entrega_pdf(
    venta_id: int,
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> Response:
    venta = (
        bd.query(Venta)
        .options(
            joinedload(Venta.sucursal),
            joinedload(Venta.cliente),
            joinedload(Venta.asesor),
            joinedload(Venta.tecnico),
            joinedload(Venta.detalles).joinedload(VentaDetalle.equipo),
            joinedload(Venta.detalles).joinedload(VentaDetalle.articulo),
            joinedload(Venta.pagos).joinedload(Pago.instrumento),
        )
        .filter(Venta.id == venta_id)
        .first()
    )
    if venta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada.")

    pdf_bytes = generar_pdf_nota_entrega(venta)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Nota_{venta.numero_venta}.pdf"'},
    )


@enrutador.post("/ventas/{venta_id}/anular")
def anular_venta(
    venta_id: int,
    datos: VentaAnularEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.ANULAR_VENTA)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    venta = (
        bd.query(Venta)
        .options(
            joinedload(Venta.detalles).joinedload(VentaDetalle.equipo),
            joinedload(Venta.pagos),
            joinedload(Venta.cuentas_por_cobrar),
        )
        .filter(Venta.id == venta_id)
        .first()
    )
    if venta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada.")
    if venta.estado == EstadoVenta.ANULADA.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La venta ya está anulada.")

    verificar_mes_abierto(bd, venta.fecha)

    venta.estado = EstadoVenta.ANULADA.value
    venta.motivo_anulacion = datos.motivo.strip()

    for det in venta.detalles:
        if det.equipo is not None:
            det.equipo.estado = EstadoEquipo.LISTO.value
            det.equipo.ubicacion_id = venta.sucursal_id
            bd.add(
                MovimientoInventario(
                    tipo=TipoMovimientoInventario.AJUSTE_POSITIVO.value,
                    articulo_id=det.articulo_id,
                    equipo_id=det.equipo.id,
                    sucursal_id=venta.sucursal_id,
                    cantidad=1,
                    costo_unitario_usd=det.costo_total_snapshot_usd,
                    documento_ref=venta.numero_venta,
                    motivo=f"Reverso por anulación de {venta.numero_venta}: {datos.motivo.strip()}",
                    usuario_id=usuario_actual.id,
                )
            )
        elif det.articulo_id is not None:
            bd.add(
                MovimientoInventario(
                    tipo=TipoMovimientoInventario.AJUSTE_POSITIVO.value,
                    articulo_id=det.articulo_id,
                    equipo_id=None,
                    sucursal_id=venta.sucursal_id,
                    cantidad=det.cantidad,
                    costo_unitario_usd=det.costo_total_snapshot_usd,
                    documento_ref=venta.numero_venta,
                    motivo=f"Reverso por anulación de {venta.numero_venta}",
                    usuario_id=usuario_actual.id,
                )
            )

    for p in venta.pagos:
        p.anulado = True
    for cxc in venta.cuentas_por_cobrar:
        cxc.estado = EstadoCuentaPorCobrar.ANULADA.value
        cxc.saldo_pendiente_usd = Decimal("0")

    registrar_auditoria(
        bd,
        usuario_actual,
        "VENTAS",
        "ANULAR_VENTA",
        venta.numero_venta,
        {"estado": "CUADRADA", "total_promo_usd": float(venta.total_promo_usd)},
        {"estado": venta.estado, "motivo_anulacion": venta.motivo_anulacion},
    )
    bd.commit()
    return {
        "id": venta.id,
        "numero_venta": venta.numero_venta,
        "estado": venta.estado,
        "motivo_anulacion": venta.motivo_anulacion,
    }


# ---------------- Devoluciones (Notas de Crédito) ----------------

@enrutador.get("/devoluciones")
def listar_devoluciones(
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    notas = (
        bd.query(NotaCredito)
        .options(
            joinedload(NotaCredito.venta_original),
            joinedload(NotaCredito.equipo),
            joinedload(NotaCredito.articulo),
            joinedload(NotaCredito.autorizado_por),
        )
        .order_by(NotaCredito.id.desc())
        .all()
    )
    return [
        {
            "id": n.id,
            "numero_nc": n.numero_nc,
            "venta_original_id": n.venta_original_id,
            "numero_venta": n.venta_original.numero_venta if n.venta_original else None,
            "serial": n.equipo.serial if n.equipo else None,
            "sku": n.articulo.sku if n.articulo else None,
            "cantidad": n.cantidad,
            "monto_reconocido_promo_usd": redondear_usd(n.monto_reconocido_promo_usd),
            "motivo": n.motivo,
            "estado_reingreso": n.estado_reingreso,
            "autorizado_por": n.autorizado_por.nombre if n.autorizado_por else None,
            "fecha": n.fecha.isoformat(),
        }
        for n in notas
    ]


@enrutador.post("/devoluciones", status_code=status.HTTP_201_CREATED)
def registrar_devolucion(
    datos: DevolucionCrearEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.AUTORIZAR_REEMBOLSO)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    hoy = obtener_fecha_hoy()
    verificar_mes_abierto(bd, hoy)

    venta = (
        bd.query(Venta)
        .options(joinedload(Venta.detalles))
        .filter(Venta.id == datos.venta_original_id)
        .first()
    )
    if venta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venta original no encontrada.",
        )

    detalle_match = next(
        (
            d
            for d in venta.detalles
            if (datos.equipo_id and d.equipo_id == datos.equipo_id)
            or (datos.articulo_id and d.articulo_id == datos.articulo_id)
        ),
        None,
    )
    monto_reconocido = (
        detalle_match.precio_promo_usd * Decimal(datos.cantidad)
        if detalle_match
        else Decimal("0")
    )

    if datos.equipo_id is not None:
        eq = bd.query(Equipo).filter(Equipo.id == datos.equipo_id).first()
        if eq is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipo no encontrado.")
        eq.estado = datos.estado_reingreso.value
        eq.ubicacion_id = venta.sucursal_id
        bd.add(
            MovimientoInventario(
                tipo=TipoMovimientoInventario.AJUSTE_POSITIVO.value,
                articulo_id=eq.articulo_id,
                equipo_id=eq.id,
                sucursal_id=venta.sucursal_id,
                cantidad=1,
                costo_unitario_usd=eq.costo_compra_usd,
                documento_ref=venta.numero_venta,
                motivo=f"Devolución (NC) → {datos.estado_reingreso.value}: {datos.motivo.strip()}",
                usuario_id=usuario_actual.id,
            )
        )
    elif datos.articulo_id is not None:
        bd.add(
            MovimientoInventario(
                tipo=TipoMovimientoInventario.AJUSTE_POSITIVO.value,
                articulo_id=datos.articulo_id,
                equipo_id=None,
                sucursal_id=venta.sucursal_id,
                cantidad=datos.cantidad,
                costo_unitario_usd=Decimal("0"),
                documento_ref=venta.numero_venta,
                motivo=f"Devolución de artículo (NC): {datos.motivo.strip()}",
                usuario_id=usuario_actual.id,
            )
        )

    numero_nc = generar_correlativo_corto(bd, NotaCredito, NotaCredito.numero_nc, "NC")
    nc = NotaCredito(
        numero_nc=numero_nc,
        venta_original_id=venta.id,
        equipo_id=datos.equipo_id,
        articulo_id=datos.articulo_id,
        cantidad=datos.cantidad,
        monto_reconocido_promo_usd=monto_reconocido,
        motivo=datos.motivo.strip(),
        estado_reingreso=datos.estado_reingreso.value,
        autorizado_por_id=usuario_actual.id,
        fecha=hoy,
    )
    bd.add(nc)
    bd.commit()
    bd.refresh(nc)

    return {
        "id": nc.id,
        "numero_nc": nc.numero_nc,
        "venta_original_id": venta.id,
        "estado_reingreso": nc.estado_reingreso,
        "monto_reconocido_promo_usd": redondear_usd(nc.monto_reconocido_promo_usd),
    }
