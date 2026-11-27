from __future__ import annotations

from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

from app.core.empresa import (
    COLOR_CARBON,
    COLOR_FONDO,
    COLOR_GRIS_SECUNDARIO,
    COLOR_NARANJA,
    DOMICILIO_FISCAL_CORTO,
    ESLOGAN,
    RAZON_SOCIAL,
    RIF,
    TELEFONO_ADMIN,
    TELEFONO_SOPORTE,
    obtener_telefono_sede,
)


ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
RUTA_MARCA_AGUA = ASSETS_DIR / "tekio-watermark.png"
RUTA_ISOTIPO = ASSETS_DIR / "tekio-isotipo.png"
RUTA_LOGO_HORIZONTAL = ASSETS_DIR / "tekio-logo-horizontal.png"

HEX_NARANJA = colors.HexColor(COLOR_NARANJA)
HEX_CARBON = colors.HexColor(COLOR_CARBON)
HEX_FONDO = colors.HexColor(COLOR_FONDO)
HEX_GRIS = colors.HexColor(COLOR_GRIS_SECUNDARIO)
HEX_BORDE = colors.HexColor("#E5E7EB")


def dibujar_pie_corporativo(pdf_canvas: Canvas, doc: Any = None) -> None:
    """Dibuja la franja inferior Naranja Tekio (#E85A28), contactos oficiales y eslogan."""
    ancho, _alto = getattr(doc, "pagesize", None) or getattr(pdf_canvas, "_pagesize", letter)
    pdf_canvas.saveState()

    # Franja inferior delgada en Naranja Tekio (#E85A28)
    pdf_canvas.setFillColor(HEX_NARANJA)
    pdf_canvas.rect(0, 0, ancho, 6, stroke=0, fill=1)

    # Línea de contacto y eslogan encima de la franja
    pdf_canvas.setFont("Helvetica", 6.8)
    pdf_canvas.setFillColor(HEX_GRIS)
    texto_contacto = (
        f"{RAZON_SOCIAL} · RIF {RIF} · "
        f"Tekio Central: 0412-5284961 · Tekio Gran Bazar: 0422-5556609 · "
        f"Tekio Support: {TELEFONO_SOPORTE} · Admin: {TELEFONO_ADMIN}"
    )
    pdf_canvas.drawString(0.5 * inch, 14, texto_contacto)

    pdf_canvas.setFont("Helvetica-BoldOblique", 7.5)
    pdf_canvas.setFillColor(HEX_NARANJA)
    pdf_canvas.drawRightString(ancho - 0.5 * inch, 14, ESLOGAN)

    pdf_canvas.restoreState()


def dibujar_marca_de_agua(pdf_canvas: Canvas, doc: Any = None) -> None:
    """
    Dibuja la marca de agua oficial de Tekio Electronics centrada detrás del contenido
    de cada página con opacidad sutil (~6%) y la papelería inferior del Manual de Marca.
    Compatible con SimpleDocTemplate (onFirstPage / onLaterPages) y Canvas directo.
    """
    ancho, alto = getattr(doc, "pagesize", None) or getattr(pdf_canvas, "_pagesize", letter)
    lado = 3.6 * inch
    x = (ancho - lado) / 2
    y = (alto - lado) / 2

    pdf_canvas.saveState()
    if RUTA_MARCA_AGUA.exists():
        pdf_canvas.drawImage(
            str(RUTA_MARCA_AGUA),
            x,
            y,
            width=lado,
            height=lado,
            preserveAspectRatio=True,
            mask="auto",
        )
    elif RUTA_ISOTIPO.exists():
        if hasattr(pdf_canvas, "setFillAlpha"):
            pdf_canvas.setFillAlpha(0.06)
        pdf_canvas.drawImage(
            str(RUTA_ISOTIPO),
            x,
            y,
            width=lado,
            height=lado,
            preserveAspectRatio=True,
            mask="auto",
        )
    pdf_canvas.restoreState()
    dibujar_pie_corporativo(pdf_canvas, doc)


