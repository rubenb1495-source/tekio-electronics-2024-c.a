"use client";

import React, { useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Upload,
} from "lucide-react";
import { usePermisos } from "@/lib/permisos";
import { ErrorApi, descargarPdfApi, obtenerToken } from "@/servicios/api";

type FlujoMasivo =
  | "compras_nacionales"
  | "compras_internacionales"
  | "consignacion"
  | "traslados_universales"
  | "cambio_estado";

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

export default function PanelImportacionMasiva({
  flujoInicial = "compras_nacionales",
  alCompletar,
}: {
  flujoInicial?: FlujoMasivo;
  alCompletar?: () => void;
}) {
  const permisos = usePermisos();
  const [flujo, setFlujo] = useState<FlujoMasivo>(flujoInicial);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [preview, setPreview] = useState<RespuestaPreview | null>(null);
  const [procesando, setProcesando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  const flujosDisponibles: { valor: FlujoMasivo; etiqueta: string; visible: boolean }[] = [
    {
      valor: "compras_nacionales",
      etiqueta: "1. Compras Nacionales",
      visible: permisos.puedeGestionarCompras,
    },
    {
      valor: "compras_internacionales",
      etiqueta: "2. Compras Internacionales (con prorrateo)",
      visible: permisos.puedeGestionarCompras,
    },
    {
      valor: "consignacion",
      etiqueta: "3. Mercancía en Consignación",
      visible: permisos.puedeGestionarCompras,
    },
    {
      valor: "traslados_universales",
      etiqueta: "4. Traslados Universales (Serial + SKU)",
      visible: permisos.puedeRegistrarTraslados,
    },
    {
      valor: "cambio_estado",
      etiqueta: "5. Cambio de Estado / Preparaciones",
      visible: true,
    },
  ];

  const visibles = flujosDisponibles.filter((f) => f.visible);

  const enviarFormulario = async <T,>(ruta: string): Promise<T> => {
    if (!archivo) {
      throw new ErrorApi("Selecciona un archivo .xlsx o .csv primero.", 400);
    }
    const form = new FormData();
    form.append("flujo", flujo);
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

  const previsualizar = async () => {
    setError(null);
    setExito(null);
    setProcesando(true);
    try {
      const res = await enviarFormulario<RespuestaPreview>(
        "/api/logistica/importar/preview"
      );
      setPreview(res);
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo validar el archivo.");
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
      const res = await enviarFormulario<{ mensaje: string }>(
        "/api/logistica/importar/confirmar"
      );
      setExito(res.mensaje);
      setPreview(null);
      setArchivo(null);
      if (alCompletar) alCompletar();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo confirmar la importación atómica."
      );
    } finally {
      setProcesando(false);
    }
  };

  return (
    <div className="bg-white/80 backdrop-blur-md border border-white/70 rounded-2xl p-5 shadow-[0_8px_30px_rgb(0,0,0,0.04)] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-[#FDF0EB] text-[#E85A28] flex items-center justify-center">
            <FileSpreadsheet className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-black text-[#191818]">
              Plantillas Oficiales e Importación Masiva Atómica (.xlsx / .csv)
            </h3>
            <p className="text-xs text-neutral-500">
              Paso 1: valida fila por fila sin guardar. Paso 2: confirma todo en una sola transacción.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() =>
            void descargarPdfApi(
              `/api/logistica/plantillas/${flujo}`,
              `plantilla_tekio_${flujo}.xlsx`
            )
          }
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-[#E85A28]/30 bg-[#FDF0EB] text-[#E85A28] text-xs font-bold hover:bg-[#E85A28] hover:text-white transition-colors cursor-pointer"
        >
          <Download className="w-3.5 h-3.5" />
          Descargar Plantilla .xlsx
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div>
          <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
            Flujo de Operación
          </label>
          <select
            value={flujo}
            onChange={(e) => {
              setFlujo(e.target.value as FlujoMasivo);
              setPreview(null);
            }}
            className="w-full px-3 py-2 rounded-xl border border-neutral-200 bg-white text-xs font-semibold text-[#191818]"
          >
            {visibles.map((f) => (
              <option key={f.valor} value={f.valor}>
                {f.etiqueta}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
            Archivo (.xlsx o .csv)
          </label>
          <input
            type="file"
            accept=".xlsx,.csv"
            onChange={(e) => {
              setArchivo(e.target.files?.[0] ?? null);
              setPreview(null);
            }}
            className="w-full text-xs file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-neutral-900 file:text-white file:text-xs file:font-bold"
          />
        </div>

        <div className="flex items-end gap-2">
          <button
            type="button"
            disabled={!archivo || procesando}
            onClick={() => void previsualizar()}
            className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl border border-neutral-300 bg-white text-xs font-bold text-[#191818] hover:bg-neutral-50 disabled:opacity-50 cursor-pointer"
          >
            <Upload className="w-3.5 h-3.5" />
            {procesando ? "Validando..." : "1. Vista Previa"}
          </button>
          <button
            type="button"
            disabled={!preview?.puede_confirmar || procesando}
            onClick={() => void confirmar()}
            className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] text-white text-xs font-bold disabled:opacity-40 cursor-pointer"
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            2. Confirmar
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700 font-semibold">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {exito && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 font-semibold">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{exito}</span>
        </div>
      )}

      {preview && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-3 text-xs font-bold">
            <span className="px-2.5 py-1 rounded-lg bg-neutral-100 text-neutral-700">
              Total filas: {preview.total_filas}
            </span>
            <span className="px-2.5 py-1 rounded-lg bg-emerald-50 text-emerald-700">
              Válidas: {preview.filas_validas}
            </span>
            <span className="px-2.5 py-1 rounded-lg bg-red-50 text-red-700">
              Con error: {preview.filas_con_error}
            </span>
          </div>
          <div className="max-h-56 overflow-y-auto rounded-xl border border-neutral-200">
            <table className="w-full text-xs">
              <thead className="bg-neutral-50 text-neutral-500 uppercase text-[10px]">
                <tr>
                  <th className="px-3 py-2 text-left">Fila</th>
                  <th className="px-3 py-2 text-left">Estado</th>
                  <th className="px-3 py-2 text-left">Detalle / Errores</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {preview.filas.map((f) => (
                  <tr key={f.fila} className={f.valida ? "bg-white" : "bg-red-50/50"}>
                    <td className="px-3 py-1.5 font-mono font-bold">#{f.fila}</td>
                    <td className="px-3 py-1.5">
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          f.valida
                            ? "bg-emerald-50 text-emerald-700"
                            : "bg-red-100 text-red-700"
                        }`}
                      >
                        {f.valida ? "VÁLIDA" : "ERROR"}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-neutral-700">
                      {f.valida
                        ? Object.entries(f.datos)
                            .filter(([, v]) => v)
                            .slice(0, 4)
                            .map(([k, v]) => `${k}: ${v}`)
                            .join(" · ")
                        : f.errores.join(" | ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
