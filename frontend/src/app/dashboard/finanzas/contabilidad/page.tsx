"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  FileDown,
  FileSpreadsheet,
  MessageCircle,
  Plus,
} from "lucide-react";
import BuscadorTabla from "@/componentes/BuscadorTabla";
import ModalResumenEjecutivoPL from "@/components/ModalResumenEjecutivoPL";
import PanelImportacionAdmin from "@/components/PanelImportacionAdmin";
import {
  ErrorApi,
  descargarPdfApi,
  fechaHoyCaracas,
  formatearBs,
  formatearUsd,
  solicitarApi,
} from "@/servicios/api";
import type { Sucursal } from "@/tipos/dominio";
import type { InstrumentoFinanciero } from "@/tipos/finanzas";

interface GastoItem {
  id: number;
  codigo: string;
  fecha: string;
  categoria: string;
  sucursal: string;
  proveedor: string;
  factura_comprobante: string;
  descripcion: string;
  moneda: string;
  monto_origen: number;
  monto_usd: number;
  instrumento: string;
  usuario: string;
}

interface EstadoResultados {
  fecha_inicio: string;
  fecha_fin: string;
  sucursal: string;
  cantidad_ventas: number;
  ingresos_ventas_usd: number;
  costo_mercancia_usd: number;
  utilidad_bruta_usd: number;
  gastos_operativos_usd: number;
  comisiones_liquidadas_usd: number;
  nomina_pagada_usd: number;
  diferencial_cambiario_usd: number;
  utilidad_neta_usd: number;
  gastos_por_categoria: { categoria: string; cantidad: number; total_usd: number }[];
}

const CATEGORIAS = [
  "ALQUILER",
  "SERVICIOS",
  "NOMINA",
  "PUBLICIDAD",
  "MANTENIMIENTO",
  "IMPUESTOS",
  "LOGISTICA_ENVIOS",
  "OTROS",
];

