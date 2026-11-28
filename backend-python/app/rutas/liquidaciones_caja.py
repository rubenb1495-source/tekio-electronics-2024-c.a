from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.esquemas_operaciones import (
    CierreCajaCrearEntrada,
    LiquidacionAnularEntrada,
    LiquidacionComisionCrearEntrada,
)
from app.modelos import RolUsuario, Sucursal, TasaDiaria, Usuario
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
    MovimientoInventario,
    TipoMovimientoInventario,
)
from app.modelos_operaciones import (
    CierreCaja,
    LiquidacionComision,
    LiquidacionComisionDetalle,
)
from app.modelos_taller import (
    CasoPostventa,
    EstadoCasoPostventa,
    TipoCasoPostventa,
)
from app.rutas.finanzas import calcular_reporte_comisiones_rango
from app.rutas.tasas import obtener_fecha_hoy
from app.rutas.ventas import generar_correlativo_corto, redondear_usd, verificar_mes_abierto
from app.core.permisos import Permiso, require_permiso, validar_sucursal_permitida
from app.seguridad import ROLES_ADMINISTRATIVOS, obtener_usuario_actual, requerir_roles
from app.servicios.auditoria_service import registrar_auditoria
from app.servicios.pdf_documentos import (
    generar_pdf_cierre_caja,
    generar_pdf_liquidacion_comision,
)


enrutador = APIRouter(prefix="/api/finanzas", tags=["Liquidaciones y Cierre de Caja"])


def _serializar_liquidacion(liq: LiquidacionComision) -> dict[str, Any]:
    estado_liq = getattr(liq, "estado", "ACTIVA") or "ACTIVA"
    if liq.detalles:
        cant_ops = len(liq.detalles)
        notas_liq = [d.referencia_origen for d in liq.detalles if d.referencia_origen]
    else:
        try:
            snap = json.loads(getattr(liq, "detalle_anulado_json", "[]") or "[]")
        except Exception:
            snap = []
        cant_ops = len(snap)
        notas_liq = [str(d.get("referencia_origen") or "") for d in snap if d.get("referencia_origen")]
    return {
        "id": liq.id,
        "codigo": liq.codigo,
        "estado": estado_liq,
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
        "anulada_por": liq.anulada_por.nombre if getattr(liq, "anulada_por", None) else None,
        "fecha_anulacion": liq.fecha_anulacion.isoformat() if getattr(liq, "fecha_anulacion", None) else None,
        "motivo_anulacion": getattr(liq, "motivo_anulacion", "") or "",
        "notas": liq.notas,
        "cantidad_operaciones": cant_ops,
        "notas_liquidadas": notas_liq,
        "creado_en": liq.creado_en.isoformat() if liq.creado_en else None,
    }


@enrutador.get("/liquidaciones")
def listar_liquidaciones(
    usuario_id: int | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.LIQUIDAR_COMISIONES)),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    consulta = (
        bd.query(LiquidacionComision)
        .options(
            joinedload(LiquidacionComision.usuario),
            joinedload(LiquidacionComision.autorizado_por),
            joinedload(LiquidacionComision.anulada_por),
            joinedload(LiquidacionComision.instrumento),
            joinedload(LiquidacionComision.detalles),
        )
        .order_by(LiquidacionComision.id.desc())
    )
    if usuario_id is not None:
        consulta = consulta.filter(LiquidacionComision.usuario_id == usuario_id)
    return [_serializar_liquidacion(liq) for liq in consulta.all()]


