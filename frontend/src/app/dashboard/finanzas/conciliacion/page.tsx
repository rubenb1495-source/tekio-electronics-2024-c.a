"use client";

import React, { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, FileDown, FileSpreadsheet } from "lucide-react";
import PanelImportacionAdmin from "@/components/PanelImportacionAdmin";
import { ErrorApi, descargarPdfApi, formatearUsd, solicitarApi } from "@/servicios/api";
import type { InstrumentoFinanciero } from "@/tipos/finanzas";

interface PartidaConciliacion {
  id: number;
  lote_codigo: string;
  instrumento: string;
  fecha_movimiento: string;
  referencia: string;
  descripcion: string;
  monto_banco: number;
  tipo_movimiento: string;
  estado: "CONCILIADO" | "PENDIENTE_SISTEMA" | "EN_TRANSITO";
  pago_id: number | null;
}

interface PagoTransito {
  pago_id: number;
  fecha: string;
  referencia: string;
  tipo_movimiento: string;
  monto_moneda_origen: number;
  moneda: string;
  nota: string;
}

export default function PaginaConciliacionAvanzada() {
  const [instrumentos, setInstrumentos] = useState<InstrumentoFinanciero[]>([]);
  const [instrumentoId, setInstrumentoId] = useState("");
  const [partidas, setPartidas] = useState<PartidaConciliacion[]>([]);
  const [enTransito, setEnTransito] = useState<PagoTransito[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  useEffect(() => {
    solicitarApi<InstrumentoFinanciero[]>("/api/finanzas/instrumentos")
      .then((res) => {
        setInstrumentos(res);
        if (res.length > 0) setInstrumentoId(String(res[0].id));
      })
      .catch(() => {});
  }, []);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      const qs = instrumentoId ? `?instrumento_id=${instrumentoId}` : "";
      const res = await solicitarApi<{ partidas: PartidaConciliacion[]; en_transito: PagoTransito[] }>(
        `/api/finanzas/conciliacion/partidas${qs}`
      );
      setPartidas(res.partidas);
      setEnTransito(res.en_transito);
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "Error cargando conciliación.");
    }
  }, [instrumentoId]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const marcarConciliado = async (id: number) => {
    setExito(null);
    await solicitarApi(`/api/finanzas/conciliacion/partidas/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ estado: "CONCILIADO" }),
    });
    setExito("Partida conciliada manualmente.");
    await cargar();
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-black text-[#191818] flex items-center gap-2">
            <FileSpreadsheet className="w-6 h-6 text-[#E85A28]" />
            Conciliación Bancaria Avanzada
          </h2>
          <p className="text-sm text-neutral-500">
            Importa extractos bancarios (.xlsx/.csv), cruza automáticamente contra pagos y tesorería, y exporta PDF.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <select
            value={instrumentoId}
            onChange={(e) => setInstrumentoId(e.target.value)}
            className="px-3 py-2 rounded-xl border border-neutral-200 bg-white font-semibold"
          >
            <option value="">Todas las cuentas</option>
            {instrumentos.map((i) => (
              <option key={i.id} value={String(i.id)}>
                {i.nombre} ({i.moneda})
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() =>
              void descargarPdfApi(
                `/api/finanzas/conciliacion/pdf${instrumentoId ? `?instrumento_id=${instrumentoId}` : ""}`,
                "Reporte_Conciliacion_Bancaria.pdf"
              )
            }
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-[#E85A28] text-white font-bold cursor-pointer"
          >
            <FileDown className="w-3.5 h-3.5" /> Reporte PDF
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3.5 rounded-2xl bg-red-50 border border-red-200 text-xs text-red-700 font-semibold">
          <AlertCircle className="w-4 h-4 shrink-0" /> <span>{error}</span>
        </div>
      )}
      {exito && (
        <div className="flex items-center gap-2 p-3.5 rounded-2xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 font-semibold">
          <CheckCircle2 className="w-4 h-4 shrink-0" /> <span>{exito}</span>
        </div>
      )}

      <PanelImportacionAdmin
        flujoInicial="extractos_bancarios"
        instrumentoId={instrumentoId}
        alCompletar={() => void cargar()}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Partidas del Extracto Bancario */}
        <div className="bg-white/80 backdrop-blur-md border border-white/70 rounded-2xl p-5 shadow-xs space-y-3">
          <h3 className="text-sm font-black text-[#191818]">
            Partidas de Extracto Bancario ({partidas.length})
          </h3>
          <div className="overflow-x-auto max-h-96 overflow-y-auto">
            <table className="w-full text-xs text-left tabular-nums">
              <thead className="bg-neutral-50 border-b border-neutral-200 uppercase text-[10px] text-neutral-500">
                <tr>
                  <th className="px-3 py-2">Fecha / Ref.</th>
                  <th className="px-3 py-2 text-right">Monto</th>
                  <th className="px-3 py-2">Estado</th>
                  <th className="px-3 py-2 text-right">Acción</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {partidas.map((p) => (
                  <tr key={p.id}>
                    <td className="px-3 py-2">
                      <p className="font-mono font-bold">{p.referencia || "—"}</p>
                      <p className="text-[11px] text-neutral-500">{p.fecha_movimiento} · {p.descripcion}</p>
                    </td>
                    <td className="px-3 py-2 text-right font-bold">
                      {p.tipo_movimiento === "DEBITO" ? "-" : "+"}{p.monto_banco.toFixed(2)}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${p.estado === "CONCILIADO" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-800"}`}>
                        {p.estado}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      {p.estado !== "CONCILIADO" && (
                        <button type="button" onClick={() => void marcarConciliado(p.id)} className="px-2.5 py-1 rounded-lg bg-[#191818] text-white text-[11px] font-bold cursor-pointer">
                          Conciliar
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Partidas EN_TRANSITO en Sistema */}
        <div className="bg-white/80 backdrop-blur-md border border-white/70 rounded-2xl p-5 shadow-xs space-y-3">
          <h3 className="text-sm font-black text-[#191818]">
            En Tránsito en Sistema sin Cruzar ({enTransito.length})
          </h3>
          <div className="overflow-x-auto max-h-96 overflow-y-auto">
            <table className="w-full text-xs text-left tabular-nums">
              <thead className="bg-neutral-50 border-b border-neutral-200 uppercase text-[10px] text-neutral-500">
                <tr>
                  <th className="px-3 py-2">Fecha / Ref.</th>
                  <th className="px-3 py-2">Tipo</th>
                  <th className="px-3 py-2 text-right">Monto</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {enTransito.map((pg) => (
                  <tr key={pg.pago_id}>
                    <td className="px-3 py-2">
                      <p className="font-mono font-bold">{pg.referencia || `#${pg.pago_id}`}</p>
                      <p className="text-[11px] text-neutral-500">{pg.fecha} · {pg.nota}</p>
                    </td>
                    <td className="px-3 py-2 text-[11px] font-semibold">{pg.tipo_movimiento}</td>
                    <td className="px-3 py-2 text-right font-bold">{formatearUsd(pg.monto_moneda_origen)} {pg.moneda}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
