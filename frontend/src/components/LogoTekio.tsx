"use client";

import React from "react";

interface LogoTekioProps {
  variante?: "horizontal" | "vertical" | "isotipo";
  tema?: "oscuro" | "claro" | "mono-blanco";
  tamano?: "sm" | "md" | "lg";
  className?: string;
}

/**
 * Componente oficial del logotipo de Tekio Electronics (Manual de Identidad 2024).
 * Respeta zona de respeto, sin sombras, sin trazos ni inclinaciones.
 */
export default function LogoTekio({
  variante = "horizontal",
  tema = "oscuro",
  tamano = "md",
  className = "",
}: LogoTekioProps) {
  const colorIsotipo = tema === "mono-blanco" ? "#FFFFFF" : "#E85A28";
  const colorWordmark =
    tema === "claro" ? "#191818" : "#FFFFFF";
  const colorSubtexto =
    tema === "claro" ? "#525252" : "#A3A3A3";

  const dimIso = tamano === "sm" ? 28 : tamano === "lg" ? 56 : 36;

  const IsotipoSvg = (
    <svg
      width={dimIso}
      height={dimIso}
      viewBox="0 0 64 64"
      fill="none"
      aria-hidden="true"
      className="shrink-0"
    >
      {/* 3 flechas convergentes del isotipo oficial Tekio */}
      <g fill={colorIsotipo}>
        <path d="M8 17.5L28.5 32L8 46.5V37.8L16.2 32L8 26.2V17.5Z" />
        <path d="M32 7.5L46.5 28H37.8L32 19.8L26.2 28H17.5L32 7.5Z" />
        <path d="M56 17.5V26.2L47.8 32L56 37.8V46.5L35.5 32L56 17.5Z" />
      </g>
    </svg>
  );

  if (variante === "isotipo") {
    return (
      <div
        className={`inline-flex items-center justify-center p-1 select-none ${className}`}
        aria-label="Tekio Electronics"
      >
        {IsotipoSvg}
      </div>
    );
  }

  if (variante === "vertical") {
    return (
      <div
        className={`inline-flex flex-col items-center gap-2.5 p-2 select-none ${className}`}
      >
        {IsotipoSvg}
        <div className="text-center leading-none">
          <span
            style={{ color: colorWordmark }}
            className={`block font-bold tracking-[-0.04em] ${
              tamano === "lg"
                ? "text-4xl"
                : tamano === "sm"
                ? "text-xl"
                : "text-3xl"
            }`}
          >
            tekio
          </span>
          <span
            style={{ color: colorSubtexto }}
            className="block text-[10px] font-medium uppercase tracking-[0.26em] mt-1"
          >
            ELECTRONICS
          </span>
        </div>
      </div>
    );
  }

  // Variante horizontal (default)
  return (
    <div
      className={`inline-flex items-center gap-2.5 py-1 px-0.5 select-none ${className}`}
    >
      {IsotipoSvg}
      <div className="leading-none">
        <span
          style={{ color: colorWordmark }}
          className={`block font-bold tracking-[-0.04em] ${
            tamano === "lg"
              ? "text-2xl"
              : tamano === "sm"
              ? "text-lg"
              : "text-xl"
          }`}
        >
          tekio
        </span>
        <span
          style={{ color: colorSubtexto }}
          className="block text-[9px] font-medium uppercase tracking-[0.22em] mt-0.5"
        >
          ELECTRONICS
        </span>
      </div>
    </div>
  );
}
