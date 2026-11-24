"use client";

import React, { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Plane, Plus } from "lucide-react";
import { ErrorApi, formatearUsd, solicitarApi } from "@/servicios/api";
import type {
  CompraResumen,
  ComprasPaginadas,
  GuiaResumen,
  ModalidadGuia,
} from "@/tipos/logistica";

export default function PaginaGuias() {
  const [guias, setGuias] = useState<GuiaResumen[]>([]);
  const [comprasPendientes, setComprasPendientes] = useState<CompraResumen[]>(
    []
  );
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  const [modalCrear, setModalCrear] = useState(false);
  const [numeroGuia, setNumeroGuia] = useState("");
  const [casillero, setCasillero] = useState("");
  const [modalidad, setModalidad] = useState<ModalidadGuia>("AEREO");
  const [fleteUsd, setFleteUsd] = useState("");
  const [otrosGastosUsd, setOtrosGastosUsd] = useState("0");
  const [comprasSeleccionadas, setComprasSeleccionadas] = useState<number[]>(
    []
  );
  const [guardando, setGuardando] = useState(false);

  const cargarDatos = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [respGuias, respCompras] = await Promise.all([
        solicitarApi<GuiaResumen[]>("/api/logistica/guias"),
        solicitarApi<ComprasPaginadas>(
          "/api/logistica/compras?origen=IMPORTACION"
        ),
      ]);
      setGuias(respGuias);
      setComprasPendientes(respCompras.elementos);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudieron cargar las guías."
      );
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void cargarDatos();
  }, [cargarDatos]);

  const alternarCompra = (id: number) => {
    setComprasSeleccionadas((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const manejarCrearGuia = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setExito(null);
    if (comprasSeleccionadas.length === 0) {
      setError("Selecciona al menos una compra asociada a esta guía.");
      return;
    }

    setGuardando(true);
    try {
      await solicitarApi("/api/logistica/guias", {
        method: "POST",
        body: JSON.stringify({
          numero_guia: numeroGuia.trim(),
          casillero: casillero.trim(),
          modalidad,
          flete_usd: Number(fleteUsd || 0),
          otros_gastos_usd: Number(otrosGastosUsd || 0),
          compras_ids: comprasSeleccionadas,
        }),
      });
      setModalCrear(false);
      setNumeroGuia("");
      setCasillero("");
      setFleteUsd("");
      setOtrosGastosUsd("0");
      setComprasSeleccionadas([]);
      setExito("Guía de importación registrada correctamente.");
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "No se pudo crear la guía."
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
            Guías de Casillero (Miami → Venezuela)
          </h2>
          <p className="text-sm text-slate-500">
            Control de envíos consolidados y flete total para prorrateo
            automático por valor en recepción.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setModalCrear(true)}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold cursor-pointer"
        >
          <Plus className="w-4 h-4" />
          Nueva guía
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
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-12 rounded-xl bg-slate-100 animate-pulse"
              />
            ))}
          </div>
        ) : guias.length === 0 ? (
          <div className="p-10 text-center space-y-2">
            <Plane className="w-10 h-10 text-slate-300 mx-auto" />
            <p className="text-sm font-semibold text-slate-600">
              No hay guías de importación registradas.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Guía</th>
                  <th className="px-4 py-3">Casillero / Modalidad</th>
                  <th className="px-4 py-3">Compras</th>
                  <th className="px-4 py-3 text-right">Flete + Otros</th>
                  <th className="px-4 py-3">Estado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {guias.map((g) => (
                  <tr key={g.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-mono font-bold text-slate-900">
                      {g.numero_guia}
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-semibold">
                        {g.casillero || "Sin casillero"}
                      </p>
                      <p className="text-xs text-slate-500">{g.modalidad}</p>
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {g.compras.map((c) => c.numero_compra).join(", ")}
                    </td>
                    <td className="px-4 py-3 text-right font-bold text-[#C9461A]">
                      {formatearUsd(g.costo_total_guia_usd)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                          g.estado === "RECIBIDA"
                            ? "bg-emerald-50 text-emerald-700"
                            : "bg-amber-50 text-amber-800"
                        }`}
                      >
                        {g.estado}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modalCrear && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl space-y-4">
            <h3 className="text-lg font-black text-slate-900">
              Crear guía de importación
            </h3>
            <form onSubmit={manejarCrearGuia} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Número de guía
                  </label>
                  <input
                    type="text"
                    required
                    value={numeroGuia}
                    onChange={(e) => setNumeroGuia(e.target.value)}
                    placeholder="Ej: MIA-2026-01"
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Modalidad
                  </label>
                  <select
                    value={modalidad}
                    onChange={(e) =>
                      setModalidad(e.target.value as ModalidadGuia)
                    }
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                  >
                    <option value="AEREO">AEREO</option>
                    <option value="MARITIMO">MARITIMO</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Casillero / Courier
                </label>
                <input
                  type="text"
                  value={casillero}
                  onChange={(e) => setCasillero(e.target.value)}
                  placeholder="Ej: Liberty Express / Zoom Miami"
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Flete USD
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    required
                    value={fleteUsd}
                    onChange={(e) => setFleteUsd(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Otros gastos USD
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={otrosGastosUsd}
                    onChange={(e) => setOtrosGastosUsd(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Compras de importación incluidas
                </label>
                <div className="max-h-40 overflow-y-auto border border-slate-200 rounded-xl p-2 space-y-1.5">
                  {comprasPendientes.length === 0 ? (
                    <p className="text-xs text-slate-500 p-2">
                      No hay compras de importación registradas.
                    </p>
                  ) : (
                    comprasPendientes.map((c) => (
                      <label
                        key={c.id}
                        className="flex items-center gap-2 text-xs p-1.5 rounded-lg hover:bg-slate-50 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={comprasSeleccionadas.includes(c.id)}
                          onChange={() => alternarCompra(c.id)}
                        />
                        <span className="font-mono font-bold">
                          {c.numero_compra}
                        </span>
                        <span className="text-slate-500">
                          ({c.total_equipos} equipos ·{" "}
                          {formatearUsd(c.monto_mercancia_usd)})
                        </span>
                      </label>
                    ))
                  )}
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setModalCrear(false)}
                  className="px-4 py-2 rounded-xl border border-slate-300 text-sm font-semibold cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={guardando}
                  className="px-4 py-2 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold disabled:opacity-60 cursor-pointer"
                >
                  {guardando ? "Guardando..." : "Crear guía"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
