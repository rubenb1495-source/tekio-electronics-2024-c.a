"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, CheckCircle2, CheckSquare, Copy } from "lucide-react";
import BuscadorTabla from "@/componentes/BuscadorTabla";
import { usarSesion } from "@/contexto/SesionContexto";
import {
  copiarTextoPortapapeles,
  formatearWhatsAppPago,
} from "@/lib/whatsapp";
import { ErrorApi, fechaHoyCaracas, formatearUsd, solicitarApi } from "@/servicios/api";
import type { TasaHoy } from "@/tipos/dominio";
import type {
  CuentaPorCobrarResumen,
  InstrumentoFinanciero,
  PagoBandeja,
} from "@/tipos/finanzas";

export default function PaginaFinanzasPagos() {
  const { usuario } = usarSesion();
  const [pagos, setPagos] = useState<PagoBandeja[]>([]);
  const [cuentas, setCuentas] = useState<CuentaPorCobrarResumen[]>([]);
  const [instrumentos, setInstrumentos] = useState<InstrumentoFinanciero[]>([]);
  const [tasaHoy, setTasaHoy] = useState<TasaHoy | null>(null);
  const [filtroInst, setFiltroInst] = useState("");
  const [busqueda, setBusqueda] = useState("");
  const [copiadoPagoId, setCopiadoPagoId] = useState<number | null>(null);
  const [ultimoAbonoWa, setUltimoAbonoWa] = useState<string | null>(null);
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
      const [respPagos, respCxc, respInst, respTasa] = await Promise.all([
        solicitarApi<PagoBandeja[]>(`/api/finanzas/pagos${qs}`),
        solicitarApi<CuentaPorCobrarResumen[]>(
          "/api/finanzas/cuentas-por-cobrar?tipo=CLIENTE&estado=PENDIENTE"
        ),
        solicitarApi<InstrumentoFinanciero[]>("/api/finanzas/instrumentos"),
        solicitarApi<TasaHoy>("/api/tasas/hoy").catch(() => null),
      ]);
      setPagos(respPagos);
      setCuentas(respCxc);
      setInstrumentos(respInst);
      setTasaHoy(respTasa);
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
      const instObj = instrumentos.find((i) => String(i.id) === instAbono);
      const montoNum = Number(montoAbono);
      const usdNom =
        instObj?.moneda === "BS" && tasaHoy?.tasa_bcv
          ? montoNum / tasaHoy.tasa_bcv
          : montoNum;
      const textoWa = formatearWhatsAppPago({
        tipo_movimiento: "INGRESO",
        tipo_documento: "ABONO",
        fecha: fechaHoyCaracas(),
        instrumento: instObj?.nombre || "Instrumento",
        monto_moneda_origen: montoNum,
        moneda: instObj?.moneda || "USD",
        usd_nominal: usdNom,
        tasa_bcv: tasaHoy?.tasa_bcv ?? null,
        tasa_usdt: tasaHoy?.tasa_usdt ?? null,
        referencia: refAbono.trim(),
        cliente_o_venta: `${cxcAbono.numero_venta} · ${cxcAbono.cliente}`,
        estado_verificacion: instObj?.requiere_verificacion
          ? "PENDIENTE"
          : "CONFIRMADO",
        usuario: usuario?.nombre || "Administración",
      });
      setUltimoAbonoWa(textoWa);
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

  const pagosFiltrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return pagos;
    return pagos.filter((p) =>
      [
        p.fecha,
        p.numero_venta || "",
        p.tipo_documento,
        p.instrumento || "",
        p.referencia || "",
        p.estado_verificacion,
        String(p.monto_moneda_origen),
      ]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [pagos, busqueda]);

  const cuentasFiltradas = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return cuentas;
    return cuentas.filter((c) =>
      [
        c.numero_venta || "",
        c.sucursal || "",
        c.cliente || "",
        String(c.saldo_pendiente_usd),
      ]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [cuentas, busqueda]);

  const copiarPagoWa = async (p: PagoBandeja) => {
    const txt = formatearWhatsAppPago(p, {
      tasa_bcv: tasaHoy?.tasa_bcv ?? null,
      tasa_usdt: tasaHoy?.tasa_usdt ?? null,
      usuario: p.verificado_por || usuario?.nombre || "Administración",
    });
    await copiarTextoPortapapeles(txt);
    setCopiadoPagoId(p.id);
    setExito(`Movimiento #${p.id} copiado para WhatsApp.`);
    setTimeout(
      () => setCopiadoPagoId((prev) => (prev === p.id ? null : prev)),
      2500
    );
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
        <div className="flex flex-wrap items-center justify-between gap-2.5 p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-sm text-emerald-700">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span>{exito}</span>
          </div>
          {ultimoAbonoWa && (
            <button
              type="button"
              onClick={() => {
                void copiarTextoPortapapeles(ultimoAbonoWa);
                setExito("Comprobante del abono copiado para WhatsApp.");
              }}
              className="inline-flex items-center gap-1 px-3 py-1 rounded-lg bg-emerald-600 text-white text-xs font-bold cursor-pointer"
            >
              <Copy className="w-3.5 h-3.5" />
              Copiar abono para WhatsApp
            </button>
          )}
        </div>
      )}

      <div className="bg-white rounded-2xl border border-slate-200 p-4">
        <BuscadorTabla
          valor={busqueda}
          alCambiar={setBusqueda}
          placeholder="Buscar por referencia, instrumento/banco, cliente, nro. de venta o monto..."
          totalRegistros={pagos.length}
          totalFiltrados={pagosFiltrados.length}
        />
      </div>

      {/* Bandeja de pagos */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-200 font-bold text-sm">
          Pagos registrados ({pagosFiltrados.length})
        </div>
        {cargando ? (
          <div className="p-6 h-24 bg-slate-100 animate-pulse" />
        ) : pagosFiltrados.length === 0 ? (
          <p className="p-8 text-center text-sm text-slate-500">
            No hay pagos que coincidan.
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
                {pagosFiltrados.map((p) => (
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
                    <td className="px-4 py-3 text-right space-x-1.5 whitespace-nowrap">
                      <button
                        type="button"
                        onClick={() => void copiarPagoWa(p)}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-emerald-300 bg-emerald-50 text-emerald-800 text-xs font-bold cursor-pointer"
                      >
                        <Copy className="w-3.5 h-3.5" />
                        {copiadoPagoId === p.id ? "¡Copiado!" : "WhatsApp"}
                      </button>
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
          Saldos pendientes de clientes ({cuentasFiltradas.length})
        </div>
        {cuentasFiltradas.length === 0 ? (
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
              {cuentasFiltradas.map((c) => (
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
