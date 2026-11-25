from __future__ import annotations

import io
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.utils.pdf_branding import dibujar_marca_de_agua


def _estilos_pdf() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle(
            "TekioTituloEF",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15,
            textColor=colors.HexColor("#191818"),
            spaceAfter=4,
        ),
        "sub": ParagraphStyle(
            "TekioSubEF",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=colors.HexColor("#555555"),
            spaceAfter=10,
        ),
        "seccion": ParagraphStyle(
            "TekioSecEF",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            textColor=colors.HexColor("#E85A28"),
            spaceBefore=8,
            spaceAfter=4,
        ),
    }


def _fmt_usd(valor: float) -> str:
    signo = "-" if valor < 0 else ""
    return f"{signo}${abs(valor):,.2f}"


def generar_pdf_pl_escalonado(pl: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
    )
    est = _estilos_pdf()
    elementos: list[Any] = [
        Paragraph("TEKIO ELECTRONICS 2024, C.A. · RIF J-50637518-4", est["sub"]),
        Paragraph("Estado de Resultados (P&L) Escalonado", est["titulo"]),
        Paragraph(
            f"Período: {pl['fecha_inicio']} al {pl['fecha_fin']} · Sucursal: {pl['sucursal']} · Zona horaria: America/Caracas",
            est["sub"],
        ),
    ]

    filas = [
        ["Concepto Contable", "Monto (USD)", "% / Ingresos"],
        ["Ingresos por Ventas de Equipos y Componentes", _fmt_usd(pl["ingresos_equipos_componentes_usd"]), ""],
        ["Ingresos por Servicios Técnicos y Taller", _fmt_usd(pl["ingresos_servicios_usd"]), ""],
        ["INGRESOS NETOS TOTALES", _fmt_usd(pl["ingresos_netos_usd"]), "100.00%"],
        ["(-) Costo de Ventas (incl. flete y componentes taller)", _fmt_usd(-pl["costo_ventas_usd"]), ""],
        ["(=) UTILIDAD BRUTA", _fmt_usd(pl["utilidad_bruta_usd"]), f"{pl['margen_bruto_pct']:.2f}%"],
        ["(-) Comisiones y Gastos de Venta", _fmt_usd(-pl["comisiones_venta_usd"]), ""],
        ["(-) Gastos Operativos Administrativos", _fmt_usd(-pl["gastos_operativos_usd"]), ""],
        ["(-) Gastos de Nómina", _fmt_usd(-pl["gastos_nomina_usd"]), ""],
        ["(=) UTILIDAD OPERATIVA (EBIT)", _fmt_usd(pl["utilidad_operativa_ebit_usd"]), f"{pl['margen_operativo_pct']:.2f}%"],
        ["(+/-) Diferencial Cambiario (Tesorería)", _fmt_usd(pl["diferencial_cambiario_usd"]), ""],
        ["(-) Intereses Financieros de Préstamos", _fmt_usd(-pl["intereses_prestamos_usd"]), ""],
        ["(=) UTILIDAD NETA DEL PERÍODO", _fmt_usd(pl["utilidad_neta_usd"]), f"{pl['margen_neto_pct']:.2f}%"],
    ]

    tabla = Table(filas, colWidths=[11.2 * cm, 3.6 * cm, 3.0 * cm])
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#191818")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#DDDDDD")),
                ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#F6F6F6")),
                ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
                ("BACKGROUND", (0, 5), (-1, 5), colors.HexColor("#FDF0EB")),
                ("FONTNAME", (0, 5), (-1, 5), "Helvetica-Bold"),
                ("BACKGROUND", (0, 9), (-1, 9), colors.HexColor("#F6F6F6")),
                ("FONTNAME", (0, 9), (-1, 9), "Helvetica-Bold"),
                ("BACKGROUND", (0, 12), (-1, 12), colors.HexColor("#E85A28")),
                ("TEXTCOLOR", (0, 12), (-1, 12), colors.white),
                ("FONTNAME", (0, 12), (-1, 12), "Helvetica-Bold"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elementos.append(tabla)
    doc.build(elementos, onFirstPage=dibujar_marca_de_agua, onLaterPages=dibujar_marca_de_agua)
    return buf.getvalue()


def generar_xlsx_pl_escalonado(pl: dict[str, Any]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "PL Escalonado"

    fill_hdr = PatternFill(start_color="191818", end_color="191818", fill_type="solid")
    fill_tot = PatternFill(start_color="FDF0EB", end_color="FDF0EB", fill_type="solid")
    font_hdr = Font(bold=True, color="FFFFFF")
    font_bold = Font(bold=True)

    ws["A1"] = "TEKIO ELECTRONICS 2024, C.A. — Estado de Resultados (P&L) Escalonado"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = f"Período: {pl['fecha_inicio']} al {pl['fecha_fin']} · Sucursal: {pl['sucursal']}"

    headers = ["Concepto", "Monto USD", "% / Ingresos"]
    ws.append([])
    ws.append(headers)
    for col in range(1, 4):
        c = ws.cell(row=4, column=col)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="right" if col > 1 else "left")

    rows = [
        ("Ingresos por Ventas de Equipos y Componentes", pl["ingresos_equipos_componentes_usd"], None, False),
        ("Ingresos por Servicios Técnicos y Taller", pl["ingresos_servicios_usd"], None, False),
        ("INGRESOS NETOS TOTALES", pl["ingresos_netos_usd"], 100.0, True),
        ("(-) Costo de Ventas", -pl["costo_ventas_usd"], None, False),
        ("(=) UTILIDAD BRUTA", pl["utilidad_bruta_usd"], pl["margen_bruto_pct"], True),
        ("(-) Comisiones y Gastos de Venta", -pl["comisiones_venta_usd"], None, False),
        ("(-) Gastos Operativos Administrativos", -pl["gastos_operativos_usd"], None, False),
        ("(-) Gastos de Nómina", -pl["gastos_nomina_usd"], None, False),
        ("(=) UTILIDAD OPERATIVA (EBIT)", pl["utilidad_operativa_ebit_usd"], pl["margen_operativo_pct"], True),
        ("(+/-) Diferencial Cambiario", pl["diferencial_cambiario_usd"], None, False),
        ("(-) Intereses Financieros de Préstamos", -pl["intereses_prestamos_usd"], None, False),
        ("(=) UTILIDAD NETA DEL PERÍODO", pl["utilidad_neta_usd"], pl["margen_neto_pct"], True),
    ]
    for nombre, monto, pct, destacado in rows:
        ws.append([nombre, round(float(monto), 2), f"{pct:.2f}%" if pct is not None else ""])
        r = ws.max_row
        ws.cell(row=r, column=2).number_format = "$#,##0.00;-$#,##0.00"
        if destacado:
            for col in range(1, 4):
                ws.cell(row=r, column=col).font = font_bold
                ws.cell(row=r, column=col).fill = fill_tot

    ws.column_dimensions["A"].width = 48
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 16
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def generar_pdf_balance_general(bal: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
    )
    est = _estilos_pdf()
    estado_cuadre = "CUADRADO EXACTO (A = P + Pat)" if bal["cuadrado"] else f"DESCUADRE: {_fmt_usd(bal['diferencia_cuadre_usd'])}"
    elementos: list[Any] = [
        Paragraph("TEKIO ELECTRONICS 2024, C.A. · RIF J-50637518-4", est["sub"]),
        Paragraph("Balance General (Estado de Situación Financiera)", est["titulo"]),
        Paragraph(
            f"Fecha de corte: {bal['fecha_corte']} · Estado: {estado_cuadre} · Zona horaria: America/Caracas",
            est["sub"],
        ),
    ]

    act = bal["activos"]
    pas = bal["pasivos"]
    pat = bal["patrimonio"]

    filas = [
        ["ACTIVOS", "Monto (USD)"],
        ["Caja y Bancos (Equivalente USD)", _fmt_usd(act["cajas_bancos_usd"])],
        ["Cuentas por Cobrar Clientes", _fmt_usd(act["cxc_clientes_usd"])],
        ["Cashea por Cobrar", _fmt_usd(act["cashea_por_cobrar_usd"])],
        ["Inventario de Equipos (Costo Total)", _fmt_usd(act["inventario_equipos_usd"])],
        ["Inventario de Componentes", _fmt_usd(act["inventario_componentes_usd"])],
        ["TOTAL ACTIVOS", _fmt_usd(act["total_activos_usd"])],
        ["PASIVOS", ""],
        ["Cuentas por Pagar Proveedores", _fmt_usd(pas["cxp_proveedores_usd"])],
        ["Préstamos por Pagar (Capital Pendiente)", _fmt_usd(pas["prestamos_por_pagar_usd"])],
        ["Obligaciones Fiscales por Pagar", _fmt_usd(pas["obligaciones_fiscales_usd"])],
        ["TOTAL PASIVOS", _fmt_usd(pas["total_pasivos_usd"])],
        ["PATRIMONIO", ""],
        ["Capital Social y Resultados Acumulados", _fmt_usd(pat["capital_social_y_reservas_usd"])],
        ["Resultado del Ejercicio (YTD)", _fmt_usd(pat["resultado_ejercicio_usd"])],
        ["TOTAL PATRIMONIO", _fmt_usd(pat["total_patrimonio_usd"])],
        ["TOTAL PASIVOS + PATRIMONIO", _fmt_usd(bal["total_pasivo_mas_patrimonio_usd"])],
    ]

    tabla = Table(filas, colWidths=[13.2 * cm, 4.6 * cm])
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#191818")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BACKGROUND", (0, 6), (-1, 6), colors.HexColor("#FDF0EB")),
                ("FONTNAME", (0, 6), (-1, 6), "Helvetica-Bold"),
                ("BACKGROUND", (0, 7), (-1, 7), colors.HexColor("#191818")),
                ("TEXTCOLOR", (0, 7), (-1, 7), colors.white),
                ("FONTNAME", (0, 7), (-1, 7), "Helvetica-Bold"),
                ("BACKGROUND", (0, 11), (-1, 11), colors.HexColor("#F6F6F6")),
                ("FONTNAME", (0, 11), (-1, 11), "Helvetica-Bold"),
                ("BACKGROUND", (0, 12), (-1, 12), colors.HexColor("#191818")),
                ("TEXTCOLOR", (0, 12), (-1, 12), colors.white),
                ("FONTNAME", (0, 12), (-1, 12), "Helvetica-Bold"),
                ("BACKGROUND", (0, 15), (-1, 15), colors.HexColor("#F6F6F6")),
                ("FONTNAME", (0, 15), (-1, 15), "Helvetica-Bold"),
                ("BACKGROUND", (0, 16), (-1, 16), colors.HexColor("#E85A28")),
                ("TEXTCOLOR", (0, 16), (-1, 16), colors.white),
                ("FONTNAME", (0, 16), (-1, 16), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#DDDDDD")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    elementos.append(Spacer(1, 0.2 * cm))
    elementos.append(tabla)
    doc.build(elementos, onFirstPage=dibujar_marca_de_agua, onLaterPages=dibujar_marca_de_agua)
    return buf.getvalue()


def generar_xlsx_balance_general(bal: dict[str, Any]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Balance General"

    fill_hdr = PatternFill(start_color="191818", end_color="191818", fill_type="solid")
    fill_tot = PatternFill(start_color="FDF0EB", end_color="FDF0EB", fill_type="solid")
    font_hdr = Font(bold=True, color="FFFFFF")
    font_bold = Font(bold=True)

    ws["A1"] = "TEKIO ELECTRONICS 2024, C.A. — Balance General"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = f"Fecha de corte: {bal['fecha_corte']} · Cuadrado: {'SÍ' if bal['cuadrado'] else 'NO'}"

    act = bal["activos"]
    pas = bal["pasivos"]
    pat = bal["patrimonio"]

    ws.append([])
    ws.append(["Cuenta / Rubro", "Monto USD"])
    for col in range(1, 3):
        c = ws.cell(row=4, column=col)
        c.fill = fill_hdr
        c.font = font_hdr

    filas = [
        ("Caja y Bancos", act["cajas_bancos_usd"], False),
        ("Cuentas por Cobrar Clientes", act["cxc_clientes_usd"], False),
        ("Cashea por Cobrar", act["cashea_por_cobrar_usd"], False),
        ("Inventario de Equipos", act["inventario_equipos_usd"], False),
        ("Inventario de Componentes", act["inventario_componentes_usd"], False),
        ("TOTAL ACTIVOS", act["total_activos_usd"], True),
        ("Cuentas por Pagar Proveedores", pas["cxp_proveedores_usd"], False),
        ("Préstamos por Pagar", pas["prestamos_por_pagar_usd"], False),
        ("Obligaciones Fiscales por Pagar", pas["obligaciones_fiscales_usd"], False),
        ("TOTAL PASIVOS", pas["total_pasivos_usd"], True),
        ("Capital Social y Resultados Acumulados", pat["capital_social_y_reservas_usd"], False),
        ("Resultado del Ejercicio (YTD)", pat["resultado_ejercicio_usd"], False),
        ("TOTAL PATRIMONIO", pat["total_patrimonio_usd"], True),
        ("TOTAL PASIVOS + PATRIMONIO", bal["total_pasivo_mas_patrimonio_usd"], True),
    ]
    for nombre, monto, dest in filas:
        ws.append([nombre, round(float(monto), 2)])
        r = ws.max_row
        ws.cell(row=r, column=2).number_format = "$#,##0.00;-$#,##0.00"
        if dest:
            for col in range(1, 3):
                ws.cell(row=r, column=col).font = font_bold
                ws.cell(row=r, column=col).fill = fill_tot

    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 20
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def generar_plantilla_apertura_xlsx(tipo: str) -> bytes:
    """
    Genera plantillas Excel (.xlsx) oficiales de carga inicial de apertura para Tekio Electronics:
    - saldos_iniciales (incluyendo Caja Chica $60 USD por sucursal + bancos/billeteras contra Capital Inicial)
    - inventario_inicial (equipos por serial + componentes/accesorios)
    - cxc_cxp_iniciales (CxC/Cashea pendiente + CxP proveedores con vencimientos)
    """
    wb = Workbook()
    fill_hdr = PatternFill(start_color="191818", end_color="191818", fill_type="solid")
    fill_sub = PatternFill(start_color="FDF0EB", end_color="FDF0EB", fill_type="solid")
    font_hdr = Font(bold=True, color="FFFFFF")
    font_note = Font(italic=True, color="555555")

    if tipo == "saldos_iniciales":
        ws = wb.active
        ws.title = "Saldos Cajas y Bancos"
        ws["A1"] = "TEKIO ELECTRONICS — Plantilla de Saldos Iniciales de Cajas y Bancos"
        ws["A1"].font = Font(bold=True, size=12)
        ws["A2"] = "Contrapartida automática: 3.1.01 Capital Inicial (Impacto $0.00 en Estado de Resultados P&L)"
        ws["A2"].font = font_note
        headers = [
            "instrumento",
            "sucursal",
            "moneda",
            "saldo_inicial_origen",
            "tasa_referencia_bcv",
            "cuenta_contrapartida",
            "nota",
        ]
        ws.append([])
        ws.append(headers)
        for col in range(1, len(headers) + 1):
            c = ws.cell(row=4, column=col)
            c.fill = fill_hdr
            c.font = font_hdr

        ejemplos = [
            ["Efectivo USD Tienda", "Tekio central", "USD", 500.00, 1.00, "3.1.01 - Capital Inicial", "Saldo inicial caja principal"],
            ["Efectivo USD Tienda", "Gran Bazar", "USD", 350.00, 1.00, "3.1.01 - Capital Inicial", "Saldo inicial caja principal"],
            ["Caja Chica USD", "Tekio central", "USD", 60.00, 1.00, "3.1.01 - Capital Inicial", "Fondo fijo caja chica $60 USD"],
            ["Caja Chica USD", "Gran Bazar", "USD", 60.00, 1.00, "3.1.01 - Capital Inicial", "Fondo fijo caja chica $60 USD"],
            ["Zelle", "General", "USD", 2500.00, 1.00, "3.1.01 - Capital Inicial", "Saldo inicial cuenta Zelle"],
            ["Binance USDT", "General", "USDT", 1800.00, 1.00, "3.1.01 - Capital Inicial", "Saldo inicial billetera USDT"],
            ["Banco Mercantil Bs", "General", "BS", 45000.00, 45.00, "3.1.01 - Capital Inicial", "Saldo inicial banco en Bs"],
            ["Pago Móvil Bs", "General", "BS", 12000.00, 45.00, "3.1.01 - Capital Inicial", "Saldo inicial Pago Móvil"],
        ]
        for fila in ejemplos:
            ws.append(fila)
            r = ws.max_row
            if "Caja Chica" in fila[0]:
                for col in range(1, len(headers) + 1):
                    ws.cell(row=r, column=col).fill = fill_sub

        for idx, ancho in enumerate([24, 18, 10, 20, 18, 28, 34], start=1):
            ws.column_dimensions[chr(64 + idx)].width = ancho

    elif tipo == "inventario_inicial":
        ws = wb.active
        ws.title = "Equipos por Serial"
        headers_eq = [
            "serial",
            "sku",
            "modelo",
            "configuracion",
            "categoria",
            "sucursal",
            "estado",
            "costo_compra_usd",
            "costo_flete_usd",
            "costo_taller_usd",
            "precio_promo_usd",
        ]
        ws.append(headers_eq)
        for col in range(1, len(headers_eq) + 1):
            c = ws.cell(row=1, column=col)
            c.fill = fill_hdr
            c.font = font_hdr
        ws.append(["SN-APE-0001", "LAP-LEN-T14", "Lenovo ThinkPad T14", "Core i5 / 16GB / 512GB", "Laptop", "Tekio central", "LISTO", 220.00, 25.00, 0.00, 390.00])
        ws.append(["SN-APE-0002", "LAP-DELL-5420", "Dell Latitude 5420", "Core i5 / 8GB / 256GB", "Laptop", "Bodega", "POR_PREPARAR", 190.00, 20.00, 0.00, 340.00])
        for idx in range(1, len(headers_eq) + 1):
            ws.column_dimensions[chr(64 + idx)].width = 20

        ws2 = wb.create_sheet(title="Componentes y Accesorios")
        headers_comp = ["sku", "descripcion", "tipo", "sucursal", "cantidad", "costo_unitario_usd", "precio_promo_usd"]
        ws2.append(headers_comp)
        for col in range(1, len(headers_comp) + 1):
            c = ws2.cell(row=1, column=col)
            c.fill = fill_hdr
            c.font = font_hdr
        ws2.append(["RAM-8GB-DDR4", "Memoria RAM 8GB DDR4", "COMPONENTE", "Bodega", 10, 18.00, 35.00])
        ws2.append(["SSD-512-NVME", "SSD 512GB NVMe", "COMPONENTE", "Bodega", 8, 28.00, 50.00])
        for idx in range(1, len(headers_comp) + 1):
            ws2.column_dimensions[chr(64 + idx)].width = 22

    elif tipo == "cxc_cxp_iniciales":
        ws = wb.active
        ws.title = "CxC y Cashea Pendiente"
        headers_cxc = ["tipo", "cliente", "documento_ref", "fecha_emision", "fecha_vencimiento", "saldo_pendiente_usd", "nota"]
        ws.append(headers_cxc)
        for col in range(1, len(headers_cxc) + 1):
            c = ws.cell(row=1, column=col)
            c.fill = fill_hdr
            c.font = font_hdr
        ws.append(["CASHEA", "Cliente Ejemplo 1", "N-0100", "2026-11-15", "2026-11-30", 240.00, "Cuota pendiente Cashea"])
        ws.append(["CLIENTE", "Empresa Ejemplo CA", "N-0101", "2026-11-10", "2026-12-10", 150.00, "Saldo crédito cliente"])
        for idx in range(1, len(headers_cxc) + 1):
            ws.column_dimensions[chr(64 + idx)].width = 22

        ws2 = wb.create_sheet(title="CxP Proveedores")
        headers_cxp = ["proveedor", "factura_ref", "origen", "fecha_emision", "fecha_vencimiento", "saldo_pendiente_usd", "nota"]
        ws2.append(headers_cxp)
        for col in range(1, len(headers_cxp) + 1):
            c = ws2.cell(row=1, column=col)
            c.fill = fill_hdr
            c.font = font_hdr
        ws2.append(["Miami Tech Wholesale", "INV-MIA-900", "INTERNACIONAL", "2026-11-01", "2026-12-01", 1200.00, "Saldo proveedor exterior"])
        for idx in range(1, len(headers_cxp) + 1):
            ws2.column_dimensions[chr(64 + idx)].width = 22
    else:
        raise ValueError("Tipo de plantilla de apertura no soportado.")

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
