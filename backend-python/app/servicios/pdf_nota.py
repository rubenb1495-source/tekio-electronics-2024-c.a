from __future__ import annotations

import io
import json
from decimal import Decimal
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from app.modelos_finanzas import MonedaInstrumento, TipoPrecioInstrumento, Venta


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


def _es_venta_regular(venta: Venta) -> bool:
    """Determina si la venta fue cobrada a precio regular (Bs, mixta con Bs o Cashea)."""
    for p in venta.pagos:
        if p.anulado:
            continue
        inst = p.instrumento
        nombre_inst = (inst.nombre if inst else "").lower()
        if (
            p.moneda == MonedaInstrumento.BS.value
            or "cashea" in nombre_inst
            or (inst is not None and inst.tipo_precio == TipoPrecioInstrumento.REGULAR.value)
        ):
            return True
    return False


def _obtener_datos_cliente(venta: Venta) -> tuple[str, str, str, str, str]:
    """Devuelve (nombre, etiqueta_doc, valor_doc, telefono, direccion)."""
    cli = venta.cliente
    if cli is None:
        return "Cliente general", "Cédula de Identidad", "N/A", "", ""
    es_juridico = (getattr(cli, "tipo_persona", "NATURAL") or "NATURAL").upper() == "JURIDICO"
    etiqueta_doc = "RIF" if es_juridico else "Cédula de Identidad"
    if getattr(cli, "tipo_documento", "") and getattr(cli, "documento", ""):
        valor_doc = f"{cli.tipo_documento}-{cli.documento}"
    else:
        valor_doc = cli.rif_cedula or "N/A"
    return (
        cli.nombre,
        etiqueta_doc,
        valor_doc,
        cli.telefono or "",
        getattr(cli, "direccion", "") or "",
    )


def _dibujar_isotipo_tekio(pdf: canvas.Canvas, x: float, y_base: float, escala: float = 0.48) -> None:
    """Dibuja el isotipo vectorial oficial de 3 flechas convergentes en Naranja Tekio (#E85A28)."""
    pdf.saveState()
    pdf.setFillColorRGB(0.91, 0.35, 0.16)  # #E85A28
    pdf.translate(x, y_base)
    pdf.scale(escala, escala)

    # Flecha izquierda apuntando al centro
    p1 = pdf.beginPath()
    p1.moveTo(8, 46.5)
    p1.lineTo(28.5, 32)
    p1.lineTo(8, 17.5)
    p1.lineTo(8, 26.2)
    p1.lineTo(16.2, 32)
    p1.lineTo(8, 37.8)
    p1.close()
    pdf.drawPath(p1, stroke=0, fill=1)

    # Flecha superior apuntando al centro
    p2 = pdf.beginPath()
    p2.moveTo(32, 56.5)
    p2.lineTo(46.5, 36)
    p2.lineTo(37.8, 36)
    p2.lineTo(32, 44.2)
    p2.lineTo(26.2, 36)
    p2.lineTo(17.5, 36)
    p2.close()
    pdf.drawPath(p2, stroke=0, fill=1)

    # Flecha derecha apuntando al centro
    p3 = pdf.beginPath()
    p3.moveTo(56, 46.5)
    p3.lineTo(56, 37.8)
    p3.lineTo(47.8, 32)
    p3.lineTo(56, 26.2)
    p3.lineTo(56, 17.5)
    p3.lineTo(35.5, 32)
    p3.close()
    pdf.drawPath(p3, stroke=0, fill=1)

    pdf.restoreState()


