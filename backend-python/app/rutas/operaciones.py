from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.esquemas_operaciones import (
    CotizacionCrearEntrada,
    CotizacionEstadoEntrada,
    DevolucionGarantiaCrearEntrada,
)
from app.modelos import CatalogoArticulo, RolUsuario, Sucursal, TasaDiaria, Usuario
from app.modelos_finanzas import (
    EstadoVenta,
    EstadoVerificacionPago,
    InstrumentoFinanciero,
    MonedaInstrumento,
    Pago,
    TipoDocumentoPago,
    TipoMovimientoPago,
    TipoPrecioInstrumento,
    Venta,
    VentaDetalle,
)
from app.modelos_logistica import (
    Equipo,
    EstadoEquipo,
    MovimientoInventario,
    Tercero,
    TipoMovimientoInventario,
)
from app.modelos_operaciones import (
    Cotizacion,
    CotizacionDetalle,
    DevolucionGarantia,
    EstadoCotizacion,
    ModalidadCotizacion,
    TipoResolucionDevolucion,
)
from app.modelos_taller import CasoPostventa, EstadoCasoPostventa, TipoCasoPostventa
from app.rutas.logistica import calcular_stock_componente
from app.rutas.tasas import obtener_fecha_hoy
from app.rutas.ventas import (
    generar_correlativo_corto,
    obtener_precio_y_costo_articulo,
    redondear_usd,
    verificar_mes_abierto,
)
from app.core.permisos import Permiso, sanear_respuesta_costos, tiene_permiso
from app.seguridad import obtener_usuario_actual, puede_ver_costos
from app.servicios.pdf_documentos import (
    generar_pdf_cotizacion,
    generar_pdf_devolucion_garantia,
    generar_pdf_lista_precios,
)


enrutador = APIRouter(prefix="/api", tags=["Operaciones, Precios y Cotizaciones"])

ROLES_REEMBOLSO = {RolUsuario.ADMINISTRACION.value, RolUsuario.DIRECCION.value}


def _obtener_tasa_actual(bd: Session, fecha_ref: date) -> tuple[Decimal, Decimal, Decimal]:
    """Devuelve (tasa_bcv, tasa_usdt, recargo_pct) usando la tasa del día o la más reciente."""
    tasa = (
        bd.query(TasaDiaria)
        .filter(TasaDiaria.fecha <= fecha_ref)
        .order_by(TasaDiaria.fecha.desc())
        .first()
    )
    if tasa is None:
        return Decimal("0"), Decimal("0"), Decimal("20")
    return tasa.tasa_bcv, tasa.tasa_usdt, tasa.recargo_porcentaje


