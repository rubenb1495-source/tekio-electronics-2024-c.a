"use client";

import React from "react";
import { Search, X } from "lucide-react";

interface BuscadorTablaProps {
  valor: string;
  alCambiar: (valor: string) => void;
  placeholder?: string;
  totalRegistros?: number;
  totalFiltrados?: number;
  className?: string;
}

export default function BuscadorTabla({
  valor,
  alCambiar,
  placeholder = "Buscar...",
  totalRegistros,
  totalFiltrados,
  className = "",
}: BuscadorTablaProps) {
  const mostrarContador =
    typeof totalRegistros === "number" && typeof totalFiltrados === "number";

  return (
    <div
      className={`flex flex-wrap items-center gap-2 min-w-0 flex-1 ${className}`}
    >
      <div className="relative flex-1 min-w-[220px]">
        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
        <input
          type="text"
          value={valor}
          onChange={(e) => alCambiar(e.target.value)}
          placeholder={placeholder}
          className="w-full min-w-0 pl-9 pr-8 py-2 rounded-xl border border-slate-300 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#E85A28]/30 focus:border-[#E85A28]"
        />
        {valor && (
          <button
            type="button"
            onClick={() => alCambiar("")}
            aria-label="Limpiar búsqueda"
            className="absolute right-2.5 top-1/2 -translate-y-1/2 p-0.5 text-slate-400 hover:text-slate-600 cursor-pointer"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      {mostrarContador && (
        <span className="text-xs font-semibold text-slate-500 whitespace-nowrap">
          Mostrando <strong className="text-slate-800">{totalFiltrados}</strong>{" "}
          de {totalRegistros}
        </span>
      )}
    </div>
  );
}
