"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, FileDown, FileSpreadsheet, Shield } from "lucide-react";
import BuscadorTabla from "@/componentes/BuscadorTabla";
import { ErrorApi, descargarPdfApi, solicitarApi } from "@/servicios/api";

interface RegistroAuditoria {
  id: number;
  fecha: string;
  usuario_nombre: string;
  usuario_rol: string;
  modulo: string;
  accion: string;
  entidad_id: string;
  detalle_anterior: Record<string, unknown>;
  detalle_nuevo: Record<string, unknown>;
}

export default function PaginaAuditoriaInterna() {
  const [registros, setRegistros] = useState<RegistroAuditoria[]>([]);
  const [modulo, setModulo] = useState("");
  const [busqueda, setBusqueda] = useState("");
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const qs = modulo ? `?modulo=${modulo}` : "";
      setRegistros(await solicitarApi<RegistroAuditoria[]>(`/api/finanzas/auditoria${qs}`));
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo cargar la bitácora.");
    } finally {
      setCargando(false);
    }
  }, [modulo]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const filtrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return registros;
    return registros.filter((r) =>
      [r.usuario_nombre, r.usuario_rol, r.modulo, r.accion, r.entidad_id, JSON.stringify(r.detalle_nuevo)]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [registros, busqueda]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-black text-[#191818] flex items-center gap-2">
            <Shield className="w-6 h-6 text-[#E85A28]" />
            Auditoría Interna Inmutable
          </h2>
          <p className="text-sm text-neutral-500">
            Registro de solo inserción de anulaciones, reembolsos, cambios de precios, tesorería y aprobaciones de nómina.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <select value={modulo} onChange={(e) => setModulo(e.target.value)} className="px-3 py-2 rounded-xl border border-neutral-200 bg-white font-semibold">
            <option value="">Todos los módulos</option>
            <option value="VENTAS">VENTAS</option>
            <option value="COMISIONES">COMISIONES</option>
            <option value="TESORERIA">TESORERIA</option>
            <option value="CONTABILIDAD">CONTABILIDAD</option>
            <option value="NOMINA">NOMINA</option>
            <option value="CATALOGO">CATALOGO</option>
          </select>
          <button type="button" onClick={() => void descargarPdfApi("/api/finanzas/auditoria/exportar/xlsx", "Auditoria_Sistema_Tekio.xlsx")} className="inline-flex items-center gap-1 px-3 py-2 rounded-xl bg-[#191818] text-white font-bold cursor-pointer">
            <FileSpreadsheet className="w-3.5 h-3.5" /> Excel
          </button>
          <button type="button" onClick={() => void descargarPdfApi("/api/finanzas/auditoria/exportar/pdf", "Auditoria_Sistema_Tekio.pdf")} className="inline-flex items-center gap-1 px-3 py-2 rounded-xl bg-[#E85A28] text-white font-bold cursor-pointer">
            <FileDown className="w-3.5 h-3.5" /> PDF
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3.5 rounded-2xl bg-red-50 border border-red-200 text-xs text-red-700 font-semibold">
          <AlertCircle className="w-4 h-4 shrink-0" /> <span>{error}</span>
        </div>
      )}

      <div className="bg-white/80 backdrop-blur-md border border-white/70 rounded-2xl p-5 shadow-xs space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs font-bold text-neutral-500">{filtrados.length} evento(s) inmutables</p>
          <div className="w-full sm:w-80">
            <BuscadorTabla valor={busqueda} alCambiar={setBusqueda} placeholder="Filtrar por usuario, acción o entidad..." />
          </div>
        </div>
        {cargando ? (
          <div className="h-24 rounded-xl bg-neutral-100 animate-pulse" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-neutral-50 border-b border-neutral-200 uppercase text-[10px] text-neutral-500">
                <tr>
                  <th className="px-3 py-2">Fecha</th>
                  <th className="px-3 py-2">Usuario / Rol</th>
                  <th className="px-3 py-2">Módulo / Acción</th>
                  <th className="px-3 py-2">Entidad</th>
                  <th className="px-3 py-2">Antes → Después</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {filtrados.map((r) => (
                  <tr key={r.id}>
                    <td className="px-3 py-2 font-mono text-[11px] whitespace-nowrap">{r.fecha.slice(0, 19).replace("T", " ")}</td>
                    <td className="px-3 py-2"><strong>{r.usuario_nombre}</strong> <span className="text-[10px] text-neutral-400">({r.usuario_rol})</span></td>
                    <td className="px-3 py-2">
                      <span className="px-2 py-0.5 rounded-full bg-[#FDF0EB] text-[#E85A28] font-bold text-[10px]">{r.modulo}</span>{" "}
                      <span className="font-semibold">{r.accion}</span>
                    </td>
                    <td className="px-3 py-2 font-mono font-bold">{r.entidad_id || "—"}</td>
                    <td className="px-3 py-2 text-[11px] text-neutral-600 max-w-md break-words">
                      {Object.keys(r.detalle_anterior).length > 0 && (
                        <span className="text-red-700">Antes: {JSON.stringify(r.detalle_anterior)} → </span>
                      )}
                      <span className="text-emerald-800">{JSON.stringify(r.detalle_nuevo)}</span>
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