@enrutador.post("/liquidaciones/{liq_id}/anular")
def anular_liquidacion_comisiones(
    liq_id: int,
    datos: LiquidacionAnularEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.LIQUIDAR_COMISIONES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    liq = (
        bd.query(LiquidacionComision)
        .options(
            joinedload(LiquidacionComision.usuario),
            joinedload(LiquidacionComision.autorizado_por),
            joinedload(LiquidacionComision.instrumento),
            joinedload(LiquidacionComision.detalles),
            joinedload(LiquidacionComision.pago_egreso),
        )
        .filter(LiquidacionComision.id == liq_id)
        .first()
    )
    if liq is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Liquidación de comisiones no encontrada.",
        )
    if (liq.estado or "ACTIVA") == "ANULADA":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La liquidación {liq.codigo} ya se encuentra ANULADA.",
        )

    motivo = datos.motivo_anulacion.strip()
    if len(motivo) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes indicar un motivo de anulación válido.",
        )

    # 1. Guardar snapshot de auditoría de las operaciones liquidadas antes de liberar candado
    snapshot_detalles = [
        {
            "venta_id": d.venta_id,
            "usuario_id": d.usuario_id,
            "referencia_origen": d.referencia_origen,
            "concepto": d.concepto,
            "base_promo_usd": redondear_usd(d.base_promo_usd),
            "monto_comision_usd": redondear_usd(d.monto_comision_usd),
        }
        for d in liq.detalles
    ]
    liq.detalle_anulado_json = json.dumps(snapshot_detalles, ensure_ascii=False)

    # 2. Liberar operaciones de liquidaciones_comisiones_detalle para que vuelvan a PENDIENTE
    bd.query(LiquidacionComisionDetalle).filter(
        LiquidacionComisionDetalle.liquidacion_id == liq.id
    ).delete(synchronize_session=False)

    # 3. Revertir automáticamente el egreso financiero asociado
    if liq.pago_egreso is not None:
        liq.pago_egreso.anulado = True
        nota_prev = (liq.pago_egreso.nota or "").strip()
        liq.pago_egreso.nota = f"{nota_prev} | ANULADO ({liq.codigo}): {motivo}".strip(" |")

    # 4. Marcar liquidación como ANULADA con trazabilidad de auditoría y reverso contable
    liq.estado = "ANULADA"
    liq.anulada_por_id = usuario_actual.id
    liq.fecha_anulacion = datetime.now(timezone.utc)
    liq.motivo_anulacion = motivo

    if liq.monto_total_usd > Decimal("0.00"):
        from app.servicios.contabilidad_service import registrar_asiento

        registrar_asiento(
            bd,
            fecha=obtener_fecha_hoy(),
            referencia=f"ANUL-{liq.codigo}",
            modulo_origen="COMISIONES_ANULACION",
            entidad_id=liq.id,
            descripcion=f"Reverso contable por anulación de liquidación {liq.codigo}: {motivo}",
            lineas=[
                {"codigo_cuenta": "1.1.01", "debe_usd": liq.monto_total_usd, "descripcion": f"Reverso egreso {liq.codigo}"},
                {"codigo_cuenta": "6.1.01", "haber_usd": liq.monto_total_usd, "descripcion": f"Reverso gasto comisiones {liq.codigo}"},
            ],
            creado_por_id=usuario_actual.id,
        )

    registrar_auditoria(
        bd,
        usuario_actual,
        "COMISIONES",
        "ANULAR_LIQUIDACION",
        liq.codigo,
        {"estado": "ACTIVA", "monto_total_usd": float(liq.monto_total_usd)},
        {"estado": "ANULADA", "motivo_anulacion": motivo},
    )
    bd.commit()
    liq_actualizada = (
        bd.query(LiquidacionComision)
        .options(
            joinedload(LiquidacionComision.usuario),
            joinedload(LiquidacionComision.autorizado_por),
            joinedload(LiquidacionComision.anulada_por),
            joinedload(LiquidacionComision.instrumento),
            joinedload(LiquidacionComision.detalles),
        )
        .filter(LiquidacionComision.id == liq.id)
        .first()
    )
    return _serializar_liquidacion(liq_actualizada)