export default function PaginaContabilidadPyL() {
  const hoy = fechaHoyCaracas();
  const inicioMes = `${hoy.slice(0, 8)}01`;

  const [fechaInicio, setFechaInicio] = useState(inicioMes);
  const [fechaFin, setFechaFin] = useState(hoy);
  const [sucursalFiltro, setSucursalFiltro] = useState("");
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [instrumentos, setInstrumentos] = useState<InstrumentoFinanciero[]>([]);
  const [pyl, setPyl] = useState<EstadoResultados | null>(null);
  const [gastos, setGastos] = useState<GastoItem[]>([]);
  const [busqueda, setBusqueda] = useState("");
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);
  const [modalResumenWa, setModalResumenWa] = useState(false);

  // Formulario gasto
  const [fechaGasto, setFechaGasto] = useState(hoy);
  const [categoria, setCategoria] = useState("ALQUILER");
  const [sucursalGasto, setSucursalGasto] = useState("");
  const [instrumentoId, setInstrumentoId] = useState("");
  const [moneda, setMoneda] = useState<"USD" | "USDT" | "BS">("USD");
  const [montoOrigen, setMontoOrigen] = useState("");
  const [proveedor, setProveedor] = useState("");
  const [factura, setFactura] = useState("");
  const [descripcion, setDescripcion] = useState("");

  useEffect(() => {
    Promise.all([
      solicitarApi<Sucursal[]>("/api/sucursales").catch(() => []),
      solicitarApi<InstrumentoFinanciero[]>("/api/finanzas/instrumentos").catch(() => []),
    ]).then(([s, i]) => {
      setSucursales(s);
      setInstrumentos(i);
    });
  }, []);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ fecha_inicio: fechaInicio, fecha_fin: fechaFin });
      if (sucursalFiltro) qs.set("sucursal_id", sucursalFiltro);
      const [respPyl, respGastos] = await Promise.all([
        solicitarApi<EstadoResultados>(`/api/finanzas/estado-resultados?${qs.toString()}`),
        solicitarApi<GastoItem[]>(`/api/finanzas/gastos?${qs.toString()}`),
      ]);
      setPyl(respPyl);
      setGastos(respGastos);
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo cargar Contabilidad.");
    } finally {
      setCargando(false);
    }
  }, [fechaInicio, fechaFin, sucursalFiltro]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const registrarGasto = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setGuardando(true);
    setError(null);
    setExito(null);
    try {
      const res = await solicitarApi<{ codigo: string }>("/api/finanzas/gastos", {
        method: "POST",
        body: JSON.stringify({
          fecha: fechaGasto,
          categoria,
          sucursal_id: sucursalGasto ? Number(sucursalGasto) : null,
          proveedor: proveedor.trim(),
          factura_comprobante: factura.trim(),
          descripcion: descripcion.trim(),
          moneda,
          monto_origen: Number(montoOrigen),
          instrumento_id: Number(instrumentoId),
        }),
      });
      setExito(`Gasto ${res.codigo} registrado y descontado del instrumento seleccionado.`);
      setMontoOrigen("");
      setProveedor("");
      setFactura("");
      setDescripcion("");
      await cargar();
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo registrar el gasto.");
    } finally {
      setGuardando(false);
    }
  };

  const gastosFiltrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return gastos;
    return gastos.filter((g) =>
      [g.codigo, g.categoria, g.proveedor, g.factura_comprobante, g.descripcion, g.sucursal]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [gastos, busqueda]);

  const qsExport = `fecha_inicio=${fechaInicio}&fecha_fin=${fechaFin}${sucursalFiltro ? `&sucursal_id=${sucursalFiltro}` : ""}`;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-black text-[#191818]">
            Contabilidad · Gastos Operativos y Estado de Resultados (P&L)
          </h2>
          <p className="text-sm text-neutral-500">
            Registro de egresos administrativos por categoría y P&L en vivo exportable a PDF y Excel.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="date"
            value={fechaInicio}
            onChange={(e) => setFechaInicio(e.target.value)}
            className="px-3 py-2 rounded-xl border border-neutral-200 bg-white text-xs"
          />
          <input
            type="date"
            value={fechaFin}
            onChange={(e) => setFechaFin(e.target.value)}
            className="px-3 py-2 rounded-xl border border-neutral-200 bg-white text-xs"
          />
          <select
            value={sucursalFiltro}
            onChange={(e) => setSucursalFiltro(e.target.value)}
            className="px-3 py-2 rounded-xl border border-neutral-200 bg-white text-xs"
          >
            <option value="">Todas las sucursales</option>
            {sucursales.map((s) => (
              <option key={s.id} value={String(s.id)}>{s.nombre}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => setModalResumenWa(true)}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] text-white text-xs font-bold cursor-pointer shadow-xs"
          >
            <MessageCircle className="w-3.5 h-3.5" />
            Resumen Ejecutivo WhatsApp
          </button>
          <button
            type="button"
            onClick={() => void descargarPdfApi(`/api/finanzas/estado-resultados/pdf?${qsExport}`, `Estado_Resultados_${fechaInicio}.pdf`)}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-[#E85A28]/40 bg-[#FDF0EB] text-[#E85A28] text-xs font-bold cursor-pointer"
          >
            <FileDown className="w-3.5 h-3.5" />
            P&L PDF
          </button>
          <button
            type="button"
            onClick={() => void descargarPdfApi(`/api/finanzas/estado-resultados/xlsx?${qsExport}`, `Estado_Resultados_${fechaInicio}.xlsx`)}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-[#191818] text-white text-xs font-bold cursor-pointer"
          >
            <FileSpreadsheet className="w-3.5 h-3.5" />
            P&L Excel
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3.5 rounded-2xl bg-red-50 border border-red-200 text-xs text-red-700 font-semibold">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}
      {exito && (
        <div className="flex items-center gap-2 p-3.5 rounded-2xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 font-semibold">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{exito}</span>
        </div>
      )}

      {/* Tarjetas Estado de Resultados (P&L) */}
      {pyl && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 tabular-nums">
          <div className="bg-white/80 backdrop-blur-md p-4 rounded-2xl border border-white/70 shadow-xs">
            <p className="text-[11px] font-bold uppercase text-neutral-500">Ingresos Ventas ({pyl.cantidad_ventas})</p>
            <p className="text-xl font-black text-[#191818] mt-1">{formatearUsd(pyl.ingresos_ventas_usd)}</p>
            <p className="text-[11px] text-neutral-500">COGS: -{formatearUsd(pyl.costo_mercancia_usd)}</p>
          </div>
          <div className="bg-white/80 backdrop-blur-md p-4 rounded-2xl border border-white/70 shadow-xs">
            <p className="text-[11px] font-bold uppercase text-neutral-500">Utilidad Bruta</p>
            <p className="text-xl font-black text-emerald-700 mt-1">{formatearUsd(pyl.utilidad_bruta_usd)}</p>
            <p className="text-[11px] text-neutral-500">Dif. Cambiario: {formatearUsd(pyl.diferencial_cambiario_usd)}</p>
          </div>
          <div className="bg-white/80 backdrop-blur-md p-4 rounded-2xl border border-white/70 shadow-xs">
            <p className="text-[11px] font-bold uppercase text-neutral-500">Gastos + Comisiones + Nómina</p>
            <p className="text-xl font-black text-red-700 mt-1">
              -{formatearUsd(pyl.gastos_operativos_usd + pyl.comisiones_liquidadas_usd + pyl.nomina_pagada_usd)}
            </p>
            <p className="text-[11px] text-neutral-500">
              Gastos: {formatearUsd(pyl.gastos_operativos_usd)} · Nómina: {formatearUsd(pyl.nomina_pagada_usd)}
            </p>
          </div>
          <div className="bg-white/80 backdrop-blur-md p-4 rounded-2xl border-2 border-[#E85A28]/30 shadow-xs">
            <p className="text-[11px] font-bold uppercase text-[#E85A28]">Utilidad Neta del Período</p>
            <p className={`text-2xl font-black mt-1 ${pyl.utilidad_neta_usd >= 0 ? "text-emerald-700" : "text-red-700"}`}>
              {formatearUsd(pyl.utilidad_neta_usd)}
            </p>
            <p className="text-[11px] text-neutral-500">{pyl.sucursal}</p>
          </div>
        </div>
      )}

      {/* Registrar Gasto Operativo */}
      <form
        onSubmit={registrarGasto}
        className="bg-white/80 backdrop-blur-md border border-white/70 rounded-2xl p-5 shadow-xs space-y-3"
      >
        <h3 className="text-sm font-black text-[#191818] flex items-center gap-1.5">
          <Plus className="w-4 h-4 text-[#E85A28]" />
          Registrar Gasto Operativo (descuenta automáticamente del banco/caja)
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
          <input type="date" required value={fechaGasto} onChange={(e) => setFechaGasto(e.target.value)} className="px-3 py-2 rounded-xl border border-neutral-200 bg-white" />
          <select value={categoria} onChange={(e) => setCategoria(e.target.value)} className="px-3 py-2 rounded-xl border border-neutral-200 bg-white font-bold">
            {CATEGORIAS.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={sucursalGasto} onChange={(e) => setSucursalGasto(e.target.value)} className="px-3 py-2 rounded-xl border border-neutral-200 bg-white">
            <option value="">General (Todas)</option>
            {sucursales.map((s) => <option key={s.id} value={String(s.id)}>{s.nombre}</option>)}
          </select>
          <select required value={instrumentoId} onChange={(e) => {
            setInstrumentoId(e.target.value);
            const found = instrumentos.find((i) => String(i.id) === e.target.value);
            if (found) setMoneda((found.moneda === "BS" ? "BS" : found.moneda === "USDT" ? "USDT" : "USD"));
          }} className="px-3 py-2 rounded-xl border border-neutral-200 bg-white">
            <option value="">Cuenta / Banco...</option>
            {instrumentos.map((i) => <option key={i.id} value={String(i.id)}>{i.nombre} ({i.moneda})</option>)}
          </select>
          <input type="number" step="0.01" min="0.01" required value={montoOrigen} onChange={(e) => setMontoOrigen(e.target.value)} placeholder={`Monto (${moneda})`} className="px-3 py-2 rounded-xl border border-neutral-200 bg-white tabular-nums" />
          <input type="text" value={proveedor} onChange={(e) => setProveedor(e.target.value)} placeholder="Proveedor / Beneficiario" className="px-3 py-2 rounded-xl border border-neutral-200 bg-white" />
          <input type="text" value={factura} onChange={(e) => setFactura(e.target.value)} placeholder="Nro. Factura / Comprobante" className="px-3 py-2 rounded-xl border border-neutral-200 bg-white" />
          <div className="flex gap-2">
            <input type="text" value={descripcion} onChange={(e) => setDescripcion(e.target.value)} placeholder="Descripción..." className="flex-1 px-3 py-2 rounded-xl border border-neutral-200 bg-white" />
            <button type="submit" disabled={guardando} className="px-4 py-2 rounded-xl bg-[#E85A28] text-white font-bold cursor-pointer disabled:opacity-50">
              {guardando ? "..." : "Guardar"}
            </button>
          </div>
        </div>
      </form>

      <PanelImportacionAdmin flujoInicial="gastos_operativos" alCompletar={() => void cargar()} />

      {/* Historial de Gastos */}
      <div className="bg-white/80 backdrop-blur-md border border-white/70 rounded-2xl p-5 shadow-xs space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-sm font-black text-[#191818]">Gastos Registrados ({gastosFiltrados.length})</h3>
          <div className="w-full sm:w-80">
            <BuscadorTabla valor={busqueda} alCambiar={setBusqueda} placeholder="Buscar gasto por categoría, proveedor..." />
          </div>
        </div>
        {cargando ? (
          <div className="h-24 rounded-xl bg-neutral-100 animate-pulse" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-neutral-50 border-b border-neutral-200 uppercase text-[10px] text-neutral-500">
                <tr>
                  <th className="px-3 py-2">Código / Fecha</th>
                  <th className="px-3 py-2">Categoría / Sucursal</th>
                  <th className="px-3 py-2">Proveedor / Factura</th>
                  <th className="px-3 py-2">Cuenta</th>
                  <th className="px-3 py-2 text-right">Monto USD</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100 tabular-nums">
                {gastosFiltrados.map((g) => (
                  <tr key={g.id}>
                    <td className="px-3 py-2">
                      <p className="font-mono font-bold">{g.codigo}</p>
                      <p className="text-[11px] text-neutral-500">{g.fecha}</p>
                    </td>
                    <td className="px-3 py-2">
                      <span className="px-2 py-0.5 rounded-full bg-[#FDF0EB] text-[#E85A28] font-bold text-[10px]">{g.categoria}</span>
                      <p className="text-[11px] text-neutral-500 mt-0.5">{g.sucursal}</p>
                    </td>
                    <td className="px-3 py-2">
                      <p className="font-semibold">{g.proveedor || "—"}</p>
                      <p className="text-[11px] text-neutral-500">{g.factura_comprobante} · {g.descripcion}</p>
                    </td>
                    <td className="px-3 py-2">
                      <p className="font-semibold">{g.instrumento}</p>
                      <p className="text-[11px] text-neutral-500">
                        {g.moneda === "BS" ? formatearBs(g.monto_origen) : formatearUsd(g.monto_origen)}
                      </p>
                    </td>
                    <td className="px-3 py-2 text-right font-black text-red-700">
                      -{formatearUsd(g.monto_usd)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <ModalResumenEjecutivoPL
        abierto={modalResumenWa}
        alCerrar={() => setModalResumenWa(false)}
        mesInicial={fechaInicio.slice(0, 7)}
        sucursalInicial={sucursalFiltro}
      />
    </div>
  );
}
