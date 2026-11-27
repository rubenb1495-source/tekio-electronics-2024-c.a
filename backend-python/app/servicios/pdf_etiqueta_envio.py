from __future__ import annotations

import io
import json
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from app.core.empresa import (
    ESLOGAN,
    RAZON_SOCIAL,
    RIF,
    obtener_telefono_sede,
)
from app.modelos_finanzas import Venta
from app.utils.pdf_branding import RUTA_LOGO_HORIZONTAL, dibujar_marca_de_agua


def normalizar_tipo_entrega(valor: str | None) -> str:
    """Normaliza tipo_entrega a los valores canónicos: RETIRO_TIENDA | DELIVERY | ENVIO_NACIONAL."""
    limpio = (valor or "").strip().upper()
    if not limpio or limpio in ("TIENDA", "RETIRO", "RETIRO_TIENDA", "RETIRO EN TIENDA"):
        return "RETIRO_TIENDA"
    if "DELIV" in limpio:
        return "DELIVERY"
    if "ENV" in limpio or "ENCOMIENDA" in limpio or "COURIER" in limpio:
        return "ENVIO_NACIONAL"
    return "RETIRO_TIENDA"


def _normalizar_modalidad_flete(valor: str | None) -> str:
    limpio = (valor or "").strip().upper()
    if not limpio:
        return ""
    if "COBRO" in limpio or "DESTINO" in limpio:
        return "COBRO_EN_DESTINO"
    if "CORTES" in limpio or "GRATIS" in limpio:
        return "CORTESIA"
    if "PAGAD" in limpio or "PREPAG" in limpio:
        return "PAGADO"
    return limpio[:40]


def _etiqueta_modalidad_flete(valor: str) -> str:
    m = _normalizar_modalidad_flete(valor)
    if m == "COBRO_EN_DESTINO":
        return "COBRO EN DESTINO"
    if m == "PAGADO":
        return "PAGADO"
    if m == "CORTESIA":
        return "CORTESÍA"
    return valor.strip() or "NO ESPECIFICADA"


def extraer_datos_envio_entrada(
    tipo_entrega: str,
    datos_entrega: dict[str, Any] | None,
    *,
    envio_destinatario_nombre: str | None = None,
    envio_destinatario_documento: str | None = None,
    envio_destinatario_telefono: str | None = None,
    envio_agencia_courier: str | None = None,
    envio_direccion_o_agencia: str | None = None,
    envio_ciudad_estado: str | None = None,
    envio_referencia: str | None = None,
    envio_modalidad_pago: str | None = None,
    envio_notas: str | None = None,
) -> dict[str, str]:
    """Unifica los datos de envío provenientes de campos directos o del diccionario datos_entrega."""
    d = datos_entrega if isinstance(datos_entrega, dict) else {}
    tipo_norm = normalizar_tipo_entrega(tipo_entrega)

    nombre = (
        (envio_destinatario_nombre or "").strip()
        or str(d.get("destinatario") or d.get("nombre_recibe") or "").strip()
    )
    documento = (
        (envio_destinatario_documento or "").strip()
        or str(d.get("cedula") or d.get("documento") or "").strip()
    )
    telefono = (
        (envio_destinatario_telefono or "").strip()
        or str(d.get("telefono") or "").strip()
    )
    agencia = (
        (envio_agencia_courier or "").strip()
        or str(d.get("empresa_envio") or d.get("agencia_courier") or "").strip()
        or ("Delivery Local" if tipo_norm == "DELIVERY" else "")
    )

    agencia_oficina = str(d.get("agencia_oficina") or "").strip()
    direccion_oficina = str(d.get("direccion_oficina") or "").strip()
    direccion_del = str(d.get("direccion") or "").strip()
    if (envio_direccion_o_agencia or "").strip():
        direccion_o_agencia = (envio_direccion_o_agencia or "").strip()
    elif tipo_norm == "ENVIO_NACIONAL":
        partes_dir = [p for p in (agencia_oficina, direccion_oficina) if p]
        direccion_o_agencia = " — ".join(partes_dir)
    else:
        direccion_o_agencia = direccion_del

    ciudad_estado = (
        (envio_ciudad_estado or "").strip()
        or str(d.get("estado_ciudad") or d.get("zona_municipio") or "").strip()
    )
    referencia = (
        (envio_referencia or "").strip()
        or str(d.get("punto_referencia") or d.get("referencia") or "").strip()
    )
    modalidad_pago = _normalizar_modalidad_flete(
        envio_modalidad_pago or str(d.get("modalidad") or d.get("modalidad_pago") or "")
    )
    notas = (
        (envio_notas or "").strip()
        or str(d.get("horario_instrucciones") or d.get("notas") or "").strip()
    )

    return {
        "envio_destinatario_nombre": nombre,
        "envio_destinatario_documento": documento,
        "envio_destinatario_telefono": telefono,
        "envio_agencia_courier": agencia,
        "envio_direccion_o_agencia": direccion_o_agencia,
        "envio_ciudad_estado": ciudad_estado,
        "envio_referencia": referencia,
        "envio_modalidad_pago": modalidad_pago,
        "envio_notas": notas,
    }


