"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Lock, Mail, ShieldCheck } from "lucide-react";
import { usarSesion } from "@/contexto/SesionContexto";
import { ErrorApi } from "@/servicios/api";

export default function PaginaLogin() {
  const { usuario, cargandoSesion, iniciarSesion } = usarSesion();
  const router = useRouter();

  const [correo, setCorreo] = useState("");
  const [clave, setClave] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!cargandoSesion && usuario) {
      router.replace("/dashboard/tasas");
    }
  }, [usuario, cargandoSesion, router]);

  const manejarEnvio = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    if (!correo.trim() || !clave) {
      setError("Ingresa tu correo electrónico y tu clave de acceso.");
      return;
    }

    setEnviando(true);
    try {
      await iniciarSesion(correo.trim(), clave);
      router.replace("/dashboard/tasas");
    } catch (err) {
      if (err instanceof ErrorApi) {
        setError(err.message);
      } else {
        setError("Ocurrió un error inesperado al iniciar sesión.");
      }
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100 p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-lg border border-slate-200 overflow-hidden">
        <div className="bg-gradient-to-br from-[#E85A28] to-[#C9461A] p-6 text-white">
          <div className="flex items-center gap-2.5 mb-2">
            <ShieldCheck className="w-6 h-6" />
            <span className="text-xs font-bold uppercase tracking-widest text-orange-100">
              Sistema Administrativo
            </span>
          </div>
          <h1 className="text-2xl font-black tracking-tight">
            TEKIO ELECTRONICS
          </h1>
          <p className="text-xs text-orange-100 mt-1">
            TEKIO ELECTRONICS 2024, C.A. · RIF J-50637518-4
          </p>
        </div>

        <form onSubmit={manejarEnvio} className="p-6 space-y-4">
          {error && (
            <div className="flex items-start gap-2.5 rounded-xl bg-red-50 border border-red-200 p-3 text-sm text-red-700">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div>
            <label
              htmlFor="correo"
              className="block text-xs font-bold text-slate-700 uppercase tracking-wide mb-1.5"
            >
              Correo electrónico
            </label>
            <div className="relative">
              <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                id="correo"
                type="email"
                required
                autoComplete="email"
                value={correo}
                onChange={(e) => setCorreo(e.target.value)}
                placeholder="usuario@tekioelectronics.com"
                className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-[#E85A28]/30 focus:border-[#E85A28]"
              />
            </div>
          </div>

          <div>
            <label
              htmlFor="clave"
              className="block text-xs font-bold text-slate-700 uppercase tracking-wide mb-1.5"
            >
              Clave de acceso
            </label>
            <div className="relative">
              <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                id="clave"
                type="password"
                required
                autoComplete="current-password"
                value={clave}
                onChange={(e) => setClave(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-[#E85A28]/30 focus:border-[#E85A28]"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={enviando}
            className="w-full py-2.5 px-4 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] disabled:opacity-60 text-white font-bold text-sm transition-colors cursor-pointer"
          >
            {enviando ? "Validando credenciales..." : "Iniciar sesión"}
          </button>
        </form>
      </div>
    </div>
  );
}
