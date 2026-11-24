"use client";

import React, { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, CheckSquare } from "lucide-react";
import { ErrorApi, formatearUsd, solicitarApi } from "@/servicios/api";
import type {
  CuentaPorCobrarResumen,
  InstrumentoFinanciero,
  PagoBandeja,
} from "@/tipos/finanzas";

export default function PaginaFinanzasPagos() {
  const [pagos, setPagos] = useState<PagoBandeja[]>([]);
  const [cuentas, setCuentas] = useState<CuentaPorCobrarResumen[]>([]);
  const [instrumentos, setInstrumentos] = useState<InstrumentoFinanciero[]>([]);
  const [filtroInst, setFiltroInst] = useState("");
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  const [cxcAbono, setCxcAbono] = useState<CuentaPorCobrarResumen | null>(null);
  const [instAbono, setInstAbono] = useState("");
  const [montoAbono, setMontoAbono] = useState("");
  const [refAbono, setRefAbono] = useState("");

  const cargarDatos = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const qs = filtroInst ? `?instrumento_id=${filtroInst}` : "";
      const [respPagos, respCxc, respInst] = await Promise.all([
        solicitarApi<PagoBandeja[]>(`/api/finanzas/pagos${qs}`),
        solicitarApi<CuentaPorCobrarResumen[]>(
          "/api/finanzas/cuentas-por-cobrar?tipo=CLIENTE&estado=PENDIENTE"
        ),
        solicitarApi<InstrumentoFinanciero[]>("/api/finanzas/instrumentos"),
      ]);
      setPagos(respPagos);
      setCuentas(respCxc);
      setInstrumentos(respInst);
      if (respInst[0] && !instAbono) setInstAbono(String(respInst[0].id));
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "No se pudieron cargar los pagos."
      );
    } finally {
      setCargando(false);
    }
  }, [filtroInst, instAbono]);

  useEffect(() => {
    void cargarDatos();
  }, [cargarDatos]);

  const confirmarPago = async (id: number) => {
    setError(null);
    setExito(null);
    try {
      await solicitarApi(`/api/finanzas/pagos/${id}/confirmar`, {
        method: "PATCH",
        body: JSON.stringify({ aprobado: true }),
      });
      setExito("Pago digital verificado y marcado como CONFIRMADO.");
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "Error al confirmar el pago."
      );
    }
  };

  const registrarAbono = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!cxcAbono) return;
    setError(null);
    setExito(null);
    try {
      await solicitarApi(`/api/finanzas/cuentas-por-cobrar/${cxcAbono.id}/abono`, {
        method: "POST",
        body: JSON.stringify({
          instrumento_id: Number(instAbono),
          monto_moneda_origen: Number(montoAbono),
          referencia: refAbono.trim(),
        }),
      });
      setCxcAbono(null);
      setMontoAbono("");
      setRefAbono("");
      setExito("Abono registrado correctamente.");
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "No se pudo registrar el abono."
      );
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900">
            Verificación de Pagos Digitales y Cuentas por Cobrar
          </h2>
          <p className="text-sm text-slate-500">
            Confirma transferencias, Pago Móvil, Zelle y Binance recibidos, y
            registra abonos de saldos pendientes.
          </p>
        </div>

        <select
          value={filtroInst}
          onChange={(e) => setFiltroInst(e.target.value)}
          className="px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
        >
          <option value="">Todos los instrumentos</option>
          {instrumentos.map((i) => (
            <option key={i.id} value={i.id}>
              {i.nombre}
            </option>
          ))}
        </select>
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

      {/* Bandeja de pagos */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-200 font-bold text-sm">
          Pagos registrados ({pagos.length})
        </div>
        {cargando ? (
          <div className="p-6 h-24 bg-slate-100 animate-pulse" />
        ) : pagos.length === 0 ? (
          <p className="p-8 text-center text-sm text-slate-500">
            No hay pagos registrados.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Fecha / Nota</th>
                  <th className="px-4 py-3">Instrumento</th>
                  <th className="px-4 py-3">Referencia</th>
                  <th className="px-4 py-3 text-right">Monto</th>
                  <th className="px-4 py-3">Verificación</th>
                  <th className="px-4 py-3 text-right">Acción</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {pagos.map((p) => (
                  <tr key={p.id}>
                    <td className="px-4 py-3 text-xs">
                      <p className="font-bold">{p.fecha}</p>
                      <p className="font-mono text-slate-500">
                        {p.numero_venta || p.tipo_documento}
                      </p>
                    </td>
                    <td className="px-4 py-3 font-semibold">{p.instrumento}</td>
                    <td className="px-4 py-3 font-mono text-xs">
                      {p.referencia || "—"}
                    </td>
                    <td className="px-4 py-3 text-right font-bold">
                      {p.monto_moneda_origen.toLocaleString("es-VE", {
                        minimumFractionDigits: 2,
                      })}{" "}
                      {p.moneda}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                          p.estado_verificacion === "CONFIRMADO"
                            ? "bg-emerald-50 text-emerald-700"
                            : "bg-amber-100 text-amber-800"
                        }`}
                      >
                        {p.estado_verificacion}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {p.estado_verificacion === "PENDIENTE" && (
                        <button
                          type="button"
                          onClick={() => void confirmarPago(p.id)}
                          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-bold cursor-pointer"
                        >
                          <CheckSquare className="w-3.5 h-3.5" />
                          Confirmar
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Cuentas por cobrar clientes */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-200 font-bold text-sm">
          Saldos pendientes de clientes ({cuentas.length})
        </div>
        {cuentas.length === 0 ? (
          <p className="p-8 text-center text-sm text-slate-500">
            No hay cuentas por cobrar de clientes pendientes.
          </p>
        ) : (
          <table className="w-full text-sm text-left">
            <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Nota</th>
                <th className="px-4 py-3">Sucursal</th>
                <th className="px-4 py-3">Cliente</th>
                <th className="px-4 py-3 text-right">Saldo Pendiente</th>
                <th className="px-4 py-3 text-right">Acción</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {cuentas.map((c) => (
                <tr key={c.id}>
                  <td className="px-4 py-3 font-mono font-bold">
                    {c.numero_venta}
                  </td>
                  <td className="px-4 py-3">{c.sucursal}</td>
                  <td className="px-4 py-3">{c.cliente}</td>
                  <td className="px-4 py-3 text-right font-black text-[#C9461A]">
                    {formatearUsd(c.saldo_pendiente_usd)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => {
                        setCxcAbono(c);
                        setMontoAbono(String(c.saldo_pendiente_usd));
                      }}
                      className="px-3 py-1.5 rounded-lg bg-[#E85A28] text-white text-xs font-bold cursor-pointer"
                    >
                      Registrar abono
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {cxcAbono && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4">
            <h3 className="text-lg font-black text-slate-900">
              Abono a Nota {cxcAbono.numero_venta}
            </h3>
            <form onSubmit={registrarAbono} className="space-y-3">
              <select
                value={instAbono}
                onChange={(e) => setInstAbono(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
              >
                {instrumentos.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.nombre} ({i.moneda})
                  </option>
                ))}
              </select>
              <input
                type="number"
                step="0.01"
                min="0.01"
                required
                value={montoAbono}
                onChange={(e) => setMontoAbono(e.target.value)}
                placeholder="Monto en moneda del instrumento"
                className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
              />
              <input
                type="text"
                value={refAbono}
                onChange={(e) => setRefAbono(e.target.value)}
                placeholder="Referencia"
                className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
              />
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setCxcAbono(null)}
                  className="px-4 py-2 rounded-xl border border-slate-300 text-sm font-semibold cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-xl bg-[#E85A28] text-white text-sm font-bold cursor-pointer"
                >
                  Guardar abono
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
