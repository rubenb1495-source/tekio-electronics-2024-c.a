"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Bell, CalendarClock, Lock, PackageX, X } from "lucide-react";
import { usePermisos } from "@/lib/permisos";
import { formatearUsd, solicitarApi } from "@/servicios/api";

export interface AlertaStockBajo {
  articulo_id: number;
  sku: string;
  descripcion: string;
  tipo: string;
  categoria: string;
  stock_actual: number;
  stock_minimo: number;
  criticidad: "AGOTADO" | "BAJO";
}

export interface AlertaCxp {
  compra_id: number;
  numero_compra: string;
  factura_orden: string;
  proveedor: string;
  origen: string;
  fecha_vencimiento: string | null;
  dias_restantes: number;
  saldo_pendiente_usd: number;
  estado: "VENCIDA" | "POR_VENCER";
}

export interface AlertaSeguridad {
  usuario_id: number;
  nombre: string;
  username: string;
  rol: string;
  intentos_fallidos: number;
  bloqueado_hasta: string | null;
  mensaje: string;
}

export interface RespuestaAlertas {
  fecha_corte: string;
  total_alertas: number;
  total_stock_bajo: number;
  total_cxp: number;
  total_seguridad?: number;
  stock_bajo: AlertaStockBajo[];
  cxp_por_vencer: AlertaCxp[];
  alertas_seguridad?: AlertaSeguridad[];
}

