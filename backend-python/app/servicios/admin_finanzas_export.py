from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from fastapi import HTTPException, status
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modelos import Sucursal, TasaDiaria, Usuario
from app.modelos_admin_finanzas import (
    AuditoriaSistema,
    ConciliacionBancaria,
    DocumentoFiscal,
    GastoOperativo,
    NominaEmpleado,
    NominaPeriodo,
    NominaRecibo,
)
from app.modelos_finanzas import (
    EstadoVerificacionPago,
    InstrumentoFinanciero,
    MonedaInstrumento,
    Pago,
    TipoDocumentoPago,
    TipoMovimientoPago,
)
from app.modelos_logistica import Compra, EstadoCompra, OrigenCompra, Tercero, TipoTercero
from app.modelos_operaciones import MovimientoTesoreria
from app.rutas.tasas import obtener_fecha_hoy
from app.rutas.ventas import generar_correlativo_corto
from app.utils.pdf_branding import ASSETS_DIR, dibujar_marca_de_agua


# =====================================================================
# 1. EXPORTADORES PDF (CON MARCA DE AGUA TEKIO)
# =====================================================================

def _cabecera_pdf_admin(
    pdf: canvas.Canvas,
    ancho: float,
    alto: float,
    titulo: str,
    subtitulo: str,
) -> float:
    dibujar_marca_de_agua(pdf)
    ruta_logo = ASSETS_DIR / "tekio-logo-horizontal.png"
    if ruta_logo.exists():
        pdf.drawImage(
            str(ruta_logo),
            0.50 * inch,
            alto - 0.96 * inch,
            width=1.9 * inch,
            height=0.58 * inch,
            preserveAspectRatio=True,
            mask="auto",
        )
    else:
        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(0.50 * inch, alto - 0.68 * inch, "TEKIO ELECTRONICS")
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 11.5)
    pdf.drawRightString(ancho - 0.50 * inch, alto - 0.56 * inch, titulo)
    pdf.setFont("Helvetica", 8.2)
    pdf.setFillColorRGB(0.4, 0.4, 0.4)
    pdf.drawRightString(ancho - 0.50 * inch, alto - 0.74 * inch, subtitulo)
    pdf.setStrokeColorRGB(0.91, 0.35, 0.16)
    pdf.setLineWidth(1.2)
    pdf.line(0.50 * inch, alto - 1.06 * inch, ancho - 0.50 * inch, alto - 1.06 * inch)
    return alto - 1.32 * inch


def generar_pdf_estado_resultados(pyl: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=letter)
    ancho, alto = letter
    y = _cabecera_pdf_admin(
        pdf,
        ancho,
        alto,
        "ESTADO DE RESULTADOS (P&L)",
        f"Período: {pyl['fecha_inicio']} al {pyl['fecha_fin']} · {pyl['sucursal']}",
    )

    filas = [
        ("Ingresos por Ventas y Servicios (Promo USD)", pyl["ingresos_ventas_usd"], False),
        ("(-) Costo de Mercancía Vendida (COGS)", -pyl["costo_mercancia_usd"], False),
        ("= UTILIDAD BRUTA", pyl["utilidad_bruta_usd"], True),
        ("(-) Gastos Operativos Administrativos", -pyl["gastos_operativos_usd"], False),
        ("(-) Comisiones Liquidadas del Período", -pyl["comisiones_liquidadas_usd"], False),
        ("(-) Nómina Pagada del Período", -pyl["nomina_pagada_usd"], False),
        ("(+/-) Diferencial Cambiario Tesorería", pyl["diferencial_cambiario_usd"], False),
        ("= UTILIDAD NETA DEL PERÍODO", pyl["utilidad_neta_usd"], True),
    ]

    for etiqueta, monto, destacado in filas:
        if destacado:
            pdf.setFillColorRGB(0.992, 0.941, 0.922)
            pdf.rect(0.50 * inch, y - 0.08 * inch, ancho - 1.0 * inch, 0.28 * inch, fill=1, stroke=0)
            pdf.setFont("Helvetica-Bold", 9.5)
            pdf.setFillColorRGB(0.098, 0.094, 0.094)
        else:
            pdf.setFont("Helvetica", 9.0)
            pdf.setFillColorRGB(0.2, 0.2, 0.2)
        pdf.drawString(0.62 * inch, y, etiqueta)
        pdf.drawRightString(ancho - 0.62 * inch, y, f"${Decimal(str(monto)):,.2f}")
        y -= 0.32 * inch

    if pyl.get("gastos_por_categoria"):
        y -= 0.18 * inch
        pdf.setFont("Helvetica-Bold", 9.2)
        pdf.setFillColorRGB(0.91, 0.35, 0.16)
        pdf.drawString(0.50 * inch, y, "Desglose de Gastos Operativos por Categoría")
        y -= 0.24 * inch
        pdf.setFont("Helvetica", 8.5)
        pdf.setFillColorRGB(0.15, 0.15, 0.15)
        for cat in pyl["gastos_por_categoria"]:
            pdf.drawString(0.62 * inch, y, f"• {cat['categoria']} ({cat['cantidad']} reg.)")
            pdf.drawRightString(ancho - 0.62 * inch, y, f"${Decimal(str(cat['total_usd'])):,.2f}")
            y -= 0.22 * inch

    pdf.save()
    return buf.getvalue()


