"use client";

import React, { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, FileSpreadsheet, Upload } from "lucide-react";
import { ErrorApi, solicitarApi, subirArchivoApi } from "@/servicios/api";
import type {
  InstrumentoFinanciero,
  ResultadoConciliacion,
} from "@/tipos/finanzas";

export default function PaginaConciliacion() {
  const [instrumentos, setInstrumentos] = useState<InstrumentoFinanciero[]>([]);
  const [instrumentoId, setInstrumentoId] = useState("");
  const [resultado, setResultado] = useState<ResultadoConciliacion | null>(null);
  const [pestana, setPestana] = useState<
    "cuadrados" | "sin_banco" | "sin_sistema"
  >("cuadrados");
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  useEffect(() => {
    void solicitarApi<InstrumentoFinanciero[]>("/api/finanzas/instrumentos")
      .then((lista) => {
        setInstrumentos(lista);
        if (lista[0]) setInstrumentoId(String(lista[0].id));
      })
      .catch(() => {});
  }, []);

  const importarExtracto = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const archivo = e.target.files?.[0];
    if (!archivo || !instrumentoId) return;
    setError(null);
    setExito(null);
    setCargando(true);
    try {
      const form = new FormData();
      form.append("instrumento_id", instrumentoId);
      form.append("archivo", archivo);
      const resp = await subirArchivoApi<ResultadoConciliacion>(
        "/api/finanzas/conciliacion/importar",
        form
      );
      setResultado(resp);
      setExito(
        `Extracto procesado: ${resp.cuadrados.length} cuadrados automáticamente.`
      );
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo importar el extracto bancario."
      );
    } finally {
      setCargando(false);
      e.target.value = "";
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900 flex items-center gap-2">
            <FileSpreadsheet className="w-6 h-6 text-[#E85A28]" />
            Conciliación Bancaria (CSV / Excel)
          </h2>
          <p className="text-sm text-slate-500">
            Cruce automático por instrumento, referencia y monto.
          </p>
        </div>

        <div className="flex flex-wrap gap-2 items-center">
          <select
            value={instrumentoId}
            onChange={(e) => setInstrumentoId(e.target.value)}
            className="px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
          >
            {instrumentos.map((i) => (
              <option key={i.id} value={i.id}>
                {i.nombre} ({i.moneda})
              </option>
            ))}
          </select>

          <label className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#E85A28] text-white text-sm font-bold cursor-pointer">
            <Upload className="w-4 h-4" />
            <span>{cargando ? "Procesando..." : "Importar Extracto"}</span>
            <input
              type="file"
              accept=".csv,.xlsx"
              onChange={importarExtracto}
              className="hidden"
            />
          </label>
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

      {resultado ? (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setPestana("cuadrados")}
              className={`px-4 py-2 rounded-xl text-xs font-bold cursor-pointer ${
                pestana === "cuadrados"
                  ? "bg-emerald-600 text-white"
                  : "bg-white border border-slate-200"
              }`}
            >
              Cuadrados ({resultado.cuadrados.length})
            </button>
            <button
              type="button"
              onClick={() => setPestana("sin_banco")}
              className={`px-4 py-2 rounded-xl text-xs font-bold cursor-pointer ${
                pestana === "sin_banco"
                  ? "bg-amber-600 text-white"
                  : "bg-white border border-slate-200"
              }`}
            >
              Faltan en banco ({resultado.registrados_sin_banco.length})
            </button>
            <button
              type="button"
              onClick={() => setPestana("sin_sistema")}
              className={`px-4 py-2 rounded-xl text-xs font-bold cursor-pointer ${
                pestana === "sin_sistema"
                  ? "bg-red-600 text-white"
                  : "bg-white border border-slate-200"
              }`}
            >
              Faltan en sistema ({resultado.en_banco_sin_registrar.length})
            </button>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 p-4 text-xs">
            {pestana === "cuadrados" && (
              <pre className="overflow-x-auto text-slate-700">
                {JSON.stringify(resultado.cuadrados, null, 2)}
              </pre>
            )}
            {pestana === "sin_banco" && (
              <pre className="overflow-x-auto text-slate-700">
                {JSON.stringify(resultado.registrados_sin_banco, null, 2)}
              </pre>
            )}
            {pestana === "sin_sistema" && (
              <pre className="overflow-x-auto text-slate-700">
                {JSON.stringify(resultado.en_banco_sin_registrar, null, 2)}
              </pre>
            )}
          </div>
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-slate-200 p-10 text-center text-sm text-slate-500">
          Selecciona un instrumento bancario y sube un extracto CSV o Excel para
          iniciar el cruce automático.
        </div>
      )}
    </div>
  );
}
