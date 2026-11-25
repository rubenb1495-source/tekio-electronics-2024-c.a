"use client";

import React, { useEffect, useState } from "react";
import { AlertCircle, Calculator, Loader2, RefreshCw, ShieldCheck } from "lucide-react";
import LogoTekio from "@/components/LogoTekio";
import { usarSesion } from "@/contexto/SesionContexto";
import {
  ErrorApi,
  esRolAdministrativo,
  formatearBs,
  formatearUsd,
  solicitarApi,
} from "@/servicios/api";
import type { TasaHoy } from "@/tipos/dominio";

export default function ModalRecargoDiario() {
  const {
    usuario,
    tasaHoy,
    cargandoTasa,
    sincronizarTasaHoy,
    actualizarTasaEnContexto,
  } = usarSesion();

  const debeBloquear = Boolean(
    usuario && tasaHoy && tasaHoy.recargo_confirmado_hoy === false
  );
  const esAdmin = usuario ? esRolAdministrativo(usuario.rol) : false;
  const faltanTasas = !tasaHoy?.tasa_bcv || tasaHoy.tasa_bcv <= 0;

  const [recargoStr, setRecargoStr] = useState("");
  const [mostrarAjusteManual, setMostrarAjusteManual] = useState(false);
  const [bcvManual, setBcvManual] = useState("");
  const [usdtManual, setUsdtManual] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!debeBloquear || !tasaHoy) return;
    const sugerido =
      tasaHoy.porcentaje_recargo ?? tasaHoy.recargo_porcentaje ?? 20;
    if (recargoStr === "" && sugerido > 0) {
      setRecargoStr(String(sugerido));
    }
    if (faltanTasas && esAdmin) {
      setMostrarAjusteManual(true);
    }
  }, [debeBloquear, tasaHoy, faltanTasas, esAdmin, recargoStr]);

  // Bloquear tecla Escape mientras el modal obligatorio esté activo
  useEffect(() => {
    if (!debeBloquear) return;
    const bloquearEscape = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") {
        ev.preventDefault();
        ev.stopPropagation();
      }
    };
    window.addEventListener("keydown", bloquearEscape, true);
    return () => window.removeEventListener("keydown", bloquearEscape, true);
  }, [debeBloquear]);

  if (!debeBloquear || !tasaHoy) return null;

  const bcvEfectiva =
    mostrarAjusteManual && Number(bcvManual) > 0
      ? Number(bcvManual)
      : Number(tasaHoy.tasa_bcv || 0);
  const usdtEfectiva =
    mostrarAjusteManual && Number(usdtManual) > 0
      ? Number(usdtManual)
      : Number(tasaHoy.tasa_usdt || 0);
  const pctNum = Number(recargoStr);
  const pctValido = Number.isFinite(pctNum) && pctNum >= 0 && pctNum <= 100;
  const ejemploRegularUsd = pctValido ? 100 * (1 + pctNum / 100) : 100;
  const ejemploBs = bcvEfectiva > 0 ? ejemploRegularUsd * bcvEfectiva : 0;

  const confirmar = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    if (!pctValido) {
      setError("Ingresa un porcentaje de recargo válido entre 0% y 100%.");
      return;
    }

    const payload: Record<string, number> = {
      porcentaje_recargo: pctNum,
    };
    if (esAdmin && mostrarAjusteManual) {
      if (Number(bcvManual) > 0) payload.tasa_bcv = Number(bcvManual);
      if (Number(usdtManual) > 0) payload.tasa_usdt = Number(usdtManual);
    }

    setGuardando(true);
    try {
      const actualizada = await solicitarApi<TasaHoy>(
        "/api/finanzas/tasas/recargo-diario",
        {
          method: "POST",
          body: JSON.stringify(payload),
        }
      );
      actualizarTasaEnContexto(actualizada);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo confirmar el recargo del día."
      );
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Confirmar porcentaje de recargo del día"
      className="fixed inset-0 z-[100] bg-black/55 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div className="bg-white/95 backdrop-blur-xl border-2 border-[#E85A28]/40 shadow-[0_20px_60px_rgb(0,0,0,0.20)] rounded-2xl max-w-lg w-full p-6 space-y-5">
        {/* Encabezado corporativo */}
        <div className="flex items-start justify-between gap-3 border-b border-neutral-200/80 pb-4">
          <div className="space-y-1.5">
            <LogoTekio variante="horizontal" tema="claro" tamano="sm" />
            <h2 className="text-lg font-black text-[#191818]">
              Apertura del Día · Recargo Diario Obligatorio
            </h2>
            <p className="text-xs text-neutral-500">
              Fecha Venezuela (Caracas):{" "}
              <strong className="text-[#191818]">{tasaHoy.fecha}</strong> · Confirma
              el porcentaje de recargo para habilitar ventas y cotizaciones de hoy.
            </p>
          </div>
          <button
            type="button"
            disabled={cargandoTasa}
            onClick={() => void sincronizarTasaHoy()}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl border border-neutral-200 bg-white hover:bg-neutral-50 text-xs font-semibold text-neutral-600 cursor-pointer shrink-0"
            title="Re-sincronizar BCV y USDT"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${cargandoTasa ? "animate-spin" : ""}`}
            />
            Refrescar
          </button>
        </div>

        {/* Tasas sincronizadas automáticamente */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-neutral-50/90 border border-neutral-200/90 p-3.5">
            <p className="text-[11px] font-bold uppercase tracking-wider text-neutral-500">
              Tasa Oficial BCV
            </p>
            <p className="text-xl font-black text-[#191818] mt-0.5 tabular-nums">
              {bcvEfectiva > 0 ? formatearBs(bcvEfectiva) : "Sin conexión"}
            </p>
            <p className="text-[10px] text-neutral-400 mt-0.5">
              Fuente: {tasaHoy.fuente || "automática"}
            </p>
          </div>
          <div className="rounded-xl bg-neutral-50/90 border border-neutral-200/90 p-3.5">
            <p className="text-[11px] font-bold uppercase tracking-wider text-neutral-500">
              Tasa USDT / Paralelo
            </p>
            <p className="text-xl font-black text-[#191818] mt-0.5 tabular-nums">
              {usdtEfectiva > 0 ? formatearBs(usdtEfectiva) : "Sin conexión"}
            </p>
            <p className="text-[10px] text-neutral-400 mt-0.5">
              Sincronizada automáticamente
            </p>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={confirmar} className="space-y-4">
          <div>
            <label className="block text-xs font-bold text-[#191818] mb-1.5">
              Porcentaje de Recargo del Día (%) *
            </label>
            <div className="relative">
              <input
                type="number"
                step="0.01"
                min={0}
                max={100}
                required
                autoFocus
                value={recargoStr}
                onChange={(e) => setRecargoStr(e.target.value)}
                placeholder="Ej. 20"
                className="w-full px-4 py-3 pr-10 rounded-xl border-2 border-[#E85A28]/40 focus:border-[#E85A28] focus:outline-none text-lg font-black text-[#191818] tabular-nums bg-white"
              />
              <span className="absolute right-3.5 top-1/2 -translate-y-1/2 text-sm font-black text-[#E85A28]">
                %
              </span>
            </div>
          </div>

          {/* Ejemplo en vivo ($100 Promo -> Regular USD y Bs) */}
          <div className="rounded-xl bg-[#FDF0EB]/80 border border-[#E85A28]/25 p-3.5 space-y-1">
            <p className="text-[11px] font-bold uppercase tracking-wide text-[#E85A28] flex items-center gap-1.5">
              <Calculator className="w-3.5 h-3.5" />
              Vista previa en vivo (Equipo de $100.00 Promo)
            </p>
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-[#191818] pt-1">
              <span>
                Precio Regular:{" "}
                <strong className="tabular-nums">
                  {formatearUsd(ejemploRegularUsd)} USD
                </strong>
              </span>
              <span>
                Equivalente Bs (BCV):{" "}
                <strong className="tabular-nums text-[#E85A28]">
                  {ejemploBs > 0 ? formatearBs(ejemploBs) : "—"}
                </strong>
              </span>
            </div>
          </div>

          {/* Ajuste manual de emergencia (solo Dirección / Administración) */}
          {esAdmin && (
            <div className="space-y-2">
              <button
                type="button"
                onClick={() => setMostrarAjusteManual((prev) => !prev)}
                className="text-xs font-semibold text-neutral-500 hover:text-[#191818] underline cursor-pointer"
              >
                {mostrarAjusteManual
                  ? "Ocultar ajuste manual de emergencia"
                  : "¿Ajuste manual de emergencia de BCV / USDT? (Solo Admin)"}
              </button>
              {mostrarAjusteManual && (
                <div className="grid grid-cols-2 gap-3 p-3 rounded-xl bg-neutral-50 border border-neutral-200">
                  <div>
                    <label className="block text-[11px] font-bold text-neutral-600 mb-1">
                      BCV manual (Bs)
                    </label>
                    <input
                      type="number"
                      step="0.0001"
                      min={0}
                      value={bcvManual}
                      onChange={(e) => setBcvManual(e.target.value)}
                      placeholder={String(tasaHoy.tasa_bcv || "")}
                      className="w-full px-3 py-2 rounded-lg border border-neutral-300 text-xs tabular-nums bg-white"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-bold text-neutral-600 mb-1">
                      USDT manual (Bs)
                    </label>
                    <input
                      type="number"
                      step="0.0001"
                      min={0}
                      value={usdtManual}
                      onChange={(e) => setUsdtManual(e.target.value)}
                      placeholder={String(tasaHoy.tasa_usdt || "")}
                      className="w-full px-3 py-2 rounded-lg border border-neutral-300 text-xs tabular-nums bg-white"
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          <button
            type="submit"
            disabled={guardando || !pctValido}
            className="w-full inline-flex items-center justify-center gap-2 py-3 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] disabled:opacity-50 text-white text-sm font-black shadow-sm transition-colors cursor-pointer"
          >
            {guardando ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <ShieldCheck className="w-4 h-4" />
            )}
            {guardando ? "Confirmando..." : "Confirmar Recargo del Día"}
          </button>
        </form>
      </div>
    </div>
  );
}
