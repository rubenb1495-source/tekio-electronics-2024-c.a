"use client";

import { useMemo } from "react";
import { usarSesion } from "@/contexto/SesionContexto";
import type { RolUsuario } from "@/tipos/dominio";

export interface PermisosUsuario {
  rol: RolUsuario | null;
  esAdmin: boolean;
  esDireccion: boolean;
  esEncargado: boolean;
  puedeAnular: boolean;
  puedeAutorizarReembolso: boolean;
  puedeVerCostos: boolean;
  puedeGestionarCatalogo: boolean;
  puedeGestionarCompras: boolean;
  puedeRegistrarTraslados: boolean;
  puedeLiquidar: boolean;
  puedeVerComisiones: boolean;
  puedeVerFinanzasGlobales: boolean;
  puedeGestionarUsuarios: boolean;
  puedeEditarTasasManual: boolean;
  puedeTaller: boolean;
  sucursalRestringidaId: number | null;
}

export function obtenerPermisos(
  rol: RolUsuario | null | undefined,
  sucursalId?: number | null
): PermisosUsuario {
  const r = rol ?? null;
  const esAdmin = r === "DIRECCION" || r === "ADMINISTRACION";
  const esDireccion = r === "DIRECCION";
  const esEncargado = r === "ENCARGADO";
  const esLogistica =
    esAdmin || r === "LOGISTICA" || r === "LIDER";

  return {
    rol: r,
    esAdmin,
    esDireccion,
    esEncargado,
    puedeAnular: esAdmin,
    puedeAutorizarReembolso: esAdmin,
    puedeVerCostos: esLogistica,
    puedeGestionarCatalogo: esLogistica,
    puedeGestionarCompras: esLogistica,
    puedeRegistrarTraslados: esLogistica || esEncargado,
    puedeLiquidar: esAdmin,
    puedeVerComisiones: esAdmin || esEncargado,
    puedeVerFinanzasGlobales: esAdmin,
    puedeGestionarUsuarios: esAdmin,
    puedeEditarTasasManual: esAdmin,
    puedeTaller: esLogistica || r === "TECNICO",
    sucursalRestringidaId: esAdmin ? null : (sucursalId ?? null),
  };
}

/**
 * Guardia centralizada de rutas del dashboard.
 * Retorna false si el rol autenticado no tiene permiso para visitar la ruta.
 */
export function puedeAccederRuta(
  ruta: string,
  rol: RolUsuario | null | undefined
): boolean {
  if (!rol) return false;
  const p = obtenerPermisos(rol);

  // Administración y usuarios
  if (ruta.startsWith("/dashboard/usuarios")) {
    return p.puedeGestionarUsuarios;
  }

  // Panel Ejecutivo de Dirección
  if (ruta.startsWith("/dashboard/direccion")) {
    return p.esAdmin;
  }

  // Finanzas globales (bancos, pagos, CxC, Cashea, conciliación, tesorería)
  if (
    ruta.startsWith("/dashboard/finanzas/pagos") ||
    ruta.startsWith("/dashboard/finanzas/cashea") ||
    ruta.startsWith("/dashboard/finanzas/conciliacion") ||
    ruta.startsWith("/dashboard/finanzas/tesoreria")
  ) {
    return p.puedeVerFinanzasGlobales;
  }

  // Comisiones (Admin: total + liquidar; Encargado: lectura de su sucursal/propias)
  if (ruta.startsWith("/dashboard/finanzas/comisiones")) {
    return p.puedeVerComisiones;
  }

  // Compras, guías y recepción por serial (exclusivo logística/admin, bloqueado para ENCARGADO)
  if (
    ruta.startsWith("/dashboard/logistica/compras") ||
    ruta.startsWith("/dashboard/logistica/guias") ||
    ruta.startsWith("/dashboard/logistica/recepcion")
  ) {
    return p.puedeGestionarCompras;
  }

  // Taller técnico especializado
  if (
    ruta.startsWith("/dashboard/taller/preparaciones") ||
    ruta.startsWith("/dashboard/taller/repuestos") ||
    ruta.startsWith("/dashboard/taller/mi-resumen")
  ) {
    return p.puedeTaller;
  }

  return true;
}

export function usePermisos(): PermisosUsuario {
  const { usuario } = usarSesion();
  return useMemo(
    () => obtenerPermisos(usuario?.rol, usuario?.sucursal?.id ?? null),
    [usuario?.rol, usuario?.sucursal?.id]
  );
}
