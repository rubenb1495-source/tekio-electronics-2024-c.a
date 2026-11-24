"use client";

import React from "react";

interface LogoTekioProps {
  variante?: "horizontal" | "vertical" | "isotipo";
  tema?: "oscuro" | "claro" | "mono-blanco";
  tamano?: "sm" | "md" | "lg";
  className?: string;
}

/**
 * Componente oficial del imagotipo de Tekio Electronics (Manual de Identidad 2024).
 * Usa los PNG oficiales en /public/brand/ respetando proporción y zona de respeto,
 * sin sombras, trazos ni inclinaciones.
 */
export default function LogoTekio({
  variante = "horizontal",
  tema = "oscuro",
  tamano = "md",
  className = "",
}: LogoTekioProps) {
  if (variante === "isotipo") {
    const dim = tamano === "sm" ? 28 : tamano === "lg" ? 56 : 36;
    return (
      <div
        className={`inline-flex items-center justify-center p-1 select-none ${className}`}
      >
        <img
          src="/brand/tekio-isotipo.png"
          alt="Tekio Electronics"
          width={dim}
          height={dim}
          className="object-contain shrink-0"
          style={{ width: dim, height: dim }}
        />
      </div>
    );
  }

  const rutaHorizontal =
    tema === "claro"
      ? "/brand/tekio-logo-horizontal.png"
      : "/brand/tekio-logo-horizontal-blanco.png";

  const altura =
    variante === "vertical"
      ? tamano === "lg"
        ? 52
        : tamano === "sm"
        ? 28
        : 40
      : tamano === "lg"
      ? 48
      : tamano === "sm"
      ? 26
      : 34;

  return (
    <div
      className={`inline-flex items-center py-1 px-0.5 select-none ${className}`}
    >
      <img
        src={rutaHorizontal}
        alt="Tekio Electronics"
        className="object-contain w-auto max-w-full"
        style={{ height: altura }}
      />
    </div>
  );
}
