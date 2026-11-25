"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  AlertTriangle,
  Boxes,
  Building2,
  Landmark,
  MessageCircle,
  RefreshCw,
  TrendingUp,
  Wallet,
} from "lucide-react";
import type { RespuestaAlertas } from "@/components/CampanaAlertas";
import ModalResumenEjecutivoPL from "@/components/ModalResumenEjecutivoPL";
import {
  ErrorApi,
  formatearBs,
  formatearUsd,
  solicitarApi,
} from "@/servicios/api";

interface ResumenDireccion {
  fecha: string;
  tasas: {
    tasa_bcv: number;
    tasa_usdt: number;
    recargo_porcentaje: number;
  };
  tesoreria: {
    total_disponible_usd: number;
    cuentas: {
      instrumento_id: number;
      nombre: string;
      moneda: string;
      saldo_origen: number;
      equivalente_usd: number;
    }[];
  };
  inventario: {
    valor_costo_usd: number;
    valor_promo_usd: number;
    utilidad_potencial_usd: number;
    unidades_listo: number;
    unidades_por_preparar: number;
    unidades_hospital: number;
    unidades_en_transito: number;
    unidades_consignacion: number;
    traslados_pendientes: number;
    listo_por_sucursal: { sucursal: string; unidades: number }[];
  };
  cartera: {
    cxc_clientes_usd: number;
    cxc_cashea_usd: number;
    cxc_total_usd: number;
    cxp_total_usd: number;
    cxp_vencidas_usd: number;
    cxp_proximas_7d_usd: number;
  };
  pulso_comercial: {
    ventas_dia_cant: number;
    ventas_dia_usd: number;
    utilidad_dia_usd: number;
    ventas_mes_cant: number;
    ventas_mes_usd: number;
    utilidad_mes_usd: number;
    comisiones_pendientes_usd: number;
    comparativo_sucursales: {
      sucursal: string;
      ventas_mes_cant: number;
      ventas_mes_usd: number;
      ventas_dia_usd: number;
      utilidad_mes_usd: number;
    }[];
  };
  alertas: RespuestaAlertas;
}

