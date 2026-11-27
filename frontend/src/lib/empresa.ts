export interface SedeOficialTekio {
  codigo: "TEKIO_CENTRAL" | "TEKIO_GRAN_BAZAR" | "DEPOSITO_TALLER";
  nombre: string;
  tipo: "TIENDA" | "DEPOSITO_TALLER";
  telefono: string;
  direccion: string;
}

export const EMPRESA_TEKIO = {
  razonSocial: "TEKIO ELECTRONICS 2024, C.A.",
  rif: "J-50637518-4",
  domicilioFiscal:
    "Av. Principal C.C. Freemarket, Nivel Mezzanina, Local Mini Tienda X47 y X48, Módulo 13, Urb. La Granja, Naguanagua, Carabobo, Zona Postal 2005",
  eslogan: "Somos tu solución",
  telefonoAdministracion: "0424-2231879",
  telefonoSoporte: "0422-5284961",
  fechaCorteApertura: "2026-12-01",
  notaFiscalSeniat:
    "Contribuyente · RIF J-50637518-4 · Referencia administrativa: condición de retención del 100% de IVA según normativa SENIAT vigente.",
  paleta: {
    naranja: "#E85A28",
    naranjaHover: "#D14D20",
    naranjaSuave: "#FDF0EB",
    carbon: "#191818",
    fondo: "#F6F6F6",
    blanco: "#FFFFFF",
  },
} as const;

export const SEDES_OFICIALES_TEKIO: readonly SedeOficialTekio[] = [
  {
    codigo: "TEKIO_CENTRAL",
    nombre: "Tekio Central",
    tipo: "TIENDA",
    telefono: "0412-5284961",
    direccion: EMPRESA_TEKIO.domicilioFiscal,
  },
  {
    codigo: "TEKIO_GRAN_BAZAR",
    nombre: "Tekio Gran Bazar",
    tipo: "TIENDA",
    telefono: "0422-5556609",
    direccion: "C.C. Gran Bazar, Centro, Local ML174, Valencia, Carabobo",
  },
  {
    codigo: "DEPOSITO_TALLER",
    nombre: "Depósito / Tekio Support (Taller)",
    tipo: "DEPOSITO_TALLER",
    telefono: "0422-5284961",
    direccion: "Depósito Central y Taller Tekio Support, Naguanagua, Carabobo",
  },
] as const;