def generar_pdf_libro_fiscal(tipo_libro: str, docs: list[DocumentoFiscal], periodo: str) -> bytes:
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=letter)
    ancho, alto = letter
    titulo = f"LIBRO DE {'COMPRAS' if tipo_libro == 'COMPRA' else 'VENTAS'} (SENIAT)"
    y = _cabecera_pdf_admin(pdf, ancho, alto, titulo, f"Período: {periodo} · {len(docs)} documentos")

    pdf.setFont("Helvetica-Bold", 7.6)
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.drawString(0.50 * inch, y, "Fecha")
    pdf.drawString(1.22 * inch, y, "Factura / Control")
    pdf.drawString(2.55 * inch, y, "RIF / Tercero")
    pdf.drawRightString(5.35 * inch, y, "Base Imp.")
    pdf.drawRightString(6.20 * inch, y, "IVA 16%")
    pdf.drawRightString(7.00 * inch, y, "IGTF / Ret.")
    pdf.drawRightString(ancho - 0.50 * inch, y, "Total")
    y -= 0.20 * inch

    total_base = Decimal("0")
    total_iva = Decimal("0")
    total_doc = Decimal("0")

    pdf.setFont("Helvetica", 7.4)
    for d in docs:
        if y < 0.85 * inch:
            pdf.showPage()
            y = _cabecera_pdf_admin(pdf, ancho, alto, titulo, f"Período: {periodo} (cont.)")
            pdf.setFont("Helvetica", 7.4)
        total_base += d.base_imponible
        total_iva += d.iva_monto
        total_doc += d.total_documento
        pdf.drawString(0.50 * inch, y, d.fecha.isoformat())
        pdf.drawString(1.22 * inch, y, f"{d.numero_factura[:14]} / {d.numero_control[:8]}")
        pdf.drawString(2.55 * inch, y, f"{d.rif_tercero} {d.nombre_tercero[:22]}")
        pdf.drawRightString(5.35 * inch, y, f"{d.base_imponible:,.2f}")
        pdf.drawRightString(6.20 * inch, y, f"{d.iva_monto:,.2f}")
        pdf.drawRightString(7.00 * inch, y, f"{(d.igtf_monto + d.retencion_iva_monto):,.2f}")
        pdf.drawRightString(ancho - 0.50 * inch, y, f"{d.total_documento:,.2f}")
        y -= 0.19 * inch

    y -= 0.14 * inch
    pdf.setFont("Helvetica-Bold", 8.4)
    pdf.drawString(0.50 * inch, y, "TOTALES DEL LIBRO:")
    pdf.drawRightString(5.35 * inch, y, f"{total_base:,.2f}")
    pdf.drawRightString(6.20 * inch, y, f"{total_iva:,.2f}")
    pdf.drawRightString(ancho - 0.50 * inch, y, f"{total_doc:,.2f}")
    pdf.save()
    return buf.getvalue()


