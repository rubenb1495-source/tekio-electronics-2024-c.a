from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any

from fastapi import Depends, HTTPException, status

from app.modelos import RolUsuario, Usuario
from app.seguridad import ROLES_ADMINISTRATIVOS, obtener_usuario_actual, puede_ver_costos


ROLES_ADMIN: frozenset[str] = frozenset(ROLES_ADMINISTRATIVOS)

ROLES_TODOS: frozenset[str] = frozenset(r.value for r in RolUsuario)

ROLES_OPERATIVOS_POS: frozenset[str] = frozenset({
    RolUsuario.DIRECCION.value,
    RolUsuario.ADMINISTRACION.value,
    RolUsuario.LOGISTICA.value,
    RolUsuario.ENCARGADO.value,
    RolUsuario.LIDER.value,
    RolUsuario.ASESORA.value,
})

ROLES_GESTION_LOGISTICA: frozenset[str] = frozenset({
    RolUsuario.DIRECCION.value,
    RolUsuario.ADMINISTRACION.value,
    RolUsuario.LOGISTICA.value,
    RolUsuario.LIDER.value,
})

ROLES_TRASLADOS_SUCURSAL: frozenset[str] = ROLES_GESTION_LOGISTICA | frozenset({
    RolUsuario.ENCARGADO.value,
})


class Permiso(str, Enum):
    """Matriz centralizada de permisos operativos y administrativos."""

    # Operaciones POS / Comercial
    EMITIR_VENTA = "EMITIR_VENTA"
    ANULAR_VENTA = "ANULAR_VENTA"
    CREAR_COTIZACION = "CREAR_COTIZACION"
    GESTIONAR_CLIENTES = "GESTIONAR_CLIENTES"
    GESTIONAR_CAMBIO_GARANTIA = "GESTIONAR_CAMBIO_GARANTIA"
    AUTORIZAR_REEMBOLSO = "AUTORIZAR_REEMBOLSO"

    # Catálogo, Inventario y Logística
    VER_COSTOS = "VER_COSTOS"
    GESTIONAR_CATALOGO = "GESTIONAR_CATALOGO"
    GESTIONAR_COMPRAS = "GESTIONAR_COMPRAS"
    GESTIONAR_PROVEEDORES = "GESTIONAR_PROVEEDORES"
    REGISTRAR_TRASLADO = "REGISTRAR_TRASLADO"
    CONFIRMAR_TRASLADO = "CONFIRMAR_TRASLADO"

    # Finanzas, Comisiones y Cierre de Caja
    VER_FINANZAS_GLOBALES = "VER_FINANZAS_GLOBALES"
    VER_COMISIONES = "VER_COMISIONES"
    LIQUIDAR_COMISIONES = "LIQUIDAR_COMISIONES"
    CIERRE_CAJA = "CIERRE_CAJA"
    CONFIRMAR_RECARGO_DIARIO = "CONFIRMAR_RECARGO_DIARIO"
    EDITAR_TASAS_MANUAL = "EDITAR_TASAS_MANUAL"

    # Administración del sistema
    GESTIONAR_USUARIOS = "GESTIONAR_USUARIOS"


MATRIZ_PERMISOS: dict[Permiso, frozenset[str]] = {
    Permiso.EMITIR_VENTA: ROLES_OPERATIVOS_POS,
    Permiso.ANULAR_VENTA: ROLES_ADMIN,
    Permiso.CREAR_COTIZACION: ROLES_OPERATIVOS_POS,
    Permiso.GESTIONAR_CLIENTES: ROLES_OPERATIVOS_POS,
    Permiso.GESTIONAR_CAMBIO_GARANTIA: ROLES_TODOS,
    Permiso.AUTORIZAR_REEMBOLSO: ROLES_ADMIN,
    Permiso.VER_COSTOS: ROLES_GESTION_LOGISTICA,
    Permiso.GESTIONAR_CATALOGO: ROLES_GESTION_LOGISTICA,
    Permiso.GESTIONAR_COMPRAS: ROLES_GESTION_LOGISTICA,
    Permiso.GESTIONAR_PROVEEDORES: ROLES_GESTION_LOGISTICA,
    Permiso.REGISTRAR_TRASLADO: ROLES_TRASLADOS_SUCURSAL,
    Permiso.CONFIRMAR_TRASLADO: ROLES_TODOS,
    Permiso.VER_FINANZAS_GLOBALES: ROLES_ADMIN,
    Permiso.VER_COMISIONES: ROLES_ADMIN | frozenset({RolUsuario.ENCARGADO.value}),
    Permiso.LIQUIDAR_COMISIONES: ROLES_ADMIN,
    Permiso.CIERRE_CAJA: ROLES_OPERATIVOS_POS,
    Permiso.CONFIRMAR_RECARGO_DIARIO: ROLES_TODOS,
    Permiso.EDITAR_TASAS_MANUAL: ROLES_ADMIN,
    Permiso.GESTIONAR_USUARIOS: ROLES_ADMIN,
}