def _dibujar_encabezado(pdf: canvas.Canvas, ancho: float, alto: float, venta: Venta, pagina: int = 1) -> float:
    # Franja superior en Naranja Tekio (#E85A28)
    pdf.setFillColorRGB(0.91, 0.35, 0.16)
    pdf.rect(0, alto - 0.10 * inch, ancho, 0.10 * inch, fill=1, stroke=0)

    # Isotipo vectorial limpio a la izquierda
    _dibujar_isotipo_tekio(pdf, 0.48 * inch, alto - 0.84 * inch, escala=0.52)

    # Nombre de la empresa y RIF en Carbón Tekio (#191818)
    pdf.setFillColorRGB(0.098, 0.094, 0.094)  # #191818
    pdf.setFont("Helvetica-Bold", 14.5)
    pdf.drawString(1.02 * inch, alto - 0.42 * inch, "TEKIO ELECTRONICS 2024, C.A.")
    pdf.setFont("Helvetica-Bold", 8.5)
    pdf.drawString(1.02 * inch, alto - 0.60 * inch, "RIF: J-50637518-4 · Valencia, Edo. Carabobo, Venezuela")
    pdf.setFillColorRGB(0.38, 0.38, 0.38)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(1.02 * inch, alto - 0.76 * inch, "Somos tu solución · WhatsApp: +58 424-4152658")

    # Bloque derecho: Nota de Entrega
    sufijo_pag = f" (Pág. {pagina})" if pagina > 1 else ""
    pdf.setFillColorRGB(0.91, 0.35, 0.16)  # #E85A28
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawRightString(ancho - 0.50 * inch, alto - 0.42 * inch, f"NOTA DE ENTREGA{sufijo_pag}")
    pdf.setFillColorRGB(0.098, 0.094, 0.094)  # #191818
    pdf.setFont("Helvetica-Bold", 10.5)
    pdf.drawRightString(ancho - 0.50 * inch, alto - 0.60 * inch, f"Nro: {venta.numero_venta}")
    pdf.setFont("Helvetica", 8.5)
    pdf.drawRightString(ancho - 0.50 * inch, alto - 0.76 * inch, f"Fecha: {venta.fecha.isoformat()}")

    # Línea divisoria sutil
    pdf.setStrokeColorRGB(0.898, 0.906, 0.922)  # #E5E7EB
    pdf.setLineWidth(0.8)
    pdf.line(0.50 * inch, alto - 0.94 * inch, ancho - 0.50 * inch, alto - 0.94 * inch)

    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    return alto - 1.18 * inch


def _parsear_datos_entrega(venta: Venta) -> dict[str, Any] | None:
    raw = getattr(venta, "datos_entrega_json", "") or ""
    if not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) and any(str(v or "").strip() for v in parsed.values()) else None
    except Exception:
        return None


def _dibujar_bloque_entrega(
    pdf: canvas.Canvas, ancho: float, y: float, tipo_entrega: str, datos: dict[str, Any]
) -> float:
    es_envio = "env" in tipo_entrega.lower()
    titulo = "DATOS DE ENVÍO NACIONAL (ENCOMIENDA)" if es_envio else "DATOS DE DELIVERY"
    pares: list[tuple[str, str]] = []
    if es_envio:
        campos = [
            ("Destinatario", datos.get("destinatario")),
            ("Cédula de Identidad", datos.get("cedula")),
            ("Teléfono", datos.get("telefono")),
            ("Empresa de envío", datos.get("empresa_envio")),
            ("Estado / Ciudad", datos.get("estado_ciudad")),
            ("Agencia / Oficina", datos.get("agencia_oficina")),
            ("Dirección de oficina", datos.get("direccion_oficina")),
            ("Modalidad", datos.get("modalidad")),
        ]
    else:
        campos = [
            ("Recibe", datos.get("nombre_recibe")),
            ("Teléfono", datos.get("telefono")),
            ("Zona / Municipio", datos.get("zona_municipio")),
            ("Dirección de entrega", datos.get("direccion")),
            ("Punto de referencia", datos.get("punto_referencia")),
            ("Horario / Instrucciones", datos.get("horario_instrucciones")),
        ]

    for etiqueta, val in campos:
        texto_val = str(val or "").strip()
        if texto_val:
            pares.append((etiqueta, texto_val))
    if not pares:
        return y

    lineas_texto: list[str] = []
    for etiqueta, val in pares:
        lineas_texto.extend(_envolver_texto(f"{etiqueta}: {val}", 104))

    alto_caja = 18 + len(lineas_texto) * 10 + 6
    y_bottom = y - alto_caja
    pdf.setFillColorRGB(0.98, 0.98, 0.99)
    pdf.setStrokeColorRGB(0.82, 0.84, 0.87)
    pdf.setLineWidth(0.7)
    pdf.rect(0.50 * inch, y_bottom, ancho - 1.00 * inch, alto_caja, fill=1, stroke=1)

    y_cursor = y - 12
    pdf.setFillColorRGB(0.91, 0.35, 0.16)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(0.62 * inch, y_cursor, titulo)
    y_cursor -= 11
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica", 7.8)
    for linea in lineas_texto:
        pdf.drawString(0.62 * inch, y_cursor, linea)
        y_cursor -= 10
    return y_bottom - 10