def construir_encabezado_corporativo(
    titulo_documento: str,
    *,
    subtitulo: str = "",
    sede: str | None = None,
    tipo_documento: str = "GENERAL",
    ancho_util: float = 7.3 * inch,
) -> list[Any]:
    """
    Encabezado estilo hoja membretada oficial del Manual de Marca Tekio:
    - Fondo blanco limpio (#FFFFFF)
    - Izquierda: imagotipo horizontal respetando zona de respeto
    - Derecha: Razón Social, RIF, Domicilio Fiscal abreviado y teléfonos oficiales
    - Separador fino en Naranja Tekio (#E85A28)
    """
    tel_sede = obtener_telefono_sede(sede)
    extras_tel: list[str] = []
    if sede:
        extras_tel.append(f"Sede {sede}: {tel_sede}")
    if tipo_documento.upper() == "TALLER":
        extras_tel.append(f"Tekio Support: {TELEFONO_SOPORTE}")
    elif tipo_documento.upper() == "FINANZAS":
        extras_tel.append(f"Administración: {TELEFONO_ADMIN}")
    elif not sede:
        extras_tel.append(f"Administración: {TELEFONO_ADMIN}")

    estilo_der = ParagraphStyle(
        "TekioHeaderDer",
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        alignment=2,  # RIGHT
        textColor=HEX_GRIS,
    )
    estilo_titulo = ParagraphStyle(
        "TekioDocTitulo",
        fontName="Helvetica-Bold",
        fontSize=12.5,
        leading=15,
        textColor=HEX_CARBON,
    )
    estilo_sub = ParagraphStyle(
        "TekioDocSub",
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=HEX_GRIS,
    )

    if RUTA_LOGO_HORIZONTAL.exists():
        celda_logo: Any = Image(str(RUTA_LOGO_HORIZONTAL), width=1.85 * inch, height=0.52 * inch)
        celda_logo.hAlign = "LEFT"
    else:
        celda_logo = Paragraph(f"<b><font color='{COLOR_NARANJA}'>tekio</font></b>", estilo_titulo)

    bloque_fiscal = Paragraph(
        f"<b><font color='{COLOR_CARBON}'>{RAZON_SOCIAL}</font></b><br/>"
        f"RIF: <b>{RIF}</b><br/>"
        f"{DOMICILIO_FISCAL_CORTO}<br/>"
        f"<font color='{COLOR_NARANJA}'><b>{' · '.join(extras_tel)}</b></font>",
        estilo_der,
    )

    tabla_cab = Table(
        [[celda_logo, bloque_fiscal]],
        colWidths=[2.2 * inch, max(ancho_util - 2.2 * inch, 3.5 * inch)],
    )
    tabla_cab.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, 0), (-1, 0), 1.5, HEX_NARANJA),
            ]
        )
    )

    elementos: list[Any] = [tabla_cab, Spacer(1, 8), Paragraph(titulo_documento, estilo_titulo)]
    if subtitulo:
        elementos.append(Paragraph(subtitulo, estilo_sub))
    elementos.append(Spacer(1, 8))
    return elementos


def estilo_tabla_corporativa() -> list[tuple[Any, ...]]:
    """
    Estilo Light-First del Manual de Marca para tablas en PDF:
    cabecera gris muy claro (#F6F6F6) con borde inferior naranja (#E85A28)
    y tipografía en Gris Carbón (#191818), sin bloques negros.
    """
    return [
        ("BACKGROUND", (0, 0), (-1, 0), HEX_FONDO),
        ("TEXTCOLOR", (0, 0), (-1, 0), HEX_CARBON),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, HEX_NARANJA),
        ("GRID", (0, 1), (-1, -1), 0.35, HEX_BORDE),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("TEXTCOLOR", (0, 1), (-1, -1), HEX_CARBON),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
