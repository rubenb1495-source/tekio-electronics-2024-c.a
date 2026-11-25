from __future__ import annotations

import io
import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from app.modelos_operaciones import (
    CierreCaja,
    Cotizacion,
    DevolucionGarantia,
    LiquidacionComision,
    ModalidadCotizacion,
    TipoResolucionDevolucion,
)
from app.utils.pdf_branding import dibujar_marca_de_agua


RUTA_LOGO_PDF = Path(__file__).resolve().parent.parent.parent / "assets" / "tekio-logo-horizontal.png"

ETIQUETAS_RESOLUCION: dict[str, str] = {
    TipoResolucionDevolucion.CAMBIO_IGUAL.value: "Cambio por Equipo Igual (Garantía / Reemplazo)",
    TipoResolucionDevolucion.GARANTIA_COMPONENTE.value: "Garantía de Componente / Taller",
    TipoResolucionDevolucion.CAMBIO_UPGRADE.value: "Cambio con Upgrade (Diferencia a Favor de Tekio)",
    TipoResolucionDevolucion.CAMBIO_DOWNGRADE.value: "Cambio con Downgrade (Diferencia a Favor del Cliente)",
    TipoResolucionDevolucion.REEMBOLSO_TOTAL.value: "Reembolso Total / Devolución de Venta",
}


def _envolver_texto(texto: str, max_chars: int) -> list[str]:
    palabras = (texto or "").split()
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
    return lineas or [""]


def _datos_cliente_tercero(cli: Any) -> tuple[str, str, str, str, str]:
    if cli is None:
        return "Cliente general", "Cédula de Identidad", "N/A", "", ""
    es_juridico = (getattr(cli, "tipo_persona", "NATURAL") or "NATURAL").upper() == "JURIDICO"
    etiqueta_doc = "RIF" if es_juridico else "Cédula de Identidad"
    if getattr(cli, "tipo_documento", "") and getattr(cli, "documento", ""):
        valor_doc = f"{cli.tipo_documento}-{cli.documento}"
    else:
        valor_doc = getattr(cli, "rif_cedula", "") or "N/A"
    return (
        cli.nombre,
        etiqueta_doc,
        valor_doc,
        getattr(cli, "telefono", "") or "",
        getattr(cli, "direccion", "") or "",
    )


def _dibujar_encabezado_corporativo(
    pdf: canvas.Canvas,
    ancho: float,
    alto: float,
    titulo_doc: str,
    numero_doc: str,
    fecha_texto: str,
    subtitulo_der: str = "",
    pagina: int = 1,
) -> float:
    dibujar_marca_de_agua(pdf)

    # Franja superior sutil en Naranja Tekio (#E85A28)
    pdf.setFillColorRGB(0.91, 0.35, 0.16)
    pdf.rect(0, alto - 0.08 * inch, ancho, 0.08 * inch, fill=1, stroke=0)

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
        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.drawString(0.50 * inch, alto - 0.70 * inch, "TEKIO ELECTRONICS 2024, C.A. · RIF: J-50637518-4")
        pdf.setFillColorRGB(0.38, 0.38, 0.38)
        pdf.setFont("Helvetica", 7.8)
        pdf.drawString(
            0.50 * inch,
            alto - 0.83 * inch,
            "Somos tu solución · Valencia, Edo. Carabobo · WhatsApp: +58 424-4152658",
        )
    else:
        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        pdf.setFont("Helvetica-Bold", 14.5)
        pdf.drawString(0.50 * inch, alto - 0.42 * inch, "TEKIO ELECTRONICS 2024, C.A.")
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.drawString(0.50 * inch, alto - 0.60 * inch, "RIF: J-50637518-4 · Valencia, Edo. Carabobo, Venezuela")
        pdf.setFillColorRGB(0.38, 0.38, 0.38)
        pdf.setFont("Helvetica", 8)
        pdf.drawString(0.50 * inch, alto - 0.76 * inch, "Somos tu solución · WhatsApp: +58 424-4152658")

    sufijo_pag = f" (Pág. {pagina})" if pagina > 1 else ""
    pdf.setFillColorRGB(0.91, 0.35, 0.16)
    pdf.setFont("Helvetica-Bold", 11.5)
    pdf.drawRightString(ancho - 0.50 * inch, alto - 0.38 * inch, f"{titulo_doc}{sufijo_pag}")
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawRightString(ancho - 0.50 * inch, alto - 0.55 * inch, numero_doc)
    pdf.setFont("Helvetica", 8.3)
    pdf.drawRightString(ancho - 0.50 * inch, alto - 0.70 * inch, fecha_texto)
    if subtitulo_der:
        pdf.setFillColorRGB(0.38, 0.38, 0.38)
        pdf.setFont("Helvetica", 7.8)
        pdf.drawRightString(ancho - 0.50 * inch, alto - 0.83 * inch, subtitulo_der)

    pdf.setStrokeColorRGB(0.898, 0.906, 0.922)
    pdf.setLineWidth(0.8)
    pdf.line(0.50 * inch, alto - 0.93 * inch, ancho - 0.50 * inch, alto - 0.93 * inch)

    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    return alto - 1.15 * inch


# =====================================================================
# 1. COMPROBANTE DE DEVOLUCIÓN / CAMBIO / GARANTÍA
# =====================================================================


