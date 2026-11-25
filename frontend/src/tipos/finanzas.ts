export interface InstrumentoFinanciero {
  id: number;
  nombre: string;
  moneda: "USD" | "USDT" | "BS";
  tipo_precio: "PROMO" | "REGULAR";
  requiere_verificacion: boolean;
  liquida_en_bs: boolean;
  activo?: boolean;
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

export interface UsuarioOperativo {
  id: number;
  nombre: string;
  rol: string;
  es_lider?: boolean;
  sucursal_id: number | null;
}

export interface VentaResumen {
  id: number;
  numero_venta: string;
  sucursal_id: number;
  sucursal: string | null;
  fecha: string;
  cliente_id: number | null;
  cliente: string;
  cliente_rif?: string;
  cliente_telefono?: string;
  cliente_direccion?: string;
  cliente_tipo_persona?: "NATURAL" | "JURIDICO" | string;
  asesor_id: number | null;
  asesor: string;
  tecnico_id?: number | null;
  tecnico?: string | null;
  canal_visita: string;
  tipo_entrega: string;
  datos_entrega?: Record<string, string> | null;
  tasa_bcv_snapshot: number;
  tasa_usdt_snapshot: number;
  recargo_porcentaje_snapshot: number;
  total_promo_usd: number;
  total_regular_usd: number;
  vuelto_caja_chica_usd?: number;
  creado_en?: string | null;
  estado: "CUADRADA" | "CON_SALDO" | "ANULADA" | "DEVUELTA";
  motivo_anulacion: string;
  nota: string;
  detalles: {
    id: number;
    equipo_id: number | null;
    serial: string | null;
    articulo_id: number | null;
    descripcion: string;
    descripcion_servicio?: string;
    es_servicio_tecnico?: boolean;
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
  total_regular_usd?: number;
  precio_regular_bs?: number;
  comision_cashea_venta_total_usd?: number;
  comision_cashea_financiado_usd?: number;
  iva_cashea_usd?: number;
  islr_cashea_usd?: number;
  total_deducciones_cashea_usd?: number;
  neto_esperado_cashea_usd?: number;
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
  telefono?: string;
  cantidad_ventas?: number;
  cantidad_operaciones?: number;
  ventas_promo_usd: number;
  ventas_equipo_lider_usd?: number;
  comision_ventas_1_usd: number;
  comision_lider_05_usd: number;
  comision_servicios_50_usd: number;
  pago_preparaciones_usd: number;
  total_comision_usd: number;
  monto_pendiente_usd?: number;
  monto_pagado_usd?: number;
  estado_comision?: "PENDIENTE" | "PAGADA";
  notas?: string[];
}

export interface OperacionComision {
  venta_id?: number | null;
  numero_nota: string;
  fecha: string;
  cliente: string;
  sucursal: string;
  usuario_id: number;
  usuario_nombre: string;
  rol: string;
  tipo: string;
  base_promo_usd: number;
  comision_usd: number;
  estado_comision?: "PENDIENTE" | "PAGADA";
  liquidacion_codigo?: string | null;
}

export interface LiquidacionComisionResumen {
  id: number;
  codigo: string;
  estado?: "ACTIVA" | "ANULADA";
  usuario_id: number;
  usuario_nombre: string;
  usuario_rol: string;
  usuario_telefono?: string;
  fecha_inicio: string;
  fecha_fin: string;
  fecha_pago: string;
  monto_total_usd: number;
  instrumento_id: number;
  instrumento: string;
  referencia: string;
  pago_egreso_id: number | null;
  autorizado_por: string;
  anulada_por?: string | null;
  fecha_anulacion?: string | null;
  motivo_anulacion?: string;
  notas: string;
  cantidad_operaciones: number;
  notas_liquidadas: string[];
  creado_en: string | null;
}

export interface TasasDiaCierre {
  fecha: string;
  tasa_bcv: number;
  tasa_usdt: number;
  recargo_porcentaje: number;
}

export interface InventarioCierre {
  recepciones_dia: number;
  traslados_recibidos_dia: number;
  unidades_vendidas_dia: number;
  traslados_despachados_dia: number;
  unidades_salientes_dia: number;
  stock_disponible_listo: number;
}

export interface TallerCierre {
  recibidos_dia: number;
  resueltos_dia: number;
  pendientes_total: number;
  gt_pendientes: number;
  st_pendientes: number;
}

export interface DesgloseInstrumentoCaja {
  instrumento_id: number;
  instrumento: string;
  moneda: "USD" | "USDT" | "BS" | string;
  ingresos_origen: number;
  egresos_origen: number;
  neto_origen: number;
  ingresos_usd: number;
  egresos_usd: number;
  neto_usd: number;
  cantidad_movimientos: number;
}

export interface DesgloseAsesorCaja {
  asesor_id: number | null;
  asesor: string;
  cantidad_ventas: number;
  total_promo_usd: number;
  total_regular_usd: number;
}

export interface PreviewCierreCaja {
  fecha: string;
  sucursal_id: number | null;
  sucursal: string;
  lider_encargado?: string;
  tasas_dia?: TasasDiaCierre | null;
  inventario?: InventarioCierre | null;
  taller?: TallerCierre | null;
  cantidad_ventas: number;
  cantidad_anulaciones: number;
  total_ventas_usd: number;
  total_ingresos_usd: number;
  total_ingresos_bs: number;
  total_egresos_usd: number;
  total_egresos_bs: number;
  total_cashea_usd: number;
  efectivo_esperado_usd: number;
  saldo_neto_esperado_usd: number;
  desglose_instrumentos: DesgloseInstrumentoCaja[];
  desglose_asesores?: DesgloseAsesorCaja[];
}

export interface CierreCajaResumen {
  id: number;
  fecha: string;
  sucursal_id: number | null;
  sucursal: string;
  usuario: string;
  lider_encargado?: string;
  tasas_dia?: TasasDiaCierre | null;
  inventario?: InventarioCierre | null;
  taller?: TallerCierre | null;
  cantidad_ventas: number;
  cantidad_anulaciones: number;
  total_ventas_usd: number;
  total_ingresos_usd: number;
  total_ingresos_bs: number;
  total_egresos_usd: number;
  total_egresos_bs: number;
  total_cashea_usd: number;
  efectivo_esperado_usd: number;
  efectivo_declarado_usd: number;
  diferencia_usd: number;
  observaciones: string;
  desglose_instrumentos: DesgloseInstrumentoCaja[];
  desglose_asesores?: DesgloseAsesorCaja[];
  creado_en: string | null;
}

export interface ReporteComisiones {
  fecha_inicio: string;
  fecha_fin: string;
  mes: number;
  anio: number;
  mes_cerrado: boolean;
  resumen?: {
    total_base_promo_usd: number;
    total_comisiones_usd: number;
    cantidad_operaciones: number;
  };
  comisiones: ComisionPersona[];
  operaciones?: OperacionComision[];
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