MENSAJES_PERMISO: dict[Permiso, str] = {
    Permiso.ANULAR_VENTA: "Solo Administración o Dirección puede anular ventas.",
    Permiso.AUTORIZAR_REEMBOLSO: "Solo Administración o Dirección puede autorizar reembolsos de dinero.",
    Permiso.VER_COSTOS: "No tienes permisos para consultar costos, márgenes ni proveedores.",
    Permiso.GESTIONAR_CATALOGO: "No tienes permisos para crear o modificar artículos y precios del catálogo.",
    Permiso.GESTIONAR_COMPRAS: "No tienes permisos para gestionar compras ni importaciones.",
    Permiso.GESTIONAR_PROVEEDORES: "No tienes permisos para consultar o gestionar proveedores.",
    Permiso.REGISTRAR_TRASLADO: "No tienes permisos para registrar traslados de inventario.",
    Permiso.VER_FINANZAS_GLOBALES: "Solo Administración o Dirección puede acceder a finanzas globales, bancos y conciliación.",
    Permiso.VER_COMISIONES: "No tienes permisos para consultar el reporte de comisiones.",
    Permiso.LIQUIDAR_COMISIONES: "Solo Administración o Dirección puede liquidar comisiones y generar egresos.",
    Permiso.CIERRE_CAJA: "No tienes permisos para consultar o registrar cierres de caja.",
    Permiso.EDITAR_TASAS_MANUAL: "Solo Administración o Dirección puede modificar tasas manuales de emergencia.",
    Permiso.GESTIONAR_USUARIOS: "Solo Administración o Dirección puede gestionar personal, usuarios y roles.",
}

PREFIJOS_SENSIBLES: tuple[str, ...] = ("costo_", "margen_", "proveedor_")
CLAVES_SENSIBLES_EXACTAS: frozenset[str] = frozenset({
    "costo",
    "margen",
    "proveedor",
    "ganancia_usd",
    "utilidad_usd",
})


def es_rol_admin(rol: str) -> bool:
    return rol in ROLES_ADMIN


def tiene_permiso(rol: str, permiso: Permiso) -> bool:
    return rol in MATRIZ_PERMISOS.get(permiso, frozenset())


def require_roles(*roles_permitidos: str, mensaje: str | None = None) -> Callable[[Usuario], Usuario]:
    """Dependencia reutilizable de FastAPI que restringe el acceso a los roles indicados."""
    conjunto = frozenset(roles_permitidos)
    detalle = mensaje or "No tienes permisos suficientes para realizar esta operación."

    def _validador(usuario_actual: Usuario = Depends(obtener_usuario_actual)) -> Usuario:
        if usuario_actual.rol not in conjunto:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detalle)
        return usuario_actual

    return _validador


def require_permiso(permiso: Permiso, mensaje: str | None = None) -> Callable[[Usuario], Usuario]:
    """Dependencia reutilizable de FastAPI basada en la matriz centralizada de permisos."""
    roles_permitidos = MATRIZ_PERMISOS.get(permiso, frozenset())
    detalle = mensaje or MENSAJES_PERMISO.get(
        permiso,
        "No tienes permisos suficientes para realizar esta operación.",
    )

    def _validador(usuario_actual: Usuario = Depends(obtener_usuario_actual)) -> Usuario:
        if usuario_actual.rol not in roles_permitidos:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detalle)
        return usuario_actual

    return _validador


def validar_sucursal_permitida(
    usuario: Usuario,
    sucursal_id: int | None,
    *,
    contexto: str = "esta operación",
) -> int | None:
    """
    Aplica restricción de sucursal para roles no administrativos (ej. ENCARGADO).
    - Administración/Dirección: puede consultar/operar en cualquier sucursal o en Todas (None).
    - Encargado/no-admin: siempre restringido a su `usuario.sucursal_id`; si solicita otra, retorna 403.
    """
    if es_rol_admin(usuario.rol):
        return sucursal_id
    if usuario.sucursal_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tu usuario no tiene una sucursal asignada para realizar {contexto}.",
        )
    if sucursal_id is not None and sucursal_id != usuario.sucursal_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Solo puedes realizar {contexto} para tu sucursal asignada.",
        )
    return usuario.sucursal_id


def _es_clave_sensible(clave: str) -> bool:
    clave_norm = clave.lower()
    if clave_norm in CLAVES_SENSIBLES_EXACTAS:
        return True
    return any(clave_norm.startswith(prefijo) for prefijo in PREFIJOS_SENSIBLES)


def sanear_respuesta_costos(datos: Any, rol: str) -> Any:
    """
    Elimina recursivamente campos `costo_*`, `margen_*` y `proveedor_*`
    de diccionarios/listas cuando el rol autenticado no puede ver costos.
    """
    if puede_ver_costos(rol):
        return datos
    if isinstance(datos, dict):
        return {
            k: sanear_respuesta_costos(v, rol)
            for k, v in datos.items()
            if not _es_clave_sensible(str(k))
        }
    if isinstance(datos, list):
        return [sanear_respuesta_costos(item, rol) for item in datos]
    return datos