def generar_pdf_devolucion_garantia(dev: DevolucionGarantia) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    ancho, alto = letter

    venta = dev.venta
    cliente_nombre, etiqueta_doc, valor_doc, cliente_tel, _ = _datos_cliente_tercero(
        venta.cliente if venta else None
    )
    sucursal_nombre = venta.sucursal.nombre if venta and venta.sucursal else "Tekio Electronics"

    y = _dibujar_encabezado_corporativo(
        pdf,
        ancho,
        alto,
        titulo_doc="COMPROBANTE DE GARANTÍA / CAMBIO",
        numero_doc=f"Nro: {dev.numero_operacion}",
        fecha_texto=f"Fecha: {dev.fecha.isoformat()}",
        subtitulo_der=f"Venta original: {venta.numero_venta if venta else 'N/A'}",
    )

    # Datos de la operación y del cliente
    pdf.setFillColorRGB(0.953, 0.957, 0.965)  # #F3F4F6
    pdf.roundRect(0.50 * inch, y - 0.82 * inch, ancho - 1.0 * inch, 0.88 * inch, 6, fill=1, stroke=0)
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(0.62 * inch, y - 0.14 * inch, f"Cliente: {cliente_nombre}")
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(0.62 * inch, y - 0.34 * inch, f"{etiqueta_doc}: {valor_doc}" + (f" · Tel: {cliente_tel}" if cliente_tel else ""))
    pdf.drawString(0.62 * inch, y - 0.52 * inch, f"Sucursal: {sucursal_nombre} · Nota original: {venta.numero_venta if venta else 'N/A'}")
    pdf.drawString(
        0.62 * inch,
        y - 0.70 * inch,
        f"Autorizado por: {dev.autorizado_por.nombre if dev.autorizado_por else 'Operador Tekio'}",
    )
    y -= 1.08 * inch

    # Tipo de resolución destacado
    etiqueta_res = ETIQUETAS_RESOLUCION.get(dev.tipo_resolucion, dev.tipo_resolucion)
    pdf.setFillColorRGB(0.992, 0.941, 0.922)  # #FDF0EB
    pdf.setStrokeColorRGB(0.91, 0.35, 0.16)
    pdf.setLineWidth(0.7)
    pdf.roundRect(0.50 * inch, y - 0.30 * inch, ancho - 1.0 * inch, 0.36 * inch, 5, fill=1, stroke=1)
    pdf.setFillColorRGB(0.75, 0.25, 0.08)
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawString(0.64 * inch, y - 0.17 * inch, f"Resolución aplicada: {etiqueta_res}")
    y -= 0.58 * inch

    # Detalle de equipos / componentes
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawString(0.50 * inch, y, "Detalle de la Operación")
    y -= 0.22 * inch

    filas: list[tuple[str, str]] = []
    if dev.equipo_origen:
        filas.append(
            (
                "Equipo recibido (Origen)",
                f"{dev.equipo_origen.modelo} · Serial: {dev.equipo_origen.serial} (Estado reingreso: {dev.estado_reingreso_origen})",
            )
        )
    if dev.equipo_destino:
        filas.append(
            (
                "Equipo entregado (Nuevo)",
                f"{dev.equipo_destino.modelo} · Serial: {dev.equipo_destino.serial}",
            )
        )
    if dev.caso_taller:
        filas.append(
            (
                "Caso de Taller (Garantía)",
                f"{dev.caso_taller.numero_caso} · Estado: {dev.caso_taller.estado}",
            )
        )
    if dev.articulo_repuesto:
        filas.append(
            (
                "Componente / Repuesto cubierto",
                f"{dev.articulo_repuesto.descripcion} (Sin cargo para el cliente — Cubierto por garantía Tekio)",
            )
        )

    dif = Decimal(str(dev.diferencia_usd or 0))
    if dev.tipo_resolucion == TipoResolucionDevolucion.CAMBIO_IGUAL.value:
        filas.append(("Diferencia monetaria", "$0.00 (Cambio directo por garantía)"))
    elif dev.tipo_resolucion == TipoResolucionDevolucion.GARANTIA_COMPONENTE.value:
        filas.append(("Cargo al cliente", "$0.00 (Cubierto por garantía de 180 días)"))
    elif dev.tipo_resolucion == TipoResolucionDevolucion.CAMBIO_UPGRADE.value:
        inst_nom = dev.instrumento.nombre if dev.instrumento else "Instrumento registrado"
        ref_txt = f" · Ref: {dev.referencia_pago}" if dev.referencia_pago else ""
        filas.append(("Diferencia abonada por el cliente", f"${dif:.2f} USD · {inst_nom}{ref_txt}"))
    elif dev.tipo_resolucion == TipoResolucionDevolucion.CAMBIO_DOWNGRADE.value:
        if dev.dejar_saldo_favor:
            filas.append(("Diferencia a favor del cliente", f"${abs(dif):.2f} USD (Acreditado como Saldo a Favor en tienda)"))
        else:
            inst_nom = dev.instrumento.nombre if dev.instrumento else "Caja / Banco"
            ref_txt = f" · Ref: {dev.referencia_pago}" if dev.referencia_pago else ""
            filas.append(("Reembolso de diferencia al cliente", f"${abs(dif):.2f} USD · {inst_nom}{ref_txt}"))
    elif dev.tipo_resolucion == TipoResolucionDevolucion.REEMBOLSO_TOTAL.value:
        inst_nom = dev.instrumento.nombre if dev.instrumento else "Caja / Banco"
        ref_txt = f" · Ref: {dev.referencia_pago}" if dev.referencia_pago else ""
        filas.append(("Monto reembolsado al cliente", f"${abs(dif):.2f} USD · {inst_nom}{ref_txt}"))

    pdf.setFont("Helvetica", 8.8)
    for clave, valor in filas:
        pdf.setFillColorRGB(0.35, 0.35, 0.35)
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.drawString(0.55 * inch, y, f"{clave}:")
        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        pdf.setFont("Helvetica", 8.5)
        lineas_val = _envolver_texto(valor, 72)
        for idx, linea in enumerate(lineas_val):
            pdf.drawString(2.35 * inch, y - (idx * 0.16 * inch), linea)
        y -= max(0.24 * inch, len(lineas_val) * 0.16 * inch + 0.08 * inch)

    y -= 0.12 * inch
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(0.50 * inch, y, "Motivo / Observaciones:")
    y -= 0.18 * inch
    pdf.setFont("Helvetica", 8.5)
    for linea in _envolver_texto(dev.motivo or "Sin observaciones adicionales.", 95):
        pdf.drawString(0.55 * inch, y, linea)
        y -= 0.16 * inch

    # Condición de continuidad de garantía
    y -= 0.20 * inch
    pdf.setFillColorRGB(0.35, 0.35, 0.35)
    pdf.setFont("Helvetica-Oblique", 7.8)
    for linea in _envolver_texto(
        "Nota: En casos de cambio de equipo o garantía de componente, la cobertura de garantía de 180 días continúa vigente según las políticas oficiales de TEKIO ELECTRONICS 2024, C.A. (RIF: J-50637518-4).",
        108,
    ):
        pdf.drawString(0.50 * inch, y, linea)
        y -= 0.14 * inch

    # Firmas
    y_firma = max(1.10 * inch, y - 0.90 * inch)
    pdf.setStrokeColorRGB(0.55, 0.55, 0.55)
    pdf.setLineWidth(0.7)
    pdf.line(0.85 * inch, y_firma, 3.45 * inch, y_firma)
    pdf.line(ancho - 3.45 * inch, y_firma, ancho - 0.85 * inch, y_firma)
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 8.5)
    pdf.drawCentredString(2.15 * inch, y_firma - 0.16 * inch, "Autorizado por Tekio Electronics")
    pdf.drawCentredString(ancho - 2.15 * inch, y_firma - 0.16 * inch, "Recibido conforme (Cliente)")
    pdf.setFont("Helvetica", 7.8)
    pdf.setFillColorRGB(0.4, 0.4, 0.4)
    pdf.drawCentredString(2.15 * inch, y_firma - 0.30 * inch, dev.autorizado_por.nombre if dev.autorizado_por else "")
    pdf.drawCentredString(ancho - 2.15 * inch, y_firma - 0.30 * inch, f"{cliente_nombre} · {etiqueta_doc}: {valor_doc}")

    pdf.save()
    return buffer.getvalue()


