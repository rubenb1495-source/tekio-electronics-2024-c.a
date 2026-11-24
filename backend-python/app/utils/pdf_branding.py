from __future__ import annotations

from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas


ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
RUTA_MARCA_AGUA = ASSETS_DIR / "tekio-watermark.png"
RUTA_ISOTIPO = ASSETS_DIR / "tekio-isotipo.png"


def dibujar_marca_de_agua(pdf_canvas: Canvas, doc: Any = None) -> None:
    """
    Dibuja la marca de agua oficial de Tekio Electronics centrada detrás del contenido
    de cada página con opacidad sutil (~7%). Compatible con SimpleDocTemplate
    (onFirstPage / onLaterPages) y con uso directo sobre Canvas.
    """
    ancho, alto = getattr(doc, "pagesize", None) or getattr(pdf_canvas, "_pagesize", letter)
    lado = 3.8 * inch
    x = (ancho - lado) / 2
    y = (alto - lado) / 2

    pdf_canvas.saveState()
    if RUTA_MARCA_AGUA.exists():
        # Imagen preprocesada con 7% de canal alfa para compatibilidad universal en visores PDF
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
            pdf_canvas.setFillAlpha(0.07)
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
