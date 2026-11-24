export type TipoResolucionDevolucion =
  | "CAMBIO_IGUAL"
  | "GARANTIA_COMPONENTE"
  | "CAMBIO_UPGRADE"
  | "CAMBIO_DOWNGRADE"
  | "REEMBOLSO_TOTAL";

export type EstadoCotizacion =
  | "VIGENTE"
  | "CONVERTIDA"
  | "VENCIDA"
  | "ANULADA";

export type ModalidadCotizacion = "DIVISAS" | "REGULAR" | "CASHEA";

export interface DevolucionGarantiaResumen {
  id: number;
  numero_operacion: string;
  fecha: string;
  venta_id: number;
  numero_venta: string | null;
  cliente: string;
  cliente_telefono: string;
  sucursal: string | null;
  tipo_resolucion: TipoResolucionDevolucion;
  estado_reingreso_origen: string;
  equipo_origen_id: number | null;
  equipo_origen_serial: string | null;
  equipo_origen_modelo: string | null;
  equipo_destino_id: number | null;
  equipo_destino_serial: string | null;
  equipo_destino_modelo: string | null;
  caso_taller_id: number | null;
  caso_taller_numero: string | null;
  articulo_repuesto_id: number | null;
  articulo_repuesto_descripcion: string | null;
  diferencia_usd: number;
  diferencia_promo_usd: number;
  costo_garantia_usd?: number;
  instrumento_id: number | null;
  instrumento: string | null;
  dejar_saldo_favor: boolean;
  referencia_pago: string;
  motivo: string;
  autorizado_por: string | null;
  creado_en: string | null;
}

export type TipoPrecioLista = "PROMO" | "REGULAR";

export interface ItemListaPrecio {
  modelo: string;
  caracteristicas: string;
  descripcion: string;
  categoria: string;
  disponibles: number;
  precio_usd: number;
  precio_bs?: number | null;
}

export interface ListaPreciosRespuesta {
  fecha_emision: string;
  sucursal: string;
  tipo_precio: TipoPrecioLista;
  tasa_bcv?: number;
  total_modelos: number;
  total_unidades: number;
  items: ItemListaPrecio[];
}

export interface CotizacionDetalleItem {
  id: number;
  equipo_id: number | null;
  serial: string | null;
  articulo_id: number | null;
  descripcion: string;
  descripcion_servicio: string;
  cantidad: number;
  precio_promo_usd: number;
  precio_regular_usd: number;
  precio_pactado_usd: number | null;
}

export interface CotizacionResumen {
  id: number;
  numero_cotizacion: string;
  fecha: string;
  vigencia_horas: number;
  estado: EstadoCotizacion;
  modalidad_precio: ModalidadCotizacion;
  cliente_id: number | null;
  cliente: string;
  cliente_rif: string;
  cliente_tipo_persona: string;
  cliente_telefono: string;
  asesor_id: number | null;
  asesor: string;
  sucursal_id: number;
  sucursal: string | null;
  venta_id: number | null;
  numero_venta: string | null;
  tasa_bcv_snapshot: number;
  recargo_porcentaje_snapshot: number;
  total_promo_usd: number;
  total_regular_usd: number;
  total_regular_bs: number;
  nota: string;
  creado_en: string | null;
  detalles: CotizacionDetalleItem[];
}
