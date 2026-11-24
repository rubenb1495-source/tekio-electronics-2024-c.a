"use client";

import React, { useCallback, useEffect, useState } from "react";
import { AlertCircle, Award } from "lucide-react";
import { ErrorApi, formatearUsd, solicitarApi } from "@/servicios/api";
import type { ResumenTecnico } from "@/tipos/taller";

const MESES = [
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
];

export default function PaginaMiResumenTecnico() {
  const hoy = new Date();
  const [mes, setMes] = useState(hoy.getMonth() + 1);
  const [anio, setAnio] = useState(hoy.getFullYear());
  const [resumen, setResumen] = useState<ResumenTecnico | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const cargarResumen = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const datos = await solicitarApi<ResumenTecnico>(
        `/api/taller/resumen-tecnico?mes=${mes}&anio=${anio}`
      );
      setResumen(datos);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo cargar tu resumen mensual."
      );
    } finally {
      setCargando(false);
    }
  }, [mes, anio]);

  useEffect(() => {
    void cargarResumen();
  }, [cargarResumen]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900 flex items-center gap-2">
            <Award className="w-6 h-6 text-[#E85A28]" />
            Mi Resumen Mensual de Taller
          </h2>
          <p className="text-sm text-slate-500">
            Preparaciones ($1 estándar), comisión 50% en servicios técnicos y 1%
            en ventas como asesor.
          </p>
        </div>

        <div className="flex gap-2">
          <select
            value={mes}
            onChange={(e) => setMes(Number(e.target.value))}
            className="px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
          >
            {MESES.map((nombre, i) => (
              <option key={nombre} value={i + 1}>
                {nombre}
              </option>
            ))}
          </select>
          <input
            type="number"
            min={2024}
            max={2100}
            value={anio}
            onChange={(e) => setAnio(Number(e.target.value))}
            className="w-24 px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
          />
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2.5 p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {cargando || !resumen ? (
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 rounded-2xl bg-slate-200 animate-pulse" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-white p-5 rounded-2xl border border-slate-200">
              <p className="text-xs font-bold uppercase text-slate-500">
                Preparaciones ({resumen.cantidad_preparaciones})
              </p>
              <p className="text-2xl font-black text-slate-900 mt-1">
                {formatearUsd(resumen.pago_preparaciones_usd)}
              </p>
            </div>
            <div className="bg-white p-5 rounded-2xl border border-slate-200">
              <p className="text-xs font-bold uppercase text-slate-500">
                Comisión servicios 50% ({resumen.cantidad_servicios})
              </p>
              <p className="text-2xl font-black text-sky-700 mt-1">
                {formatearUsd(resumen.comision_servicios_usd)}
              </p>
            </div>
            <div className="bg-white p-5 rounded-2xl border border-slate-200">
              <p className="text-xs font-bold uppercase text-slate-500">
                Comisión asesor 1%
              </p>
              <p className="text-2xl font-black text-emerald-700 mt-1">
                {formatearUsd(resumen.comision_asesor_usd)}
              </p>
            </div>
            <div className="bg-gradient-to-br from-[#E85A28] to-[#C9461A] p-5 rounded-2xl text-white">
              <p className="text-xs font-bold uppercase text-orange-100">
                Total del mes
              </p>
              <p className="text-2xl font-black mt-1">
                {formatearUsd(resumen.total_mes_usd)}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
              <div className="px-5 py-3 border-b border-slate-200 font-bold text-sm">
                Detalle de preparaciones
              </div>
              {resumen.detalle_preparaciones.length === 0 ? (
                <p className="p-6 text-xs text-slate-500 text-center">
                  Sin preparaciones este mes.
                </p>
              ) : (
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase">
                    <tr>
                      <th className="px-4 py-2">Fecha</th>
                      <th className="px-4 py-2">Serial</th>
                      <th className="px-4 py-2">Resultado</th>
                      <th className="px-4 py-2 text-right">Pago</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {resumen.detalle_preparaciones.map((p) => (
                      <tr key={p.id}>
                        <td className="px-4 py-2">{p.fecha}</td>
                        <td className="px-4 py-2 font-mono font-bold">
                          {p.serial}
                        </td>
                        <td className="px-4 py-2">{p.resultado}</td>
                        <td className="px-4 py-2 text-right font-bold text-emerald-700">
                          {formatearUsd(p.pago_tecnico_usd)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
              <div className="px-5 py-3 border-b border-slate-200 font-bold text-sm">
                Detalle de servicios técnicos (50%)
              </div>
              {resumen.detalle_servicios.length === 0 ? (
                <p className="p-6 text-xs text-slate-500 text-center">
                  Sin servicios comisionables este mes.
                </p>
              ) : (
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase">
                    <tr>
                      <th className="px-4 py-2">Caso</th>
                      <th className="px-4 py-2">Equipo</th>
                      <th className="px-4 py-2 text-right">Mano Obra</th>
                      <th className="px-4 py-2 text-right">Comisión 50%</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {resumen.detalle_servicios.map((s) => (
                      <tr key={s.numero_caso}>
                        <td className="px-4 py-2 font-mono font-bold">
                          {s.numero_caso}
                        </td>
                        <td className="px-4 py-2">{s.descripcion_equipo}</td>
                        <td className="px-4 py-2 text-right">
                          {formatearUsd(s.mano_obra_usd)}
                        </td>
                        <td className="px-4 py-2 text-right font-bold text-sky-700">
                          {formatearUsd(s.comision_50_usd)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
