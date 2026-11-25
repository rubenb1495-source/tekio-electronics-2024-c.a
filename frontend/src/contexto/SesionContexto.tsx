"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { guardarToken, obtenerToken, solicitarApi } from "@/servicios/api";
import type { RespuestaLogin, TasaHoy, Usuario } from "@/tipos/dominio";

interface ValorContextoSesion {
  usuario: Usuario | null;
  cargandoSesion: boolean;
  tasaHoy: TasaHoy | null;
  cargandoTasa: boolean;
  iniciarSesion: (correo: string, clave: string) => Promise<void>;
  cerrarSesion: () => void;
  recargarTasaHoy: () => Promise<void>;
  sincronizarTasaHoy: () => Promise<void>;
  actualizarTasaEnContexto: (nueva: TasaHoy) => void;
}

const ContextoSesion = createContext<ValorContextoSesion | undefined>(undefined);

export function ProveedorSesion({ children }: { children: React.ReactNode }) {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [cargandoSesion, setCargandoSesion] = useState(true);
  const [tasaHoy, setTasaHoy] = useState<TasaHoy | null>(null);
  const [cargandoTasa, setCargandoTasa] = useState(false);

  const recargarTasaHoy = useCallback(async () => {
    if (!obtenerToken()) return;
    setCargandoTasa(true);
    try {
      const datos = await solicitarApi<TasaHoy>("/api/finanzas/tasas/hoy");
      setTasaHoy(datos);
    } catch {
      try {
        const fallback = await solicitarApi<TasaHoy>("/api/tasas/hoy");
        setTasaHoy(fallback);
      } catch {
        setTasaHoy(null);
      }
    } finally {
      setCargandoTasa(false);
    }
  }, []);

  const sincronizarTasaHoy = useCallback(async () => {
    if (!obtenerToken()) return;
    setCargandoTasa(true);
    try {
      const datos = await solicitarApi<TasaHoy>("/api/finanzas/tasas/sincronizar", {
        method: "POST",
      });
      setTasaHoy(datos);
    } catch {
      await recargarTasaHoy();
    } finally {
      setCargandoTasa(false);
    }
  }, [recargarTasaHoy]);

  const actualizarTasaEnContexto = useCallback((nueva: TasaHoy) => {
    setTasaHoy(nueva);
  }, []);

  useEffect(() => {
    const inicializar = async () => {
      const token = obtenerToken();
      if (!token) {
        setCargandoSesion(false);
        return;
      }
      try {
        const perfil = await solicitarApi<Usuario>("/api/auth/perfil");
        setUsuario(perfil);
        await recargarTasaHoy();
      } catch {
        guardarToken(null);
        setUsuario(null);
      } finally {
        setCargandoSesion(false);
      }
    };
    void inicializar();
  }, [recargarTasaHoy]);

  const iniciarSesion = useCallback(
    async (correo: string, clave: string) => {
      const respuesta = await solicitarApi<RespuestaLogin>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ correo, clave }),
      });
      guardarToken(respuesta.token);
      setUsuario(respuesta.usuario);
      await recargarTasaHoy();
    },
    [recargarTasaHoy]
  );

  const cerrarSesion = useCallback(() => {
    guardarToken(null);
    setUsuario(null);
    setTasaHoy(null);
  }, []);

  return (
    <ContextoSesion.Provider
      value={{
        usuario,
        cargandoSesion,
        tasaHoy,
        cargandoTasa,
        iniciarSesion,
        cerrarSesion,
        recargarTasaHoy,
        sincronizarTasaHoy,
        actualizarTasaEnContexto,
      }}
    >
      {children}
    </ContextoSesion.Provider>
  );
}

export function usarSesion(): ValorContextoSesion {
  const contexto = useContext(ContextoSesion);
  if (!contexto) {
    throw new Error("usarSesion debe utilizarse dentro de ProveedorSesion.");
  }
  return contexto;
}
