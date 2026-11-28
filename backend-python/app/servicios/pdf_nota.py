from __future__ import annotations

import io
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from app.modelos_finanzas import MonedaInstrumento, TipoPrecioInstrumento, Venta
from app.utils.pdf_branding import dibujar_marca_de_agua


RUTA_LOGO_PDF = Path(__file__).resolve().parent.parent.parent / "assets" / "tekio-logo-horizontal.png"

ESTILO_GARANTIA_JUSTIFICADO = ParagraphStyle(
    name="GarantiaTekioJustificado",
    fontName="Helvetica",
    fontSize=6.7,
    leading=8.3,
    textColor=colors.HexColor("#191818"),
    alignment=TA_JUSTIFY,
    spaceAfter=1.8,
)


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


def _dibujar_encabezado(pdf: canvas.Canvas, ancho: float, alto: float, venta: Venta, pagina: int = 1) -> float:
    # Marca de agua Tekio (~7% opacidad) centrada detrás del contenido de cada página
    dibujar_marca_de_agua(pdf)

    # Franja superior sutil en Naranja Tekio (#E85A28)
    pdf.setFillColorRGB(0.91, 0.35, 0.16)
    pdf.rect(0, alto - 0.08 * inch, ancho, 0.08 * inch, fill=1, stroke=0)

    # Imagotipo oficial PNG a la izquierda respetando proporción y zona de respeto
    if RUTA_LOGO_PDF.exists():
        pdf.drawImage(
            str(RUTA_LOGO_PDF),
            0.50 * inch,
            alto - 0.54 * inch,
            width=1.65 * inch,
            height=0.39 * inch,
            preserveAspectRatio=True,
            anchor="sw",
            mask="auto",
        )
        pdf.setFillColorRGB(0.098, 0.094, 0.094)  # #191818
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.drawString(0.50 * inch, alto - 0.70 * inch, "TEKIO ELECTRONICS 2024, C.A. · RIF: J-50637518-4")
        pdf.setFillColorRGB(0.38, 0.38, 0.38)
        pdf.setFont("Helvetica", 7.8)
        pdf.drawString(0.50 * inch, alto - 0.83 * inch, "Somos tu solución · Valencia, Edo. Carabobo · WhatsApp: +58 424-4152658")
    else:
        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        pdf.setFont("Helvetica-Bold", 14.5)
        pdf.drawString(0.50 * inch, alto - 0.42 * inch, "TEKIO ELECTRONICS 2024, C.A.")
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.drawString(0.50 * inch, alto - 0.60 * inch, "RIF: J-50637518-4 · Valencia, Edo. Carabobo, Venezuela")
        pdf.setFillColorRGB(0.38, 0.38, 0.38)
        pdf.setFont("Helvetica", 8)
        pdf.drawString(0.50 * inch, alto - 0.76 * inch, "Somos tu solución · WhatsApp: +58 424-4152658")

    # Bloque derecho: Nota de Entrega
    sufijo_pag = f" (Pág. {pagina})" if pagina > 1 else ""
    pdf.setFillColorRGB(0.91, 0.35, 0.16)  # #E85A28
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawRightString(ancho - 0.50 * inch, alto - 0.38 * inch, f"NOTA DE ENTREGA{sufijo_pag}")
    pdf.setFillColorRGB(0.098, 0.094, 0.094)  # #191818
    pdf.setFont("Helvetica-Bold", 10.5)
    pdf.drawRightString(ancho - 0.50 * inch, alto - 0.56 * inch, f"Nro: {venta.numero_venta}")
    pdf.setFont("Helvetica", 8.5)
    pdf.drawRightString(ancho - 0.50 * inch, alto - 0.72 * inch, f"Fecha: {venta.fecha.isoformat()}")

    # Línea divisoria sutil
    pdf.setStrokeColorRGB(0.898, 0.906, 0.922)  # #E5E7EB
    pdf.setLineWidth(0.8)
    pdf.line(0.50 * inch, alto - 0.93 * inch, ancho - 0.50 * inch, alto - 0.93 * inch)

    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    return alto - 1.15 * inch