# =====================================================================
# 2. LISTA DE PRECIOS DE EQUIPOS DISPONIBLES (SOLO LISTO, SIN COSTOS)
# =====================================================================


def generar_pdf_lista_precios(
    items: list[dict[str, Any]],
    sucursal_nombre: str,
    fecha_emision: date,
    tasa_bcv: Decimal = Decimal("0"),
    tipo_precio: str = "PROMO",
) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    ancho, alto = letter
    pagina = 1
    es_regular = (tipo_precio or "PROMO").upper() == "REGULAR"

    def iniciar_pagina(num_pag: int) -> float:
        sub_der = (
            (f"Tasa BCV ref.: Bs. {tasa_bcv:,.2f}" if tasa_bcv > 0 else "Precios sujetos a tasa BCV vigente")
            if es_regular
            else "Precios en USD Divisas"
        )
        y_inicio = _dibujar_encabezado_corporativo(
            pdf,
            ancho,
            alto,
            titulo_doc="LISTA DE PRECIOS DISPONIBLES",
            numero_doc=f"Sucursal: {sucursal_nombre}",
            fecha_texto=f"Emisión: {fecha_emision.isoformat()}",
            subtitulo_der=sub_der,
            pagina=num_pag,
        )
        # Encabezado de tabla claro (#F3F4F6)
        pdf.setFillColorRGB(0.953, 0.957, 0.965)
        pdf.rect(0.50 * inch, y_inicio - 0.24 * inch, ancho - 1.0 * inch, 0.28 * inch, fill=1, stroke=0)
        pdf.setStrokeColorRGB(0.91, 0.35, 0.16)
        pdf.setLineWidth(1.0)
        pdf.line(0.50 * inch, y_inicio - 0.24 * inch, ancho - 0.50 * inch, y_inicio - 0.24 * inch)

        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        pdf.setFont("Helvetica-Bold", 8.4)
        pdf.drawString(0.58 * inch, y_inicio - 0.14 * inch, "Modelo y Características")
        pdf.drawCentredString(5.55 * inch, y_inicio - 0.14 * inch, "Disponibles")
        pdf.drawRightString(
            ancho - 0.56 * inch,
            y_inicio - 0.14 * inch,
            "Precio (USD / Bs)" if es_regular else "Precio (USD)",
        )
        return y_inicio - 0.44 * inch

    y = iniciar_pagina(pagina)

    if not items:
        pdf.setFillColorRGB(0.4, 0.4, 0.4)
        pdf.setFont("Helvetica", 9.5)
        pdf.drawString(0.55 * inch, y, "No hay equipos disponibles en estado LISTO para los filtros seleccionados.")
    else:
        for idx, item in enumerate(items):
            modelo = str(item.get("modelo") or item.get("descripcion") or "Equipo")
            caracteristicas = str(item.get("caracteristicas") or "").strip()
            categoria = str(item.get("categoria") or "").strip()
            lineas_modelo = _envolver_texto(modelo, 62)
            lineas_caract = _envolver_texto(caracteristicas, 70) if caracteristicas else []
            extra_h = (len(lineas_caract) * 0.13 * inch) + (0.13 * inch if categoria else 0.0)
            alto_fila = max(0.36 * inch, len(lineas_modelo) * 0.15 * inch + extra_h + 0.12 * inch)

            if y - alto_fila < 0.95 * inch:
                pdf.setFillColorRGB(0.45, 0.45, 0.45)
                pdf.setFont("Helvetica-Oblique", 7.5)
                pdf.drawString(
                    0.50 * inch,
                    0.48 * inch,
                    "Disponibilidad sujeta a inventario al momento de la compra · Garantía de 180 días Tekio Electronics.",
                )
                pdf.showPage()
                pagina += 1
                y = iniciar_pagina(pagina)

            if idx % 2 == 1:
                pdf.setFillColorRGB(0.985, 0.985, 0.985)
                pdf.rect(0.50 * inch, y - alto_fila + 0.16 * inch, ancho - 1.0 * inch, alto_fila, fill=1, stroke=0)

            pdf.setFillColorRGB(0.098, 0.094, 0.094)
            pdf.setFont("Helvetica-Bold", 8.6)
            cursor_y = y
            for linea in lineas_modelo:
                pdf.drawString(0.58 * inch, cursor_y, linea)
                cursor_y -= 0.15 * inch
            if lineas_caract:
                pdf.setFillColorRGB(0.28, 0.28, 0.28)
                pdf.setFont("Helvetica", 7.7)
                for linea in lineas_caract:
                    pdf.drawString(0.58 * inch, cursor_y, linea)
                    cursor_y -= 0.13 * inch
            if categoria:
                pdf.setFillColorRGB(0.48, 0.48, 0.48)
                pdf.setFont("Helvetica", 7.0)
                pdf.drawString(0.58 * inch, cursor_y, categoria)

            disponibles = int(item.get("disponibles") or 0)
            precio_usd = Decimal(str(item.get("precio_usd") or 0))
            precio_bs = item.get("precio_bs")

            pdf.setFillColorRGB(0.098, 0.094, 0.094)
            pdf.setFont("Helvetica-Bold", 9.0)
            pdf.drawCentredString(5.55 * inch, y, str(disponibles))

            pdf.setFillColorRGB(0.91, 0.35, 0.16)
            pdf.setFont("Helvetica-Bold", 9.2)
            pdf.drawRightString(ancho - 0.56 * inch, y, f"${precio_usd:,.2f}")

            if es_regular and precio_bs is not None and Decimal(str(precio_bs)) > 0:
                pdf.setFillColorRGB(0.32, 0.32, 0.32)
                pdf.setFont("Helvetica-Bold", 7.8)
                pdf.drawRightString(ancho - 0.56 * inch, y - 0.15 * inch, f"Bs. {Decimal(str(precio_bs)):,.2f}")

            pdf.setStrokeColorRGB(0.91, 0.92, 0.93)
            pdf.setLineWidth(0.4)
            pdf.line(0.50 * inch, y - alto_fila + 0.16 * inch, ancho - 0.50 * inch, y - alto_fila + 0.16 * inch)
            y -= alto_fila

    # Pie corporativo final
    pdf.setFillColorRGB(0.45, 0.45, 0.45)
    pdf.setFont("Helvetica-Oblique", 7.6)
    texto_pie = (
        "Precios expresados en USD y Bolívares referenciales a tasa BCV del día. Disponibilidad sujeta a inventario al momento de la compra."
        if es_regular
        else "Precios expresados en USD Divisas. Disponibilidad sujeta a inventario al momento de la compra."
    )
    pdf.drawString(0.50 * inch, 0.55 * inch, texto_pie)
    pdf.drawString(
        0.50 * inch,
        0.41 * inch,
        "Todos nuestros equipos incluyen 180 días de garantía Tekio Electronics · WhatsApp: +58 424-4152658",
    )

    pdf.save()
    return buffer.getvalue()


