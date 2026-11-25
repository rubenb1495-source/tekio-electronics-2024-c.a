"use client";

import React, { useEffect, useState } from "react";
import { Download, Share, X } from "lucide-react";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

export default function InstaladorPwa() {
  const [eventoInstalacion, setEventoInstalacion] =
    useState<BeforeInstallPromptEvent | null>(null);
  const [esIosSafari, setEsIosSafari] = useState(false);
  const [modalIosAbierto, setModalIosAbierto] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;

    // Registrar Service Worker ligero para habilitar PWA sin interferir con la API
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }

    const yaInstalada =
      window.matchMedia?.("(display-mode: standalone)")?.matches ||
      (window.navigator as Navigator & { standalone?: boolean }).standalone === true;
    if (yaInstalada) return;

    const ua = window.navigator.userAgent;
    const esIos = /iPhone|iPad|iPod/i.test(ua);
    const esSafari = /Safari/i.test(ua) && !/CriOS|FxiOS|EdgiOS/i.test(ua);
    if (esIos && esSafari) {
      setEsIosSafari(true);
    }

    const manejarPrompt = (e: Event) => {
      e.preventDefault();
      setEventoInstalacion(e as BeforeInstallPromptEvent);
    };

    window.addEventListener("beforeinstallprompt", manejarPrompt);
    return () => window.removeEventListener("beforeinstallprompt", manejarPrompt);
  }, []);

  const instalar = async () => {
    if (!eventoInstalacion) return;
    await eventoInstalacion.prompt();
    const res = await eventoInstalacion.userChoice;
    if (res.outcome === "accepted") {
      setEventoInstalacion(null);
    }
  };

  if (!eventoInstalacion && !esIosSafari) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => {
          if (eventoInstalacion) {
            void instalar();
          } else {
            setModalIosAbierto(true);
          }
        }}
        title="Instalar Tekio ERP como aplicación"
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#FDF0EB] border border-[#E85A28]/30 text-[#E85A28] hover:bg-[#E85A28] hover:text-white text-xs font-bold transition-colors cursor-pointer"
      >
        <Download className="w-3.5 h-3.5" />
        <span className="hidden sm:inline">Instalar App</span>
      </button>

      {modalIosAbierto && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white/95 backdrop-blur-md border border-white/70 rounded-2xl max-w-sm w-full p-5 shadow-xl space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-black text-[#191818]">
                Instalar Tekio ERP en iPhone / iPad
              </h3>
              <button
                type="button"
                onClick={() => setModalIosAbierto(false)}
                className="p-1 rounded-lg text-neutral-400 hover:text-neutral-700 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <ol className="text-xs text-neutral-600 space-y-2 list-decimal list-inside">
              <li>
                Toca el botón <strong className="inline-flex items-center gap-0.5 text-[#191818]"><Share className="w-3 h-3" /> Compartir</strong> en la barra inferior de Safari.
              </li>
              <li>
                Desliza hacia abajo y selecciona <strong>&ldquo;Agregar a inicio&rdquo;</strong>.
              </li>
              <li>
                Confirma tocando <strong>&ldquo;Agregar&rdquo;</strong> para abrir Tekio ERP en pantalla completa.
              </li>
            </ol>
          </div>
        </div>
      )}
    </>
  );
}
