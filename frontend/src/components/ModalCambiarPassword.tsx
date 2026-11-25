"use client";

import React, { useState } from "react";
import { AlertCircle, CheckCircle2, Eye, EyeOff, KeyRound, X } from "lucide-react";
import { extraerMensajeError, solicitarApi } from "@/servicios/api";

export default function ModalCambiarPassword({
  abierto,
  alCerrar,
}: {
  abierto: boolean;
  alCerrar: () => void;
}) {
  const [claveActual, setClaveActual] = useState("");
  const [claveNueva, setClaveNueva] = useState("");
  const [confirmacion, setConfirmacion] = useState("");
  const [verActual, setVerActual] = useState(false);
  const [verNueva, setVerNueva] = useState(false);
  const [verConf, setVerConf] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  if (!abierto) return null;

  const manejarGuardar = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setExito(null);

    if (claveNueva.length < 8) {
      setError("La nueva contraseña debe tener al menos 8 caracteres.");
      return;
    }
    if (claveNueva !== confirmacion) {
      setError("La confirmación no coincide con la nueva contraseña.");
      return;
    }

    setGuardando(true);
    try {
      const res = await solicitarApi<{ mensaje: string }>("/api/auth/cambiar-password", {
        method: "POST",
        body: JSON.stringify({
          clave_actual: claveActual,
          clave_nueva: claveNueva,
          confirmar_clave: confirmacion,
        }),
      });
      setExito(res.mensaje || "Contraseña actualizada correctamente.");
      setClaveActual("");
      setClaveNueva("");
      setConfirmacion("");
    } catch (err) {
      setError(extraerMensajeError(err, "No se pudo cambiar la contraseña."));
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="w-full max-w-md rounded-2xl bg-white/95 backdrop-blur-xl border border-neutral-200 shadow-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-neutral-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <KeyRound className="w-4 h-4 text-[#E85A28]" />
            <h3 className="text-sm font-black text-[#191818]">
              Cambiar contraseña
            </h3>
          </div>
          <button
            type="button"
            onClick={alCerrar}
            className="p-1 rounded-lg hover:bg-neutral-100 text-neutral-500 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={manejarGuardar} className="p-5 space-y-3.5">
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

          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Contraseña actual
            </label>
            <div className="relative">
              <input
                type={verActual ? "text" : "password"}
                required
                value={claveActual}
                onChange={(e) => setClaveActual(e.target.value)}
                className="w-full pl-3 pr-9 py-2 rounded-xl border border-neutral-300 text-sm"
              />
              <button
                type="button"
                onClick={() => setVerActual((v) => !v)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-700 cursor-pointer"
                aria-label="Ver u ocultar contraseña actual"
              >
                {verActual ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Nueva contraseña (mínimo 8 caracteres)
            </label>
            <div className="relative">
              <input
                type={verNueva ? "text" : "password"}
                required
                minLength={8}
                value={claveNueva}
                onChange={(e) => setClaveNueva(e.target.value)}
                className="w-full pl-3 pr-9 py-2 rounded-xl border border-neutral-300 text-sm"
              />
              <button
                type="button"
                onClick={() => setVerNueva((v) => !v)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-700 cursor-pointer"
                aria-label="Ver u ocultar nueva contraseña"
              >
                {verNueva ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Confirmar nueva contraseña
            </label>
            <div className="relative">
              <input
                type={verConf ? "text" : "password"}
                required
                minLength={8}
                value={confirmacion}
                onChange={(e) => setConfirmacion(e.target.value)}
                className="w-full pl-3 pr-9 py-2 rounded-xl border border-neutral-300 text-sm"
              />
              <button
                type="button"
                onClick={() => setVerConf((v) => !v)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-700 cursor-pointer"
                aria-label="Ver u ocultar confirmación"
              >
                {verConf ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={alCerrar}
              className="px-4 py-2 rounded-xl border border-neutral-200 text-xs font-bold text-neutral-600 cursor-pointer"
            >
              Cerrar
            </button>
            <button
              type="submit"
              disabled={guardando}
              className="px-4 py-2 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-xs font-bold cursor-pointer disabled:opacity-50"
            >
              {guardando ? "Actualizando..." : "Guardar clave"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
