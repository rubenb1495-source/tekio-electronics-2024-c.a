"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  Award,
  CheckCircle2,
  Download,
  Plus,
  Users,
} from "lucide-react";
import {
  descargarPdfApi,
  extraerMensajeError,
  fechaHoyCaracas,
  formatearUsd,
  solicitarApi,
} from "@/servicios/api";
import type { InstrumentoFinanciero } from "@/tipos/finanzas";

interface SocioItem {
  id: number;
  nombre: string;
  porcentaje_participacion: number;
  activo: boolean;
}

interface SimulacionReparto {
  periodo_mes: string;
  utilidad_neta_mes_usd: number;
  monto_a_distribuir_usd: number;
  porcentaje_total_socios: number;
  distribucion: Array<{
    socio_id: number;
    socio_nombre: string;
    porcentaje_participacion: number;
    monto_usd: number;
  }>;
}

interface RepartoItem {
  id: number;
  periodo_mes: string;
  utilidad_neta_base_usd: number;
  monto_distribuido_usd: number;
  fecha_pago: string;
  instrumento: string;
  notas: string;
  detalles: Array<{
    id: number;
    socio_nombre: string;
    porcentaje_aplicado: number;
    monto_usd: number;
    referencia: string;
  }>;
}

export default function PaginaRepartoUtilidades() {
  const mesActual = fechaHoyCaracas().slice(0, 7);

  const [socios, setSocios] = useState<SocioItem[]>([]);
  const [repartos, setRepartos] = useState<RepartoItem[]>([]);
  const [instrumentos, setInstrumentos] = useState<InstrumentoFinanciero[]>([]);
  const [simulacion, setSimulacion] = useState<SimulacionReparto | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  // Nuevo socio
  const [nombreSocio, setNombreSocio] = useState("");
  const [pctSocio, setPctSocio] = useState("");

  // Nuevo reparto
  const [periodoMes, setPeriodoMes] = useState(mesActual);
  const [montoDistribuir, setMontoDistribuir] = useState("");
  const [instrumentoId, setInstrumentoId] = useState("");
  const [referenciaBase, setReferenciaBase] = useState("");
  const [notas, setNotas] = useState("");
  const [guardando, setGuardando] = useState(false);

  const cargarTodo = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ periodo_mes: periodoMes });
      if (montoDistribuir && Number(montoDistribuir) > 0) {
        qs.set("monto_distribuir_usd", montoDistribuir);
      }
      const [rSoc, rRep, rInst, rSim] = await Promise.all([
        solicitarApi<SocioItem[]>("/api/finanzas/socios"),
        solicitarApi<RepartoItem[]>("/api/finanzas/utilidades/repartos"),
        solicitarApi<InstrumentoFinanciero[]>("/api/finanzas/instrumentos"),
        solicitarApi<SimulacionReparto>(
          `/api/finanzas/utilidades/simular?${qs.toString()}`
        ),
      ]);
      setSocios(rSoc);
      setRepartos(rRep);
      setInstrumentos(rInst);
      setSimulacion(rSim);
      if (rInst.length > 0 && !instrumentoId) {
        setInstrumentoId(String(rInst[0].id));
      }
    } catch (err) {
      setError(
        extraerMensajeError(err, "No se pudo cargar el módulo de utilidades.")
      );
    } finally {
      setCargando(false);
    }
  }, [periodoMes, montoDistribuir, instrumentoId]);

  useEffect(() => {
    void cargarTodo();
  }, [cargarTodo]);

  const agregarSocio = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setExito(null);
    try {
      await solicitarApi("/api/finanzas/socios", {
        method: "POST",
        body: JSON.stringify({
          nombre: nombreSocio.trim(),
          porcentaje_participacion: Number(pctSocio),
          activo: true,
        }),
      });
      setNombreSocio("");
      setPctSocio("");
      setExito("Socio registrado correctamente.");
      await cargarTodo();
    } catch (err) {
      setError(extraerMensajeError(err, "No se pudo registrar el socio."));
    }
  };

  const registrarReparto = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!instrumentoId) return;
    setGuardando(true);
    setError(null);
    setExito(null);
    try {
      const montoFinal = Number(
        montoDistribuir || simulacion?.utilidad_neta_mes_usd || 0
      );
      await solicitarApi("/api/finanzas/utilidades/repartos", {
        method: "POST",
        body: JSON.stringify({
          periodo_mes: periodoMes,
          monto_distribuido_usd: montoFinal,
          fecha_pago: fechaHoyCaracas(),
          instrumento_id: Number(instrumentoId),
          referencia_base: referenciaBase.trim(),
          notas: notas.trim(),
        }),
      });
      setMontoDistribuir("");
      setReferenciaBase("");
      setNotas("");
      setExito(
        "Reparto de utilidades registrado con egreso bancario y asiento contable automático."
      );
      await cargarTodo();
    } catch (err) {
      setError(extraerMensajeError(err, "No se pudo registrar el reparto."));
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-black text-[#191818]">
          Reparto de Utilidades a Socios
        </h2>
        <p className="text-sm text-neutral-500">
          Distribución porcentual sobre utilidad neta disponible con descuento bancario, asiento patrimonial automático y comprobante PDF con marca de agua.
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Socios y Participación */}
        <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 space-y-4">
          <h3 className="text-sm font-black text-[#191818] flex items-center gap-2">
            <Users className="w-4 h-4 text-[#E85A28]" />
            Socios y Participación (%)
          </h3>
          <form onSubmit={agregarSocio} className="space-y-2.5">
            <input
              type="text"
              required
              value={nombreSocio}
              onChange={(e) => setNombreSocio(e.target.value)}
              placeholder="Nombre del socio..."
              className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-xs"
            />
            <div className="flex gap-2">
              <input
                type="number"
                step="0.01"
                min="0.01"
                max="100"
                required
                value={pctSocio}
                onChange={(e) => setPctSocio(e.target.value)}
                placeholder="% participación"
                className="flex-1 px-3 py-2 rounded-xl border border-neutral-300 bg-white text-xs tabular-nums"
              />
              <button
                type="submit"
                className="inline-flex items-center gap-1 px-3 py-2 rounded-xl bg-[#191818] text-white text-xs font-bold cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                Agregar
              </button>
            </div>
          </form>

          <div className="divide-y divide-neutral-100 text-xs tabular-nums">
            {socios.map((s) => (
              <div key={s.id} className="py-2.5 flex items-center justify-between">
                <span className="font-bold text-[#191818]">{s.nombre}</span>
                <span className="px-2 py-0.5 rounded-full bg-[#FDF0EB] text-[#E85A28] font-black">
                  {s.porcentaje_participacion}%
                </span>
              </div>
            ))}
            {socios.length === 0 && (
              <p className="text-neutral-400 py-3">Sin socios registrados.</p>
            )}
          </div>
        </div>

        {/* Simulador y Registro de Reparto */}
        <form
          onSubmit={registrarReparto}
          className="lg:col-span-2 bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 space-y-4"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-black text-[#191818] flex items-center gap-2">
              <Award className="w-4 h-4 text-[#E85A28]" />
              Calcular y Registrar Reparto de Utilidades
            </h3>
            {simulacion && (
              <span className="text-xs font-bold text-emerald-700 tabular-nums">
                Utilidad Neta del mes: {formatearUsd(simulacion.utilidad_neta_mes_usd)}
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
                Período (Mes)
              </label>
              <input
                type="month"
                required
                value={periodoMes}
                onChange={(e) => setPeriodoMes(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
              />
            </div>
            <div>
              <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
                Monto a Distribuir (USD)
              </label>
              <input
                type="number"
                step="0.01"
                min="1"
                required
                value={montoDistribuir}
                onChange={(e) => setMontoDistribuir(e.target.value)}
                placeholder={String(simulacion?.utilidad_neta_mes_usd ?? 0)}
                className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm tabular-nums"
              />
            </div>
            <div>
              <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
                Banco / Instrumento de Egreso
              </label>
              <select
                required
                value={instrumentoId}
                onChange={(e) => setInstrumentoId(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
              >
                {instrumentos.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.nombre} ({i.moneda})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {simulacion && simulacion.distribucion.length > 0 && (
            <div className="rounded-xl bg-neutral-50 border border-neutral-200 p-3 space-y-1.5 text-xs tabular-nums">
              <p className="font-black text-neutral-700">
                Vista previa de distribución por socio:
              </p>
              {simulacion.distribucion.map((d) => (
                <div key={d.socio_id} className="flex justify-between">
                  <span>
                    {d.socio_nombre} ({d.porcentaje_participacion}%)
                  </span>
                  <span className="font-bold text-[#191818]">
                    {formatearUsd(d.monto_usd)}
                  </span>
                </div>
              ))}
            </div>
          )}

          <div className="flex flex-wrap gap-3">
            <input
              type="text"
              value={referenciaBase}
              onChange={(e) => setReferenciaBase(e.target.value)}
              placeholder="Referencia base (ej. DIV-2026-11)"
              className="w-52 px-3 py-2 rounded-xl border border-neutral-300 bg-white text-xs"
            />
            <input
              type="text"
              value={notas}
              onChange={(e) => setNotas(e.target.value)}
              placeholder="Notas del acta de socios..."
              className="flex-1 min-w-[200px] px-3 py-2 rounded-xl border border-neutral-300 bg-white text-xs"
            />
            <button
              type="submit"
              disabled={guardando}
              className="px-5 py-2 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-xs font-bold cursor-pointer disabled:opacity-50"
            >
              {guardando ? "Registrando..." : "Registrar Pago y Asiento"}
            </button>
          </div>
        </form>
      </div>

      {/* Historial de repartos */}
      <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl overflow-hidden">
        <div className="px-5 py-3.5 border-b border-neutral-100 font-black text-sm text-[#191818]">
          Historial de Repartos Registrados ({repartos.length})
        </div>
        {cargando ? (
          <div className="p-6 h-24 animate-pulse bg-neutral-100" />
        ) : repartos.length === 0 ? (
          <div className="p-8 text-center text-sm text-neutral-500">
            No se han registrado repartos de utilidades aún.
          </div>
        ) : (
          <div className="divide-y divide-neutral-100">
            {repartos.map((r) => (
              <div
                key={r.id}
                className="p-4 flex flex-wrap items-center justify-between gap-4 tabular-nums"
              >
                <div>
                  <p className="text-sm font-black text-[#191818]">
                    Período {r.periodo_mes} · {formatearUsd(r.monto_distribuido_usd)}
                  </p>
                  <p className="text-xs text-neutral-500">
                    Pagado el {r.fecha_pago} desde {r.instrumento} ·{" "}
                    {r.detalles
                      .map((d) => `${d.socio_nombre}: ${formatearUsd(d.monto_usd)}`)
                      .join(" | ")}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    void descargarPdfApi(
                      `/api/finanzas/utilidades/repartos/${r.id}/pdf`,
                      `reparto_utilidades_${r.periodo_mes}_${r.id}.pdf`
                    )
                  }
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#191818] text-white text-xs font-bold cursor-pointer"
                >
                  <Download className="w-3.5 h-3.5" />
                  Comprobante PDF
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
