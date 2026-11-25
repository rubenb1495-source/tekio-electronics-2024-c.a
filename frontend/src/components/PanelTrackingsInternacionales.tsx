"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, CheckCircle2, PackageCheck, Plus } from "lucide-react";
import BuscadorTabla from "@/componentes/BuscadorTabla";
import { extraerMensajeError, solicitarApi } from "@/servicios/api";
import type { CompraResumen } from "@/tipos/logistica";

type EstadoTracking =
  | "EN_ORIGEN"
  | "EN_TRANSITO"
  | "EN_ADUANA"
  | "RECIBIDO_ALMACEN";

interface TrackingItem {
  id: number;
  compra_id: number;
  numero_compra: string;
  origen: string;
  proveedor: string;
  numero_tracking: string;
  courier: string;
  estado: EstadoTracking;
  peso_lb: number;
  fecha_estimada: string | null;
  notas: string;
  actualizado_en: string | null;
}

const ESTADOS_TRACKING: EstadoTracking[] = [
  "EN_ORIGEN",
  "EN_TRANSITO",
  "EN_ADUANA",
  "RECIBIDO_ALMACEN",
];

const BADGE_ESTADO: Record<EstadoTracking, string> = {
  EN_ORIGEN: "bg-neutral-100 text-neutral-700",
  EN_TRANSITO: "bg-blue-100 text-blue-800",
  EN_ADUANA: "bg-amber-100 text-amber-800",
  RECIBIDO_ALMACEN: "bg-emerald-100 text-emerald-800",
};

