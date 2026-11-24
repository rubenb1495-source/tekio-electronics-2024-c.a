import type { Metadata } from "next";
import { ProveedorSesion } from "@/contexto/SesionContexto";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sistema Administrativo · Tekio Electronics",
  description:
    "Sistema administrativo centralizado de TEKIO ELECTRONICS 2024, C.A.",
};

export default function DisenoRaiz({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es">
      <body className="antialiased min-h-screen bg-slate-50 text-slate-900">
        <ProveedorSesion>{children}</ProveedorSesion>
      </body>
    </html>
  );
}
