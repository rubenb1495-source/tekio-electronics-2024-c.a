from __future__ import annotations

from typing import TypedDict


class SedeOficial(TypedDict):
    codigo: str
    nombre: str
    nombre_anterior: str
    tipo: str
    telefono: str
    direccion: str


RAZON_SOCIAL = "TEKIO ELECTRONICS 2024, C.A."
RIF = "J-50637518-4"
DOMICILIO_FISCAL = (
    "Av. Principal C.C. Freemarket, Nivel Mezzanina, Local Mini Tienda X47 y X48, "
    "Módulo 13, Urb. La Granja, Naguanagua, Carabobo, Zona Postal 2005"
)
DOMICILIO_FISCAL_CORTO = (
    "C.C. Freemarket, Mezzanina, Locales X47-X48, Mód. 13, Urb. La Granja, Naguanagua, Carabobo (2005)"
)
ESLOGAN = "Somos tu solución"
TELEFONO_ADMIN = "0424-2231879"
TELEFONO_SOPORTE = "0422-5284961"
FECHA_CORTE_APERTURA = "2026-12-01"
NOTA_FISCAL_SENIAT = (
    f"RIF {RIF} · Condición de retención del 100% de IVA aplicable para referencia administrativa SENIAT."
)

# Paleta oficial Manual de Marca Tekio (Light-First)
COLOR_NARANJA = "#E85A28"
COLOR_NARANJA_HOVER = "#D14D20"
COLOR_NARANJA_SUAVE = "#FDF0EB"
COLOR_CARBON = "#191818"
COLOR_FONDO = "#F6F6F6"
COLOR_BLANCO = "#FFFFFF"
COLOR_GRIS_SECUNDARIO = "#525252"

SEDES_OFICIALES: tuple[SedeOficial, ...] = (
    {
        "codigo": "DEPOSITO_TALLER",
        "nombre": "Depósito / Tekio Support (Taller)",
        "nombre_anterior": "Bodega",
        "tipo": "DEPOSITO_TALLER",
        "telefono": "0422-5284961",
        "direccion": "Depósito Central y Taller Tekio Support, Naguanagua, Carabobo",
    },
    {
        "codigo": "TEKIO_CENTRAL",
        "nombre": "Tekio Central",
        "nombre_anterior": "Tekio central",
        "tipo": "TIENDA",
        "telefono": "0412-5284961",
        "direccion": DOMICILIO_FISCAL,
    },
    {
        "codigo": "TEKIO_GRAN_BAZAR",
        "nombre": "Tekio Gran Bazar",
        "nombre_anterior": "Gran Bazar",
        "tipo": "TIENDA",
        "telefono": "0422-5556609",
        "direccion": "C.C. Gran Bazar, Centro, Local ML174, Valencia, Carabobo",
    },
)


def obtener_telefono_sede(nombre_sede: str | None) -> str:
    """Devuelve el teléfono oficial de la sede indicada (o Administración por defecto)."""
    if not nombre_sede:
        return TELEFONO_ADMIN
    n = nombre_sede.strip().lower()
    if "gran bazar" in n:
        return "0422-5556609"
    if "central" in n or "freemarket" in n:
        return "0412-5284961"
    if "depósito" in n or "deposito" in n or "support" in n or "taller" in n or "bodega" in n:
        return TELEFONO_SOPORTE
    return TELEFONO_ADMIN
