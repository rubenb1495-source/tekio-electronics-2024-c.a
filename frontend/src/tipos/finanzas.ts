export interface InstrumentoFinanciero {
  id: number;
  nombre: string;
  moneda: "USD" | "USDT" | "BS";
  tipo_precio: "PROMO" | "REGULAR";
  requiere_verificacion: boolean;
  liquida_en_bs: boolean;
}

export interface SimulacionVenta {
  total_promo_usd: number;
  total_regular_usd: number;
  cubierto_promo_usd: number;
  cubierto_regular_usd?: number;
  falta_usd_promo: number;
  sobra_usd_promo: number;
  falta_usd_regular: number;
  falta_bs: number | null;
  cashea_financiado_sugerido_usd?: number;
  cashea_financiado_sugerido_bs?: number | null;
  usa_cashea: boolean;
  tasa_bcv: number;
  recargo_porcentaje: number;
  estado: "CUADRADA" | "CON_SALDO";
}

export interface VentaResumen {
  id: number;
  numero_venta: string;
  sucursal_id: number;
  sucursal: string | null;
  fecha: string;
  cliente_id: number | null;
  cliente: string;
  asesor_id: number | null;
  asesor: string;
  canal_visita: string;
  tipo_entrega: string;
  tasa_bcv_snapshot: number;
  tasa_usdt_snapshot: number;
  recargo_porcentaje_snapshot: number;
  total_promo_usd: number;
  total_regular_usd: number;
  estado: "CUADRADA" | "CON_SALDO" | "ANULADA";
  motivo_anulacion: string;
  nota: string;
  detalles: {
    id: number;
    equipo_id: number | null;
    serial: string | null;
    articulo_id: number | null;
    descripcion: string;
    cantidad: number;
    precio_promo_usd: number;
    precio_regular_usd: number;
  }[];
  pagos: {
    id: number;
    instrumento: string | null;
    monto_moneda_origen: number;
    moneda: string;
    usd_nominal: number;
    usd_real: number;
    cubre_promo_usd: number;
    referencia: string;
    estado_verificacion: "CONFIRMADO" | "PENDIENTE";
    anulado: boolean;
  }[];
}

export interface NotaCreditoResumen {
  id: number;
  numero_nc: string;
  venta_original_id: number;
  numero_venta: string | null;
  serial: string | null;
  sku: string | null;
  cantidad: number;
  monto_reconocido_promo_usd: number;
  motivo: string;
  estado_reingreso: "POR_PREPARAR" | "GARANTIA" | "LISTO";
  autorizado_por: string | null;
  fecha: string;
}

export interface PagoBandeja {
  id: number;
  venta_id: number | null;
  numero_venta: string | null;
  instrumento_id: number;
  instrumento: string | null;
  fecha: string;
  tipo_documento: string;
  monto_moneda_origen: number;
  moneda: string;
  usd_nominal: number;
  usd_real: number;
  referencia: string;
  estado_verificacion: "CONFIRMADO" | "PENDIENTE";
  verificado_por: string | null;
  conciliado: boolean;
  nota: string;
}

export interface CuentaPorCobrarResumen {
  id: number;
  venta_id: number;
  numero_venta: string | null;
  sucursal: string | null;
  fecha_venta: string | null;
  tipo: "CLIENTE" | "CASHEA";
  cliente: string;
  monto_original_usd: number;
  saldo_pendiente_usd: number;
  estado: "PENDIENTE" | "PAGADA" | "ANULADA";
}

export interface ResultadoConciliacion {
  cuadrados: {
    pago_id: number;
    extracto_id: number;
    referencia: string;
    monto: number;
  }[];
  registrados_sin_banco: {
    pago_id: number;
    fecha: string;
    referencia: string;
    monto: number;
  }[];
  en_banco_sin_registrar: {
    extracto_id: number;
    fecha: string;
    referencia: string;
    descripcion: string;
    monto: number;
  }[];
}

export interface ComisionPersona {
  usuario_id: number;
  nombre: string;
  rol: string;
  ventas_promo_usd: number;
  comision_ventas_1_usd: number;
  comision_lider_05_usd: number;
  comision_servicios_50_usd: number;
  pago_preparaciones_usd: number;
  total_comision_usd: number;
}

export interface ReporteComisiones {
  mes: number;
  anio: number;
  mes_cerrado: boolean;
  comisiones: ComisionPersona[];
}

export interface TableroFinanciero {
  desde: string;
  hasta: string;
  cantidad_ventas: number;
  venta_promo_usd: number;
  usd_nominal: number;
  usd_real: number;
  diferencial_cambiario_usd: number;
  cashea_por_cobrar_usd: number;
  costo_total_usd: number;
  utilidad_real_neta_usd: number;
}
