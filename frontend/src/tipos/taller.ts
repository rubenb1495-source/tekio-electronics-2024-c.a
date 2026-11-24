export type TipoPreparacion = "ESTANDAR" | "ESPECIAL";
export type ResultadoPreparacion = "LISTO" | "HOSPITAL" | "CEMENTERIO";
export type EstadoRepuesto = "PENDIENTE" | "COMPRADO" | "RECIBIDO" | "CANCELADO";
export type TipoCaso = "GARANTIA" | "SERVICIO";
export type EstadoCaso =
  | "RECIBIDO"
  | "EN_DIAGNOSTICO"
  | "ESPERANDO_PRESUPUESTO"
  | "ESPERANDO_APROBACION"
  | "AUTORIZADO"
  | "ESPERANDO_REPUESTO"
  | "TERMINADO"
  | "LISTO_PARA_ENTREGAR"
  | "ENTREGADO"
  | "RECHAZADO";

export interface EquipoColaTaller {
  id: number;
  serial: string;
  modelo: string;
  configuracion: string;
  categoria: string;
  ubicacion_id: number;
  ubicacion: string | null;
  estado: "POR_PREPARAR" | "HOSPITAL";
  dias_en_taller: number;
  repuesto_disponible: boolean;
  repuestos_pendientes: string[];
  nota: string;
}

export interface RepuestoSolicitado {
  id: number;
  origen: "HOSPITAL" | "CASO_TECNICO";
  equipo_id: number | null;
  serial: string | null;
  caso_id: number | null;
  numero_caso: string | null;
  articulo_id: number | null;
  sku: string | null;
  descripcion_repuesto: string;
  cantidad: number;
  estado: EstadoRepuesto;
  solicitado_por: string | null;
  fecha_solicitud: string;
  fecha_recepcion: string | null;
  notificado_tecnico: boolean;
}

export interface PresupuestoCaso {
  id: number;
  mano_obra_usd: number;
  repuestos: {
    articulo_id: number | null;
    descripcion: string;
    cantidad: number;
    precio_promo_usd: number;
  }[];
  total_promo_usd: number;
  aprobado_cliente: boolean | null;
  fecha_envio: string;
  fecha_respuesta: string | null;
  nota_cliente: string;
}

export interface CasoPostventa {
  id: number;
  numero_caso: string;
  tipo: TipoCaso;
  sucursal_id: number;
  sucursal: string | null;
  cliente_id: number | null;
  cliente: string;
  equipo_id: number | null;
  serial_o_codigo: string;
  descripcion_equipo: string;
  tipo_marca_color: string;
  accesorios_recibidos: string;
  estado_fisico: string;
  clave_equipo: string;
  falla_reportada: string;
  tecnico_id: number | null;
  tecnico: string | null;
  diagnostico: string;
  trabajo_realizado: string;
  estado: EstadoCaso;
  alerta_garantia: string | null;
  dias_abiertos: number;
  fecha_ingreso: string;
  fecha_cierre: string | null;
  presupuesto: PresupuestoCaso | null;
}

export interface ResumenTecnico {
  tecnico_id: number;
  tecnico_nombre: string;
  mes: number;
  anio: number;
  cantidad_preparaciones: number;
  pago_preparaciones_usd: number;
  cantidad_servicios: number;
  comision_servicios_usd: number;
  comision_asesor_usd: number;
  total_mes_usd: number;
  detalle_preparaciones: {
    id: number;
    fecha: string;
    serial: string | null;
    tipo: TipoPreparacion;
    resultado: ResultadoPreparacion;
    pago_tecnico_usd: number;
  }[];
  detalle_servicios: {
    numero_caso: string;
    descripcion_equipo: string;
    mano_obra_usd: number;
    comision_50_usd: number;
    estado: EstadoCaso;
  }[];
}
