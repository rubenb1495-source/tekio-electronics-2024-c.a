"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  Check,
  Copy,
  ExternalLink,
  FileDown,
  MessageCircle,
  Send,
  X,
} from "lucide-react";
import {
  type ResumenEjecutivoPL,
  construirUrlWhatsApp,
  copiarTextoPortapapeles,
  formatearResumenEjecutivoPL,
} from "@/lib/whatsapp";
import {
  ErrorApi,
  descargarPdfApi,
  fechaHoyCaracas,
  solicitarApi,
} from "@/servicios/api";
import type { Sucursal } from "@/tipos/dominio";

export default function ModalResumenEjecutivoPL({
  abierto,
  alCerrar,
  mesInicial,
  sucursalInicial = "",
}: {
  abierto: boolean;
  alCerrar: () => void;
  mesInicial?: string;
  sucursalInicial?: string;
}) {
  const hoy = fechaHoyCaracas();
  const [mes, setMes] = useState(mesInicial || hoy.slice(0, 7));
  const [sucursalId, setSucursalId] = useState(sucursalInicial);
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [incluirPosicion, setIncluirPosicion] = useState(true);
  const [datos, setDatos] = useState<ResumenEjecutivoPL | null>(null);
  const [mensaje, setMensaje] = useState("");
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiado, setCopiado] = useState(false);

  useEffect(() => {
    if (!abierto) return;
    solicitarApi<Sucursal[]>("/api/sucursales")
      .then((res) => setSucursales(res))
      .catch(() => {});
  }, [abierto]);

  const cargarResumen = useCallback(async () => {
    if (!abierto) return;
    setCargando(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ mes });
      if (sucursalId) qs.set("sucursal_id", sucursalId);
      const res = await solicitarApi<ResumenEjecutivoPL>(
        `/api/finanzas/estado-resultados/resumen-ejecutivo?${qs.toString()}`
      );
      setDatos(res);
      setMensaje(
        formatearResumenEjecutivoPL(res, {
          incluirPosicionFinanciera: incluirPosicion,
        })
      );
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo generar el Resumen Ejecutivo Mensual."
      );
    } finally {
      setCargando(false);
    }
  }, [abierto, mes, sucursalId, incluirPosicion]);

  useEffect(() => {
    void cargarResumen();
  }, [cargarResumen]);

  useEffect(() => {
    if (datos) {
      setMensaje(
        formatearResumenEjecutivoPL(datos, {
          incluirPosicionFinanciera: incluirPosicion,
        })
      );
    }
  }, [datos, incluirPosicion]);

  if (!abierto) return null;

  const copiar = async () => {
    await copiarTextoPortapapeles(mensaje);
    setCopiado(true);
    setTimeout(() => setCopiado(false), 2000);
  };

  const descargarPdf = () => {
    if (!datos) return;
    const qs = new URLSearchParams({
      fecha_inicio: datos.fecha_inicio,
      fecha_fin: datos.fecha_fin,
    });
    if (sucursalId) qs.set("sucursal_id", sucursalId);
    void descargarPdfApi(
      `/api/finanzas/estado-resultados/pdf?${qs.toString()}`,
      `Estado_Resultados_${datos.mes}.pdf`
    );
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/45 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white/95 backdrop-blur-xl border border-white/80 rounded-2xl max-w-2xl w-full shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Cabecera */}
        <div className="px-5 py-4 border-b border-neutral-100 bg-[#FDF0EB]/70 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-[#E85A28] text-white flex items-center justify-center">
              <MessageCircle className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-black text-[#191818]">
                Resumen Ejecutivo Mensual (P&L) para WhatsApp
              </h3>
              <p className="text-[11px] text-neutral-500">
                Confidencial · Uso exclusivo Dirección y Administración
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={alCerrar}
            className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-700 hover:bg-white/80 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Controles */}
        <div className="p-5 space-y-4 overflow-y-auto flex-1">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div>
              <label className="block font-bold uppercase text-[10px] text-neutral-500 mb-1">
                Mes (YYYY-MM)
              </label>
              <input
                type="month"
                value={mes}
                onChange={(e) => setMes(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-neutral-200 bg-white font-semibold"
              />
            </div>
            <div>
              <label className="block font-bold uppercase text-[10px] text-neutral-500 mb-1">
                Sucursal / Alcance
              </label>
              <select
                value={sucursalId}
                onChange={(e) => setSucursalId(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-neutral-200 bg-white font-semibold"
              >
                <option value="">Consolidado (Todas)</option>
                {sucursales.map((s) => (
                  <option key={s.id} value={String(s.id)}>
                    {s.nombre}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 px-3 py-2 rounded-xl border border-neutral-200 bg-white/80 cursor-pointer w-full">
                <input
                  type="checkbox"
                  checked={incluirPosicion}
                  onChange={(e) => setIncluirPosicion(e.target.checked)}
                  className="rounded border-neutral-300 accent-[#E85A28]"
                />
                <span className="text-[11px] font-bold text-[#191818]">
                  Incluir Cajas, CxC y CxP
                </span>
              </label>
            </div>
          </div>

          {error && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700 font-semibold">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Vista previa editable */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-[10px] font-bold uppercase text-neutral-500">
                Vista previa editable del mensaje
              </label>
              {cargando && (
                <span className="text-[11px] text-[#E85A28] font-bold animate-pulse">
                  Calculando P&L...
                </span>
              )}
            </div>
            <textarea
              rows={13}
              value={mensaje}
              onChange={(e) => setMensaje(e.target.value)}
              className="w-full p-3.5 rounded-2xl border border-neutral-200 bg-[#F6F6F6]/70 font-mono text-xs text-[#191818] leading-relaxed focus:outline-none focus:border-[#E85A28]"
            />
          </div>

          {/* Botones directos por Director */}
          {datos && datos.directores.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[10px] font-bold uppercase text-neutral-500">
                Envío directo a Directores (1 clic)
              </p>
              <div className="flex flex-wrap gap-2">
                {datos.directores.map((dir) => (
                  <a
                    key={dir.id}
                    href={construirUrlWhatsApp(mensaje, dir.telefono)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold transition-colors"
                  >
                    <Send className="w-3 h-3" />
                    Enviar a {dir.nombre}
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Pie de acciones */}
        <div className="px-5 py-3.5 border-t border-neutral-100 bg-white/80 flex flex-wrap items-center justify-between gap-2">
          <button
            type="button"
            onClick={descargarPdf}
            disabled={!datos}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-neutral-300 bg-white hover:bg-neutral-50 text-xs font-bold text-[#191818] cursor-pointer disabled:opacity-40"
          >
            <FileDown className="w-3.5 h-3.5 text-[#E85A28]" />
            Descargar P&L PDF
          </button>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void copiar()}
              disabled={!mensaje}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-emerald-300 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 text-xs font-bold cursor-pointer disabled:opacity-40"
            >
              {copiado ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              {copiado ? "¡Copiado!" : "Copiar para WhatsApp"}
            </button>
            <a
              href={`https://wa.me/?text=${encodeURIComponent(mensaje)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] text-white text-xs font-bold"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Abrir en WhatsApp
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
