"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeftRight,
  Award,
  BarChart3,
  Boxes,
  CheckSquare,
  ClipboardList,
  Cpu,
  CreditCard,
  FileSpreadsheet,
  LogOut,
  Menu,
  Package,
  Plane,
  Receipt,
  RefreshCw,
  RotateCcw,
  ScanBarcode,
  Shield,
  ShoppingBag,
  ShoppingCart,
  Truck,
  Users,
  Wrench,
  X,
} from "lucide-react";
import { usarSesion } from "@/contexto/SesionContexto";
import {
  esRolAdministrativo,
  formatearBs,
  formatearPorcentaje,
  puedeGestionarCatalogo,
} from "@/servicios/api";

export default function DisenoDashboard({
  children,
}: {
  children: React.ReactNode;
}) {
  const {
    usuario,
    cargandoSesion,
    tasaHoy,
    cargandoTasa,
    cerrarSesion,
    recargarTasaHoy,
  } = usarSesion();
  const router = useRouter();
  const rutaActual = usePathname();
  const [menuMovilAbierto, setMenuMovilAbierto] = useState(false);

  useEffect(() => {
    if (!cargandoSesion && !usuario) {
      router.replace("/login");
    }
  }, [usuario, cargandoSesion, router]);

  if (cargandoSesion || !usuario) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="space-y-3 text-center">
          <div className="h-8 w-48 mx-auto rounded-lg bg-slate-200 animate-pulse" />
          <p className="text-xs font-medium text-slate-500">
            Verificando sesión...
          </p>
        </div>
      </div>
    );
  }

  const esAdmin = esRolAdministrativo(usuario.rol);
  const esLogistica = puedeGestionarCatalogo(usuario.rol);
  const esTallerOAdmin = esLogistica || usuario.rol === "TECNICO";
  const enlaces = [
    {
      href: "/dashboard/ventas/nueva",
      etiqueta: "POS · Nueva Venta",
      icono: <ShoppingCart className="w-4 h-4" />,
      visible: true,
    },
    {
      href: "/dashboard/ventas",
      etiqueta: "Historial de Ventas",
      icono: <Receipt className="w-4 h-4" />,
      visible: true,
    },
    {
      href: "/dashboard/devoluciones",
      etiqueta: "Devoluciones / NC",
      icono: <RotateCcw className="w-4 h-4" />,
      visible: esLogistica,
    },
    {
      href: "/dashboard/tasas",
      etiqueta: "Tasas Diarias",
      icono: <ArrowLeftRight className="w-4 h-4" />,
      visible: true,
    },
    {
      href: "/dashboard/catalogo",
      etiqueta: "Catálogo y Precios",
      icono: <Package className="w-4 h-4" />,
      visible: true,
    },
    {
      href: "/dashboard/logistica/compras",
      etiqueta: "Compras e Importación",
      icono: <ShoppingBag className="w-4 h-4" />,
      visible: esLogistica,
    },
    {
      href: "/dashboard/logistica/guias",
      etiqueta: "Guías de Casillero",
      icono: <Plane className="w-4 h-4" />,
      visible: esLogistica,
    },
    {
      href: "/dashboard/logistica/recepcion",
      etiqueta: "Recepción por Serial",
      icono: <ScanBarcode className="w-4 h-4" />,
      visible: esLogistica,
    },
    {
      href: "/dashboard/logistica/traslados",
      etiqueta: "Traslados (2 Pasos)",
      icono: <Truck className="w-4 h-4" />,
      visible: true,
    },
    {
      href: "/dashboard/logistica/inventario",
      etiqueta: "Inventario y Ajustes",
      icono: <Boxes className="w-4 h-4" />,
      visible: true,
    },
    {
      href: "/dashboard/taller/preparaciones",
      etiqueta: "Taller · Preparaciones",
      icono: <Wrench className="w-4 h-4" />,
      visible: esTallerOAdmin,
    },
    {
      href: "/dashboard/taller/casos",
      etiqueta: "Taller · Casos GT/ST",
      icono: <ClipboardList className="w-4 h-4" />,
      visible: true,
    },
    {
      href: "/dashboard/taller/repuestos",
      etiqueta: "Taller · Repuestos",
      icono: <Cpu className="w-4 h-4" />,
      visible: esTallerOAdmin,
    },
    {
      href: "/dashboard/taller/mi-resumen",
      etiqueta: "Taller · Mi Resumen",
      icono: <Award className="w-4 h-4" />,
      visible: esTallerOAdmin,
    },
    {
      href: "/dashboard/finanzas/pagos",
      etiqueta: "Finanzas · Pagos y CxC",
      icono: <CheckSquare className="w-4 h-4" />,
      visible: esAdmin,
    },
    {
      href: "/dashboard/finanzas/cashea",
      etiqueta: "Finanzas · Cashea",
      icono: <CreditCard className="w-4 h-4" />,
      visible: esAdmin,
    },
    {
      href: "/dashboard/finanzas/conciliacion",
      etiqueta: "Finanzas · Conciliación",
      icono: <FileSpreadsheet className="w-4 h-4" />,
      visible: esAdmin,
    },
    {
      href: "/dashboard/finanzas/comisiones",
      etiqueta: "Comisiones y Cierre",
      icono: <BarChart3 className="w-4 h-4" />,
      visible: esAdmin,
    },
    {
      href: "/dashboard/usuarios",
      etiqueta: "Usuarios y Sedes",
      icono: <Users className="w-4 h-4" />,
      visible: esAdmin,
    },
  ].filter((e) => e.visible);

  const manejarSalir = () => {
    cerrarSesion();
    router.replace("/login");
  };

  return (
    <div className="min-h-screen flex bg-slate-50 text-slate-900">
      {/* Barra lateral escritorio */}
      <aside className="hidden lg:flex lg:flex-col w-64 bg-white border-r border-slate-200 shrink-0">
        <div className="p-5 bg-gradient-to-br from-[#E85A28] to-[#C9461A] text-white">
          <p className="text-[11px] font-bold uppercase tracking-widest text-orange-100">
            Tekio Electronics
          </p>
          <h1 className="text-lg font-black tracking-tight mt-0.5">
            Sistema Admin
          </h1>
          <p className="text-[11px] text-orange-100 mt-1">RIF: J-50637518-4</p>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {enlaces.map((enlace) => {
            const activo = rutaActual === enlace.href;
            return (
              <Link
                key={enlace.href}
                href={enlace.href}
                className={`flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl text-sm font-semibold transition-colors ${
                  activo
                    ? "bg-[#E85A28] text-white shadow-sm"
                    : "text-slate-700 hover:bg-orange-50 hover:text-[#E85A28]"
                }`}
              >
                {enlace.icono}
                <span>{enlace.etiqueta}</span>
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-slate-200 bg-slate-50 space-y-3">
          <div className="text-xs">
            <p className="font-bold text-slate-900 truncate">{usuario.nombre}</p>
            <p className="text-slate-500 truncate">{usuario.correo}</p>
            <div className="mt-1.5 flex items-center gap-1.5">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-orange-100 text-[#C9461A] font-bold text-[11px]">
                <Shield className="w-3 h-3" />
                {usuario.rol}
              </span>
              {usuario.sucursal && (
                <span className="text-[11px] text-slate-600 truncate">
                  · {usuario.sucursal.nombre}
                </span>
              )}
            </div>
          </div>

          <button
            type="button"
            onClick={manejarSalir}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl text-xs font-bold text-slate-700 bg-white border border-slate-300 hover:bg-slate-100 transition-colors cursor-pointer"
          >
            <LogOut className="w-3.5 h-3.5" />
            Cerrar sesión
          </button>
        </div>
      </aside>

      {/* Menú móvil */}
      {menuMovilAbierto && (
        <div className="fixed inset-0 z-50 lg:hidden flex">
          <div
            className="fixed inset-0 bg-black/50"
            onClick={() => setMenuMovilAbierto(false)}
          />
          <div className="relative w-64 bg-white flex flex-col z-10 shadow-xl">
            <div className="p-4 bg-[#E85A28] text-white flex items-center justify-between">
              <span className="font-black text-sm">TEKIO ELECTRONICS</span>
              <button
                type="button"
                onClick={() => setMenuMovilAbierto(false)}
                className="p-1 rounded-lg hover:bg-black/20"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <nav className="flex-1 p-3 space-y-1">
              {enlaces.map((enlace) => (
                <Link
                  key={enlace.href}
                  href={enlace.href}
                  onClick={() => setMenuMovilAbierto(false)}
                  className={`flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl text-sm font-semibold ${
                    rutaActual === enlace.href
                      ? "bg-[#E85A28] text-white"
                      : "text-slate-700 hover:bg-orange-50"
                  }`}
                >
                  {enlace.icono}
                  <span>{enlace.etiqueta}</span>
                </Link>
              ))}
            </nav>
            <div className="p-4 border-t border-slate-200">
              <button
                type="button"
                onClick={manejarSalir}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl text-xs font-bold text-white bg-[#E85A28]"
              >
                <LogOut className="w-3.5 h-3.5" />
                Cerrar sesión
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Contenido principal + Barra superior global de tasas */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-30 bg-white border-b border-slate-200 px-4 lg:px-6 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setMenuMovilAbierto(true)}
                className="lg:hidden p-2 rounded-lg border border-slate-200 text-slate-700"
              >
                <Menu className="w-5 h-5" />
              </button>

              {cargandoTasa ? (
                <div className="h-7 w-72 rounded-lg bg-slate-200 animate-pulse" />
              ) : tasaHoy && tasaHoy.permite_bolivares ? (
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="px-2.5 py-1 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 font-bold">
                    BCV: {formatearBs(tasaHoy.tasa_bcv)}
                  </span>
                  <span className="px-2.5 py-1 rounded-lg bg-sky-50 border border-sky-200 text-sky-800 font-bold">
                    USDT: {formatearBs(tasaHoy.tasa_usdt)}
                  </span>
                  <span className="px-2.5 py-1 rounded-lg bg-orange-50 border border-orange-200 text-[#C9461A] font-bold">
                    Recargo: {formatearPorcentaje(tasaHoy.recargo_porcentaje)}
                  </span>
                </div>
              ) : (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-red-600 text-white text-xs font-bold shadow-sm">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>
                    {tasaHoy?.alerta ||
                      "Sin tasa del día — Cobros en Bs bloqueados"}
                  </span>
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={() => void recargarTasaHoy()}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold text-slate-600 hover:bg-slate-100 border border-slate-200 cursor-pointer"
              title="Actualizar tasas del día"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Actualizar</span>
            </button>
          </div>
        </header>

        <main className="flex-1 p-4 lg:p-6 max-w-7xl w-full mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