def generar_pdf_recibo_nomina(recibo: NominaRecibo, periodo: NominaPeriodo, empleado: NominaEmpleado) -> bytes:
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=letter)
    ancho, alto = letter
    y = _cabecera_pdf_admin(
        pdf,
        ancho,
        alto,
        f"RECIBO DE PAGO · {periodo.codigo}",
        f"Período {periodo.tipo_periodo}: {periodo.fecha_inicio.isoformat()} al {periodo.fecha_fin.isoformat()}",
    )

    nombre_usr = recibo.usuario.nombre if recibo.usuario else "Colaborador"
    pdf.setFillColorRGB(0.953, 0.957, 0.965)
    pdf.roundRect(0.50 * inch, y - 0.72 * inch, ancho - 1.0 * inch, 0.78 * inch, 6, fill=1, stroke=0)
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 9.0)
    pdf.drawString(0.62 * inch, y - 0.16 * inch, f"Trabajador: {nombre_usr}  ·  C.I.: {empleado.cedula or 'N/D'}")
    pdf.setFont("Helvetica", 8.4)
    pdf.drawString(0.62 * inch, y - 0.36 * inch, f"Cargo: {empleado.cargo or 'Personal'}  ·  Cuenta/Pago: {empleado.datos_bancarios or 'N/D'}")
    pdf.drawString(0.62 * inch, y - 0.56 * inch, f"Estado Nómina: {periodo.estado}  ·  Ref. Pago: {periodo.referencia_pago or '—'}")
    y -= 1.02 * inch

    conceptos = [
        ("Salario Base", recibo.salario_base_usd),
        ("Bonificación / Cestaticket", recibo.bonos_usd),
        ("Horas Extras / Otros Ingresos", recibo.otros_ingresos_usd),
        ("(-) Adelantos / Préstamos", -recibo.adelantos_usd),
        ("(-) Deducción IVSS", -recibo.deduccion_ivss_usd),
        ("(-) Deducción FAOV", -recibo.deduccion_faov_usd),
        ("(-) Deducción RPE", -recibo.deduccion_rpe_usd),
        ("(-) Otras Deducciones", -recibo.otras_deducciones_usd),
    ]
    pdf.setFont("Helvetica", 9.0)
    for label, val in conceptos:
        pdf.drawString(0.62 * inch, y, label)
        pdf.drawRightString(ancho - 0.62 * inch, y, f"${val:,.2f}")
        y -= 0.26 * inch

    y -= 0.08 * inch
    pdf.setFillColorRGB(0.992, 0.941, 0.922)
    pdf.rect(0.50 * inch, y - 0.10 * inch, ancho - 1.0 * inch, 0.32 * inch, fill=1, stroke=0)
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 10.2)
    pdf.drawString(0.62 * inch, y, "NETO A PAGAR EN NÓMINA (USD)")
    pdf.drawRightString(ancho - 0.62 * inch, y, f"${recibo.neto_pagar_usd:,.2f}")
    y -= 0.42 * inch

    if recibo.comisiones_informativas_usd > 0:
        pdf.setFont("Helvetica-Oblique", 8.2)
        pdf.setFillColorRGB(0.35, 0.35, 0.35)
        pdf.drawString(
            0.62 * inch,
            y,
            f"Nota informativa (no duplica pago): Comisiones liquidadas por separado en el período: ${recibo.comisiones_informativas_usd:,.2f} USD.",
        )

    y_firma = max(1.2 * inch, y - 1.0 * inch)
    pdf.setStrokeColorRGB(0.5, 0.5, 0.5)
    pdf.line(0.85 * inch, y_firma, 3.35 * inch, y_firma)
    pdf.line(ancho - 3.35 * inch, y_firma, ancho - 0.85 * inch, y_firma)
    pdf.setFont("Helvetica-Bold", 8.2)
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.drawCentredString(2.10 * inch, y_firma - 0.16 * inch, "Recibí Conforme (Trabajador)")
    pdf.drawCentredString(ancho - 2.10 * inch, y_firma - 0.16 * inch, "Administración / Dirección")

    pdf.save()
    return buf.getvalue()


def generar_pdf_conciliacion(partidas: list[ConciliacionBancaria], instrumento_nombre: str) -> bytes:
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=letter)
    ancho, alto = letter
    y = _cabecera_pdf_admin(
        pdf,
        ancho,
        alto,
        "REPORTE DE CONCILIACIÓN BANCARIA",
        f"Cuenta: {instrumento_nombre} · {len(partidas)} partidas",
    )
    pdf.setFont("Helvetica-Bold", 7.8)
    pdf.drawString(0.50 * inch, y, "Fecha")
    pdf.drawString(1.25 * inch, y, "Referencia")
    pdf.drawString(2.45 * inch, y, "Descripción")
    pdf.drawRightString(5.85 * inch, y, "Monto Banco")
    pdf.drawRightString(ancho - 0.50 * inch, y, "Estado")
    y -= 0.22 * inch

    pdf.setFont("Helvetica", 7.5)
    for p in partidas:
        if y < 0.85 * inch:
            pdf.showPage()
            y = _cabecera_pdf_admin(pdf, ancho, alto, "REPORTE DE CONCILIACIÓN BANCARIA", f"{instrumento_nombre} (cont.)")
            pdf.setFont("Helvetica", 7.5)
        pdf.drawString(0.50 * inch, y, p.fecha_movimiento.isoformat())
        pdf.drawString(1.25 * inch, y, (p.referencia or "—")[:18])
        pdf.drawString(2.45 * inch, y, (p.descripcion or "—")[:38])
        signo = "-" if p.tipo_movimiento == "DEBITO" else "+"
        pdf.drawRightString(5.85 * inch, y, f"{signo}{p.monto_banco:,.2f}")
        pdf.drawRightString(ancho - 0.50 * inch, y, p.estado)
        y -= 0.19 * inch

    pdf.save()
    return buf.getvalue()


