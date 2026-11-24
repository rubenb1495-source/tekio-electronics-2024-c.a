"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { usarSesion } from "@/contexto/SesionContexto";

export default function PaginaInicio() {
  const { usuario, cargandoSesion } = usarSesion();
  const router = useRouter();

  useEffect(() => {
    if (cargandoSesion) return;
    if (usuario) {
      router.replace("/dashboard/tasas");
    } else {
      router.replace("/login");
    }
  }, [usuario, cargandoSesion, router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="animate-pulse text-sm font-semibold text-slate-500">
        Cargando Sistema Administrativo Tekio Electronics...
      </div>
    </div>
  );
}