def extraer_datos_envio_venta(venta: Venta) -> dict[str, str]:
    """Obtiene los campos normalizados de envío combinando columnas de Venta, datos_entrega_json y fallback de cliente."""
    parsed_json: dict[str, Any] | None = None
    raw = getattr(venta, "datos_entrega_json", "") or ""
    if raw.strip():
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                parsed_json = obj
        except Exception:
            parsed_json = None

    datos = extraer_datos_envio_entrada(
        venta.tipo_entrega,
        parsed_json,
        envio_destinatario_nombre=getattr(venta, "envio_destinatario_nombre", ""),
        envio_destinatario_documento=getattr(venta, "envio_destinatario_documento", ""),
        envio_destinatario_telefono=getattr(venta, "envio_destinatario_telefono", ""),
        envio_agencia_courier=getattr(venta, "envio_agencia_courier", ""),
        envio_direccion_o_agencia=getattr(venta, "envio_direccion_o_agencia", ""),
        envio_ciudad_estado=getattr(venta, "envio_ciudad_estado", ""),
        envio_referencia=getattr(venta, "envio_referencia", ""),
        envio_modalidad_pago=getattr(venta, "envio_modalidad_pago", ""),
        envio_notas=getattr(venta, "envio_notas", ""),
    )

    # Fallback respetuoso con datos del cliente si faltan nombre/doc/teléfono
    if venta.cliente is not None:
        if not datos["envio_destinatario_nombre"]:
            datos["envio_destinatario_nombre"] = venta.cliente.nombre or ""
        if not datos["envio_destinatario_documento"]:
            if venta.cliente.tipo_documento and venta.cliente.documento:
                datos["envio_destinatario_documento"] = (
                    f"{venta.cliente.tipo_documento}-{venta.cliente.documento}"
                )
            else:
                datos["envio_destinatario_documento"] = venta.cliente.rif_cedula or ""
        if not datos["envio_destinatario_telefono"]:
            datos["envio_destinatario_telefono"] = venta.cliente.telefono or ""
        if not datos["envio_direccion_o_agencia"]:
            datos["envio_direccion_o_agencia"] = venta.cliente.direccion or ""

    return datos


def _envolver_lineas(texto: str, max_chars: int) -> list[str]:
    palabras = (texto or "").strip().split()
    if not palabras:
        return []
    lineas: list[str] = []
    actual = ""
    for p in palabras:
        if len(actual) + len(p) + 1 <= max_chars:
            actual = f"{actual} {p}".strip()
        else:
            if actual:
                lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


def _dibujar_triangulo_alerta(pdf: canvas.Canvas, cx: float, cy: float, lado: float) -> None:
    """Dibuja un ícono vectorial de alerta (triángulo con signo !) en Naranja Tekio #E85A28."""
    pdf.saveState()
    mitad = lado / 2.0
    altura = lado * 0.86
    p = pdf.beginPath()
    p.moveTo(cx, cy + altura / 2.0)
    p.lineTo(cx - mitad, cy - altura / 2.0)
    p.lineTo(cx + mitad, cy - altura / 2.0)
    p.close()
    pdf.setFillColorRGB(0.910, 0.353, 0.157)  # #E85A28
    pdf.setStrokeColorRGB(0.910, 0.353, 0.157)
    pdf.setLineWidth(1.5)
    pdf.drawPath(p, fill=1, stroke=1)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", lado * 0.56)
    pdf.drawCentredString(cx, cy - altura * 0.28, "!")
    pdf.restoreState()