def generar_pdf_auditoria(registros: list[AuditoriaSistema]) -> bytes:
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=letter)
    ancho, alto = letter
    y = _cabecera_pdf_admin(
        pdf,
        ancho,
        alto,
        "BITÁCORA DE AUDITORÍA INTERNA",
        f"Registros inmutables exportados: {len(registros)}",
    )
    pdf.setFont("Helvetica-Bold", 7.6)
    pdf.drawString(0.50 * inch, y, "Fecha")
    pdf.drawString(1.75 * inch, y, "Usuario / Rol")
    pdf.drawString(3.45 * inch, y, "Módulo")
    pdf.drawString(4.55 * inch, y, "Acción")
    pdf.drawRightString(ancho - 0.50 * inch, y, "Entidad")
    y -= 0.22 * inch

    pdf.setFont("Helvetica", 7.4)
    for r in registros[:250]:
        if y < 0.85 * inch:
            pdf.showPage()
            y = _cabecera_pdf_admin(pdf, ancho, alto, "BITÁCORA DE AUDITORÍA INTERNA", "Continuación")
            pdf.setFont("Helvetica", 7.4)
        fecha_txt = r.fecha.strftime("%Y-%m-%d %H:%M") if r.fecha else ""
        pdf.drawString(0.50 * inch, y, fecha_txt)
        pdf.drawString(1.75 * inch, y, f"{r.usuario_nombre[:18]} ({r.usuario_rol[:6]})")
        pdf.drawString(3.45 * inch, y, r.modulo[:16])
        pdf.drawString(4.55 * inch, y, r.accion[:32])
        pdf.drawRightString(ancho - 0.50 * inch, y, r.entidad_id[:14])
        y -= 0.19 * inch

    pdf.save()
    return buf.getvalue()


# =====================================================================
# 2. EXPORTADORES EXCEL (.XLSX)
# =====================================================================

def _estilo_cabecera_xlsx(ws: Any, cabeceras: list[str]) -> None:
    relleno = PatternFill(start_color="191818", end_color="191818", fill_type="solid")
    fuente = Font(color="FFFFFF", bold=True, size=10)
    for idx, titulo in enumerate(cabeceras, start=1):
        celda = ws.cell(row=1, column=idx, value=titulo)
        celda.fill = relleno
        celda.font = fuente
        celda.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[celda.column_letter].width = max(16, len(titulo) + 4)


