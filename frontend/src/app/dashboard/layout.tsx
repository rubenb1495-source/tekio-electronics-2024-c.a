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
import ModalRecargoDiario from "@/components/ModalRecargoDiario";
import InstaladorPwa from "@/components/InstaladorPwa";
import CampanaAlertas from "@/components/CampanaAlertas";
import { usarSesion } from "@/contexto/SesionContexto";
import { puedeAccederRuta, usePermisos } from "@/lib/permisos";
import {
  formatearBs,
  formatearPorcentaje,
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
    sincronizarTasaHoy,
  } = usarSesion();
  const router = useRouter();
  const rutaActual = usePathname();
  const permisos = usePermisos();
  const [menuMovilAbierto, setMenuMovilAbierto] = useState(false);
  const [sidebarColapsado, setSidebarColapsado] = useState(false);
  const [avisoPermiso, setAvisoPermiso] = useState<string | null>(null);

  useEffect(() => {
    if (!cargandoSesion && !usuario) {
      router.replace("/login");
    }
  }, [usuario, cargandoSesion, router]);

  const rutaAutorizada = usuario ? puedeAccederRuta(rutaActual, usuario.rol) : true;

  useEffect(() => {
    if (!cargandoSesion && usuario && !rutaAutorizada) {
      setAvisoPermiso("No tienes permisos para acceder a esta sección.");
      router.replace("/dashboard");
    }
  }, [cargandoSesion, usuario, rutaAutorizada, router]);

  useEffect(() => {
    if (!avisoPermiso) return;
    const timer = setTimeout(() => setAvisoPermiso(null), 6000);
    return () => clearTimeout(timer);
  }, [avisoPermiso]);

  if (cargandoSesion || !usuario) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="space-y-3 text-center">
          <LogoTekio variante="isotipo" tema="claro" tamano="md" />
          <p className="text-xs font-medium text-neutral-500">
            Verificando sesión...
          </p>
        </div>
      </div>
    );
  }

  const esAdmin = permisos.esAdmin;
  const esLogistica = permisos.puedeGestionarCompras;
  const esTallerOAdmin = permisos.puedeTaller;

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
          href: "/dashboard/cotizaciones",
          etiqueta: "Cotizaciones",
          icono: <ClipboardList className="w-4 h-4 shrink-0" />,
          visible: true,
        },
        {
          href: "/dashboard/ventas/devoluciones",
          etiqueta: "Devoluciones y Garantías",
          icono: <RotateCcw className="w-4 h-4 shrink-0" />,
          visible: true,
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
          href: "/dashboard/direccion",
          etiqueta: "Panel Dirección",
          icono: <BarChart3 className="w-4 h-4 shrink-0" />,
          visible: esAdmin,
        },
        {
          href: "/dashboard/finanzas/tesoreria",
          etiqueta: "Tesorería y Divisas",
          icono: <ArrowLeftRight className="w-4 h-4 shrink-0" />,
          visible: esAdmin,
        },
        {
          href: "/dashboard/finanzas/contabilidad",
          etiqueta: "Contabilidad y P&L",
          icono: <FileSpreadsheet className="w-4 h-4 shrink-0" />,
          visible: esAdmin,
        },
        {
          href: "/dashboard/finanzas/fiscal",
          etiqueta: "Fiscal · SENIAT",
          icono: <Receipt className="w-4 h-4 shrink-0" />,
          visible: esAdmin,
        },
        {
          href: "/dashboard/finanzas/nomina",
          etiqueta: "Nómina y Laboral",
          icono: <Users className="w-4 h-4 shrink-0" />,
          visible: esAdmin,
        },
        {
          href: "/dashboard/finanzas/auditoria",
          etiqueta: "Auditoría Interna",
          icono: <Shield className="w-4 h-4 shrink-0" />,
          visible: esAdmin,
        },
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
          etiqueta: permisos.puedeLiquidar ? "Comisiones y Cierre" : "Mis Comisiones",
          icono: <BarChart3 className="w-4 h-4 shrink-0" />,
          visible: permisos.puedeVerComisiones,
        },
        {
          href: "/dashboard/finanzas/cierre-caja",
          etiqueta: "Cierre de Caja",
          icono: <Receipt className="w-4 h-4 shrink-0" />,
          visible: true,
        },
      ],
    },
    {
      titulo: "Administración",
      enlaces: [
        {
          href: "/dashboard/usuarios",
          etiqueta: "Personal y Usuarios",
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
    <div className="min-h-screen flex text-[#191818] relative">
      {/* Sidebar escritorio claro translúcido (glassmorphism) */}
      <aside
        className={`hidden lg:flex lg:flex-col bg-white/80 backdrop-blur-lg border-r border-gray-200/70 shadow-[0_8px_30px_rgb(0,0,0,0.04)] shrink-0 z-20 transition-all duration-200 ${
          sidebarColapsado ? "w-[74px]" : "w-64"
        }`}
      >
        {/* Cabecera del Sidebar */}
        <div
          className={`h-16 px-3.5 border-b border-gray-200/70 flex items-center ${
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
              <LogoTekio variante="isotipo" tema="claro" tamano="sm" />
            </button>
          ) : (
            <>
              <LogoTekio variante="horizontal" tema="claro" tamano="sm" />
              <button
                type="button"
                onClick={() => setSidebarColapsado(true)}
                title="Colapsar menú"
                aria-label="Colapsar menú"
                className="p-1.5 rounded-lg text-gray-400 hover:text-[#191818] hover:bg-gray-100/80 transition-colors cursor-pointer"
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
                <p className="px-3 pb-1 text-[10px] font-bold uppercase tracking-[0.14em] text-gray-400">
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
                    className={`flex items-center rounded-xl text-[13px] transition-colors ${
                      sidebarColapsado
                        ? "justify-center px-2 py-2.5"
                        : "gap-2.5 px-3 py-2"
                    } ${
                      activo
                        ? "bg-[#FDF0EB] text-[#E85A28] font-bold border-l-[3px] border-[#E85A28]"
                        : "text-[#4B5563] font-medium hover:bg-gray-100/80 hover:text-[#191818]"
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
        <div className="p-3 border-t border-gray-200/70 bg-white/50 space-y-2.5">
          {sidebarColapsado ? (
            <div className="flex flex-col items-center gap-2">
              <button
                type="button"
                onClick={() => setSidebarColapsado(false)}
                title="Expandir menú"
                className="p-2 rounded-lg text-gray-500 hover:text-[#191818] hover:bg-gray-100 cursor-pointer"
              >
                <PanelLeftOpen className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={manejarSalir}
                title="Cerrar sesión"
                className="p-2 rounded-lg text-gray-500 hover:text-[#E85A28] hover:bg-[#FDF0EB] cursor-pointer"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <>
              <div className="text-xs px-1">
                <p className="font-bold text-[#191818] truncate">
                  {usuario.nombre}
                </p>
                <p className="text-[11px] text-gray-500 truncate">
                  {usuario.correo}
                </p>
              </div>
              <button
                type="button"
                onClick={manejarSalir}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold text-[#4B5563] bg-white/80 border border-gray-200 hover:border-[#E85A28] hover:text-[#E85A28] hover:bg-[#FDF0EB]/60 transition-colors cursor-pointer"
              >
                <LogOut className="w-3.5 h-3.5" />
                Cerrar sesión
              </button>
            </>
          )}
        </div>
      </aside>

      {/* Menú móvil claro translúcido */}
      {menuMovilAbierto && (
        <div className="fixed inset-0 z-50 lg:hidden flex">
          <div
            className="fixed inset-0 bg-black/30 backdrop-blur-xs"
            onClick={() => setMenuMovilAbierto(false)}
          />
          <div className="relative w-72 bg-white/95 backdrop-blur-xl text-[#191818] flex flex-col z-10 shadow-2xl border-r border-gray-200">
            <div className="h-16 px-4 border-b border-gray-200/80 flex items-center justify-between">
              <LogoTekio variante="horizontal" tema="claro" tamano="sm" />
              <button
                type="button"
                onClick={() => setMenuMovilAbierto(false)}
                className="p-1.5 rounded-lg text-gray-500 hover:text-[#191818] hover:bg-gray-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <nav className="flex-1 overflow-y-auto p-3 space-y-4">
              {grupos.map((grupo) => (
                <div key={grupo.titulo} className="space-y-1">
                  <p className="px-3 pb-1 text-[10px] font-bold uppercase tracking-[0.14em] text-gray-400">
                    {grupo.titulo}
                  </p>
                  {grupo.enlaces.map((enlace) => (
                    <Link
                      key={enlace.href}
                      href={enlace.href}
                      onClick={() => setMenuMovilAbierto(false)}
                      className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm ${
                        rutaActual === enlace.href
                          ? "bg-[#FDF0EB] text-[#E85A28] font-bold border-l-[3px] border-[#E85A28]"
                          : "text-[#4B5563] font-medium hover:bg-gray-100 hover:text-[#191818]"
                      }`}
                    >
                      {enlace.icono}
                      <span>{enlace.etiqueta}</span>
                    </Link>
                  ))}
                </div>
              ))}
            </nav>
            <div className="p-4 border-t border-gray-200/80">
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

      {/* Área principal + Topbar translúcida + Marca de agua fija */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        {/* Marca de agua sutil fija detrás del contenido del dashboard */}
        <div
          aria-hidden="true"
          className="marca-agua-tekio pointer-events-none select-none fixed inset-0 lg:left-64 z-0 flex items-center justify-center opacity-[0.04]"
        >
          <img
            src="/brand/tekio-isotipo.png"
            alt=""
            className="w-[420px] h-[420px] object-contain"
          />
        </div>

        <header className="sticky top-0 z-30 bg-white/75 backdrop-blur-md border-b border-white/60 shadow-[0_4px_20px_rgb(0,0,0,0.03)] px-4 lg:px-6 py-2.5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            {/* Izquierda: botón móvil + píldoras de tasas */}
            <div className="flex flex-wrap items-center gap-2.5">
              <button
                type="button"
                onClick={() => setMenuMovilAbierto(true)}
                aria-label="Abrir menú"
                className="lg:hidden p-2 rounded-xl border border-gray-200/80 bg-white/80 text-[#191818] hover:bg-gray-50"
              >
                <Menu className="w-5 h-5" />
              </button>

              {cargandoTasa ? (
                <div className="h-7 w-72 rounded-lg bg-gray-200/70 animate-pulse" />
              ) : tasaHoy && tasaHoy.permite_bolivares ? (
                <div className="flex flex-wrap items-center gap-1.5 text-xs cifra-tabular">
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white/80 border border-gray-200/80 text-[#191818] font-bold">
                    <span className="text-gray-500 font-medium">BCV</span>
                    {formatearBs(tasaHoy.tasa_bcv)}
                  </span>
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white/80 border border-gray-200/80 text-[#191818] font-bold">
                    <span className="text-gray-500 font-medium">USDT</span>
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
                onClick={() => void sincronizarTasaHoy()}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-gray-500 hover:text-[#191818] hover:bg-white/80 transition-colors cursor-pointer"
                title="Sincronizar tasas BCV y USDT ahora"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${cargandoTasa ? "animate-spin" : ""}`} />
                <span className="hidden sm:inline">Actualizar</span>
              </button>
            </div>

            {/* Derecha: PWA + Alertas + Sucursal activa + Perfil de usuario */}
            <div className="flex items-center gap-2 text-xs">
              <InstaladorPwa />
              <CampanaAlertas />
              {usuario.sucursal && (
                <span className="hidden md:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/80 border border-gray-200/80 text-[#191818] font-semibold">
                  <Building2 className="w-3.5 h-3.5 text-[#E85A28]" />
                  {usuario.sucursal.nombre}
                </span>
              )}
              <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-lg bg-white/80 border border-gray-200/80">
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

        <main className="relative z-10 flex-1 p-4 lg:p-6 max-w-7xl w-full mx-auto min-w-0">
          {avisoPermiso && (
            <div className="mb-4 flex items-center justify-between gap-3 rounded-2xl border border-amber-200 bg-amber-50/90 backdrop-blur-md px-4 py-3 text-xs font-semibold text-amber-900 shadow-sm">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                <span>{avisoPermiso}</span>
              </div>
              <button
                type="button"
                onClick={() => setAvisoPermiso(null)}
                className="p-1 rounded-lg hover:bg-amber-100 text-amber-700 cursor-pointer"
                aria-label="Cerrar aviso"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
          {rutaAutorizada ? (
            children
          ) : (
            <div className="p-8 text-center text-sm text-gray-500">
              Redirigiendo...
            </div>
          )}
        </main>
      </div>

      {/* Modal bloqueante de confirmación de recargo diario */}
      <ModalRecargoDiario />
    </div>
  );
}
