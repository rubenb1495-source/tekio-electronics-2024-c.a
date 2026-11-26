"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, CheckCircle2, Copy, CreditCard } from "lucide-react";
import BuscadorTabla from "@/componentes/BuscadorTabla";
import { usarSesion } from "@/contexto/SesionContexto";
import {
  copiarTextoPortapapeles,
  formatearWhatsAppPago,
} from "@/lib/whatsapp";
import { ErrorApi, fechaHoyCaracas, formatearBs, formatearUsd, solicitarApi } from "@/servicios/api";
import type {
  CuentaPorCobrarResumen,
  InstrumentoFinanciero,
} from "@/tipos/finanzas";

export default function PaginaFinanzasCashea() {
  const { usuario } = usarSesion();
  const [cuentas, setCuentas] = useState<CuentaPorCobrarResumen[]>([]);
  const [busqueda, setBusqueda] = useState("");
  const [ultimaLiqWa, setUltimaLiqWa] = useState<string | null>(null);
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
      // Garantizar 1 fila única por venta_id (nota N-XXXX) sin concatenar estado previo
      const vistasPorVenta = new Map<string, CuentaPorCobrarResumen>();
      for (const item of respCxc) {
        const clave = item.venta_id != null ? `v-${item.venta_id}` : `c-${item.id}`;
        if (!vistasPorVenta.has(clave)) {
          vistasPorVenta.set(clave, item);
        }
      }
      setCuentas(Array.from(vistasPorVenta.values()));
      setInstrumentos(respInst);
      if (respInst[0]) {
        setDestinoId((prev) => prev || String(respInst[0].id));
      }
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudieron cargar las cuentas Cashea."
      );
    } finally {
      setCargando(false);
    }
  }, []);

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
      const instObj = instrumentos.find((i) => String(i.id) === destinoId);
      setUltimaLiqWa(
        formatearWhatsAppPago({
          tipo_movimiento: "INGRESO",
          tipo_documento: "CASHEA",
          fecha: fechaPago,
          instrumento: instObj?.nombre || "Banco destino",
          monto_moneda_origen: resp.neto_depositado_usd,
          moneda: "USD",
          usd_nominal: resp.neto_depositado_usd,
          referencia: referencia.trim() || `Lote ${resp.cuentas_liquidadas} notas`,
          cliente_o_venta: `Liquidación Cashea (${resp.cuentas_liquidadas} notas)`,
          estado_verificacion: "CONFIRMADO",
          usuario: usuario?.nombre || "Administración",
        })
      );
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

  const cuentasFiltradas = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return cuentas;
    return cuentas.filter((c) =>
      [
        c.numero_venta || "",
        c.fecha_venta || "",
        c.sucursal || "",
        c.cliente || "",
        String(c.saldo_pendiente_usd),
      ]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [cuentas, busqueda]);

  const cuentasLote = useMemo(() => {
    if (seleccionadas.length > 0) {
      return cuentas.filter((c) => seleccionadas.includes(c.id));
    }
    return cuentasFiltradas;
  }, [cuentas, cuentasFiltradas, seleccionadas]);

  const consolidadoCashea = useMemo(() => {
    return cuentasLote.reduce(
      (acc, c) => ({
        financiado: acc.financiado + (c.saldo_pendiente_usd || 0),
        comTotal: acc.comTotal + (c.comision_cashea_venta_total_usd || 0),
        comFin: acc.comFin + (c.comision_cashea_financiado_usd || 0),
        iva: acc.iva + (c.iva_cashea_usd || 0),
        islr: acc.islr + (c.islr_cashea_usd || 0),
        deducciones: acc.deducciones + (c.total_deducciones_cashea_usd || 0),
        neto: acc.neto + (c.neto_esperado_cashea_usd ?? c.saldo_pendiente_usd ?? 0),
      }),
      { financiado: 0, comTotal: 0, comFin: 0, iva: 0, islr: 0, deducciones: 0, neto: 0 }
    );
  }, [cuentasLote]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-black text-slate-900 flex items-center gap-2">
          <CreditCard className="w-6 h-6 text-[#E85A28]" />
          Conciliación Financiera Cashea (Solo Administración / Dirección)
        </h2>
        <p className="text-xs text-neutral-500 mt-0.5">
          Desglose consolidado: 4% sobre total Regular + 4% sobre financiado + 16% IVA + 2% ISLR sobre el fee total.
        </p>
      </div>

      {/* Consolidado financiero Cashea */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 tabular-nums">
        <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-4">
          <p className="text-[11px] font-bold uppercase text-neutral-500">Financiado Bruto</p>
          <p className="text-xl font-black text-[#191818] mt-1">{formatearUsd(consolidadoCashea.financiado)}</p>
        </div>
        <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-4">
          <p className="text-[11px] font-bold uppercase text-neutral-500">4% Total + 4% Fin.</p>
          <p className="text-xl font-black text-amber-700 mt-1">
            -{formatearUsd(consolidadoCashea.comTotal + consolidadoCashea.comFin)}
          </p>
        </div>
        <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-4">
          <p className="text-[11px] font-bold uppercase text-neutral-500">16% IVA + 2% ISLR</p>
          <p className="text-xl font-black text-amber-700 mt-1">
            -{formatearUsd(consolidadoCashea.iva + consolidadoCashea.islr)}
          </p>
        </div>
        <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-4">
          <p className="text-[11px] font-bold uppercase text-neutral-500">Total Deducciones</p>
          <p className="text-xl font-black text-red-700 mt-1">-{formatearUsd(consolidadoCashea.deducciones)}</p>
        </div>
        <div className="bg-[#FDF0EB] border border-[#E85A28]/30 rounded-2xl p-4">
          <p className="text-[11px] font-bold uppercase text-[#E85A28]">Neto Real Esperado</p>
          <p className="text-xl font-black text-[#191818] mt-1">{formatearUsd(consolidadoCashea.neto)}</p>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2.5 p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}
      {exito && (
        <div className="flex flex-wrap items-center justify-between gap-2.5 p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-sm text-emerald-700">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span>{exito}</span>
          </div>
          {ultimaLiqWa && (
            <button
              type="button"
              onClick={() => {
                void copiarTextoPortapapeles(ultimaLiqWa);
                setExito("Reporte de liquidación Cashea copiado para WhatsApp.");
              }}
              className="inline-flex items-center gap-1 px-3 py-1 rounded-lg bg-emerald-600 text-white text-xs font-bold cursor-pointer"
            >
              <Copy className="w-3.5 h-3.5" />
              Copiar para WhatsApp
            </button>
          )}
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

      <div className="bg-white rounded-2xl border border-slate-200 p-4">
        <BuscadorTabla
          valor={busqueda}
          alCambiar={setBusqueda}
          placeholder="Buscar por nro. de nota, fecha, sucursal, cliente o monto..."
          totalRegistros={cuentas.length}
          totalFiltrados={cuentasFiltradas.length}
        />
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        {cargando ? (
          <div className="p-6 h-24 bg-slate-100 animate-pulse" />
        ) : cuentasFiltradas.length === 0 ? (
          <p className="p-10 text-center text-sm text-slate-500">
            No hay cuotas Cashea que coincidan.
          </p>
        ) : (
          <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-50 border-b border-slate-200 text-[11px] uppercase text-slate-500">
              <tr>
                <th className="px-3 py-3 w-8" />
                <th className="px-3 py-3">Nota / Fecha</th>
                <th className="px-3 py-3">Sucursal / Cliente</th>
                <th className="px-3 py-3 text-right">Regular (USDT / Bs)</th>
                <th className="px-3 py-3 text-right">Financiado</th>
                <th className="px-3 py-3 text-right">4% Tot + 4% Fin</th>
                <th className="px-3 py-3 text-right">IVA 16% + ISLR 2%</th>
                <th className="px-3 py-3 text-right">Deducciones</th>
                <th className="px-3 py-3 text-right">Neto Esperado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 tabular-nums">
              {cuentasFiltradas.map((c) => (
                <tr key={c.venta_id ?? c.id} className="hover:bg-slate-50/70">
                  <td className="px-3 py-3">
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
                  <td className="px-3 py-3">
                    <p className="font-mono font-bold text-[#191818]">{c.numero_venta}</p>
                    <p className="text-[11px] text-neutral-500">{c.fecha_venta}</p>
                  </td>
                  <td className="px-3 py-3">
                    <p className="font-semibold">{c.sucursal}</p>
                    <p className="text-[11px] text-neutral-500">{c.cliente}</p>
                  </td>
                  <td className="px-3 py-3 text-right">
                    <p className="font-bold">{formatearUsd(c.total_regular_usd ?? c.monto_original_usd)}</p>
                    <p className="text-[10px] text-neutral-500">{formatearBs(c.precio_regular_bs ?? 0)}</p>
                  </td>
                  <td className="px-3 py-3 text-right font-bold text-[#191818]">
                    {formatearUsd(c.saldo_pendiente_usd)}
                  </td>
                  <td className="px-3 py-3 text-right text-amber-700">
                    -{formatearUsd((c.comision_cashea_venta_total_usd ?? 0) + (c.comision_cashea_financiado_usd ?? 0))}
                  </td>
                  <td className="px-3 py-3 text-right text-amber-700">
                    -{formatearUsd((c.iva_cashea_usd ?? 0) + (c.islr_cashea_usd ?? 0))}
                  </td>
                  <td className="px-3 py-3 text-right font-bold text-red-700">
                    -{formatearUsd(c.total_deducciones_cashea_usd ?? 0)}
                  </td>
                  <td className="px-3 py-3 text-right font-black text-emerald-700">
                    {formatearUsd(c.neto_esperado_cashea_usd ?? c.saldo_pendiente_usd)}
                  </td>
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