def generar_xlsx_estado_resultados(pyl: dict[str, Any]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Estado de Resultados"
    _estilo_cabecera_xlsx(ws, ["Concepto", "Monto USD"])
    filas = [
        ("Ingresos por Ventas y Servicios", pyl["ingresos_ventas_usd"]),
        ("Costo de Mercancía Vendida (COGS)", -pyl["costo_mercancia_usd"]),
        ("Utilidad Bruta", pyl["utilidad_bruta_usd"]),
        ("Gastos Operativos Administrativos", -pyl["gastos_operativos_usd"]),
        ("Comisiones Liquidadas", -pyl["comisiones_liquidadas_usd"]),
        ("Nómina Pagada", -pyl["nomina_pagada_usd"]),
        ("Diferencial Cambiario Tesorería", pyl["diferencial_cambiario_usd"]),
        ("Utilidad Neta", pyl["utilidad_neta_usd"]),
    ]
    for r_idx, (c, m) in enumerate(filas, start=2):
        ws.cell(row=r_idx, column=1, value=c)
        ws.cell(row=r_idx, column=2, value=float(m))
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def generar_xlsx_libro_fiscal(tipo_libro: str, docs: list[DocumentoFiscal]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = f"Libro {'Compras' if tipo_libro == 'COMPRA' else 'Ventas'}"
    cabeceras = [
        "Fecha",
        "Nro. Factura",
        "Nro. Control",
        "RIF Tercero",
        "Nombre Tercero",
        "Moneda",
        "Tasa BCV",
        "Base Imponible",
        "Monto Exento",
        "IVA %",
        "IVA Monto",
        "IGTF %",
        "IGTF Monto",
        "Total Documento",
        "Ret. IVA %",
        "Ret. IVA Monto",
        "Comp. Ret. IVA",
        "Ret. ISLR Monto",
        "Comp. Ret. ISLR",
    ]
    _estilo_cabecera_xlsx(ws, cabeceras)
    for r_idx, d in enumerate(docs, start=2):
        vals = [
            d.fecha.isoformat(),
            d.numero_factura,
            d.numero_control,
            d.rif_tercero,
            d.nombre_tercero,
            d.moneda,
            float(d.tasa_bcv),
            float(d.base_imponible),
            float(d.monto_exento),
            float(d.iva_pct),
            float(d.iva_monto),
            float(d.igtf_pct),
            float(d.igtf_monto),
            float(d.total_documento),
            float(d.retencion_iva_pct),
            float(d.retencion_iva_monto),
            d.comprobante_ret_iva,
            float(d.retencion_islr_monto),
            d.comprobante_ret_islr,
        ]
        for c_idx, v in enumerate(vals, start=1):
            ws.cell(row=r_idx, column=c_idx, value=v)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def generar_xlsx_auditoria(registros: list[AuditoriaSistema]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Auditoria Sistema"
    _estilo_cabecera_xlsx(
        ws,
        ["ID", "Fecha", "Usuario", "Rol", "Módulo", "Acción", "Entidad", "Antes", "Después"],
    )
    for r_idx, r in enumerate(registros, start=2):
        vals = [
            r.id,
            r.fecha.isoformat() if r.fecha else "",
            r.usuario_nombre,
            r.usuario_rol,
            r.modulo,
            r.accion,
            r.entidad_id,
            r.detalle_anterior_json,
            r.detalle_nuevo_json,
        ]
        for c_idx, v in enumerate(vals, start=1):
            ws.cell(row=r_idx, column=c_idx, value=v)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# =====================================================================
# 3. PLANTILLAS .XLSX Y CARGA MASIVA ADMINISTRATIVA ATÓMICA (4 FLUJOS)
# =====================================================================

FLUJOS_ADMIN: dict[str, dict[str, Any]] = {
    "gastos_operativos": {
        "titulo": "Gastos Operativos",
        "columnas": [
            "fecha",
            "categoria",
            "sucursal",
            "proveedor",
            "factura_comprobante",
            "descripcion",
            "moneda",
            "monto_origen",
            "instrumento",
        ],
        "ejemplo": [
            "2026-11-24",
            "ALQUILER",
            "Tekio central",
            "CC Free Market",
            "FAC-ALQ-11",
            "Alquiler local noviembre",
            "USD",
            "350.00",
            "Efectivo divisas",
        ],
    },
    "facturas_cxp": {
        "titulo": "Facturas Proveedores CxP",
        "columnas": [
            "fecha",
            "fecha_vencimiento",
            "proveedor",
            "factura_orden",
            "monto_total_usd",
            "saldo_pendiente_usd",
            "origen",
            "nota",
        ],
        "ejemplo": [
            "2026-11-24",
            "2026-12-01",
            "Distribuidora Tech CA",
            "FAC-PROV-102",
            "1200.00",
            "1200.00",
            "NACIONAL",
            "Crédito 7 días",
        ],
    },
    "nomina_adelantos": {
        "titulo": "Nomina y Adelantos",
        "columnas": [
            "nombre_usuario",
            "cedula",
            "cargo",
            "salario_base_usd",
            "bono_cestaticket_usd",
            "datos_bancarios",
        ],
        "ejemplo": [
            "Valeria Asesora",
            "V-25123456",
            "Asesora Comercial",
            "220.00",
            "40.00",
            "Pago Móvil 0414-0000000",
        ],
    },
    "extractos_bancarios": {
        "titulo": "Extractos Bancarios",
        "columnas": [
            "fecha",
            "referencia",
            "descripcion",
            "tipo_movimiento",
            "monto",
        ],
        "ejemplo": [
            "2026-11-24",
            "REF-88421",
            "Pago móvil cliente",
            "CREDITO",
            "15000.00",
        ],
    },
}

CATEGORIAS_GASTO = {
    "ALQUILER",
    "SERVICIOS",
    "NOMINA",
    "PUBLICIDAD",
    "MANTENIMIENTO",
    "IMPUESTOS",
    "LOGISTICA_ENVIOS",
    "OTROS",
}


def generar_plantilla_admin_xlsx(flujo: str) -> bytes:
    if flujo not in FLUJOS_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Flujo administrativo no soportado: '{flujo}'.",
        )
    spec = FLUJOS_ADMIN[flujo]
    wb = Workbook()
    ws = wb.active
    ws.title = spec["titulo"][:31]
    _estilo_cabecera_xlsx(ws, spec["columnas"])
    relleno_ej = PatternFill(start_color="FDF0EB", end_color="FDF0EB", fill_type="solid")
    for idx, val in enumerate(spec["ejemplo"], start=1):
        c = ws.cell(row=2, column=idx, value=val)
        c.fill = relleno_ej
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _leer_archivo_tabular(contenido: bytes, nombre_archivo: str) -> list[dict[str, Any]]:
    nombre = (nombre_archivo or "").lower()
    if nombre.endswith(".csv"):
        try:
            texto = contenido.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = contenido.decode("latin-1")
        lector = csv.DictReader(io.StringIO(texto))
        filas = []
        for idx, fila in enumerate(lector, start=2):
            limpia = {str(k).strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in fila.items() if k}
            if not any(str(v or "").strip() for v in limpia.values()):
                continue
            limpia["_fila"] = idx
            filas.append(limpia)
        return filas
    if nombre.endswith(".xlsx") or nombre.endswith(".xlsm"):
        wb = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        try:
            primera = next(it)
        except StopIteration:
            return []
        cabs = [str(c).strip().lower() if c is not None else "" for c in primera]
        filas = []
        for idx, vals in enumerate(it, start=2):
            if not any(v is not None and str(v).strip() != "" for v in vals):
                continue
            reg: dict[str, Any] = {"_fila": idx}
            for c_i, c_nom in enumerate(cabs):
                if c_nom:
                    v = vals[c_i] if c_i < len(vals) else None
                    reg[c_nom] = str(v).strip() if v is not None else ""
            filas.append(reg)
        wb.close()
        return filas
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Formato no soportado. Sube un archivo .xlsx o .csv.",
    )


def _dec(valor: Any, default: Decimal = Decimal("0")) -> Decimal:
    txt = str(valor if valor is not None else "").strip().replace(",", ".")
    if not txt:
        return default
    try:
        return Decimal(txt)
    except InvalidOperation as exc:
        raise ValueError(f"Monto inválido: '{valor}'") from exc


def _fecha_iso(valor: Any, default: date | None = None) -> date | None:
    txt = str(valor or "").strip()[:10]
    if not txt:
        return default
    try:
        return date.fromisoformat(txt)
    except ValueError as exc:
        raise ValueError(f"Fecha inválida (usa YYYY-MM-DD): '{valor}'") from exc


def previsualizar_importacion_admin(
    bd: Session,
    *,
    flujo: str,
    contenido: bytes,
    nombre_archivo: str,
    instrumento_id: int | None = None,
) -> dict[str, Any]:
    if flujo not in FLUJOS_ADMIN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Flujo inválido: {flujo}")

    filas = _leer_archivo_tabular(contenido, nombre_archivo)
    if not filas:
        return {
            "flujo": flujo,
            "total_filas": 0,
            "filas_validas": 0,
            "filas_con_error": 1,
            "puede_confirmar": False,
            "filas": [{"fila": 1, "valida": False, "errores": ["El archivo no contiene filas."], "datos": {}}],
        }

    inst_map = {i.nombre.strip().lower(): i for i in bd.query(InstrumentoFinanciero).all()}
    usr_map = {u.nombre.strip().lower(): u for u in bd.query(Usuario).all()}

    resultados = []
    validas = 0
    for f in filas:
        num = int(f.get("_fila", 0))
        errores: list[str] = []
        if flujo == "gastos_operativos":
            cat = str(f.get("categoria") or "").strip().upper()
            if cat not in CATEGORIAS_GASTO:
                errores.append(f"Categoría inválida '{cat}'.")
            inst_nom = str(f.get("instrumento") or "").strip().lower()
            if inst_nom not in inst_map:
                errores.append(f"Instrumento/banco '{f.get('instrumento')}' no encontrado.")
            try:
                _fecha_iso(f.get("fecha"), obtener_fecha_hoy())
                m = _dec(f.get("monto_origen"))
                if m <= 0:
                    errores.append("monto_origen debe ser mayor a 0.")
            except ValueError as exc:
                errores.append(str(exc))
        elif flujo == "facturas_cxp":
            if not str(f.get("proveedor") or "").strip():
                errores.append("Proveedor obligatorio.")
            try:
                _fecha_iso(f.get("fecha"), obtener_fecha_hoy())
                _fecha_iso(f.get("fecha_vencimiento"), None)
                s = _dec(f.get("saldo_pendiente_usd"))
                if s <= 0:
                    errores.append("saldo_pendiente_usd debe ser mayor a 0.")
            except ValueError as exc:
                errores.append(str(exc))
        elif flujo == "nomina_adelantos":
            u_nom = str(f.get("nombre_usuario") or "").strip().lower()
            if u_nom not in usr_map:
                errores.append(f"Usuario '{f.get('nombre_usuario')}' no encontrado.")
            try:
                _dec(f.get("salario_base_usd"))
                _dec(f.get("bono_cestaticket_usd"))
            except ValueError as exc:
                errores.append(str(exc))
        elif flujo == "extractos_bancarios":
            if instrumento_id is None:
                errores.append("Debes seleccionar la cuenta/instrumento bancario.")
            tm = str(f.get("tipo_movimiento") or "CREDITO").strip().upper()
            if tm not in {"CREDITO", "DEBITO"}:
                errores.append("tipo_movimiento debe ser CREDITO o DEBITO.")
            try:
                _fecha_iso(f.get("fecha"), obtener_fecha_hoy())
                m = _dec(f.get("monto"))
                if m <= 0:
                    errores.append("monto debe ser mayor a 0.")
            except ValueError as exc:
                errores.append(str(exc))

        ok = len(errores) == 0
        if ok:
            validas += 1
        resultados.append(
            {
                "fila": num,
                "valida": ok,
                "errores": errores,
                "datos": {k: v for k, v in f.items() if k != "_fila"},
            }
        )

    con_error = len(resultados) - validas
    return {
        "flujo": flujo,
        "total_filas": len(resultados),
        "filas_validas": validas,
        "filas_con_error": con_error,
        "puede_confirmar": len(resultados) > 0 and con_error == 0,
        "filas": resultados,
    }


def confirmar_importacion_admin_atomica(
    bd: Session,
    *,
    flujo: str,
    contenido: bytes,
    nombre_archivo: str,
    usuario: Usuario,
    instrumento_id: int | None = None,
) -> dict[str, Any]:
    preview = previsualizar_importacion_admin(
        bd,
        flujo=flujo,
        contenido=contenido,
        nombre_archivo=nombre_archivo,
        instrumento_id=instrumento_id,
    )
    if not preview["puede_confirmar"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "mensaje": "El archivo contiene errores. No se guardó ningún registro.",
                "filas_con_error": preview["filas_con_error"],
                "filas": [f for f in preview["filas"] if not f["valida"]],
            },
        )

    hoy = obtener_fecha_hoy()
    tasa = bd.query(TasaDiaria).filter(TasaDiaria.fecha <= hoy).order_by(TasaDiaria.fecha.desc()).first()
    tasa_bcv = tasa.tasa_bcv if tasa else Decimal("0")
    tasa_usdt = tasa.tasa_usdt if tasa else tasa_bcv

    inst_map = {i.nombre.strip().lower(): i for i in bd.query(InstrumentoFinanciero).all()}
    suc_map = {s.nombre.strip().lower(): s for s in bd.query(Sucursal).all()}
    usr_map = {u.nombre.strip().lower(): u for u in bd.query(Usuario).all()}
    filas = [f["datos"] for f in preview["filas"]]

    try:
        procesados = 0
        if flujo == "gastos_operativos":
            for f in filas:
                inst = inst_map[str(f.get("instrumento") or "").strip().lower()]
                suc_nom = str(f.get("sucursal") or "").strip().lower()
                suc = suc_map.get(suc_nom) if suc_nom and suc_nom != "general" else None
                fecha_op = _fecha_iso(f.get("fecha"), hoy) or hoy
                monto_orig = _dec(f.get("monto_origen"))
                mon = str(f.get("moneda") or inst.moneda).strip().upper()
                monto_usd = (
                    (monto_orig / tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    if mon == "BS" and tasa_bcv > 0
                    else monto_orig.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                )
                codigo = generar_correlativo_corto(bd, GastoOperativo, GastoOperativo.codigo, "GAS")
                pago = Pago(
                    venta_id=None,
                    instrumento_id=inst.id,
                    fecha=fecha_op,
                    tipo_movimiento=TipoMovimientoPago.EGRESO.value,
                    tipo_documento=TipoDocumentoPago.GASTO_OPERATIVO.value,
                    monto_moneda_origen=monto_orig,
                    moneda=mon,
                    usd_nominal=monto_usd,
                    usd_real=(
                        (monto_orig / tasa_usdt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        if mon == "BS" and tasa_usdt > 0
                        else monto_usd
                    ),
                    referencia=str(f.get("factura_comprobante") or codigo).strip(),
                    estado_verificacion=EstadoVerificacionPago.CONFIRMADO.value,
                    verificado_por_id=usuario.id,
                    nota=f"{codigo} · {f.get('categoria')} · {f.get('descripcion')}",
                )
                bd.add(pago)
                bd.flush()
                bd.add(
                    GastoOperativo(
                        codigo=codigo,
                        fecha=fecha_op,
                        categoria=str(f.get("categoria") or "OTROS").strip().upper(),
                        sucursal_id=suc.id if suc else None,
                        proveedor=str(f.get("proveedor") or "").strip(),
                        factura_comprobante=str(f.get("factura_comprobante") or "").strip(),
                        descripcion=str(f.get("descripcion") or "").strip(),
                        moneda=mon,
                        monto_origen=monto_orig,
                        tasa_bcv=tasa_bcv,
                        monto_usd=monto_usd,
                        instrumento_id=inst.id,
                        pago_egreso_id=pago.id,
                        usuario_id=usuario.id,
                    )
                )
                procesados += 1

        elif flujo == "facturas_cxp":
            for f in filas:
                prov_nom = str(f.get("proveedor") or "").strip()
                prov = bd.query(Tercero).filter(func.lower(Tercero.nombre) == prov_nom.lower()).first()
                if prov is None:
                    prov = Tercero(nombre=prov_nom, tipo=TipoTercero.PROVEEDOR.value, rif_cedula="", telefono="", activo=True)
                    bd.add(prov)
                    bd.flush()
                num_cmp = generar_correlativo_corto(bd, Compra, Compra.numero_compra, "CXP")
                bd.add(
                    Compra(
                        numero_compra=num_cmp,
                        origen=str(f.get("origen") or OrigenCompra.NACIONAL.value).strip().upper(),
                        tipo_compra="NACIONAL",
                        proveedor_id=prov.id,
                        fecha=_fecha_iso(f.get("fecha"), hoy) or hoy,
                        fecha_vencimiento=_fecha_iso(f.get("fecha_vencimiento"), None),
                        factura_orden=str(f.get("factura_orden") or num_cmp).strip(),
                        monto_mercancia_usd=_dec(f.get("monto_total_usd")),
                        saldo_pendiente_usd=_dec(f.get("saldo_pendiente_usd")),
                        estado=EstadoCompra.RECIBIDA.value,
                        nota=str(f.get("nota") or "Importación CxP").strip(),
                        creado_por_id=usuario.id,
                    )
                )
                procesados += 1

        elif flujo == "nomina_adelantos":
            for f in filas:
                usr = usr_map[str(f.get("nombre_usuario") or "").strip().lower()]
                emp = bd.query(NominaEmpleado).filter(NominaEmpleado.usuario_id == usr.id).first()
                if emp is None:
                    emp = NominaEmpleado(usuario_id=usr.id, sucursal_id=usr.sucursal_id)
                    bd.add(emp)
                emp.cedula = str(f.get("cedula") or emp.cedula or "").strip()
                emp.cargo = str(f.get("cargo") or emp.cargo or usr.rol).strip()
                emp.salario_base_usd = _dec(f.get("salario_base_usd"), emp.salario_base_usd or Decimal("0"))
                emp.bono_cestaticket_usd = _dec(f.get("bono_cestaticket_usd"), emp.bono_cestaticket_usd or Decimal("0"))
                emp.datos_bancarios = str(f.get("datos_bancarios") or emp.datos_bancarios or "").strip()
                procesados += 1

        elif flujo == "extractos_bancarios":
            lote = generar_correlativo_corto(bd, ConciliacionBancaria, ConciliacionBancaria.lote_codigo, "CONC")
            pagos_inst = (
                bd.query(Pago)
                .filter(Pago.instrumento_id == instrumento_id, Pago.anulado.is_(False))
                .all()
            )
            tes_inst = (
                bd.query(MovimientoTesoreria)
                .filter(
                    (MovimientoTesoreria.instrumento_origen_id == instrumento_id)
                    | (MovimientoTesoreria.instrumento_destino_id == instrumento_id)
                )
                .all()
            )
            usados_pagos: set[int] = set()
            for f in filas:
                f_mov = _fecha_iso(f.get("fecha"), hoy) or hoy
                ref = str(f.get("referencia") or "").strip()
                desc = str(f.get("descripcion") or "").strip()
                tm = str(f.get("tipo_movimiento") or "CREDITO").strip().upper()
                monto = _dec(f.get("monto")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                match_pago = None
                for p in pagos_inst:
                    if p.id in usados_pagos:
                        continue
                    tipo_esperado = TipoMovimientoPago.INGRESO.value if tm == "CREDITO" else TipoMovimientoPago.EGRESO.value
                    if p.tipo_movimiento != tipo_esperado:
                        continue
                    if abs(p.monto_moneda_origen - monto) <= Decimal("0.05") and abs((p.fecha - f_mov).days) <= 3:
                        if not ref or (p.referencia and ref.lower() in p.referencia.lower()):
                            match_pago = p
                            break
                match_tes = None
                if match_pago is None and ref:
                    for t in tes_inst:
                        if ref.lower() in (t.referencia or "").lower() or ref.lower() == t.codigo.lower():
                            match_tes = t
                            break

                estado_c = "CONCILIADO" if (match_pago or match_tes) else "PENDIENTE_SISTEMA"
                if match_pago:
                    usados_pagos.add(match_pago.id)
                    match_pago.conciliado = True

                bd.add(
                    ConciliacionBancaria(
                        instrumento_id=int(instrumento_id),
                        lote_codigo=lote,
                        fecha_movimiento=f_mov,
                        referencia=ref,
                        descripcion=desc,
                        monto_banco=monto,
                        tipo_movimiento=tm,
                        estado=estado_c,
                        pago_id=match_pago.id if match_pago else None,
                        tesoreria_id=match_tes.id if match_tes else None,
                        conciliado_por_id=usuario.id if estado_c == "CONCILIADO" else None,
                        fecha_conciliacion=datetime.now() if estado_c == "CONCILIADO" else None,
                    )
                )
                procesados += 1

        bd.commit()
        return {
            "flujo": flujo,
            "procesados": procesados,
            "mensaje": f"Se procesaron {procesados} registros correctamente en '{flujo}'.",
        }
    except HTTPException:
        bd.rollback()
        raise
    except Exception as exc:
        bd.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error en importación atómica (cambios revertidos): {exc}",
        ) from exc
