"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowRight, Lock, Mail } from "lucide-react";
import LogoTekio from "@/components/LogoTekio";
import { usarSesion } from "@/contexto/SesionContexto";
import { ErrorApi, solicitarApi } from "@/servicios/api";

export default function PaginaLogin() {
  const { usuario, cargandoSesion, iniciarSesion } = usarSesion();
  const router = useRouter();

  const [correo, setCorreo] = useState("");
  const [clave, setClave] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Recuperación de contraseña olvidada
  const [modalRec, setModalRec] = useState(false);
  const [usuarioRec, setUsuarioRec] = useState("");
  const [codigoRec, setCodigoRec] = useState("");
  const [nuevaClaveRec, setNuevaClaveRec] = useState("");
  const [confClaveRec, setConfClaveRec] = useState("");
  const [enviandoRec, setEnviandoRec] = useState(false);
  const [recError, setRecError] = useState<string | null>(null);
  const [recEstado, setRecEstado] = useState<{ modo: string; mensaje: string } | null>(null);

  const solicitarRecuperacion = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setRecError(null);
    setRecEstado(null);
    setEnviandoRec(true);
    try {
      const resp = await solicitarApi<{ modo: string; mensaje: string }>(
        "/api/auth/solicitar-recuperacion",
        {
          method: "POST",
          body: JSON.stringify({ usuario: usuarioRec.trim() }),
        }
      );
      setRecEstado(resp);
    } catch (err) {
      setRecError(
        err instanceof ErrorApi ? err.message : "No se pudo procesar la solicitud."
      );
    } finally {
      setEnviandoRec(false);
    }
  };

  const confirmarRecuperacion = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setRecError(null);
    setEnviandoRec(true);
    try {
      const resp = await solicitarApi<{ mensaje: string }>(
        "/api/auth/confirmar-recuperacion",
        {
          method: "POST",
          body: JSON.stringify({
            usuario: usuarioRec.trim(),
            codigo: codigoRec.trim(),
            nueva_clave: nuevaClaveRec,
            confirmar_clave: confClaveRec,
          }),
        }
      );
      setRecEstado({ modo: "COMPLETADO", mensaje: resp.mensaje });
      setCodigoRec("");
      setNuevaClaveRec("");
      setConfClaveRec("");
    } catch (err) {
      setRecError(
        err instanceof ErrorApi ? err.message : "No se pudo restablecer la contraseña."
      );
    } finally {
      setEnviandoRec(false);
    }
  };

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

            <div className="text-center pt-1">
              <button
                type="button"
                onClick={() => {
                  setModalRec(true);
                  setUsuarioRec(correo);
                  setRecEstado(null);
                  setRecError(null);
                }}
                className="text-xs font-bold text-[#E85A28] hover:underline cursor-pointer"
              >
                ¿Olvidaste tu contraseña?
              </button>
            </div>
          </form>

          {modalRec && (
            <div className="rounded-2xl border border-[#E85A28]/35 bg-[#FDF0EB]/70 p-4 space-y-3 text-xs">
              <div className="flex items-center justify-between">
                <p className="font-black text-[#191818]">Recuperar acceso</p>
                <button
                  type="button"
                  onClick={() => setModalRec(false)}
                  className="text-neutral-500 hover:text-[#191818] font-bold cursor-pointer"
                >
                  Cerrar
                </button>
              </div>
              {recError && (
                <div className="p-2.5 rounded-xl bg-red-50 border border-red-200 text-red-700 font-semibold">
                  {recError}
                </div>
              )}
              {recEstado?.mensaje && (
                <div className="p-2.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 font-semibold">
                  {recEstado.mensaje}
                </div>
              )}

              {recEstado?.modo !== "SMTP" ? (
                <form onSubmit={solicitarRecuperacion} className="space-y-2.5">
                  <input
                    type="text"
                    required
                    value={usuarioRec}
                    onChange={(e) => setUsuarioRec(e.target.value)}
                    placeholder="Ingresa tu nombre de usuario"
                    className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-xs text-[#191818]"
                  />
                  <button
                    type="submit"
                    disabled={enviandoRec}
                    className="w-full py-2 rounded-xl bg-[#E85A28] hover:bg-[#D14D20] disabled:opacity-50 text-white font-bold cursor-pointer"
                  >
                    {enviandoRec ? "Enviando solicitud..." : "Solicitar recuperación"}
                  </button>
                </form>
              ) : (
                <form onSubmit={confirmarRecuperacion} className="space-y-2">
                  <input
                    type="text"
                    required
                    value={codigoRec}
                    onChange={(e) => setCodigoRec(e.target.value)}
                    placeholder="Código de 6 dígitos enviado al correo"
                    className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white font-mono text-xs"
                  />
                  <input
                    type="password"
                    required
                    minLength={8}
                    value={nuevaClaveRec}
                    onChange={(e) => setNuevaClaveRec(e.target.value)}
                    placeholder="Nueva contraseña (mínimo 8 caracteres)"
                    className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-xs"
                  />
                  <input
                    type="password"
                    required
                    minLength={8}
                    value={confClaveRec}
                    onChange={(e) => setConfClaveRec(e.target.value)}
                    placeholder="Confirmar nueva contraseña"
                    className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-xs"
                  />
                  <button
                    type="submit"
                    disabled={enviandoRec}
                    className="w-full py-2 rounded-xl bg-[#E85A28] hover:bg-[#D14D20] disabled:opacity-50 text-white font-bold cursor-pointer"
                  >
                    {enviandoRec ? "Restableciendo..." : "Confirmar nueva contraseña"}
                  </button>
                </form>
              )}
            </div>
          )}

          <p className="text-center text-[11px] text-neutral-400 pt-1">
            Valencia, Edo. Carabobo · Venezuela
          </p>
        </div>
      </div>
    </div>
  );
}
