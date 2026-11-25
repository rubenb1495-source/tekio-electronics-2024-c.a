import type { Metadata, Viewport } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import SplashTekio from "@/components/SplashTekio";
import { ProveedorSesion } from "@/contexto/SesionContexto";
import "./globals.css";

const plusJakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "700"],
  variable: "--font-plus-jakarta",
  display: "swap",
});

export const viewport: Viewport = {
  themeColor: "#E85A28",
  width: "device-width",
  initialScale: 1,
};

export const metadata: Metadata = {
  title: "Sistema Administrativo · Tekio Electronics",
  description:
    "Sistema administrativo centralizado de TEKIO ELECTRONICS 2024, C.A. — Somos tu solución.",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Tekio ERP",
  },
  icons: {
    icon: [
      { url: "/icon-192x192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512x512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
};

export default function DisenoRaiz({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className={plusJakarta.variable}>
      <body className="font-sans antialiased min-h-screen text-[#191818]">
        <SplashTekio />
        <ProveedorSesion>{children}</ProveedorSesion>
      </body>
    </html>
  );
}