# =====================================================================
# 3. COTIZACIÓN DE EQUIPOS / PRESUPUESTO
# =====================================================================


def generar_pdf_cotizacion(cot: Cotizacion) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    ancho, alto = letter

    cliente_nombre, etiqueta_doc, valor_doc, cliente_tel, cliente_dir = _datos_cliente_tercero(cot.cliente)
    fecha_vence = cot.fecha + timedelta(hours=cot.vigencia_horas)
    sucursal_nombre = cot.sucursal.nombre if cot.sucursal else "Tekio Electronics"
    asesor_nombre = cot.asesor.nombre if cot.asesor else "Tienda Tekio"

    y = _dibujar_encabezado_corporativo(
        pdf,
        ancho,
        alto,
        titulo_doc="COTIZACIÓN",
        numero_doc=f"Nro: {cot.numero_cotizacion}",
        fecha_texto=f"Emisión: {cot.fecha.isoformat()}",
        subtitulo_der=f"Vigencia: {cot.vigencia_horas}h (hasta {fecha_vence.isoformat()})",
    )

    # Datos del cliente y de la cotización
    pdf.setFillColorRGB(0.953, 0.957, 0.965)
    pdf.roundRect(0.50 * inch, y - 0.86 * inch, ancho - 1.0 * inch, 0.92 * inch, 6, fill=1, stroke=0)
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(0.62 * inch, y - 0.14 * inch, f"Cliente: {cliente_nombre}")
    pdf.setFont("Helvetica", 8.4)
    pdf.drawString(
        0.62 * inch,
        y - 0.33 * inch,
        f"{etiqueta_doc}: {valor_doc}" + (f" · Tel: {cliente_tel}" if cliente_tel else ""),
    )
    if cliente_dir:
        pdf.drawString(0.62 * inch, y - 0.50 * inch, f"Dirección: {cliente_dir[:92]}")
    pdf.drawString(
        0.62 * inch,
        y - 0.69 * inch,
        f"Sucursal: {sucursal_nombre} · Asesor: {asesor_nombre}",
    )
    y -= 1.12 * inch

    # Modalidad de precio
    es_divisas = cot.modalidad_precio == ModalidadCotizacion.DIVISAS.value
    es_cashea = cot.modalidad_precio == ModalidadCotizacion.CASHEA.value
    etiqueta_mod = (
        "Divisas / USDT (Precio Promocional)"
        if es_divisas
        else ("Financiamiento Cashea (Precio Regular)" if es_cashea else "Bolívares / Pago Mixto (Precio Regular)")
    )
    pdf.setFont("Helvetica-Bold", 8.6)
    pdf.setFillColorRGB(0.91, 0.35, 0.16)
    pdf.drawString(0.50 * inch, y, f"Modalidad cotizada: {etiqueta_mod}")
    if not es_divisas and cot.tasa_bcv_snapshot > 0:
        pdf.setFillColorRGB(0.35, 0.35, 0.35)
        pdf.setFont("Helvetica", 8.2)
        pdf.drawRightString(ancho - 0.50 * inch, y, f"Tasa BCV ref.: Bs. {cot.tasa_bcv_snapshot:,.2f}")
    y -= 0.28 * inch

    # Encabezado de tabla
    pdf.setFillColorRGB(0.953, 0.957, 0.965)
    pdf.rect(0.50 * inch, y - 0.22 * inch, ancho - 1.0 * inch, 0.26 * inch, fill=1, stroke=0)
    pdf.setStrokeColorRGB(0.91, 0.35, 0.16)
    pdf.setLineWidth(1.0)
    pdf.line(0.50 * inch, y - 0.22 * inch, ancho - 0.50 * inch, y - 0.22 * inch)

    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 8.3)
    pdf.drawString(0.58 * inch, y - 0.13 * inch, "Descripción")
    pdf.drawCentredString(4.95 * inch, y - 0.13 * inch, "Cant.")
    pdf.drawRightString(6.15 * inch, y - 0.13 * inch, "Precio Unit.")
    pdf.drawRightString(ancho - 0.56 * inch, y - 0.13 * inch, "Subtotal")
    y -= 0.42 * inch

    tasa_bcv = Decimal(str(cot.tasa_bcv_snapshot or 0))
    for det in cot.detalles:
        unit_usd = det.precio_promo_usd if es_divisas else det.precio_regular_usd
        sub_usd = (unit_usd * Decimal(det.cantidad)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        desc_completa = det.descripcion
        if det.descripcion_servicio:
            desc_completa = f"{desc_completa} — {det.descripcion_servicio}"
        if det.equipo and det.equipo.serial:
            desc_completa = f"{desc_completa} (Serial ref.: {det.equipo.serial})"
        if unit_usd == Decimal("0"):
            desc_completa = f"{desc_completa} [Obsequio]"

        lineas_desc = _envolver_texto(desc_completa, 58)
        alto_fila = max(0.28 * inch, len(lineas_desc) * 0.15 * inch + 0.10 * inch)

        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        pdf.setFont("Helvetica", 8.4)
        for l_idx, linea in enumerate(lineas_desc):
            pdf.drawString(0.58 * inch, y - (l_idx * 0.15 * inch), linea)

        pdf.drawCentredString(4.95 * inch, y, str(det.cantidad))
        pdf.drawRightString(6.15 * inch, y, f"${unit_usd:,.2f}")
        pdf.setFont("Helvetica-Bold", 8.4)
        pdf.drawRightString(ancho - 0.56 * inch, y, f"${sub_usd:,.2f}")

        pdf.setStrokeColorRGB(0.91, 0.92, 0.93)
        pdf.setLineWidth(0.4)
        pdf.line(0.50 * inch, y - alto_fila + 0.14 * inch, ancho - 0.50 * inch, y - alto_fila + 0.14 * inch)
        y -= alto_fila

    # Bloque de totales
    y -= 0.14 * inch
    total_mostrar_usd = cot.total_promo_usd if es_divisas else cot.total_regular_usd
    total_bs = (total_mostrar_usd * tasa_bcv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if tasa_bcv > 0 else Decimal("0")

    alto_caja_tot = 0.72 * inch if es_divisas else (1.12 * inch if es_cashea else 0.90 * inch)
    pdf.setFillColorRGB(0.985, 0.985, 0.985)
    pdf.setStrokeColorRGB(0.85, 0.86, 0.88)
    pdf.setLineWidth(0.7)
    pdf.roundRect(ancho - 3.65 * inch, y - alto_caja_tot + 0.18 * inch, 3.15 * inch, alto_caja_tot, 6, fill=1, stroke=1)

    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 10.5)
    pdf.drawString(ancho - 3.50 * inch, y - 0.06 * inch, "Monto Total:")
    pdf.setFillColorRGB(0.91, 0.35, 0.16)
    pdf.drawRightString(ancho - 0.62 * inch, y - 0.06 * inch, f"${total_mostrar_usd:,.2f} USD")

    if not es_divisas and total_bs > 0:
        pdf.setFillColorRGB(0.25, 0.25, 0.25)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(ancho - 3.50 * inch, y - 0.28 * inch, "Equivalente BCV:")
        pdf.drawRightString(ancho - 0.62 * inch, y - 0.28 * inch, f"Bs. {total_bs:,.2f}")

    if es_cashea:
        inicial_est = (total_mostrar_usd * Decimal("0.40")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cuota_est = ((total_mostrar_usd - inicial_est) / Decimal("3")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        pdf.setFillColorRGB(0.35, 0.35, 0.35)
        pdf.setFont("Helvetica", 7.8)
        pdf.drawString(
            ancho - 3.50 * inch,
            y - 0.50 * inch,
            f"Ref. Cashea (40%): Ini. ${inicial_est:,.2f} + 3 cuotas de ${cuota_est:,.2f}",
        )
        pdf.drawString(
            ancho - 3.50 * inch,
            y - 0.64 * inch,
            "(Sujeto al nivel y aprobación del cliente en app Cashea)",
        )

    y -= alto_caja_tot + 0.16 * inch

    if cot.nota:
        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.drawString(0.50 * inch, y, "Notas:")
        y -= 0.16 * inch
        pdf.setFont("Helvetica", 8.2)
        for linea in _envolver_texto(cot.nota, 96):
            pdf.drawString(0.55 * inch, y, linea)
            y -= 0.15 * inch

    # Aviso legal obligatorio al pie
    pdf.setFillColorRGB(0.992, 0.941, 0.922)
    pdf.setStrokeColorRGB(0.91, 0.35, 0.16)
    pdf.setLineWidth(0.6)
    pdf.roundRect(0.50 * inch, 0.52 * inch, ancho - 1.0 * inch, 0.54 * inch, 5, fill=1, stroke=1)
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 8.0)
    pdf.drawCentredString(
        ancho / 2,
        0.84 * inch,
        "Presupuesto sujeto a disponibilidad de inventario y tasa BCV vigente al momento del pago.",
    )
    pdf.setFillColorRGB(0.38, 0.38, 0.38)
    pdf.setFont("Helvetica", 7.4)
    pdf.drawCentredString(
        ancho / 2,
        0.66 * inch,
        f"Cotización válida por {cot.vigencia_horas} horas desde su emisión · Esta cotización no reserva inventario ni constituye Nota de Entrega.",
    )

    pdf.save()
    return buffer.getvalue()


# =====================================================================
# 4. COMPROBANTE DE LIQUIDACIÓN DE COMISIONES
# =====================================================================


def generar_pdf_liquidacion_comision(liq: LiquidacionComision) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    ancho, alto = letter

    colaborador = liq.usuario.nombre if liq.usuario else "Colaborador"
    rol_col = liq.usuario.rol if liq.usuario else ""
    inst_nom = liq.instrumento.nombre if liq.instrumento else "Caja / Banco"
    aut_nom = liq.autorizado_por.nombre if liq.autorizado_por else "Administración"

    y = _dibujar_encabezado_corporativo(
        pdf,
        ancho,
        alto,
        titulo_doc="COMPROBANTE DE LIQUIDACIÓN",
        numero_doc=f"Nro: {liq.codigo}",
        fecha_texto=f"Fecha de pago: {liq.fecha_pago.isoformat()}",
        subtitulo_der=f"Período: {liq.fecha_inicio.isoformat()} al {liq.fecha_fin.isoformat()}",
    )

    pdf.setFillColorRGB(0.953, 0.957, 0.965)
    pdf.roundRect(0.50 * inch, y - 0.84 * inch, ancho - 1.0 * inch, 0.90 * inch, 6, fill=1, stroke=0)
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 9.2)
    pdf.drawString(0.62 * inch, y - 0.14 * inch, f"Colaborador: {colaborador} ({rol_col})")
    pdf.setFont("Helvetica", 8.4)
    pdf.drawString(
        0.62 * inch,
        y - 0.34 * inch,
        f"Período liquidado: {liq.fecha_inicio.isoformat()} al {liq.fecha_fin.isoformat()}",
    )
    pdf.drawString(
        0.62 * inch,
        y - 0.52 * inch,
        f"Método de pago: {inst_nom}" + (f" · Ref: {liq.referencia}" if liq.referencia else ""),
    )
    pdf.drawString(0.62 * inch, y - 0.70 * inch, f"Autorizado por: {aut_nom}")
    y -= 1.10 * inch

    # Encabezado de tabla
    pdf.setFillColorRGB(0.953, 0.957, 0.965)
    pdf.rect(0.50 * inch, y - 0.22 * inch, ancho - 1.0 * inch, 0.26 * inch, fill=1, stroke=0)
    pdf.setStrokeColorRGB(0.91, 0.35, 0.16)
    pdf.setLineWidth(1.0)
    pdf.line(0.50 * inch, y - 0.22 * inch, ancho - 0.50 * inch, y - 0.22 * inch)

    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 8.2)
    pdf.drawString(0.58 * inch, y - 0.13 * inch, "Referencia / Nota")
    pdf.drawString(2.35 * inch, y - 0.13 * inch, "Concepto")
    pdf.drawRightString(5.85 * inch, y - 0.13 * inch, "Base Promo USD")
    pdf.drawRightString(ancho - 0.56 * inch, y - 0.13 * inch, "Comisión USD")
    y -= 0.40 * inch

    for det in liq.detalles:
        if y < 1.65 * inch:
            pdf.showPage()
            y = _dibujar_encabezado_corporativo(
                pdf,
                ancho,
                alto,
                titulo_doc="COMPROBANTE DE LIQUIDACIÓN",
                numero_doc=f"Nro: {liq.codigo}",
                fecha_texto=f"Fecha de pago: {liq.fecha_pago.isoformat()}",
                pagina=2,
            )
        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        pdf.setFont("Helvetica-Bold", 8.2)
        pdf.drawString(0.58 * inch, y, det.referencia_origen or f"OP-{det.id}")
        pdf.setFont("Helvetica", 8.2)
        pdf.drawString(2.35 * inch, y, det.concepto)
        pdf.drawRightString(5.85 * inch, y, f"${Decimal(str(det.base_promo_usd)):,.2f}")
        pdf.setFont("Helvetica-Bold", 8.2)
        pdf.drawRightString(ancho - 0.56 * inch, y, f"${Decimal(str(det.monto_comision_usd)):,.2f}")
        pdf.setStrokeColorRGB(0.91, 0.92, 0.93)
        pdf.setLineWidth(0.4)
        pdf.line(0.50 * inch, y - 0.09 * inch, ancho - 0.50 * inch, y - 0.09 * inch)
        y -= 0.24 * inch

    y -= 0.14 * inch
    pdf.setFillColorRGB(0.992, 0.941, 0.922)
    pdf.setStrokeColorRGB(0.91, 0.35, 0.16)
    pdf.setLineWidth(0.8)
    pdf.roundRect(ancho - 3.30 * inch, y - 0.36 * inch, 2.80 * inch, 0.44 * inch, 6, fill=1, stroke=1)
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(ancho - 3.16 * inch, y - 0.19 * inch, "TOTAL PAGADO:")
    pdf.setFillColorRGB(0.91, 0.35, 0.16)
    pdf.drawRightString(ancho - 0.62 * inch, y - 0.19 * inch, f"${Decimal(str(liq.monto_total_usd)):,.2f} USD")

    if liq.notas:
        y -= 0.62 * inch
        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        pdf.setFont("Helvetica-Bold", 8.4)
        pdf.drawString(0.50 * inch, y, "Notas:")
        pdf.setFont("Helvetica", 8.2)
        for linea in _envolver_texto(liq.notas, 95):
            y -= 0.15 * inch
            pdf.drawString(0.55 * inch, y, linea)

    y_firma = max(1.05 * inch, y - 0.90 * inch)
    pdf.setStrokeColorRGB(0.55, 0.55, 0.55)
    pdf.setLineWidth(0.7)
    pdf.line(0.85 * inch, y_firma, 3.45 * inch, y_firma)
    pdf.line(ancho - 3.45 * inch, y_firma, ancho - 0.85 * inch, y_firma)
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 8.4)
    pdf.drawCentredString(2.15 * inch, y_firma - 0.16 * inch, "Pagado / Autorizado por")
    pdf.drawCentredString(ancho - 2.15 * inch, y_firma - 0.16 * inch, "Recibido conforme")
    pdf.setFont("Helvetica", 7.8)
    pdf.setFillColorRGB(0.4, 0.4, 0.4)
    pdf.drawCentredString(2.15 * inch, y_firma - 0.30 * inch, aut_nom)
    pdf.drawCentredString(ancho - 2.15 * inch, y_firma - 0.30 * inch, colaborador)

    pdf.save()
    return buffer.getvalue()


