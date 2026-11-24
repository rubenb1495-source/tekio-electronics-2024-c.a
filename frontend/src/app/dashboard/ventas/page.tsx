"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  Ban,
  CheckCircle2,
  Copy,
  FileDown,
  Plus,
  Receipt,
} from "lucide-react";
import {
  ErrorApi,
  descargarPdfApi,
  formatearUsd,
  solicitarApi,
} from "@/servicios/api";
import type { VentaResumen } from "@/tipos/finanzas";

export default function PaginaHistorialVentas() {
  const [ventas, setVentas] = useState<VentaResumen[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  const [ventaAnular, setVentaAnular] = useState<VentaResumen | null>(null);
  const [motivo, setMotivo] = useState("");
  const [procesando, setProcesando] = useState(false);

  const cargarVentas = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const lista = await solicitarApi<VentaResumen[]>("/api/ventas");
      setVentas(lista);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo cargar el historial de ventas."
      );
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void cargarVentas();
  }, [cargarVentas]);

  const manejarAnular = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!ventaAnular) return;
    setError(null);
    setExito(null);
    setProcesando(true);
    try {
      await solicitarApi(`/api/ventas/${ventaAnular.id}/anular`, {
        method: "POST",
        body: JSON.stringify({ motivo: motivo.trim() }),
      });
      setVentaAnular(null);
      setMotivo("");
      setExito("Venta anulada correctamente. Seriales y stock revertidos.");
      await cargarVentas();
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "No se pudo anular la venta."
      );
    } finally {
      setProcesando(false);
    }
  };

  const copiarWhatsApp = (v: VentaResumen) => {
    const txt = `*TEKIO · ${v.numero_venta}* (${v.fecha})\nSucursal: ${v.sucursal}\nTotal Promo: ${formatearUsd(v.total_promo_usd)} | Estado: ${v.estado}`;
    void navigator.clipboard?.writeText(txt);
    setExito(`Reporte de ${v.numero_venta} copiado para WhatsApp.`);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900">
            Historial de Ventas
          </h2>
          <p className="text-sm text-slate-500">
            Descarga Notas de Entrega en PDF, copia reportes WhatsApp o anula
            con motivo obligatorio.
          </p>
        </div>

        <Link
          href="/dashboard/ventas/nueva"
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold"
        >
          <Plus className="w-4 h-4" />
          Nueva venta POS
        </Link>
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

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        {cargando ? (
          <div className="p-6 space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 rounded-xl bg-slate-100 animate-pulse" />
            ))}
          </div>
        ) : ventas.length === 0 ? (
          <div className="p-10 text-center space-y-2">
            <Receipt className="w-10 h-10 text-slate-300 mx-auto" />
            <p className="text-sm font-semibold text-slate-600">
              No hay ventas registradas todavía.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Nota</th>
                  <th className="px-4 py-3">Fecha / Sucursal</th>
                  <th className="px-4 py-3">Asesor</th>
                  <th className="px-4 py-3 text-right">Promo USD</th>
                  <th className="px-4 py-3">Estado</th>
                  <th className="px-4 py-3 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {ventas.map((v) => (
                  <tr key={v.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-mono font-bold text-slate-900">
                      {v.numero_venta}
                    </td>
                    <td className="px-4 py-3 text-xs">
                      <p className="font-semibold">{v.fecha}</p>
                      <p className="text-slate-500">{v.sucursal}</p>
                    </td>
                    <td className="px-4 py-3 text-xs">{v.asesor}</td>
                    <td className="px-4 py-3 text-right font-bold text-emerald-700">
                      {formatearUsd(v.total_promo_usd)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                          v.estado === "CUADRADA"
                            ? "bg-emerald-50 text-emerald-700"
                            : v.estado === "ANULADA"
                            ? "bg-red-50 text-red-700"
                            : "bg-amber-50 text-amber-800"
                        }`}
                      >
                        {v.estado}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right space-x-1.5">
                      <button
                        type="button"
                        onClick={() =>
                          void descargarPdfApi(
                            `/api/ventas/${v.id}/nota-pdf`,
                            `Nota_${v.numero_venta}.pdf`
                          )
                        }
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[#E85A28] text-white text-xs font-bold cursor-pointer"
                      >
                        <FileDown className="w-3.5 h-3.5" />
                        PDF
                      </button>
                      <button
                        type="button"
                        onClick={() => copiarWhatsApp(v)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-300 text-xs font-bold cursor-pointer"
                      >
                        <Copy className="w-3.5 h-3.5" />
                        WA
                      </button>
                      {v.estado !== "ANULADA" && (
                        <button
                          type="button"
                          onClick={() => {
                            setMotivo("");
                            setVentaAnular(v);
                          }}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-red-300 text-red-700 text-xs font-bold cursor-pointer"
                        >
                          <Ban className="w-3.5 h-3.5" />
                          Anular
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {ventaAnular && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4">
            <h3 className="text-lg font-black text-slate-900">
              Anular venta {ventaAnular.numero_venta}
            </h3>
            <form onSubmit={manejarAnular} className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Motivo obligatorio
                </label>
                <input
                  type="text"
                  required
                  minLength={3}
                  value={motivo}
                  onChange={(e) => setMotivo(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setVentaAnular(null)}
                  className="px-4 py-2 rounded-xl border border-slate-300 text-sm font-semibold cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={procesando}
                  className="px-4 py-2 rounded-xl bg-red-600 text-white text-sm font-bold cursor-pointer"
                >
                  Confirmar anulación
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
