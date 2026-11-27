from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.empresa import SEDES_OFICIALES
from app.modelos import EstadoSucursal, RolUsuario, Sucursal, Usuario
from app.seguridad import generar_hash_clave


SUCURSALES_HISTORICAS = [
    {
        "nombre": "INFOT",
        "direccion": "CC INFOT (Sede cerrada — solo histórico y cobranzas)",
        "telefono": "",
        "tipo": "HISTORICO",
        "estado": EstadoSucursal.CERRADA.value,
        "fecha_cierre": date(2026, 11, 8),
    },
    {
        "nombre": "Free Market C13",
        "direccion": "CC Free Market, local C13 (Sede cerrada — solo histórico y cobranzas)",
        "telefono": "",
        "tipo": "HISTORICO",
        "estado": EstadoSucursal.CERRADA.value,
        "fecha_cierre": date(2026, 11, 16),
    },
]


def ejecutar_semilla(bd: Session) -> None:
    """
    Crea y actualiza de forma idempotente las 3 sedes operativas oficiales de Tekio
    (conservando IDs existentes en Neon/SQLite), las 2 sedes históricas cerradas
    y el usuario DIRECCION inicial.
    """
    for sede in SEDES_OFICIALES:
        existente = (
            bd.query(Sucursal)
            .filter(
                (Sucursal.nombre == sede["nombre"])
                | (Sucursal.nombre == sede["nombre_anterior"])
            )
            .first()
        )
        if existente is None:
            bd.add(
                Sucursal(
                    nombre=sede["nombre"],
                    direccion=sede["direccion"],
                    telefono=sede["telefono"],
                    tipo=sede["tipo"],
                    estado=EstadoSucursal.ACTIVA.value,
                    fecha_cierre=None,
                )
            )
        else:
            existente.nombre = sede["nombre"]
            existente.direccion = sede["direccion"]
            existente.telefono = sede["telefono"]
            existente.tipo = sede["tipo"]
            existente.estado = EstadoSucursal.ACTIVA.value

    for datos in SUCURSALES_HISTORICAS:
        existente = bd.query(Sucursal).filter(Sucursal.nombre == datos["nombre"]).first()
        if existente is None:
            bd.add(Sucursal(**datos))
        else:
            existente.tipo = datos["tipo"]

    bd.flush()

    sucursal_central = bd.query(Sucursal).filter(Sucursal.nombre == "Tekio Central").first()

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
