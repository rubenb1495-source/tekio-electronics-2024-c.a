from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from app.modelos_finanzas import Venta


def _envolver_texto(texto: str, max_chars: int) -> list[str]:
    palabras = texto.split()
    lineas: list[str] = []
    actual = ""
    for palabra in palabras:
        candidata = f"{actual} {palabra}".strip()
        if len(candidata) <= max_chars:
            actual = candidata
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def generar_pdf_nota_entrega(venta: Venta) -> bytes:
    """Genera el PDF tamaño carta de la Nota de Entrega de TEKIO ELECTRONICS 2024, C.A."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    ancho, alto = letter

    # Encabezado corporativo
    pdf.setFillColorRGB(0.91, 0.35, 0.16)  # Naranja Tekio (#E85A28)
    pdf.rect(0, alto - 1.10 * inch, ancho, 1.10 * inch, fill=1, stroke=0)

    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(0.55 * inch, alto - 0.50 * inch, "TEKIO ELECTRONICS 2024, C.A.")
    pdf.setFont("Helvetica", 9.5)
    pdf.drawString(0.55 * inch, alto - 0.74 * inch, "RIF: J-50637518-4 · Valencia, Edo. Carabobo, Venezuela")
    pdf.drawString(0.55 * inch, alto - 0.92 * inch, "Tecnología con criterio · WhatsApp: +58 424-4152658")

    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawRightString(ancho - 0.55 * inch, alto - 0.50 * inch, "NOTA DE ENTREGA")
    pdf.setFont("Helvetica-Bold", 11.5)
    pdf.drawRightString(ancho - 0.55 * inch, alto - 0.74 * inch, f"Nro: {venta.numero_venta}")
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(ancho - 0.55 * inch, alto - 0.92 * inch, f"Fecha: {venta.fecha.isoformat()}")

    # Datos de la operación
    y = alto - 1.42 * inch
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica-Bold", 9.5)
    cliente_nombre = venta.cliente.nombre if venta.cliente else "Cliente general"
    cliente_rif = venta.cliente.rif_cedula if venta.cliente and venta.cliente.rif_cedula else "N/A"
    cliente_tel = venta.cliente.telefono if venta.cliente and venta.cliente.telefono else ""
    sucursal_nombre = venta.sucursal.nombre if venta.sucursal else "Tekio central"
    asesor_nombre = venta.asesor.nombre if venta.asesor else "Tienda"
    tecnico_nombre = venta.tecnico.nombre if venta.tecnico else None

    pdf.drawString(0.55 * inch, y, f"Cliente: {cliente_nombre}")
    pdf.drawRightString(
        ancho - 0.55 * inch,
        y,
        f"RIF / C.I.: {cliente_rif}" + (f" · Tel: {cliente_tel}" if cliente_tel else ""),
    )
    y -= 15
    pdf.setFont("Helvetica", 9)
    pdf.drawString(0.55 * inch, y, f"Sucursal: {sucursal_nombre} · Entrega: {venta.tipo_entrega}")
    pdf.drawRightString(ancho - 0.55 * inch, y, f"Asesor: {asesor_nombre} · Estado: {venta.estado}")
    if tecnico_nombre:
        y -= 13
        pdf.drawString(0.55 * inch, y, f"Técnico responsable: {tecnico_nombre}")

    # Tabla de artículos
    y -= 24
    pdf.setFillColorRGB(0.95, 0.96, 0.97)
    pdf.rect(0.55 * inch, y - 4, ancho - 1.10 * inch, 19, fill=1, stroke=0)
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica-Bold", 8.5)
    pdf.drawString(0.65 * inch, y + 3, "Cant.")
    pdf.drawString(1.10 * inch, y + 3, "Descripción / Serial")
    pdf.drawRightString(ancho - 1.65 * inch, y + 3, "Promo USD")
    pdf.drawRightString(ancho - 0.65 * inch, y + 3, "Regular USD")

    y -= 18
    pdf.setFont("Helvetica", 8.5)
    for det in venta.detalles:
        serial_txt = f" [Serial: {det.equipo.serial}]" if det.equipo else ""
        es_obsequio = float(det.precio_promo_usd) == 0.0 and float(det.precio_regular_usd) == 0.0
        etiqueta_obs = " [OBSEQUIO]" if es_obsequio else ""
        desc = f"{det.descripcion}{serial_txt}{etiqueta_obs}"[:68]
        pdf.drawString(0.65 * inch, y, str(det.cantidad))
        pdf.drawString(1.10 * inch, y, desc)
        if es_obsequio:
            pdf.drawRightString(ancho - 1.65 * inch, y, "OBSEQUIO ($0.00)")
            pdf.drawRightString(ancho - 0.65 * inch, y, "$0.00")
        else:
            pdf.drawRightString(ancho - 1.65 * inch, y, f"${float(det.precio_promo_usd):,.2f}")
            pdf.drawRightString(ancho - 0.65 * inch, y, f"${float(det.precio_regular_usd):,.2f}")
        y -= 14
        desc_srv = (getattr(det, "descripcion_servicio", "") or "").strip()
        if desc_srv:
            pdf.setFont("Helvetica-Oblique", 7.8)
            pdf.setFillColorRGB(0.3, 0.35, 0.4)
            for linea in _envolver_texto(f"Trabajo realizado: {desc_srv}", 76):
                pdf.drawString(1.20 * inch, y, linea)
                y -= 10
            pdf.setFillColor(colors.black)
            pdf.setFont("Helvetica", 8.5)

    # Línea separadora y totales
    y -= 6
    pdf.setStrokeColor(colors.grey)
    pdf.line(0.55 * inch, y, ancho - 0.55 * inch, y)
    y -= 16
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawRightString(ancho - 0.65 * inch, y, f"Total Promo USD: ${float(venta.total_promo_usd):,.2f}")
    y -= 14
    pdf.drawRightString(ancho - 0.65 * inch, y, f"Total Regular USD: ${float(venta.total_regular_usd):,.2f}")

    # Pagos recibidos
    y -= 20
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(0.55 * inch, y, "Detalle de pagos registrados:")
    y -= 13
    pdf.setFont("Helvetica", 8.5)
    for p in venta.pagos:
        if p.anulado:
            continue
        inst_nombre = p.instrumento.nombre if p.instrumento else "Pago"
        ref = f" · Ref: {p.referencia}" if p.referencia else ""
        pdf.drawString(
            0.65 * inch,
            y,
            f"- {inst_nombre}: {float(p.monto_moneda_origen):,.2f} {p.moneda}{ref}",
        )
        y -= 12

    if venta.nota:
        y -= 6
        pdf.setFont("Helvetica-Oblique", 8)
        for linea in _envolver_texto(f"Nota: {venta.nota}", 95)[:2]:
            pdf.drawString(0.55 * inch, y, linea)
            y -= 10

    # Bloque formal de Políticas y Condiciones de Garantía al pie
    y_caja_top = 2.85 * inch
    y_caja_bottom = 0.95 * inch
    pdf.setStrokeColorRGB(0.91, 0.35, 0.16)
    pdf.setLineWidth(0.9)
    pdf.rect(0.55 * inch, y_caja_bottom, ancho - 1.10 * inch, y_caja_top - y_caja_bottom, fill=0, stroke=1)

    y_g = y_caja_top - 13
    pdf.setFillColorRGB(0.91, 0.35, 0.16)
    pdf.setFont("Helvetica-Bold", 8.5)
    pdf.drawString(
        0.68 * inch,
        y_g,
        "POLÍTICAS Y CONDICIONES DE GARANTÍA — TEKIO ELECTRONICS 2024, C.A. (RIF: J-50637518-4)",
    )
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica", 7.3)
    y_g -= 11

    clausulas = [
        (
            "1. Cobertura (180 días): Los equipos (laptops/computadores) cuentan con garantía de 180 días "
            "continuos a partir de la fecha de emisión de esta nota, cubriendo únicamente defectos de hardware "
            "de fábrica o funcionamiento."
        ),
        (
            "2. Exclusiones expresas: No cubre daños físicos (golpes, caídas, pantallas partidas, bisagras rotas), "
            "derrame de líquidos, fluctuaciones eléctricas/cortocircuitos, manipulación o apertura por personal ajeno "
            "a Tekio Electronics, sellos de garantía rotos, ni fallas de software, sistema operativo o virus."
        ),
        (
            "3. Accesorios, obsequios y servicios técnicos (ST): Cargadores, baterías y accesorios entregados como "
            "obsequio ($0.00) no tienen cambio ni cobertura extendida (salvo condición expresa en esta nota). En "
            "servicios técnicos (ST), la garantía aplica exclusivamente sobre el trabajo realizado y el repuesto "
            "instalado descrito en este documento."
        ),
        (
            "4. Requisitos de validez: Es indispensable presentar esta Nota de Entrega original o digital y verificar "
            "la coincidencia exacta del serial único del equipo registrado en este documento."
        ),
    ]

    for clausula in clausulas:
        for linea in _envolver_texto(clausula, 108):
            pdf.drawString(0.68 * inch, y_g, linea)
            y_g -= 9.5
        y_g -= 2.5

    # Líneas de firma al pie de página
    y_firma = 0.55 * inch
    pdf.setStrokeColor(colors.grey)
    pdf.setLineWidth(0.7)
    pdf.line(0.85 * inch, y_firma, 3.35 * inch, y_firma)
    pdf.line(ancho - 3.35 * inch, y_firma, ancho - 0.85 * inch, y_firma)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.setFillColor(colors.black)
    pdf.drawCentredString(2.10 * inch, y_firma - 11, "Entregado por (Tekio Electronics)")
    pdf.drawCentredString(ancho - 2.10 * inch, y_firma - 11, "Recibido conforme (Cliente / C.I.)")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
