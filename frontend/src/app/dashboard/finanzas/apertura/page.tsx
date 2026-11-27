"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  Archive,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Lock,
  RefreshCw,
  ShieldAlert,
  Upload,
} from "lucide-react";
import { usePermisos } from "@/lib/permisos";
import {
  ErrorApi,
  descargarPdfApi,
  formatearUsd,
  solicitarApi,
  subirArchivoApi,
} from "@/servicios/api";

interface PasoApertura {
  tipo: string;
  paso: number;
  titulo: string;
  archivo: string;
  cargado: boolean;
}

interface CuadreApertura {
  cajas_bancos_usd: number;
  inventario_equipos_usd: number;
  inventario_componentes_usd: number;
  cxc_clientes_usd: number;
  cashea_por_cobrar_usd: number;
  total_activos_usd: number;
  cxp_proveedores_usd: number;
  prestamos_por_pagar_usd: number;
  total_pasivos_usd: number;
  patrimonio_capital_inicial_usd: number;
  varianza_usd: number;
  cuadrado: boolean;
  pl_diciembre_utilidad_neta_usd: number;
  pl_diciembre_ingresos_usd: number;
}

interface EstadoAperturaResp {
  fecha_apertura: string;
  tasa_bcv_apertura: number | null;
  tasa_usdt_apertura: number | null;
  pasos: PasoApertura[];
  cuadre: CuadreApertura;
}

interface FilaPreviewApertura {
  fila: number;
  hoja?: string;
  valida: boolean;
  errores: string[];
  resumen: string;
  monto_usd: number;
}

interface PreviewAperturaResp {
  tipo: string;
  total_filas: number;
  validas: number;
  con_errores: number;
  errores_globales: string[];
  total_monto_usd: number;
  filas: FilaPreviewApertura[];
}

