from __future__ import annotations

import sys
from pathlib import Path

_RAIZ_BACKEND = Path(__file__).resolve().parent.parent
if str(_RAIZ_BACKEND) not in sys.path:
    sys.path.insert(0, str(_RAIZ_BACKEND))

from sqlalchemy.orm import Session

from app.modelos_finanzas import (
    InstrumentoFinanciero,
    MonedaInstrumento,
    TipoPrecioInstrumento,
)


# Renombres seguros de nombres anteriores -> nombres oficiales definitivos (sin borrar historial)
RENOMBRES_INSTRUMENTOS: dict[str, str] = {
    "Efectivo USD": "Efectivo divisas",
    "Punto de venta Banesco": "Punto de venta Banesco (Bs)",
    "Pago móvil Mercantil": "Pago móvil Mercantil (Bs)",
    "BNC Jurídico": "BNC Jurídico (Bs)",
    "Bancamiga Pago Móvil": "Bancamiga (Bs)",
}

# Catálogo oficial exacto de 14 instrumentos financieros de Tekio Electronics
INSTRUMENTOS_INICIALES = [
    # Divisas / Cripto (PROMO, liquida_en_bs=False)
    ("Efectivo divisas", MonedaInstrumento.USD.value, TipoPrecioInstrumento.PROMO.value, False, False),
    ("Binance (USDT)", MonedaInstrumento.USDT.value, TipoPrecioInstrumento.PROMO.value, True, False),
    ("Zelle", MonedaInstrumento.USD.value, TipoPrecioInstrumento.PROMO.value, True, False),
    ("Zinli", MonedaInstrumento.USD.value, TipoPrecioInstrumento.PROMO.value, True, False),
    ("PayPal", MonedaInstrumento.USD.value, TipoPrecioInstrumento.PROMO.value, True, False),
    ("Banesco Panamá", MonedaInstrumento.USD.value, TipoPrecioInstrumento.PROMO.value, True, False),
    ("Bancamiga (USD)", MonedaInstrumento.USD.value, TipoPrecioInstrumento.PROMO.value, True, False),
    # Bolívares (REGULAR, liquida_en_bs=True, requiere_verificacion=True)
    ("Punto de venta Banesco (Bs)", MonedaInstrumento.BS.value, TipoPrecioInstrumento.REGULAR.value, True, True),
    ("Pago móvil Mercantil (Bs)", MonedaInstrumento.BS.value, TipoPrecioInstrumento.REGULAR.value, True, True),
    ("BNC Jurídico (Bs)", MonedaInstrumento.BS.value, TipoPrecioInstrumento.REGULAR.value, True, True),
    ("Bancamiga (Bs)", MonedaInstrumento.BS.value, TipoPrecioInstrumento.REGULAR.value, True, True),
    # Financiamiento y especiales
    ("Cashea · financiado", MonedaInstrumento.BS.value, TipoPrecioInstrumento.REGULAR.value, True, True),
    ("Equipo como parte de pago", MonedaInstrumento.USD.value, TipoPrecioInstrumento.PROMO.value, False, False),
    ("Cuenta por cobrar", MonedaInstrumento.USD.value, TipoPrecioInstrumento.PROMO.value, False, False),
]


def ejecutar_semilla_finanzas(bd: Session) -> None:
    """Sincroniza de forma idempotente los 14 instrumentos oficiales sin borrar historial."""
    # 1. Renombrar instrumentos previos en sitio si aún no existe el nombre destino
    for nombre_viejo, nombre_nuevo in RENOMBRES_INSTRUMENTOS.items():
        viejo = bd.query(InstrumentoFinanciero).filter(InstrumentoFinanciero.nombre == nombre_viejo).first()
        nuevo = bd.query(InstrumentoFinanciero).filter(InstrumentoFinanciero.nombre == nombre_nuevo).first()
        if viejo is not None and nuevo is None:
            viejo.nombre = nombre_nuevo
    bd.flush()

    nombres_oficiales = {item[0] for item in INSTRUMENTOS_INICIALES}

    # 2. Crear o actualizar propiedades de los 14 instrumentos oficiales
    for nombre, moneda, tipo_precio, req_verif, liq_bs in INSTRUMENTOS_INICIALES:
        existente = (
            bd.query(InstrumentoFinanciero)
            .filter(InstrumentoFinanciero.nombre == nombre)
            .first()
        )
        if existente is None:
            bd.add(
                InstrumentoFinanciero(
                    nombre=nombre,
                    moneda=moneda,
                    tipo_precio=tipo_precio,
                    requiere_verificacion=req_verif,
                    liquida_en_bs=liq_bs,
                    activo=True,
                )
            )
        else:
            existente.moneda = moneda
            existente.tipo_precio = tipo_precio
            existente.requiere_verificacion = req_verif
            existente.liquida_en_bs = liq_bs
            existente.activo = True

    # 3. Desactivar lógicamente cualquier instrumento heredado fuera de los 14 oficiales (nunca DELETE)
    for inst in bd.query(InstrumentoFinanciero).all():
        if inst.nombre not in nombres_oficiales and inst.activo:
            inst.activo = False

    bd.commit()


if __name__ == "__main__":
    import sys
    from pathlib import Path

    raiz_backend = Path(__file__).resolve().parent.parent
    if str(raiz_backend) not in sys.path:
        sys.path.insert(0, str(raiz_backend))

    import app.main  # noqa: F401 - registra todos los modelos ORM
    from app.base_datos import Base, SesionLocal, motor

    Base.metadata.create_all(bind=motor)
    bd = SesionLocal()
    try:
        ejecutar_semilla_finanzas(bd)
        activos = (
            bd.query(InstrumentoFinanciero)
            .filter(InstrumentoFinanciero.activo.is_(True))
            .order_by(InstrumentoFinanciero.id.asc())
            .all()
        )
        print(f"Semilla de instrumentos completada ({len(activos)} activos):")
        for idx, inst in enumerate(activos, 1):
            print(f"  {idx:2d}. {inst.nombre} ({inst.moneda} | {inst.tipo_precio})")
    finally:
        bd.close()
