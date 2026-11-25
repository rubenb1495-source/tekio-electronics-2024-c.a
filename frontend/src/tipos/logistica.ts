export type OrigenCompra =
  | "IMPORTACION"
  | "INTERNACIONAL"
  | "NACIONAL"
  | "CONSIGNACION"
  | "INVENTARIO_EXISTENTE"
  | "PARTE_DE_PAGO";

export type EstadoCompra = "PENDIENTE" | "RECIBIDA_PARCIAL" | "RECIBIDA";
export type ModalidadGuia = "AEREO" | "MARITIMO";
export type EstadoGuia = "EN_TRANSITO" | "RECIBIDA";
export type EstadoEquipo =
  | "EN_TRANSITO"
  | "POR_PREPARAR"
  | "EN_PREPARACION"
  | "LISTO"
  | "HOSPITAL"
  | "RESERVADO"
  | "CEMENTERIO"
  | "VENDIDO";
export type EstadoTraslado = "EN_TRANSITO" | "RECIBIDO" | "ANULADO";
export type TipoAjuste = "BAJA_EQUIPO" | "CORRECCION_MAS" | "CORRECCION_MENOS";
export type EstadoAjuste = "PENDIENTE" | "APROBADO" | "RECHAZADO";

export interface Tercero {
  id: number;
  nombre: string;
  tipo: "PROVEEDOR" | "CLIENTE" | "AMBOS";
  tipo_persona?: "NATURAL" | "JURIDICO";
  tipo_documento?: "V" | "E" | "J" | "G" | "P" | "";
  documento?: string;
  rif_cedula: string;
  telefono: string;
  direccion?: string;
  activo: boolean;
}

export interface Verificador {
  id: number;
  nombre: string;
  rol: string;
}

export interface CompraResumen {
  id: number;
  numero_compra: string;
  origen: OrigenCompra;
  proveedor_id: number | null;
  proveedor: string;
  fecha: string;
  factura_orden: string;
  llega_preparada: boolean;
  estado: EstadoCompra;
  nota: string;
  creado_por: string | null;
  total_equipos: number;
  total_componentes: number;
  monto_mercancia_usd?: number;
  envio_usd?: number;
  otros_gastos_usd?: number;
}

export interface ComprasPaginadas {
  elementos: CompraResumen[];
  total: number;
  pagina: number;
  por_pagina: number;
}

export interface FilaValidacionArchivo {
  fila: number;
  serial: string | null;
  sku: string | null;
  modelo: string;
  configuracion: string;
  categoria: string;
  cantidad: number;
  costo_compra_usd: number | null;
  precio_promo_usd: number;
  ubicacion: string | null;
  estado: string | null;
  valida: boolean;
  errores: string[];
}

export interface ValidacionArchivo {
  nombre_archivo: string;
  total_filas: number;
  filas_validas: number;
  filas_con_error: number;
  puede_confirmar: boolean;
  filas: FilaValidacionArchivo[];
}

export interface GuiaResumen {
  id: number;
  numero_guia: string;
  casillero: string;
  modalidad: ModalidadGuia;
  fecha_salida: string | null;
  fecha_llegada_estimada: string | null;
  fecha_llegada_real: string | null;
  estado: EstadoGuia;
  nota: string;
  compras: { id: number; numero_compra: string }[];
  seriales_esperados: string[];
  flete_usd?: number;
  otros_gastos_usd?: number;
  costo_total_guia_usd?: number;
}

export interface ResultadoRecepcionGuia {
  guia_id: number;
  numero_guia: string;
  estado: EstadoGuia;
  equipos_recibidos: number;
  componentes_recibidos: number;
  verificado_por: string;
  prorrateo: {
    serial: string;
    estado: EstadoEquipo;
    costo_compra_usd: number;
    costo_flete_usd: number;
  }[];
}

export interface EquipoInventario {
  id: number;
  serial: string;
  articulo_id: number | null;
  sku: string | null;
  compra_id: number | null;
  numero_compra: string | null;
  guia_id: number | null;
  numero_guia: string | null;
  modelo: string;
  configuracion: string;
  categoria: string;
  ubicacion_id: number;
  ubicacion: string | null;
  estado: EstadoEquipo;
  precio_promo_usd: number;
  es_consignacion?: boolean;
  proveedor_consignacion_id?: number | null;
  proveedor_consignacion?: string | null;
  recibido_por: string | null;
  verificado_por: string | null;
  fecha_recepcion: string | null;
  nota: string;
  costo_compra_usd?: number;
  costo_flete_usd?: number;
  costo_taller_usd?: number;
  costo_total_usd?: number;
}

export interface TrazabilidadEquipo {
  equipo: EquipoInventario;
  linea_tiempo: {
    fecha: string;
    tipo: string;
    sucursal: string | null;
    documento_ref: string;
    motivo: string;
    usuario: string | null;
    costo_unitario_usd?: number;
  }[];
}

export interface KardexRespuesta {
  saldos: {
    articulo_id: number;
    sku: string;
    descripcion: string;
    sucursal_id: number;
    sucursal: string;
    stock_actual: number;
  }[];
  movimientos: {
    id: number;
    fecha: string;
    tipo: string;
    sku: string | null;
    sucursal: string | null;
    cantidad: number;
    documento_ref: string;
    motivo: string;
    usuario: string | null;
    costo_unitario_usd?: number;
  }[];
}

export interface TrasladoResumen {
  id: number;
  numero_traslado: string;
  origen_id: number;
  origen: string | null;
  destino_id: number;
  destino: string | null;
  estado: EstadoTraslado;
  enviado_por: string | null;
  recibido_por: string | null;
  fecha_envio: string;
  fecha_recepcion: string | null;
  nota: string;
  nota_recepcion: string;
  motivo_anulacion: string;
  detalles: {
    id: number;
    equipo_id: number | null;
    serial: string | null;
    modelo: string | null;
    articulo_id: number | null;
    sku: string | null;
    cantidad: number;
  }[];
}

export interface AjusteResumen {
  id: number;
  numero_ajuste: string;
  sucursal_id: number;
  sucursal: string | null;
  tipo: TipoAjuste;
  equipo_id: number | null;
  serial: string | null;
  articulo_id: number | null;
  sku: string | null;
  cantidad: number;
  motivo: string;
  estado: EstadoAjuste;
  solicitado_por: string | null;
  revisado_por: string | null;
  fecha_revision: string | null;
  comentario_revision: string;
  creado_en: string;
}