@enrutador.post("/liquidaciones", status_code=status.HTTP_201_CREATED)
def crear_liquidacion_comisiones(
    datos: LiquidacionComisionCrearEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.LIQUIDAR_COMISIONES)),
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
        _, ops_pagadas = calcular_reporte_comisiones_rango(
            bd,
            fecha_inicio=f_ini,
            fecha_fin=f_fin,
            usuario_id=datos.usuario_id,
            estado="PAGADA",
        )
        if ops_pagadas:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Las comisiones de este colaborador en el período indicado ya fueron liquidadas.",
            )
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
        tipo_documento=TipoDocumentoPago.LIQUIDACION_COMISION.value,
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

    if liq.monto_total_usd > Decimal("0.00"):
        from app.servicios.contabilidad_service import registrar_asiento

        registrar_asiento(
            bd,
            fecha=fecha_pago,
            referencia=liq.codigo,
            modulo_origen="COMISIONES",
            entidad_id=liq.id,
            descripcion=f"Liquidación de comisiones {liq.codigo} a {colaborador.nombre}",
            lineas=[
                {"codigo_cuenta": "6.1.01", "debe_usd": liq.monto_total_usd, "descripcion": f"Comisiones {colaborador.nombre}"},
                {"codigo_cuenta": "1.1.01", "haber_usd": liq.monto_total_usd, "descripcion": f"Pago por {instrumento.nombre}"},
            ],
            creado_por_id=usuario_actual.id,
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
    _usuario: Usuario = Depends(require_permiso(Permiso.LIQUIDAR_COMISIONES)),
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

    q_ventas = (
        bd.query(Venta)
        .options(joinedload(Venta.asesor))
        .filter(Venta.fecha == fecha_op)
    )
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

    # Desglose de ventas activas por asesor
    por_asesor: dict[str, dict[str, Any]] = {}
    for v in ventas_activas:
        clave_as = str(v.asesor_id or "tienda")
        if clave_as not in por_asesor:
            por_asesor[clave_as] = {
                "asesor_id": v.asesor_id,
                "asesor": v.asesor.nombre if v.asesor else "Tienda (Sin asesor)",
                "cantidad_ventas": 0,
                "total_promo_usd": Decimal("0"),
                "total_regular_usd": Decimal("0"),
            }
        por_asesor[clave_as]["cantidad_ventas"] += 1
        por_asesor[clave_as]["total_promo_usd"] += v.total_promo_usd
        por_asesor[clave_as]["total_regular_usd"] += v.total_regular_usd

    desglose_asesores = [
        {
            "asesor_id": a["asesor_id"],
            "asesor": a["asesor"],
            "cantidad_ventas": a["cantidad_ventas"],
            "total_promo_usd": redondear_usd(a["total_promo_usd"]),
            "total_regular_usd": redondear_usd(a["total_regular_usd"]),
        }
        for a in sorted(por_asesor.values(), key=lambda x: (-x["total_promo_usd"], x["asesor"]))
    ]

    # Movimientos financieros operativos del día
    # Excluye automáticamente egresos de tipo LIQUIDACION_COMISION para no distorsionar el cuadre diario
    q_pagos = (
        bd.query(Pago)
        .options(joinedload(Pago.instrumento), joinedload(Pago.venta))
        .filter(
            Pago.fecha == fecha_op,
            Pago.anulado.is_(False),
            Pago.tipo_documento != TipoDocumentoPago.LIQUIDACION_COMISION.value,
        )
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

    # Bloque Operativo Ampliado: Líder/Encargado, Tasas del Día, Inventario y Taller
    tz_caracas = ZoneInfo("America/Caracas")

    def _fecha_local(dt: datetime | None) -> date | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz_caracas).date()

    # 1. Líder Comercial / Encargado asignado
    q_lider = bd.query(Usuario).filter(
        Usuario.activo.is_(True),
        Usuario.rol.in_([RolUsuario.ENCARGADO.value, RolUsuario.LIDER.value]),
    )
    if sucursal_id is not None:
        q_lider = q_lider.filter(Usuario.sucursal_id == sucursal_id)
    lider_obj = q_lider.order_by(Usuario.id.asc()).first()
    lider_encargado = lider_obj.nombre if lider_obj else "Sin asignar"

    # 2. Tasas del día
    tasa_obj = (
        bd.query(TasaDiaria)
        .filter(TasaDiaria.fecha <= fecha_op)
        .order_by(TasaDiaria.fecha.desc())
        .first()
    )
    tasas_dia = {
        "fecha": tasa_obj.fecha.isoformat() if tasa_obj else fecha_op.isoformat(),
        "tasa_bcv": redondear_usd(tasa_obj.tasa_bcv) if tasa_obj else 0.0,
        "tasa_usdt": redondear_usd(tasa_obj.tasa_usdt) if tasa_obj else 0.0,
        "recargo_porcentaje": redondear_usd(tasa_obj.recargo_porcentaje) if tasa_obj else 0.0,
    }

    # 3. Bloque de Inventario y Almacén
    q_movs = bd.query(MovimientoInventario)
    if sucursal_id is not None:
        q_movs = q_movs.filter(MovimientoInventario.sucursal_id == sucursal_id)
    movs_dia = [m for m in q_movs.all() if _fecha_local(m.fecha) == fecha_op]

    recepciones_dia = sum(
        max(0, int(m.cantidad or 0))
        for m in movs_dia
        if m.tipo == TipoMovimientoInventario.COMPRA.value
    )
    traslados_recibidos_dia = sum(
        max(0, int(m.cantidad or 0))
        for m in movs_dia
        if m.tipo == TipoMovimientoInventario.TRASLADO_ENTRADA.value
    )
    traslados_despachados_dia = sum(
        abs(int(m.cantidad or 0))
        for m in movs_dia
        if m.tipo == TipoMovimientoInventario.TRASLADO_SALIDA.value
    )
    unidades_vendidas_dia = sum(
        sum(int(det.cantidad or 0) for det in v.detalles) for v in ventas_activas
    )
    unidades_salientes_dia = unidades_vendidas_dia + traslados_despachados_dia

    q_stock = bd.query(Equipo).filter(Equipo.estado == EstadoEquipo.LISTO.value)
    if sucursal_id is not None:
        q_stock = q_stock.filter(Equipo.ubicacion_id == sucursal_id)
    stock_disponible_listo = q_stock.count()

    inventario_resumen = {
        "recepciones_dia": recepciones_dia,
        "traslados_recibidos_dia": traslados_recibidos_dia,
        "unidades_vendidas_dia": unidades_vendidas_dia,
        "traslados_despachados_dia": traslados_despachados_dia,
        "unidades_salientes_dia": unidades_salientes_dia,
        "stock_disponible_listo": stock_disponible_listo,
    }

    # 4. Bloque de Taller / Garantías (GT y ST)
    q_casos = bd.query(CasoPostventa)
    if sucursal_id is not None:
        q_casos = q_casos.filter(CasoPostventa.sucursal_id == sucursal_id)
    casos_todos = q_casos.all()

    estados_resueltos = {
        EstadoCasoPostventa.TERMINADO.value,
        EstadoCasoPostventa.LISTO_PARA_ENTREGAR.value,
        EstadoCasoPostventa.ENTREGADO.value,
    }
    estados_cerrados = {
        EstadoCasoPostventa.ENTREGADO.value,
        EstadoCasoPostventa.RECHAZADO.value,
    }
    recibidos_taller = sum(1 for c in casos_todos if _fecha_local(c.fecha_ingreso) == fecha_op)
    resueltos_taller = sum(
        1
        for c in casos_todos
        if c.estado in estados_resueltos and _fecha_local(c.fecha_cierre) == fecha_op
    )
    casos_pendientes = [c for c in casos_todos if c.estado not in estados_cerrados]
    gt_pendientes = sum(1 for c in casos_pendientes if c.tipo == TipoCasoPostventa.GARANTIA.value)
    st_pendientes = sum(1 for c in casos_pendientes if c.tipo == TipoCasoPostventa.SERVICIO.value)

    taller_resumen = {
        "recibidos_dia": recibidos_taller,
        "resueltos_dia": resueltos_taller,
        "pendientes_total": len(casos_pendientes),
        "gt_pendientes": gt_pendientes,
        "st_pendientes": st_pendientes,
    }

    return {
        "fecha": fecha_op.isoformat(),
        "sucursal_id": sucursal_id,
        "sucursal": sucursal_nombre,
        "lider_encargado": lider_encargado,
        "tasas_dia": tasas_dia,
        "inventario": inventario_resumen,
        "taller": taller_resumen,
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
        "desglose_asesores": desglose_asesores,
    }


def _serializar_cierre_caja(cierre: CierreCaja) -> dict[str, Any]:
    try:
        desglose = json.loads(cierre.desglose_instrumentos_json or "[]")
    except Exception:
        desglose = []
    try:
        desglose_as = json.loads(getattr(cierre, "desglose_asesores_json", "[]") or "[]")
    except Exception:
        desglose_as = []
    try:
        resumen_op = json.loads(getattr(cierre, "resumen_operativo_json", "{}") or "{}")
    except Exception:
        resumen_op = {}
    return {
        "id": cierre.id,
        "fecha": cierre.fecha.isoformat(),
        "sucursal_id": cierre.sucursal_id,
        "sucursal": cierre.sucursal.nombre if cierre.sucursal else "Todas las sucursales",
        "usuario": cierre.usuario.nombre if cierre.usuario else "",
        "lider_encargado": resumen_op.get("lider_encargado", ""),
        "tasas_dia": resumen_op.get("tasas_dia"),
        "inventario": resumen_op.get("inventario"),
        "taller": resumen_op.get("taller"),
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
        "desglose_asesores": desglose_as,
        "creado_en": cierre.creado_en.isoformat() if cierre.creado_en else None,
    }


@enrutador.get("/cierre-caja/preview")
def preview_cierre_caja(
    fecha: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    usuario_actual: Usuario = Depends(require_permiso(Permiso.CIERRE_CAJA)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    fecha_op = fecha or obtener_fecha_hoy()
    sucursal_efectiva = validar_sucursal_permitida(
        usuario_actual,
        sucursal_id,
        contexto="consultar el cierre de caja",
    )
    return _calcular_preview_cierre_caja(bd, fecha_op=fecha_op, sucursal_id=sucursal_efectiva)


@enrutador.get("/cierre-caja")
def listar_cierres_caja(
    sucursal_id: int | None = Query(default=None),
    usuario_actual: Usuario = Depends(require_permiso(Permiso.CIERRE_CAJA)),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, Any]]:
    sucursal_efectiva = validar_sucursal_permitida(
        usuario_actual,
        sucursal_id,
        contexto="consultar el historial de cierres de caja",
    )
    consulta = (
        bd.query(CierreCaja)
        .options(joinedload(CierreCaja.sucursal), joinedload(CierreCaja.usuario))
        .order_by(CierreCaja.fecha.desc(), CierreCaja.id.desc())
    )
    if sucursal_efectiva is not None:
        consulta = consulta.filter(CierreCaja.sucursal_id == sucursal_efectiva)
    return [_serializar_cierre_caja(c) for c in consulta.all()]


@enrutador.post("/cierre-caja", status_code=status.HTTP_201_CREATED)
def guardar_cierre_caja(
    datos: CierreCajaCrearEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.CIERRE_CAJA)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    fecha_op = datos.fecha or obtener_fecha_hoy()
    sucursal_efectiva = validar_sucursal_permitida(
        usuario_actual,
        datos.sucursal_id,
        contexto="guardar el cierre de caja",
    )
    preview = _calcular_preview_cierre_caja(bd, fecha_op=fecha_op, sucursal_id=sucursal_efectiva)

    esperado = Decimal(str(preview["efectivo_esperado_usd"]))
    declarado = datos.efectivo_declarado_usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    diferencia = (declarado - esperado).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    cierre = CierreCaja(
        fecha=fecha_op,
        sucursal_id=sucursal_efectiva,
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
        desglose_asesores_json=json.dumps(preview["desglose_asesores"], ensure_ascii=False),
        resumen_operativo_json=json.dumps(
            {
                "lider_encargado": preview.get("lider_encargado", ""),
                "tasas_dia": preview.get("tasas_dia"),
                "inventario": preview.get("inventario"),
                "taller": preview.get("taller"),
            },
            ensure_ascii=False,
        ),
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
    usuario_actual: Usuario = Depends(require_permiso(Permiso.CIERRE_CAJA)),
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

    validar_sucursal_permitida(
        usuario_actual,
        cierre.sucursal_id,
        contexto="descargar el PDF de cierre de caja",
    )

    pdf_bytes = generar_pdf_cierre_caja(cierre)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="cierre-caja-{cierre.fecha.isoformat()}-{cierre.id}.pdf"'},
    )


@enrutador.get("/cierre-caja/tablero-saldos")
def obtener_tablero_saldos_cierre(
    fecha: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    usuario_actual: Usuario = Depends(require_permiso(Permiso.CIERRE_CAJA)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    """
    Separación estricta Tienda vs Administración General con tablero visual de saldos:
    - Roles de tienda (LIDER/ASESORA/ENCARGADO): solo ven su sucursal (`tienda`), nunca `administracion_general`.
    - DIRECCION / ADMINISTRACION: ven ambos ámbitos separados y la liquidez consolidada.
    """
    fecha_op = fecha or obtener_fecha_hoy()
    suc_efectiva = validar_sucursal_permitida(
        usuario_actual,
        sucursal_id,
        contexto="consultar el tablero de saldos de cierre diario",
    )
    es_admin_global = usuario_actual.rol in (
        RolUsuario.DIRECCION.value,
        RolUsuario.ADMINISTRACION.value,
    )

    preview_tienda = _calcular_preview_cierre_caja(bd, fecha_op, suc_efectiva)

    # Clasificar instrumentos del día para la vista Tienda
    canales_tienda_kw = ("efectivo", "caja chica", "punto de venta", "pago móvil", "pago movil")
    instrumentos_activos = (
        bd.query(InstrumentoFinanciero)
        .filter(InstrumentoFinanciero.activo.is_(True))
        .order_by(InstrumentoFinanciero.nombre.asc())
        .all()
    )

    # Tasa de conversión a la fecha
    tasa = (
        bd.query(TasaDiaria)
        .filter(TasaDiaria.fecha <= fecha_op)
        .order_by(TasaDiaria.fecha.desc())
        .first()
    )
    tasa_conv = (
        tasa.tasa_usdt
        if tasa and tasa.tasa_usdt and tasa.tasa_usdt > 0
        else (tasa.tasa_bcv if tasa and tasa.tasa_bcv else Decimal("1"))
    )

    pagos_hasta_fecha = (
        bd.query(Pago)
        .filter(Pago.anulado.is_(False), Pago.fecha <= fecha_op)
        .all()
    )
    saldos_por_inst: dict[int, Decimal] = {i.id: Decimal("0.00") for i in instrumentos_activos}
    for p in pagos_hasta_fecha:
        if p.instrumento_id not in saldos_por_inst:
            continue
        signo = Decimal("1") if p.tipo_movimiento == TipoMovimientoPago.INGRESO.value else Decimal("-1")
        saldos_por_inst[p.instrumento_id] += signo * p.monto_moneda_origen

    saldos_tienda_inst: list[dict[str, Any]] = []
    saldos_admin_inst: list[dict[str, Any]] = []
    total_tienda_usd = Decimal("0.00")
    total_admin_usd = Decimal("0.00")

    for inst in instrumentos_activos:
        nom_l = inst.nombre.lower()
        if "cashea" in nom_l or "parte de pago" in nom_l or "cuenta por cobrar" in nom_l:
            continue
        saldo_orig = saldos_por_inst.get(inst.id, Decimal("0.00"))
        equiv_usd = (
            (saldo_orig / tasa_conv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if inst.moneda == MonedaInstrumento.BS.value and tasa_conv > 0
            else saldo_orig.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
        fila = {
            "id": inst.id,
            "nombre": inst.nombre,
            "moneda": inst.moneda,
            "saldo_moneda_origen": redondear_usd(saldo_orig),
            "saldo_usd": redondear_usd(equiv_usd),
        }
        if any(k in nom_l for k in canales_tienda_kw):
            saldos_tienda_inst.append(fila)
            total_tienda_usd += equiv_usd
        else:
            saldos_admin_inst.append(fila)
            total_admin_usd += equiv_usd

    salida: dict[str, Any] = {
        "fecha": fecha_op.isoformat(),
        "sucursal_id": suc_efectiva,
        "ambito_usuario": "ADMINISTRACION_GENERAL" if es_admin_global else "TIENDA",
        "tienda": {
            "sucursal": preview_tienda["sucursal"],
            "efectivo_esperado_dia_usd": preview_tienda["efectivo_esperado_usd"],
            "ventas_del_dia_usd": preview_tienda["total_ventas_usd"],
            "cantidad_ventas": preview_tienda["cantidad_ventas"],
            "vueltos_entregados_usd": preview_tienda["total_egresos_usd"],
            "canales_locales": saldos_tienda_inst,
            "total_saldos_locales_usd": redondear_usd(total_tienda_usd),
        },
        "administracion_general": None,
    }

    if es_admin_global:
        cxcs = (
            bd.query(CuentaPorCobrar)
            .filter(
                CuentaPorCobrar.estado == EstadoCuentaPorCobrar.PENDIENTE.value,
                CuentaPorCobrar.saldo_pendiente_usd > Decimal("0"),
            )
            .all()
        )
        cashea_cobrar = sum(
            (c.saldo_pendiente_usd for c in cxcs if c.tipo == TipoCuentaPorCobrar.CASHEA.value),
            Decimal("0.00"),
        )
        cxc_clientes = sum(
            (c.saldo_pendiente_usd for c in cxcs if c.tipo != TipoCuentaPorCobrar.CASHEA.value),
            Decimal("0.00"),
        )
        cxp_proveedores = sum(
            (
                c.saldo_pendiente_usd
                for c in bd.query(Compra)
                .filter(Compra.saldo_pendiente_usd > Decimal("0"), Compra.fecha <= fecha_op)
                .all()
            ),
            Decimal("0.00"),
        )
        salida["administracion_general"] = {
            "cuentas_corporativas": saldos_admin_inst,
            "total_liquidez_corporativa_usd": redondear_usd(total_admin_usd),
            "total_liquidez_consolidada_usd": redondear_usd(total_tienda_usd + total_admin_usd),
            "cashea_por_cobrar_usd": redondear_usd(cashea_cobrar),
            "cxc_clientes_usd": redondear_usd(cxc_clientes),
            "cxp_proveedores_usd": redondear_usd(cxp_proveedores),
        }

    return salida
