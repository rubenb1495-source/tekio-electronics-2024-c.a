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
  Building2,
  CheckSquare,
  ClipboardList,
  Cpu,
  CreditCard,
  FileSpreadsheet,
  LogOut,
  Menu,
  Package,
  PanelLeftClose,
  PanelLeftOpen,
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
import LogoTekio from "@/components/LogoTekio";
import { usarSesion } from "@/contexto/SesionContexto";
import {
  esRolAdministrativo,
  formatearBs,
  formatearPorcentaje,
  puedeGestionarCatalogo,
} from "@/servicios/api";

interface EnlaceNav {
  href: string;
  etiqueta: string;
  icono: React.ReactNode;
  visible: boolean;
}

interface GrupoNav {
  titulo: string;
  enlaces: EnlaceNav[];
}

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
  const [sidebarColapsado, setSidebarColapsado] = useState(false);

  useEffect(() => {
    if (!cargandoSesion && !usuario) {
      router.replace("/login");
    }
  }, [usuario, cargandoSesion, router]);

  if (cargandoSesion || !usuario) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F6F6F6]">
        <div className="space-y-3 text-center">
          <LogoTekio variante="isotipo" tema="claro" tamano="md" />
          <p className="text-xs font-medium text-neutral-500">
            Verificando sesión...
          </p>
        </div>
      </div>
    );
  }

  const esAdmin = esRolAdministrativo(usuario.rol);
  const esLogistica = puedeGestionarCatalogo(usuario.rol);
  const esTallerOAdmin = esLogistica || usuario.rol === "TECNICO";

  const grupos: GrupoNav[] = [
    {
      titulo: "Operaciones",
      enlaces: [
        {
          href: "/dashboard/ventas/nueva",
          etiqueta: "POS · Nueva Venta",
          icono: <ShoppingCart className="w-4 h-4 shrink-0" />,
          visible: true,
        },
        {
          href: "/dashboard/ventas",
          etiqueta: "Historial de Ventas",
          icono: <Receipt className="w-4 h-4 shrink-0" />,
          visible: true,
        },
        {
          href: "/dashboard/devoluciones",
          etiqueta: "Devoluciones / NC",
          icono: <RotateCcw className="w-4 h-4 shrink-0" />,
          visible: esLogistica,
        },
        {
          href: "/dashboard/tasas",
          etiqueta: "Tasas Diarias",
          icono: <ArrowLeftRight className="w-4 h-4 shrink-0" />,
          visible: true,
        },
        {
          href: "/dashboard/catalogo",
          etiqueta: "Catálogo y Precios",
          icono: <Package className="w-4 h-4 shrink-0" />,
          visible: true,
        },
      ],
    },
    {
      titulo: "Logística",
      enlaces: [
        {
          href: "/dashboard/logistica/compras",
          etiqueta: "Compras e Importación",
          icono: <ShoppingBag className="w-4 h-4 shrink-0" />,
          visible: esLogistica,
        },
        {
          href: "/dashboard/logistica/guias",
          etiqueta: "Guías de Casillero",
          icono: <Plane className="w-4 h-4 shrink-0" />,
          visible: esLogistica,
        },
        {
          href: "/dashboard/logistica/recepcion",
          etiqueta: "Recepción por Serial",
          icono: <ScanBarcode className="w-4 h-4 shrink-0" />,
          visible: esLogistica,
        },
        {
          href: "/dashboard/logistica/traslados",
          etiqueta: "Traslados (2 Pasos)",
          icono: <Truck className="w-4 h-4 shrink-0" />,
          visible: true,
        },
        {
          href: "/dashboard/logistica/inventario",
          etiqueta: "Inventario y Ajustes",
          icono: <Boxes className="w-4 h-4 shrink-0" />,
          visible: true,
        },
      ],
    },
    {
      titulo: "Taller",
      enlaces: [
        {
          href: "/dashboard/taller/preparaciones",
          etiqueta: "Preparaciones",
          icono: <Wrench className="w-4 h-4 shrink-0" />,
          visible: esTallerOAdmin,
        },
        {
          href: "/dashboard/taller/casos",
          etiqueta: "Casos GT / ST",
          icono: <ClipboardList className="w-4 h-4 shrink-0" />,
          visible: true,
        },
        {
          href: "/dashboard/taller/repuestos",
          etiqueta: "Repuestos Solicitados",
          icono: <Cpu className="w-4 h-4 shrink-0" />,
          visible: esTallerOAdmin,
        },
        {
          href: "/dashboard/taller/mi-resumen",
          etiqueta: "Mi Resumen Técnico",
          icono: <Award className="w-4 h-4 shrink-0" />,
          visible: esTallerOAdmin,
        },
      ],
    },
    {
      titulo: "Finanzas",
      enlaces: [
        {
          href: "/dashboard/finanzas/pagos",
          etiqueta: "Pagos y CxC",
          icono: <CheckSquare className="w-4 h-4 shrink-0" />,
          visible: esAdmin,
        },
        {
          href: "/dashboard/finanzas/cashea",
          etiqueta: "Cashea",
          icono: <CreditCard className="w-4 h-4 shrink-0" />,
          visible: esAdmin,
        },
        {
          href: "/dashboard/finanzas/conciliacion",
          etiqueta: "Conciliación",
          icono: <FileSpreadsheet className="w-4 h-4 shrink-0" />,
          visible: esAdmin,
        },
        {
          href: "/dashboard/finanzas/comisiones",
          etiqueta: "Comisiones y Cierre",
          icono: <BarChart3 className="w-4 h-4 shrink-0" />,
          visible: esAdmin,
        },
      ],
    },
    {
      titulo: "Administración",
      enlaces: [
        {
          href: "/dashboard/usuarios",
          etiqueta: "Usuarios y Sedes",
          icono: <Users className="w-4 h-4 shrink-0" />,
          visible: esAdmin,
        },
      ],
    },
  ]
    .map((g) => ({
      ...g,
      enlaces: g.enlaces.filter((e) => e.visible),
    }))
    .filter((g) => g.enlaces.length > 0);

  const manejarSalir = () => {
    cerrarSesion();
    router.replace("/login");
  };

  return (
    <div className="min-h-screen flex bg-[#F6F6F6] text-[#191818]">
      {/* Sidebar escritorio (#191818 Carbón Tekio) */}
      <aside
        className={`hidden lg:flex lg:flex-col bg-[#191818] text-white border-r border-[#2E2D2D] shrink-0 transition-all duration-200 ${
          sidebarColapsado ? "w-[74px]" : "w-64"
        }`}
      >
        {/* Cabecera del Sidebar */}
        <div
          className={`h-16 px-3.5 border-b border-[#2E2D2D] flex items-center ${
            sidebarColapsado ? "justify-center" : "justify-between"
          }`}
        >
          {sidebarColapsado ? (
            <button
              type="button"
              onClick={() => setSidebarColapsado(false)}
              title="Expandir menú"
              className="cursor-pointer"
            >
              <LogoTekio variante="isotipo" tema="oscuro" tamano="sm" />
            </button>
          ) : (
            <>
              <LogoTekio variante="horizontal" tema="oscuro" tamano="sm" />
              <button
                type="button"
                onClick={() => setSidebarColapsado(true)}
                title="Colapsar menú"
                aria-label="Colapsar menú"
                className="p-1.5 rounded-lg text-neutral-400 hover:text-white hover:bg-[#242323] transition-colors cursor-pointer"
              >
                <PanelLeftClose className="w-4 h-4" />
              </button>
            </>
          )}
        </div>

        {/* Navegación agrupada por módulos */}
        <nav className="flex-1 overflow-y-auto px-2.5 py-4 space-y-5">
          {grupos.map((grupo) => (
            <div key={grupo.titulo} className="space-y-1">
              {!sidebarColapsado && (
                <p className="px-3 pb-1 text-[10px] font-bold uppercase tracking-[0.14em] text-neutral-500">
                  {grupo.titulo}
                </p>
              )}
              {grupo.enlaces.map((enlace) => {
                const activo = rutaActual === enlace.href;
                return (
                  <Link
                    key={enlace.href}
                    href={enlace.href}
                    title={sidebarColapsado ? enlace.etiqueta : undefined}
                    className={`flex items-center rounded-xl text-[13px] font-medium transition-colors ${
                      sidebarColapsado
                        ? "justify-center px-2 py-2.5"
                        : "gap-2.5 px-3 py-2"
                    } ${
                      activo
                        ? "bg-[#E85A28] text-white font-semibold"
                        : "text-neutral-300 hover:bg-[#242323] hover:text-white"
                    }`}
                  >
                    {enlace.icono}
                    {!sidebarColapsado && (
                      <span className="truncate">{enlace.etiqueta}</span>
                    )}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        {/* Pie del Sidebar */}
        <div className="p-3 border-t border-[#2E2D2D] bg-[#242323]/60 space-y-2.5">
          {sidebarColapsado ? (
            <div className="flex flex-col items-center gap-2">
              <button
                type="button"
                onClick={() => setSidebarColapsado(false)}
                title="Expandir menú"
                className="p-2 rounded-lg text-neutral-400 hover:text-white hover:bg-[#242323] cursor-pointer"
              >
                <PanelLeftOpen className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={manejarSalir}
                title="Cerrar sesión"
                className="p-2 rounded-lg text-neutral-400 hover:text-[#E85A28] hover:bg-[#242323] cursor-pointer"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <>
              <div className="text-xs px-1">
                <p className="font-bold text-white truncate">
                  {usuario.nombre}
                </p>
                <p className="text-[11px] text-neutral-400 truncate">
                  {usuario.correo}
                </p>
              </div>
              <button
                type="button"
                onClick={manejarSalir}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold text-neutral-200 bg-[#242323] border border-[#2E2D2D] hover:border-[#E85A28] hover:text-white transition-colors cursor-pointer"
              >
                <LogOut className="w-3.5 h-3.5" />
                Cerrar sesión
              </button>
            </>
          )}
        </div>
      </aside>

      {/* Menú móvil (#191818) */}
      {menuMovilAbierto && (
        <div className="fixed inset-0 z-50 lg:hidden flex">
          <div
            className="fixed inset-0 bg-black/60"
            onClick={() => setMenuMovilAbierto(false)}
          />
          <div className="relative w-72 bg-[#191818] text-white flex flex-col z-10 shadow-2xl border-r border-[#2E2D2D]">
            <div className="h-16 px-4 border-b border-[#2E2D2D] flex items-center justify-between">
              <LogoTekio variante="horizontal" tema="oscuro" tamano="sm" />
              <button
                type="button"
                onClick={() => setMenuMovilAbierto(false)}
                className="p-1.5 rounded-lg text-neutral-400 hover:text-white hover:bg-[#242323]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <nav className="flex-1 overflow-y-auto p-3 space-y-4">
              {grupos.map((grupo) => (
                <div key={grupo.titulo} className="space-y-1">
                  <p className="px-3 pb-1 text-[10px] font-bold uppercase tracking-[0.14em] text-neutral-500">
                    {grupo.titulo}
                  </p>
                  {grupo.enlaces.map((enlace) => (
                    <Link
                      key={enlace.href}
                      href={enlace.href}
                      onClick={() => setMenuMovilAbierto(false)}
                      className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-medium ${
                        rutaActual === enlace.href
                          ? "bg-[#E85A28] text-white font-semibold"
                          : "text-neutral-300 hover:bg-[#242323] hover:text-white"
                      }`}
                    >
                      {enlace.icono}
                      <span>{enlace.etiqueta}</span>
                    </Link>
                  ))}
                </div>
              ))}
            </nav>
            <div className="p-4 border-t border-[#2E2D2D]">
              <button
                type="button"
                onClick={manejarSalir}
                className="w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl text-xs font-bold text-white bg-[#E85A28] hover:bg-[#D14D1F]"
              >
                <LogOut className="w-3.5 h-3.5" />
                Cerrar sesión
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Área principal + Topbar blanca (#FFFFFF) */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-30 bg-[#FFFFFF] border-b border-[#E5E7EB] px-4 lg:px-6 py-2.5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            {/* Izquierda: botón móvil + píldoras de tasas */}
            <div className="flex flex-wrap items-center gap-2.5">
              <button
                type="button"
                onClick={() => setMenuMovilAbierto(true)}
                aria-label="Abrir menú"
                className="lg:hidden p-2 rounded-xl border border-neutral-200 text-[#191818] hover:bg-neutral-50"
              >
                <Menu className="w-5 h-5" />
              </button>

              {cargandoTasa ? (
                <div className="h-7 w-72 rounded-lg bg-neutral-200 animate-pulse" />
              ) : tasaHoy && tasaHoy.permite_bolivares ? (
                <div className="flex flex-wrap items-center gap-1.5 text-xs cifra-tabular">
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-neutral-100 border border-neutral-200 text-[#191818] font-bold">
                    <span className="text-neutral-500 font-medium">BCV</span>
                    {formatearBs(tasaHoy.tasa_bcv)}
                  </span>
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-neutral-100 border border-neutral-200 text-[#191818] font-bold">
                    <span className="text-neutral-500 font-medium">USDT</span>
                    {formatearBs(tasaHoy.tasa_usdt)}
                  </span>
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[#FDF0EB] border border-[#E85A28]/25 text-[#E85A28] font-bold">
                    Recargo {formatearPorcentaje(tasaHoy.recargo_porcentaje)}
                  </span>
                </div>
              ) : (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-red-600 text-white text-xs font-bold">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>
                    {tasaHoy?.alerta ||
                      "Sin tasa del día — Cobros en Bs bloqueados"}
                  </span>
                </div>
              )}

              <button
                type="button"
                onClick={() => void recargarTasaHoy()}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-neutral-500 hover:text-[#191818] hover:bg-neutral-100 transition-colors cursor-pointer"
                title="Actualizar tasas del día"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Actualizar</span>
              </button>
            </div>

            {/* Derecha: Sucursal activa + Perfil de usuario */}
            <div className="flex items-center gap-2 text-xs">
              {usuario.sucursal && (
                <span className="hidden md:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#F6F6F6] border border-[#E5E7EB] text-[#191818] font-semibold">
                  <Building2 className="w-3.5 h-3.5 text-[#E85A28]" />
                  {usuario.sucursal.nombre}
                </span>
              )}
              <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-lg bg-[#F6F6F6] border border-[#E5E7EB]">
                <span className="font-bold text-[#191818] max-w-[140px] truncate">
                  {usuario.nombre}
                </span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-[#FDF0EB] text-[#E85A28] font-bold text-[10px] tracking-wide">
                  <Shield className="w-2.5 h-2.5" />
                  {usuario.rol}
                </span>
              </div>
            </div>
          </div>
        </header>

        <main className="flex-1 p-4 lg:p-6 max-w-7xl w-full mx-auto min-w-0">
          {children}
        </main>
      </div>
    </div>
  );
}
