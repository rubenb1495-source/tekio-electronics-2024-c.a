"use client";

import React, { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Cpu } from "lucide-react";
import { usarSesion } from "@/contexto/SesionContexto";
import { ErrorApi, solicitarApi } from "@/servicios/api";
import type { EstadoRepuesto, RepuestoSolicitado } from "@/tipos/taller";

export default function PaginaRepuestosTaller() {
  const { usuario } = usarSesion();
  const puedeGestionarEstado =
    usuario?.rol === "DIRECCION" ||
    usuario?.rol === "ADMINISTRACION" ||
    usuario?.rol === "LOGISTICA";

  const [repuestos, setRepuestos] = useState<RepuestoSolicitado[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  const cargarRepuestos = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const lista = await solicitarApi<RepuestoSolicitado[]>(
        "/api/taller/repuestos-solicitados"
      );
      setRepuestos(lista);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudieron cargar los repuestos solicitados."
      );
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void cargarRepuestos();
  }, [cargarRepuestos]);

  const cambiarEstado = async (
    id: number,
    estado: Exclude<EstadoRepuesto, "PENDIENTE">
  ) => {
    setError(null);
    setExito(null);
    try {
      await solicitarApi(`/api/taller/repuestos-solicitados/${id}/estado`, {
        method: "PATCH",
        body: JSON.stringify({ estado }),
      });
      setExito(
        estado === "RECIBIDO"
          ? "Repuesto marcado como RECIBIDO. Se activó la alerta en la cola del técnico."
          : `Estado actualizado a ${estado}.`
      );
      await cargarRepuestos();
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "No se pudo actualizar estado."
      );
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-black text-slate-900">
          Repuestos Solicitados (Taller ↔ Logística)
        </h2>
        <p className="text-sm text-slate-500">
          Cuando Logística marca un repuesto como RECIBIDO, se notifica
          automáticamente en la cola de preparaciones del técnico.
        </p>
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
        ) : repuestos.length === 0 ? (
          <div className="p-10 text-center space-y-2">
            <Cpu className="w-10 h-10 text-slate-300 mx-auto" />
            <p className="text-sm font-semibold text-slate-600">
              No hay repuestos solicitados actualmente.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Origen / Ref</th>
                  <th className="px-4 py-3">Repuesto</th>
                  <th className="px-4 py-3 text-right">Cant.</th>
                  <th className="px-4 py-3">Solicitado por</th>
                  <th className="px-4 py-3">Estado</th>
                  {puedeGestionarEstado && (
                    <th className="px-4 py-3 text-right">Acción Logística</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {repuestos.map((r) => (
                  <tr key={r.id}>
                    <td className="px-4 py-3 text-xs">
                      <span className="font-bold">{r.origen}</span>
                      <p className="font-mono text-slate-500">
                        {r.serial || r.numero_caso || "—"}
                      </p>
                    </td>
                    <td className="px-4 py-3 font-semibold">
                      {r.descripcion_repuesto}
                    </td>
                    <td className="px-4 py-3 text-right font-bold">
                      {r.cantidad}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-600">
                      {r.solicitado_por}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                          r.estado === "RECIBIDO"
                            ? "bg-emerald-100 text-emerald-800"
                            : r.estado === "COMPRADO"
                            ? "bg-sky-100 text-sky-800"
                            : r.estado === "CANCELADO"
                            ? "bg-slate-200 text-slate-600"
                            : "bg-amber-100 text-amber-800"
                        }`}
                      >
                        {r.estado}
                      </span>
                    </td>
                    {puedeGestionarEstado && (
                      <td className="px-4 py-3 text-right space-x-1.5">
                        {r.estado === "PENDIENTE" && (
                          <button
                            type="button"
                            onClick={() => void cambiarEstado(r.id, "COMPRADO")}
                            className="px-2.5 py-1 rounded-lg bg-sky-600 text-white text-xs font-bold cursor-pointer"
                          >
                            Comprado
                          </button>
                        )}
                        {(r.estado === "PENDIENTE" ||
                          r.estado === "COMPRADO") && (
                          <button
                            type="button"
                            onClick={() => void cambiarEstado(r.id, "RECIBIDO")}
                            className="px-2.5 py-1 rounded-lg bg-emerald-600 text-white text-xs font-bold cursor-pointer"
                          >
                            Recibido
                          </button>
                        )}
                      </td>
                    )}
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
