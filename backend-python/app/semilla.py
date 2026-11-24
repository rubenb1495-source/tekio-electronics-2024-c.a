from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.modelos import EstadoSucursal, RolUsuario, Sucursal, Usuario
from app.seguridad import generar_hash_clave


SUCURSALES_INICIALES = [
    {
        "nombre": "Bodega",
        "direccion": "Almacén central y recepción de compras/guías, Valencia",
        "estado": EstadoSucursal.ACTIVA.value,
        "fecha_cierre": None,
    },
    {
        "nombre": "Tekio central",
        "direccion": "Av. Universidad, CC Free Market, locales X47-X48, Naguanagua, Valencia",
        "estado": EstadoSucursal.ACTIVA.value,
        "fecha_cierre": None,
    },
    {
        "nombre": "Gran Bazar",
        "direccion": "CC Gran Bazar, Centro, local ML174, Valencia",
        "estado": EstadoSucursal.ACTIVA.value,
        "fecha_cierre": None,
    },
    {
        "nombre": "INFOT",
        "direccion": "CC INFOT (Sede cerrada — solo histórico y cobranzas)",
        "estado": EstadoSucursal.CERRADA.value,
        "fecha_cierre": date(2026, 11, 8),
    },
    {
        "nombre": "Free Market C13",
        "direccion": "CC Free Market, local C13 (Sede cerrada — solo histórico y cobranzas)",
        "estado": EstadoSucursal.CERRADA.value,
        "fecha_cierre": date(2026, 11, 16),
    },
]


def ejecutar_semilla(bd: Session) -> None:
    """Crea de forma idempotente las 5 sucursales reales de Tekio y el usuario DIRECCION inicial."""
    for datos in SUCURSALES_INICIALES:
        existente = bd.query(Sucursal).filter(Sucursal.nombre == datos["nombre"]).first()
        if existente is None:
            bd.add(Sucursal(**datos))
    bd.flush()

    sucursal_central = bd.query(Sucursal).filter(Sucursal.nombre == "Tekio central").first()

    correo_admin = "direccion@tekioelectronics.com"
    admin_existente = bd.query(Usuario).filter(Usuario.correo == correo_admin).first()
    if admin_existente is None:
        bd.add(
            Usuario(
                nombre="Dirección General Tekio",
                correo=correo_admin,
                clave_hash=generar_hash_clave("Tekio2026!"),
                rol=RolUsuario.DIRECCION.value,
                sucursal_id=sucursal_central.id if sucursal_central else None,
                activo=True,
            )
        )

    bd.commit()
