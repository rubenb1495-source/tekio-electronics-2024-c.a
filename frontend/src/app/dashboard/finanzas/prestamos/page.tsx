"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CalendarClock,
  CheckCircle2,
  CreditCard,
  Plus,
  Wallet,
} from "lucide-react";
import {
  extraerMensajeError,
  fechaHoyCaracas,
  formatearUsd,
  solicitarApi,
} from "@/servicios/api";
import type { InstrumentoFinanciero } from "@/tipos/finanzas";

interface CuotaPrestamo {
  id: number;
  nro_cuota: number;
  fecha_vencimiento: string;
  capital_usd: number;
  interes_usd: number;
  cuota_total_usd: number;
  estado: "PENDIENTE" | "PAGADA";
  fecha_pago: string | null;
  pago_egreso_id: number | null;
  referencia_pago: string;
}

interface PrestamoResumen {
  id: number;
  acreedor: string;
  monto_principal_usd: number;
  tasa_interes_anual_pct: number;
  plazo_meses: number;
  fecha_inicio: string;
  estado: string;
  instrumento_desembolso_id: number | null;
  instrumento_desembolso: string | null;
  notas: string;
  capital_pagado_usd: number;
  intereses_pagados_usd: number;
  saldo_capital_usd: number;
  cuotas_pagadas: number;
  cuotas_totales: number;
  proxima_cuota: {
    id: number;
    nro_cuota: number;
    fecha_vencimiento: string;
    cuota_total_usd: number;
  } | null;
  cuotas: CuotaPrestamo[];
}

