"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Copy,
  FileDown,
  Loader2,
  Receipt,
  Save,
} from "lucide-react";
import BuscadorTabla from "@/componentes/BuscadorTabla";
import {
  copiarTextoPortapapeles,
  formatearWhatsAppCierreCaja,
} from "@/lib/whatsapp";
import {
  ErrorApi,
  descargarPdfApi,
  fechaHoyCaracas,
  formatearBs,
  formatearUsd,
  solicitarApi,
} from "@/servicios/api";
import type { Sucursal } from "@/tipos/dominio";
import type { CierreCajaResumen, PreviewCierreCaja } from "@/tipos/finanzas";

export default function PaginaCierreCajaDiario() {
  const [fecha, setFecha] = useState(fechaHoyCaracas());
  const [sucursalId, setSucursalId] = useState("");
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);

  const [preview, setPreview] = useState<PreviewCierreCaja | null>(null);
  const [cierres, setCierres] = useState<CierreCajaResumen[]>([]);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cierreReciente, setCierreReciente] = useState<CierreCajaResumen | null>(
    null
  );

  // Formulario de conteo físico
  const [efectivoDeclarado, setEfectivoDeclarado] = useState("");
  const [observaciones, setObservaciones] = useState("");
  const [busqueda, setBusqueda] = useState("");
  const [copiadoId, setCopiadoId] = useState<number | null>(null);

  useEffect(() => {
    solicitarApi<Sucursal[]>("/api/sucursales")
      .then((res) => setSucursales(res))
      .catch(() => {});
  }, []);

  const cargarTodo = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const paramsPrev = new URLSearchParams();
      if (fecha) paramsPrev.set("fecha", fecha);
      if (sucursalId) paramsPrev.set("sucursal_id", sucursalId);

      const paramsHist = sucursalId ? `?sucursal_id=${sucursalId}` : "";
      const [respPrev, respHist] = await Promise.all([
        solicitarApi<PreviewCierreCaja>(
          `/api/finanzas/cierre-caja/preview?${paramsPrev.toString()}`
        ),
        solicitarApi<CierreCajaResumen[]>(
          `/api/finanzas/cierre-caja${paramsHist}`
        ),
      ]);
      setPreview(respPrev);
      setCierres(respHist);
      setEfectivoDeclarado(String(respPrev.efectivo_esperado_usd));
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo cargar el cierre de caja."
      );
    } finally {
      setCargando(false);
    }
  }, [fecha, sucursalId]);

  useEffect(() => {
    void cargarTodo();
  }, [cargarTodo]);

  const esperadoUsd = preview?.efectivo_esperado_usd ?? 0;
  const declaradoNum = Number(efectivoDeclarado || 0);
  const diferenciaEnVivo = Number.isFinite(declaradoNum)
    ? declaradoNum - esperadoUsd
    : 0;

  const guardarCierre = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setGuardando(true);
    try {
      const creado = await solicitarApi<CierreCajaResumen>(
        "/api/finanzas/cierre-caja",
        {
          method: "POST",
          body: JSON.stringify({
            fecha,
            sucursal_id: sucursalId ? Number(sucursalId) : null,
            efectivo_declarado_usd: Math.max(0, Number(efectivoDeclarado) || 0),
            observaciones: observaciones.trim(),
          }),
        }
      );
      setCierreReciente(creado);
      setObservaciones("");
      await cargarTodo();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo guardar el cierre de caja."
      );
    } finally {
      setGuardando(false);
    }
  };

  const copiarWa = async (cierre: CierreCajaResumen) => {
    const ok = await copiarTextoPortapapeles(formatearWhatsAppCierreCaja(cierre));
    if (ok) {
      setCopiadoId(cierre.id);
      setTimeout(() => setCopiadoId(null), 2400);
    }
  };

  const cierresFiltrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return cierres;
    return cierres.filter((c) =>
      [c.fecha, c.sucursal, c.usuario, c.observaciones]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [cierres, busqueda]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-[#191818] flex items-center gap-2">
            <Receipt className="w-6 h-6 text-[#E85A28]" />
            Cierre de Caja Diario
          </h2>
          <p className="text-sm text-neutral-500">
            Cuadre consolidado por sucursal de efectivo, transferencias, Pago Móvil, USDT, Cashea y egresos del día.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input
            type="date"
            value={fecha}
            onChange={(e) => setFecha(e.target.value)}
            className="px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm text-[#191818]"
          />
          <select
            value={sucursalId}
            onChange={(e) => setSucursalId(e.target.value)}
            className="px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm text-[#191818]"
          >
            <option value="">Todas las sucursales</option>
            {sucursales.map((s) => (
              <option key={s.id} value={String(s.id)}>
                {s.nombre}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2.5 p-4 rounded-2xl bg-red-50/90 border border-red-200 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {cierreReciente && (
        <div className="bg-white/85 backdrop-blur-md border-2 border-[#E85A28]/40 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
            <div className="text-sm">
              <p className="font-black text-[#191818]">
                Cierre #{cierreReciente.id} guardado ({cierreReciente.fecha} ·{" "}
                {cierreReciente.sucursal})
              </p>
              <p className="text-xs text-neutral-600">
                Efectivo declarado:{" "}
                <strong className="tabular-nums">
                  {formatearUsd(cierreReciente.efectivo_declarado_usd)}
                </strong>{" "}
                · Diferencia:{" "}
                <strong className="tabular-nums">
                  {formatearUsd(cierreReciente.diferencia_usd)}
                </strong>
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() =>
                void descargarPdfApi(
                  `/api/finanzas/cierre-caja/${cierreReciente.id}/pdf`,
                  `Cierre_Caja_${cierreReciente.fecha}.pdf`
                )
              }
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] text-white text-xs font-bold cursor-pointer"
            >
              <FileDown className="w-3.5 h-3.5" />
              Descargar PDF
            </button>
            <button
              type="button"
              onClick={() => void copiarWa(cierreReciente)}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold cursor-pointer"
            >
              {copiadoId === cierreReciente.id ? (
                <Check className="w-3.5 h-3.5" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
              {copiadoId === cierreReciente.id
                ? "¡Copiado!"
                : "Copiar Cierre para WhatsApp"}
            </button>
          </div>
        </div>
      )}

      {/* KPIs del día */}
      {preview && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <div className="bg-white/75 backdrop-blur-md p-4 rounded-2xl border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border-t-2 border-t-[#191818]">
            <p className="text-[11px] font-bold uppercase text-neutral-500">
              Ventas del Día ({preview.cantidad_ventas})
            </p>
            <p className="text-xl font-black text-[#191818] mt-1 tabular-nums">
              {formatearUsd(preview.total_ventas_usd)}
            </p>
            <p className="text-[11px] text-neutral-400">
              Anulaciones / Dev.: {preview.cantidad_anulaciones}
            </p>
          </div>

          <div className="bg-white/75 backdrop-blur-md p-4 rounded-2xl border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border-t-2 border-t-emerald-600">
            <p className="text-[11px] font-bold uppercase text-neutral-500">
              Ingresos Cobrados
            </p>
            <p className="text-xl font-black text-emerald-700 mt-1 tabular-nums">
              {formatearUsd(preview.total_ingresos_usd)}
            </p>
            <p className="text-[11px] text-neutral-500 tabular-nums">
              {formatearBs(preview.total_ingresos_bs)}
            </p>
          </div>

          <div className="bg-white/75 backdrop-blur-md p-4 rounded-2xl border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border-t-2 border-t-purple-600">
            <p className="text-[11px] font-bold uppercase text-neutral-500">
              Cashea Financiado
            </p>
            <p className="text-xl font-black text-purple-700 mt-1 tabular-nums">
              {formatearUsd(preview.total_cashea_usd)}
            </p>
          </div>

          <div className="bg-white/75 backdrop-blur-md p-4 rounded-2xl border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border-t-2 border-t-red-500">
            <p className="text-[11px] font-bold uppercase text-neutral-500">
              Egresos del Día
            </p>
            <p className="text-xl font-black text-red-600 mt-1 tabular-nums">
              {formatearUsd(preview.total_egresos_usd)}
            </p>
            <p className="text-[11px] text-neutral-500 tabular-nums">
              {formatearBs(preview.total_egresos_bs)}
            </p>
          </div>

          <div className="bg-white/75 backdrop-blur-md p-4 rounded-2xl border border-[#E85A28]/30 bg-gradient-to-br from-[#FDF0EB]/90 to-white/80 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
            <p className="text-[11px] font-bold uppercase text-[#E85A28]">
              Efectivo Esperado USD
            </p>
            <p className="text-xl font-black text-[#191818] mt-1 tabular-nums">
              {formatearUsd(preview.efectivo_esperado_usd)}
            </p>
            <p className="text-[11px] text-neutral-500 tabular-nums">
              Saldo neto: {formatearUsd(preview.saldo_neto_esperado_usd)}
            </p>
          </div>
        </div>
      )}

      {/* Desglose por instrumento + Formulario de conteo físico */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        <div className="lg:col-span-7 bg-white/75 backdrop-blur-md border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl overflow-hidden">
          <div className="px-5 py-3.5 border-b border-neutral-200/80 font-bold text-sm text-[#191818]">
            Desglose por Instrumento / Banco ({fecha})
          </div>
          {cargando ? (
            <div className="p-8 text-center text-sm text-neutral-500">
              Calculando movimientos del día...
            </div>
          ) : !preview || preview.desglose_instrumentos.length === 0 ? (
            <div className="p-8 text-center text-sm text-neutral-500">
              No hay movimientos registrados para esta fecha y sucursal.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="bg-neutral-50/90 border-b border-neutral-200 text-xs uppercase text-neutral-500">
                  <tr>
                    <th className="px-4 py-2.5">Instrumento</th>
                    <th className="px-4 py-2.5 text-center">Mon.</th>
                    <th className="px-4 py-2.5 text-right">Ingresos</th>
                    <th className="px-4 py-2.5 text-right">Egresos</th>
                    <th className="px-4 py-2.5 text-right">Neto USD</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-100">
                  {preview.desglose_instrumentos.map((d) => (
                    <tr key={d.instrumento_id} className="hover:bg-white/60">
                      <td className="px-4 py-2.5 font-semibold text-[#191818]">
                        {d.instrumento}
                        <span className="block text-[11px] font-normal text-neutral-400">
                          {d.cantidad_movimientos} mov.
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-center text-xs font-bold text-neutral-600">
                        {d.moneda}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-emerald-700 font-semibold">
                        {d.moneda === "BS"
                          ? formatearBs(d.ingresos_origen)
                          : formatearUsd(d.ingresos_origen)}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-red-600 font-semibold">
                        {d.moneda === "BS"
                          ? formatearBs(d.egresos_origen)
                          : formatearUsd(d.egresos_origen)}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums font-black text-[#191818]">
                        {formatearUsd(d.neto_usd)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Formulario de conteo físico */}
        <form
          onSubmit={guardarCierre}
          className="lg:col-span-5 bg-white/75 backdrop-blur-md border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl p-5 space-y-4"
        >
          <h3 className="text-base font-black text-[#191818]">
            Arqueo de Efectivo Físico
          </h3>

          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Efectivo físico contado / declarado (USD) *
            </label>
            <input
              type="number"
              step="0.01"
              min={0}
              required
              value={efectivoDeclarado}
              onChange={(e) => setEfectivoDeclarado(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl border border-neutral-300 bg-white text-base font-black text-[#191818] tabular-nums"
            />
          </div>

          <div
            className={`rounded-xl p-3 border text-xs font-bold flex items-center justify-between ${
              Math.abs(diferenciaEnVivo) < 0.01
                ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                : diferenciaEnVivo > 0
                ? "bg-blue-50 border-blue-200 text-blue-800"
                : "bg-red-50 border-red-200 text-red-700"
            }`}
          >
            <span>
              {Math.abs(diferenciaEnVivo) < 0.01
                ? "✅ Caja cuadrada"
                : diferenciaEnVivo > 0
                ? "Sobrante detectado"
                : "Faltante detectado"}
            </span>
            <span className="tabular-nums text-sm">
              {diferenciaEnVivo >= 0 ? "+" : ""}
              {formatearUsd(diferenciaEnVivo)}
            </span>
          </div>

          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Observaciones del cierre
            </label>
            <textarea
              rows={3}
              value={observaciones}
              onChange={(e) => setObservaciones(e.target.value)}
              placeholder="Ej. Todo cuadrado, billetes en sobre sellado..."
              className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
            />
          </div>

          <button
            type="submit"
            disabled={guardando}
            className="w-full inline-flex items-center justify-center gap-2 py-3 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] disabled:opacity-60 text-white text-sm font-black cursor-pointer transition-colors"
          >
            {guardando ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {guardando ? "Guardando cierre..." : "Guardar Cierre de Caja"}
          </button>
        </form>
      </div>

      {/* Tabla de Ventas por Asesor */}
      {preview && preview.desglose_asesores && preview.desglose_asesores.length > 0 && (
        <div className="bg-white/75 backdrop-blur-md border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl overflow-hidden">
          <div className="px-5 py-3.5 border-b border-neutral-200/80 font-bold text-sm text-[#191818]">
            Ventas por Asesor ({fecha})
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-neutral-50/90 border-b border-neutral-200 text-xs uppercase text-neutral-500">
                <tr>
                  <th className="px-4 py-2.5">Asesor</th>
                  <th className="px-4 py-2.5 text-center">Cant. Ventas</th>
                  <th className="px-4 py-2.5 text-right">Total Promo USD</th>
                  <th className="px-4 py-2.5 text-right">Total Regular USD</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {preview.desglose_asesores.map((a, idx) => (
                  <tr
                    key={`${a.asesor_id ?? "tienda"}-${idx}`}
                    className="hover:bg-white/60"
                  >
                    <td className="px-4 py-2.5 font-semibold text-[#191818]">
                      {a.asesor}
                    </td>
                    <td className="px-4 py-2.5 text-center tabular-nums font-bold">
                      {a.cantidad_ventas}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums font-black text-emerald-700">
                      {formatearUsd(a.total_promo_usd)}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-neutral-600">
                      {formatearUsd(a.total_regular_usd)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Historial de cierres */}
      <div className="bg-white/75 backdrop-blur-md border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-base font-bold text-[#191818]">
            Historial de Cierres de Caja ({cierresFiltrados.length})
          </h3>
          <div className="w-full sm:w-80">
            <BuscadorTabla
              valor={busqueda}
              alCambiar={setBusqueda}
              placeholder="Buscar por fecha, sucursal o responsable..."
            />
          </div>
        </div>

        {cierresFiltrados.length === 0 ? (
          <p className="text-sm text-neutral-500 text-center py-6">
            Aún no hay cierres de caja guardados.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-neutral-50/90 border-b border-neutral-200 text-xs uppercase text-neutral-500">
                <tr>
                  <th className="px-4 py-2.5">Fecha / Sede</th>
                  <th className="px-4 py-2.5">Responsable</th>
                  <th className="px-4 py-2.5 text-right">Ingresos USD</th>
                  <th className="px-4 py-2.5 text-right">Egresos USD</th>
                  <th className="px-4 py-2.5 text-right">Efectivo Decl.</th>
                  <th className="px-4 py-2.5 text-right">Diferencia</th>
                  <th className="px-4 py-2.5 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {cierresFiltrados.map((c) => (
                  <tr key={c.id} className="hover:bg-white/60">
                    <td className="px-4 py-3">
                      <p className="font-bold text-[#191818]">{c.fecha}</p>
                      <p className="text-xs text-neutral-500">{c.sucursal}</p>
                    </td>
                    <td className="px-4 py-3 text-xs font-semibold text-[#191818]">
                      {c.usuario}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums font-semibold text-emerald-700">
                      {formatearUsd(c.total_ingresos_usd)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums font-semibold text-red-600">
                      {formatearUsd(c.total_egresos_usd)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums font-bold">
                      {formatearUsd(c.efectivo_declarado_usd)}
                    </td>
                    <td
                      className={`px-4 py-3 text-right tabular-nums font-black ${
                        c.diferencia_usd === 0
                          ? "text-emerald-700"
                          : c.diferencia_usd > 0
                          ? "text-blue-700"
                          : "text-red-600"
                      }`}
                    >
                      {c.diferencia_usd >= 0 ? "+" : ""}
                      {formatearUsd(c.diferencia_usd)}
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap space-x-1.5">
                      <button
                        type="button"
                        onClick={() =>
                          void descargarPdfApi(
                            `/api/finanzas/cierre-caja/${c.id}/pdf`,
                            `Cierre_Caja_${c.fecha}.pdf`
                          )
                        }
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-neutral-200 bg-white hover:bg-neutral-50 text-xs font-bold text-[#191818] cursor-pointer"
                      >
                        <FileDown className="w-3.5 h-3.5 text-[#E85A28]" />
                        PDF
                      </button>
                      <button
                        type="button"
                        onClick={() => void copiarWa(c)}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 text-xs font-bold cursor-pointer"
                      >
                        {copiadoId === c.id ? (
                          <Check className="w-3.5 h-3.5" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                        WA
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
