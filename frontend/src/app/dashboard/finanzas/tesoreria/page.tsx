"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowLeftRight,
  Check,
  CheckCircle2,
  Copy,
} from "lucide-react";
import BuscadorTabla from "@/componentes/BuscadorTabla";
import { usarSesion } from "@/contexto/SesionContexto";
import { copiarTextoPortapapeles } from "@/lib/whatsapp";
import {
  ErrorApi,
  fechaHoyCaracas,
  formatearBs,
  formatearUsd,
  solicitarApi,
} from "@/servicios/api";
import type { InstrumentoFinanciero } from "@/tipos/finanzas";

interface MovimientoTesoreriaResumen {
  id: number;
  codigo: string;
  tipo: "TRANSFERENCIA" | "CAMBIO_DIVISA";
  fecha: string;
  instrumento_origen_id: number;
  instrumento_origen: string;
  monto_origen: number;
  moneda_origen: string;
  instrumento_destino_id: number;
  instrumento_destino: string;
  monto_destino: number;
  moneda_destino: string;
  tasa_pactada: number;
  tasa_referencia_bcv: number;
  tasa_referencia_usdt: number;
  diferencia_usd: number;
  diferencia_pct: number;
  referencia: string;
  notas: string;
  usuario: string;
}

export default function PaginaTesoreriaDivisas() {
  const { tasaHoy } = usarSesion();
  const [instrumentos, setInstrumentos] = useState<InstrumentoFinanciero[]>([]);
  const [movimientos, setMovimientos] = useState<MovimientoTesoreriaResumen[]>([]);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);
  const [busqueda, setBusqueda] = useState("");
  const [copiadoId, setCopiadoId] = useState<number | null>(null);

  // Formulario
  const [tipo, setTipo] = useState<"TRANSFERENCIA" | "CAMBIO_DIVISA">("CAMBIO_DIVISA");
  const [fecha, setFecha] = useState(fechaHoyCaracas());
  const [origenId, setOrigenId] = useState("");
  const [montoOrigen, setMontoOrigen] = useState("");
  const [destinoId, setDestinoId] = useState("");
  const [montoDestino, setMontoDestino] = useState("");
  const [tasaPactada, setTasaPactada] = useState("");
  const [referencia, setReferencia] = useState("");
  const [notas, setNotas] = useState("");

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [insts, movs] = await Promise.all([
        solicitarApi<InstrumentoFinanciero[]>("/api/finanzas/instrumentos"),
        solicitarApi<MovimientoTesoreriaResumen[]>("/api/finanzas/tesoreria"),
      ]);
      setInstrumentos(insts);
      setMovimientos(movs);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo cargar el módulo de Tesorería."
      );
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const instOrig = instrumentos.find((i) => String(i.id) === origenId);
  const instDest = instrumentos.find((i) => String(i.id) === destinoId);

  // Vista previa en vivo del diferencial cambiario
  const previewDiferencial = useMemo(() => {
    if (tipo !== "CAMBIO_DIVISA" || !instOrig || !instDest) return null;
    const mOrig = Number(montoOrigen || 0);
    const mDest = Number(montoDestino || 0);
    if (mOrig <= 0 || mDest <= 0) return null;

    const tasaRef = Number(tasaHoy?.tasa_usdt || tasaHoy?.tasa_bcv || 0);
    const esBsOrig = instOrig.moneda === "BS";
    const esBsDest = instDest.moneda === "BS";

    let difUsd = 0;
    let difPct = 0;
    if (esBsOrig && !esBsDest && tasaRef > 0) {
      const entregadoUsd = mOrig / tasaRef;
      difUsd = mDest - entregadoUsd;
      difPct = entregadoUsd > 0 ? (difUsd / entregadoUsd) * 100 : 0;
    } else if (!esBsOrig && esBsDest && tasaRef > 0) {
      const recibidoUsd = mDest / tasaRef;
      difUsd = recibidoUsd - mOrig;
      difPct = (difUsd / mOrig) * 100;
    } else if (!esBsOrig && !esBsDest) {
      difUsd = mDest - mOrig;
      difPct = (difUsd / mOrig) * 100;
    } else {
      return null;
    }
    return {
      difUsd: Number(difUsd.toFixed(2)),
      difPct: Number(difPct.toFixed(2)),
    };
  }, [tipo, instOrig, instDest, montoOrigen, montoDestino, tasaHoy]);

  const registrar = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setExito(null);
    setGuardando(true);
    try {
      const creado = await solicitarApi<MovimientoTesoreriaResumen>(
        "/api/finanzas/tesoreria",
        {
          method: "POST",
          body: JSON.stringify({
            tipo,
            fecha,
            instrumento_origen_id: Number(origenId),
            monto_origen: Number(montoOrigen),
            instrumento_destino_id: Number(destinoId),
            monto_destino: Number(montoDestino),
            tasa_pactada: Number(tasaPactada || 0),
            referencia: referencia.trim(),
            notas: notas.trim(),
          }),
        }
      );
      setExito(`Movimiento ${creado.codigo} registrado atómicamente en ambas cuentas.`);
      setMontoOrigen("");
      setMontoDestino("");
      setTasaPactada("");
      setReferencia("");
      setNotas("");
      await cargar();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo registrar el movimiento de tesorería."
      );
    } finally {
      setGuardando(false);
    }
  };

  const copiarWa = async (m: MovimientoTesoreriaResumen) => {
    const origTxt =
      m.moneda_origen === "BS"
        ? formatearBs(m.monto_origen)
        : `${formatearUsd(m.monto_origen)} ${m.moneda_origen}`;
    const destTxt =
      m.moneda_destino === "BS"
        ? formatearBs(m.monto_destino)
        : `${formatearUsd(m.monto_destino)} ${m.moneda_destino}`;
    const texto = [
      `💱 *TESORERÍA · TEKIO ELECTRONICS (${m.codigo})*`,
      `📅 Fecha: *${m.fecha}* · Tipo: *${m.tipo === "CAMBIO_DIVISA" ? "Cambio de Divisa" : "Transferencia"}*`,
      `📤 Salida: *${m.instrumento_origen}* — ${origTxt}`,
      `📥 Entrada: *${m.instrumento_destino}* — ${destTxt}`,
      m.tipo === "CAMBIO_DIVISA"
        ? `📊 Tasa pactada: *${m.tasa_pactada.toFixed(2)}* · Diferencial: *${m.diferencia_usd >= 0 ? "+" : ""}${formatearUsd(m.diferencia_usd)} (${m.diferencia_pct >= 0 ? "+" : ""}${m.diferencia_pct.toFixed(2)}%)*`
        : "",
      m.referencia ? `🔖 Ref: ${m.referencia}` : "",
      m.notas ? `📝 Notas: ${m.notas}` : "",
    ]
      .filter(Boolean)
      .join("\n");
    await copiarTextoPortapapeles(texto);
    setCopiadoId(m.id);
    setTimeout(() => setCopiadoId(null), 2000);
  };

  const filtrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return movimientos;
    return movimientos.filter((m) =>
      [m.codigo, m.tipo, m.instrumento_origen, m.instrumento_destino, m.referencia, m.notas]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [movimientos, busqueda]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-black text-[#191818] flex items-center gap-2">
          <ArrowLeftRight className="w-6 h-6 text-[#E85A28]" />
          Tesorería · Traslados y Cambios de Divisa
        </h2>
        <p className="text-sm text-neutral-500">
          Mueve fondos entre cuentas o registra cambios de divisa con cálculo automático de ganancia o pérdida cambiaria.
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-4 rounded-2xl bg-red-50 border border-red-200 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}
      {exito && (
        <div className="flex items-center gap-2 p-4 rounded-2xl bg-emerald-50 border border-emerald-200 text-sm text-emerald-800">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{exito}</span>
        </div>
      )}

      {/* Formulario interactivo */}
      <form
        onSubmit={registrar}
        className="bg-white/80 backdrop-blur-md border border-white/70 rounded-2xl p-5 shadow-[0_8px_30px_rgb(0,0,0,0.04)] space-y-4"
      >
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div>
            <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
              Operación
            </label>
            <select
              value={tipo}
              onChange={(e) => setTipo(e.target.value as "TRANSFERENCIA" | "CAMBIO_DIVISA")}
              className="w-full px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm font-bold"
            >
              <option value="CAMBIO_DIVISA">Cambio de Divisa</option>
              <option value="TRANSFERENCIA">Transferencia (Misma Moneda)</option>
            </select>
          </div>
          <div>
            <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
              Fecha
            </label>
            <input
              type="date"
              required
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm"
            />
          </div>
          <div>
            <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
              Cuenta Origen (Salida)
            </label>
            <select
              required
              value={origenId}
              onChange={(e) => setOrigenId(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm"
            >
              <option value="">Seleccionar...</option>
              {instrumentos.map((i) => (
                <option key={i.id} value={String(i.id)}>
                  {i.nombre} ({i.moneda})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
              Monto Salida ({instOrig?.moneda || "—"})
            </label>
            <input
              type="number"
              step="0.01"
              min="0.01"
              required
              value={montoOrigen}
              onChange={(e) => setMontoOrigen(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm tabular-nums"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div>
            <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
              Cuenta Destino (Entrada)
            </label>
            <select
              required
              value={destinoId}
              onChange={(e) => setDestinoId(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm"
            >
              <option value="">Seleccionar...</option>
              {instrumentos.map((i) => (
                <option key={i.id} value={String(i.id)}>
                  {i.nombre} ({i.moneda})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
              Monto Entrada ({instDest?.moneda || "—"})
            </label>
            <input
              type="number"
              step="0.01"
              min="0.01"
              required
              value={montoDestino}
              onChange={(e) => setMontoDestino(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm tabular-nums"
            />
          </div>
          <div>
            <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
              Tasa Pactada (Opcional)
            </label>
            <input
              type="number"
              step="0.0001"
              min="0"
              value={tasaPactada}
              onChange={(e) => setTasaPactada(e.target.value)}
              placeholder="Auto si vacío"
              className="w-full px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm tabular-nums"
            />
          </div>
          <div>
            <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
              Referencia
            </label>
            <input
              type="text"
              value={referencia}
              onChange={(e) => setReferencia(e.target.value)}
              placeholder="Nro. ref / comprobante"
              className="w-full px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm"
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <div className="flex-1 min-w-[220px]">
            <input
              type="text"
              value={notas}
              onChange={(e) => setNotas(e.target.value)}
              placeholder="Observaciones de la operación..."
              className="w-full px-3 py-2 rounded-xl border border-neutral-200 bg-white text-xs"
            />
          </div>

          {previewDiferencial && (
            <div
              className={`px-3.5 py-2 rounded-xl text-xs font-black tabular-nums border ${
                previewDiferencial.difUsd >= 0
                  ? "bg-emerald-50 border-emerald-200 text-emerald-700"
                  : "bg-red-50 border-red-200 text-red-700"
              }`}
            >
              {previewDiferencial.difUsd >= 0 ? "Ganancia" : "Pérdida"} cambiaria:{" "}
              {previewDiferencial.difUsd >= 0 ? "+" : ""}
              {formatearUsd(previewDiferencial.difUsd)} (
              {previewDiferencial.difPct >= 0 ? "+" : ""}
              {previewDiferencial.difPct.toFixed(2)}%)
            </div>
          )}

          <button
            type="submit"
            disabled={guardando}
            className="px-5 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] text-white text-xs font-bold cursor-pointer disabled:opacity-50"
          >
            {guardando ? "Registrando..." : "Registrar Movimiento"}
          </button>
        </div>
      </form>

      {/* Historial */}
      <div className="bg-white/80 backdrop-blur-md border border-white/70 rounded-2xl p-5 shadow-[0_8px_30px_rgb(0,0,0,0.04)] space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-base font-bold text-[#191818]">
            Historial de Tesorería ({filtrados.length})
          </h3>
          <div className="w-full sm:w-80">
            <BuscadorTabla
              valor={busqueda}
              alCambiar={setBusqueda}
              placeholder="Buscar por código, cuenta o referencia..."
            />
          </div>
        </div>

        {cargando ? (
          <div className="h-24 rounded-xl bg-neutral-100 animate-pulse" />
        ) : filtrados.length === 0 ? (
          <p className="text-sm text-neutral-500 py-6 text-center">
            No hay movimientos de tesorería registrados.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-neutral-50 border-b border-neutral-200 uppercase text-[10px] text-neutral-500">
                <tr>
                  <th className="px-3 py-2.5">Código / Fecha</th>
                  <th className="px-3 py-2.5">Origen → Destino</th>
                  <th className="px-3 py-2.5 text-right">Salida</th>
                  <th className="px-3 py-2.5 text-right">Entrada</th>
                  <th className="px-3 py-2.5 text-right">Diferencial</th>
                  <th className="px-3 py-2.5 text-right">WhatsApp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100 tabular-nums">
                {filtrados.map((m) => (
                  <tr key={m.id} className="hover:bg-white/60">
                    <td className="px-3 py-2.5">
                      <p className="font-mono font-bold text-[#191818]">{m.codigo}</p>
                      <p className="text-[11px] text-neutral-500">
                        {m.fecha} · {m.tipo === "CAMBIO_DIVISA" ? "Cambio" : "Traslado"}
                      </p>
                    </td>
                    <td className="px-3 py-2.5">
                      <p className="font-semibold text-[#191818]">
                        {m.instrumento_origen} → {m.instrumento_destino}
                      </p>
                      <p className="text-[11px] text-neutral-500">
                        {m.referencia || "—"} {m.notas ? `· ${m.notas}` : ""}
                      </p>
                    </td>
                    <td className="px-3 py-2.5 text-right font-semibold text-red-700">
                      {m.moneda_origen === "BS"
                        ? formatearBs(m.monto_origen)
                        : formatearUsd(m.monto_origen)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-semibold text-emerald-700">
                      {m.moneda_destino === "BS"
                        ? formatearBs(m.monto_destino)
                        : formatearUsd(m.monto_destino)}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {m.tipo === "CAMBIO_DIVISA" ? (
                        <span
                          className={`inline-block px-2 py-0.5 rounded-full font-black text-[11px] ${
                            m.diferencia_usd >= 0
                              ? "bg-emerald-50 text-emerald-700"
                              : "bg-red-50 text-red-700"
                          }`}
                        >
                          {m.diferencia_usd >= 0 ? "+" : ""}
                          {formatearUsd(m.diferencia_usd)} ({m.diferencia_pct >= 0 ? "+" : ""}
                          {m.diferencia_pct.toFixed(2)}%)
                        </span>
                      ) : (
                        <span className="text-neutral-400">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <button
                        type="button"
                        onClick={() => void copiarWa(m)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-800 font-bold cursor-pointer"
                      >
                        {copiadoId === m.id ? (
                          <Check className="w-3.5 h-3.5" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                        {copiadoId === m.id ? "¡Copiado!" : "Copiar"}
                      </button>
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