export default function PaginaPanelDireccion() {
  const [datos, setDatos] = useState<ResumenDireccion | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalResumenWa, setModalResumenWa] = useState(false);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const res = await solicitarApi<ResumenDireccion>("/api/direccion/resumen");
      setDatos(res);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo cargar el Panel Ejecutivo de Dirección."
      );
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-[#191818]">
            Panel Ejecutivo de Dirección
          </h2>
          <p className="text-sm text-neutral-500">
            Consolidado en tiempo real de cajas y bancos, inventario valorizado, CxC/CxP, pulso comercial y alertas.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setModalResumenWa(true)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] text-white text-xs font-bold cursor-pointer shadow-xs"
          >
            <MessageCircle className="w-3.5 h-3.5" />
            Resumen Ejecutivo WhatsApp
          </button>
          <button
            type="button"
            onClick={() => void cargar()}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-white/85 border border-neutral-200 hover:border-[#E85A28] text-xs font-bold text-[#191818] cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${cargando ? "animate-spin" : ""}`} />
            Actualizar en vivo
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2.5 p-4 rounded-2xl bg-red-50 border border-red-200 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {cargando && !datos ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 rounded-2xl bg-white/60 animate-pulse" />
          ))}
        </div>
      ) : datos ? (
        <>
          {/* KPIs Ejecutivos Principales */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-white/80 backdrop-blur-md p-5 rounded-2xl border border-white/70 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border-t-2 border-t-emerald-600">
              <p className="text-[11px] font-bold uppercase text-neutral-500 flex items-center gap-1.5">
                <Landmark className="w-3.5 h-3.5 text-emerald-600" />
                Liquidez Cajas y Bancos
              </p>
              <p className="text-2xl font-black text-emerald-700 mt-1 tabular-nums">
                {formatearUsd(datos.tesoreria.total_disponible_usd)}
              </p>
              <p className="text-[11px] text-neutral-500 mt-1">
                Equivalente consolidado USD ({datos.tesoreria.cuentas.length} cuentas)
              </p>
            </div>

            <div className="bg-white/80 backdrop-blur-md p-5 rounded-2xl border border-white/70 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border-t-2 border-t-[#191818]">
              <p className="text-[11px] font-bold uppercase text-neutral-500 flex items-center gap-1.5">
                <Boxes className="w-3.5 h-3.5 text-[#191818]" />
                Inventario Valorizado
              </p>
              <p className="text-2xl font-black text-[#191818] mt-1 tabular-nums">
                {formatearUsd(datos.inventario.valor_promo_usd)}
              </p>
              <p className="text-[11px] text-neutral-500 mt-1 tabular-nums">
                Costo: <strong>{formatearUsd(datos.inventario.valor_costo_usd)}</strong> · LISTO: <strong>{datos.inventario.unidades_listo}</strong>
              </p>
            </div>

            <div className="bg-white/80 backdrop-blur-md p-5 rounded-2xl border border-white/70 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border-t-2 border-t-blue-600">
              <p className="text-[11px] font-bold uppercase text-neutral-500 flex items-center gap-1.5">
                <Wallet className="w-3.5 h-3.5 text-blue-600" />
                CxC vs CxP
              </p>
              <p className="text-2xl font-black text-blue-700 mt-1 tabular-nums">
                {formatearUsd(datos.cartera.cxc_total_usd)}
              </p>
              <p className="text-[11px] text-neutral-500 mt-1 tabular-nums">
                Cashea: {formatearUsd(datos.cartera.cxc_cashea_usd)} · CxP:{" "}
                <strong className="text-red-700">{formatearUsd(datos.cartera.cxp_total_usd)}</strong>
              </p>
            </div>

            <div className="bg-white/80 backdrop-blur-md p-5 rounded-2xl border border-white/70 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border-t-2 border-t-[#E85A28]">
              <p className="text-[11px] font-bold uppercase text-neutral-500 flex items-center gap-1.5">
                <TrendingUp className="w-3.5 h-3.5 text-[#E85A28]" />
                Ventas del Mes ({datos.pulso_comercial.ventas_mes_cant})
              </p>
              <p className="text-2xl font-black text-[#E85A28] mt-1 tabular-nums">
                {formatearUsd(datos.pulso_comercial.ventas_mes_usd)}
              </p>
              <p className="text-[11px] text-neutral-500 mt-1 tabular-nums">
                Hoy: <strong>{formatearUsd(datos.pulso_comercial.ventas_dia_usd)}</strong> · Utilidad est.:{" "}
                <strong className="text-emerald-700">{formatearUsd(datos.pulso_comercial.utilidad_mes_usd)}</strong>
              </p>
            </div>
          </div>

          {/* Cajas/Bancos + Inventario por Sucursal */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white/80 backdrop-blur-md rounded-2xl border border-white/70 shadow-[0_8px_30px_rgb(0,0,0,0.04)] p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-black text-[#191818]">
                  Saldos en Vivo · Cajas y Bancos
                </h3>
                <Link
                  href="/dashboard/finanzas/tesoreria"
                  className="text-xs font-bold text-[#E85A28] hover:underline"
                >
                  Ir a Tesorería →
                </Link>
              </div>
              <div className="overflow-x-auto max-h-72 overflow-y-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-neutral-50 text-neutral-500 uppercase text-[10px]">
                    <tr>
                      <th className="px-3 py-2">Instrumento / Cuenta</th>
                      <th className="px-3 py-2 text-right">Saldo Origen</th>
                      <th className="px-3 py-2 text-right">Equiv. USD</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-100 tabular-nums">
                    {datos.tesoreria.cuentas.map((c) => (
                      <tr key={c.instrumento_id}>
                        <td className="px-3 py-2 font-semibold text-[#191818]">
                          {c.nombre}{" "}
                          <span className="text-[10px] text-neutral-400">({c.moneda})</span>
                        </td>
                        <td className="px-3 py-2 text-right text-neutral-700">
                          {c.moneda === "BS"
                            ? formatearBs(c.saldo_origen)
                            : formatearUsd(c.saldo_origen)}
                        </td>
                        <td className="px-3 py-2 text-right font-bold text-emerald-700">
                          {formatearUsd(c.equivalente_usd)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="bg-white/80 backdrop-blur-md rounded-2xl border border-white/70 shadow-[0_8px_30px_rgb(0,0,0,0.04)] p-5 space-y-4">
              <h3 className="text-sm font-black text-[#191818]">
                Inventario Físico, Tránsito y Comparativo Sucursales
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs tabular-nums">
                <div className="p-3 rounded-xl bg-emerald-50/70 border border-emerald-100">
                  <p className="text-[10px] font-bold text-emerald-700 uppercase">LISTO</p>
                  <p className="text-lg font-black text-emerald-800">{datos.inventario.unidades_listo}</p>
                </div>
                <div className="p-3 rounded-xl bg-amber-50/70 border border-amber-100">
                  <p className="text-[10px] font-bold text-amber-700 uppercase">Por Preparar / Hosp.</p>
                  <p className="text-lg font-black text-amber-800">
                    {datos.inventario.unidades_por_preparar} / {datos.inventario.unidades_hospital}
                  </p>
                </div>
                <div className="p-3 rounded-xl bg-blue-50/70 border border-blue-100">
                  <p className="text-[10px] font-bold text-blue-700 uppercase">En Tránsito</p>
                  <p className="text-lg font-black text-blue-800">
                    {datos.inventario.unidades_en_transito} ({datos.inventario.traslados_pendientes} trs)
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                {datos.inventario.listo_por_sucursal.map((s) => (
                  <span
                    key={s.sucursal}
                    className="inline-flex items-center gap-1.5 px-3 py-1 rounded-xl bg-neutral-100 text-xs font-bold text-[#191818] tabular-nums"
                  >
                    <Building2 className="w-3.5 h-3.5 text-[#E85A28]" />
                    {s.sucursal}: {s.unidades} LISTO
                  </span>
                ))}
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-neutral-50 text-neutral-500 uppercase text-[10px]">
                    <tr>
                      <th className="px-3 py-2">Sucursal</th>
                      <th className="px-3 py-2 text-right">Ventas Hoy</th>
                      <th className="px-3 py-2 text-right">Ventas Mes</th>
                      <th className="px-3 py-2 text-right">Utilidad Est.</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-100 tabular-nums">
                    {datos.pulso_comercial.comparativo_sucursales.map((s) => (
                      <tr key={s.sucursal}>
                        <td className="px-3 py-2 font-bold text-[#191818]">
                          {s.sucursal} ({s.ventas_mes_cant})
                        </td>
                        <td className="px-3 py-2 text-right">{formatearUsd(s.ventas_dia_usd)}</td>
                        <td className="px-3 py-2 text-right font-bold">{formatearUsd(s.ventas_mes_usd)}</td>
                        <td className="px-3 py-2 text-right font-bold text-emerald-700">
                          {formatearUsd(s.utilidad_mes_usd)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-neutral-500 tabular-nums">
                Comisiones pendientes por liquidar en el mes:{" "}
                <strong className="text-[#E85A28]">
                  {formatearUsd(datos.pulso_comercial.comisiones_pendientes_usd)}
                </strong>
              </p>
            </div>
          </div>

          {/* Resumen de Alertas Inteligentes */}
          <div className="bg-white/80 backdrop-blur-md rounded-2xl border border-white/70 shadow-[0_8px_30px_rgb(0,0,0,0.04)] p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-black text-[#191818] flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-[#E85A28]" />
                Alertas Inteligentes Activas ({datos.alertas.total_alertas})
              </h3>
              <span className="text-xs text-neutral-500 tabular-nums">
                Stock bajo: <strong>{datos.alertas.total_stock_bajo}</strong> · CxP por vencer:{" "}
                <strong className="text-red-700">{datos.alertas.total_cxp}</strong>
              </span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              <div className="space-y-1.5">
                <p className="font-bold text-amber-700 uppercase text-[10px]">
                  Modelos / Repuestos en Stock Bajo
                </p>
                {datos.alertas.stock_bajo.slice(0, 5).map((s) => (
                  <div
                    key={s.articulo_id}
                    className="flex items-center justify-between p-2 rounded-xl bg-amber-50/70 border border-amber-100"
                  >
                    <span className="font-semibold truncate pr-2">
                      {s.sku} · {s.descripcion}
                    </span>
                    <span className="font-black tabular-nums text-amber-900 shrink-0">
                      {s.stock_actual} / mín. {s.stock_minimo}
                    </span>
                  </div>
                ))}
                {datos.alertas.stock_bajo.length === 0 && (
                  <p className="text-neutral-400">Sin alertas de stock bajo.</p>
                )}
              </div>
              <div className="space-y-1.5">
                <p className="font-bold text-red-700 uppercase text-[10px]">
                  Cuentas por Pagar Vencidas o Próximas (7 días)
                </p>
                {datos.alertas.cxp_por_vencer.slice(0, 5).map((c) => (
                  <div
                    key={c.compra_id}
                    className="flex items-center justify-between p-2 rounded-xl bg-red-50/70 border border-red-100"
                  >
                    <span className="font-semibold truncate pr-2">
                      {c.proveedor} · {c.factura_orden} ({c.fecha_vencimiento})
                    </span>
                    <span className="font-black tabular-nums text-red-700 shrink-0">
                      {formatearUsd(c.saldo_pendiente_usd)}
                    </span>
                  </div>
                ))}
                {datos.alertas.cxp_por_vencer.length === 0 && (
                  <p className="text-neutral-400">Sin CxP vencidas ni próximas a vencer.</p>
                )}
              </div>
            </div>
          </div>
        </>
      ) : null}

      <ModalResumenEjecutivoPL
        abierto={modalResumenWa}
        alCerrar={() => setModalResumenWa(false)}
      />
    </div>
  );
}
