"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  CloudUpload,
  DatabaseBackup,
  Download,
  History,
} from "lucide-react";
import { usarSesion } from "@/contexto/SesionContexto";
import {
  extraerMensajeError,
  obtenerToken,
  solicitarApi,
} from "@/servicios/api";

interface HistorialRespaldo {
  id: number;
  archivo: string;
  usuario: string;
  fecha_hora: string | null;
  tamano_kb: number;
  total_tablas: number;
  total_registros: number;
}

const URL_BASE_API =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_URL_API_PYTHON?.replace(/\/+$/, "") ||
  "http://localhost:8000";

function formatearFechaCaracas(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString("es-VE", {
      timeZone: "America/Caracas",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    });
  } catch {
    return iso;
  }
}

export default function TarjetaRespaldoBD() {
  const { usuario } = usarSesion();
  const esAdmin = usuario?.rol === "ADMINISTRACION";

  const [historial, setHistorial] = useState<HistorialRespaldo[]>([]);
  const [descargando, setDescargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  const cargarHistorial = useCallback(async () => {
    if (!esAdmin) return;
    try {
      const lista = await solicitarApi<HistorialRespaldo[]>(
        "/api/admin/respaldo/historial"
      );
      setHistorial(lista);
    } catch {
      // Silencioso en carga inicial
    }
  }, [esAdmin]);

  useEffect(() => {
    void cargarHistorial();
  }, [cargarHistorial]);

  if (!esAdmin) return null;

  const descargarRespaldo = async () => {
    setDescargando(true);
    setError(null);
    setExito(null);
    try {
      const token = obtenerToken();
      const headers = new Headers();
      if (token) headers.set("Authorization", `Bearer ${token}`);

      const resp = await fetch(`${URL_BASE_API}/api/admin/respaldo/descargar`, {
        headers,
      });
      if (!resp.ok) {
        const cuerpo = await resp.json().catch(() => null);
        throw new Error(
          extraerMensajeError(
            cuerpo,
            `Error al generar respaldo (HTTP ${resp.status}).`
          )
        );
      }

      const disp = resp.headers.get("Content-Disposition") || "";
      const match = disp.match(/filename="?([^"]+)"?/i);
      const nombreArchivo = match?.[1] || "respaldo_tekio.zip";

      const blob = await resp.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = nombreArchivo;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);

      setExito(
        `Respaldo "${nombreArchivo}" descargado correctamente (JSON técnico + Excel legible).`
      );
      await cargarHistorial();
    } catch (err) {
      setError(
        extraerMensajeError(err, "No se pudo descargar el respaldo completo.")
      );
    } finally {
      setDescargando(false);
    }
  };

  const ultimo = historial[0] ?? null;

  return (
    <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 shadow-xs space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h3 className="text-base font-black text-[#191818] flex items-center gap-2">
            <DatabaseBackup className="w-5 h-5 text-[#E85A28]" />
            Respaldo de Base de Datos (Solo Administración)
          </h3>
          <p className="text-xs text-neutral-500">
            Descarga en un solo archivo <code>.zip</code> el volcado completo en JSON (<code>backup_completo.json</code>) y el libro Excel legible (<code>resumen_legible_tekio.xlsx</code>).
          </p>
        </div>

        <button
          type="button"
          disabled={descargando}
          onClick={() => void descargarRespaldo()}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-xs font-black shadow-sm cursor-pointer disabled:opacity-60"
        >
          <Download className={`w-4 h-4 ${descargando ? "animate-bounce" : ""}`} />
          {descargando
            ? "Generando respaldo..."
            : "Descargar Respaldo Completo (.zip)"}
        </button>
      </div>

      {/* Estado del último respaldo + Recordatorio Google Drive */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
        <div className="rounded-xl bg-neutral-50 border border-neutral-200/80 p-3 flex items-start gap-2.5">
          <History className="w-4 h-4 text-[#E85A28] shrink-0 mt-0.5" />
          <div>
            <p className="font-bold text-[#191818]">Último respaldo descargado</p>
            {ultimo ? (
              <p className="text-neutral-600 mt-0.5 tabular-nums">
                <strong>{formatearFechaCaracas(ultimo.fecha_hora)}</strong> · por{" "}
                {ultimo.usuario} ({ultimo.tamano_kb} KB · {ultimo.total_tablas} tablas)
              </p>
            ) : (
              <p className="text-amber-700 font-semibold mt-0.5">
                Aún no se ha descargado ninguna copia de seguridad.
              </p>
            )}
          </div>
        </div>

        <div className="rounded-xl bg-blue-50/80 border border-blue-200/80 p-3 flex items-start gap-2.5">
          <CloudUpload className="w-4 h-4 text-blue-700 shrink-0 mt-0.5" />
          <div>
            <p className="font-bold text-blue-900">Recomendación de resguardo</p>
            <p className="text-blue-800 mt-0.5">
              Guarda el archivo <code>.zip</code> descargado en una carpeta segura de{" "}
              <strong>Google Drive</strong> al cierre de cada semana.
            </p>
          </div>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}
      {exito && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-700">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{exito}</span>
        </div>
      )}
    </div>
  );
}