export default function PaginaPrestamos() {
  const [prestamos, setPrestamos] = useState<PrestamoResumen[]>([]);
  const [instrumentos, setInstrumentos] = useState<InstrumentoFinanciero[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  // Formulario nuevo préstamo
  const [acreedor, setAcreedor] = useState("");
  const [montoPrincipal, setMontoPrincipal] = useState("");
  const [tasaAnual, setTasaAnual] = useState("12");
  const [plazoMeses, setPlazoMeses] = useState("6");
  const [fechaInicio, setFechaInicio] = useState(fechaHoyCaracas());
  const [instrumentoDesembolsoId, setInstrumentoDesembolsoId] = useState("");
  const [notas, setNotas] = useState("");
  const [guardando, setGuardando] = useState(false);

  // Pago de cuota
  const [cuotaSeleccionada, setCuotaSeleccionada] = useState<{
    prestamoId: number;
    acreedor: string;
    cuota: CuotaPrestamo;
  } | null>(null);
  const [instrumentoPagoId, setInstrumentoPagoId] = useState("");
  const [referenciaPago, setReferenciaPago] = useState("");
  const [pagandoCuota, setPagandoCuota] = useState(false);

  const cargarTodo = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [respPrest, respInst] = await Promise.all([
        solicitarApi<PrestamoResumen[]>("/api/finanzas/prestamos"),
        solicitarApi<InstrumentoFinanciero[]>("/api/finanzas/instrumentos"),
      ]);
      setPrestamos(respPrest);
      setInstrumentos(respInst);
      if (respInst.length > 0 && !instrumentoPagoId) {
        setInstrumentoPagoId(String(respInst[0].id));
      }
    } catch (err) {
      setError(extraerMensajeError(err, "No se pudieron cargar los préstamos."));
    } finally {
      setCargando(false);
    }
  }, [instrumentoPagoId]);

  useEffect(() => {
    void cargarTodo();
  }, [cargarTodo]);

  const crearPrestamo = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setExito(null);
    setGuardando(true);
    try {
      await solicitarApi("/api/finanzas/prestamos", {
        method: "POST",
        body: JSON.stringify({
          acreedor: acreedor.trim(),
          monto_principal_usd: Number(montoPrincipal),
          tasa_interes_anual_pct: Number(tasaAnual || 0),
          plazo_meses: Number(plazoMeses),
          fecha_inicio: fechaInicio,
          instrumento_desembolso_id: instrumentoDesembolsoId
            ? Number(instrumentoDesembolsoId)
            : null,
          notas: notas.trim(),
        }),
      });
      setAcreedor("");
      setMontoPrincipal("");
      setNotas("");
      setExito("Préstamo registrado con tabla de amortización y asiento contable automático.");
      await cargarTodo();
    } catch (err) {
      setError(extraerMensajeError(err, "No se pudo registrar el préstamo."));
    } finally {
      setGuardando(false);
    }
  };

  const confirmarPagoCuota = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!cuotaSeleccionada || !instrumentoPagoId) return;
    setPagandoCuota(true);
    setError(null);
    setExito(null);
    try {
      await solicitarApi(
        `/api/finanzas/prestamos/${cuotaSeleccionada.prestamoId}/cuotas/${cuotaSeleccionada.cuota.id}/pagar`,
        {
          method: "POST",
          body: JSON.stringify({
            instrumento_id: Number(instrumentoPagoId),
            fecha_pago: fechaHoyCaracas(),
            referencia_pago: referenciaPago.trim(),
          }),
        }
      );
      setExito(
        `Cuota #${cuotaSeleccionada.cuota.nro_cuota} de ${cuotaSeleccionada.acreedor} pagada y contabilizada.`
      );
      setCuotaSeleccionada(null);
      setReferenciaPago("");
      await cargarTodo();
    } catch (err) {
      setError(extraerMensajeError(err, "No se pudo registrar el pago de la cuota."));
    } finally {
      setPagandoCuota(false);
    }
  };

  const totalActivos = prestamos.filter((p) => p.estado === "ACTIVO").length;
  const totalCapitalPendiente = prestamos.reduce(
    (acc, p) => acc + p.saldo_capital_usd,
    0
  );
  const totalInteresesPagados = prestamos.reduce(
    (acc, p) => acc + p.intereses_pagados_usd,
    0
  );

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-black text-[#191818]">
          Préstamos y Tabla de Amortización
        </h2>
        <p className="text-sm text-neutral-500">
          Control de financiamientos, cuotas con vencimientos en alertas inteligentes y contabilización automática por partida doble.
        </p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5">
          <p className="text-xs font-bold uppercase text-neutral-500 flex items-center gap-1.5">
            <CreditCard className="w-4 h-4 text-[#E85A28]" />
            Préstamos activos
          </p>
          <p className="text-3xl font-black text-[#191818] mt-1 tabular-nums">
            {totalActivos}
          </p>
        </div>
        <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5">
          <p className="text-xs font-bold uppercase text-neutral-500 flex items-center gap-1.5">
            <Wallet className="w-4 h-4 text-[#E85A28]" />
            Capital pendiente por pagar
          </p>
          <p className="text-3xl font-black text-[#191818] mt-1 tabular-nums">
            {formatearUsd(totalCapitalPendiente)}
          </p>
        </div>
        <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5">
          <p className="text-xs font-bold uppercase text-neutral-500 flex items-center gap-1.5">
            <CalendarClock className="w-4 h-4 text-emerald-600" />
            Intereses pagados acumulados
          </p>
          <p className="text-3xl font-black text-emerald-700 mt-1 tabular-nums">
            {formatearUsd(totalInteresesPagados)}
          </p>
        </div>
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

      {/* Registrar nuevo préstamo */}
      <form
        onSubmit={crearPrestamo}
        className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-6 space-y-4"
      >
        <h3 className="text-base font-bold text-[#191818] flex items-center gap-2">
          <Plus className="w-4 h-4 text-[#E85A28]" />
          Registrar nuevo préstamo
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Acreedor / Institución
            </label>
            <input
              type="text"
              required
              value={acreedor}
              onChange={(e) => setAcreedor(e.target.value)}
              placeholder="Ej: Banco Mercantil / Inversionista"
              className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Monto Principal (USD)
            </label>
            <input
              type="number"
              step="0.01"
              min="1"
              required
              value={montoPrincipal}
              onChange={(e) => setMontoPrincipal(e.target.value)}
              placeholder="5000.00"
              className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm tabular-nums"
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Tasa Interés Anual (%)
            </label>
            <input
              type="number"
              step="0.01"
              min="0"
              max="200"
              value={tasaAnual}
              onChange={(e) => setTasaAnual(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm tabular-nums"
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Plazo (Meses)
            </label>
            <input
              type="number"
              min="1"
              max="120"
              required
              value={plazoMeses}
              onChange={(e) => setPlazoMeses(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm tabular-nums"
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Fecha de inicio
            </label>
            <input
              type="date"
              required
              value={fechaInicio}
              onChange={(e) => setFechaInicio(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Instrumento de desembolso (opcional)
            </label>
            <select
              value={instrumentoDesembolsoId}
              onChange={(e) => setInstrumentoDesembolsoId(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
            >
              <option value="">Solo registro contable</option>
              {instrumentos.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.nombre} ({i.moneda})
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="text"
            value={notas}
            onChange={(e) => setNotas(e.target.value)}
            placeholder="Notas u observaciones del contrato..."
            className="flex-1 min-w-[240px] px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
          />
          <button
            type="submit"
            disabled={guardando}
            className="px-5 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold cursor-pointer disabled:opacity-50"
          >
            {guardando ? "Registrando..." : "Crear Préstamo y Amortización"}
          </button>
        </div>
      </form>

      {/* Modal rápido de pago de cuota */}
      {cuotaSeleccionada && (
        <form
          onSubmit={confirmarPagoCuota}
          className="bg-[#FDF0EB] border border-[#E85A28]/40 rounded-2xl p-5 space-y-3"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h4 className="text-sm font-black text-[#191818]">
                Pagar Cuota #{cuotaSeleccionada.cuota.nro_cuota} ·{" "}
                {cuotaSeleccionada.acreedor}
              </h4>
              <p className="text-xs text-neutral-600 tabular-nums">
                Capital: {formatearUsd(cuotaSeleccionada.cuota.capital_usd)} + Interés:{" "}
                {formatearUsd(cuotaSeleccionada.cuota.interes_usd)} ={" "}
                <strong>
                  {formatearUsd(cuotaSeleccionada.cuota.cuota_total_usd)}
                </strong>
              </p>
            </div>
            <button
              type="button"
              onClick={() => setCuotaSeleccionada(null)}
              className="text-xs font-bold text-neutral-600 hover:underline cursor-pointer"
            >
              Cancelar
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <select
              required
              value={instrumentoPagoId}
              onChange={(e) => setInstrumentoPagoId(e.target.value)}
              className="px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
            >
              {instrumentos.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.nombre} ({i.moneda})
                </option>
              ))}
            </select>
            <input
              type="text"
              value={referenciaPago}
              onChange={(e) => setReferenciaPago(e.target.value)}
              placeholder="Nro. referencia / comprobante..."
              className="px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
            />
            <button
              type="submit"
              disabled={pagandoCuota}
              className="px-4 py-2 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold cursor-pointer disabled:opacity-50"
            >
              {pagandoCuota ? "Contabilizando..." : "Confirmar Pago de Cuota"}
            </button>
          </div>
        </form>
      )}

      {/* Listado de préstamos y tablas de amortización */}
      {cargando ? (
        <div className="bg-white/80 border border-neutral-200 rounded-2xl p-6 space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="h-14 rounded-xl bg-neutral-100 animate-pulse" />
          ))}
        </div>
      ) : prestamos.length === 0 ? (
        <div className="bg-white/80 border border-neutral-200 rounded-2xl p-10 text-center text-sm text-neutral-500">
          No hay préstamos registrados todavía.
        </div>
      ) : (
        <div className="space-y-4">
          {prestamos.map((p) => (
            <div
              key={p.id}
              className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl overflow-hidden"
            >
              <div className="p-5 border-b border-neutral-100 flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-black text-[#191818]">
                      {p.acreedor}
                    </h3>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${
                        p.estado === "PAGADO"
                          ? "bg-emerald-100 text-emerald-800"
                          : "bg-amber-100 text-amber-800"
                      }`}
                    >
                      {p.estado}
                    </span>
                  </div>
                  <p className="text-xs text-neutral-500 mt-0.5 tabular-nums">
                    Inicio: {p.fecha_inicio} · Plazo: {p.plazo_meses} meses · Tasa anual:{" "}
                    {p.tasa_interes_anual_pct}% · Cuotas: {p.cuotas_pagadas}/{p.cuotas_totales}
                  </p>
                </div>
                <div className="flex flex-wrap gap-6 text-right tabular-nums">
                  <div>
                    <p className="text-[11px] uppercase font-bold text-neutral-400">
                      Principal
                    </p>
                    <p className="text-sm font-black text-[#191818]">
                      {formatearUsd(p.monto_principal_usd)}
                    </p>
                  </div>
                  <div>
                    <p className="text-[11px] uppercase font-bold text-neutral-400">
                      Saldo Capital
                    </p>
                    <p className="text-sm font-black text-[#E85A28]">
                      {formatearUsd(p.saldo_capital_usd)}
                    </p>
                  </div>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-neutral-50 text-neutral-500 uppercase">
                    <tr>
                      <th className="px-4 py-2.5">Cuota</th>
                      <th className="px-4 py-2.5">Vencimiento</th>
                      <th className="px-4 py-2.5 text-right">Capital</th>
                      <th className="px-4 py-2.5 text-right">Interés</th>
                      <th className="px-4 py-2.5 text-right">Total Cuota</th>
                      <th className="px-4 py-2.5">Estado</th>
                      <th className="px-4 py-2.5 text-right">Acción</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-100 tabular-nums">
                    {p.cuotas.map((c) => (
                      <tr key={c.id} className="hover:bg-neutral-50/80">
                        <td className="px-4 py-2.5 font-bold">#{c.nro_cuota}</td>
                        <td className="px-4 py-2.5">{c.fecha_vencimiento}</td>
                        <td className="px-4 py-2.5 text-right">
                          {formatearUsd(c.capital_usd)}
                        </td>
                        <td className="px-4 py-2.5 text-right text-amber-700">
                          {formatearUsd(c.interes_usd)}
                        </td>
                        <td className="px-4 py-2.5 text-right font-bold text-[#191818]">
                          {formatearUsd(c.cuota_total_usd)}
                        </td>
                        <td className="px-4 py-2.5">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              c.estado === "PAGADA"
                                ? "bg-emerald-100 text-emerald-800"
                                : "bg-neutral-100 text-neutral-700"
                            }`}
                          >
                            {c.estado}
                            {c.fecha_pago ? ` · ${c.fecha_pago}` : ""}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          {c.estado === "PENDIENTE" ? (
                            <button
                              type="button"
                              onClick={() =>
                                setCuotaSeleccionada({
                                  prestamoId: p.id,
                                  acreedor: p.acreedor,
                                  cuota: c,
                                })
                              }
                              className="px-2.5 py-1 rounded-lg bg-[#E85A28] hover:bg-[#C9461A] text-white font-bold cursor-pointer"
                            >
                              Pagar Cuota
                            </button>
                          ) : (
                            <span className="text-neutral-400">
                              {c.referencia_pago || "Pagada"}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
