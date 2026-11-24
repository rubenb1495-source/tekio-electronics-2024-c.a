"use client";

import React, { useEffect, useState } from "react";

const CLAVE_SESION_SPLASH = "tekio_splash_visto";

/**
 * Animación breve (~1.3s) del isotipo de Tekio al abrir la aplicación
 * (una sola vez por sesión, respeta prefers-reduced-motion y no bloquea la carga).
 */
export default function SplashTekio() {
  const [visible, setVisible] = useState(false);
  const [saliendo, setSaliendo] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const prefiereReducido = window.matchMedia?.(
      "(prefers-reduced-motion: reduce)"
    ).matches;
    if (prefiereReducido) return;

    try {
      if (window.sessionStorage.getItem(CLAVE_SESION_SPLASH) === "1") {
        return;
      }
      window.sessionStorage.setItem(CLAVE_SESION_SPLASH, "1");
    } catch {
      return;
    }

    setVisible(true);
    const tSalida = window.setTimeout(() => setSaliendo(true), 950);
    const tFin = window.setTimeout(() => setVisible(false), 1320);

    return () => {
      window.clearTimeout(tSalida);
      window.clearTimeout(tFin);
    };
  }, []);

  if (!visible) return null;

  return (
    <div
      aria-hidden="true"
      className={`fixed inset-0 z-[100] flex flex-col items-center justify-center bg-[#F6F6F6]/90 backdrop-blur-md transition-opacity duration-350 ${
        saliendo ? "opacity-0 pointer-events-none" : "opacity-100"
      }`}
    >
      <div className="relative flex items-center justify-center">
        <div className="animacion-splash-halo absolute w-28 h-28 rounded-full bg-[#E85A28]/25 blur-xl" />
        <img
          src="/brand/tekio-isotipo.png"
          alt="Tekio Electronics"
          width={76}
          height={76}
          className="animacion-splash-isotipo relative w-[76px] h-[76px] object-contain"
        />
      </div>
      <p className="mt-4 text-[11px] font-bold uppercase tracking-[0.26em] text-[#191818]/70">
        tekio electronics
      </p>
    </div>
  );
}
