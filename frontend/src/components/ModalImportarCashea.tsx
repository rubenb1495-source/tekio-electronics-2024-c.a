"use client";

import React, { useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  FileSpreadsheet,
  Upload,
  X,
} from "lucide-react";
import {
  ErrorApi,
  fechaHoyCaracas,
  formatearUsd,
  solicitarApi,
  subirArchivoApi,
} from "@/servicios/api";
import type {
  CasheaPreviewRespuesta,
  InstrumentoFinanciero,
} from "@/tipos/finanzas";

interface ModalImportarCasheaProps {
  abierto: boolean;
  instrumentos: InstrumentoFinanciero[];
  alCerrar: () => void;
  alConfirmarExito: (mensaje: string) => void;
}

export default function ModalImportarCashea({
  abierto,
  instrumentos,
  alCerrar,
  alConfirmarExito,
}: ModalImportarCasheaProps) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [preview, setPreview] = useState<CasheaPreviewRespuesta | null>(null);
  const [seleccionados, setSeleccionados] = useState<number[]>([]);
  const [destinoId, setDestinoId] = useState<string>("");
  const [fechaDeposito, setFechaDeposito] = useState<string>(fechaHoyCaracas());
  const [referenciaBancaria, setReferenciaBancaria] = useState<string>("");
  const [colOrdenOverride, setColOrdenOverride] = useState<string>("");
  const [colNetoOverride, setColNetoOverride] = useState<string>("");
  const [analizando, setAnalizando] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const destinoEfectivo =
    destinoId || (instrumentos[0] ? String(instrumentos[0].id) : "");

  const filasListasSeleccionadas = useMemo(() => {
    if (!preview) return [];
    return preview.filas.filter(
      (f) =>
        f.estado_cruce === "LISTA_PARA_CONCILIAR" &&
        f.venta_id !== null &&
        seleccionados.includes(f.venta_id)
    );
  }, [preview, seleccionados]);

  const totalesSeleccion = useMemo(() => {
    return filasListasSeleccionadas.reduce(
      (acc, f) => ({
        pagado: acc.pagado + (f.monto_pagado_real_usd || 0),
        descuento: acc.descuento + (f.descuento_real_usd || 0),
        esperado: acc.esperado + (f.neto_esperado_tekio_usd || 0),
        diferencia: acc.diferencia + (f.diferencia_usd || 0),
      }),
      { pagado: 0, descuento: 0, esperado: 0, diferencia: 0 }
    );
  }, [filasListasSeleccionadas]);

  if (!abierto) return null;

  const analizarArchivo = async (
    archivoObjetivo: File,
    overrides?: { colOrden?: string; colNeto?: string }
  ) => {
    setAnalizando(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("archivo", archivoObjetivo);
      if (overrides?.colOrden) fd.append("col_orden", overrides.colOrden);
      if (overrides?.colNeto) fd.append("col_neto", overrides.colNeto);

      const resp = await subirArchivoApi<CasheaPreviewRespuesta>(
        "/api/finanzas/cashea/importar-reporte/preview",
        fd
      );
      setPreview(resp);
      setColOrdenOverride(resp.mapeo_detectado.col_orden || "");
      setColNetoOverride(resp.mapeo_detectado.col_neto || "");
      const idsListos = resp.filas
        .filter((f) => f.estado_cruce === "LISTA_PARA_CONCILIAR" && f.venta_id !== null)
        .map((f) => f.venta_id as number);
      setSeleccionados(idsListos);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo leer el reporte de Cashea."
      );
    } finally {
      setAnalizando(false);
    }
  };

  const manejarConfirmar = async () => {
    if (!preview || filasListasSeleccionadas.length === 0) {
      setError("Selecciona al menos una orden lista para conciliar.");
      return;
    }
    if (!destinoEfectivo) {
      setError("Selecciona el banco o instrumento destino donde ingresó el depósito.");
      return;
    }
    setConfirmando(true);
    setError(null);
    try {
      const resp = await solicitarApi<{
        lote_id: number;
        asiento_id: number;
        notas_conciliadas: number;
        total_pagado_real_usd: number;
        total_descuento_real_usd: number;
      }>("/api/finanzas/cashea/importar-reporte/confirmar", {
        method: "POST",
        body: JSON.stringify({
          nombre_archivo: preview.nombre_archivo,
          instrumento_destino_id: Number(destinoEfectivo),
          fecha_deposito: fechaDeposito,
          referencia_bancaria: referenciaBancaria.trim(),
          ordenes: filasListasSeleccionadas.map((f) => ({
            venta_id: f.venta_id,
            cashea_numero_orden: f.cashea_numero_orden,
            monto_pagado_real_usd: f.monto_pagado_real_usd,
            descuento_real_usd: f.descuento_real_usd,
          })),
        }),
      });
      setArchivo(null);
      setPreview(null);
      setSeleccionados([]);
      setReferenciaBancaria("");
      alConfirmarExito(
        `Lote Cashea #${resp.lote_id} conciliado: ${resp.notas_conciliadas} nota(s) liquidadas · Ingreso real ${formatearUsd(resp.total_pagado_real_usd)} · Asiento #${resp.asiento_id}.`
      );
      alCerrar();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo confirmar la liquidación Cashea."
      );
    } finally {
      setConfirmando(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="w-full max-w-5xl max-h-[92vh] rounded-3xl bg-white/95 backdrop-blur-xl border border-white/70 shadow-2xl flex flex-col overflow-hidden">
        {/* Cabecera */}
        <div className="px-6 py-4 border-b border-neutral-200/80 flex items-center justify-between bg-[#F6F6F6]/80">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-[#FDF0EB] text-[#E85A28] flex items-center justify-center">
              <FileSpreadsheet className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-black text-[#191818]">
                Cargar Reporte Cashea (Liquidación y Conciliación en Lote)
              </h3>
              <p className="text-xs text-neutral-500">
                Sube el archivo .xlsx o .csv de Cashea Merchant Web para cruzar órdenes, ver diferencias y registrar el ingreso en banco.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={alCerrar}
            className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100 cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Cuerpo scrollable */}
        <div className="p-6 overflow-y-auto space-y-5 flex-1">
          {error && (
            <div className="flex items-start gap-2.5 p-3.5 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700 font-medium">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {/* Paso 1: Zona de carga */}
          <div className="rounded-2xl border-2 border-dashed border-neutral-300 bg-[#F6F6F6]/60 p-5 flex flex-wrap items-center justify-between gap-4">
            <div className="space-y-1">
              <p className="text-xs font-black uppercase tracking-wider text-[#191818]">
                Paso 1 · Archivo de Cashea Merchant Web (.xlsx / .csv)
              </p>
              <p className="text-xs text-neutral-500">
                {archivo
                  ? `Archivo cargado: ${archivo.name}`
                  : "Detección automática de Nro. de Orden, Bruto, Pagado Real y Comisiones/Retenciones."}
              </p>
            </div>
            <label className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#D14D20] text-white text-xs font-bold cursor-pointer">
              <Upload className="w-4 h-4 text-white" />
              <span>{analizando ? "Analizando..." : archivo ? "Cambiar archivo" : "Seleccionar .xlsx / .csv"}</span>
              <input
                type="file"
                accept=".xlsx,.csv"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) {
                    setArchivo(f);
                    void analizarArchivo(f);
                  }
                }}
              />
            </label>
          </div>

          {preview && (
            <>
              {/* Mapeo rápido opcional si el usuario desea ajustar columnas */}
              {preview.encabezados_detectados.length > 0 && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 bg-white border border-neutral-200 rounded-2xl p-3.5 items-end text-xs">
                  <div>
                    <label className="block font-bold text-neutral-600 mb-1">
                      Columna Nro. de Orden
                    </label>
                    <select
                      value={colOrdenOverride}
                      onChange={(e) => setColOrdenOverride(e.target.value)}
                      className="w-full px-2.5 py-1.5 rounded-lg border border-neutral-300 bg-white text-xs"
                    >
                      {preview.encabezados_detectados.map((h) => (
                        <option key={h} value={h}>
                          {h}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block font-bold text-neutral-600 mb-1">
                      Columna Pagado Real / Neto
                    </label>
                    <select
                      value={colNetoOverride}
                      onChange={(e) => setColNetoOverride(e.target.value)}
                      className="w-full px-2.5 py-1.5 rounded-lg border border-neutral-300 bg-white text-xs"
                    >
                      <option value="">(Detección automática)</option>
                      {preview.encabezados_detectados.map((h) => (
                        <option key={h} value={h}>
                          {h}
                        </option>
                      ))}
                    </select>
                  </div>
                  <button
                    type="button"
                    disabled={!archivo || analizando}
                    onClick={() =>
                      archivo &&
                      void analizarArchivo(archivo, {
                        colOrden: colOrdenOverride,
                        colNeto: colNetoOverride || undefined,
                      })
                    }
                    className="px-3 py-2 rounded-lg border border-neutral-300 bg-neutral-50 hover:bg-neutral-100 text-xs font-bold text-[#191818] cursor-pointer"
                  >
                    Re-aplicar mapeo
                  </button>
                </div>
              )}

              {/* KPIs de Vista Previa */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 tabular-nums">
                <div className="rounded-2xl bg-emerald-50 border border-emerald-200 p-3.5">
                  <p className="text-[10px] font-bold uppercase text-emerald-700">
                    Total a Cobrar Real ({filasListasSeleccionadas.length} notas)
                  </p>
                  <p className="text-lg font-black text-emerald-900 mt-0.5">
                    {formatearUsd(totalesSeleccion.pagado)}
                  </p>
                </div>
                <div className="rounded-2xl bg-amber-50 border border-amber-200 p-3.5">
                  <p className="text-[10px] font-bold uppercase text-amber-800">
                    Descuentos Reales Cashea
                  </p>
                  <p className="text-lg font-black text-amber-900 mt-0.5">
                    -{formatearUsd(totalesSeleccion.descuento)}
                  </p>
                </div>
                <div className="rounded-2xl bg-white border border-neutral-200 p-3.5">
                  <p className="text-[10px] font-bold uppercase text-neutral-500">
                    Neto Esperado Tekio
                  </p>
                  <p className="text-lg font-black text-[#191818] mt-0.5">
                    {formatearUsd(totalesSeleccion.esperado)}
                  </p>
                </div>
                <div
                  className={`rounded-2xl border p-3.5 ${
                    Math.abs(totalesSeleccion.diferencia) < 0.01
                      ? "bg-emerald-50/70 border-emerald-200"
                      : "bg-red-50 border-red-200"
                  }`}
                >
                  <p className="text-[10px] font-bold uppercase text-neutral-600">
                    Diferencia Neta
                  </p>
                  <p
                    className={`text-lg font-black mt-0.5 ${
                      Math.abs(totalesSeleccion.diferencia) < 0.01
                        ? "text-emerald-700"
                        : "text-red-700"
                    }`}
                  >
                    {totalesSeleccion.diferencia >= 0 ? "+" : ""}
                    {formatearUsd(totalesSeleccion.diferencia)}
                  </p>
                </div>
              </div>

              {/* Resumen de clasificación */}
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-bold">
                  Listas: {preview.resumen.listas_para_conciliar}
                </span>
                <span className="px-2.5 py-1 rounded-full bg-neutral-100 text-neutral-700 border border-neutral-200 font-bold">
                  Ya conciliadas: {preview.resumen.ya_conciliadas}
                </span>
                <span className="px-2.5 py-1 rounded-full bg-red-50 text-red-700 border border-red-200 font-bold">
                  No encontradas: {preview.resumen.no_encontradas}
                </span>
              </div>

              {/* Tabla comparativa */}
              <div className="rounded-2xl border border-neutral-200 overflow-hidden bg-white">
                <div className="overflow-x-auto max-h-64">
                  <table className="w-full text-xs text-left">
                    <thead className="bg-neutral-50 border-b border-neutral-200 text-[10px] uppercase text-neutral-500 sticky top-0">
                      <tr>
                        <th className="px-3 py-2.5 w-8" />
                        <th className="px-3 py-2.5">Estado</th>
                        <th className="px-3 py-2.5">Nro. Orden / Nota</th>
                        <th className="px-3 py-2.5 text-right">Neto Esp. Tekio</th>
                        <th className="px-3 py-2.5 text-right">Pagado Real</th>
                        <th className="px-3 py-2.5 text-right">Desc. Esp. / Real</th>
                        <th className="px-3 py-2.5 text-right">Diferencia</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-neutral-100 tabular-nums">
                      {preview.filas.map((f) => {
                        const esLista =
                          f.estado_cruce === "LISTA_PARA_CONCILIAR" &&
                          f.venta_id !== null;
                        const diff = f.diferencia_usd ?? 0;
                        return (
                          <tr
                            key={`${f.fila_archivo}-${f.cashea_numero_orden}`}
                            className={esLista ? "hover:bg-neutral-50" : "bg-neutral-50/50 opacity-75"}
                          >
                            <td className="px-3 py-2.5">
                              {esLista && (
                                <input
                                  type="checkbox"
                                  checked={seleccionados.includes(f.venta_id as number)}
                                  onChange={() =>
                                    setSeleccionados((prev) =>
                                      prev.includes(f.venta_id as number)
                                        ? prev.filter((x) => x !== f.venta_id)
                                        : [...prev, f.venta_id as number]
                                    )
                                  }
                                />
                              )}
                            </td>
                            <td className="px-3 py-2.5">
                              <span
                                className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                                  f.estado_cruce === "LISTA_PARA_CONCILIAR"
                                    ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                                    : f.estado_cruce === "YA_CONCILIADA"
                                    ? "bg-neutral-100 text-neutral-600 border-neutral-200"
                                    : "bg-red-50 text-red-700 border-red-200"
                                }`}
                              >
                                {f.estado_cruce === "LISTA_PARA_CONCILIAR"
                                  ? "Lista"
                                  : f.estado_cruce === "YA_CONCILIADA"
                                  ? "Ya conciliada"
                                  : "No encontrada"}
                              </span>
                            </td>
                            <td className="px-3 py-2.5">
                              <p className="font-mono font-bold text-[#191818]">
                                {f.cashea_numero_orden}
                              </p>
                              <p className="text-[10px] text-neutral-500">
                                {f.numero_venta
                                  ? `${f.numero_venta} · ${f.cliente || ""}`
                                  : "Sin nota vinculada en Tekio"}
                              </p>
                            </td>
                            <td className="px-3 py-2.5 text-right font-semibold">
                              {f.neto_esperado_tekio_usd !== null
                                ? formatearUsd(f.neto_esperado_tekio_usd)
                                : "—"}
                            </td>
                            <td className="px-3 py-2.5 text-right font-bold text-emerald-700">
                              {formatearUsd(f.monto_pagado_real_usd)}
                            </td>
                            <td className="px-3 py-2.5 text-right text-amber-700">
                              {f.descuento_esperado_tekio_usd !== null
                                ? `${formatearUsd(f.descuento_esperado_tekio_usd)} / `
                                : ""}
                              <strong>{formatearUsd(f.descuento_real_usd)}</strong>
                            </td>
                            <td className="px-3 py-2.5 text-right font-black">
                              {f.diferencia_usd !== null ? (
                                <span
                                  className={
                                    Math.abs(diff) < 0.01
                                      ? "text-emerald-700"
                                      : "text-red-700"
                                  }
                                >
                                  {diff >= 0 ? "+" : ""}
                                  {formatearUsd(diff)}
                                </span>
                              ) : (
                                "—"
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Paso 2: Destino bancario y confirmación */}
              <div className="rounded-2xl border border-[#E85A28]/30 bg-[#FDF0EB]/40 p-4 grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
                <div>
                  <label className="block text-xs font-bold text-[#191818] mb-1">
                    Banco / Instrumento donde ingresó el dinero *
                  </label>
                  <select
                    value={destinoEfectivo}
                    onChange={(e) => setDestinoId(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-xs font-semibold"
                  >
                    {instrumentos.map((i) => (
                      <option key={i.id} value={i.id}>
                        {i.nombre} ({i.moneda})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-bold text-[#191818] mb-1">
                    Fecha del depósito *
                  </label>
                  <input
                    type="date"
                    value={fechaDeposito}
                    onChange={(e) => setFechaDeposito(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-xs"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-[#191818] mb-1">
                    Referencia bancaria
                  </label>
                  <input
                    type="text"
                    value={referenciaBancaria}
                    onChange={(e) => setReferenciaBancaria(e.target.value)}
                    placeholder="Ej. REF-982341"
                    className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-xs font-mono"
                  />
                </div>
              </div>
            </>
          )}
        </div>

        {/* Pie de modal */}
        <div className="px-6 py-4 border-t border-neutral-200/80 bg-[#F6F6F6]/70 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={alCerrar}
            className="px-4 py-2.5 rounded-xl border border-neutral-300 bg-white text-xs font-bold text-neutral-700 cursor-pointer"
          >
            Cancelar
          </button>
          <button
            type="button"
            disabled={confirmando || filasListasSeleccionadas.length === 0}
            onClick={() => void manejarConfirmar()}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] disabled:opacity-40 text-white text-xs font-black shadow-sm cursor-pointer"
          >
            <CheckCircle2 className="w-4 h-4" />
            {confirmando
              ? "Liquidando y conciliando..."
              : `Confirmar Liquidación y Conciliar (${filasListasSeleccionadas.length})`}
          </button>
        </div>
      </div>
    </div>
  );
}