def _calcular_regular(promo_usd: Decimal, regular_fijo: Decimal | None, recargo_pct: Decimal) -> Decimal:
    if promo_usd <= 0:
        return Decimal("0.00")
    if regular_fijo is not None and regular_fijo > 0:
        return regular_fijo.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    factor = Decimal("1") + (recargo_pct / Decimal("100"))
    return (promo_usd * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _serializar_devolucion(dev: DevolucionGarantia, incluir_costos: bool) -> dict[str, Any]:
    venta = dev.venta
    cli = venta.cliente if venta else None
    datos: dict[str, Any] = {
        "id": dev.id,
        "numero_operacion": dev.numero_operacion,
        "fecha": dev.fecha.isoformat(),
        "venta_id": dev.venta_id,
        "numero_venta": venta.numero_venta if venta else None,
        "cliente": cli.nombre if cli else "Cliente general",
        "cliente_telefono": cli.telefono if cli and cli.telefono else "",
        "sucursal": venta.sucursal.nombre if venta and venta.sucursal else None,
        "tipo_resolucion": dev.tipo_resolucion,
        "estado_reingreso_origen": dev.estado_reingreso_origen,
        "equipo_origen_id": dev.equipo_origen_id,
        "equipo_origen_serial": dev.equipo_origen.serial if dev.equipo_origen else None,
        "equipo_origen_modelo": dev.equipo_origen.modelo if dev.equipo_origen else None,
        "equipo_destino_id": dev.equipo_destino_id,
        "equipo_destino_serial": dev.equipo_destino.serial if dev.equipo_destino else None,
        "equipo_destino_modelo": dev.equipo_destino.modelo if dev.equipo_destino else None,
        "caso_taller_id": dev.caso_taller_id,
        "caso_taller_numero": dev.caso_taller.numero_caso if dev.caso_taller else None,
        "articulo_repuesto_id": dev.articulo_repuesto_id,
        "articulo_repuesto_descripcion": (
            dev.articulo_repuesto.descripcion if dev.articulo_repuesto else None
        ),
        "diferencia_usd": redondear_usd(dev.diferencia_usd),
        "diferencia_promo_usd": redondear_usd(dev.diferencia_promo_usd),
        "instrumento_id": dev.instrumento_id,
        "instrumento": dev.instrumento.nombre if dev.instrumento else None,
        "dejar_saldo_favor": dev.dejar_saldo_favor,
        "referencia_pago": dev.referencia_pago,
        "motivo": dev.motivo,
        "autorizado_por": dev.autorizado_por.nombre if dev.autorizado_por else None,
        "creado_en": dev.creado_en.isoformat() if dev.creado_en else None,
    }
    if incluir_costos:
        datos["costo_garantia_usd"] = redondear_usd(dev.costo_garantia_usd)
    return datos


# =====================================================================
# 1. DEVOLUCIONES, CAMBIOS Y GARANTÍAS (5 ESCENARIOS)
# =====================================================================


@enrutador.get("/devoluciones-garantias")
def listar_devoluciones_garantias(
    venta_id: int | None = Query(default=None),
    tipo_resolucion: str | None = Query(default=None),
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    consulta = (
        bd.query(DevolucionGarantia)
        .options(
            joinedload(DevolucionGarantia.venta).joinedload(Venta.cliente),
            joinedload(DevolucionGarantia.venta).joinedload(Venta.sucursal),
            joinedload(DevolucionGarantia.equipo_origen),
            joinedload(DevolucionGarantia.equipo_destino),
            joinedload(DevolucionGarantia.caso_taller),
            joinedload(DevolucionGarantia.articulo_repuesto),
            joinedload(DevolucionGarantia.instrumento),
            joinedload(DevolucionGarantia.autorizado_por),
        )
        .order_by(DevolucionGarantia.id.desc())
    )
    if venta_id is not None:
        consulta = consulta.filter(DevolucionGarantia.venta_id == venta_id)
    if tipo_resolucion:
        consulta = consulta.filter(DevolucionGarantia.tipo_resolucion == tipo_resolucion)

    incluir_costos = puede_ver_costos(usuario_actual.rol)
    return sanear_respuesta_costos(
        [_serializar_devolucion(d, incluir_costos) for d in consulta.all()],
        usuario_actual.rol,
    )


@enrutador.post("/devoluciones-garantias", status_code=status.HTTP_201_CREATED)
def crear_devolucion_garantia(
    datos: DevolucionGarantiaCrearEntrada,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    fecha_op = obtener_fecha_hoy()
    verificar_mes_abierto(bd, fecha_op)

    venta = (
        bd.query(Venta)
        .options(
            joinedload(Venta.cliente),
            joinedload(Venta.sucursal),
            joinedload(Venta.detalles).joinedload(VentaDetalle.equipo),
            joinedload(Venta.pagos),
        )
        .filter(Venta.id == datos.venta_id)
        .first()
    )
    if venta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada.")
    if venta.estado in (EstadoVenta.ANULADA.value, EstadoVenta.DEVUELTA.value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La venta {venta.numero_venta} ya se encuentra en estado {venta.estado}.",
        )

    tipo = datos.tipo_resolucion
    # Restricción estricta de roles para reembolsos de dinero
    puede_reembolsar = tiene_permiso(usuario_actual.rol, Permiso.AUTORIZAR_REEMBOLSO)
    if tipo == TipoResolucionDevolucion.REEMBOLSO_TOTAL and not puede_reembolsar:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo Administración o Dirección pueden autorizar un Reembolso Total.",
        )
    if (
        tipo == TipoResolucionDevolucion.CAMBIO_DOWNGRADE
        and not datos.dejar_saldo_favor
        and not puede_reembolsar
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo Administración o Dirección pueden reembolsar efectivo/transferencia en un Downgrade. Puedes optar por dejar Saldo a Favor.",
        )

    tasa_bcv, tasa_usdt, recargo_pct = _obtener_tasa_actual(bd, fecha_op)
    numero_op = generar_correlativo_corto(bd, DevolucionGarantia, DevolucionGarantia.numero_operacion, "DEV")

    # Localizar equipo origen (si aplica)
    equipo_origen: Equipo | None = None
    detalle_origen: VentaDetalle | None = None
    if datos.equipo_origen_id is not None:
        detalle_origen = next((d for d in venta.detalles if d.equipo_id == datos.equipo_origen_id), None)
        if detalle_origen is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El equipo de origen indicado no pertenece a esta venta.",
            )
        equipo_origen = bd.query(Equipo).filter(Equipo.id == datos.equipo_origen_id).first()
    else:
        detalle_origen = next((d for d in venta.detalles if d.equipo_id is not None), None)
        if detalle_origen and detalle_origen.equipo_id:
            equipo_origen = bd.query(Equipo).filter(Equipo.id == detalle_origen.equipo_id).first()

    equipo_destino: Equipo | None = None
    caso_taller: CasoPostventa | None = None
    articulo_repuesto: CatalogoArticulo | None = None
    instrumento: InstrumentoFinanciero | None = None
    diferencia_usd = Decimal("0")
    diferencia_promo_usd = Decimal("0")
    costo_garantia_usd = Decimal("0")

    def _reingresar_equipo(eq: Equipo, estado_nuevo: str, motivo_mov: str) -> None:
        eq.estado = estado_nuevo
        bd.add(
            MovimientoInventario(
                tipo=TipoMovimientoInventario.AJUSTE_POSITIVO.value,
                articulo_id=eq.articulo_id,
                equipo_id=eq.id,
                sucursal_id=venta.sucursal_id,
                cantidad=1,
                costo_unitario_usd=eq.costo_compra_usd,
                documento_ref=numero_op,
                motivo=motivo_mov,
                usuario_id=usuario_actual.id,
            )
        )

    def _entregar_equipo_destino(eq_id: int | None) -> tuple[Equipo, Decimal, Decimal]:
        if eq_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes seleccionar el equipo de reemplazo (serial en estado LISTO).",
            )
        eq_dest = bd.query(Equipo).filter(Equipo.id == eq_id).first()
        if eq_dest is None or eq_dest.estado != EstadoEquipo.LISTO.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El equipo de reemplazo debe existir y estar en estado LISTO.",
            )
        p_promo = Decimal(str(eq_dest.precio_promo_usd or 0))
        p_reg_fijo: Decimal | None = None
        if eq_dest.articulo_id:
            cat_promo, cat_reg_fijo, _ = obtener_precio_y_costo_articulo(bd, eq_dest.articulo_id, fecha_op)
            if p_promo <= 0:
                p_promo = cat_promo
            p_reg_fijo = cat_reg_fijo
        p_reg = _calcular_regular(p_promo, p_reg_fijo, recargo_pct)
        eq_dest.estado = EstadoEquipo.VENDIDO.value
        bd.add(
            MovimientoInventario(
                tipo=TipoMovimientoInventario.VENTA.value,
                articulo_id=eq_dest.articulo_id,
                equipo_id=eq_dest.id,
                sucursal_id=venta.sucursal_id,
                cantidad=-1,
                costo_unitario_usd=eq_dest.costo_compra_usd,
                documento_ref=numero_op,
                motivo=f"Entrega por {tipo.value} ({numero_op}) sobre {venta.numero_venta}",
                usuario_id=usuario_actual.id,
            )
        )
        return eq_dest, p_promo, p_reg

    # ---- ESCENARIO 1: CAMBIO_IGUAL ----
    if tipo == TipoResolucionDevolucion.CAMBIO_IGUAL:
        if equipo_origen is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Esta venta no tiene un equipo serializado para cambiar.",
            )
        equipo_destino, _, _ = _entregar_equipo_destino(datos.equipo_destino_id)
        if (
            equipo_origen.articulo_id is not None
            and equipo_destino.articulo_id is not None
            and equipo_origen.articulo_id != equipo_destino.articulo_id
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Para CAMBIO_IGUAL el equipo destino debe ser del mismo SKU/modelo. Usa Upgrade o Downgrade si es otro modelo.",
            )
        _reingresar_equipo(
            equipo_origen,
            datos.estado_reingreso_origen,
            f"Reingreso por cambio igual ({numero_op}) de {venta.numero_venta}",
        )
        diferencia_usd = Decimal("0")
        diferencia_promo_usd = Decimal("0")

    # ---- ESCENARIO 2: GARANTIA_COMPONENTE ----
    elif tipo == TipoResolucionDevolucion.GARANTIA_COMPONENTE:
        num_gt = generar_correlativo_corto(bd, CasoPostventa, CasoPostventa.numero_caso, "GT")
        desc_eq = (
            equipo_origen.modelo
            if equipo_origen
            else (detalle_origen.descripcion if detalle_origen else f"Equipo de {venta.numero_venta}")
        )
        serial_eq = equipo_origen.serial if equipo_origen else venta.numero_venta
        falla_txt = (
            f"Garantía de componente ({datos.componente_afectado.strip()}): {datos.motivo.strip()}"
            if datos.componente_afectado.strip()
            else f"Garantía de componente: {datos.motivo.strip()}"
        )
        caso_taller = CasoPostventa(
            numero_caso=num_gt,
            tipo=TipoCasoPostventa.GARANTIA.value,
            sucursal_id=venta.sucursal_id,
            cliente_id=venta.cliente_id,
            equipo_id=equipo_origen.id if equipo_origen else None,
            serial_o_codigo=serial_eq,
            descripcion_equipo=desc_eq,
            falla_reportada=falla_txt,
            estado=EstadoCasoPostventa.RECIBIDO.value,
            alerta_garantia=f"Vinculado a {venta.numero_venta} ({numero_op})",
        )
        bd.add(caso_taller)
        bd.flush()

        if datos.articulo_repuesto_id is not None:
            articulo_repuesto = (
                bd.query(CatalogoArticulo)
                .filter(CatalogoArticulo.id == datos.articulo_repuesto_id)
                .first()
            )
            if articulo_repuesto is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="El repuesto/componente seleccionado no existe.",
                )
            stock_disp = calcular_stock_componente(bd, articulo_repuesto.id, venta.sucursal_id)
            if stock_disp < datos.cantidad_repuesto:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Stock insuficiente de '{articulo_repuesto.descripcion}' en esta sucursal (disponible: {stock_disp}).",
                )
            _, _, costo_ref = obtener_precio_y_costo_articulo(bd, articulo_repuesto.id, fecha_op)
            costo_garantia_usd = (costo_ref * Decimal(datos.cantidad_repuesto)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            bd.add(
                MovimientoInventario(
                    tipo=TipoMovimientoInventario.TALLER.value,
                    articulo_id=articulo_repuesto.id,
                    equipo_id=equipo_origen.id if equipo_origen else None,
                    sucursal_id=venta.sucursal_id,
                    cantidad=-datos.cantidad_repuesto,
                    costo_unitario_usd=costo_ref,
                    documento_ref=num_gt,
                    motivo=f"Repuesto por garantía sin cargo al cliente ({numero_op} / {num_gt})",
                    usuario_id=usuario_actual.id,
                )
            )
        diferencia_usd = Decimal("0")
        diferencia_promo_usd = Decimal("0")

    # ---- ESCENARIO 3: CAMBIO_UPGRADE ----
    elif tipo == TipoResolucionDevolucion.CAMBIO_UPGRADE:
        if equipo_origen is None or detalle_origen is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Esta venta no tiene un equipo serializado para hacer Upgrade.",
            )
        if datos.instrumento_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes seleccionar el método/instrumento de pago para cobrar la diferencia del Upgrade.",
            )
        instrumento = (
            bd.query(InstrumentoFinanciero)
            .filter(InstrumentoFinanciero.id == datos.instrumento_id)
            .first()
        )
        if instrumento is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instrumento financiero no encontrado.")

        equipo_destino, dest_promo, dest_reg = _entregar_equipo_destino(datos.equipo_destino_id)
        origen_promo = detalle_origen.precio_promo_usd
        origen_reg = detalle_origen.precio_regular_usd
        dif_promo = (dest_promo - origen_promo).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if dif_promo <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El equipo destino no tiene un precio superior al equipo original. Usa Cambio Igual o Downgrade.",
            )

        es_regular = (
            instrumento.moneda == MonedaInstrumento.BS.value
            or instrumento.tipo_precio == TipoPrecioInstrumento.REGULAR.value
            or "cashea" in instrumento.nombre.lower()
        )
        dif_cobrar_usd = (
            max(Decimal("0.01"), (dest_reg - origen_reg).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            if es_regular
            else dif_promo
        )

        if instrumento.moneda == MonedaInstrumento.BS.value:
            if tasa_bcv <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No existe tasa BCV registrada para cobrar la diferencia en bolívares.",
                )
            monto_origen = (
                datos.monto_pagado_origen
                if datos.monto_pagado_origen is not None and datos.monto_pagado_origen > 0
                else (dif_cobrar_usd * tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            )
            usd_nominal = (monto_origen / tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            usd_real = (
                (monto_origen / tasa_usdt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if tasa_usdt > 0
                else usd_nominal
            )
        else:
            monto_origen = (
                datos.monto_pagado_origen
                if datos.monto_pagado_origen is not None and datos.monto_pagado_origen > 0
                else dif_cobrar_usd
            )
            usd_nominal = monto_origen
            usd_real = monto_origen

        _reingresar_equipo(
            equipo_origen,
            datos.estado_reingreso_origen,
            f"Reingreso por Upgrade ({numero_op}) de {venta.numero_venta}",
        )
        bd.add(
            Pago(
                venta_id=venta.id,
                instrumento_id=instrumento.id,
                fecha=fecha_op,
                tipo_movimiento=TipoMovimientoPago.INGRESO.value,
                tipo_documento=TipoDocumentoPago.VENTA.value,
                monto_moneda_origen=monto_origen,
                moneda=instrumento.moneda,
                tasa_bcv_dia=tasa_bcv,
                tasa_usdt_dia=tasa_usdt,
                usd_nominal=usd_nominal,
                usd_real=usd_real,
                cubre_promo_usd=dif_promo,
                referencia=datos.referencia_pago.strip(),
                estado_verificacion=(
                    EstadoVerificacionPago.PENDIENTE.value
                    if instrumento.requiere_verificacion
                    else EstadoVerificacionPago.CONFIRMADO.value
                ),
                nota=f"Diferencia Upgrade {numero_op} ({equipo_origen.serial} -> {equipo_destino.serial})",
            )
        )
        diferencia_usd = usd_nominal
        diferencia_promo_usd = dif_promo

    # ---- ESCENARIO 4: CAMBIO_DOWNGRADE ----
    elif tipo == TipoResolucionDevolucion.CAMBIO_DOWNGRADE:
        if equipo_origen is None or detalle_origen is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Esta venta no tiene un equipo serializado para hacer Downgrade.",
            )
        equipo_destino, dest_promo, _ = _entregar_equipo_destino(datos.equipo_destino_id)
        origen_promo = detalle_origen.precio_promo_usd
        dif_favor_cliente = (origen_promo - dest_promo).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if dif_favor_cliente <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El equipo destino no tiene un precio menor al equipo original. Usa Cambio Igual o Upgrade.",
            )

        _reingresar_equipo(
            equipo_origen,
            datos.estado_reingreso_origen,
            f"Reingreso por Downgrade ({numero_op}) de {venta.numero_venta}",
        )

        if datos.dejar_saldo_favor:
            if venta.cliente is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La venta no tiene cliente asignado para acreditar Saldo a Favor.",
                )
            venta.cliente.saldo_favor_usd = (
                Decimal(str(venta.cliente.saldo_favor_usd or 0)) + dif_favor_cliente
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            if datos.instrumento_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Debes seleccionar el instrumento financiero para reembolsar la diferencia al cliente.",
                )
            instrumento = (
                bd.query(InstrumentoFinanciero)
                .filter(InstrumentoFinanciero.id == datos.instrumento_id)
                .first()
            )
            if instrumento is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instrumento financiero no encontrado.")
            if instrumento.moneda == MonedaInstrumento.BS.value:
                if tasa_bcv <= 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="No existe tasa BCV registrada para registrar el egreso en bolívares.",
                    )
                monto_origen = (dif_favor_cliente * tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                usd_real = (
                    (monto_origen / tasa_usdt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    if tasa_usdt > 0
                    else dif_favor_cliente
                )
            else:
                monto_origen = dif_favor_cliente
                usd_real = dif_favor_cliente
            bd.add(
                Pago(
                    venta_id=venta.id,
                    instrumento_id=instrumento.id,
                    fecha=fecha_op,
                    tipo_movimiento=TipoMovimientoPago.EGRESO.value,
                    tipo_documento=TipoDocumentoPago.DEVOLUCION.value,
                    monto_moneda_origen=monto_origen,
                    moneda=instrumento.moneda,
                    tasa_bcv_dia=tasa_bcv,
                    tasa_usdt_dia=tasa_usdt,
                    usd_nominal=dif_favor_cliente,
                    usd_real=usd_real,
                    cubre_promo_usd=dif_favor_cliente,
                    referencia=datos.referencia_pago.strip(),
                    estado_verificacion=EstadoVerificacionPago.CONFIRMADO.value,
                    nota=f"Reembolso diferencia Downgrade {numero_op}",
                )
            )
        diferencia_usd = -dif_favor_cliente
        diferencia_promo_usd = -dif_favor_cliente

    # ---- ESCENARIO 5: REEMBOLSO_TOTAL ----
    elif tipo == TipoResolucionDevolucion.REEMBOLSO_TOTAL:
        if datos.instrumento_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes seleccionar el instrumento financiero desde el cual se realiza el reembolso.",
            )
        instrumento = (
            bd.query(InstrumentoFinanciero)
            .filter(InstrumentoFinanciero.id == datos.instrumento_id)
            .first()
        )
        if instrumento is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instrumento financiero no encontrado.")

        # Reingresar equipo origen o todos los equipos de la venta
        equipos_reingresar: list[Equipo] = []
        if equipo_origen is not None:
            equipos_reingresar.append(equipo_origen)
        else:
            for d in venta.detalles:
                if d.equipo is not None:
                    equipos_reingresar.append(d.equipo)
        for eq in equipos_reingresar:
            _reingresar_equipo(
                eq,
                datos.estado_reingreso_origen,
                f"Reingreso por Reembolso Total ({numero_op}) de {venta.numero_venta}",
            )

        total_pagado_usd = sum(
            (p.usd_nominal for p in venta.pagos if not p.anulado and p.tipo_movimiento == TipoMovimientoPago.INGRESO.value),
            Decimal("0"),
        )
        monto_reembolso_usd = (
            datos.monto_pagado_origen
            if datos.monto_pagado_origen is not None and datos.monto_pagado_origen > 0 and instrumento.moneda != MonedaInstrumento.BS.value
            else (total_pagado_usd if total_pagado_usd > 0 else venta.total_promo_usd)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if instrumento.moneda == MonedaInstrumento.BS.value:
            if tasa_bcv <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No existe tasa BCV registrada para reembolsar en bolívares.",
                )
            monto_origen = (
                datos.monto_pagado_origen
                if datos.monto_pagado_origen is not None and datos.monto_pagado_origen > 0
                else (monto_reembolso_usd * tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            )
            usd_nominal = (monto_origen / tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            usd_real = (
                (monto_origen / tasa_usdt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if tasa_usdt > 0
                else usd_nominal
            )
        else:
            monto_origen = monto_reembolso_usd
            usd_nominal = monto_reembolso_usd
            usd_real = monto_reembolso_usd

        bd.add(
            Pago(
                venta_id=venta.id,
                instrumento_id=instrumento.id,
                fecha=fecha_op,
                tipo_movimiento=TipoMovimientoPago.EGRESO.value,
                tipo_documento=TipoDocumentoPago.DEVOLUCION.value,
                monto_moneda_origen=monto_origen,
                moneda=instrumento.moneda,
                tasa_bcv_dia=tasa_bcv,
                tasa_usdt_dia=tasa_usdt,
                usd_nominal=usd_nominal,
                usd_real=usd_real,
                cubre_promo_usd=venta.total_promo_usd,
                referencia=datos.referencia_pago.strip(),
                estado_verificacion=EstadoVerificacionPago.CONFIRMADO.value,
                nota=f"Reembolso Total {numero_op} · {datos.motivo.strip()}",
            )
        )
        venta.estado = EstadoVenta.DEVUELTA.value
        diferencia_usd = -usd_nominal
        diferencia_promo_usd = -venta.total_promo_usd

    registro = DevolucionGarantia(
        numero_operacion=numero_op,
        venta_id=venta.id,
        equipo_origen_id=equipo_origen.id if equipo_origen else None,
        equipo_destino_id=equipo_destino.id if equipo_destino else None,
        caso_taller_id=caso_taller.id if caso_taller else None,
        articulo_repuesto_id=articulo_repuesto.id if articulo_repuesto else None,
        tipo_resolucion=tipo.value,
        estado_reingreso_origen=datos.estado_reingreso_origen,
        diferencia_usd=diferencia_usd,
        diferencia_promo_usd=diferencia_promo_usd,
        costo_garantia_usd=costo_garantia_usd,
        instrumento_id=instrumento.id if instrumento else None,
        dejar_saldo_favor=datos.dejar_saldo_favor,
        referencia_pago=datos.referencia_pago.strip(),
        motivo=datos.motivo.strip(),
        autorizado_por_id=usuario_actual.id,
        fecha=fecha_op,
    )
    bd.add(registro)
    bd.commit()

    dev_completa = (
        bd.query(DevolucionGarantia)
        .options(
            joinedload(DevolucionGarantia.venta).joinedload(Venta.cliente),
            joinedload(DevolucionGarantia.venta).joinedload(Venta.sucursal),
            joinedload(DevolucionGarantia.equipo_origen),
            joinedload(DevolucionGarantia.equipo_destino),
            joinedload(DevolucionGarantia.caso_taller),
            joinedload(DevolucionGarantia.articulo_repuesto),
            joinedload(DevolucionGarantia.instrumento),
            joinedload(DevolucionGarantia.autorizado_por),
        )
        .filter(DevolucionGarantia.id == registro.id)
        .first()
    )
    return sanear_respuesta_costos(
        _serializar_devolucion(dev_completa, puede_ver_costos(usuario_actual.rol)),
        usuario_actual.rol,
    )


@enrutador.get("/devoluciones-garantias/{dev_id}/pdf")
def descargar_pdf_devolucion_garantia(
    dev_id: int,
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> Response:
    dev = (
        bd.query(DevolucionGarantia)
        .options(
            joinedload(DevolucionGarantia.venta).joinedload(Venta.cliente),
            joinedload(DevolucionGarantia.venta).joinedload(Venta.sucursal),
            joinedload(DevolucionGarantia.equipo_origen),
            joinedload(DevolucionGarantia.equipo_destino),
            joinedload(DevolucionGarantia.caso_taller),
            joinedload(DevolucionGarantia.articulo_repuesto),
            joinedload(DevolucionGarantia.instrumento),
            joinedload(DevolucionGarantia.autorizado_por),
        )
        .filter(DevolucionGarantia.id == dev_id)
        .first()
    )
    if dev is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro de devolución/garantía no encontrado.")

    pdf_bytes = generar_pdf_devolucion_garantia(dev)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="comprobante-{dev.numero_operacion}.pdf"'},
    )


# =====================================================================
# 2. LISTA DE PRECIOS DE EQUIPOS DISPONIBLES (SOLO LISTO, SIN COSTOS)
# =====================================================================


def _construir_lista_precios(
    bd: Session,
    sucursal_id: int | None = None,
    categoria: str | None = None,
    tipo_precio: str = "PROMO",
) -> dict[str, Any]:
    hoy = obtener_fecha_hoy()
    tasa_bcv, _, recargo_pct = _obtener_tasa_actual(bd, hoy)
    modo = "REGULAR" if (tipo_precio or "").strip().upper() == "REGULAR" else "PROMO"

    sucursal_nombre = "Todas las sucursales"
    if sucursal_id is not None:
        suc = bd.query(Sucursal).filter(Sucursal.id == sucursal_id).first()
        if suc:
            sucursal_nombre = suc.nombre

    consulta = (
        bd.query(Equipo)
        .options(joinedload(Equipo.articulo), joinedload(Equipo.ubicacion))
        .filter(Equipo.estado == EstadoEquipo.LISTO.value)
    )
    if sucursal_id is not None:
        consulta = consulta.filter(Equipo.ubicacion_id == sucursal_id)

    equipos_listos = consulta.all()

    agrupado: dict[tuple[str, str, str], dict[str, Any]] = {}
    for eq in equipos_listos:
        art = eq.articulo
        cat_item = (
            (art.categoria if art and art.categoria else None)
            or (eq.categoria if getattr(eq, "categoria", None) else None)
            or "Equipos"
        ).strip()
        if categoria and categoria.strip().lower() not in cat_item.lower():
            continue

        modelo_base = (eq.modelo or (art.descripcion if art else "") or "Equipo").strip()
        caract = (getattr(eq, "configuracion", "") or "").strip()
        if caract and caract.lower() in modelo_base.lower():
            caract = ""
        descripcion_completa = f"{modelo_base} · {caract}" if caract else modelo_base

        p_promo = Decimal(str(eq.precio_promo_usd or 0))
        p_reg_fijo: Decimal | None = None
        if art:
            cat_promo, cat_reg_fijo, _ = obtener_precio_y_costo_articulo(bd, art.id, hoy)
            if p_promo <= 0:
                p_promo = cat_promo
            p_reg_fijo = cat_reg_fijo
        p_reg = _calcular_regular(p_promo, p_reg_fijo, recargo_pct)
        p_bs = (
            (p_reg * tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if tasa_bcv > 0 and p_reg > 0
            else None
        )

        clave = (modelo_base.lower(), caract.lower(), f"{p_promo:.2f}")
        if clave not in agrupado:
            item_base: dict[str, Any] = {
                "modelo": modelo_base,
                "caracteristicas": caract,
                "descripcion": descripcion_completa,
                "categoria": cat_item,
                "disponibles": 0,
            }
            if modo == "REGULAR":
                item_base["precio_usd"] = redondear_usd(p_reg)
                item_base["precio_bs"] = float(p_bs) if p_bs is not None else None
            else:
                item_base["precio_usd"] = redondear_usd(p_promo)
            agrupado[clave] = item_base
        agrupado[clave]["disponibles"] += 1

    items = sorted(agrupado.values(), key=lambda x: (x["categoria"], x["modelo"], x["caracteristicas"]))
    respuesta: dict[str, Any] = {
        "fecha_emision": hoy.isoformat(),
        "sucursal": sucursal_nombre,
        "tipo_precio": modo,
        "total_modelos": len(items),
        "total_unidades": sum(i["disponibles"] for i in items),
        "items": items,
    }
    if modo == "REGULAR":
        respuesta["tasa_bcv"] = float(tasa_bcv)
    return respuesta


@enrutador.get("/catalogo/lista-precios")
def obtener_lista_precios(
    sucursal_id: int | None = Query(default=None),
    categoria: str | None = Query(default=None),
    tipo_precio: str = Query(default="PROMO"),
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    return _construir_lista_precios(
        bd,
        sucursal_id=sucursal_id,
        categoria=categoria,
        tipo_precio=tipo_precio,
    )


@enrutador.get("/catalogo/lista-precios-pdf")
def descargar_lista_precios_pdf(
    sucursal_id: int | None = Query(default=None),
    categoria: str | None = Query(default=None),
    tipo_precio: str = Query(default="PROMO"),
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> Response:
    datos = _construir_lista_precios(
        bd,
        sucursal_id=sucursal_id,
        categoria=categoria,
        tipo_precio=tipo_precio,
    )
    pdf_bytes = generar_pdf_lista_precios(
        items=datos["items"],
        sucursal_nombre=datos["sucursal"],
        fecha_emision=date.fromisoformat(datos["fecha_emision"]),
        tasa_bcv=Decimal(str(datos.get("tasa_bcv", 0))),
        tipo_precio=datos["tipo_precio"],
    )
    sufijo = datos["tipo_precio"].lower()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="lista-precios-tekio-{sufijo}-{datos["fecha_emision"]}.pdf"'
        },
    )


# =====================================================================
# 3. MÓDULO DE COTIZACIONES DE EQUIPOS
# =====================================================================


def _serializar_cotizacion(cot: Cotizacion) -> dict[str, Any]:
    cli = cot.cliente
    tasa_bcv = Decimal(str(cot.tasa_bcv_snapshot or 0))
    total_bs = (
        (cot.total_regular_usd * tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if tasa_bcv > 0
        else Decimal("0")
    )
    return {
        "id": cot.id,
        "numero_cotizacion": cot.numero_cotizacion,
        "fecha": cot.fecha.isoformat(),
        "vigencia_horas": cot.vigencia_horas,
        "estado": cot.estado,
        "modalidad_precio": cot.modalidad_precio,
        "cliente_id": cot.cliente_id,
        "cliente": cli.nombre if cli else "Cliente general",
        "cliente_rif": (
            f"{cli.tipo_documento}-{cli.documento}"
            if cli and cli.tipo_documento and cli.documento
            else (cli.rif_cedula if cli and cli.rif_cedula else "")
        ),
        "cliente_tipo_persona": cli.tipo_persona if cli and cli.tipo_persona else "NATURAL",
        "cliente_telefono": cli.telefono if cli and cli.telefono else "",
        "asesor_id": cot.asesor_id,
        "asesor": cot.asesor.nombre if cot.asesor else "Tienda",
        "sucursal_id": cot.sucursal_id,
        "sucursal": cot.sucursal.nombre if cot.sucursal else None,
        "venta_id": cot.venta_id,
        "numero_venta": cot.venta.numero_venta if cot.venta else None,
        "tasa_bcv_snapshot": float(cot.tasa_bcv_snapshot),
        "recargo_porcentaje_snapshot": float(cot.recargo_porcentaje_snapshot),
        "total_promo_usd": redondear_usd(cot.total_promo_usd),
        "total_regular_usd": redondear_usd(cot.total_regular_usd),
        "total_regular_bs": redondear_usd(total_bs),
        "nota": cot.nota,
        "creado_en": cot.creado_en.isoformat() if cot.creado_en else None,
        "detalles": [
            {
                "id": d.id,
                "equipo_id": d.equipo_id,
                "serial": d.equipo.serial if d.equipo else None,
                "articulo_id": d.articulo_id,
                "descripcion": d.descripcion,
                "descripcion_servicio": d.descripcion_servicio or "",
                "cantidad": d.cantidad,
                "precio_promo_usd": redondear_usd(d.precio_promo_usd),
                "precio_regular_usd": redondear_usd(d.precio_regular_usd),
                "precio_pactado_usd": (
                    redondear_usd(d.precio_pactado_usd) if d.precio_pactado_usd is not None else None
                ),
            }
            for d in cot.detalles
        ],
    }


def _actualizar_vencidas(bd: Session, cotizaciones: list[Cotizacion]) -> None:
    ahora = datetime.now(timezone.utc)
    cambio = False
    for c in cotizaciones:
        if c.estado != EstadoCotizacion.VIGENTE.value:
            continue
        base_dt = c.creado_en
        if base_dt is None:
            continue
        if base_dt.tzinfo is None:
            base_dt = base_dt.replace(tzinfo=timezone.utc)
        if ahora > base_dt + timedelta(hours=c.vigencia_horas):
            c.estado = EstadoCotizacion.VENCIDA.value
            cambio = True
    if cambio:
        bd.commit()


@enrutador.get("/cotizaciones")
def listar_cotizaciones(
    estado: str | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    consulta = (
        bd.query(Cotizacion)
        .options(
            joinedload(Cotizacion.cliente),
            joinedload(Cotizacion.asesor),
            joinedload(Cotizacion.sucursal),
            joinedload(Cotizacion.venta),
            joinedload(Cotizacion.detalles).joinedload(CotizacionDetalle.equipo),
        )
        .order_by(Cotizacion.id.desc())
    )
    if sucursal_id is not None:
        consulta = consulta.filter(Cotizacion.sucursal_id == sucursal_id)
    filas = consulta.all()
    _actualizar_vencidas(bd, filas)
    if estado:
        filas = [c for c in filas if c.estado == estado]
    return [_serializar_cotizacion(c) for c in filas]


@enrutador.get("/cotizaciones/{cot_id}")
def obtener_cotizacion(
    cot_id: int,
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    cot = (
        bd.query(Cotizacion)
        .options(
            joinedload(Cotizacion.cliente),
            joinedload(Cotizacion.asesor),
            joinedload(Cotizacion.sucursal),
            joinedload(Cotizacion.venta),
            joinedload(Cotizacion.detalles).joinedload(CotizacionDetalle.equipo),
        )
        .filter(Cotizacion.id == cot_id)
        .first()
    )
    if cot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cotización no encontrada.")
    _actualizar_vencidas(bd, [cot])
    return _serializar_cotizacion(cot)


@enrutador.post("/cotizaciones", status_code=status.HTTP_201_CREATED)
def crear_cotizacion(
    datos: CotizacionCrearEntrada,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    sucursal = bd.query(Sucursal).filter(Sucursal.id == datos.sucursal_id).first()
    if sucursal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada.")

    fecha_hoy = obtener_fecha_hoy()
    if datos.modalidad_precio in (ModalidadCotizacion.REGULAR, ModalidadCotizacion.CASHEA):
        tasa_hoy_obj = bd.query(TasaDiaria).filter(TasaDiaria.fecha == fecha_hoy).first()
        if tasa_hoy_obj is not None and not getattr(tasa_hoy_obj, "recargo_confirmado_hoy", True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes confirmar el porcentaje de recargo del día antes de emitir cotizaciones a Precio Regular.",
            )
    tasa_bcv, _, recargo_pct = _obtener_tasa_actual(bd, fecha_hoy)
    numero_cot = generar_correlativo_corto(bd, Cotizacion, Cotizacion.numero_cotizacion, "COT")

    total_promo = Decimal("0")
    total_regular = Decimal("0")
    detalles_obj: list[CotizacionDetalle] = []

    for item in datos.items:
        equipo: Equipo | None = None
        articulo: CatalogoArticulo | None = None
        descripcion = item.descripcion_libre.strip()
        p_promo_base = Decimal("0")
        p_reg_fijo: Decimal | None = None

        if item.equipo_id is not None:
            equipo = bd.query(Equipo).filter(Equipo.id == item.equipo_id).first()
            if equipo is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Equipo #{item.equipo_id} no encontrado.",
                )
            if equipo.articulo_id:
                articulo = bd.query(CatalogoArticulo).filter(CatalogoArticulo.id == equipo.articulo_id).first()
                p_promo_base, p_reg_fijo, _ = obtener_precio_y_costo_articulo(bd, equipo.articulo_id, fecha_hoy)
            descripcion = descripcion or (articulo.descripcion if articulo else equipo.modelo)
        elif item.articulo_id is not None:
            articulo = bd.query(CatalogoArticulo).filter(CatalogoArticulo.id == item.articulo_id).first()
            if articulo is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Artículo #{item.articulo_id} no encontrado.",
                )
            p_promo_base, p_reg_fijo, _ = obtener_precio_y_costo_articulo(bd, articulo.id, fecha_hoy)
            descripcion = descripcion or articulo.descripcion

        if not descripcion:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cada línea de la cotización debe tener un equipo, artículo o descripción.",
            )

        if item.precio_pactado_usd is not None:
            p_promo = item.precio_pactado_usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            p_reg = _calcular_regular(p_promo, None, recargo_pct)
        else:
            p_promo = p_promo_base.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            p_reg = _calcular_regular(p_promo, p_reg_fijo, recargo_pct)

        total_promo += p_promo * Decimal(item.cantidad)
        total_regular += p_reg * Decimal(item.cantidad)

        detalles_obj.append(
            CotizacionDetalle(
                equipo_id=equipo.id if equipo else None,
                articulo_id=articulo.id if articulo else None,
                descripcion=descripcion,
                descripcion_servicio=item.descripcion_servicio.strip(),
                cantidad=item.cantidad,
                precio_promo_usd=p_promo,
                precio_regular_usd=p_reg,
                precio_pactado_usd=item.precio_pactado_usd,
            )
        )

    cot = Cotizacion(
        numero_cotizacion=numero_cot,
        fecha=fecha_hoy,
        vigencia_horas=datos.vigencia_horas,
        estado=EstadoCotizacion.VIGENTE.value,
        modalidad_precio=datos.modalidad_precio.value,
        cliente_id=datos.cliente_id,
        asesor_id=datos.asesor_id,
        sucursal_id=datos.sucursal_id,
        tasa_bcv_snapshot=tasa_bcv,
        recargo_porcentaje_snapshot=recargo_pct,
        total_promo_usd=total_promo.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        total_regular_usd=total_regular.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        nota=datos.nota.strip(),
        creado_por_id=usuario_actual.id,
        detalles=detalles_obj,
    )
    bd.add(cot)
    bd.commit()

    cot_completa = (
        bd.query(Cotizacion)
        .options(
            joinedload(Cotizacion.cliente),
            joinedload(Cotizacion.asesor),
            joinedload(Cotizacion.sucursal),
            joinedload(Cotizacion.venta),
            joinedload(Cotizacion.detalles).joinedload(CotizacionDetalle.equipo),
        )
        .filter(Cotizacion.id == cot.id)
        .first()
    )
    return _serializar_cotizacion(cot_completa)


@enrutador.patch("/cotizaciones/{cot_id}/estado")
def actualizar_estado_cotizacion(
    cot_id: int,
    datos: CotizacionEstadoEntrada,
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    cot = bd.query(Cotizacion).filter(Cotizacion.id == cot_id).first()
    if cot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cotización no encontrada.")
    cot.estado = datos.estado.value
    bd.commit()
    return {"id": cot.id, "numero_cotizacion": cot.numero_cotizacion, "estado": cot.estado}


@enrutador.get("/cotizaciones/{cot_id}/pdf")
def descargar_pdf_cotizacion(
    cot_id: int,
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> Response:
    cot = (
        bd.query(Cotizacion)
        .options(
            joinedload(Cotizacion.cliente),
            joinedload(Cotizacion.asesor),
            joinedload(Cotizacion.sucursal),
            joinedload(Cotizacion.detalles).joinedload(CotizacionDetalle.equipo),
        )
        .filter(Cotizacion.id == cot_id)
        .first()
    )
    if cot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cotización no encontrada.")

    pdf_bytes = generar_pdf_cotizacion(cot)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="cotizacion-{cot.numero_cotizacion}.pdf"'},
    )