export default function PaginaApertura0112() {
  const { esDireccion, esAdmin } = usePermisos();
  const [estado, setEstado] = useState<EstadoAperturaResp | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  // Selector de Tasa BCV de Apertura (01/12/2026)
  const [tasaBcvInput, setTasaBcvInput] = useState("");
  const [guardandoTasa, setGuardandoTasa] = useState(false);

  // Estado por tarjeta (archivo + preview)
  const [archivosPorPaso, setArchivosPorPaso] = useState<Record<string, File | null>>({});
  const [previewsPorPaso, setPreviewsPorPaso] = useState<Record<string, PreviewAperturaResp | null>>({});
  const [procesandoPaso, setProcesandoPaso] = useState<string | null>(null);

  // Modal de Reset a Cero (exclusivo DIRECCION)
  const [modalReset, setModalReset] = useState(false);
  const [passwordReset, setPasswordReset] = useState("");
  const [fraseReset, setFraseReset] = useState("");
  const [ejecutandoReset, setEjecutandoReset] = useState(false);

  const cargarEstado = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const resp = await solicitarApi<EstadoAperturaResp>("/api/finanzas/apertura/estado");
      setEstado(resp);
      if (resp.tasa_bcv_apertura) {
        setTasaBcvInput(String(resp.tasa_bcv_apertura));
      }
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo cargar el estado de apertura 01/12/2026."
      );
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    if (esAdmin) {
      void cargarEstado();
    } else {
      setCargando(false);
    }
  }, [esAdmin, cargarEstado]);

  if (!esAdmin) {
    return (
      <div className="bg-white/85 backdrop-blur-md border border-red-200 rounded-2xl p-6 text-sm text-red-700 flex items-center gap-3">
        <Lock className="w-5 h-5 shrink-0" />
        <span>
          Acceso denegado (403): El módulo de Apertura 01/12/2026 es exclusivo de Dirección y Administración.
        </span>
      </div>
    );
  }

  const guardarTasaApertura = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const valor = Number(tasaBcvInput);
    if (!valor || valor <= 0) {
      setError("Ingresa una Tasa BCV válida mayor a 0.");
      return;
    }
    setGuardandoTasa(true);
    setError(null);
    setExito(null);
    try {
      await solicitarApi("/api/finanzas/apertura/tasa-bcv", {
        method: "POST",
        body: JSON.stringify({ tasa_bcv: valor, tasa_usdt: valor }),
      });
      setExito(`Tasa BCV de Apertura (01/12/2026) fijada en Bs ${valor.toFixed(2)}.`);
      await cargarEstado();
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo guardar la tasa.");
    } finally {
      setGuardandoTasa(false);
    }
  };

  const analizarPaso = async (tipo: string, archivo: File) => {
    setProcesandoPaso(tipo);
    setError(null);
    setExito(null);
    try {
      const fd = new FormData();
      fd.append("archivo", archivo);
      const prev = await subirArchivoApi<PreviewAperturaResp>(
        `/api/finanzas/apertura/importar/${tipo}/preview`,
        fd
      );
      setArchivosPorPaso((p) => ({ ...p, [tipo]: archivo }));
      setPreviewsPorPaso((p) => ({ ...p, [tipo]: prev }));
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo analizar la planilla.");
    } finally {
      setProcesandoPaso(null);
    }
  };

  const confirmarPaso = async (tipo: string) => {
    const archivo = archivosPorPaso[tipo];
    if (!archivo) return;
    setProcesandoPaso(tipo);
    setError(null);
    setExito(null);
    try {
      const fd = new FormData();
      fd.append("archivo", archivo);
      const resp = await subirArchivoApi<{
        filas_importadas: number;
        monto_asiento_usd: number;
      }>(`/api/finanzas/apertura/importar/${tipo}/confirmar`, fd);
      setExito(
        `Carga '${tipo}' confirmada (${resp.filas_importadas} filas · asiento contable ${formatearUsd(
          resp.monto_asiento_usd
        )} al 01/12/2026).`
      );
      setPreviewsPorPaso((p) => ({ ...p, [tipo]: null }));
      setArchivosPorPaso((p) => ({ ...p, [tipo]: null }));
      await cargarEstado();
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo confirmar la carga.");
    } finally {
      setProcesandoPaso(null);
    }
  };

  const ejecutarResetSeguro = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setEjecutandoReset(true);
    setError(null);
    setExito(null);
    try {
      const resp = await solicitarApi<{
        tablas_limpiadas: number;
        respaldo_previo: { nombre_archivo: string };
      }>("/api/admin/reset-apertura", {
        method: "POST",
        body: JSON.stringify({
          password: passwordReset,
          frase_confirmacion: fraseReset.trim(),
        }),
      });
      setModalReset(false);
      setPasswordReset("");
      setFraseReset("");
      setExito(
        `Sistema reiniciado a cero para apertura 01/12/2026 (${resp.tablas_limpiadas} tablas limpiadas · respaldo previo: ${resp.respaldo_previo.nombre_archivo}).`
      );
      await cargarEstado();
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo ejecutar el reinicio.");
    } finally {
      setEjecutandoReset(false);
    }
  };

  const cuadre = estado?.cuadre;

  return (
    <div className="space-y-6">
      {/* Encabezado Light-First */}
      <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 flex flex-wrap items-center justify-between gap-4">
        <div>
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full bg-[#FDF0EB] text-[#E85A28] text-[11px] font-black uppercase tracking-wide mb-1">
            Corte Oficial · 01/12/2026
          </span>
          <h2 className="text-2xl font-black text-[#191818] flex items-center gap-2">
            <FileSpreadsheet className="w-6 h-6 text-[#E85A28]" />
            Apertura 01/12/2026 — Inicio en Cero y Carga Inicial
          </h2>
          <p className="text-xs text-neutral-500 mt-0.5">
            Carga guiada en 6 pasos contra Capital Inicial (3.1.01) con varianza $0.00 en Balance General e impacto $0.00 en el P&amp;L de diciembre.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={() =>
              void descargarPdfApi(
                "/api/finanzas/apertura/plantillas/zip",
                "tekio_apertura_01_12_2026_planillas.zip"
              )
            }
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#D14D20] text-white text-xs font-black shadow-sm cursor-pointer"
          >
            <Archive className="w-4 h-4" />
            Descargar las 6 Planillas (.zip)
          </button>

          {esDireccion && (
            <button
              type="button"
              onClick={() => setModalReset(true)}
              className="inline-flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl border border-red-300 bg-red-50 hover:bg-red-100 text-red-700 text-xs font-bold cursor-pointer"
            >
              <ShieldAlert className="w-4 h-4" />
              Reiniciar a Cero (Dirección)
            </button>
          )}
        </div>
      </div>

      {/* Selector de Tasa BCV de Apertura */}
      <form
        onSubmit={guardarTasaApertura}
        className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-4 flex flex-wrap items-end justify-between gap-4"
      >
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs font-bold text-[#191818] mb-1">
              Tasa BCV de Apertura (01/12/2026) — Bs / USD
            </label>
            <input
              type="number"
              step="0.0001"
              min="0.01"
              value={tasaBcvInput}
              onChange={(e) => setTasaBcvInput(e.target.value)}
              placeholder="Ej. 52.50"
              className="w-48 px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm font-mono font-bold text-[#191818] tabular-nums"
            />
          </div>
          <button
            type="submit"
            disabled={guardandoTasa}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#E85A28] hover:bg-[#D14D20] disabled:opacity-50 text-white text-xs font-bold cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${guardandoTasa ? "animate-spin" : ""}`} />
            Guardar Tasa de Apertura
          </button>
        </div>

        {cuadre && (
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-black tabular-nums border ${
                cuadre.cuadrado
                  ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                  : "bg-red-50 text-red-700 border-red-200"
              }`}
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              Balance General: {cuadre.cuadrado ? "Cuadrado" : "Descuadrado"} (Varianza{" "}
              {formatearUsd(cuadre.varianza_usd)})
            </span>
            <span
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-black tabular-nums border ${
                cuadre.pl_diciembre_utilidad_neta_usd === 0
                  ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                  : "bg-amber-50 text-amber-800 border-amber-200"
              }`}
            >
              P&amp;L Diciembre: {formatearUsd(cuadre.pl_diciembre_utilidad_neta_usd)}
            </span>
          </div>
        )}
      </form>

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

      {/* Panel en vivo de Cuadre de Apertura */}
      {cuadre && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 space-y-1.5">
            <p className="text-[11px] font-bold uppercase tracking-wide text-neutral-500">
              Total Activos de Apertura
            </p>
            <p className="text-2xl font-black text-[#191818] tabular-nums">
              {formatearUsd(cuadre.total_activos_usd)}
            </p>
            <div className="text-[11px] text-neutral-500 space-y-0.5 tabular-nums pt-1 border-t border-neutral-100">
              <p>Cajas y Bancos: {formatearUsd(cuadre.cajas_bancos_usd)}</p>
              <p>
                Inventario Propio:{" "}
                {formatearUsd(cuadre.inventario_equipos_usd + cuadre.inventario_componentes_usd)}
              </p>
              <p>
                CxC + Cashea:{" "}
                {formatearUsd(cuadre.cxc_clientes_usd + cuadre.cashea_por_cobrar_usd)}
              </p>
            </div>
          </div>

          <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 space-y-1.5">
            <p className="text-[11px] font-bold uppercase tracking-wide text-neutral-500">
              (-) Total Pasivos Iniciales
            </p>
            <p className="text-2xl font-black text-red-700 tabular-nums">
              {formatearUsd(cuadre.total_pasivos_usd)}
            </p>
            <div className="text-[11px] text-neutral-500 space-y-0.5 tabular-nums pt-1 border-t border-neutral-100">
              <p>CxP Proveedores: {formatearUsd(cuadre.cxp_proveedores_usd)}</p>
              <p>Préstamos Activos: {formatearUsd(cuadre.prestamos_por_pagar_usd)}</p>
            </div>
          </div>

          <div className="bg-[#FDF0EB]/80 backdrop-blur-md border-2 border-[#E85A28]/40 rounded-2xl p-5 space-y-1.5">
            <p className="text-[11px] font-bold uppercase tracking-wide text-[#E85A28]">
              (=) Patrimonio / Capital Inicial Neto
            </p>
            <p className="text-2xl font-black text-[#191818] tabular-nums">
              {formatearUsd(cuadre.patrimonio_capital_inicial_usd)}
            </p>
            <p className="text-[11px] text-neutral-600 pt-1 border-t border-[#E85A28]/20">
              Contrapartida contable 3.1.01 · Corte 01/12/2026
            </p>
          </div>
        </div>
      )}

      {/* Tarjetas secuenciales Paso 1 al Paso 6 */}
      {cargando ? (
        <div className="h-48 rounded-2xl bg-white/70 animate-pulse border border-neutral-200" />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {(estado?.pasos || []).map((paso) => {
            const preview = previewsPorPaso[paso.tipo];
            const ocupado = procesandoPaso === paso.tipo;
            return (
              <div
                key={paso.tipo}
                className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 space-y-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <span className="text-[11px] font-black uppercase text-[#E85A28]">
                      Paso {paso.paso} de 6
                    </span>
                    <h3 className="text-sm font-black text-[#191818]">{paso.titulo}</h3>
                    <p className="text-[11px] font-mono text-neutral-500">{paso.archivo}</p>
                  </div>
                  <span
                    className={`px-2.5 py-1 rounded-full text-[11px] font-bold border ${
                      paso.cargado
                        ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                        : "bg-neutral-100 text-neutral-600 border-neutral-200"
                    }`}
                  >
                    {paso.cargado ? "Cargado" : "Pendiente"}
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() =>
                      void descargarPdfApi(
                        `/api/finanzas/apertura/plantillas/${paso.tipo}`,
                        paso.archivo
                      )
                    }
                    className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-neutral-300 bg-white hover:bg-neutral-50 text-xs font-bold text-[#191818] cursor-pointer"
                  >
                    <Download className="w-3.5 h-3.5 text-[#E85A28]" />
                    Descargar Planilla .xlsx
                  </button>

                  <label className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-[#FDF0EB] border border-[#E85A28]/40 text-[#E85A28] hover:bg-[#E85A28] hover:text-white text-xs font-bold transition-colors cursor-pointer">
                    <Upload className="w-3.5 h-3.5" />
                    <span>{ocupado ? "Validando..." : "Subir .xlsx (Vista Previa)"}</span>
                    <input
                      type="file"
                      accept=".xlsx"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) void analizarPaso(paso.tipo, f);
                        e.target.value = "";
                      }}
                    />
                  </label>
                </div>

                {preview && (
                  <div className="rounded-xl border border-neutral-200 bg-[#F6F6F6]/70 p-3.5 space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 font-bold">
                          Válidas: {preview.validas}
                        </span>
                        <span className="px-2 py-0.5 rounded-full bg-red-50 text-red-700 font-bold">
                          Errores: {preview.con_errores}
                        </span>
                        <span className="font-bold text-[#191818] tabular-nums">
                          Total: {formatearUsd(preview.total_monto_usd)}
                        </span>
                      </div>
                      <button
                        type="button"
                        disabled={ocupado || preview.validas === 0 || preview.con_errores > 0}
                        onClick={() => void confirmarPaso(paso.tipo)}
                        className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-[#E85A28] hover:bg-[#D14D20] disabled:opacity-40 text-white text-xs font-black cursor-pointer"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        Confirmar Carga
                      </button>
                    </div>

                    {preview.errores_globales.length > 0 && (
                      <div className="p-2.5 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700 font-bold">
                        {preview.errores_globales.join(" · ")}
                      </div>
                    )}

                    <div className="max-h-40 overflow-y-auto divide-y divide-neutral-200 bg-white rounded-lg border border-neutral-200 text-[11px]">
                      {preview.filas.map((f, i) => (
                        <div
                          key={`${f.hoja || "h"}-${f.fila}-${i}`}
                          className={`px-2.5 py-1.5 flex items-center justify-between gap-2 ${
                            f.valida ? "" : "bg-red-50 text-red-700"
                          }`}
                        >
                          <span className="truncate">
                            <strong>#{f.fila}</strong> {f.resumen}
                          </span>
                          <span className="shrink-0 font-bold tabular-nums">
                            {f.valida ? formatearUsd(f.monto_usd) : f.errores.join(" · ")}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Modal de Doble Confirmación Reset a Cero (Exclusivo DIRECCION) */}
      {modalReset && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 border border-red-200 shadow-xl space-y-4">
            <h3 className="text-lg font-black text-red-700 flex items-center gap-2">
              <ShieldAlert className="w-5 h-5" />
              Reiniciar Sistema a Cero (01/12/2026)
            </h3>
            <p className="text-xs text-neutral-600 leading-relaxed">
              Esta acción genera primero un respaldo JSON automático y luego elimina todas las transacciones de prueba conservando las 3 sedes, el RIF, el plan de cuentas, los instrumentos en $0.00 y el equipo activo.
            </p>
            <form onSubmit={ejecutarResetSeguro} className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-[#191818] mb-1">
                  Tu contraseña de Dirección *
                </label>
                <input
                  type="password"
                  required
                  value={passwordReset}
                  onChange={(e) => setPasswordReset(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-[#191818] mb-1">
                  Escribe exactamente: <span className="font-mono text-red-700">REINICIAR TEKIO 01-12</span>
                </label>
                <input
                  type="text"
                  required
                  value={fraseReset}
                  onChange={(e) => setFraseReset(e.target.value)}
                  placeholder="REINICIAR TEKIO 01-12"
                  className="w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm font-mono"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setModalReset(false)}
                  className="px-4 py-2 rounded-xl border border-neutral-300 text-xs font-bold text-[#191818] cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={ejecutandoReset || fraseReset.trim() !== "REINICIAR TEKIO 01-12"}
                  className="px-4 py-2 rounded-xl bg-red-600 hover:bg-red-700 disabled:opacity-40 text-white text-xs font-black cursor-pointer"
                >
                  {ejecutandoReset ? "Reiniciando..." : "Confirmar Reinicio a Cero"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
