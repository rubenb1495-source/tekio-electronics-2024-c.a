from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.core.permisos import Permiso, require_permiso
from app.esquemas_finanzas import (
    CasheaImportarConfirmarEntrada,
    CasheaOrdenActualizarEntrada,
)
from app.modelos import TasaDiaria, Usuario
from app.modelos_finanzas import (
    CasheaLoteLiquidacion,
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
from app.rutas.ventas import verificar_mes_abierto
from app.servicios.auditoria_service import registrar_auditoria
from app.servicios.contabilidad_service import registrar_asiento


enrutador = APIRouter(prefix="/api/finanzas", tags=["Conciliación Financiera Cashea"])
ZONA_CARACAS = ZoneInfo("America/Caracas")


def _r2(valor: Decimal | float | int) -> float:
    return float(Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _d2(valor: Decimal | float | int) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _normalizar_orden(texto: str | None) -> str:
    if not texto:
        return ""
    return re.sub(r"\s+", "", str(texto).strip()).upper()


def _normalizar_encabezado(texto: Any) -> str:
    s = str(texto or "").strip().lower()
    s = "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _parsear_monto(valor: Any) -> Decimal | None:
    if valor is None:
        return None
    if isinstance(valor, (int, float, Decimal)):
        return _d2(valor)
    s = str(valor).strip()
    if not s:
        return None
    s = re.sub(r"[^0-9,.\-]", "", s)
    if not s or s in ("-", ".", ","):
        return None
    # Formato venezolano/europeo 1.234,56 -> 1234.56
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s and s.count(",") == 1 and len(s.split(",")[1]) <= 2:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return _d2(Decimal(s))
    except InvalidOperation:
        return None


def _estado_efectivo_venta(v: Venta) -> str:
    est = (getattr(v, "cashea_estado_conciliacion", None) or "PENDIENTE").upper()
    if est == "CONCILIADO":
        return "CONCILIADO"
    # Compatibilidad con liquidaciones manuales anteriores (CxC ya PAGADA)
    cxcs_cashea = [c for c in (v.cuentas_por_cobrar or []) if c.tipo == TipoCuentaPorCobrar.CASHEA.value]
    if cxcs_cashea and all(c.estado == EstadoCuentaPorCobrar.PAGADA.value for c in cxcs_cashea):
        return "CONCILIADO"
    return "PENDIENTE"


def _serializar_venta_cashea(v: Venta) -> dict[str, Any]:
    total_reg = Decimal(v.total_regular_usd or 0)
    financiado = Decimal(v.monto_financiado_cashea_usd or 0)
    inicial = max(Decimal("0.00"), total_reg - financiado)
    precio_reg_bs = (
        Decimal(v.precio_regular_bs or 0)
        if getattr(v, "precio_regular_bs", Decimal("0")) > 0
        else (
            (total_reg * Decimal(v.tasa_bcv_snapshot or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if (v.tasa_bcv_snapshot or 0) > 0
            else Decimal("0.00")
        )
    )
    com_tot = (
        Decimal(v.comision_cashea_venta_total_usd or 0)
        if getattr(v, "comision_cashea_venta_total_usd", Decimal("0")) > 0
        else _d2(total_reg * Decimal("0.04"))
    )
    com_fin = (
        Decimal(v.comision_cashea_financiado_usd or 0)
        if getattr(v, "comision_cashea_financiado_usd", Decimal("0")) > 0
        else _d2(financiado * Decimal("0.04"))
    )
    iva_c = (
        Decimal(v.iva_cashea_usd or 0)
        if getattr(v, "iva_cashea_usd", Decimal("0")) > 0
        else _d2(com_tot * Decimal("0.16"))
    )
    islr_c = (
        Decimal(v.islr_cashea_usd or 0)
        if getattr(v, "islr_cashea_usd", Decimal("0")) > 0
        else _d2(com_tot * Decimal("0.02"))
    )
    tot_ded = _d2(com_tot + com_fin + iva_c + islr_c)
    neto_esp = max(Decimal("0.00"), _d2(financiado - tot_ded))

    estado_conc = _estado_efectivo_venta(v)
    cxcs_cashea = [c for c in (v.cuentas_por_cobrar or []) if c.tipo == TipoCuentaPorCobrar.CASHEA.value]
    cxc_principal = cxcs_cashea[0] if cxcs_cashea else None
    saldo_pendiente = (
        Decimal("0.00")
        if estado_conc == "CONCILIADO"
        else sum((Decimal(c.saldo_pendiente_usd or 0) for c in cxcs_cashea), Decimal("0.00")) or financiado
    )

    pagado_real = (
        _r2(v.cashea_monto_pagado_real_usd)
        if getattr(v, "cashea_monto_pagado_real_usd", None) is not None
        else None
    )
    descuento_real = (
        _r2(v.cashea_descuento_real_usd)
        if getattr(v, "cashea_descuento_real_usd", None) is not None
        else None
    )
    diferencia = (
        _r2(v.cashea_diferencia_usd)
        if getattr(v, "cashea_diferencia_usd", None) is not None
        else None
    )

    return {
        "id": cxc_principal.id if cxc_principal else v.id,
        "venta_id": v.id,
        "numero_venta": v.numero_venta,
        "cashea_numero_orden": getattr(v, "cashea_numero_orden", None),
        "sucursal_id": v.sucursal_id,
        "sucursal": v.sucursal.nombre if v.sucursal else "",
        "fecha_venta": v.fecha.isoformat(),
        "cliente": v.cliente.nombre if v.cliente else "Cliente general",
        "total_regular_usd": _r2(total_reg),
        "precio_regular_bs": _r2(precio_reg_bs),
        "inicial_usd": _r2(inicial),
        "monto_original_usd": _r2(financiado),
        "saldo_pendiente_usd": _r2(saldo_pendiente),
        "comision_cashea_venta_total_usd": _r2(com_tot),
        "comision_cashea_financiado_usd": _r2(com_fin),
        "iva_cashea_usd": _r2(iva_c),
        "islr_cashea_usd": _r2(islr_c),
        "total_deducciones_cashea_usd": _r2(tot_ded),
        "neto_esperado_cashea_usd": _r2(neto_esp),
        "cashea_monto_pagado_real_usd": pagado_real,
        "cashea_descuento_real_usd": descuento_real,
        "cashea_diferencia_usd": diferencia,
        "cashea_estado_conciliacion": estado_conc,
        "estado": estado_conc,
        "cashea_fecha_conciliacion": (
            v.cashea_fecha_conciliacion.isoformat()
            if getattr(v, "cashea_fecha_conciliacion", None) is not None
            else None
        ),
        "cashea_lote_liquidacion_id": getattr(v, "cashea_lote_liquidacion_id", None),
    }


def _consultar_ventas_cashea(
    bd: Session,
    *,
    estado_conciliacion: str = "TODOS",
    fecha_inicio: date | None = None,
    fecha_fin: date | None = None,
    sucursal_id: int | None = None,
    buscar: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    consulta = (
        bd.query(Venta)
        .options(
            joinedload(Venta.sucursal),
            joinedload(Venta.cliente),
            joinedload(Venta.cuentas_por_cobrar),
        )
        .filter(
            Venta.monto_financiado_cashea_usd > Decimal("0"),
            Venta.estado.notin_([EstadoVenta.ANULADA.value, EstadoVenta.DEVUELTA.value]),
        )
    )
    if fecha_inicio is not None:
        consulta = consulta.filter(Venta.fecha >= fecha_inicio)
    if fecha_fin is not None:
        consulta = consulta.filter(Venta.fecha <= fecha_fin)
    if sucursal_id is not None:
        consulta = consulta.filter(Venta.sucursal_id == sucursal_id)

    ventas_unicas = consulta.order_by(Venta.fecha.desc(), Venta.id.desc()).all()
    todas = [_serializar_venta_cashea(v) for v in ventas_unicas]

    if buscar and buscar.strip():
        q = buscar.strip().lower()
        todas = [
            it
            for it in todas
            if q in (it["numero_venta"] or "").lower()
            or q in (it["cliente"] or "").lower()
            or q in (it["cashea_numero_orden"] or "").lower()
            or q in (it["sucursal"] or "").lower()
        ]

    conteo = {
        "todos": len(todas),
        "pendientes": sum(1 for it in todas if it["cashea_estado_conciliacion"] == "PENDIENTE"),
        "conciliados": sum(1 for it in todas if it["cashea_estado_conciliacion"] == "CONCILIADO"),
    }

    filtro = (estado_conciliacion or "TODOS").strip().upper()
    if filtro in ("PENDIENTE", "CONCILIADO"):
        filtradas = [it for it in todas if it["cashea_estado_conciliacion"] == filtro]
    else:
        filtradas = todas

    return filtradas, conteo


@enrutador.get("/cashea")
def listar_conciliacion_cashea(
    estado_conciliacion: str = Query(default="TODOS"),
    estado: str | None = Query(default=None),
    fecha_inicio: date | None = Query(default=None),
    fecha_fin: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    buscar: str | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    """Listado consolidado de Conciliación Financiera Cashea (estrictamente 1 fila por venta.id)."""
    filtro_estado = (estado or estado_conciliacion or "TODOS").strip().upper()
    items, conteo = _consultar_ventas_cashea(
        bd,
        estado_conciliacion=filtro_estado,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        sucursal_id=sucursal_id,
        buscar=buscar,
    )

    financiado = sum((Decimal(str(i["monto_original_usd"])) for i in items), Decimal("0.00"))
    com_tot = sum((Decimal(str(i["comision_cashea_venta_total_usd"])) for i in items), Decimal("0.00"))
    com_fin = sum((Decimal(str(i["comision_cashea_financiado_usd"])) for i in items), Decimal("0.00"))
    iva = sum((Decimal(str(i["iva_cashea_usd"])) for i in items), Decimal("0.00"))
    islr = sum((Decimal(str(i["islr_cashea_usd"])) for i in items), Decimal("0.00"))
    deducciones = sum((Decimal(str(i["total_deducciones_cashea_usd"])) for i in items), Decimal("0.00"))
    neto = sum((Decimal(str(i["neto_esperado_cashea_usd"])) for i in items), Decimal("0.00"))
    pagado_real = sum(
        (Decimal(str(i["cashea_monto_pagado_real_usd"])) for i in items if i["cashea_monto_pagado_real_usd"] is not None),
        Decimal("0.00"),
    )
    descuento_real = sum(
        (Decimal(str(i["cashea_descuento_real_usd"])) for i in items if i["cashea_descuento_real_usd"] is not None),
        Decimal("0.00"),
    )
    diferencia_neta = sum(
        (Decimal(str(i["cashea_diferencia_usd"])) for i in items if i["cashea_diferencia_usd"] is not None),
        Decimal("0.00"),
    )

    return {
        "total_notas": len(items),
        "conteo": conteo,
        "kpis": {
            "financiado_bruto_usd": _r2(financiado),
            "comision_venta_total_usd": _r2(com_tot),
            "comision_financiado_usd": _r2(com_fin),
            "iva_cashea_usd": _r2(iva),
            "islr_cashea_usd": _r2(islr),
            "total_deducciones_usd": _r2(deducciones),
            "neto_real_esperado_usd": _r2(neto),
            "pagado_real_usd": _r2(pagado_real),
            "descuento_real_usd": _r2(descuento_real),
            "diferencia_neta_usd": _r2(diferencia_neta),
        },
        "items": items,
    }


@enrutador.get("/cashea/exportar-xlsx")
def exportar_cashea_xlsx(
    estado_conciliacion: str = Query(default="TODOS"),
    fecha_inicio: date | None = Query(default=None),
    fecha_fin: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    buscar: str | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> StreamingResponse:
    """Exporta la Conciliación Financiera Cashea en formato .xlsx respetando filtros activos (sin duplicados)."""
    items, _ = _consultar_ventas_cashea(
        bd,
        estado_conciliacion=estado_conciliacion,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        sucursal_id=sucursal_id,
        buscar=buscar,
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Conciliación Cashea"

    fill_titulo = PatternFill(start_color="E85A28", end_color="E85A28", fill_type="solid")
    fill_header = PatternFill(start_color="191818", end_color="191818", fill_type="solid")
    fill_total = PatternFill(start_color="FDF0EB", end_color="FDF0EB", fill_type="solid")
    font_titulo = Font(bold=True, color="FFFFFF", size=12)
    font_header = Font(bold=True, color="FFFFFF", size=10)
    font_total = Font(bold=True, color="191818", size=10)

    ws.merge_cells("A1:T1")
    celda_t = ws["A1"]
    celda_t.value = f"TEKIO ELECTRONICS — CONCILIACIÓN FINANCIERA CASHEA ({estado_conciliacion.upper()})"
    celda_t.fill = fill_titulo
    celda_t.font = font_titulo
    celda_t.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 26

    columnas = [
        "Fecha",
        "Nro. Nota",
        "Nro. Orden Cashea",
        "Sucursal",
        "Cliente",
        "Precio Regular (USDT)",
        "Precio Regular (Bs)",
        "Inicial (USD)",
        "Monto Financiado (USD)",
        "Fee 4% Venta",
        "Fee 4% Financiado",
        "IVA 16%",
        "ISLR 2%",
        "Total Deducciones Esperadas",
        "Neto Esperado",
        "Pagado Real Cashea",
        "Descuento Real Cashea",
        "Diferencia",
        "Estado",
        "Fecha Conciliación",
    ]
    ws.append(columnas)
    for col_idx in range(1, len(columnas) + 1):
        c = ws.cell(row=2, column=col_idx)
        c.fill = fill_header
        c.font = font_header
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 22

    for it in items:
        ws.append(
            [
                it["fecha_venta"],
                it["numero_venta"],
                it["cashea_numero_orden"] or "—",
                it["sucursal"],
                it["cliente"],
                it["total_regular_usd"],
                it["precio_regular_bs"],
                it["inicial_usd"],
                it["monto_original_usd"],
                it["comision_cashea_venta_total_usd"],
                it["comision_cashea_financiado_usd"],
                it["iva_cashea_usd"],
                it["islr_cashea_usd"],
                it["total_deducciones_cashea_usd"],
                it["neto_esperado_cashea_usd"],
                it["cashea_monto_pagado_real_usd"] if it["cashea_monto_pagado_real_usd"] is not None else "",
                it["cashea_descuento_real_usd"] if it["cashea_descuento_real_usd"] is not None else "",
                it["cashea_diferencia_usd"] if it["cashea_diferencia_usd"] is not None else "",
                it["cashea_estado_conciliacion"],
                (it["cashea_fecha_conciliacion"] or "")[:19].replace("T", " "),
            ]
        )

    # Formato numérico en filas de datos
    ultima_fila_datos = 2 + len(items)
    for r_idx in range(3, ultima_fila_datos + 1):
        for c_idx in range(6, 19):
            cell = ws.cell(row=r_idx, column=c_idx)
            if isinstance(cell.value, (int, float)):
                cell.number_format = "#,##0.00"

    # Fila de totales al pie
    fila_tot = ultima_fila_datos + 1
    ws.cell(row=fila_tot, column=1, value="TOTALES")
    ws.cell(row=fila_tot, column=2, value=f"{len(items)} notas")
    claves_suma = [
        (6, "total_regular_usd"),
        (7, "precio_regular_bs"),
        (8, "inicial_usd"),
        (9, "monto_original_usd"),
        (10, "comision_cashea_venta_total_usd"),
        (11, "comision_cashea_financiado_usd"),
        (12, "iva_cashea_usd"),
        (13, "islr_cashea_usd"),
        (14, "total_deducciones_cashea_usd"),
        (15, "neto_esperado_cashea_usd"),
        (16, "cashea_monto_pagado_real_usd"),
        (17, "cashea_descuento_real_usd"),
        (18, "cashea_diferencia_usd"),
    ]
    for c_idx, clave in claves_suma:
        total_col = sum(float(it[clave]) for it in items if it[clave] is not None)
        cell = ws.cell(row=fila_tot, column=c_idx, value=round(total_col, 2))
        cell.number_format = "#,##0.00"

    for c_idx in range(1, len(columnas) + 1):
        c = ws.cell(row=fila_tot, column=c_idx)
        c.fill = fill_total
        c.font = font_total

    for idx_col, col in enumerate(ws.iter_cols(min_row=2, max_row=fila_tot, min_col=1, max_col=len(columnas)), start=1):
        max_len = max((len(str(cell.value or "")) for cell in col), default=10)
        ws.column_dimensions[get_column_letter(idx_col)].width = min(max(max_len + 3, 12), 34)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    ahora_str = datetime.now(ZONA_CARACAS).strftime("%Y-%m-%d_%H%M")
    nombre = f"conciliacion_cashea_tekio_{ahora_str}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@enrutador.patch("/cashea/{venta_id}/orden")
def asignar_orden_cashea_pendiente(
    venta_id: int,
    datos: CasheaOrdenActualizarEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    """Permite asignar o corregir el número de orden Cashea en notas pendientes."""
    venta = (
        bd.query(Venta)
        .options(joinedload(Venta.sucursal), joinedload(Venta.cliente), joinedload(Venta.cuentas_por_cobrar))
        .filter(Venta.id == venta_id)
        .first()
    )
    if venta is None or (venta.monto_financiado_cashea_usd or Decimal("0")) <= Decimal("0"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nota Cashea no encontrada.")

    orden_norm = _normalizar_orden(datos.cashea_numero_orden)
    if not orden_norm:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El número de orden de Cashea es obligatorio.",
        )

    dup = (
        bd.query(Venta)
        .filter(
            func.upper(Venta.cashea_numero_orden) == orden_norm,
            Venta.id != venta.id,
            Venta.estado != EstadoVenta.ANULADA.value,
        )
        .first()
    )
    if dup is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ese número de orden de Cashea ya está registrado en la nota {dup.numero_venta}.",
        )

    anterior = venta.cashea_numero_orden
    venta.cashea_numero_orden = orden_norm
    registrar_auditoria(
        bd,
        usuario=usuario_actual,
        modulo="FINANZAS_CASHEA",
        accion="ASIGNAR_ORDEN_CASHEA",
        entidad_id=venta.numero_venta,
        detalle_anterior={"cashea_numero_orden": anterior},
        detalle_nuevo={"cashea_numero_orden": orden_norm},
    )
    bd.commit()
    bd.refresh(venta)
    return _serializar_venta_cashea(venta)


def _leer_filas_archivo_cashea(contenido: bytes, nombre_archivo: str) -> tuple[list[str], list[dict[str, Any]]]:
    ext = (nombre_archivo or "").lower()
    if ext.endswith(".csv"):
        texto = contenido.decode("utf-8-sig", errors="replace")
        muestra = texto[:2048]
        delimitador = ";" if muestra.count(";") > muestra.count(",") else ","
        lector = list(csv.reader(io.StringIO(texto), delimiter=delimitador))
        if not lector:
            return [], []
        encabezados = [str(h or "").strip() for h in lector[0]]
        filas = []
        for row in lector[1:]:
            if not any(str(c or "").strip() for c in row):
                continue
            d = {encabezados[i]: (row[i] if i < len(row) else "") for i in range(len(encabezados))}
            filas.append(d)
        return encabezados, filas

    wb = load_workbook(io.BytesIO(contenido), data_only=True)
    ws = wb.active
    todas_filas = list(ws.iter_rows(values_only=True))
    if not todas_filas:
        return [], []
    # Buscar la primera fila que parezca encabezado (con >= 2 celdas con texto)
    idx_header = 0
    for idx, row in enumerate(todas_filas[:10]):
        textos = [c for c in row if isinstance(c, str) and c.strip()]
        if len(textos) >= 2:
            idx_header = idx
            break
    encabezados = [str(h or f"col_{i}").strip() for i, h in enumerate(todas_filas[idx_header])]
    filas = []
    for row in todas_filas[idx_header + 1 :]:
        if not any(c is not None and str(c).strip() for c in row):
            continue
        d = {encabezados[i]: (row[i] if i < len(row) else None) for i in range(len(encabezados))}
        filas.append(d)
    return encabezados, filas


def _detectar_columnas_cashea(
    encabezados: list[str],
    *,
    col_orden_override: str | None = None,
    col_bruto_override: str | None = None,
    col_neto_override: str | None = None,
    col_descuento_override: str | None = None,
) -> dict[str, Any]:
    norm_map = {h: _normalizar_encabezado(h) for h in encabezados}

    def buscar_col(override: str | None, patrones: tuple[str, ...]) -> str | None:
        if override and override in encabezados:
            return override
        for h, n in norm_map.items():
            if any(p in n for p in patrones):
                return h
        return None

    col_orden = buscar_col(
        col_orden_override,
        ("order id", "nro orden", "numero orden", "numero de orden", "orden", "order", "referencia"),
    )
    col_neto = buscar_col(
        col_neto_override,
        ("monto pagado", "pagado", "neto liquidado", "monto liquidado", "neto", "payout", "transferido", "liquidado"),
    )
    col_bruto = buscar_col(
        col_bruto_override,
        ("monto financiado", "financiado", "bruto", "gross", "monto venta", "monto total", "amount"),
    )
    cols_descuento: list[str] = []
    if col_descuento_override and col_descuento_override in encabezados:
        cols_descuento = [col_descuento_override]
    else:
        for h, n in norm_map.items():
            if h in (col_orden, col_neto, col_bruto):
                continue
            if any(p in n for p in ("descuento", "comision", "fee", "iva", "islr", "factoring", "retencion", "deduccion")):
                cols_descuento.append(h)

    col_fecha = buscar_col(None, ("fecha pago", "fecha liquidacion", "fecha", "date"))
    col_ref_banco = buscar_col(None, ("referencia bancaria", "ref banco", "banco", "comprobante"))

    return {
        "col_orden": col_orden,
        "col_bruto": col_bruto,
        "col_neto": col_neto,
        "cols_descuento": cols_descuento,
        "col_fecha": col_fecha,
        "col_ref_banco": col_ref_banco,
    }


@enrutador.post("/cashea/importar-reporte/preview")
async def preview_reporte_cashea(
    archivo: UploadFile = File(...),
    col_orden: str | None = Form(default=None),
    col_bruto: str | None = Form(default=None),
    col_neto: str | None = Form(default=None),
    col_descuento: str | None = Form(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    """Paso 1: Lee reporte .xlsx/.csv de Cashea Merchant Web y cruza contra ventas Tekio sin guardar nada."""
    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo está vacío.")

    nombre_archivo = archivo.filename or "reporte_cashea.xlsx"
    try:
        encabezados, filas_raw = _leer_filas_archivo_cashea(contenido, nombre_archivo)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se pudo leer el archivo '{nombre_archivo}': {exc}",
        ) from exc

    if not encabezados or not filas_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo no contiene encabezados ni filas de datos.",
        )

    mapeo = _detectar_columnas_cashea(
        encabezados,
        col_orden_override=col_orden,
        col_bruto_override=col_bruto,
        col_neto_override=col_neto,
        col_descuento_override=col_descuento,
    )
    if not mapeo["col_orden"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se detectó la columna de Número de Orden en el archivo. Selecciónala manualmente en el mapeo.",
        )

    # Mapa de ventas Cashea activas indexado por cashea_numero_orden normalizado
    ventas_cashea = (
        bd.query(Venta)
        .options(joinedload(Venta.sucursal), joinedload(Venta.cliente), joinedload(Venta.cuentas_por_cobrar))
        .filter(
            Venta.monto_financiado_cashea_usd > Decimal("0"),
            Venta.estado.notin_([EstadoVenta.ANULADA.value, EstadoVenta.DEVUELTA.value]),
            Venta.cashea_numero_orden.isnot(None),
        )
        .all()
    )
    mapa_ventas: dict[str, Venta] = {}
    for v in ventas_cashea:
        k = _normalizar_orden(v.cashea_numero_orden)
        if k:
            mapa_ventas[k] = v

    filas_cruce: list[dict[str, Any]] = []
    tot_cobrar_real = Decimal("0.00")
    tot_desc_real = Decimal("0.00")
    tot_esperado = Decimal("0.00")
    tot_diferencia = Decimal("0.00")
    conteo_listas = 0
    conteo_ya = 0
    conteo_no = 0

    for idx, row in enumerate(filas_raw, start=1):
        orden_val = _normalizar_orden(row.get(mapeo["col_orden"]))
        if not orden_val:
            continue

        bruto_archivo = _parsear_monto(row.get(mapeo["col_bruto"])) if mapeo["col_bruto"] else None
        neto_archivo = _parsear_monto(row.get(mapeo["col_neto"])) if mapeo["col_neto"] else None
        desc_cols = Decimal("0.00")
        tiene_desc_col = False
        for c_desc in mapeo["cols_descuento"]:
            val_d = _parsear_monto(row.get(c_desc))
            if val_d is not None:
                desc_cols += abs(val_d)
                tiene_desc_col = True

        v = mapa_ventas.get(orden_val)
        if v is None:
            conteo_no += 1
            desc_final = desc_cols if tiene_desc_col else (
                max(Decimal("0.00"), _d2(bruto_archivo - neto_archivo))
                if bruto_archivo is not None and neto_archivo is not None
                else Decimal("0.00")
            )
            filas_cruce.append(
                {
                    "fila_archivo": idx,
                    "estado_cruce": "NO_ENCONTRADA",
                    "cashea_numero_orden": orden_val,
                    "venta_id": None,
                    "numero_venta": None,
                    "cliente": None,
                    "sucursal": None,
                    "financiado_tekio_usd": None,
                    "neto_esperado_tekio_usd": None,
                    "descuento_esperado_tekio_usd": None,
                    "bruto_reporte_usd": _r2(bruto_archivo) if bruto_archivo is not None else None,
                    "monto_pagado_real_usd": _r2(neto_archivo) if neto_archivo is not None else 0.0,
                    "descuento_real_usd": _r2(desc_final),
                    "diferencia_usd": None,
                    "fecha_pago_archivo": str(row.get(mapeo["col_fecha"]) or "").strip() if mapeo["col_fecha"] else "",
                    "referencia_archivo": str(row.get(mapeo["col_ref_banco"]) or "").strip() if mapeo["col_ref_banco"] else "",
                }
            )
            continue

        ser = _serializar_venta_cashea(v)
        financiado_tekio = _d2(ser["monto_original_usd"])
        neto_esp_tekio = _d2(ser["neto_esperado_cashea_usd"])
        desc_esp_tekio = _d2(ser["total_deducciones_cashea_usd"])

        bruto_base = bruto_archivo if bruto_archivo is not None else financiado_tekio
        if neto_archivo is not None:
            pagado_real = neto_archivo
            desc_real = desc_cols if tiene_desc_col else max(Decimal("0.00"), _d2(bruto_base - pagado_real))
        elif tiene_desc_col:
            desc_real = desc_cols
            pagado_real = max(Decimal("0.00"), _d2(bruto_base - desc_real))
        else:
            pagado_real = neto_esp_tekio
            desc_real = desc_esp_tekio

        diferencia = _d2(pagado_real - neto_esp_tekio)
        estado_actual = ser["cashea_estado_conciliacion"]
        if estado_actual == "CONCILIADO":
            estado_cruce = "YA_CONCILIADA"
            conteo_ya += 1
        else:
            estado_cruce = "LISTA_PARA_CONCILIAR"
            conteo_listas += 1
            tot_cobrar_real += pagado_real
            tot_desc_real += desc_real
            tot_esperado += neto_esp_tekio
            tot_diferencia += diferencia

        filas_cruce.append(
            {
                "fila_archivo": idx,
                "estado_cruce": estado_cruce,
                "cashea_numero_orden": orden_val,
                "venta_id": v.id,
                "numero_venta": v.numero_venta,
                "cliente": ser["cliente"],
                "sucursal": ser["sucursal"],
                "financiado_tekio_usd": _r2(financiado_tekio),
                "neto_esperado_tekio_usd": _r2(neto_esp_tekio),
                "descuento_esperado_tekio_usd": _r2(desc_esp_tekio),
                "bruto_reporte_usd": _r2(bruto_base),
                "monto_pagado_real_usd": _r2(pagado_real),
                "descuento_real_usd": _r2(desc_real),
                "diferencia_usd": _r2(diferencia),
                "fecha_pago_archivo": str(row.get(mapeo["col_fecha"]) or "").strip() if mapeo["col_fecha"] else "",
                "referencia_archivo": str(row.get(mapeo["col_ref_banco"]) or "").strip() if mapeo["col_ref_banco"] else "",
            }
        )

    return {
        "nombre_archivo": nombre_archivo,
        "encabezados_detectados": encabezados,
        "mapeo_detectado": mapeo,
        "resumen": {
            "total_filas": len(filas_cruce),
            "listas_para_conciliar": conteo_listas,
            "ya_conciliadas": conteo_ya,
            "no_encontradas": conteo_no,
            "total_a_cobrar_real_usd": _r2(tot_cobrar_real),
            "total_descuentos_reales_usd": _r2(tot_desc_real),
            "total_neto_esperado_usd": _r2(tot_esperado),
            "diferencia_neta_usd": _r2(tot_diferencia),
        },
        "filas": filas_cruce,
    }


@enrutador.post("/cashea/importar-reporte/confirmar")
def confirmar_reporte_cashea(
    datos: CasheaImportarConfirmarEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.VER_FINANZAS_GLOBALES)),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    """Paso 2: Confirmación y liquidación atómica del lote Cashea (BD + Pago real + Asiento contable cuadrado)."""
    verificar_mes_abierto(bd, datos.fecha_deposito)

    destino = (
        bd.query(InstrumentoFinanciero)
        .filter(InstrumentoFinanciero.id == datos.instrumento_destino_id)
        .first()
    )
    if destino is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instrumento/banco destino no encontrado.",
        )

    tasa_row = (
        bd.query(TasaDiaria)
        .filter(TasaDiaria.fecha <= datos.fecha_deposito)
        .order_by(TasaDiaria.fecha.desc())
        .first()
    )
    tasa_bcv = datos.tasa_bcv_dia or (tasa_row.tasa_bcv if tasa_row else Decimal("0"))
    tasa_usdt = tasa_row.tasa_usdt if tasa_row else tasa_bcv
    if destino.moneda == MonedaInstrumento.BS.value and tasa_bcv <= Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes indicar o tener registrada la tasa BCV del día para liquidar en bolívares.",
        )

    # Deduplicar venta_ids en la solicitud
    ordenes_por_venta: dict[int, Any] = {}
    for item in datos.ordenes:
        ordenes_por_venta[item.venta_id] = item

    ventas = (
        bd.query(Venta)
        .options(joinedload(Venta.cuentas_por_cobrar))
        .filter(Venta.id.in_(list(ordenes_por_venta.keys())))
        .all()
    )
    mapa_ventas = {v.id: v for v in ventas}

    if len(mapa_ventas) != len(ordenes_por_venta):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Una o más ventas seleccionadas no existen.",
        )

    ahora_caracas = datetime.now(ZONA_CARACAS)
    total_financiado = Decimal("0.00")
    total_neto_esperado = Decimal("0.00")
    total_pagado_real = Decimal("0.00")
    total_descuento_real = Decimal("0.00")
    total_diferencia = Decimal("0.00")

    try:
        for vid, item in ordenes_por_venta.items():
            v = mapa_ventas[vid]
            if _estado_efectivo_venta(v) == "CONCILIADO":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"La nota {v.numero_venta} (orden {v.cashea_numero_orden}) ya se encuentra conciliada.",
                )
            ser = _serializar_venta_cashea(v)
            financiado = _d2(ser["monto_original_usd"])
            neto_esp = _d2(ser["neto_esperado_cashea_usd"])
            pagado_real = _d2(item.monto_pagado_real_usd)
            desc_real = _d2(item.descuento_real_usd)
            diff = _d2(pagado_real - neto_esp)

            total_financiado += financiado
            total_neto_esperado += neto_esp
            total_pagado_real += pagado_real
            total_descuento_real += desc_real
            total_diferencia += diff

        # 1. Crear lote de liquidación Cashea
        lote = CasheaLoteLiquidacion(
            nombre_archivo=datos.nombre_archivo.strip() or "reporte_cashea.xlsx",
            fecha_deposito=datos.fecha_deposito,
            instrumento_destino_id=destino.id,
            referencia_bancaria=datos.referencia_bancaria.strip(),
            tasa_bcv_dia=tasa_bcv,
            cantidad_notas=len(ordenes_por_venta),
            total_financiado_usd=_d2(total_financiado),
            total_neto_esperado_usd=_d2(total_neto_esperado),
            total_pagado_real_usd=_d2(total_pagado_real),
            total_descuento_real_usd=_d2(total_descuento_real),
            total_diferencia_usd=_d2(total_diferencia),
            creado_por_id=usuario_actual.id,
        )
        bd.add(lote)
        bd.flush()

        # 2. Actualizar cada venta y cerrar sus CxC Cashea pendientes
        notas_conciliadas: list[str] = []
        for vid, item in ordenes_por_venta.items():
            v = mapa_ventas[vid]
            ser = _serializar_venta_cashea(v)
            neto_esp = _d2(ser["neto_esperado_cashea_usd"])
            pagado_real = _d2(item.monto_pagado_real_usd)
            desc_real = _d2(item.descuento_real_usd)
            diff = _d2(pagado_real - neto_esp)

            v.cashea_estado_conciliacion = "CONCILIADO"
            v.cashea_fecha_conciliacion = ahora_caracas
            v.cashea_monto_pagado_real_usd = pagado_real
            v.cashea_descuento_real_usd = desc_real
            v.cashea_diferencia_usd = diff
            v.cashea_lote_liquidacion_id = lote.id
            if not v.cashea_numero_orden:
                v.cashea_numero_orden = _normalizar_orden(item.cashea_numero_orden)

            for cxc in v.cuentas_por_cobrar or []:
                if cxc.tipo == TipoCuentaPorCobrar.CASHEA.value and cxc.estado == EstadoCuentaPorCobrar.PENDIENTE.value:
                    cxc.saldo_pendiente_usd = Decimal("0.00")
                    cxc.estado = EstadoCuentaPorCobrar.PAGADA.value
            notas_conciliadas.append(v.numero_venta)

        # 3. Registrar INGRESO real en banco/instrumento destino
        if destino.moneda == MonedaInstrumento.BS.value:
            monto_origen = _d2(total_pagado_real * tasa_bcv)
            usd_real = _d2(monto_origen / tasa_usdt) if tasa_usdt > 0 else _d2(total_pagado_real)
        else:
            monto_origen = _d2(total_pagado_real)
            usd_real = _d2(total_pagado_real)

        pago_ingreso = Pago(
            venta_id=None,
            instrumento_id=destino.id,
            fecha=datos.fecha_deposito,
            tipo_movimiento=TipoMovimientoPago.INGRESO.value,
            tipo_documento=TipoDocumentoPago.CASHEA.value,
            monto_moneda_origen=monto_origen,
            moneda=destino.moneda,
            tasa_bcv_dia=tasa_bcv,
            tasa_usdt_dia=tasa_usdt,
            usd_nominal=_d2(total_pagado_real),
            usd_real=usd_real,
            cubre_promo_usd=_d2(total_pagado_real),
            referencia=datos.referencia_bancaria.strip() or f"LOTE-CASHEA-{lote.id}",
            estado_verificacion=EstadoVerificacionPago.CONFIRMADO.value,
            nota=(
                f"Liquidación Lote Cashea #{lote.id} ({len(notas_conciliadas)} notas: "
                f"{', '.join(notas_conciliadas[:5])}) · Pagado ${_r2(total_pagado_real):.2f} "
                f"· Descuento ${_r2(total_descuento_real):.2f}"
            ),
        )
        bd.add(pago_ingreso)
        bd.flush()

        # 4. Asiento contable automático por partida doble (Debe == Haber exacto)
        lineas_asiento: list[dict[str, Any]] = []
        if total_pagado_real > Decimal("0.00"):
            lineas_asiento.append(
                {
                    "codigo_cuenta": "1.1.01",
                    "debe_usd": _d2(total_pagado_real),
                    "descripcion": f"Ingreso liquidación Cashea Lote #{lote.id} ({destino.nombre})",
                }
            )
        if total_descuento_real > Decimal("0.00"):
            lineas_asiento.append(
                {
                    "codigo_cuenta": "6.3.03",
                    "debe_usd": _d2(total_descuento_real),
                    "descripcion": f"Comisiones y retenciones reales Cashea Lote #{lote.id}",
                }
            )
        # Ajuste contable si pagado_real + descuento_real != total_financiado
        ajuste = _d2(total_financiado - (total_pagado_real + total_descuento_real))
        if ajuste > Decimal("0.00"):
            lineas_asiento.append(
                {
                    "codigo_cuenta": "6.3.03",
                    "debe_usd": ajuste,
                    "descripcion": f"Ajuste/diferencia en liquidación Cashea Lote #{lote.id}",
                }
            )
        elif ajuste < Decimal("0.00"):
            lineas_asiento.append(
                {
                    "codigo_cuenta": "4.1.01",
                    "haber_usd": abs(ajuste),
                    "descripcion": f"Ajuste favorable en liquidación Cashea Lote #{lote.id}",
                }
            )

        lineas_asiento.append(
            {
                "codigo_cuenta": "1.1.03",
                "haber_usd": _d2(total_financiado),
                "descripcion": f"Cancelación Cashea por Cobrar Lote #{lote.id} ({len(notas_conciliadas)} notas)",
            }
        )

        asiento = registrar_asiento(
            bd,
            fecha=datos.fecha_deposito,
            referencia=f"CASHEA-LOTE-{lote.id}",
            modulo_origen="CASHEA_LIQUIDACION",
            entidad_id=str(lote.id),
            descripcion=f"Liquidación y conciliación Cashea Lote #{lote.id} ({len(notas_conciliadas)} notas)",
            creado_por_id=usuario_actual.id,
            lineas=lineas_asiento,
        )

        # 5. Auditoría del sistema
        registrar_auditoria(
            bd,
            usuario=usuario_actual,
            modulo="FINANZAS_CASHEA",
            accion="CONCILIAR_LOTE_CASHEA",
            entidad_id=f"LOTE-{lote.id}",
            detalle_anterior={"notas_pendientes": notas_conciliadas},
            detalle_nuevo={
                "lote_id": lote.id,
                "notas_conciliadas": notas_conciliadas,
                "instrumento_destino": destino.nombre,
                "total_financiado_usd": _r2(total_financiado),
                "total_pagado_real_usd": _r2(total_pagado_real),
                "total_descuento_real_usd": _r2(total_descuento_real),
                "total_diferencia_usd": _r2(total_diferencia),
                "asiento_id": asiento.id,
            },
        )
        bd.commit()
    except HTTPException:
        bd.rollback()
        raise
    except Exception as exc:
        bd.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al confirmar la liquidación Cashea: {exc}",
        ) from exc

    return {
        "lote_id": lote.id,
        "asiento_id": asiento.id,
        "pago_id": pago_ingreso.id,
        "notas_conciliadas": len(notas_conciliadas),
        "total_financiado_usd": _r2(total_financiado),
        "total_pagado_real_usd": _r2(total_pagado_real),
        "total_descuento_real_usd": _r2(total_descuento_real),
        "total_diferencia_usd": _r2(total_diferencia),
        "monto_moneda_destino": _r2(monto_origen),
        "moneda_destino": destino.moneda,
    }
