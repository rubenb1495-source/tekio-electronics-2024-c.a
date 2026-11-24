from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from app.modelos_finanzas import Venta


def generar_pdf_nota_entrega(venta: Venta) -> bytes:
    """Genera el PDF tamaño carta de la Nota de Entrega de TEKIO ELECTRONICS 2024, C.A."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    ancho, alto = letter

    # Encabezado corporativo
    pdf.setFillColorRGB(0.91, 0.35, 0.16)  # Naranja Tekio (#E85A28)
    pdf.rect(0, alto - 1.15 * inch, ancho, 1.15 * inch, fill=1, stroke=0)

    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(0.6 * inch, alto - 0.55 * inch, "TEKIO ELECTRONICS 2024, C.A.")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(0.6 * inch, alto - 0.80 * inch, "RIF: J-50637518-4 · Valencia, Edo. Carabobo, Venezuela")
    pdf.drawString(0.6 * inch, alto - 0.98 * inch, "Tecnología con criterio · WhatsApp: +58 424-4152658")

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawRightString(ancho - 0.6 * inch, alto - 0.55 * inch, f"NOTA DE ENTREGA")
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawRightString(ancho - 0.6 * inch, alto - 0.80 * inch, f"Nro: {venta.numero_venta}")
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(ancho - 0.6 * inch, alto - 0.98 * inch, f"Fecha: {venta.fecha.isoformat()}")

    # Datos de la operación
    y = alto - 1.55 * inch
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica-Bold", 10)
    cliente_nombre = venta.cliente.nombre if venta.cliente else "Cliente general"
    cliente_rif = venta.cliente.rif_cedula if venta.cliente and venta.cliente.rif_cedula else "N/A"
    sucursal_nombre = venta.sucursal.nombre if venta.sucursal else "Tekio central"
    asesor_nombre = venta.asesor.nombre if venta.asesor else "Tienda"

    pdf.drawString(0.6 * inch, y, f"Cliente: {cliente_nombre}")
    pdf.drawRightString(ancho - 0.6 * inch, y, f"RIF / Cédula: {cliente_rif}")
    y -= 16
    pdf.setFont("Helvetica", 9.5)
    pdf.drawString(0.6 * inch, y, f"Sucursal: {sucursal_nombre} · Entrega: {venta.tipo_entrega}")
    pdf.drawRightString(ancho - 0.6 * inch, y, f"Asesor: {asesor_nombre} · Estado: {venta.estado}")

    # Tabla de artículos
    y -= 28
    pdf.setFillColorRGB(0.95, 0.96, 0.97)
    pdf.rect(0.6 * inch, y - 4, ancho - 1.2 * inch, 20, fill=1, stroke=0)
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(0.7 * inch, y + 3, "Cant.")
    pdf.drawString(1.2 * inch, y + 3, "Descripción / Serial")
    pdf.drawRightString(ancho - 1.7 * inch, y + 3, "Promo USD")
    pdf.drawRightString(ancho - 0.7 * inch, y + 3, "Regular USD")

    y -= 20
    pdf.setFont("Helvetica", 9)
    for det in venta.detalles:
        serial_txt = f" [Serial: {det.equipo.serial}]" if det.equipo else ""
        desc = f"{det.descripcion}{serial_txt}"[:68]
        pdf.drawString(0.7 * inch, y, str(det.cantidad))
        pdf.drawString(1.2 * inch, y, desc)
        pdf.drawRightString(ancho - 1.7 * inch, y, f"${float(det.precio_promo_usd):,.2f}")
        pdf.drawRightString(ancho - 0.7 * inch, y, f"${float(det.precio_regular_usd):,.2f}")
        y -= 16

    # Línea separadora y totales
    y -= 8
    pdf.setStrokeColor(colors.grey)
    pdf.line(0.6 * inch, y, ancho - 0.6 * inch, y)
    y -= 18
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawRightString(ancho - 0.7 * inch, y, f"Total Promo USD: ${float(venta.total_promo_usd):,.2f}")
    y -= 15
    pdf.drawRightString(ancho - 0.7 * inch, y, f"Total Regular USD: ${float(venta.total_regular_usd):,.2f}")

    # Pagos recibidos
    y -= 26
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawString(0.6 * inch, y, "Detalle de pagos registrados:")
    y -= 14
    pdf.setFont("Helvetica", 9)
    for p in venta.pagos:
        if p.anulado:
            continue
        inst_nombre = p.instrumento.nombre if p.instrumento else "Pago"
        ref = f" · Ref: {p.referencia}" if p.referencia else ""
        pdf.drawString(
            0.7 * inch,
            y,
            f"- {inst_nombre}: {float(p.monto_moneda_origen):,.2f} {p.moneda}{ref}",
        )
        y -= 14

    # Cláusula de garantía 180 días
    y_garantia = 1.45 * inch
    pdf.setStrokeColorRGB(0.91, 0.35, 0.16)
    pdf.rect(0.6 * inch, y_garantia - 0.65 * inch, ancho - 1.2 * inch, 0.85 * inch, fill=0, stroke=1)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(0.75 * inch, y_garantia + 4, "CONDICIONES DE GARANTÍA (180 DÍAS)")
    pdf.setFont("Helvetica", 8)
    pdf.drawString(
        0.75 * inch,
        y_garantia - 12,
        "1. Todos los equipos cuentan con garantía de 180 días por defectos de fábrica presentando esta Nota de Entrega.",
    )
    pdf.drawString(
        0.75 * inch,
        y_garantia - 24,
        "2. La garantía no cubre golpes, humedad, descargas eléctricas ni manipulación por terceros no autorizados.",
    )
    pdf.drawString(
        0.75 * inch,
        y_garantia - 36,
        "3. Para hacer efectiva la garantía el serial del equipo debe coincidir exactamente con el registrado en este documento.",
    )

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