def _parsear_datos_entrega(venta: Venta) -> dict[str, Any] | None:
    raw = getattr(venta, "datos_entrega_json", "") or ""
    parsed: dict[str, Any] = {}
    if raw.strip():
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                parsed = dict(obj)
        except Exception:
            parsed = {}

    # Complementar con columnas estructuradas envio_* si existen en la venta
    es_envio = "env" in (getattr(venta, "tipo_entrega", "") or "").lower()
    mapeo = {
        "destinatario" if es_envio else "nombre_recibe": getattr(venta, "envio_destinatario_nombre", ""),
        "cedula": getattr(venta, "envio_destinatario_documento", ""),
        "telefono": getattr(venta, "envio_destinatario_telefono", ""),
        "empresa_envio": getattr(venta, "envio_agencia_courier", ""),
        "direccion_oficina" if es_envio else "direccion": getattr(venta, "envio_direccion_o_agencia", ""),
        "estado_ciudad" if es_envio else "zona_municipio": getattr(venta, "envio_ciudad_estado", ""),
        "punto_referencia": getattr(venta, "envio_referencia", ""),
        "modalidad": getattr(venta, "envio_modalidad_pago", ""),
        "horario_instrucciones": getattr(venta, "envio_notas", ""),
    }
    for k, v in mapeo.items():
        if str(v or "").strip() and not str(parsed.get(k) or "").strip():
            parsed[k] = str(v).strip()

    return parsed if any(str(v or "").strip() for v in parsed.values()) else None


def _dibujar_bloque_entrega(
    pdf: canvas.Canvas, ancho: float, y: float, tipo_entrega: str, datos: dict[str, Any]
) -> float:
    es_envio = "env" in tipo_entrega.lower()
    titulo = "DATOS DE ENVÍO NACIONAL (ENCOMIENDA)" if es_envio else "DATOS DE DELIVERY"
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

    lineas_texto: list[str] = []
    for etiqueta, val in campos:
        texto_val = str(val or "").strip()
        if texto_val:
            lineas_texto.extend(_envolver_texto(f"{etiqueta}: {texto_val}", 104))
    if not lineas_texto:
        return y

    alto_caja = 18 + len(lineas_texto) * 9.8 + 6
    y_bottom = y - alto_caja
    pdf.setFillColorRGB(0.975, 0.978, 0.985)
    pdf.setStrokeColorRGB(0.85, 0.87, 0.89)
    pdf.setLineWidth(0.7)
    pdf.rect(0.50 * inch, y_bottom, ancho - 1.00 * inch, alto_caja, fill=1, stroke=1)

    y_cursor = y - 12
    pdf.setFillColorRGB(0.91, 0.35, 0.16)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(0.62 * inch, y_cursor, titulo)
    y_cursor -= 11
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica", 7.8)
    for linea in lineas_texto:
        pdf.drawString(0.62 * inch, y_cursor, linea)
        y_cursor -= 9.8
    return y_bottom - 8


