export type RolUsuario =
  | "DIRECCION"
  | "ADMINISTRACION"
  | "LOGISTICA"
  | "ENCARGADO"
  | "LIDER"
  | "ASESORA"
  | "TECNICO";

export type EstadoSucursal = "ACTIVA" | "CERRADA";

export type TipoArticulo = "EQUIPO" | "COMPONENTE" | "ACCESORIO" | "SERVICIO";

export type OrigenTasa = "AUTOMATICO" | "MANUAL";

export interface Sucursal {
  id: number;
  nombre: string;
  direccion: string;
  estado: EstadoSucursal;
  fecha_cierre: string | null;
}

export interface Usuario {
  id: number;
  nombre: string;
  username?: string | null;
  correo: string | null;
  rol: RolUsuario;
  modalidad?: "PRESENCIAL" | "ONLINE";
  telefono?: string;
  cedula?: string;
  tiene_acceso?: boolean;
  intentos_fallidos_login?: number;
  cuenta_bloqueada?: boolean;
  bloqueado_hasta?: string | null;
  activo: boolean;
  motivo_estado: string | null;
  creado_en: string;
  sucursal: Sucursal | null;
}

export interface RespuestaLogin {
  token: string;
  usuario: Usuario;
}

export interface TasaHoy {
  fecha: string;
  permite_bolivares: boolean;
  alerta: string | null;
  tasa_bcv: number | null;
  tasa_usdt: number | null;
  recargo_porcentaje: number | null;
  porcentaje_recargo?: number | null;
  recargo_confirmado_hoy?: boolean;
  brecha_porcentaje: number | null;
  origen?: OrigenTasa | null;
  fuente?: string | null;
  nota?: string;
  actualizado_en: string | null;
}

export interface TasaDiaria {
  id: number;
  fecha: string;
  tasa_bcv: number;
  tasa_usdt: number;
  recargo_porcentaje: number;
  brecha_porcentaje: number;
  origen: OrigenTasa;
  nota: string;
  publicado_por: string | null;
  actualizado_en: string;
}

export interface TasasPaginadas {
  elementos: TasaDiaria[];
  total: number;
  pagina: number;
  por_pagina: number;
}

export interface ArticuloCatalogo {
  id: number;
  sku: string;
  descripcion: string;
  tipo: TipoArticulo;
  categoria: string;
  activo: boolean;
  precio_promo_usd: number;
  precio_regular_fijo_usd: number | null;
  precio_regular_usd: number;
  precio_regular_bs: number | null;
  fecha_vigencia: string | null;
  creado_en: string;
  costo_referencia_usd?: number | null;
}

export interface CatalogoPaginado {
  elementos: ArticuloCatalogo[];
  total: number;
  pagina: number;
  por_pagina: number;
  recargo_aplicado_porcentaje: number;
  tasa_bcv_aplicada: number | null;
}

export interface PrecioHistorial {
  id: number;
  precio_promo_usd: number;
  precio_regular_fijo_usd: number | null;
  fecha_vigencia: string;
  creado_por: string | null;
  creado_en: string;
  costo_referencia_usd?: number | null;
}
