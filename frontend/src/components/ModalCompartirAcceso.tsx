"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  Copy,
  KeyRound,
  MessageCircle,
  RefreshCw,
  Share2,
  ShieldCheck,
  X,
} from "lucide-react";
import {
  construirEnlaceWhatsAppDirecto,
  copiarTextoPortapapeles,
  formatearAccesoUsuario,
} from "@/lib/whatsapp";
import { ErrorApi, solicitarApi } from "@/servicios/api";
import type { AccesoTemporalUsuario, Usuario } from "@/tipos/dominio";

interface ModalCompartirAccesoProps {
  abierto: boolean;
  usuarioObjetivo: Usuario | null;
  accesoInicial: AccesoTemporalUsuario | null;
  alCerrar: () => void;
  alRegenerar?: () => void;
}

export default function ModalCompartirAcceso({
  abierto,
  usuarioObjetivo,
  accesoInicial,
  alCerrar,
  alRegenerar,
}: ModalCompartirAccesoProps) {
  const [acceso, setAcceso] = useState<AccesoTemporalUsuario | null>(accesoInicial);
  const [generando, setGenerando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiado, setCopiado] = useState(false);

  useEffect(() => {
    setAcceso(accesoInicial);
    setError(null);
    setCopiado(false);
  }, [accesoInicial, usuarioObjetivo, abierto]);

  const mensajeWhatsApp = useMemo(() => {
    if (!acceso) return "";
    return formatearAccesoUsuario(acceso);
  }, [acceso]);

  const enlaceWhatsApp = useMemo(() => {
    if (!acceso) return "";
    return construirEnlaceWhatsAppDirecto(mensajeWhatsApp, acceso.telefono);
  }, [acceso, mensajeWhatsApp]);

  if (!abierto || (!usuarioObjetivo && !acceso)) return null;

  const nombreMostrar = acceso?.nombre || usuarioObjetivo?.nombre || "Usuario";

  const manejarGenerarTemporal = async () => {
    if (!usuarioObjetivo) return;
    setGenerando(true);
    setError(null);
    try {
      const resp = await solicitarApi<AccesoTemporalUsuario>(
        `/api/usuarios/${usuarioObjetivo.id}/generar-acceso-temporal`,
        { method: "POST" }
      );
      setAcceso(resp);
      if (alRegenerar) alRegenerar();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo generar la contraseña temporal."
      );
    } finally {
      setGenerando(false);
    }
  };

  const manejarCopiar = async () => {
    if (!mensajeWhatsApp) return;
    const ok = await copiarTextoPortapapeles(mensajeWhatsApp);
    if (ok) {
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2500);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/45 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="w-full max-w-lg rounded-2xl bg-white/95 backdrop-blur-xl border border-white/70 shadow-2xl overflow-hidden">
        {/* Cabecera */}
        <div className="px-5 py-4 border-b border-neutral-100 flex items-center justify-between bg-[#F6F6F6]/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-[#FDF0EB] text-[#E85A28] flex items-center justify-center">
              <Share2 className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-black text-[#191818]">
                Compartir acceso al sistema
              </h3>
              <p className="text-[11px] text-neutral-500">
                {nombreMostrar}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={alCerrar}
            className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100 cursor-pointer"
            aria-label="Cerrar modal"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {error && (
            <div className="flex items-start gap-2 p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {!acceso ? (
            <div className="space-y-4">
              <div className="rounded-xl border border-amber-200 bg-amber-50/80 p-4 space-y-1.5">
                <div className="flex items-center gap-2 text-xs font-bold text-amber-900">
                  <KeyRound className="w-4 h-4 text-[#E85A28]" />
                  <span>Se generará una nueva contraseña temporal</span>
                </div>
                <p className="text-xs text-amber-800 leading-relaxed">
                  Por seguridad, las contraseñas actuales están encriptadas y no se pueden consultar.
                  Al continuar se generará una <strong>nueva contraseña temporal</strong> para{" "}
                  <strong>{nombreMostrar}</strong> (y si su cuenta estaba bloqueada, quedará desbloqueada automáticamente).
                </p>
              </div>

              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={alCerrar}
                  className="px-4 py-2 rounded-xl border border-neutral-200 text-xs font-bold text-neutral-600 hover:bg-neutral-50 cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="button"
                  disabled={generando}
                  onClick={() => void manejarGenerarTemporal()}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] disabled:opacity-60 text-white text-xs font-bold shadow-sm cursor-pointer"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${generando ? "animate-spin" : ""}`} />
                  {generando ? "Generando credenciales..." : "Generar y preparar mensaje"}
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center gap-2 rounded-xl bg-emerald-50 border border-emerald-200 px-3.5 py-2.5 text-xs text-emerald-800 font-semibold">
                <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>
                  Credenciales listas para compartir. Esta clave se muestra una sola vez.
                </span>
              </div>

              {/* Resumen visual rápido */}
              <div className="grid grid-cols-2 gap-2.5 text-xs">
                <div className="rounded-xl bg-[#F6F6F6] border border-neutral-200/80 p-3">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-neutral-400">
                    Usuario
                  </p>
                  <p className="font-mono font-bold text-[#191818] mt-0.5 truncate">
                    {acceso.username}
                  </p>
                </div>
                <div className="rounded-xl bg-[#FDF0EB]/70 border border-[#E85A28]/25 p-3">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-[#E85A28]">
                    Contraseña temporal
                  </p>
                  <p className="font-mono font-black text-[#191818] mt-0.5 tracking-wide">
                    {acceso.password_temporal}
                  </p>
                </div>
              </div>

              {/* Vista previa del mensaje */}
              <div className="space-y-1.5">
                <p className="text-[11px] font-bold uppercase tracking-wider text-neutral-500">
                  Vista previa del mensaje
                </p>
                <pre className="whitespace-pre-wrap font-sans text-xs text-[#191818] bg-[#F6F6F6]/90 border border-neutral-200 rounded-xl p-3.5 leading-relaxed max-h-56 overflow-y-auto">
                  {mensajeWhatsApp}
                </pre>
              </div>

              {/* Acciones rápidas */}
              <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => void manejarCopiar()}
                  className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl border border-neutral-300 bg-white hover:bg-neutral-50 text-[#191818] text-xs font-bold cursor-pointer transition-colors"
                >
                  {copiado ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-emerald-600" />
                      <span className="text-emerald-700">¡Copiado!</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5 text-[#E85A28]" />
                      <span>Copiar credenciales</span>
                    </>
                  )}
                </button>
                <a
                  href={enlaceWhatsApp}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold shadow-sm transition-colors"
                >
                  <MessageCircle className="w-3.5 h-3.5" />
                  <span>Enviar por WhatsApp</span>
                </a>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