def generar_pdf_etiqueta_envio(venta: Venta, bultos: int | None = None) -> bytes:
    """
    Genera una Hoja Carta (8.5" x 11") de Etiqueta de Envío con aviso FRÁGIL
    lista para imprimir y pegar en el exterior del paquete.
    SEGURIDAD: No incluye precios, montos de venta, costos ni detalles de pago.
    """
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    ancho, alto = letter
    margen_x = 0.55 * inch
    ancho_util = ancho - (2 * margen_x)

    tipo_norm = normalizar_tipo_entrega(venta.tipo_entrega)
    es_nacional = tipo_norm == "ENVIO_NACIONAL"
    datos = extraer_datos_envio_venta(venta)

    sucursal_nombre = venta.sucursal.nombre if venta.sucursal else "Tekio Central"
    tel_sede = obtener_telefono_sede(sucursal_nombre)
    fecha_str = venta.fecha.strftime("%d/%m/%Y") if venta.fecha else ""

    # Marca de agua sutil y pie corporativo oficial
    dibujar_marca_de_agua(pdf)

    # =========================================================================
    # 1. ENCABEZADO TEKIO (Light-First, sin fondos negros)
    # =========================================================================
    pdf.setFillColorRGB(0.910, 0.353, 0.157)  # #E85A28
    pdf.rect(0, alto - 8, ancho, 8, fill=1, stroke=0)

    y_top = alto - 0.50 * inch
    if RUTA_LOGO_HORIZONTAL.exists():
        pdf.drawImage(
            str(RUTA_LOGO_HORIZONTAL),
            margen_x,
            y_top - 0.52 * inch,
            width=2.15 * inch,
            height=0.58 * inch,
            preserveAspectRatio=True,
            mask="auto",
        )
    else:
        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(margen_x, y_top - 0.25 * inch, "TEKIO ELECTRONICS")

    # Datos empresa + Nota correlativo a la derecha
    pdf.setFillColorRGB(0.098, 0.094, 0.094)  # #191818
    pdf.setFont("Helvetica-Bold", 10.5)
    pdf.drawRightString(ancho - margen_x, y_top - 0.08 * inch, RAZON_SOCIAL)
    pdf.setFont("Helvetica", 8.8)
    pdf.setFillColorRGB(0.32, 0.34, 0.38)
    pdf.drawRightString(
        ancho - margen_x,
        y_top - 0.25 * inch,
        f"RIF: {RIF}  ·  {sucursal_nombre} ({tel_sede})",
    )
    pdf.setFillColorRGB(0.910, 0.353, 0.157)
    pdf.setFont("Helvetica-Bold", 12)
    texto_ref = f"NOTA: {venta.numero_venta}   |   FECHA: {fecha_str}"
    if bultos and bultos > 0:
        texto_ref += f"   |   BULTOS: {bultos}"
    pdf.drawRightString(ancho - margen_x, y_top - 0.48 * inch, texto_ref)

    y_sep = y_top - 0.68 * inch
    pdf.setStrokeColorRGB(0.910, 0.353, 0.157)
    pdf.setLineWidth(1.6)
    pdf.line(margen_x, y_sep, ancho - margen_x, y_sep)

    # =========================================================================
    # 2. BANNER PRINCIPAL "FRÁGIL" (Alto contraste, acento #E85A28, sin negro)
    # =========================================================================
    banner_alto = 1.48 * inch
    banner_y = y_sep - 0.22 * inch - banner_alto

    pdf.setFillColorRGB(0.992, 0.941, 0.922)  # #FDF0EB suave
    pdf.setStrokeColorRGB(0.910, 0.353, 0.157)  # #E85A28
    pdf.setLineWidth(3.2)
    pdf.roundRect(margen_x, banner_y, ancho_util, banner_alto, 12, fill=1, stroke=1)

    # Dos triángulos de advertencia flanqueando "FRÁGIL"
    centro_x = ancho / 2.0
    cy_fragil = banner_y + banner_alto * 0.62
    _dibujar_triangulo_alerta(pdf, centro_x - 2.15 * inch, cy_fragil + 0.04 * inch, 0.56 * inch)
    _dibujar_triangulo_alerta(pdf, centro_x + 2.15 * inch, cy_fragil + 0.04 * inch, 0.56 * inch)

    pdf.setFillColorRGB(0.910, 0.353, 0.157)
    pdf.setFont("Helvetica-Bold", 44)
    pdf.drawCentredString(centro_x, banner_y + banner_alto * 0.44, "FRÁGIL")

    # Franja subtítulo dentro del banner
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 11.5)
    pdf.drawCentredString(
        centro_x,
        banner_y + 0.24 * inch,
        "EQUIPO ELECTRÓNICO  ·  MANEJAR CON CUIDADO  ·  NO APILAR  ·  NO MOJAR",
    )

    # =========================================================================
    # 3. BLOQUE DESTINATARIO (Tipografía grande y legible a distancia)
    # =========================================================================
    y_dest_top = banner_y - 0.28 * inch
    dest_alto = 5.15 * inch
    dest_y = y_dest_top - dest_alto

    pdf.setFillColorRGB(1, 1, 1)
    pdf.setStrokeColorRGB(0.82, 0.84, 0.87)
    pdf.setLineWidth(1.5)
    pdf.roundRect(margen_x, dest_y, ancho_util, dest_alto, 12, fill=1, stroke=1)

    # Cabecera del bloque DESTINATARIO con badge de tipo de envío y courier
    y_cur = y_dest_top - 0.38 * inch
    badge_texto = "ENVÍO NACIONAL" if es_nacional else "DELIVERY LOCAL"
    badge_w = 2.35 * inch
    pdf.setFillColorRGB(0.910, 0.353, 0.157)
    pdf.roundRect(margen_x + 0.25 * inch, y_cur - 0.10 * inch, badge_w, 0.38 * inch, 7, fill=1, stroke=0)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawCentredString(margen_x + 0.25 * inch + badge_w / 2.0, y_cur + 0.02 * inch, badge_texto)

    agencia_txt = (datos["envio_agencia_courier"] or ("ENCOMIENDA" if es_nacional else "DELIVERY LOCAL")).upper()
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawRightString(ancho - margen_x - 0.28 * inch, y_cur - 0.02 * inch, agencia_txt[:28])

    y_cur -= 0.28 * inch
    pdf.setStrokeColorRGB(0.90, 0.91, 0.93)
    pdf.setLineWidth(1.0)
    pdf.line(margen_x + 0.25 * inch, y_cur, ancho - margen_x - 0.25 * inch, y_cur)

    # Nombre del destinatario
    y_cur -= 0.30 * inch
    pdf.setFillColorRGB(0.45, 0.47, 0.51)
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawString(margen_x + 0.28 * inch, y_cur, "DESTINATARIO")
    y_cur -= 0.34 * inch
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 21)
    nombre_dest = datos["envio_destinatario_nombre"] or "POR CONFIRMAR"
    for linea in _envolver_lineas(nombre_dest.upper(), 36)[:2]:
        pdf.drawString(margen_x + 0.28 * inch, y_cur, linea)
        y_cur -= 0.30 * inch

    # Cédula/RIF y Teléfono lado a lado en tamaño grande
    y_cur -= 0.12 * inch
    col2_x = margen_x + ancho_util * 0.50
    pdf.setFillColorRGB(0.45, 0.47, 0.51)
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawString(margen_x + 0.28 * inch, y_cur, "CÉDULA / RIF")
    pdf.drawString(col2_x, y_cur, "TELÉFONO DE CONTACTO")
    y_cur -= 0.28 * inch
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(
        margen_x + 0.28 * inch,
        y_cur,
        datos["envio_destinatario_documento"] or "—",
    )
    pdf.setFillColorRGB(0.910, 0.353, 0.157)
    pdf.drawString(
        col2_x,
        y_cur,
        datos["envio_destinatario_telefono"] or "—",
    )

    # Dirección exacta / Agencia destino
    y_cur -= 0.38 * inch
    pdf.setFillColorRGB(0.45, 0.47, 0.51)
    pdf.setFont("Helvetica-Bold", 9.5)
    etiqueta_dir = "AGENCIA / DIRECCIÓN DESTINO" if es_nacional else "DIRECCIÓN EXACTA DE ENTREGA"
    pdf.drawString(margen_x + 0.28 * inch, y_cur, etiqueta_dir)
    y_cur -= 0.25 * inch
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 13.5)
    dir_txt = datos["envio_direccion_o_agencia"] or "—"
    for linea in _envolver_lineas(dir_txt, 58)[:3]:
        pdf.drawString(margen_x + 0.28 * inch, y_cur, linea)
        y_cur -= 0.23 * inch

    # Ciudad / Estado y Modalidad de Flete
    y_cur -= 0.14 * inch
    pdf.setFillColorRGB(0.45, 0.47, 0.51)
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawString(margen_x + 0.28 * inch, y_cur, "CIUDAD / ESTADO · ZONA")
    pdf.drawString(col2_x, y_cur, "MODALIDAD DE FLETE")
    y_cur -= 0.26 * inch
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 13.5)
    pdf.drawString(
        margen_x + 0.28 * inch,
        y_cur,
        (datos["envio_ciudad_estado"] or "—")[:34],
    )
    pdf.setFillColorRGB(0.910, 0.353, 0.157)
    pdf.drawString(col2_x, y_cur, _etiqueta_modalidad_flete(datos["envio_modalidad_pago"]))

    # Punto de referencia y Notas
    if datos["envio_referencia"]:
        y_cur -= 0.32 * inch
        pdf.setFillColorRGB(0.45, 0.47, 0.51)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(margen_x + 0.28 * inch, y_cur, "PUNTO DE REFERENCIA")
        y_cur -= 0.20 * inch
        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        pdf.setFont("Helvetica", 11.5)
        for linea in _envolver_lineas(datos["envio_referencia"], 70)[:2]:
            pdf.drawString(margen_x + 0.28 * inch, y_cur, linea)
            y_cur -= 0.19 * inch

    if datos["envio_notas"] and y_cur > dest_y + 0.40 * inch:
        y_cur -= 0.14 * inch
        pdf.setFillColorRGB(0.45, 0.47, 0.51)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(margen_x + 0.28 * inch, y_cur, "INSTRUCCIONES DE ENTREGA")
        y_cur -= 0.19 * inch
        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        pdf.setFont("Helvetica", 10.5)
        for linea in _envolver_lineas(datos["envio_notas"], 74)[:2]:
            pdf.drawString(margen_x + 0.28 * inch, y_cur, linea)
            y_cur -= 0.18 * inch

    # =========================================================================
    # 4. BLOQUE REMITENTE (Claro #F6F6F6, sin precios ni montos)
    # =========================================================================
    rem_alto = 1.25 * inch
    rem_y = dest_y - 0.24 * inch - rem_alto

    pdf.setFillColorRGB(0.965, 0.965, 0.965)  # #F6F6F6
    pdf.setStrokeColorRGB(0.85, 0.87, 0.89)
    pdf.setLineWidth(1.0)
    pdf.roundRect(margen_x, rem_y, ancho_util, rem_alto, 10, fill=1, stroke=1)

    y_rem = rem_y + rem_alto - 0.26 * inch
    pdf.setFillColorRGB(0.910, 0.353, 0.157)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margen_x + 0.25 * inch, y_rem, "REMITENTE")

    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margen_x + 0.25 * inch, y_rem - 0.24 * inch, f"{RAZON_SOCIAL}  ·  RIF: {RIF}")

    pdf.setFont("Helvetica", 10.5)
    pdf.setFillColorRGB(0.25, 0.27, 0.31)
    pdf.drawString(
        margen_x + 0.25 * inch,
        y_rem - 0.46 * inch,
        f"Sede emisora: {sucursal_nombre}  ·  Teléfono de contacto: {tel_sede}",
    )

    pdf.setFont("Helvetica-BoldOblique", 10)
    pdf.setFillColorRGB(0.910, 0.353, 0.157)
    pdf.drawString(margen_x + 0.25 * inch, y_rem - 0.70 * inch, f'"{ESLOGAN}"')

    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.setFillColorRGB(0.32, 0.34, 0.38)
    etiqueta_doc = f"Documento de referencia: {venta.numero_venta}"
    if bultos and bultos > 0:
        etiqueta_doc += f"  ·  Total bultos: {bultos}"
    pdf.drawRightString(ancho - margen_x - 0.25 * inch, y_rem - 0.70 * inch, etiqueta_doc)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