def generar_pdf_nota_entrega(venta: Venta) -> bytes:
    """Genera el PDF tamaño carta de la Nota de Entrega oficial de TEKIO ELECTRONICS 2024, C.A."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    ancho, alto = letter

    es_regular = _es_venta_regular(venta)
    tasa_bcv = float(venta.tasa_bcv_snapshot or Decimal("0"))
    cli_nombre, cli_etiqueta_doc, cli_doc, cli_tel, cli_dir = _obtener_datos_cliente(venta)
    sucursal_nombre = venta.sucursal.nombre if venta.sucursal else "Tekio central"
    asesor_nombre = venta.asesor.nombre if venta.asesor else "Tienda"
    tecnico_nombre = venta.tecnico.nombre if venta.tecnico else None

    y = _dibujar_encabezado(pdf, ancho, alto, venta, pagina=1)

    # Datos de la operación (sin campo Estado)
    pdf.setFont("Helvetica-Bold", 9.2)
    pdf.drawString(0.50 * inch, y, f"Cliente: {cli_nombre}")
    pdf.drawRightString(
        ancho - 0.50 * inch,
        y,
        f"{cli_etiqueta_doc}: {cli_doc}" + (f" · Tel: {cli_tel}" if cli_tel else ""),
    )
    if cli_dir:
        y -= 13
        pdf.setFont("Helvetica", 8.3)
        pdf.drawString(0.50 * inch, y, f"Dirección: {cli_dir[:102]}")
    y -= 13
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(0.50 * inch, y, f"Sucursal: {sucursal_nombre} · Entrega: {venta.tipo_entrega}")
    pdf.drawRightString(
        ancho - 0.50 * inch,
        y,
        f"Asesor: {asesor_nombre}" + (f" · Técnico: {tecnico_nombre}" if tecnico_nombre else ""),
    )

    # Tabla de artículos (encabezado Carbón #191818 con texto blanco y filas alternadas #F6F6F6)
    y -= 20
    pdf.setFillColorRGB(0.098, 0.094, 0.094)  # #191818
    pdf.rect(0.50 * inch, y - 4, ancho - 1.00 * inch, 18, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 8.3)
    pdf.drawString(0.60 * inch, y + 2, "Cant.")
    pdf.drawString(1.02 * inch, y + 2, "Descripción / Serial")
    pdf.drawRightString(ancho - 1.60 * inch, y + 2, "Precio Unitario")
    pdf.drawRightString(ancho - 0.60 * inch, y + 2, "Subtotal")

    y -= 17
    pdf.setFont("Helvetica", 8.2)
    for idx_det, det in enumerate(venta.detalles):
        if y < 1.2 * inch:
            pdf.showPage()
            y = _dibujar_encabezado(pdf, ancho, alto, venta, pagina=2)
            pdf.setFont("Helvetica", 8.2)

        if idx_det % 2 == 1:
            pdf.setFillColorRGB(0.965, 0.965, 0.965)  # #F6F6F6
            pdf.rect(0.50 * inch, y - 3.5, ancho - 1.00 * inch, 13.5, fill=1, stroke=0)

        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        serial_txt = f" [Serial: {det.equipo.serial}]" if det.equipo else ""
        precio_unit = float(det.precio_regular_usd if es_regular else det.precio_promo_usd)
        subtotal = precio_unit * int(det.cantidad)
        es_obsequio = float(det.precio_promo_usd) == 0.0 and float(det.precio_regular_usd) == 0.0
        etiqueta_obs = " [OBSEQUIO]" if es_obsequio else ""
        desc = f"{det.descripcion}{serial_txt}{etiqueta_obs}"[:68]

        pdf.drawString(0.60 * inch, y, str(det.cantidad))
        pdf.drawString(1.02 * inch, y, desc)
        if es_obsequio:
            pdf.drawRightString(ancho - 1.60 * inch, y, "OBSEQUIO ($0.00)")
            pdf.drawRightString(ancho - 0.60 * inch, y, "$0.00")
        else:
            pdf.drawRightString(ancho - 1.60 * inch, y, f"${precio_unit:,.2f}")
            pdf.drawRightString(ancho - 0.60 * inch, y, f"${subtotal:,.2f}")
        y -= 13.5

        desc_srv = (getattr(det, "descripcion_servicio", "") or "").strip()
        if desc_srv:
            pdf.setFont("Helvetica-Oblique", 7.6)
            pdf.setFillColorRGB(0.3, 0.35, 0.4)
            for linea in _envolver_texto(f"Trabajo realizado: {desc_srv}", 78):
                pdf.drawString(1.12 * inch, y, linea)
                y -= 9.5
            pdf.setFillColor(colors.black)
            pdf.setFont("Helvetica", 8.2)

    # Monto Total (solo USD si Promo; USD y Bs si Regular)
    y -= 4
    pdf.setStrokeColor(colors.grey)
    pdf.setLineWidth(0.7)
    pdf.line(0.50 * inch, y, ancho - 0.50 * inch, y)
    y -= 15
    pdf.setFont("Helvetica-Bold", 10)
    monto_total_usd = float(venta.total_regular_usd if es_regular else venta.total_promo_usd)
    if es_regular and tasa_bcv > 0:
        monto_total_bs = monto_total_usd * tasa_bcv
        pdf.drawRightString(
            ancho - 0.60 * inch,
            y,
            f"Monto Total: ${monto_total_usd:,.2f} USD  |  Bs. {monto_total_bs:,.2f}",
        )
    else:
        pdf.drawRightString(ancho - 0.60 * inch, y, f"Monto Total: ${monto_total_usd:,.2f} USD")

    # Detalle de pagos registrados
    pagos_activos = [p for p in venta.pagos if not p.anulado]
    if pagos_activos:
        y -= 16
        pdf.setFont("Helvetica-Bold", 8.3)
        pdf.drawString(0.50 * inch, y, "Pagos registrados:")
        y -= 11
        pdf.setFont("Helvetica", 8)
        for p in pagos_activos:
            inst_nombre = p.instrumento.nombre if p.instrumento else "Pago"
            ref = f" · Ref: {p.referencia}" if p.referencia else ""
            pdf.drawString(
                0.60 * inch,
                y,
                f"- {inst_nombre}: {float(p.monto_moneda_origen):,.2f} {p.moneda}{ref}",
            )
            y -= 10.5

    # Bloque estructurado de Delivery o Envío Nacional si aplica
    datos_entrega = _parsear_datos_entrega(venta)
    if datos_entrega:
        y -= 6
        if y < 2.2 * inch:
            pdf.showPage()
            y = _dibujar_encabezado(pdf, ancho, alto, venta, pagina=2)
        y = _dibujar_bloque_entrega(pdf, ancho, y, venta.tipo_entrega, datos_entrega)

    # Si no cabe cómodamente el bloque oficial de Garantía + Prueba de Funcionalidad + Firmas (~5.25 in), pasar a Página 2 limpia
    espacio_requerido = 5.25 * inch
    if y < espacio_requerido:
        pdf.showPage()
        y = _dibujar_encabezado(pdf, ancho, alto, venta, pagina=2)
    else:
        y -= 8

    # ---------------- POLÍTICA Y CONDICIONES DE GARANTÍA ----------------
    pdf.setFillColorRGB(0.91, 0.35, 0.16)
    pdf.setFont("Helvetica-Bold", 8.5)
    pdf.drawString(0.50 * inch, y, "POLÍTICA Y CONDICIONES DE GARANTÍA — TEKIO ELECTRONICS 2024, C.A.")
    y -= 10
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica", 6.8)

    clausulas = [
        "• Todos nuestros equipos tendrán una garantía de CIENTO OCHENTA (180) días continuos a partir de la fecha de facturación/emisión.",
        "• Los productos cuentan con garantía solo por defectos de fábrica; el equipo es probado y chequeado por el personal frente al cliente. La empresa únicamente será responsable por garantías de equipos que presenten daños de fábrica o los indicados al momento de adquirirlos.",
        "• Debe verificar el equipo al momento de la entrega en el caso de los equipos refurbished, ya que pueden presentar detalles estéticos de uso.",
        "• Es obligatorio conservar esta nota de entrega para la garantía.",
        "• El equipo no debe mostrar signos o señales de maltrato físico o abuso (golpes, rayones, grietas o daños en su estructura física), ni rastro de contacto con humedad o líquidos (todos los equipos poseen indicadores internos y externos).",
        "• Las fallas de software por modificaciones o manipulaciones indebidas, virus o incompatibilidad no son cubiertas por la garantía; de ser reparadas por nuestros técnicos generarán un costo cubierto por el cliente.",
        "• Nuestro soporte técnico labora de 10:00 AM a 5:00 PM. En caso de dudas con respecto al equipo, consultar primero con su vendedor dentro del mismo horario. En caso de garantía, el equipo entrará en proceso de revisión con una duración aproximada de 3 días.",
        "• No se cubrirán garantías por daños ocasionados por altos voltajes, cortocircuitos de corriente externa, impericia, mal manejo, accidentes o presencia de elementos nocivos (líquidos, ácidos, polvo, cuerpos orgánicos/inorgánicos, sustancias químicas, etc.).",
        "• Las pantallas son probadas y chequeadas frente al cliente; solo serán cubiertas garantías por daños de circuitos internos o flex. No se cubren táctil, líneas o manchas producidas, descontrol o marcación.",
        "• \"La garantía contempla reparación o reemplazo del producto, según corresponda. No aplica reembolso de dinero.\"",
        "• La garantía no será aceptada si el producto fue manipulado por personas ajenas a nuestros técnicos autorizados.",
    ]

    for clausula in clausulas:
        for linea in _envolver_texto(clausula, 122):
            pdf.drawString(0.52 * inch, y, linea)
            y -= 8.2
        y -= 1.0

    # ---------------- PRUEBA DE FUNCIONALIDAD DEL EQUIPO ----------------
    y -= 6
    ancho_tabla = ancho - 1.00 * inch
    mitad = ancho_tabla / 2
    alto_fila = 12
    x_izq = 0.50 * inch
    x_der = x_izq + mitad

    # Encabezado Carbón (#191818) con texto blanco
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.rect(x_izq, y - 12, ancho_tabla, 14, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 7.8)
    pdf.drawString(x_izq + 6, y - 8, "PRUEBA DE FUNCIONALIDAD DEL EQUIPO")
    pdf.drawRightString(x_izq + ancho_tabla - 6, y - 8, "Verificación frente al cliente")
    y -= 12

    items_funcionalidad = [
        ("PANTALLA", "MICRÓFONO / AUDIO"),
        ("TECLADO", "CÁMARA FRONTAL"),
        ("USB / HDMI", "BOTÓN DE ENCENDIDO"),
        ("PIN DE CARGA", "CARGADOR"),
        ("WIFI / BLUETOOTH", "VINIL"),
    ]

    pdf.setStrokeColorRGB(0.85, 0.87, 0.89)
    pdf.setLineWidth(0.5)
    pdf.setFont("Helvetica", 7.2)

    for idx_f, (izq_lbl, der_lbl) in enumerate(items_funcionalidad):
        y -= alto_fila
        if idx_f % 2 == 1:
            pdf.setFillColorRGB(0.965, 0.965, 0.965)  # #F6F6F6
            pdf.rect(x_izq, y, ancho_tabla, alto_fila, fill=1, stroke=0)
        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        pdf.rect(x_izq, y, mitad, alto_fila, fill=0, stroke=1)
        pdf.rect(x_der, y, mitad, alto_fila, fill=0, stroke=1)
        pdf.drawString(x_izq + 5, y + 3.5, izq_lbl)
        pdf.drawRightString(x_izq + mitad - 6, y + 3.5, "[  ] SI   [  ] NO")
        pdf.drawString(x_der + 5, y + 3.5, der_lbl)
        pdf.drawRightString(x_der + mitad - 6, y + 3.5, "[  ] SI   [  ] NO")

    # ¿Cómo nos encontraste?
    y -= 15
    canal_lower = (venta.canal_visita or "").strip().lower()
    m_ig = "X" if "instagram" in canal_lower else " "
    m_tt = "X" if "tiktok" in canal_lower else " "
    m_fb = "X" if "facebook" in canal_lower else " "
    m_ot = "X" if (canal_lower and m_ig == " " and m_tt == " " and m_fb == " ") else " "
    pdf.setFont("Helvetica-Bold", 7.4)
    pdf.drawString(0.50 * inch, y, "¿Cómo nos encontraste?:")
    pdf.setFont("Helvetica", 7.4)
    pdf.drawString(
        1.95 * inch,
        y,
        f"[{m_ig}] Instagram     [{m_tt}] TikTok     [{m_fb}] Facebook     [{m_ot}] Otros",
    )

    # Observaciones
    y -= 13
    pdf.setFont("Helvetica-Bold", 7.4)
    pdf.drawString(0.50 * inch, y, "Observaciones:")
    pdf.setFont("Helvetica", 7.4)
    if venta.nota and venta.nota.strip():
        pdf.drawString(1.38 * inch, y, venta.nota.strip()[:95])
    else:
        pdf.setStrokeColorRGB(0.75, 0.78, 0.82)
        pdf.line(1.38 * inch, y - 2, ancho - 0.50 * inch, y - 2)

    # Texto de conformidad
    y -= 13
    pdf.setFont("Helvetica-Oblique", 7.2)
    pdf.drawString(
        0.50 * inch,
        y,
        "Al firmar este documento, usted acepta nuestras condiciones de garantía y las condiciones en las que está siendo entregado nuestro producto.",
    )

    # Datos de conformidad del cliente + Firmas
    y -= 14
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawString(
        0.50 * inch,
        y,
        f"Nombre / Razón Social: {cli_nombre}   ·   {cli_etiqueta_doc}: {cli_doc}"
        + (f"   ·   Teléfono: {cli_tel}" if cli_tel else ""),
    )

    y_firma = max(0.45 * inch, y - 28)
    pdf.setStrokeColor(colors.grey)
    pdf.setLineWidth(0.7)
    pdf.line(0.85 * inch, y_firma, 3.35 * inch, y_firma)
    pdf.line(ancho - 3.35 * inch, y_firma, ancho - 0.85 * inch, y_firma)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(2.10 * inch, y_firma - 11, "Entregado por (Tekio Electronics)")
    pdf.drawCentredString(ancho - 2.10 * inch, y_firma - 11, "Firma del Cliente")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
