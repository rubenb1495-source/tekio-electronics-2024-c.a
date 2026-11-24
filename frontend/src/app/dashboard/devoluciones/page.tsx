"use client";

import React, { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Plus, RotateCcw } from "lucide-react";
import { ErrorApi, formatearUsd, solicitarApi } from "@/servicios/api";
import type { NotaCreditoResumen, VentaResumen } from "@/tipos/finanzas";

export default function PaginaDevoluciones() {
  const [notas, setNotas] = useState<NotaCreditoResumen[]>([]);
  const [ventas, setVentas] = useState<VentaResumen[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  const [modalNueva, setModalNueva] = useState(false);
  const [ventaId, setVentaId] = useState("");
  const [equipoId, setEquipoId] = useState("");
  const [estadoReingreso, setEstadoReingreso] = useState<
    "POR_PREPARAR" | "GARANTIA" | "LISTO"
  >("POR_PREPARAR");
  const [motivo, setMotivo] = useState("");
  const [guardando, setGuardando] = useState(false);

  const cargarDatos = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [respNc, respVtas] = await Promise.all([
        solicitarApi<NotaCreditoResumen[]>("/api/devoluciones"),
        solicitarApi<VentaResumen[]>("/api/ventas"),
      ]);
      setNotas(respNc);
      setVentas(respVtas.filter((v) => v.estado !== "ANULADA"));
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudieron cargar las devoluciones."
      );
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void cargarDatos();
  }, [cargarDatos]);

  const ventaSel = ventas.find((v) => String(v.id) === ventaId);

  const manejarCrearNC = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setExito(null);
    setGuardando(true);
    try {
      await solicitarApi("/api/devoluciones", {
        method: "POST",
        body: JSON.stringify({
          venta_original_id: Number(ventaId),
          equipo_id: equipoId ? Number(equipoId) : null,
          cantidad: 1,
          motivo: motivo.trim(),
          estado_reingreso: estadoReingreso,
        }),
      });
      setModalNueva(false);
      setMotivo("");
      setEquipoId("");
      setExito(
        "Nota de Crédito creada sin modificar la venta original. Serial reingresado."
      );
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo registrar la devolución."
      );
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900">
            Devoluciones y Cambios (Notas de Crédito)
          </h2>
          <p className="text-sm text-slate-500">
            Reingresa seriales a POR_PREPARAR, GARANTIA o LISTO preservando el
            histórico de la venta original.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setModalNueva(true)}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold cursor-pointer"
        >
          <Plus className="w-4 h-4" />
          Nueva Nota de Crédito
        </button>
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
            {[1, 2].map((i) => (
              <div key={i} className="h-12 rounded-xl bg-slate-100 animate-pulse" />
            ))}
          </div>
        ) : notas.length === 0 ? (
          <div className="p-10 text-center space-y-2">
            <RotateCcw className="w-10 h-10 text-slate-300 mx-auto" />
            <p className="text-sm font-semibold text-slate-600">
              No hay Notas de Crédito registradas.
            </p>
          </div>
        ) : (
          <table className="w-full text-sm text-left">
            <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">NC</th>
                <th className="px-4 py-3">Venta Original</th>
                <th className="px-4 py-3">Serial / SKU</th>
                <th className="px-4 py-3 text-right">Monto Promo</th>
                <th className="px-4 py-3">Reingreso</th>
                <th className="px-4 py-3">Motivo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {notas.map((n) => (
                <tr key={n.id}>
                  <td className="px-4 py-3 font-mono font-bold">
                    {n.numero_nc}
                  </td>
                  <td className="px-4 py-3 font-mono">{n.numero_venta}</td>
                  <td className="px-4 py-3 font-mono">
                    {n.serial || n.sku || "—"}
                  </td>
                  <td className="px-4 py-3 text-right font-bold text-[#C9461A]">
                    {formatearUsd(n.monto_reconocido_promo_usd)}
                  </td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded-full bg-slate-100 text-xs font-bold">
                      {n.estado_reingreso}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-600">
                    {n.motivo}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {modalNueva && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4">
            <h3 className="text-lg font-black text-slate-900">
              Registrar Nota de Crédito
            </h3>
            <form onSubmit={manejarCrearNC} className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Venta original
                </label>
                <select
                  required
                  value={ventaId}
                  onChange={(e) => {
                    setVentaId(e.target.value);
                    setEquipoId("");
                  }}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                >
                  <option value="">Seleccionar venta...</option>
                  {ventas.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.numero_venta} ({v.fecha} · {formatearUsd(v.total_promo_usd)})
                    </option>
                  ))}
                </select>
              </div>
              {ventaSel && (
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Serial devuelto
                  </label>
                  <select
                    value={equipoId}
                    onChange={(e) => setEquipoId(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                  >
                    <option value="">Seleccionar equipo...</option>
                    {ventaSel.detalles
                      .filter((d) => d.equipo_id)
                      .map((d) => (
                        <option key={d.id} value={d.equipo_id ?? ""}>
                          {d.serial} — {d.descripcion}
                        </option>
                      ))}
                  </select>
                </div>
              )}
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Estado de reingreso
                </label>
                <select
                  value={estadoReingreso}
                  onChange={(e) =>
                    setEstadoReingreso(
                      e.target.value as "POR_PREPARAR" | "GARANTIA" | "LISTO"
                    )
                  }
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                >
                  <option value="POR_PREPARAR">POR_PREPARAR</option>
                  <option value="GARANTIA">GARANTIA</option>
                  <option value="LISTO">LISTO</option>
                </select>
              </div>
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
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setModalNueva(false)}
                  className="px-4 py-2 rounded-xl border border-slate-300 text-sm font-semibold cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={guardando}
                  className="px-4 py-2 rounded-xl bg-[#E85A28] text-white text-sm font-bold cursor-pointer"
                >
                  Emitir Nota de Crédito
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
