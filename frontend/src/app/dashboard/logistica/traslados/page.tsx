"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  Ban,
  CheckCircle2,
  Plus,
  Truck,
} from "lucide-react";
import { usarSesion } from "@/contexto/SesionContexto";
import {
  ErrorApi,
  puedeGestionarCatalogo,
  solicitarApi,
} from "@/servicios/api";
import type { Sucursal } from "@/tipos/dominio";
import type { EquipoInventario, TrasladoResumen } from "@/tipos/logistica";

export default function PaginaTraslados() {
  const { usuario } = usarSesion();
  const puedeEnviar = usuario ? puedeGestionarCatalogo(usuario.rol) : false;

  const [pestana, setPestana] = useState<"enviados" | "por_recibir">("enviados");
  const [traslados, setTraslados] = useState<TrasladoResumen[]>([]);
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [equiposDisponibles, setEquiposDisponibles] = useState<
    EquipoInventario[]
  >([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  // Modal nuevo traslado
  const [modalCrear, setModalCrear] = useState(false);
  const [origenId, setOrigenId] = useState("");
  const [destinoId, setDestinoId] = useState("");
  const [equiposSeleccionados, setEquiposSeleccionados] = useState<number[]>(
    []
  );
  const [nota, setNota] = useState("");
  const [procesando, setProcesando] = useState(false);

  // Modal anular traslado
  const [trasladoAnular, setTrasladoAnular] = useState<TrasladoResumen | null>(
    null
  );
  const [motivoAnulacion, setMotivoAnulacion] = useState("");

  const cargarDatos = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [respTrs, respSuc] = await Promise.all([
        solicitarApi<TrasladoResumen[]>("/api/logistica/traslados"),
        solicitarApi<Sucursal[]>("/api/sucursales"),
      ]);
      setTraslados(respTrs);
      setSucursales(respSuc);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudieron cargar los traslados."
      );
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void cargarDatos();
  }, [cargarDatos]);

  useEffect(() => {
    if (!origenId) {
      setEquiposDisponibles([]);
      return;
    }
    const cargarEquipos = async () => {
      try {
        const lista = await solicitarApi<EquipoInventario[]>(
          `/api/logistica/inventario/equipos?sucursal_id=${origenId}`
        );
        setEquiposDisponibles(
          lista.filter(
            (e) =>
              e.estado !== "EN_TRANSITO" &&
              e.estado !== "VENDIDO" &&
              e.estado !== "CEMENTERIO"
          )
        );
      } catch {
        setEquiposDisponibles([]);
      }
    };
    void cargarEquipos();
  }, [origenId]);

  const manejarCrearTraslado = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setExito(null);
    if (equiposSeleccionados.length === 0) {
      setError("Selecciona al menos un equipo para trasladar.");
      return;
    }

    setProcesando(true);
    try {
      await solicitarApi("/api/logistica/traslados", {
        method: "POST",
        body: JSON.stringify({
          origen_id: Number(origenId),
          destino_id: Number(destinoId),
          equipos_ids: equiposSeleccionados,
          nota: nota.trim(),
        }),
      });
      setModalCrear(false);
      setEquiposSeleccionados([]);
      setNota("");
      setExito("Traslado enviado en estado EN_TRANSITO.");
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "Error al crear traslado."
      );
    } finally {
      setProcesando(false);
    }
  };

  const confirmarRecepcion = async (trasladoId: number) => {
    setError(null);
    setExito(null);
    try {
      await solicitarApi(`/api/logistica/traslados/${trasladoId}/confirmar`, {
        method: "POST",
        body: JSON.stringify({ nota_recepcion: "Recibido conforme" }),
      });
      setExito("Recepción física confirmada. Stock habilitado en destino.");
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "No se pudo confirmar traslado."
      );
    }
  };

  const manejarAnular = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!trasladoAnular) return;
    setError(null);
    setExito(null);
    setProcesando(true);
    try {
      await solicitarApi(
        `/api/logistica/traslados/${trasladoAnular.id}/anular`,
        {
          method: "POST",
          body: JSON.stringify({ motivo: motivoAnulacion.trim() }),
        }
      );
      setTrasladoAnular(null);
      setMotivoAnulacion("");
      setExito("Traslado anulado y equipos devueltos a origen.");
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "No se pudo anular traslado."
      );
    } finally {
      setProcesando(false);
    }
  };

  const miSucursalId = usuario?.sucursal?.id ?? null;
  const trasladosVisibles =
    pestana === "por_recibir"
      ? traslados.filter(
          (t) =>
            t.estado === "EN_TRANSITO" &&
            (miSucursalId === null || t.destino_id === miSucursalId)
        )
      : traslados;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900">
            Traslados Seguros en 2 Pasos
          </h2>
          <p className="text-sm text-slate-500">
            Los equipos en tránsito quedan bloqueados hasta confirmar su
            recepción física en la sucursal destino.
          </p>
        </div>

        {puedeEnviar && (
          <button
            type="button"
            onClick={() => setModalCrear(true)}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            Nuevo traslado
          </button>
        )}
      </div>

      {/* Dos pestañas claras */}
      <div className="flex gap-2 border-b border-slate-200 pb-2">
        <button
          type="button"
          onClick={() => setPestana("enviados")}
          className={`px-4 py-2 rounded-xl text-sm font-bold cursor-pointer ${
            pestana === "enviados"
              ? "bg-[#E85A28] text-white"
              : "bg-white border border-slate-200 text-slate-700"
          }`}
        >
          Enviados / En tránsito ({traslados.length})
        </button>
        <button
          type="button"
          onClick={() => setPestana("por_recibir")}
          className={`px-4 py-2 rounded-xl text-sm font-bold cursor-pointer ${
            pestana === "por_recibir"
              ? "bg-[#E85A28] text-white"
              : "bg-white border border-slate-200 text-slate-700"
          }`}
        >
          Por recibir en mi sucursal
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
                className="h-14 rounded-xl bg-slate-100 animate-pulse"
              />
            ))}
          </div>
        ) : trasladosVisibles.length === 0 ? (
          <div className="p-10 text-center space-y-2">
            <Truck className="w-10 h-10 text-slate-300 mx-auto" />
            <p className="text-sm font-semibold text-slate-600">
              No hay traslados en esta bandeja.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Traslado</th>
                  <th className="px-4 py-3">Ruta</th>
                  <th className="px-4 py-3">Seriales / Ítems</th>
                  <th className="px-4 py-3">Estado</th>
                  <th className="px-4 py-3 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {trasladosVisibles.map((t) => (
                  <tr key={t.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <p className="font-mono font-bold text-slate-900">
                        {t.numero_traslado}
                      </p>
                      <p className="text-xs text-slate-500">
                        Envía: {t.enviado_por}
                      </p>
                    </td>
                    <td className="px-4 py-3 font-semibold">
                      {t.origen} → {t.destino}
                    </td>
                    <td className="px-4 py-3 text-xs font-mono">
                      {t.detalles
                        .map((d) => d.serial || `${d.sku} (x${d.cantidad})`)
                        .join(", ")}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                          t.estado === "RECIBIDO"
                            ? "bg-emerald-50 text-emerald-700"
                            : t.estado === "ANULADO"
                            ? "bg-slate-200 text-slate-600"
                            : "bg-amber-50 text-amber-800"
                        }`}
                      >
                        {t.estado}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right space-x-2">
                      {t.estado === "EN_TRANSITO" && (
                        <>
                          <button
                            type="button"
                            onClick={() => void confirmarRecepcion(t.id)}
                            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold cursor-pointer"
                          >
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            Confirmar recepción
                          </button>
                          {puedeEnviar && (
                            <button
                              type="button"
                              onClick={() => {
                                setMotivoAnulacion("");
                                setTrasladoAnular(t);
                              }}
                              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-red-300 text-red-700 hover:bg-red-50 text-xs font-bold cursor-pointer"
                            >
                              <Ban className="w-3.5 h-3.5" />
                              Anular
                            </button>
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal crear traslado */}
      {modalCrear && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl space-y-4">
            <h3 className="text-lg font-black text-slate-900">
              Enviar traslado en 2 pasos
            </h3>
            <form onSubmit={manejarCrearTraslado} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Origen
                  </label>
                  <select
                    required
                    value={origenId}
                    onChange={(e) => {
                      setOrigenId(e.target.value);
                      setEquiposSeleccionados([]);
                    }}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                  >
                    <option value="">Seleccionar...</option>
                    {sucursales
                      .filter((s) => s.estado === "ACTIVA")
                      .map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.nombre}
                        </option>
                      ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Destino
                  </label>
                  <select
                    required
                    value={destinoId}
                    onChange={(e) => setDestinoId(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                  >
                    <option value="">Seleccionar...</option>
                    {sucursales
                      .filter((s) => s.estado === "ACTIVA")
                      .map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.nombre}
                        </option>
                      ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Equipos disponibles en origen ({equiposDisponibles.length})
                </label>
                <div className="max-h-44 overflow-y-auto border border-slate-200 rounded-xl p-2 space-y-1">
                  {equiposDisponibles.length === 0 ? (
                    <p className="text-xs text-slate-500 p-2">
                      Selecciona una sucursal de origen con equipos disponibles.
                    </p>
                  ) : (
                    equiposDisponibles.map((eq) => (
                      <label
                        key={eq.id}
                        className="flex items-center gap-2 text-xs p-1.5 rounded-lg hover:bg-slate-50 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={equiposSeleccionados.includes(eq.id)}
                          onChange={() =>
                            setEquiposSeleccionados((prev) =>
                              prev.includes(eq.id)
                                ? prev.filter((x) => x !== eq.id)
                                : [...prev, eq.id]
                            )
                          }
                        />
                        <span className="font-mono font-bold">{eq.serial}</span>
                        <span className="text-slate-600">{eq.modelo}</span>
                        <span className="ml-auto text-[10px] font-bold text-slate-500">
                          {eq.estado}
                        </span>
                      </label>
                    ))
                  )}
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Nota de despacho
                </label>
                <input
                  type="text"
                  value={nota}
                  onChange={(e) => setNota(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
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
                  disabled={procesando}
                  className="px-4 py-2 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold disabled:opacity-60 cursor-pointer"
                >
                  {procesando ? "Enviando..." : "Enviar traslado"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal anular */}
      {trasladoAnular && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4">
            <h3 className="text-lg font-black text-slate-900">
              Anular traslado {trasladoAnular.numero_traslado}
            </h3>
            <form onSubmit={manejarAnular} className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Motivo obligatorio de anulación
                </label>
                <input
                  type="text"
                  required
                  minLength={3}
                  value={motivoAnulacion}
                  onChange={(e) => setMotivoAnulacion(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setTrasladoAnular(null)}
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