def generar_pdf_nota_entrega(venta: Venta) -> bytes:
    """Genera el PDF tamaño carta de la Nota de Entrega oficial de TEKIO ELECTRONICS 2024, C.A."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    ancho, alto = letter
    ancho_util = ancho - 1.00 * inch

    es_regular = _es_venta_regular(venta)
    tasa_bcv = float(venta.tasa_bcv_snapshot or Decimal("0"))
    cli_nombre, cli_etiqueta_doc, cli_doc, cli_tel, cli_dir = _obtener_datos_cliente(venta)
    sucursal_nombre = venta.sucursal.nombre if venta.sucursal else "Tekio central"
    asesor_nombre = venta.asesor.nombre if venta.asesor else "Tienda"
    tecnico_nombre = venta.tecnico.nombre if venta.tecnico else None

    pagina_actual = 1
    y = _dibujar_encabezado(pdf, ancho, alto, venta, pagina=pagina_actual)

    # Datos de la operación (sin campo Estado)
    pdf.setFont("Helvetica-Bold", 9.2)
    pdf.drawString(0.50 * inch, y, f"Cliente: {cli_nombre}")
    pdf.drawRightString(
        ancho - 0.50 * inch,
        y,
        f"{cli_etiqueta_doc}: {cli_doc}" + (f" · Tel: {cli_tel}" if cli_tel else ""),
    )
    if cli_dir:
        y -= 12.5
        pdf.setFont("Helvetica", 8.2)
        pdf.drawString(0.50 * inch, y, f"Dirección: {cli_dir[:102]}")
    y -= 12.5
    pdf.setFont("Helvetica", 8.4)
    pdf.drawString(0.50 * inch, y, f"Sucursal: {sucursal_nombre} · Entrega: {venta.tipo_entrega}")
    pdf.drawRightString(
        ancho - 0.50 * inch,
        y,
        f"Asesor: {asesor_nombre}" + (f" · Técnico: {tecnico_nombre}" if tecnico_nombre else ""),
    )

    # Tabla de artículos con encabezado claro (#F3F4F6) + acento inferior #E85A28
    y -= 19
    pdf.setFillColorRGB(0.953, 0.957, 0.965)  # #F3F4F6
    pdf.rect(0.50 * inch, y - 4, ancho_util, 18, fill=1, stroke=0)
    pdf.setStrokeColorRGB(0.91, 0.35, 0.16)  # #E85A28
    pdf.setLineWidth(1.0)
    pdf.line(0.50 * inch, y - 4, ancho - 0.50 * inch, y - 4)

    pdf.setFillColorRGB(0.098, 0.094, 0.094)  # #191818
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
            pagina_actual += 1
            y = _dibujar_encabezado(pdf, ancho, alto, venta, pagina=pagina_actual)
            pdf.setFont("Helvetica", 8.2)

        if idx_det % 2 == 1:
            pdf.setFillColorRGB(0.975, 0.975, 0.975)
            pdf.rect(0.50 * inch, y - 3.5, ancho_util, 13.5, fill=1, stroke=0)

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
            pdf.setFillColorRGB(0.098, 0.094, 0.094)
            pdf.setFont("Helvetica", 8.2)

    # Monto Total (solo USD si Promo; USD y Bs si Regular)
    y -= 4
    pdf.setStrokeColorRGB(0.85, 0.87, 0.89)
    pdf.setLineWidth(0.7)
    pdf.line(0.50 * inch, y, ancho - 0.50 * inch, y)
    y -= 15
    pdf.setFont("Helvetica-Bold", 10)
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
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
        y -= 15
        pdf.setFont("Helvetica-Bold", 8.2)
        pdf.drawString(0.50 * inch, y, "Pagos registrados:")
        y -= 11
        pdf.setFont("Helvetica", 7.9)
        for p in pagos_activos:
            inst_nombre = p.instrumento.nombre if p.instrumento else "Pago"
            ref = f" · Ref: {p.referencia}" if p.referencia else ""
            pdf.drawString(
                0.60 * inch,
                y,
                f"- {inst_nombre}: {float(p.monto_moneda_origen):,.2f} {p.moneda}{ref}",
            )
            y -= 10

    # Constancia visible si el equipo fue entregado SIN cargador
    if bool(getattr(venta, "sin_cargador", False)):
        motivo_sc = (getattr(venta, "motivo_sin_cargador", "") or "").strip()
        texto_sc = "Observación: Equipo entregado SIN cargador"
        if motivo_sc:
            texto_sc += f" ({motivo_sc})"
        y -= 10
        if y < 1.8 * inch:
            pdf.showPage()
            pagina_actual += 1
            y = _dibujar_encabezado(pdf, ancho, alto, venta, pagina=pagina_actual)
        alto_sc = 22
        y_sc_bottom = y - alto_sc
        pdf.setFillColorRGB(0.996, 0.953, 0.922)  # #FDF0EB suave
        pdf.setStrokeColorRGB(0.910, 0.353, 0.157)  # #E85A28
        pdf.setLineWidth(1.0)
        pdf.rect(0.50 * inch, y_sc_bottom, ancho - 1.00 * inch, alto_sc, fill=1, stroke=1)
        pdf.setFillColorRGB(0.60, 0.20, 0.07)
        pdf.setFont("Helvetica-Bold", 8.4)
        pdf.drawString(0.62 * inch, y_sc_bottom + 7, texto_sc[:110])
        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        y = y_sc_bottom - 6

    # Bloque estructurado de Delivery o Envío Nacional si aplica
    datos_entrega = _parsear_datos_entrega(venta)
    if datos_entrega:
        y -= 6
        if y < 2.2 * inch:
            pdf.showPage()
            pagina_actual += 1
            y = _dibujar_encabezado(pdf, ancho, alto, venta, pagina=pagina_actual)
        y = _dibujar_bloque_entrega(pdf, ancho, y, venta.tipo_entrega, datos_entrega)

    # ---------------- PREPARAR BLOQUE AL PIE (GARANTÍAS JUSTIFICADAS + FUNCIONALIDAD + FIRMAS) ----------------
    clausulas_html = [
        "• <b>Cobertura (180 días):</b> Todos nuestros equipos tendrán una garantía de <b>CIENTO OCHENTA (180) días continuos</b> a partir de la fecha de facturación/emisión.",
        "• Los productos cuentan con garantía solo por defectos de fábrica; el equipo es probado y chequeado por el personal frente al cliente. La empresa únicamente será responsable por garantías de equipos que presenten daños de fábrica o los indicados al momento de adquirirlos.",
        "• Debe verificar el equipo al momento de la entrega en el caso de los equipos <i>refurbished</i>, ya que pueden presentar detalles estéticos de uso. <b>Es obligatorio conservar esta nota de entrega para la garantía.</b>",
        "• El equipo no debe mostrar signos o señales de maltrato físico o abuso (golpes, rayones, grietas o daños en su estructura física), ni rastro de contacto con humedad o líquidos (todos los equipos poseen indicadores internos y externos).",
        "• Las fallas de software por modificaciones o manipulaciones indebidas, virus o incompatibilidad no son cubiertas por la garantía; de ser reparadas por nuestros técnicos generarán un costo cubierto por el cliente.",
        "• Nuestro soporte técnico labora de <b>10:00 AM a 5:00 PM</b>. En caso de dudas con respecto al equipo, consultar primero con su vendedor dentro del mismo horario. En caso de garantía, el equipo entrará en proceso de revisión con una duración aproximada de <b>3 días</b>.",
        "• No se cubrirán garantías por daños ocasionados por altos voltajes, cortocircuitos de corriente externa, impericia, mal manejo, accidentes o presencia de elementos nocivos (líquidos, ácidos, polvo, cuerpos orgánicos/inorgánicos, sustancias químicas, etc.).",
        "• Las pantallas son probadas y chequeadas frente al cliente; solo serán cubiertas garantías <b>por daños de circuitos internos o flex</b>. No se cubren táctil, líneas o manchas producidas, descontrol o marcación.",
        "• <i>\"La garantía contempla reparación o reemplazo del producto, según corresponda. No aplica reembolso de dinero.\"</i> La garantía no será aceptada si el producto fue manipulado por personas ajenas a nuestros técnicos autorizados.",
    ]

    parrafos_garantia: list[tuple[Paragraph, float]] = []
    alto_garantia = 14.0  # título de garantías
    for texto_html in clausulas_html:
        p = Paragraph(texto_html, ESTILO_GARANTIA_JUSTIFICADO)
        _, h_p = p.wrapOn(pdf, ancho_util, alto)
        parrafos_garantia.append((p, h_p))
        alto_garantia += h_p + 1.8

    alto_funcionalidad = 14 + (5 * 11.5) + 12  # encabezado + 5 filas + margen
    alto_cierre = 13 + 12 + 12 + 13 + 38  # canal + obs + conformidad + datos cliente + firmas
    alto_total_pie = alto_garantia + alto_funcionalidad + alto_cierre + 12

    margen_inferior = 0.42 * inch
    y_inicio_pie = margen_inferior + alto_total_pie

    # Si no cabe en el espacio restante de la página actual, saltar limpiamente a nueva página y anclar al pie
    if y < y_inicio_pie + 12:
        pdf.showPage()
        pagina_actual += 1
        _dibujar_encabezado(pdf, ancho, alto, venta, pagina=pagina_actual)

    # Anclar exactamente al pie de la hoja
    y_pie = y_inicio_pie

    # Línea separadora sutil arriba del bloque de garantías
    pdf.setStrokeColorRGB(0.898, 0.906, 0.922)
    pdf.setLineWidth(0.6)
    pdf.line(0.50 * inch, y_pie + 4, ancho - 0.50 * inch, y_pie + 4)

    # Título de Políticas y Condiciones de Garantía
    y_pie -= 8
    pdf.setFillColorRGB(0.91, 0.35, 0.16)  # #E85A28
    pdf.setFont("Helvetica-Bold", 8.2)
    pdf.drawString(0.50 * inch, y_pie, "POLÍTICA Y CONDICIONES DE GARANTÍA — TEKIO ELECTRONICS 2024, C.A.")
    y_pie -= 4

    # Párrafos justificados (TA_JUSTIFY)
    for p, h_p in parrafos_garantia:
        y_pie -= h_p
        p.drawOn(pdf, 0.50 * inch, y_pie)
        y_pie -= 1.8

    # ---------------- PRUEBA DE FUNCIONALIDAD DEL EQUIPO (encabezado claro #F3F4F6) ----------------
    y_pie -= 6
    mitad = ancho_util / 2
    alto_fila = 11.5
    x_izq = 0.50 * inch
    x_der = x_izq + mitad

    pdf.setFillColorRGB(0.953, 0.957, 0.965)  # #F3F4F6
    pdf.rect(x_izq, y_pie - 12, ancho_util, 13.5, fill=1, stroke=0)
    pdf.setStrokeColorRGB(0.91, 0.35, 0.16)  # #E85A28
    pdf.setLineWidth(0.9)
    pdf.line(x_izq, y_pie - 12, x_izq + ancho_util, y_pie - 12)

    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 7.6)
    pdf.drawString(x_izq + 6, y_pie - 8, "PRUEBA DE FUNCIONALIDAD DEL EQUIPO")
    pdf.setFillColorRGB(0.42, 0.45, 0.49)
    pdf.setFont("Helvetica", 7.2)
    pdf.drawRightString(x_izq + ancho_util - 6, y_pie - 8, "Verificación frente al cliente")
    y_pie -= 12

    items_funcionalidad = [
        ("PANTALLA", "MICRÓFONO / AUDIO"),
        ("TECLADO", "CÁMARA FRONTAL"),
        ("USB / HDMI", "BOTÓN DE ENCENDIDO"),
        ("PIN DE CARGA", "CARGADOR"),
        ("WIFI / BLUETOOTH", "VINIL"),
    ]

    pdf.setStrokeColorRGB(0.86, 0.88, 0.90)
    pdf.setLineWidth(0.5)
    pdf.setFont("Helvetica", 7.1)

    for idx_f, (izq_lbl, der_lbl) in enumerate(items_funcionalidad):
        y_pie -= alto_fila
        if idx_f % 2 == 1:
            pdf.setFillColorRGB(0.975, 0.975, 0.975)
            pdf.rect(x_izq, y_pie, ancho_util, alto_fila, fill=1, stroke=0)
        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        pdf.rect(x_izq, y_pie, mitad, alto_fila, fill=0, stroke=1)
        pdf.rect(x_der, y_pie, mitad, alto_fila, fill=0, stroke=1)
        pdf.drawString(x_izq + 5, y_pie + 3.2, izq_lbl)
        pdf.drawRightString(x_izq + mitad - 6, y_pie + 3.2, "[  ] SI   [  ] NO")
        pdf.drawString(x_der + 5, y_pie + 3.2, der_lbl)
        pdf.drawRightString(x_der + mitad - 6, y_pie + 3.2, "[  ] SI   [  ] NO")

    # ¿Cómo nos encontraste?
    y_pie -= 13
    canal_lower = (venta.canal_visita or "").strip().lower()
    m_ig = "X" if "instagram" in canal_lower else " "
    m_tt = "X" if "tiktok" in canal_lower else " "
    m_fb = "X" if "facebook" in canal_lower else " "
    m_ot = "X" if (canal_lower and m_ig == " " and m_tt == " " and m_fb == " ") else " "
    pdf.setFont("Helvetica-Bold", 7.3)
    pdf.drawString(0.50 * inch, y_pie, "¿Cómo nos encontraste?:")
    pdf.setFont("Helvetica", 7.3)
    pdf.drawString(
        1.92 * inch,
        y_pie,
        f"[{m_ig}] Instagram     [{m_tt}] TikTok     [{m_fb}] Facebook     [{m_ot}] Otros",
    )

    # Observaciones
    y_pie -= 12
    pdf.setFont("Helvetica-Bold", 7.3)
    pdf.drawString(0.50 * inch, y_pie, "Observaciones:")
    pdf.setFont("Helvetica", 7.3)
    if venta.nota and venta.nota.strip():
        pdf.drawString(1.36 * inch, y_pie, venta.nota.strip()[:95])
    else:
        pdf.setStrokeColorRGB(0.78, 0.80, 0.83)
        pdf.line(1.36 * inch, y_pie - 2, ancho - 0.50 * inch, y_pie - 2)

    # Texto de conformidad
    y_pie -= 12
    pdf.setFont("Helvetica-Oblique", 7.1)
    pdf.drawString(
        0.50 * inch,
        y_pie,
        "Al firmar este documento, usted acepta nuestras condiciones de garantía y las condiciones en las que está siendo entregado nuestro producto.",
    )

    # Datos de conformidad del cliente + Firmas
    y_pie -= 13
    pdf.setFont("Helvetica-Bold", 7.4)
    pdf.drawString(
        0.50 * inch,
        y_pie,
        f"Nombre / Razón Social: {cli_nombre}   ·   {cli_etiqueta_doc}: {cli_doc}"
        + (f"   ·   Teléfono: {cli_tel}" if cli_tel else ""),
    )

    y_firma = max(0.48 * inch, y_pie - 26)
    pdf.setStrokeColorRGB(0.60, 0.63, 0.67)
    pdf.setLineWidth(0.7)
    pdf.line(0.85 * inch, y_firma, 3.35 * inch, y_firma)
    pdf.line(ancho - 3.35 * inch, y_firma, ancho - 0.85 * inch, y_firma)
    pdf.setFont("Helvetica-Bold", 7.9)
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.drawCentredString(2.10 * inch, y_firma - 10, "Entregado por (Tekio Electronics)")
    pdf.drawCentredString(ancho - 2.10 * inch, y_firma - 10, "Firma del Cliente")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
