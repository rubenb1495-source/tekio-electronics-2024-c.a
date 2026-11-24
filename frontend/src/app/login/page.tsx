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
    <div className="min-h-screen grid grid-cols-1 lg:grid-cols-12 bg-[#FFFFFF]">
      {/* Panel izquierdo: Identidad Tekio Carbón (#191818) */}
      <section className="lg:col-span-5 xl:col-span-6 bg-[#191818] text-white flex flex-col justify-between p-8 sm:p-12 lg:p-16 relative overflow-hidden">
        {/* Acento superior en Naranja Tekio (#E85A28) */}
        <div className="absolute top-0 left-0 right-0 h-1.5 bg-[#E85A28]" />

        <div className="flex items-center justify-between">
          <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#242323] border border-[#2E2D2D] text-[11px] font-medium tracking-wider uppercase text-neutral-300">
            <span className="w-2 h-2 rounded-full bg-[#E85A28]" />
            Sistema Administrativo
          </span>
          <span className="text-[11px] font-medium text-neutral-500">
            RIF J-50637518-4
          </span>
        </div>

        <div className="my-12 lg:my-0 flex flex-col items-center lg:items-start text-center lg:text-left space-y-6">
          <LogoTekio variante="vertical" tema="oscuro" tamano="lg" />

          <div className="space-y-2 max-w-md">
            <div className="h-1 w-12 bg-[#E85A28] mx-auto lg:mx-0 rounded-full" />
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
              Somos tu solución
            </h1>
            <p className="text-sm text-neutral-400 leading-relaxed font-light">
              Plataforma operativa centralizada de inventario por serial,
              logística de importación, taller técnico, ventas multimoneda y
              finanzas.
            </p>
          </div>
        </div>

        <div className="pt-6 border-t border-[#2E2D2D] flex flex-wrap items-center justify-between gap-2 text-xs text-neutral-500">
          <span>TEKIO ELECTRONICS 2024, C.A.</span>
          <span>Valencia, Edo. Carabobo · Venezuela</span>
        </div>
      </section>

      {/* Panel derecho: Formulario limpio sobre #FFFFFF */}
      <section className="lg:col-span-7 xl:col-span-6 bg-[#FFFFFF] flex items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-md space-y-8">
          <div className="space-y-2">
            <div className="lg:hidden mb-4">
              <LogoTekio variante="horizontal" tema="claro" tamano="md" />
            </div>
            <h2 className="text-2xl font-bold tracking-tight text-[#191818]">
              Iniciar sesión
            </h2>
            <p className="text-sm text-neutral-500">
              Ingresa tus credenciales corporativas para acceder al panel.
            </p>
          </div>

          <form onSubmit={manejarEnvio} className="space-y-5">
            {error && (
              <div className="flex items-start gap-2.5 rounded-xl bg-red-50 border border-red-200 p-3.5 text-sm text-red-700">
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div className="space-y-1.5">
              <label
                htmlFor="correo"
                className="block text-xs font-bold text-[#191818] uppercase tracking-wider"
              >
                Correo electrónico
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-neutral-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  id="correo"
                  type="email"
                  required
                  autoComplete="email"
                  value={correo}
                  onChange={(e) => setCorreo(e.target.value)}
                  placeholder="usuario@tekioelectronics.com"
                  className="w-full pl-10 pr-3.5 py-3 rounded-xl border border-neutral-300 bg-white text-sm text-[#191818] placeholder:text-neutral-400"
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
                  className="w-full pl-10 pr-3.5 py-3 rounded-xl border border-neutral-300 bg-white text-sm text-[#191818] placeholder:text-neutral-400"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={enviando}
              className="w-full inline-flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] disabled:opacity-60 text-white font-bold text-sm transition-colors cursor-pointer"
            >
              <span>
                {enviando ? "Validando credenciales..." : "Ingresar al sistema"}
              </span>
              {!enviando && <ArrowRight className="w-4 h-4" />}
            </button>
          </form>

          <p className="text-center text-xs text-neutral-400">
            Acceso exclusivo para personal autorizado de Tekio Electronics.
          </p>
        </div>
      </section>
    </div>
  );
}
