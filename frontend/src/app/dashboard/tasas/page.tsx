"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Calendar,
  CheckCircle2,
  Save,
  TrendingUp,
} from "lucide-react";
import { usarSesion } from "@/contexto/SesionContexto";
import {
  ErrorApi,
  esRolAdministrativo,
  formatearBs,
  formatearPorcentaje,
  solicitarApi,
} from "@/servicios/api";
import type { TasaDiaria, TasasPaginadas } from "@/tipos/dominio";

export default function PaginaTasas() {
  const { usuario, tasaHoy, recargarTasaHoy } = usarSesion();
  const puedeEditar = usuario ? esRolAdministrativo(usuario.rol) : false;

  const [historial, setHistorial] = useState<TasaDiaria[]>([]);
  const [total, setTotal] = useState(0);
  const [pagina, setPagina] = useState(1);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mensajeExito, setMensajeExito] = useState<string | null>(null);

  // Formulario rápido de hoy
  const [tasaBcv, setTasaBcv] = useState("");
  const [tasaUsdt, setTasaUsdt] = useState("");
  const [recargo, setRecargo] = useState("");
  const [nota, setNota] = useState("");
  const [guardando, setGuardando] = useState(false);

  const cargarHistorial = useCallback(async (paginaActual: number) => {
    setCargando(true);
    setError(null);
    try {
      const datos = await solicitarApi<TasasPaginadas>(
        `/api/tasas?pagina=${paginaActual}&por_pagina=15`
      );
      setHistorial(datos.elementos);
      setTotal(datos.total);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo cargar el historial de tasas."
      );
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void cargarHistorial(pagina);
  }, [cargarHistorial, pagina]);

  useEffect(() => {
    if (!tasaHoy) return;
    if (tasaHoy.tasa_bcv !== null) setTasaBcv(String(tasaHoy.tasa_bcv));
    if (tasaHoy.tasa_usdt !== null) setTasaUsdt(String(tasaHoy.tasa_usdt));
    if (tasaHoy.recargo_porcentaje !== null) {
      setRecargo(String(tasaHoy.recargo_porcentaje));
    }
    if (tasaHoy.nota) setNota(tasaHoy.nota);
  }, [tasaHoy]);

  const manejarGuardarHoy = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setMensajeExito(null);

    const bcvNum = Number(tasaBcv);
    const usdtNum = Number(tasaUsdt);
    const recargoNum = recargo.trim() === "" ? null : Number(recargo);

    if (!Number.isFinite(bcvNum) || bcvNum <= 0) {
      setError("Ingresa una tasa BCV válida mayor a 0.");
      return;
    }
    if (!Number.isFinite(usdtNum) || usdtNum <= 0) {
      setError("Ingresa una tasa USDT válida mayor a 0.");
      return;
    }
    if (recargoNum !== null && (!Number.isFinite(recargoNum) || recargoNum < 0)) {
      setError("El porcentaje de recargo debe ser un número mayor o igual a 0.");
      return;
    }

    setGuardando(true);
    try {
      await solicitarApi<TasaDiaria>("/api/tasas/hoy", {
        method: "PUT",
        body: JSON.stringify({
          tasa_bcv: bcvNum,
          tasa_usdt: usdtNum,
          recargo_porcentaje: recargoNum,
          nota: nota.trim(),
        }),
      });
      await Promise.all([recargarTasaHoy(), cargarHistorial(1)]);
      setPagina(1);
      setMensajeExito("Tasa del día actualizada correctamente (origen MANUAL).");
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo guardar la tasa del día."
      );
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-black text-slate-900">
          Tasas Diarias y Diferencial Cambiario
        </h2>
        <p className="text-sm text-slate-500">
          Las tasas de fechas pasadas son inmutables para preservar el historial
          financiero.
        </p>
      </div>

      {/* Alerta si falta la tasa de hoy */}
      {tasaHoy && !tasaHoy.permite_bolivares && (
        <div className="flex items-start gap-3 p-4 rounded-2xl bg-red-50 border-2 border-red-300 text-red-800">
          <AlertTriangle className="w-5 h-5 mt-0.5 shrink-0 text-red-600" />
          <div>
            <p className="font-bold text-sm">
              {tasaHoy.alerta || "Sin tasa del día — Cobros en Bs bloqueados"}
            </p>
            <p className="text-xs mt-0.5 text-red-700">
              Registra la tasa BCV y USDT de hoy ({tasaHoy.fecha}) para
              habilitar los cobros en bolívares y el cálculo de Precio Regular
              en Bs.
            </p>
          </div>
        </div>
      )}

      {/* Tarjetas de resumen del día */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-2xl border border-slate-200">
          <p className="text-xs font-bold uppercase text-slate-500">
            Tasa BCV hoy
          </p>
          <p className="text-2xl font-black text-emerald-700 mt-1">
            {formatearBs(tasaHoy?.tasa_bcv)}
          </p>
        </div>
        <div className="bg-white p-5 rounded-2xl border border-slate-200">
          <p className="text-xs font-bold uppercase text-slate-500">
            Tasa USDT hoy
          </p>
          <p className="text-2xl font-black text-sky-700 mt-1">
            {formatearBs(tasaHoy?.tasa_usdt)}
          </p>
        </div>
        <div className="bg-white p-5 rounded-2xl border border-slate-200">
          <p className="text-xs font-bold uppercase text-slate-500">
            Brecha cambiaria
          </p>
          <p className="text-2xl font-black text-slate-900 mt-1">
            {formatearPorcentaje(tasaHoy?.brecha_porcentaje)}
          </p>
        </div>
        <div className="bg-white p-5 rounded-2xl border border-slate-200">
          <p className="text-xs font-bold uppercase text-slate-500">
            Recargo del día
          </p>
          <p className="text-2xl font-black text-[#E85A28] mt-1">
            {formatearPorcentaje(tasaHoy?.recargo_porcentaje)}
          </p>
        </div>
      </div>

      {/* Formulario rápido manual (solo DIRECCION / ADMINISTRACION) */}
      {puedeEditar && (
        <div className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-[#E85A28]" />
            <h3 className="text-base font-bold text-slate-900">
              Cargar o actualizar tasa de hoy ({tasaHoy?.fecha || "Hoy"})
            </h3>
          </div>

          {error && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          {mensajeExito && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-700">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{mensajeExito}</span>
            </div>
          )}

          <form
            onSubmit={manejarGuardarHoy}
            className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end"
          >
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Tasa BCV (Bs)
              </label>
              <input
                type="number"
                step="0.0001"
                min="0.0001"
                required
                value={tasaBcv}
                onChange={(e) => setTasaBcv(e.target.value)}
                placeholder="Ej: 62.45"
                className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Tasa USDT (Bs)
              </label>
              <input
                type="number"
                step="0.0001"
                min="0.0001"
                required
                value={tasaUsdt}
                onChange={(e) => setTasaUsdt(e.target.value)}
                placeholder="Ej: 74.80"
                className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">
                % Recargo (opcional si hereda)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                max="500"
                value={recargo}
                onChange={(e) => setRecargo(e.target.value)}
                placeholder="Ej: 30"
                className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
              />
            </div>
            <div>
              <button
                type="submit"
                disabled={guardando}
                className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold disabled:opacity-60 cursor-pointer"
              >
                <Save className="w-4 h-4" />
                {guardando ? "Guardando..." : "Guardar tasa hoy"}
              </button>
            </div>
            <div className="md:col-span-4">
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Nota / observación
              </label>
              <input
                type="text"
                value={nota}
                onChange={(e) => setNota(e.target.value)}
                placeholder="Ej: Tasa apertura 8:00 am Binance P2P"
                className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
              />
            </div>
          </form>
        </div>
      )}

      {/* Tabla histórica */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wide flex items-center gap-2">
            <Calendar className="w-4 h-4 text-[#E85A28]" />
            Historial inmutable de tasas ({total})
          </h3>
        </div>

        {cargando ? (
          <div className="p-6 space-y-3">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-10 rounded-xl bg-slate-100 animate-pulse"
              />
            ))}
          </div>
        ) : historial.length === 0 ? (
          <div className="p-10 text-center">
            <p className="text-sm font-semibold text-slate-600">
              Aún no hay tasas registradas en el historial.
            </p>
            <p className="text-xs text-slate-400 mt-1">
              {puedeEditar
                ? "Usa el formulario superior para registrar la primera tasa del día."
                : "Solicita a Administración registrar la tasa del día."}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Fecha</th>
                  <th className="px-4 py-3">BCV</th>
                  <th className="px-4 py-3">USDT</th>
                  <th className="px-4 py-3">Brecha</th>
                  <th className="px-4 py-3">Recargo</th>
                  <th className="px-4 py-3">Origen</th>
                  <th className="px-4 py-3">Publicado por</th>
                  <th className="px-4 py-3">Nota</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {historial.map((t) => (
                  <tr key={t.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-bold text-slate-900">
                      {t.fecha}
                    </td>
                    <td className="px-4 py-3 text-emerald-700 font-semibold">
                      {formatearBs(t.tasa_bcv)}
                    </td>
                    <td className="px-4 py-3 text-sky-700 font-semibold">
                      {formatearBs(t.tasa_usdt)}
                    </td>
                    <td className="px-4 py-3">
                      {formatearPorcentaje(t.brecha_porcentaje)}
                    </td>
                    <td className="px-4 py-3 font-semibold text-[#C9461A]">
                      {formatearPorcentaje(t.recargo_porcentaje)}
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 text-xs font-bold">
                        {t.origen}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {t.publicado_por || "Sistema"}
                    </td>
                    <td className="px-4 py-3 text-slate-500">{t.nota || "—"}</td>
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
