"use client";

import React, { useEffect, useState } from "react";
import { Check, Copy, FileDown, Loader2 } from "lucide-react";
import {
  copiarTextoPortapapeles,
  formatearWhatsAppListaPrecios,
} from "@/lib/whatsapp";
import {
  descargarPdfApi,
  solicitarApi,
} from "@/servicios/api";
import type { Sucursal } from "@/tipos/dominio";
import type { ListaPreciosRespuesta } from "@/tipos/operaciones";

interface BarraListaPreciosProps {
  sucursalInicialId?: string;
  categoria?: string;
}

export default function BarraListaPrecios({
  sucursalInicialId = "",
  categoria = "",
}: BarraListaPreciosProps) {
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [sucursalId, setSucursalId] = useState(sucursalInicialId);
  const [descargandoPdf, setDescargandoPdf] = useState(false);
  const [copiandoWa, setCopiandoWa] = useState(false);
  const [copiadoOk, setCopiadoOk] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    solicitarApi<Sucursal[]>("/api/sucursales")
      .then((res) => setSucursales(res))
      .catch(() => {});
  }, []);

  useEffect(() => {
    setSucursalId(sucursalInicialId);
  }, [sucursalInicialId]);

  const construirQuery = () => {
    const params = new URLSearchParams();
    if (sucursalId) params.set("sucursal_id", sucursalId);
    if (categoria.trim()) params.set("categoria", categoria.trim());
    return params.toString() ? `?${params.toString()}` : "";
  };

  const descargarPdf = async () => {
    setDescargandoPdf(true);
    setErrorMsg(null);
    try {
      await descargarPdfApi(
        `/api/catalogo/lista-precios-pdf${construirQuery()}`,
        "Lista_Precios_Tekio.pdf"
      );
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Error al descargar el PDF."
      );
    } finally {
      setDescargandoPdf(false);
    }
  };

  const copiarWhatsApp = async () => {
    setCopiandoWa(true);
    setErrorMsg(null);
    try {
      const lista = await solicitarApi<ListaPreciosRespuesta>(
        `/api/catalogo/lista-precios${construirQuery()}`
      );
      const texto = formatearWhatsAppListaPrecios(lista);
      const ok = await copiarTextoPortapapeles(texto);
      if (ok) {
        setCopiadoOk(true);
        setTimeout(() => setCopiadoOk(false), 2500);
      }
    } catch {
      setErrorMsg("No se pudo obtener la lista de precios para WhatsApp.");
    } finally {
      setCopiandoWa(false);
    }
  };

  return (
    <div className="bg-white/75 backdrop-blur-md border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl px-4 py-3 flex flex-wrap items-center justify-between gap-3">
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-wide text-tekio-naranja">
          Lista de Precios · Equipos Disponibles (LISTO)
        </p>
        <p className="text-xs text-neutral-500">
          Exporta solo modelos disponibles con precio Divisas y Bs/Regular (sin costos internos).
        </p>
        {errorMsg && (
          <p className="text-xs text-red-600 mt-1 font-medium">{errorMsg}</p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={sucursalId}
          onChange={(e) => setSucursalId(e.target.value)}
          className="rounded-xl border border-neutral-200 bg-white/90 px-3 py-2 text-xs font-medium text-tekio-carbon focus:outline-none focus:ring-2 focus:ring-tekio-naranja/40"
          aria-label="Sucursal para lista de precios"
        >
          <option value="">Todas las sucursales</option>
          {sucursales.map((s) => (
            <option key={s.id} value={String(s.id)}>
              {s.nombre}
            </option>
          ))}
        </select>

        <button
          type="button"
          onClick={descargarPdf}
          disabled={descargandoPdf}
          className="inline-flex items-center gap-1.5 rounded-xl bg-tekio-naranja hover:bg-tekio-naranja-hover text-white px-3.5 py-2 text-xs font-semibold transition-colors disabled:opacity-60"
        >
          {descargandoPdf ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <FileDown className="w-3.5 h-3.5" />
          )}
          Descargar Lista de Precios
        </button>

        <button
          type="button"
          onClick={copiarWhatsApp}
          disabled={copiandoWa}
          className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 px-3.5 py-2 text-xs font-semibold transition-colors disabled:opacity-60"
        >
          {copiadoOk ? (
            <Check className="w-3.5 h-3.5 text-emerald-600" />
          ) : copiandoWa ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Copy className="w-3.5 h-3.5" />
          )}
          {copiadoOk ? "Lista copiada" : "Copiar Lista WhatsApp"}
        </button>
      </div>
    </div>
  );
}