export default function PanelTrackingsInternacionales({
  compras,
}: {
  compras: CompraResumen[];
}) {
  const [trackings, setTrackings] = useState<TrackingItem[]>([]);
  const [busqueda, setBusqueda] = useState("");
  const [compraId, setCompraId] = useState("");
  const [numeroTracking, setNumeroTracking] = useState("");
  const [courier, setCourier] = useState("");
  const [pesoLb, setPesoLb] = useState("");
  const [fechaEstimada, setFechaEstimada] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  const cargarTrackings = useCallback(async () => {
    try {
      const lista = await solicitarApi<TrackingItem[]>("/api/logistica/trackings");
      setTrackings(lista);
    } catch (err) {
      setError(extraerMensajeError(err, "No se pudieron cargar los trackings."));
    }
  }, []);

  useEffect(() => {
    void cargarTrackings();
  }, [cargarTrackings]);

  const agregarTracking = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!compraId || !numeroTracking.trim()) return;
    setGuardando(true);
    setError(null);
    setExito(null);
    try {
      await solicitarApi(`/api/logistica/compras/${compraId}/trackings`, {
        method: "POST",
        body: JSON.stringify({
          numero_tracking: numeroTracking.trim().toUpperCase(),
          courier: courier.trim(),
          estado: "EN_ORIGEN",
          peso_lb: pesoLb ? Number(pesoLb) : 0,
          fecha_estimada: fechaEstimada || null,
        }),
      });
      setNumeroTracking("");
      setCourier("");
      setPesoLb("");
      setFechaEstimada("");
      setExito("Tracking asociado correctamente a la compra.");
      await cargarTrackings();
    } catch (err) {
      setError(extraerMensajeError(err, "No se pudo registrar el tracking."));
    } finally {
      setGuardando(false);
    }
  };

  const cambiarEstado = async (trk: TrackingItem, nuevoEstado: EstadoTracking) => {
    setError(null);
    setExito(null);
    try {
      const act = await solicitarApi<TrackingItem>(
        `/api/logistica/trackings/${trk.id}/estado`,
        {
          method: "PATCH",
          body: JSON.stringify({ estado: nuevoEstado }),
        }
      );
      setTrackings((prev) => prev.map((t) => (t.id === trk.id ? act : t)));
      setExito(`Tracking ${trk.numero_tracking} actualizado a ${nuevoEstado}.`);
    } catch (err) {
      setError(extraerMensajeError(err, "No se pudo actualizar el estado."));
    }
  };

  const filtrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return trackings;
    return trackings.filter((t) =>
      [t.numero_tracking, t.courier, t.numero_compra, t.proveedor, t.estado]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [trackings, busqueda]);

  return (
    <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-black text-[#191818] flex items-center gap-2">
            <PackageCheck className="w-4 h-4 text-[#E85A28]" />
            Seguimiento de Trackings Internacionales ({trackings.length})
          </h3>
          <p className="text-xs text-neutral-500">
            Asocia números de tracking / courier a tus compras y rastrea paquetes en origen, tránsito, aduana o almacén.
          </p>
        </div>
        <div className="w-full sm:w-72">
          <BuscadorTabla
            valor={busqueda}
            alCambiar={setBusqueda}
            placeholder="Buscar por tracking, courier o compra..."
          />
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}
      {exito && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-700">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{exito}</span>
        </div>
      )}

      <form
        onSubmit={agregarTracking}
        className="grid grid-cols-1 md:grid-cols-6 gap-2.5 bg-neutral-50/80 p-3 rounded-xl border border-neutral-200/70"
      >
        <select
          required
          value={compraId}
          onChange={(e) => setCompraId(e.target.value)}
          className="px-2.5 py-2 rounded-lg border border-neutral-300 bg-white text-xs"
        >
          <option value="">Compra...</option>
          {compras.map((c) => (
            <option key={c.id} value={c.id}>
              {c.numero_compra} · {c.origen}
            </option>
          ))}
        </select>
        <input
          type="text"
          required
          value={numeroTracking}
          onChange={(e) => setNumeroTracking(e.target.value)}
          placeholder="Nro. Tracking (ej. 1Z999...)"
          className="md:col-span-2 px-2.5 py-2 rounded-lg border border-neutral-300 bg-white text-xs font-mono uppercase"
        />
        <input
          type="text"
          value={courier}
          onChange={(e) => setCourier(e.target.value)}
          placeholder="Courier (UPS, FedEx...)"
          className="px-2.5 py-2 rounded-lg border border-neutral-300 bg-white text-xs"
        />
        <input
          type="number"
          step="0.1"
          min="0"
          value={pesoLb}
          onChange={(e) => setPesoLb(e.target.value)}
          placeholder="Peso (lb)"
          className="px-2.5 py-2 rounded-lg border border-neutral-300 bg-white text-xs tabular-nums"
        />
        <button
          type="submit"
          disabled={guardando}
          className="inline-flex items-center justify-center gap-1 px-3 py-2 rounded-lg bg-[#E85A28] hover:bg-[#C9461A] text-white text-xs font-bold cursor-pointer disabled:opacity-50"
        >
          <Plus className="w-3.5 h-3.5" />
          {guardando ? "..." : "Asociar"}
        </button>
      </form>

      {filtrados.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-neutral-50 text-neutral-500 uppercase">
              <tr>
                <th className="px-3 py-2.5">Tracking</th>
                <th className="px-3 py-2.5">Compra</th>
                <th className="px-3 py-2.5">Courier</th>
                <th className="px-3 py-2.5 text-right">Peso</th>
                <th className="px-3 py-2.5">Estado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 tabular-nums">
              {filtrados.map((t) => (
                <tr key={t.id} className="hover:bg-neutral-50/70">
                  <td className="px-3 py-2.5 font-mono font-black text-[#191818]">
                    {t.numero_tracking}
                  </td>
                  <td className="px-3 py-2.5">
                    <span className="font-bold">{t.numero_compra}</span>
                    <span className="text-neutral-500 ml-1">({t.proveedor})</span>
                  </td>
                  <td className="px-3 py-2.5">{t.courier || "—"}</td>
                  <td className="px-3 py-2.5 text-right">
                    {t.peso_lb > 0 ? `${t.peso_lb} lb` : "—"}
                  </td>
                  <td className="px-3 py-2.5">
                    <select
                      value={t.estado}
                      onChange={(e) =>
                        void cambiarEstado(t, e.target.value as EstadoTracking)
                      }
                      className={`px-2 py-1 rounded-lg text-[11px] font-bold border border-neutral-200 cursor-pointer ${BADGE_ESTADO[t.estado]}`}
                    >
                      {ESTADOS_TRACKING.map((est) => (
                        <option key={est} value={est}>
                          {est}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
