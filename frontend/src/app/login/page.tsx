"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowRight, Lock, Mail } from "lucide-react";
import LogoTekio from "@/components/LogoTekio";
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
      setError("Ingresa tu nombre de usuario o correo y tu clave de acceso.");
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
    <div className="min-h-screen relative flex items-center justify-center p-4 sm:p-8 overflow-hidden">
      {/* Marca de agua ambiental sutil */}
      <div
        aria-hidden="true"
        className="pointer-events-none select-none fixed inset-0 flex items-center justify-center opacity-[0.04]"
      >
        <img
          src="/brand/tekio-isotipo.png"
          alt=""
          className="w-[460px] h-[460px] object-contain"
        />
      </div>

      {/* Tarjeta translúcida corporativa */}
      <div className="relative z-10 w-full max-w-md rounded-3xl bg-white/80 backdrop-blur-xl border border-white/70 shadow-xl overflow-hidden">
        {/* Acento gráfico superior en Naranja Tekio (#E85A28) */}
        <div className="h-1.5 w-full bg-[#E85A28]" />

        <div className="p-7 sm:p-9 space-y-6">
          <div className="text-center space-y-3">
            <div className="flex justify-center">
              <LogoTekio variante="horizontal" tema="claro" tamano="lg" />
            </div>
            <div className="space-y-1">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#FDF0EB] text-[#E85A28] text-[11px] font-bold uppercase tracking-wider">
                Sistema Administrativo
              </span>
              <p className="text-xs font-medium text-neutral-500">
                Somos tu solución · TEKIO ELECTRONICS 2024, C.A. (RIF
                J-50637518-4)
              </p>
            </div>
          </div>

          <form onSubmit={manejarEnvio} className="space-y-4">
            {error && (
              <div
                className={`flex items-start gap-2.5 rounded-xl p-3.5 text-sm ${
                  error.toLowerCase().includes("bloquead")
                    ? "bg-red-600 text-white border border-red-700 font-bold shadow-sm"
                    : "bg-red-50/90 border border-red-200 text-red-700"
                }`}
              >
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div className="space-y-1.5">
              <label
                htmlFor="correo"
                className="block text-xs font-bold text-[#191818] uppercase tracking-wider"
              >
                Usuario (Nombre) o Correo
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-neutral-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  id="correo"
                  type="text"
                  required
                  autoComplete="username"
                  value={correo}
                  onChange={(e) => setCorreo(e.target.value)}
                  placeholder="Tu nombre de usuario (o correo)"
                  className="w-full pl-10 pr-3.5 py-2.5 rounded-xl border border-neutral-200 bg-white/90 text-sm text-[#191818] placeholder:text-neutral-400"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="clave"
                className="block text-xs font-bold text-[#191818] uppercase tracking-wider"
              >
                Clave de acceso
              </label>
              <div className="relative">
                <Lock className="w-4 h-4 text-neutral-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  id="clave"
                  type="password"
                  required
                  autoComplete="current-password"
                  value={clave}
                  onChange={(e) => setClave(e.target.value)}
                  placeholder="••••••••"
                  className="w-full pl-10 pr-3.5 py-2.5 rounded-xl border border-neutral-200 bg-white/90 text-sm text-[#191818] placeholder:text-neutral-400"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={enviando}
              className="w-full inline-flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] disabled:opacity-60 text-white font-bold text-sm shadow-sm transition-colors cursor-pointer"
            >
              <span>
                {enviando ? "Validando credenciales..." : "Ingresar al sistema"}
              </span>
              {!enviando && <ArrowRight className="w-4 h-4" />}
            </button>
          </form>

          <p className="text-center text-[11px] text-neutral-400 pt-1">
            Valencia, Edo. Carabobo · Venezuela
          </p>
        </div>
      </div>
    </div>
  );
}
