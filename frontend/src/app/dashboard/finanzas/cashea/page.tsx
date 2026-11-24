"use client";

import React, { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, CreditCard } from "lucide-react";
import { ErrorApi, fechaHoyCaracas, formatearUsd, solicitarApi } from "@/servicios/api";
import type {
  CuentaPorCobrarResumen,
  InstrumentoFinanciero,
} from "@/tipos/finanzas";

export default function PaginaFinanzasCashea() {
  const [cuentas, setCuentas] = useState<CuentaPorCobrarResumen[]>([]);
  const [instrumentos, setInstrumentos] = useState<InstrumentoFinanciero[]>([]);
  const [seleccionadas, setSeleccionadas] = useState<number[]>([]);
  const [destinoId, setDestinoId] = useState("");
  const [fechaPago, setFechaPago] = useState(
    fechaHoyCaracas()
  );
  const [comision, setComision] = useState("0");
  const [impuestos, setImpuestos] = useState("0");
  const [referencia, setReferencia] = useState("");
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  const cargarDatos = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [respCxc, respInst] = await Promise.all([
        solicitarApi<CuentaPorCobrarResumen[]>(
          "/api/finanzas/cuentas-por-cobrar?tipo=CASHEA&estado=PENDIENTE"
        ),
        solicitarApi<InstrumentoFinanciero[]>("/api/finanzas/instrumentos"),
      ]);
      setCuentas(respCxc);
      setInstrumentos(respInst);
      if (respInst[0] && !destinoId) setDestinoId(String(respInst[0].id));
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudieron cargar las cuentas Cashea."
      );
    } finally {
      setCargando(false);
    }
  }, [destinoId]);

  useEffect(() => {
    void cargarDatos();
  }, [cargarDatos]);

  const liquidarLote = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (seleccionadas.length === 0) {
      setError("Selecciona al menos una cuenta Cashea para liquidar.");
      return;
    }
    setError(null);
    setExito(null);
    try {
      const resp = await solicitarApi<{
        cuentas_liquidadas: number;
        neto_depositado_usd: number;
      }>("/api/finanzas/cashea/liquidar", {
        method: "POST",
        body: JSON.stringify({
          cuentas_cashea_ids: seleccionadas,
          instrumento_destino_id: Number(destinoId),
          fecha_pago: fechaPago,
          comision_usd: Number(comision || 0),
          impuestos_usd: Number(impuestos || 0),
          referencia: referencia.trim(),
        }),
      });
      setSeleccionadas([]);
      setReferencia("");
      setExito(
        `Se liquidaron ${resp.cuentas_liquidadas} notas Cashea. Neto depositado: ${formatearUsd(resp.neto_depositado_usd)}.`
      );
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo registrar la liquidación Cashea."
      );
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-black text-slate-900 flex items-center gap-2">
          <CreditCard className="w-6 h-6 text-[#E85A28]" />
          Por Cobrar Cashea y Liquidaciones
        </h2>
        <p className="text-sm text-slate-500">
          Selecciona las cuotas financiadas por liquidar y registra el depósito
          neto a tasa BCV del día de pago.
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

      <form
        onSubmit={liquidarLote}
        className="bg-white rounded-2xl border border-slate-200 p-5 grid grid-cols-1 md:grid-cols-6 gap-3 items-end"
      >
        <div className="md:col-span-2">
          <label className="block text-xs font-bold text-slate-700 mb-1">
            Banco destino
          </label>
          <select
            value={destinoId}
            onChange={(e) => setDestinoId(e.target.value)}
            className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
          >
            {instrumentos.map((i) => (
              <option key={i.id} value={i.id}>
                {i.nombre} ({i.moneda})
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-bold text-slate-700 mb-1">
            Fecha pago
          </label>
          <input
            type="date"
            value={fechaPago}
            onChange={(e) => setFechaPago(e.target.value)}
            className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-bold text-slate-700 mb-1">
            Comisión USD
          </label>
          <input
            type="number"
            step="0.01"
            min="0"
            value={comision}
            onChange={(e) => setComision(e.target.value)}
            className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-bold text-slate-700 mb-1">
            Impuestos USD
          </label>
          <input
            type="number"
            step="0.01"
            min="0"
            value={impuestos}
            onChange={(e) => setImpuestos(e.target.value)}
            className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
          />
        </div>
        <button
          type="submit"
          disabled={seleccionadas.length === 0}
          className="px-4 py-2.5 rounded-xl bg-[#E85A28] disabled:opacity-40 text-white text-xs font-bold cursor-pointer"
        >
          Liquidar ({seleccionadas.length})
        </button>
      </form>

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        {cargando ? (
          <div className="p-6 h-24 bg-slate-100 animate-pulse" />
        ) : cuentas.length === 0 ? (
          <p className="p-10 text-center text-sm text-slate-500">
            No hay cuotas Cashea pendientes de liquidar.
          </p>
        ) : (
          <table className="w-full text-sm text-left">
            <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3 w-10" />
                <th className="px-4 py-3">Nota</th>
                <th className="px-4 py-3">Fecha</th>
                <th className="px-4 py-3">Sucursal</th>
                <th className="px-4 py-3 text-right">Pendiente USD</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {cuentas.map((c) => (
                <tr key={c.id}>
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={seleccionadas.includes(c.id)}
                      onChange={() =>
                        setSeleccionadas((prev) =>
                          prev.includes(c.id)
                            ? prev.filter((x) => x !== c.id)
                            : [...prev, c.id]
                        )
                      }
                    />
                  </td>
                  <td className="px-4 py-3 font-mono font-bold">
                    {c.numero_venta}
                  </td>
                  <td className="px-4 py-3">{c.fecha_venta}</td>
                  <td className="px-4 py-3">{c.sucursal}</td>
                  <td className="px-4 py-3 text-right font-black text-[#C9461A]">
                    {formatearUsd(c.saldo_pendiente_usd)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
