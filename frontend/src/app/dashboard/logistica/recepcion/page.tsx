"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ScanBarcode,
  ShieldCheck,
  X,
} from "lucide-react";
import { ErrorApi, fechaHoyCaracas, formatearUsd, solicitarApi } from "@/servicios/api";
import type {
  GuiaResumen,
  ResultadoRecepcionGuia,
  Verificador,
} from "@/tipos/logistica";

export default function PaginaRecepcion() {
  const [guias, setGuias] = useState<GuiaResumen[]>([]);
  const [verificadores, setVerificadores] = useState<Verificador[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [guiaId, setGuiaId] = useState("");
  const [verificadorId, setVerificadorId] = useState("");
  const [fechaReal, setFechaReal] = useState(
    fechaHoyCaracas()
  );
  const [inputSerial, setInputSerial] = useState("");
  const [serialesEscaneados, setSerialesEscaneados] = useState<string[]>([]);
  const [procesando, setProcesando] = useState(false);
  const [resultado, setResultado] = useState<ResultadoRecepcionGuia | null>(
    null
  );

  const refInput = useRef<HTMLInputElement>(null);

  const cargarDatos = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [respGuias, respVerif] = await Promise.all([
        solicitarApi<GuiaResumen[]>("/api/logistica/guias?estado=EN_TRANSITO"),
        solicitarApi<Verificador[]>("/api/logistica/verificadores"),
      ]);
      setGuias(respGuias);
      setVerificadores(respVerif);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudieron cargar las guías en tránsito."
      );
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void cargarDatos();
  }, [cargarDatos]);

  useEffect(() => {
    refInput.current?.focus();
  }, [guiaId]);

  const agregarSerial = (valor: string) => {
    const limpio = valor.trim().replace(/\s+/g, "").toUpperCase();
    if (!limpio) return;
    if (!serialesEscaneados.includes(limpio)) {
      setSerialesEscaneados((prev) => [...prev, limpio]);
    }
    setInputSerial("");
    refInput.current?.focus();
  };

  const manejarConfirmarRecepcion = async (
    e: React.FormEvent<HTMLFormElement>
  ) => {
    e.preventDefault();
    setError(null);
    setResultado(null);

    if (!guiaId) {
      setError("Selecciona la guía que estás recibiendo.");
      return;
    }
    if (!verificadorId) {
      setError(
        "Doble control obligatorio: selecciona un segundo usuario verificador."
      );
      return;
    }

    setProcesando(true);
    try {
      const resp = await solicitarApi<ResultadoRecepcionGuia>(
        `/api/logistica/guias/${guiaId}/recibir`,
        {
          method: "POST",
          body: JSON.stringify({
            fecha_llegada_real: fechaReal,
            verificado_por_id: Number(verificadorId),
            seriales_recibidos: serialesEscaneados,
          }),
        }
      );
      setResultado(resp);
      setSerialesEscaneados([]);
      setGuiaId("");
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo confirmar la recepción."
      );
    } finally {
      setProcesando(false);
    }
  };

  const guiaActual = guias.find((g) => String(g.id) === guiaId);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-black text-slate-900">
          Recepción Física por Serial (Doble Verificación)
        </h2>
        <p className="text-sm text-slate-500">
          Escanea los seriales con lector de código de barras (Enter para
          agregar), valida con una segunda persona y prorratea el flete
          automáticamente.
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2.5 p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {resultado && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2 text-emerald-800 font-bold">
            <CheckCircle2 className="w-5 h-5" />
            <span>
              Guía {resultado.numero_guia} recibida · {resultado.equipos_recibidos}{" "}
              equipos ingresados · Verificado por {resultado.verificado_por}
            </span>
          </div>
          {resultado.prorrateo.length > 0 && (
            <div className="bg-white rounded-xl border border-emerald-200 overflow-hidden">
              <table className="w-full text-xs text-left">
                <thead className="bg-emerald-100/50 text-emerald-900 uppercase">
                  <tr>
                    <th className="px-3 py-2">Serial</th>
                    <th className="px-3 py-2">Estado</th>
                    <th className="px-3 py-2 text-right">Costo Compra</th>
                    <th className="px-3 py-2 text-right">Flete Asignado</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-emerald-100">
                  {resultado.prorrateo.map((p) => (
                    <tr key={p.serial}>
                      <td className="px-3 py-2 font-mono font-bold">
                        {p.serial}
                      </td>
                      <td className="px-3 py-2">{p.estado}</td>
                      <td className="px-3 py-2 text-right">
                        {formatearUsd(p.costo_compra_usd)}
                      </td>
                      <td className="px-3 py-2 text-right font-bold text-[#C9461A]">
                        {formatearUsd(p.costo_flete_usd)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <div className="bg-white rounded-2xl border border-slate-200 p-6">
        {cargando ? (
          <div className="h-32 rounded-xl bg-slate-100 animate-pulse" />
        ) : guias.length === 0 ? (
          <div className="text-center py-8 space-y-2">
            <ScanBarcode className="w-10 h-10 text-slate-300 mx-auto" />
            <p className="text-sm font-semibold text-slate-600">
              No hay guías en tránsito pendientes de recepción.
            </p>
          </div>
        ) : (
          <form onSubmit={manejarConfirmarRecepcion} className="space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Guía en tránsito
                </label>
                <select
                  required
                  value={guiaId}
                  onChange={(e) => {
                    setGuiaId(e.target.value);
                    setSerialesEscaneados([]);
                  }}
                  className="w-full px-3 py-2.5 rounded-xl border border-slate-300 text-sm bg-white"
                >
                  <option value="">Seleccionar guía...</option>
                  {guias.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.numero_guia} ({g.seriales_esperados.length} seriales ·
                      Flete {formatearUsd(g.costo_total_guia_usd)})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Fecha de llegada real
                </label>
                <input
                  type="date"
                  required
                  value={fechaReal}
                  onChange={(e) => setFechaReal(e.target.value)}
                  className="w-full px-3 py-2.5 rounded-xl border border-slate-300 text-sm"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Verificado por (2do usuario obligatorio)
                </label>
                <select
                  required
                  value={verificadorId}
                  onChange={(e) => setVerificadorId(e.target.value)}
                  className="w-full px-3 py-2.5 rounded-xl border border-slate-300 text-sm bg-white"
                >
                  <option value="">Seleccionar verificador...</option>
                  {verificadores.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.nombre} ({v.rol})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {guiaActual && (
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
                <p className="text-xs font-bold text-slate-700">
                  Seriales esperados en {guiaActual.numero_guia}:{" "}
                  <span className="font-mono text-slate-600">
                    {guiaActual.seriales_esperados.join(", ") || "Ninguno"}
                  </span>
                </p>

                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <ScanBarcode className="w-4 h-4 text-[#E85A28] absolute left-3 top-1/2 -translate-y-1/2" />
                    <input
                      ref={refInput}
                      type="text"
                      value={inputSerial}
                      onChange={(e) => setInputSerial(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          agregarSerial(inputSerial);
                        }
                      }}
                      placeholder="Escanea o escribe el serial y presiona Enter..."
                      className="w-full pl-9 pr-3 py-2.5 rounded-xl border-2 border-[#E85A28]/40 bg-white text-sm font-mono focus:outline-none focus:border-[#E85A28]"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => agregarSerial(inputSerial)}
                    className="px-4 py-2 rounded-xl bg-slate-900 text-white text-xs font-bold cursor-pointer"
                  >
                    Agregar
                  </button>
                </div>

                {serialesEscaneados.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {serialesEscaneados.map((s) => (
                      <span
                        key={s}
                        className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-orange-100 text-[#C9461A] font-mono text-xs font-bold"
                      >
                        {s}
                        <button
                          type="button"
                          onClick={() =>
                            setSerialesEscaneados((prev) =>
                              prev.filter((x) => x !== s)
                            )
                          }
                          className="cursor-pointer"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={procesando}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold disabled:opacity-60 cursor-pointer"
              >
                <ShieldCheck className="w-4 h-4" />
                {procesando
                  ? "Confirmando recepción..."
                  : "Confirmar recepción y prorratear flete"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