# =====================================================================
# 5. REPORTE DE CIERRE DE CAJA DIARIO
# =====================================================================


def generar_pdf_cierre_caja(cierre: CierreCaja) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    ancho, alto = letter

    suc_nom = cierre.sucursal.nombre if cierre.sucursal else "Todas las sucursales"
    usr_nom = cierre.usuario.nombre if cierre.usuario else "Operador"

    y = _dibujar_encabezado_corporativo(
        pdf,
        ancho,
        alto,
        titulo_doc="CIERRE DE CAJA DIARIO",
        numero_doc=f"Cierre #{cierre.id:04d}",
        fecha_texto=f"Fecha: {cierre.fecha.isoformat()}",
        subtitulo_der=f"Sucursal: {suc_nom}",
    )

    # Resumen ejecutivo
    pdf.setFillColorRGB(0.953, 0.957, 0.965)
    pdf.roundRect(0.50 * inch, y - 0.98 * inch, ancho - 1.0 * inch, 1.04 * inch, 6, fill=1, stroke=0)
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 8.8)
    pdf.drawString(0.62 * inch, y - 0.15 * inch, f"Sucursal: {suc_nom} · Responsable: {usr_nom}")
    pdf.setFont("Helvetica", 8.3)
    pdf.drawString(
        0.62 * inch,
        y - 0.35 * inch,
        f"Ventas emitidas: {cierre.cantidad_ventas} · Anulaciones/Devoluciones: {cierre.cantidad_anulaciones} · Total Ventas Promo: ${Decimal(str(cierre.total_ventas_usd)):,.2f}",
    )
    pdf.drawString(
        0.62 * inch,
        y - 0.54 * inch,
        f"Ingresos: ${Decimal(str(cierre.total_ingresos_usd)):,.2f} USD / Bs. {Decimal(str(cierre.total_ingresos_bs)):,.2f} · Cashea Financiado: ${Decimal(str(cierre.total_cashea_usd)):,.2f}",
    )
    pdf.drawString(
        0.62 * inch,
        y - 0.73 * inch,
        f"Egresos: ${Decimal(str(cierre.total_egresos_usd)):,.2f} USD / Bs. {Decimal(str(cierre.total_egresos_bs)):,.2f}",
    )
    pdf.setFont("Helvetica-Bold", 8.5)
    dif = Decimal(str(cierre.diferencia_usd))
    etiqueta_dif = "CUADRADO" if dif == 0 else ("SOBRANTE" if dif > 0 else "FALTANTE")
    pdf.drawString(
        0.62 * inch,
        y - 0.90 * inch,
        f"Efectivo Esperado USD: ${Decimal(str(cierre.efectivo_esperado_usd)):,.2f} · Declarado: ${Decimal(str(cierre.efectivo_declarado_usd)):,.2f} · Diferencia: ${dif:+,.2f} ({etiqueta_dif})",
    )
    y -= 1.24 * inch

    # Desglose por instrumento
    pdf.setFillColorRGB(0.953, 0.957, 0.965)
    pdf.rect(0.50 * inch, y - 0.22 * inch, ancho - 1.0 * inch, 0.26 * inch, fill=1, stroke=0)
    pdf.setStrokeColorRGB(0.91, 0.35, 0.16)
    pdf.setLineWidth(1.0)
    pdf.line(0.50 * inch, y - 0.22 * inch, ancho - 0.50 * inch, y - 0.22 * inch)

    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 8.1)
    pdf.drawString(0.58 * inch, y - 0.13 * inch, "Instrumento / Banco")
    pdf.drawCentredString(3.55 * inch, y - 0.13 * inch, "Moneda")
    pdf.drawRightString(4.95 * inch, y - 0.13 * inch, "Ingresos")
    pdf.drawRightString(6.25 * inch, y - 0.13 * inch, "Egresos")
    pdf.drawRightString(ancho - 0.56 * inch, y - 0.13 * inch, "Neto USD")
    y -= 0.40 * inch

    try:
        desglose = json.loads(cierre.desglose_instrumentos_json or "[]")
    except Exception:
        desglose = []

    for fila in desglose:
        mon = str(fila.get("moneda") or "USD")
        pref = "Bs. " if mon == "BS" else "$"
        ing = Decimal(str(fila.get("ingresos_origen") or 0))
        egr = Decimal(str(fila.get("egresos_origen") or 0))
        neto_usd = Decimal(str(fila.get("neto_usd") or 0))

        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        pdf.setFont("Helvetica-Bold", 8.1)
        pdf.drawString(0.58 * inch, y, str(fila.get("instrumento") or "Instrumento")[:38])
        pdf.setFont("Helvetica", 8.1)
        pdf.drawCentredString(3.55 * inch, y, mon)
        pdf.drawRightString(4.95 * inch, y, f"{pref}{ing:,.2f}")
        pdf.drawRightString(6.25 * inch, y, f"{pref}{egr:,.2f}")
        pdf.setFont("Helvetica-Bold", 8.1)
        pdf.drawRightString(ancho - 0.56 * inch, y, f"${neto_usd:,.2f}")
        pdf.setStrokeColorRGB(0.91, 0.92, 0.93)
        pdf.setLineWidth(0.4)
        pdf.line(0.50 * inch, y - 0.08 * inch, ancho - 0.50 * inch, y - 0.08 * inch)
        y -= 0.24 * inch

    # Desglose de ventas por asesor
    try:
        desglose_as = json.loads(getattr(cierre, "desglose_asesores_json", "[]") or "[]")
    except Exception:
        desglose_as = []

    if desglose_as:
        y -= 0.16 * inch
        pdf.setFillColorRGB(0.953, 0.957, 0.965)
        pdf.rect(0.50 * inch, y - 0.22 * inch, ancho - 1.0 * inch, 0.26 * inch, fill=1, stroke=0)
        pdf.setStrokeColorRGB(0.91, 0.35, 0.16)
        pdf.setLineWidth(1.0)
        pdf.line(0.50 * inch, y - 0.22 * inch, ancho - 0.50 * inch, y - 0.22 * inch)

        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        pdf.setFont("Helvetica-Bold", 8.1)
        pdf.drawString(0.58 * inch, y - 0.13 * inch, "Ventas por Asesor")
        pdf.drawCentredString(4.35 * inch, y - 0.13 * inch, "Cant. Ventas")
        pdf.drawRightString(ancho - 0.56 * inch, y - 0.13 * inch, "Total Promo USD")
        y -= 0.40 * inch

        for as_row in desglose_as:
            pdf.setFillColorRGB(0.098, 0.094, 0.094)
            pdf.setFont("Helvetica-Bold", 8.1)
            pdf.drawString(0.58 * inch, y, str(as_row.get("asesor") or "Tienda")[:42])
            pdf.setFont("Helvetica", 8.1)
            pdf.drawCentredString(4.35 * inch, y, str(int(as_row.get("cantidad_ventas") or 0)))
            pdf.setFont("Helvetica-Bold", 8.1)
            pdf.drawRightString(
                ancho - 0.56 * inch,
                y,
                f"${Decimal(str(as_row.get('total_promo_usd') or 0)):,.2f}",
            )
            pdf.setStrokeColorRGB(0.91, 0.92, 0.93)
            pdf.setLineWidth(0.4)
            pdf.line(0.50 * inch, y - 0.08 * inch, ancho - 0.50 * inch, y - 0.08 * inch)
            y -= 0.23 * inch

    if cierre.observaciones:
        y -= 0.16 * inch
        pdf.setFillColorRGB(0.098, 0.094, 0.094)
        pdf.setFont("Helvetica-Bold", 8.4)
        pdf.drawString(0.50 * inch, y, "Observaciones:")
        pdf.setFont("Helvetica", 8.2)
        for linea in _envolver_texto(cierre.observaciones, 95):
            y -= 0.15 * inch
            pdf.drawString(0.55 * inch, y, linea)

    y_firma = max(1.05 * inch, y - 0.85 * inch)
    pdf.setStrokeColorRGB(0.55, 0.55, 0.55)
    pdf.setLineWidth(0.7)
    pdf.line(0.85 * inch, y_firma, 3.45 * inch, y_firma)
    pdf.line(ancho - 3.45 * inch, y_firma, ancho - 0.85 * inch, y_firma)
    pdf.setFillColorRGB(0.098, 0.094, 0.094)
    pdf.setFont("Helvetica-Bold", 8.4)
    pdf.drawCentredString(2.15 * inch, y_firma - 0.16 * inch, "Elaborado por")
    pdf.drawCentredString(ancho - 2.15 * inch, y_firma - 0.16 * inch, "Revisado por Dirección / Admin.")
    pdf.setFont("Helvetica", 7.8)
    pdf.setFillColorRGB(0.4, 0.4, 0.4)
    pdf.drawCentredString(2.15 * inch, y_firma - 0.30 * inch, usr_nom)

    pdf.save()
    return buffer.getvalue()
