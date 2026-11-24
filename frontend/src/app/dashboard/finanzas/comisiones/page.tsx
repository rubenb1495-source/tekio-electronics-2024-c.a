"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, BarChart3, CheckCircle2, Lock } from "lucide-react";
import BuscadorTabla from "@/componentes/BuscadorTabla";
import { usarSesion } from "@/contexto/SesionContexto";
import { ErrorApi, formatearUsd, solicitarApi } from "@/servicios/api";
import type { ReporteComisiones, TableroFinanciero } from "@/tipos/finanzas";

export default function PaginaComisionesYCierre() {
  const { usuario } = usarSesion();
  const esDireccion = usuario?.rol === "DIRECCION";

  const hoy = new Date();
  const [mes, setMes] = useState(hoy.getMonth() + 1);
  const [anio, setAnio] = useState(hoy.getFullYear());
  const [busqueda, setBusqueda] = useState("");
  const [reporte, setReporte] = useState<ReporteComisiones | null>(null);
  const [tablero, setTablero] = useState<TableroFinanciero | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);
  const [modalCierre, setModalCierre] = useState(false);

  const cargarDatos = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [respCom, respTab] = await Promise.all([
        solicitarApi<ReporteComisiones>(
          `/api/finanzas/comisiones?mes=${mes}&anio=${anio}`
        ),
        solicitarApi<TableroFinanciero>("/api/finanzas/tablero"),
      ]);
      setReporte(respCom);
      setTablero(respTab);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudieron cargar las comisiones y el tablero."
      );
    } finally {
      setCargando(false);
    }
  }, [mes, anio]);

  useEffect(() => {
    void cargarDatos();
  }, [cargarDatos]);

  const confirmarCierreMes = async () => {
    setError(null);
    setExito(null);
    try {
      await solicitarApi("/api/finanzas/cierres-mensuales", {
        method: "POST",
        body: JSON.stringify({ anio, mes }),
      });
      setModalCierre(false);
      setExito(
        `Período ${String(mes).padStart(2, "0")}/${anio} cerrado y bloqueado correctamente.`
      );
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "No se pudo cerrar el mes."
      );
    }
  };

  const comisionesFiltradas = useMemo(() => {
    const lista = reporte?.comisiones ?? [];
    const q = busqueda.trim().toLowerCase();
    if (!q) return lista;
    return lista.filter((c) =>
      `${c.nombre} ${c.rol}`.toLowerCase().includes(q)
    );
  }, [reporte, busqueda]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900 flex items-center gap-2">
            <BarChart3 className="w-6 h-6 text-[#E85A28]" />
            Tablero Financiero, Comisiones y Cierre de Mes
          </h2>
          <p className="text-sm text-slate-500">
            Solo Dirección y Administración. Cálculo sobre Precio Promo
            excluyendo ventas anuladas.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <input
            type="number"
            min={1}
            max={12}
            value={mes}
            onChange={(e) => setMes(Number(e.target.value))}
            className="w-20 px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
          />
          <input
            type="number"
            min={2024}
            max={2100}
            value={anio}
            onChange={(e) => setAnio(Number(e.target.value))}
            className="w-24 px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
          />
          {esDireccion && !reporte?.mes_cerrado && (
            <button
              type="button"
              onClick={() => setModalCierre(true)}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-slate-900 text-white text-xs font-bold cursor-pointer"
            >
              <Lock className="w-3.5 h-3.5" />
              Cerrar mes
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2.5 p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}
      {exito && (
        <div className="flex items-center gap-2.5 p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-sm text-emerald-700">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{exito}</span>
        </div>
      )}

      {/* KPIs del Tablero Financiero */}
      {tablero && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <div className="bg-white p-4 rounded-2xl border border-[#E5E7EB] border-t-2 border-t-[#191818]">
            <p className="text-[11px] font-bold uppercase tracking-wider text-neutral-500">
              Venta Promo
            </p>
            <p className="text-xl font-black text-[#191818] mt-1 cifra-tabular">
              {formatearUsd(tablero.venta_promo_usd)}
            </p>
          </div>
          <div className="bg-white p-4 rounded-2xl border border-[#E5E7EB] border-t-2 border-t-emerald-600">
            <p className="text-[11px] font-bold uppercase tracking-wider text-neutral-500">
              USD Real
            </p>
            <p className="text-xl font-black text-emerald-700 mt-1 cifra-tabular">
              {formatearUsd(tablero.usd_real)}
            </p>
          </div>
          <div className="bg-white p-4 rounded-2xl border border-[#E5E7EB] border-t-2 border-t-[#E85A28]">
            <p className="text-[11px] font-bold uppercase tracking-wider text-neutral-500">
              Diferencial
            </p>
            <p className="text-xl font-black text-[#E85A28] mt-1 cifra-tabular">
              {formatearUsd(tablero.diferencial_cambiario_usd)}
            </p>
          </div>
          <div className="bg-white p-4 rounded-2xl border border-[#E5E7EB] border-t-2 border-t-[#191818]">
            <p className="text-[11px] font-bold uppercase tracking-wider text-neutral-500">
              Cashea x Cobrar
            </p>
            <p className="text-xl font-black text-[#191818] mt-1 cifra-tabular">
              {formatearUsd(tablero.cashea_por_cobrar_usd)}
            </p>
          </div>
          <div className="bg-[#191818] p-4 rounded-2xl border border-[#2E2D2D] border-t-2 border-t-[#E85A28] text-white">
            <p className="text-[11px] font-bold uppercase tracking-wider text-[#E85A28]">
              Utilidad Real Neta
            </p>
            <p className="text-xl font-black mt-1 cifra-tabular">
              {formatearUsd(tablero.utilidad_real_neta_usd)}
            </p>
          </div>
        </div>
      )}

      {/* Tabla de comisiones */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3">
          <span className="font-bold text-sm">
            Comisiones del período {String(mes).padStart(2, "0")}/{anio}
          </span>
          <div className="flex items-center gap-3 flex-1 max-w-md">
            <BuscadorTabla
              valor={busqueda}
              alCambiar={setBusqueda}
              placeholder="Buscar por persona o rol..."
              totalRegistros={reporte?.comisiones.length ?? 0}
              totalFiltrados={comisionesFiltradas.length}
            />
          </div>
          {reporte?.mes_cerrado && (
            <span className="px-2.5 py-1 rounded-full bg-slate-900 text-white text-xs font-bold">
              MES CERRADO Y BLOQUEADO
            </span>
          )}
        </div>

        {cargando ? (
          <div className="p-6 h-24 bg-slate-100 animate-pulse" />
        ) : comisionesFiltradas.length === 0 ? (
          <p className="p-8 text-center text-sm text-slate-500">
            No hay comisiones que coincidan.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Persona</th>
                  <th className="px-4 py-3">Rol</th>
                  <th className="px-4 py-3 text-right">Ventas Promo</th>
                  <th className="px-4 py-3 text-right">1% Ventas</th>
                  <th className="px-4 py-3 text-right">0.5% Líder</th>
                  <th className="px-4 py-3 text-right">50% ST</th>
                  <th className="px-4 py-3 text-right">Preps</th>
                  <th className="px-4 py-3 text-right">Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {comisionesFiltradas.map((c) => (
                  <tr key={c.usuario_id}>
                    <td className="px-4 py-3 font-bold">{c.nombre}</td>
                    <td className="px-4 py-3 text-xs">{c.rol}</td>
                    <td className="px-4 py-3 text-right">
                      {formatearUsd(c.ventas_promo_usd)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {formatearUsd(c.comision_ventas_1_usd)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {formatearUsd(c.comision_lider_05_usd)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {formatearUsd(c.comision_servicios_50_usd)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {formatearUsd(c.pago_preparaciones_usd)}
                    </td>
                    <td className="px-4 py-3 text-right font-black text-emerald-700">
                      {formatearUsd(c.total_comision_usd)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modalCierre && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4">
            <h3 className="text-lg font-black text-slate-900">
              Confirmar cierre de {String(mes).padStart(2, "0")}/{anio}
            </h3>
            <p className="text-sm text-slate-600">
              Al cerrar el mes se bloqueará el registro o anulación de ventas,
              pagos y devoluciones dentro de este período. El historial nunca se
              borra.
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setModalCierre(false)}
                className="px-4 py-2 rounded-xl border border-slate-300 text-sm font-semibold cursor-pointer"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={() => void confirmarCierreMes()}
                className="px-4 py-2 rounded-xl bg-slate-900 text-white text-sm font-bold cursor-pointer"
              >
                Confirmar cierre inmutable
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
