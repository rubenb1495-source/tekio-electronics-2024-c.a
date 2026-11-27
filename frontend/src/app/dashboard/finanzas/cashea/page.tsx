"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  CreditCard,
  Download,
  FileSpreadsheet,
  Pencil,
  X,
} from "lucide-react";
import BuscadorTabla from "@/componentes/BuscadorTabla";
import ModalImportarCashea from "@/components/ModalImportarCashea";
import {
  descargarPdfApi,
  ErrorApi,
  formatearBs,
  formatearUsd,
  solicitarApi,
} from "@/servicios/api";
import type { Sucursal } from "@/tipos/dominio";
import type {
  CasheaConciliacionRespuesta,
  CasheaItemConciliacion,
  InstrumentoFinanciero,
} from "@/tipos/finanzas";

type FiltroEstadoCashea = "TODOS" | "PENDIENTE" | "CONCILIADO";

export default function PaginaFinanzasCashea() {
  const [items, setItems] = useState<CasheaItemConciliacion[]>([]);
  const [conteo, setConteo] = useState({ todos: 0, pendientes: 0, conciliados: 0 });
  const [kpis, setKpis] = useState<CasheaConciliacionRespuesta["kpis"] | null>(null);
  const [instrumentos, setInstrumentos] = useState<InstrumentoFinanciero[]>([]);
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);

  // Filtros
  const [estadoFiltro, setEstadoFiltro] = useState<FiltroEstadoCashea>("PENDIENTE");
  const [fechaInicio, setFechaInicio] = useState("");
  const [fechaFin, setFechaFin] = useState("");
  const [sucursalId, setSucursalId] = useState("");
  const [busqueda, setBusqueda] = useState("");

  // Edición inline de cashea_numero_orden en notas pendientes
  const [editandoVentaId, setEditandoVentaId] = useState<number | null>(null);
  const [ordenEdit, setOrdenEdit] = useState("");
  const [guardandoOrden, setGuardandoOrden] = useState(false);

  // Modal de importación de reporte Cashea
  const [modalImportarAbierto, setModalImportarAbierto] = useState(false);
  const [exportando, setExportando] = useState(false);

  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  const construirQueryParams = useCallback(() => {
    const params = new URLSearchParams();
    params.set("estado_conciliacion", estadoFiltro);
    if (fechaInicio) params.set("fecha_inicio", fechaInicio);
    if (fechaFin) params.set("fecha_fin", fechaFin);
    if (sucursalId) params.set("sucursal_id", sucursalId);
    if (busqueda.trim()) params.set("buscar", busqueda.trim());
    return params.toString();
  }, [estadoFiltro, fechaInicio, fechaFin, sucursalId, busqueda]);

  const cargarDatos = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const qs = construirQueryParams();
      const [respCashea, respInst, respSuc] = await Promise.all([
        solicitarApi<CasheaConciliacionRespuesta>(`/api/finanzas/cashea?${qs}`),
        solicitarApi<InstrumentoFinanciero[]>("/api/finanzas/instrumentos"),
        solicitarApi<Sucursal[]>("/api/sucursales"),
      ]);
      // Garantizar estrictamente 1 fila única por venta_id
      const unicas = new Map<number, CasheaItemConciliacion>();
      for (const it of respCashea.items) {
        if (!unicas.has(it.venta_id)) {
          unicas.set(it.venta_id, it);
        }
      }
      setItems(Array.from(unicas.values()));
      setConteo(respCashea.conteo);
      setKpis(respCashea.kpis);
      setInstrumentos(respInst);
      setSucursales(respSuc);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo cargar la conciliación financiera Cashea."
      );
    } finally {
      setCargando(false);
    }
  }, [construirQueryParams]);

  useEffect(() => {
    void cargarDatos();
  }, [cargarDatos]);

  const exportarExcel = async () => {
    setExportando(true);
    setError(null);
    try {
      const qs = construirQueryParams();
      await descargarPdfApi(
        `/api/finanzas/cashea/exportar-xlsx?${qs}`,
        `conciliacion_cashea_${estadoFiltro.toLowerCase()}.xlsx`
      );
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo exportar el archivo Excel de Cashea."
      );
    } finally {
      setExportando(false);
    }
  };

  const guardarOrdenCashea = async (ventaId: number) => {
    if (!ordenEdit.trim()) return;
    setGuardandoOrden(true);
    setError(null);
    setExito(null);
    try {
      await solicitarApi(`/api/finanzas/cashea/${ventaId}/orden`, {
        method: "PATCH",
        body: JSON.stringify({
          cashea_numero_orden: ordenEdit.trim().toUpperCase(),
        }),
      });
      setEditandoVentaId(null);
      setOrdenEdit("");
      setExito("Número de orden Cashea actualizado correctamente.");
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo actualizar el número de orden Cashea."
      );
    } finally {
      setGuardandoOrden(false);
    }
  };

  const kpiResumen = useMemo(() => {
    if (kpis) return kpis;
    return {
      financiado_bruto_usd: 0,
      comision_venta_total_usd: 0,
      comision_financiado_usd: 0,
      iva_cashea_usd: 0,
      islr_cashea_usd: 0,
      total_deducciones_usd: 0,
      neto_real_esperado_usd: 0,
      pagado_real_usd: 0,
      descuento_real_usd: 0,
      diferencia_neta_usd: 0,
    };
  }, [kpis]);

  return (
    <div className="space-y-6">
      {/* Cabecera + Botones principales */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-[#191818] flex items-center gap-2">
            <CreditCard className="w-6 h-6 text-[#E85A28]" />
            Conciliación Financiera Cashea (Solo Administración / Dirección)
          </h2>
          <p className="text-xs text-neutral-500 mt-0.5">
            Control 1:1 por nota: 4% sobre total Regular + 4% sobre financiado + 16% IVA + 2% ISLR y liquidación automática por reporte Cashea.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            disabled={exportando}
            onClick={() => void exportarExcel()}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-neutral-300 bg-white/90 hover:bg-neutral-50 text-[#191818] text-xs font-bold shadow-xs cursor-pointer disabled:opacity-50"
          >
            <Download className="w-4 h-4 text-[#E85A28]" />
            {exportando ? "Exportando..." : "Exportar Excel (.xlsx)"}
          </button>

          <button
            type="button"
            onClick={() => setModalImportarAbierto(true)}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] text-white text-xs font-black shadow-sm cursor-pointer transition-colors"
          >
            <FileSpreadsheet className="w-4 h-4" />
            Cargar Reporte Cashea (Liquidar)
          </button>
        </div>
      </div>

      {/* KPIs Consolidados sobre notas únicas */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 tabular-nums">
        <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-4">
          <p className="text-[11px] font-bold uppercase text-neutral-500">Financiado Bruto</p>
          <p className="text-xl font-black text-[#191818] mt-1">
            {formatearUsd(kpiResumen.financiado_bruto_usd)}
          </p>
        </div>
        <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-4">
          <p className="text-[11px] font-bold uppercase text-neutral-500">4% Total + 4% Fin.</p>
          <p className="text-xl font-black text-amber-700 mt-1">
            -{formatearUsd(kpiResumen.comision_venta_total_usd + kpiResumen.comision_financiado_usd)}
          </p>
        </div>
        <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-4">
          <p className="text-[11px] font-bold uppercase text-neutral-500">16% IVA + 2% ISLR</p>
          <p className="text-xl font-black text-amber-700 mt-1">
            -{formatearUsd(kpiResumen.iva_cashea_usd + kpiResumen.islr_cashea_usd)}
          </p>
        </div>
        <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-4">
          <p className="text-[11px] font-bold uppercase text-neutral-500">Total Deducciones</p>
          <p className="text-xl font-black text-red-700 mt-1">
            -{formatearUsd(kpiResumen.total_deducciones_usd)}
          </p>
        </div>
        <div className="bg-[#FDF0EB] border border-[#E85A28]/30 rounded-2xl p-4">
          <p className="text-[11px] font-bold uppercase text-[#E85A28]">
            {estadoFiltro === "CONCILIADO" ? "Pagado Real Cashea" : "Neto Real Esperado"}
          </p>
          <p className="text-xl font-black text-[#191818] mt-1">
            {formatearUsd(
              estadoFiltro === "CONCILIADO"
                ? kpiResumen.pagado_real_usd
                : kpiResumen.neto_real_esperado_usd
            )}
          </p>
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

      {/* Pills de Estado + Filtros */}
      <div className="bg-white/80 backdrop-blur-md border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1.5 bg-[#F6F6F6] p-1 rounded-xl border border-neutral-200">
            {(
              [
                { key: "TODOS", label: "Todos", count: conteo.todos },
                { key: "PENDIENTE", label: "Pendientes", count: conteo.pendientes },
                { key: "CONCILIADO", label: "Conciliados", count: conteo.conciliados },
              ] as const
            ).map((tab) => {
              const activo = estadoFiltro === tab.key;
              return (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setEstadoFiltro(tab.key)}
                  className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer ${
                    activo
                      ? "bg-[#E85A28] text-white shadow-xs"
                      : "text-neutral-600 hover:text-[#191818]"
                  }`}
                >
                  <span>{tab.label}</span>
                  <span
                    className={`px-1.5 py-0.5 rounded-full text-[10px] tabular-nums ${
                      activo ? "bg-white/25 text-white" : "bg-neutral-200 text-neutral-700"
                    }`}
                  >
                    {tab.count}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <input
              type="date"
              value={fechaInicio}
              onChange={(e) => setFechaInicio(e.target.value)}
              className="px-2.5 py-1.5 rounded-lg border border-neutral-300 bg-white"
              aria-label="Fecha inicio"
            />
            <span className="text-neutral-400">a</span>
            <input
              type="date"
              value={fechaFin}
              onChange={(e) => setFechaFin(e.target.value)}
              className="px-2.5 py-1.5 rounded-lg border border-neutral-300 bg-white"
              aria-label="Fecha fin"
            />
            <select
              value={sucursalId}
              onChange={(e) => setSucursalId(e.target.value)}
              className="px-2.5 py-1.5 rounded-lg border border-neutral-300 bg-white"
            >
              <option value="">Todas las sucursales</option>
              {sucursales.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nombre}
                </option>
              ))}
            </select>
          </div>
        </div>

        <BuscadorTabla
          valor={busqueda}
          alCambiar={setBusqueda}
          placeholder="Buscar por N-XXXX, Nro. Orden Cashea, cliente o sucursal..."
          totalRegistros={conteo.todos}
          totalFiltrados={items.length}
        />
      </div>

      {/* Tabla de Notas Cashea (1 fila única por venta_id) */}
      <div className="bg-white/80 backdrop-blur-md border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl overflow-hidden">
        {cargando ? (
          <div className="p-6 h-24 bg-slate-100 animate-pulse" />
        ) : items.length === 0 ? (
          <p className="p-10 text-center text-sm text-neutral-500">
            No hay notas Cashea para los filtros seleccionados.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-neutral-50/90 border-b border-neutral-200 text-[11px] uppercase text-neutral-500">
                <tr>
                  <th className="px-3 py-3">Nota / Fecha</th>
                  <th className="px-3 py-3">Nro. Orden Cashea</th>
                  <th className="px-3 py-3">Sucursal / Cliente</th>
                  <th className="px-3 py-3 text-right">Regular (USDT / Bs)</th>
                  <th className="px-3 py-3 text-right">Financiado</th>
                  <th className="px-3 py-3 text-right">Deducciones Esp.</th>
                  <th className="px-3 py-3 text-right">Neto Esperado</th>
                  <th className="px-3 py-3 text-right">Pagado Real / Diff</th>
                  <th className="px-3 py-3 text-center">Estado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100 tabular-nums">
                {items.map((c) => {
                  const editando = editandoVentaId === c.venta_id;
                  const esConc = c.cashea_estado_conciliacion === "CONCILIADO";
                  const diff = c.cashea_diferencia_usd;
                  return (
                    <tr key={c.venta_id} className="hover:bg-white/70">
                      <td className="px-3 py-3">
                        <p className="font-mono font-bold text-[#191818]">{c.numero_venta}</p>
                        <p className="text-[11px] text-neutral-500">{c.fecha_venta}</p>
                      </td>
                      <td className="px-3 py-3">
                        {editando ? (
                          <div className="flex items-center gap-1">
                            <input
                              type="text"
                              value={ordenEdit}
                              onChange={(e) => setOrdenEdit(e.target.value.toUpperCase())}
                              placeholder="CSH-..."
                              className="w-28 px-2 py-1 rounded-lg border border-[#E85A28] font-mono text-xs bg-white"
                            />
                            <button
                              type="button"
                              disabled={guardandoOrden}
                              onClick={() => void guardarOrdenCashea(c.venta_id)}
                              className="p-1 rounded-lg bg-emerald-600 text-white cursor-pointer"
                              title="Guardar orden"
                            >
                              <Check className="w-3.5 h-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setEditandoVentaId(null);
                                setOrdenEdit("");
                              }}
                              className="p-1 rounded-lg bg-neutral-200 text-neutral-700 cursor-pointer"
                              title="Cancelar"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5">
                            <span
                              className={`font-mono font-bold ${
                                c.cashea_numero_orden ? "text-[#191818]" : "text-amber-700 italic"
                              }`}
                            >
                              {c.cashea_numero_orden || "Sin orden"}
                            </span>
                            {!esConc && (
                              <button
                                type="button"
                                onClick={() => {
                                  setEditandoVentaId(c.venta_id);
                                  setOrdenEdit(c.cashea_numero_orden || "");
                                }}
                                title="Asignar o editar Nro. de Orden Cashea"
                                className="p-1 rounded-md hover:bg-neutral-100 text-neutral-400 hover:text-[#E85A28] cursor-pointer"
                              >
                                <Pencil className="w-3 h-3" />
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-3">
                        <p className="font-semibold text-[#191818]">{c.sucursal}</p>
                        <p className="text-[11px] text-neutral-500">{c.cliente}</p>
                      </td>
                      <td className="px-3 py-3 text-right">
                        <p className="font-bold">{formatearUsd(c.total_regular_usd)}</p>
                        <p className="text-[10px] text-neutral-500">
                          {formatearBs(c.precio_regular_bs)}
                        </p>
                      </td>
                      <td className="px-3 py-3 text-right font-bold text-[#191818]">
                        {formatearUsd(c.monto_original_usd)}
                      </td>
                      <td className="px-3 py-3 text-right font-bold text-red-700">
                        -{formatearUsd(c.total_deducciones_cashea_usd)}
                      </td>
                      <td className="px-3 py-3 text-right font-black text-emerald-700">
                        {formatearUsd(c.neto_esperado_cashea_usd)}
                      </td>
                      <td className="px-3 py-3 text-right">
                        {c.cashea_monto_pagado_real_usd !== null ? (
                          <>
                            <p className="font-black text-[#191818]">
                              {formatearUsd(c.cashea_monto_pagado_real_usd)}
                            </p>
                            {diff !== null && (
                              <p
                                className={`text-[10px] font-bold ${
                                  Math.abs(diff) < 0.01 ? "text-emerald-700" : "text-red-600"
                                }`}
                              >
                                {diff >= 0 ? "+" : ""}
                                {formatearUsd(diff)}
                              </p>
                            )}
                          </>
                        ) : (
                          <span className="text-neutral-400">—</span>
                        )}
                      </td>
                      <td className="px-3 py-3 text-center">
                        <span
                          className={`inline-flex px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${
                            esConc
                              ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                              : "bg-amber-50 text-amber-800 border-amber-200"
                          }`}
                        >
                          {esConc ? "Conciliado" : "Pendiente"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal de Carga y Liquidación en Lote de Reporte Cashea */}
      <ModalImportarCashea
        abierto={modalImportarAbierto}
        instrumentos={instrumentos}
        alCerrar={() => setModalImportarAbierto(false)}
        alConfirmarExito={(msg) => {
          setExito(msg);
          void cargarDatos();
        }}
      />
    </div>
  );
}
