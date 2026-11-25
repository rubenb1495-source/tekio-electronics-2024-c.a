"use client";

import React, { useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Upload,
} from "lucide-react";
import { ErrorApi, descargarPdfApi, obtenerToken } from "@/servicios/api";

export type FlujoAdminMasivo =
  | "gastos_operativos"
  | "facturas_cxp"
  | "nomina_adelantos"
  | "extractos_bancarios";

interface FilaPreview {
  fila: number;
  valida: boolean;
  errores: string[];
  datos: Record<string, string>;
}

interface RespuestaPreview {
  flujo: string;
  total_filas: number;
  filas_validas: number;
  filas_con_error: number;
  puede_confirmar: boolean;
  filas: FilaPreview[];
}

const URL_BASE_API =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_URL_API_PYTHON?.replace(/\/+$/, "") ||
  "http://localhost:8000";

export default function PanelImportacionAdmin({
  flujoInicial = "gastos_operativos",
  instrumentoId,
  alCompletar,
}: {
  flujoInicial?: FlujoAdminMasivo;
  instrumentoId?: string;
  alCompletar?: () => void;
}) {
  const [flujo, setFlujo] = useState<FlujoAdminMasivo>(flujoInicial);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [preview, setPreview] = useState<RespuestaPreview | null>(null);
  const [procesando, setProcesando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  const enviar = async <T,>(ruta: string): Promise<T> => {
    if (!archivo) throw new ErrorApi("Selecciona un archivo .xlsx o .csv.", 400);
    const form = new FormData();
    form.append("flujo", flujo);
    if (instrumentoId) form.append("instrumento_id", instrumentoId);
    form.append("archivo", archivo);
    const token = obtenerToken();
    const res = await fetch(`${URL_BASE_API}${ruta}`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      body: form,
    });
    const cuerpo = await res.json().catch(() => null);
    if (!res.ok) {
      const msg =
        typeof cuerpo?.detail === "string"
          ? cuerpo.detail
          : cuerpo?.detail?.mensaje || `Error HTTP ${res.status}`;
      throw new ErrorApi(msg, res.status);
    }
    return cuerpo as T;
  };

  const validar = async () => {
    setError(null);
    setExito(null);
    setProcesando(true);
    try {
      setPreview(await enviar<RespuestaPreview>("/api/finanzas/admin-importar/preview"));
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "Error validando archivo.");
      setPreview(null);
    } finally {
      setProcesando(false);
    }
  };

  const confirmar = async () => {
    setError(null);
    setExito(null);
    setProcesando(true);
    try {
      const res = await enviar<{ mensaje: string }>("/api/finanzas/admin-importar/confirmar");
      setExito(res.mensaje);
      setPreview(null);
      setArchivo(null);
      if (alCompletar) alCompletar();
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "Error confirmando carga masiva.");
    } finally {
      setProcesando(false);
    }
  };

  return (
    <div className="bg-white/80 backdrop-blur-md border border-white/70 rounded-2xl p-4 shadow-[0_8px_30px_rgb(0,0,0,0.04)] space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <FileSpreadsheet className="w-4 h-4 text-[#E85A28]" />
          <p className="text-xs font-black text-[#191818]">
            Carga Masiva Administrativa (.xlsx / .csv) con Validación Atómica
          </p>
        </div>
        <button
          type="button"
          onClick={() =>
            void descargarPdfApi(
              `/api/finanzas/admin-plantillas/${flujo}`,
              `plantilla_admin_${flujo}.xlsx`
            )
          }
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#FDF0EB] border border-[#E85A28]/30 text-[#E85A28] hover:bg-[#E85A28] hover:text-white text-xs font-bold cursor-pointer"
        >
          <Download className="w-3.5 h-3.5" />
          Plantilla .xlsx
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
        <select
          value={flujo}
          onChange={(e) => {
            setFlujo(e.target.value as FlujoAdminMasivo);
            setPreview(null);
          }}
          className="px-3 py-2 rounded-xl border border-neutral-200 bg-white text-xs font-semibold"
        >
          <option value="gastos_operativos">1. Gastos Operativos</option>
          <option value="facturas_cxp">2. Facturas Proveedores / CxP</option>
          <option value="nomina_adelantos">3. Nómina / Fichas Personal</option>
          <option value="extractos_bancarios">4. Extractos Bancarios</option>
        </select>
        <input
          type="file"
          accept=".xlsx,.csv"
          onChange={(e) => {
            setArchivo(e.target.files?.[0] ?? null);
            setPreview(null);
          }}
          className="text-xs file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-[#191818] file:text-white file:text-xs file:font-bold"
        />
        <div className="flex gap-2">
          <button
            type="button"
            disabled={!archivo || procesando}
            onClick={() => void validar()}
            className="flex-1 inline-flex items-center justify-center gap-1 px-3 py-2 rounded-xl border border-neutral-300 bg-white text-xs font-bold cursor-pointer disabled:opacity-50"
          >
            <Upload className="w-3.5 h-3.5" />
            1. Preview
          </button>
          <button
            type="button"
            disabled={!preview?.puede_confirmar || procesando}
            onClick={() => void confirmar()}
            className="flex-1 inline-flex items-center justify-center gap-1 px-3 py-2 rounded-xl bg-[#E85A28] text-white text-xs font-bold cursor-pointer disabled:opacity-40"
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            2. Confirmar
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-2.5 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700 font-semibold">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}
      {exito && (
        <div className="flex items-center gap-2 p-2.5 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 font-semibold">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{exito}</span>
        </div>
      )}
      {preview && (
        <div className="text-xs space-y-1.5">
          <div className="flex gap-2 font-bold">
            <span className="px-2 py-0.5 rounded bg-neutral-100">Filas: {preview.total_filas}</span>
            <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700">Válidas: {preview.filas_validas}</span>
            <span className="px-2 py-0.5 rounded bg-red-50 text-red-700">Errores: {preview.filas_con_error}</span>
          </div>
          {preview.filas.some((f) => !f.valida) && (
            <div className="max-h-36 overflow-y-auto rounded-xl border border-red-200 bg-red-50/40 p-2 space-y-1">
              {preview.filas
                .filter((f) => !f.valida)
                .map((f) => (
                  <p key={f.fila} className="text-red-700">
                    <strong>Fila #{f.fila}:</strong> {f.errores.join(" | ")}
                  </p>
                ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