export default function CampanaAlertas() {
  const { esAdmin } = usePermisos();
  const [alertas, setAlertas] = useState<RespuestaAlertas | null>(null);
  const [abierto, setAbierto] = useState(false);

  const cargar = useCallback(async () => {
    if (!esAdmin) return;
    try {
      const res = await solicitarApi<RespuestaAlertas>("/api/alertas");
      setAlertas(res);
    } catch {
      // Silencioso en topbar
    }
  }, [esAdmin]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  if (!esAdmin) return null;

  const total = alertas?.total_alertas ?? 0;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => {
          setAbierto((prev) => !prev);
          if (!abierto) void cargar();
        }}
        title="Alertas inteligentes (Stock bajo y CxP por vencer)"
        className="relative p-1.5 rounded-lg bg-white/80 border border-gray-200/80 text-[#191818] hover:border-[#E85A28] hover:text-[#E85A28] transition-colors cursor-pointer"
      >
        <Bell className="w-4 h-4" />
        {total > 0 && (
          <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full bg-[#E85A28] text-white text-[10px] font-black flex items-center justify-center tabular-nums shadow-xs">
            {total > 99 ? "99+" : total}
          </span>
        )}
      </button>

      {abierto && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setAbierto(false)}
          />
          <div className="absolute right-0 mt-2 w-80 sm:w-96 z-50 bg-white/95 backdrop-blur-xl border border-gray-200/90 rounded-2xl shadow-2xl overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between bg-[#FDF0EB]/60">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-[#E85A28]" />
                <p className="text-xs font-black text-[#191818]">
                  Alertas Inteligentes ({total})
                </p>
              </div>
              <button
                type="button"
                onClick={() => setAbierto(false)}
                className="p-1 rounded-lg text-gray-400 hover:text-gray-700 cursor-pointer"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            <div className="max-h-96 overflow-y-auto divide-y divide-gray-100 text-xs">
              {/* Bloque Alertas de Seguridad */}
              {alertas?.alertas_seguridad && alertas.alertas_seguridad.length > 0 && (
                <div className="p-3 space-y-2 bg-red-50/40">
                  <div className="flex items-center justify-between">
                    <p className="font-bold uppercase tracking-wide text-[10px] text-red-700 flex items-center gap-1">
                      <Lock className="w-3.5 h-3.5" />
                      Alertas de Seguridad ({alertas.alertas_seguridad.length})
                    </p>
                    <Link
                      href="/dashboard/usuarios"
                      onClick={() => setAbierto(false)}
                      className="text-[11px] font-bold text-[#E85A28] hover:underline"
                    >
                      Ver personal
                    </Link>
                  </div>
                  {alertas.alertas_seguridad.map((seg) => (
                    <div
                      key={seg.usuario_id}
                      className="p-2 rounded-xl bg-red-100/70 border border-red-200 flex items-center justify-between gap-2"
                    >
                      <div className="min-w-0">
                        <p className="font-bold text-red-900 truncate">
                          {seg.nombre} ({seg.rol})
                        </p>
                        <p className="text-[11px] text-red-700">{seg.mensaje}</p>
                      </div>
                      <button
                        type="button"
                        onClick={async () => {
                          try {
                            await solicitarApi(`/api/personal/${seg.usuario_id}/desbloquear`, {
                              method: "POST",
                            });
                            await cargar();
                          } catch {
                            // Silencioso
                          }
                        }}
                        className="px-2.5 py-1 rounded-lg bg-[#E85A28] text-white text-[10px] font-bold shrink-0 cursor-pointer"
                      >
                        Desbloquear
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Bloque CxP */}
              <div className="p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <p className="font-bold uppercase tracking-wide text-[10px] text-red-700 flex items-center gap-1">
                    <CalendarClock className="w-3.5 h-3.5" />
                    CxP Vencidas / Por Vencer ({alertas?.total_cxp ?? 0})
                  </p>
                  <Link
                    href="/dashboard/logistica/compras"
                    onClick={() => setAbierto(false)}
                    className="text-[11px] font-bold text-[#E85A28] hover:underline"
                  >
                    Ver compras
                  </Link>
                </div>
                {!alertas || alertas.cxp_por_vencer.length === 0 ? (
                  <p className="text-gray-400 text-[11px]">
                    Sin facturas por vencer en los próximos 7 días.
                  </p>
                ) : (
                  alertas.cxp_por_vencer.slice(0, 5).map((c) => (
                    <div
                      key={c.compra_id}
                      className="p-2 rounded-xl bg-red-50/70 border border-red-100 flex items-center justify-between gap-2"
                    >
                      <div className="min-w-0">
                        <p className="font-bold text-[#191818] truncate">
                          {c.proveedor} · {c.factura_orden}
                        </p>
                        <p className="text-[11px] text-red-700">
                          {c.estado === "VENCIDA"
                            ? `Vencida hace ${Math.abs(c.dias_restantes)}d`
                            : `Vence en ${c.dias_restantes}d (${c.fecha_vencimiento})`}
                        </p>
                      </div>
                      <span className="font-black tabular-nums text-red-700 shrink-0">
                        {formatearUsd(c.saldo_pendiente_usd)}
                      </span>
                    </div>
                  ))
                )}
              </div>

              {/* Bloque Stock Bajo */}
              <div className="p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <p className="font-bold uppercase tracking-wide text-[10px] text-amber-700 flex items-center gap-1">
                    <PackageX className="w-3.5 h-3.5" />
                    Stock Bajo / Agotado ({alertas?.total_stock_bajo ?? 0})
                  </p>
                  <Link
                    href="/dashboard/catalogo"
                    onClick={() => setAbierto(false)}
                    className="text-[11px] font-bold text-[#E85A28] hover:underline"
                  >
                    Ver catálogo
                  </Link>
                </div>
                {!alertas || alertas.stock_bajo.length === 0 ? (
                  <p className="text-gray-400 text-[11px]">
                    Todos los modelos y repuestos están sobre el stock mínimo.
                  </p>
                ) : (
                  alertas.stock_bajo.slice(0, 6).map((s) => (
                    <div
                      key={s.articulo_id}
                      className="p-2 rounded-xl bg-amber-50/70 border border-amber-100 flex items-center justify-between gap-2"
                    >
                      <div className="min-w-0">
                        <p className="font-bold text-[#191818] truncate">
                          {s.sku} · {s.descripcion}
                        </p>
                        <p className="text-[11px] text-amber-800">
                          Mínimo: {s.stock_minimo} · {s.tipo}
                        </p>
                      </div>
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-black tabular-nums shrink-0 ${
                          s.criticidad === "AGOTADO"
                            ? "bg-red-100 text-red-700"
                            : "bg-amber-200 text-amber-900"
                        }`}
                      >
                        {s.stock_actual} disp.
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
