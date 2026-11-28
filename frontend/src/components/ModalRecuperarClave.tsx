"use client";

import React, { useState } from "react";
import { AlertCircle, CheckCircle2, KeyRound, Mail, X } from "lucide-react";
import { ErrorApi, solicitarApi } from "@/servicios/api";

export default function ModalRecuperarClave({
  abierto,
  alCerrar,
  colorPrimario = "#E85A28",
  colorHover = "#D14D1F",
}: {
  abierto: boolean;
  alCerrar: () => void;
  colorPrimario?: string;
  colorHover?: string;
}) {
  const [usuario, setUsuario] = useState("");
  const [codigo, setCodigo] = useState("");
  const [nuevaClave, setNuevaClave] = useState("");
  const [confirmarClave, setConfirmarClave] = useState("");
  const [pasoCodigo, setPasoCodigo] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mensajeExito, setMensajeExito] = useState<string | null>(null);

  if (!abierto) return null;

  const reiniciarYCerrar = () => {
    setUsuario("");
    setCodigo("");
    setNuevaClave("");
    setConfirmarClave("");
    setPasoCodigo(false);
    setError(null);
    setMensajeExito(null);
    alCerrar();
  };

  const solicitar = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setMensajeExito(null);
    if (!usuario.trim()) {
      setError("Ingresa tu nombre de usuario.");
      return;
    }
    setEnviando(true);
    try {
      const res = await solicitarApi<{
        enviado_correo: boolean;
        requiere_codigo: boolean;
        mensaje: string;
      }>("/api/auth/solicitar-recuperacion", {
        method: "POST",
        body: JSON.stringify({ usuario: usuario.trim() }),
      });
      setMensajeExito(res.mensaje);
      if (res.requiere_codigo) {
        setPasoCodigo(true);
      }
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo procesar la solicitud de recuperación."
      );
    } finally {
      setEnviando(false);
    }
  };

  const confirmar = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    if (nuevaClave.length < 6) {
      setError("La nueva clave debe tener al menos 6 caracteres.");
      return;
    }
    if (nuevaClave !== confirmarClave) {
      setError("Las contraseñas no coinciden.");
      return;
    }
    setEnviando(true);
    try {
      const res = await solicitarApi<{ mensaje: string }>(
        "/api/auth/confirmar-recuperacion",
        {
          method: "POST",
          body: JSON.stringify({
            usuario: usuario.trim(),
            codigo: codigo.trim(),
            nueva_clave: nuevaClave,
          }),
        }
      );
      setMensajeExito(res.mensaje);
      setPasoCodigo(false);
      setCodigo("");
      setNuevaClave("");
      setConfirmarClave("");
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo restablecer la contraseña."
      );
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="w-full max-w-md rounded-2xl bg-white border border-slate-200 shadow-2xl overflow-hidden">
        <div
          className="px-5 py-4 text-white flex items-center justify-between"
          style={{ backgroundColor: colorPrimario }}
        >
          <div className="flex items-center gap-2">
            <KeyRound className="w-5 h-5" />
            <div>
              <h3 className="text-sm font-black">Recuperar Acceso</h3>
              <p className="text-[11px] text-white/80">
                Restablecimiento por correo o solicitud a Administración
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={reiniciarYCerrar}
            className="p-1.5 rounded-lg hover:bg-white/10 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {error && (
            <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {mensajeExito && (
            <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-900 flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-emerald-700" />
              <span>{mensajeExito}</span>
            </div>
          )}

          {!pasoCodigo ? (
            <form onSubmit={solicitar} className="space-y-4">
              <div>
                <label className="block text-xs font-bold uppercase text-slate-700 mb-1">
                  Tu nombre de usuario *
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    required
                    value={usuario}
                    onChange={(e) => setUsuario(e.target.value)}
                    placeholder="Ej. admin o Carlos Mendoza"
                    className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-300 text-sm"
                  />
                </div>
                <p className="text-[11px] text-slate-500 mt-1.5">
                  Si tienes correo activo recibirás un código de 15 minutos; de lo contrario,
                  notificaremos automáticamente a Dirección / Administración.
                </p>
              </div>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={reiniciarYCerrar}
                  className="px-4 py-2 rounded-xl border border-slate-300 text-xs font-bold text-slate-700 cursor-pointer"
                >
                  Cerrar
                </button>
                <button
                  type="submit"
                  disabled={enviando}
                  style={{ backgroundColor: colorPrimario }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = colorHover)}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = colorPrimario)}
                  className="px-4 py-2 rounded-xl text-white text-xs font-black disabled:opacity-50 cursor-pointer"
                >
                  {enviando ? "Procesando..." : "Solicitar Recuperación"}
                </button>
              </div>
            </form>
          ) : (
            <form onSubmit={confirmar} className="space-y-3">
              <div>
                <label className="block text-xs font-bold uppercase text-slate-700 mb-1">
                  Código de 6 dígitos recibido *
                </label>
                <input
                  type="text"
                  required
                  value={codigo}
                  onChange={(e) => setCodigo(e.target.value)}
                  placeholder="123456"
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm font-mono tracking-widest"
                />
              </div>
              <div>
                <label className="block text-xs font-bold uppercase text-slate-700 mb-1">
                  Nueva contraseña *
                </label>
                <input
                  type="password"
                  required
                  minLength={6}
                  value={nuevaClave}
                  onChange={(e) => setNuevaClave(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-bold uppercase text-slate-700 mb-1">
                  Confirmar contraseña *
                </label>
                <input
                  type="password"
                  required
                  minLength={6}
                  value={confirmarClave}
                  onChange={(e) => setConfirmarClave(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>
              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={reiniciarYCerrar}
                  className="px-4 py-2 rounded-xl border border-slate-300 text-xs font-bold text-slate-700 cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={enviando}
                  style={{ backgroundColor: colorPrimario }}
                  className="px-4 py-2 rounded-xl text-white text-xs font-black disabled:opacity-50 cursor-pointer"
                >
                  {enviando ? "Guardando..." : "Restablecer Clave"}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
