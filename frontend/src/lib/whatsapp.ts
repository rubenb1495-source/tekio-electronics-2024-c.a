import { formatearBs, formatearUsd } from "@/servicios/api";
import type {
  CierreCajaResumen,
  ComisionPersona,
  LiquidacionComisionResumen,
  PagoBandeja,
  VentaResumen,
} from "@/tipos/finanzas";
import type { TrasladoResumen } from "@/tipos/logistica";
import type {
  CotizacionResumen,
  DevolucionGarantiaResumen,
  ListaPreciosRespuesta,
} from "@/tipos/operaciones";

/**
 * Copia texto al portapapeles con fallback seguro para navegadores sin Clipboard API.
 */
export async function copiarTextoPortapapeles(texto: string): Promise<boolean> {
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(texto);
      return true;
    }
  } catch {
    // Fallback manual abajo
  }
  try {
    const textarea = document.createElement("textarea");
    textarea.value = texto;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
    return true;
  } catch {
    return false;
  }
}

function formatearFechaHora(fecha: string, creadoEn?: string | null): string {
  if (!creadoEn) return fecha;
  try {
    const d = new Date(creadoEn);
    if (Number.isNaN(d.getTime())) return fecha;
    const hora = d.toLocaleTimeString("es-VE", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    });
    return `${fecha} · ${hora}`;
  } catch {
    return fecha;
  }
}

/**
 * 1. Mensaje completo de Ventas y Servicios Técnicos (sin costos internos).
 */
export function formatearWhatsAppVenta(venta: VentaResumen): string {
  const esJuridico =
    (venta.cliente_tipo_persona || "NATURAL").toUpperCase() === "JURIDICO";
  const etiquetaDoc = esJuridico ? "RIF" : "Cédula de Identidad";
  const docTxt = venta.cliente_rif
    ? ` · ${etiquetaDoc}: ${venta.cliente_rif}`
    : "";

  const lineas: string[] = [
    `🧾 *TEKIO ELECTRONICS · Nota ${venta.numero_venta}*`,
    `📅 Fecha: ${formatearFechaHora(venta.fecha, venta.creado_en)}`,
    `🏪 Sucursal: ${venta.sucursal || "Tekio central"} · Entrega: ${venta.tipo_entrega} · Canal: ${venta.canal_visita}`,
    `👤 Cliente: ${venta.cliente}${docTxt}${venta.cliente_telefono ? ` · Tel: ${venta.cliente_telefono}` : ""}`,
    ...(venta.cliente_direccion && venta.cliente_direccion.trim()
      ? [`📍 Dirección: ${venta.cliente_direccion.trim()}`]
      : []),
    `🤝 Asesor: ${venta.asesor || "Tienda"}${venta.tecnico ? ` · 🔧 Técnico: ${venta.tecnico}` : ""}`,
    `📌 Estado: *${venta.estado}*`,
    "",
    "📦 *Detalle:*",
  ];

  for (const d of venta.detalles) {
    const esObsequio =
      Number(d.precio_promo_usd) === 0 && Number(d.precio_regular_usd) === 0;
    const serialTxt = d.serial ? ` [Serial: ${d.serial}]` : "";
    const precioTxt = esObsequio
      ? "*OBSEQUIO ($0.00)*"
      : `${formatearUsd(d.precio_promo_usd)} Promo / ${formatearUsd(d.precio_regular_usd)} Reg.`;
    lineas.push(`• ${d.cantidad}x ${d.descripcion}${serialTxt} — ${precioTxt}`);
    if (d.descripcion_servicio && d.descripcion_servicio.trim()) {
      lineas.push(`  ↳ _Trabajo:_ ${d.descripcion_servicio.trim()}`);
    }
  }

  lineas.push(
    "",
    `💵 *Total Promo:* ${formatearUsd(venta.total_promo_usd)} | *Total Regular:* ${formatearUsd(venta.total_regular_usd)}`
  );

  if (venta.tasa_bcv_snapshot > 0) {
    lineas.push(
      `💱 Tasa BCV: ${formatearBs(venta.tasa_bcv_snapshot)} · Recargo: ${venta.recargo_porcentaje_snapshot}%`
    );
  }

  const pagosActivos = (venta.pagos || []).filter((p) => !p.anulado);
  if (pagosActivos.length > 0) {
    lineas.push("", "💳 *Desglose de pagos:*");
    let totalCashea = 0;
    for (const p of pagosActivos) {
      const montoTxt =
        p.moneda === "BS"
          ? `${formatearBs(p.monto_moneda_origen)} (≈ ${formatearUsd(p.usd_nominal)})`
          : `${formatearUsd(p.monto_moneda_origen)} ${p.moneda}`;
      const refTxt = p.referencia ? ` · Ref: ${p.referencia}` : "";
      lineas.push(`• ${p.instrumento || "Pago"}: ${montoTxt}${refTxt}`);
      if ((p.instrumento || "").toLowerCase().includes("cashea")) {
        totalCashea += Number(p.usd_nominal || 0);
      }
    }
    if (totalCashea > 0) {
      const casheaBs =
        venta.tasa_bcv_snapshot > 0
          ? ` (≈ ${formatearBs(totalCashea * venta.tasa_bcv_snapshot)} BCV)`
          : "";
      lineas.push(
        `🟣 *Financiado Cashea:* ${formatearUsd(totalCashea)}${casheaBs}`
      );
    }
  }

  if (venta.vuelto_caja_chica_usd && venta.vuelto_caja_chica_usd > 0) {
    lineas.push(`🔄 Vuelto entregado: ${formatearUsd(venta.vuelto_caja_chica_usd)}`);
  }

  if (venta.estado === "CON_SALDO") {
    const cubierto = pagosActivos.reduce(
      (acc, p) => acc + Number(p.cubre_promo_usd || 0),
      0
    );
    const saldo = Math.max(0, Number(venta.total_promo_usd) - cubierto);
    if (saldo > 0) {
      lineas.push(`⚠️ *Saldo pendiente estimado:* ${formatearUsd(saldo)}`);
    }
  }

  if (venta.datos_entrega && Object.keys(venta.datos_entrega).length > 0) {
    const de = venta.datos_entrega;
    const esEnvio = venta.tipo_entrega.toLowerCase().includes("env");
    lineas.push(
      "",
      esEnvio
        ? "📦 *Datos de Envío Nacional:*"
        : "🚚 *Datos de Delivery:*"
    );
    if (esEnvio) {
      if (de.destinatario) lineas.push(`• Destinatario: ${de.destinatario}`);
      if (de.cedula) lineas.push(`• Cédula de Identidad: ${de.cedula}`);
      if (de.telefono) lineas.push(`• Teléfono: ${de.telefono}`);
      if (de.empresa_envio) lineas.push(`• Empresa: ${de.empresa_envio}`);
      if (de.estado_ciudad) lineas.push(`• Estado / Ciudad: ${de.estado_ciudad}`);
      if (de.agencia_oficina) lineas.push(`• Agencia / Oficina: ${de.agencia_oficina}`);
      if (de.direccion_oficina) lineas.push(`• Dirección oficina: ${de.direccion_oficina}`);
      if (de.modalidad) lineas.push(`• Modalidad: ${de.modalidad}`);
    } else {
      if (de.nombre_recibe) lineas.push(`• Recibe: ${de.nombre_recibe}`);
      if (de.telefono) lineas.push(`• Teléfono: ${de.telefono}`);
      if (de.zona_municipio) lineas.push(`• Zona / Municipio: ${de.zona_municipio}`);
      if (de.direccion) lineas.push(`• Dirección: ${de.direccion}`);
      if (de.punto_referencia) lineas.push(`• Referencia: ${de.punto_referencia}`);
      if (de.horario_instrucciones) lineas.push(`• Horario / Instrucciones: ${de.horario_instrucciones}`);
    }
  }

  if (venta.nota && venta.nota.trim()) {
    lineas.push("", `📝 *Nota:* ${venta.nota.trim()}`);
  }

  return lineas.join("\n");
}

export interface DatosWhatsAppPago {
  tipo_movimiento?: string;
  tipo_documento?: string;
  fecha: string;
  instrumento?: string | null;
  monto_moneda_origen: number;
  moneda: string;
  usd_nominal?: number;
  tasa_bcv?: number | null;
  tasa_usdt?: number | null;
  referencia?: string;
  cliente_o_venta?: string | null;
  estado_verificacion?: string;
  usuario?: string | null;
  nota?: string;
}

/**
 * 2. Mensaje completo de Movimientos de Banco / Pagos / Abonos / Liquidaciones.
 */
export function formatearWhatsAppPago(
  pago: PagoBandeja | DatosWhatsAppPago,
  extras?: {
    tasa_bcv?: number | null;
    tasa_usdt?: number | null;
    usuario?: string | null;
    tipo_movimiento?: string;
  }
): string {
  const esBandeja = "venta_id" in pago;
  const tipoMov =
    extras?.tipo_movimiento ||
    (!esBandeja && pago.tipo_movimiento) ||
    "INGRESO";
  const tipoDoc = pago.tipo_documento || "PAGO";
  const montoTxt =
    pago.moneda === "BS"
      ? formatearBs(pago.monto_moneda_origen)
      : `${formatearUsd(pago.monto_moneda_origen)} ${pago.moneda}`;
  const usdEq =
    pago.usd_nominal !== undefined ? formatearUsd(pago.usd_nominal) : "N/A";
  const tasaBcv = extras?.tasa_bcv ?? (!esBandeja ? pago.tasa_bcv : null);
  const tasaUsdt = extras?.tasa_usdt ?? (!esBandeja ? pago.tasa_usdt : null);
  const vinculo = esBandeja
    ? pago.numero_venta || (pago.venta_id ? `Venta #${pago.venta_id}` : "Sin venta")
    : pago.cliente_o_venta || "N/A";
  const usuarioTxt =
    extras?.usuario ||
    (esBandeja ? pago.verificado_por : pago.usuario) ||
    "Sistema";

  const lineas: string[] = [
    `🏦 *TEKIO ELECTRONICS · Movimiento Bancario*`,
    `📌 Tipo: *${tipoMov}* · Documento: *${tipoDoc}*`,
    `📅 Fecha: ${pago.fecha}`,
    `💳 Instrumento / Banco: *${pago.instrumento || "Instrumento"}*`,
    `💵 Monto: *${montoTxt}* (Equiv. USD: *${usdEq}*)`,
  ];

  if (tasaBcv || tasaUsdt) {
    const partes: string[] = [];
    if (tasaBcv) partes.push(`BCV: ${formatearBs(tasaBcv)}`);
    if (tasaUsdt) partes.push(`USDT: ${formatearBs(tasaUsdt)}`);
    lineas.push(`💱 Tasa del día: ${partes.join(" · ")}`);
  }

  lineas.push(
    `🔖 Referencia: ${pago.referencia || "Sin referencia"}`,
    `🔗 Venta / Cliente: ${vinculo}`,
    `✅ Verificación: *${pago.estado_verificacion || "CONFIRMADO"}*`,
    `👤 Registrado / Verificado por: ${usuarioTxt}`
  );

  if (pago.nota && pago.nota.trim()) {
    lineas.push(`📝 Nota: ${pago.nota.trim()}`);
  }

  return lineas.join("\n");
}

/**
 * 3. Mensaje completo de Traslados de Inventario (sin costos internos).
 */
export function formatearWhatsAppTraslado(traslado: TrasladoResumen): string {
  const lineas: string[] = [
    `🚚 *TEKIO ELECTRONICS · Traslado ${traslado.numero_traslado}*`,
    `📅 Fecha despacho: ${traslado.fecha_envio}${traslado.fecha_recepcion ? ` · Recepción: ${traslado.fecha_recepcion}` : ""}`,
    `📍 Ruta: *${traslado.origen || "Origen"}* ➔ *${traslado.destino || "Destino"}*`,
    `📌 Estado: *${traslado.estado}*`,
    `👤 Despacha: ${traslado.enviado_por || "N/A"} · Recibe: ${traslado.recibido_por || "Pendiente"}`,
    "",
    "📦 *Detalle trasladado:*",
  ];

  for (const d of traslado.detalles) {
    if (d.serial) {
      lineas.push(`• 💻 ${d.modelo || "Equipo"} — Serial: \`${d.serial}\``);
    } else {
      lineas.push(
        `• 🧩 ${d.cantidad}x ${d.sku || "SKU"}${d.modelo ? ` — ${d.modelo}` : ""}`
      );
    }
  }

  if (traslado.nota && traslado.nota.trim()) {
    lineas.push("", `📝 *Observaciones:* ${traslado.nota.trim()}`);
  }

  return lineas.join("\n");
}

const ETIQUETAS_DEVOLUCION: Record<string, string> = {
  CAMBIO_IGUAL: "Cambio por Equipo Igual",
  GARANTIA_COMPONENTE: "Garantía de Componente / Taller",
  CAMBIO_UPGRADE: "Cambio con Upgrade",
  CAMBIO_DOWNGRADE: "Cambio con Downgrade",
  REEMBOLSO_TOTAL: "Reembolso Total",
};

/**
 * 4. Mensaje WhatsApp para Devoluciones, Cambios y Garantías (nunca expone costos internos).
 */
export function formatearWhatsAppDevolucion(
  dev: DevolucionGarantiaResumen
): string {
  const lineas: string[] = [
    `🔄 *TEKIO ELECTRONICS · ${dev.numero_operacion}*`,
    `📋 Resolución: *${ETIQUETAS_DEVOLUCION[dev.tipo_resolucion] || dev.tipo_resolucion}*`,
    `📅 Fecha: ${dev.fecha} · Venta original: *${dev.numero_venta || "N/A"}*`,
    `👤 Cliente: ${dev.cliente}${dev.cliente_telefono ? ` · Tel: ${dev.cliente_telefono}` : ""}`,
    `🏪 Sucursal: ${dev.sucursal || "Tekio central"} · Autorizado por: ${dev.autorizado_por || "Tekio"}`,
    "",
  ];

  if (dev.equipo_origen_serial) {
    lineas.push(
      `📥 *Equipo recibido:* ${dev.equipo_origen_modelo || "Equipo"} · Serial: \`${dev.equipo_origen_serial}\` (Reingreso: ${dev.estado_reingreso_origen})`
    );
  }
  if (dev.equipo_destino_serial) {
    lineas.push(
      `📤 *Equipo entregado:* ${dev.equipo_destino_modelo || "Equipo"} · Serial: \`${dev.equipo_destino_serial}\``
    );
  }
  if (dev.caso_taller_numero) {
    lineas.push(`🔧 *Caso Taller (Garantía):* ${dev.caso_taller_numero}`);
  }
  if (dev.articulo_repuesto_descripcion) {
    lineas.push(
      `🧩 *Repuesto cubierto:* ${dev.articulo_repuesto_descripcion} ($0.00 al cliente)`
    );
  }

  if (dev.tipo_resolucion === "CAMBIO_IGUAL" || dev.tipo_resolucion === "GARANTIA_COMPONENTE") {
    lineas.push("💵 *Diferencia:* $0.00 (Cubierto por garantía Tekio)");
  } else if (dev.tipo_resolucion === "CAMBIO_UPGRADE") {
    lineas.push(
      `💵 *Diferencia abonada:* ${formatearUsd(Math.abs(dev.diferencia_usd))}${dev.instrumento ? ` · ${dev.instrumento}` : ""}${dev.referencia_pago ? ` · Ref: ${dev.referencia_pago}` : ""}`
    );
  } else if (dev.tipo_resolucion === "CAMBIO_DOWNGRADE") {
    lineas.push(
      dev.dejar_saldo_favor
        ? `💳 *Saldo a favor del cliente:* ${formatearUsd(Math.abs(dev.diferencia_usd))}`
        : `💸 *Diferencia reembolsada:* ${formatearUsd(Math.abs(dev.diferencia_usd))}${dev.instrumento ? ` · ${dev.instrumento}` : ""}`
    );
  } else if (dev.tipo_resolucion === "REEMBOLSO_TOTAL") {
    lineas.push(
      `💸 *Reembolso total:* ${formatearUsd(Math.abs(dev.diferencia_usd))}${dev.instrumento ? ` · ${dev.instrumento}` : ""}${dev.referencia_pago ? ` · Ref: ${dev.referencia_pago}` : ""}`
    );
  }

  if (dev.motivo) {
    lineas.push("", `📝 *Motivo:* ${dev.motivo}`);
  }
  return lineas.join("\n");
}

/**
 * 5. Lista de Precios para WhatsApp (agrupada por Modelo y Características, solo LISTO,
 *    mostrando exclusivamente Precio Promo USD o Precio Regular USD/Bs según selección).
 */
export function formatearWhatsAppListaPrecios(
  lista: ListaPreciosRespuesta
): string {
  const esRegular = lista.tipo_precio === "REGULAR";
  const lineas: string[] = [
    `💻 *TEKIO ELECTRONICS · EQUIPOS DISPONIBLES*`,
    `📅 Fecha: ${lista.fecha_emision} · 🏪 ${lista.sucursal}`,
    ...(esRegular && lista.tasa_bcv && lista.tasa_bcv > 0
      ? [`💱 Tasa BCV ref.: ${formatearBs(lista.tasa_bcv)}`]
      : []),
    "",
  ];

  if (lista.items.length === 0) {
    lineas.push("_Actualmente no hay equipos disponibles para esta sucursal._");
  } else {
    for (const item of lista.items) {
      const titulo = item.caracteristicas
        ? `*${item.modelo}* — ${item.caracteristicas}`
        : `*${item.modelo}*`;
      const dispTxt =
        item.disponibles === 1
          ? "1 disponible"
          : `${item.disponibles} disponibles`;
      if (esRegular) {
        const bsTxt =
          item.precio_bs && item.precio_bs > 0
            ? ` / *${formatearBs(item.precio_bs)}*`
            : "";
        lineas.push(
          `• ${titulo} (${dispTxt})\n  💵 *${formatearUsd(item.precio_usd)} USD*${bsTxt}`
        );
      } else {
        lineas.push(
          `• ${titulo} (${dispTxt})\n  💵 *${formatearUsd(item.precio_usd)} USD*`
        );
      }
    }
  }

  lineas.push(
    "",
    "🛡️ _Todos nuestros equipos incluyen 180 días de garantía Tekio Electronics._",
    "📲 WhatsApp: +58 424-4152658 · Valencia, Edo. Carabobo"
  );
  return lineas.join("\n");
}

/**
 * 6. Mensaje WhatsApp para Cotizaciones (sin costos internos).
 */
export function formatearWhatsAppCotizacion(cot: CotizacionResumen): string {
  const esDivisas = cot.modalidad_precio === "DIVISAS";
  const esCashea = cot.modalidad_precio === "CASHEA";
  const esJuridico =
    (cot.cliente_tipo_persona || "NATURAL").toUpperCase() === "JURIDICO";
  const etiquetaDoc = esJuridico ? "RIF" : "Cédula de Identidad";

  const lineas: string[] = [
    `📋 *TEKIO ELECTRONICS · COTIZACIÓN ${cot.numero_cotizacion}*`,
    `📅 Emisión: ${cot.fecha} · ⏳ Vigencia: ${cot.vigencia_horas}h`,
    `👤 Cliente: ${cot.cliente}${cot.cliente_rif ? ` · ${etiquetaDoc}: ${cot.cliente_rif}` : ""}`,
    `🏪 Sucursal: ${cot.sucursal || "Tekio central"} · 🤝 Asesor: ${cot.asesor || "Tienda"}`,
    "",
    "📦 *Detalle cotizado:*",
  ];

  for (const d of cot.detalles) {
    const unit = esDivisas ? d.precio_promo_usd : d.precio_regular_usd;
    const sub = unit * d.cantidad;
    const obsTxt = unit === 0 ? " *[OBSEQUIO]*" : ` — ${formatearUsd(sub)}`;
    lineas.push(`• ${d.cantidad}x ${d.descripcion}${obsTxt}`);
    if (d.descripcion_servicio) {
      lineas.push(`  ↳ _${d.descripcion_servicio}_`);
    }
  }

  const totalUsd = esDivisas ? cot.total_promo_usd : cot.total_regular_usd;
  lineas.push(
    "",
    `💵 *Monto Total:* *${formatearUsd(totalUsd)} USD*` +
      (!esDivisas && cot.total_regular_bs > 0
        ? ` (≈ *${formatearBs(cot.total_regular_bs)}* a tasa BCV ${formatearBs(cot.tasa_bcv_snapshot)})`
        : "")
  );

  if (esCashea) {
    const ini = totalUsd * 0.4;
    const cuota = (totalUsd - ini) / 3;
    lineas.push(
      `🟣 _Ref. Cashea (40%):_ Inicial aprox. ${formatearUsd(ini)} + 3 cuotas de ${formatearUsd(cuota)}`
    );
  }

  if (cot.nota) {
    lineas.push(`📝 Nota: ${cot.nota}`);
  }
  lineas.push(
    "",
    "⚠️ _Presupuesto sujeto a disponibilidad de inventario y tasa BCV vigente al momento del pago._"
  );
  return lineas.join("\n");
}

function formatearFechaLatam(iso: string): string {
  const partes = (iso || "").split("-");
  if (partes.length === 3) {
    return `${partes[2]}/${partes[1]}/${partes[0]}`;
  }
  return iso;
}

export function construirUrlWhatsApp(
  texto: string,
  telefono?: string | null
): string {
  const encoded = encodeURIComponent(texto);
  if (!telefono) return `https://wa.me/?text=${encoded}`;
  const digitos = telefono.replace(/\D/g, "");
  if (digitos.length < 10) return `https://wa.me/?text=${encoded}`;
  const normalizado =
    digitos.startsWith("0") && digitos.length === 11
      ? `58${digitos.slice(1)}`
      : digitos.length === 10 && digitos.startsWith("4")
      ? `58${digitos}`
      : digitos;
  return `https://wa.me/${normalizado}?text=${encoded}`;
}

/**
 * 7. Resumen individual de comisiones para enviar por WhatsApp (sin costos internos ni márgenes).
 */
export function formatearWhatsAppComisionIndividual(
  persona: ComisionPersona,
  fechaInicio: string,
  fechaFin: string,
  incluirNotas: boolean
): string {
  const periodo = `${formatearFechaLatam(fechaInicio)} al ${formatearFechaLatam(fechaFin)}`;
  const cantVentas = persona.cantidad_ventas ?? 0;
  const esLider = persona.rol === "LIDER";
  const esTecnico =
    persona.rol === "TECNICO" ||
    persona.comision_servicios_50_usd > 0 ||
    persona.pago_preparaciones_usd > 0;

  const lineas: string[] = [
    "💼 *Resumen de Comisiones — Tekio Electronics*",
    `📅 Período: *${periodo}*`,
    `👤 Colaborador: *${persona.nombre}* (${persona.rol})`,
    "",
    "📊 *Desglose (sobre Precio Promo USD):*",
  ];

  if (persona.ventas_promo_usd > 0 || persona.comision_ventas_1_usd > 0 || !esTecnico) {
    lineas.push(
      `• Ventas propias (${cantVentas}): Base ${formatearUsd(persona.ventas_promo_usd)} → *1%: ${formatearUsd(persona.comision_ventas_1_usd)}*`
    );
  }

  if (esLider) {
    const baseEquipo = persona.ventas_equipo_lider_usd ?? 0;
    lineas.push(
      `• Equipo multi-tienda: Base ${formatearUsd(baseEquipo)} → *0,5%: ${formatearUsd(persona.comision_lider_05_usd)}*`
    );
  }

  if (esTecnico) {
    lineas.push(
      `• Servicios técnicos / Mano de obra (50%): *${formatearUsd(persona.comision_servicios_50_usd)}*`,
      `• Preparaciones de equipos: *${formatearUsd(persona.pago_preparaciones_usd)}*`
    );
  }

  if (incluirNotas && persona.notas && persona.notas.length > 0) {
    const notasTxt = persona.notas.slice(0, 40).join(", ");
    const sufijo =
      persona.notas.length > 40 ? ` (+${persona.notas.length - 40} más)` : "";
    lineas.push("", `🧾 *Notas incluidas:* ${notasTxt}${sufijo}`);
  }

  lineas.push(
    "",
    `💵 *TOTAL A PAGAR: ${formatearUsd(persona.total_comision_usd)} USD*`
  );

  return lineas.join("\n");
}

/**
 * 8. Resumen general de comisiones del filtro activo para WhatsApp (sin costos internos ni márgenes).
 */
export function formatearWhatsAppComisionesGeneral(
  comisiones: ComisionPersona[],
  fechaInicio: string,
  fechaFin: string,
  incluirNotas: boolean
): string {
  const periodo = `${formatearFechaLatam(fechaInicio)} al ${formatearFechaLatam(fechaFin)}`;
  const totalBase = comisiones.reduce((acc, c) => acc + c.ventas_promo_usd, 0);
  const totalPagar = comisiones.reduce((acc, c) => acc + c.total_comision_usd, 0);

  const lineas: string[] = [
    "📊 *Resumen General de Comisiones — Tekio Electronics*",
    `📅 Período: *${periodo}*`,
    `💵 Base Promo USD: *${formatearUsd(totalBase)}*`,
    "",
    "👥 *Detalle por colaborador:*",
  ];

  for (const c of comisiones) {
    const partes: string[] = [];
    if (c.comision_ventas_1_usd > 0) {
      partes.push(`1% Ventas: ${formatearUsd(c.comision_ventas_1_usd)}`);
    }
    if (c.comision_lider_05_usd > 0) {
      partes.push(`0,5% Líder: ${formatearUsd(c.comision_lider_05_usd)}`);
    }
    if (c.comision_servicios_50_usd > 0) {
      partes.push(`50% ST: ${formatearUsd(c.comision_servicios_50_usd)}`);
    }
    if (c.pago_preparaciones_usd > 0) {
      partes.push(`Preps: ${formatearUsd(c.pago_preparaciones_usd)}`);
    }
    const detalleTxt = partes.length > 0 ? ` (${partes.join(" · ")})` : "";
    lineas.push(
      `• *${c.nombre}* [${c.rol}]: *${formatearUsd(c.total_comision_usd)}*${detalleTxt}`
    );
    if (incluirNotas && c.notas && c.notas.length > 0) {
      lineas.push(`  ↳ _Notas:_ ${c.notas.slice(0, 20).join(", ")}`);
    }
  }

  lineas.push(
    "",
    `💰 *TOTAL COMISIONES A PAGAR: ${formatearUsd(totalPagar)} USD*`
  );
  return lineas.join("\n");
}

/**
 * 9. Comprobante de Liquidación de Comisiones para WhatsApp.
 */
export function formatearWhatsAppLiquidacion(
  liq: LiquidacionComisionResumen
): string {
  const periodo = `${formatearFechaLatam(liq.fecha_inicio)} al ${formatearFechaLatam(liq.fecha_fin)}`;
  const lineas: string[] = [
    `✅ *COMPROBANTE DE LIQUIDACIÓN · TEKIO ELECTRONICS*`,
    `🧾 Código: *${liq.codigo}* · Fecha pago: ${formatearFechaLatam(liq.fecha_pago)}`,
    `👤 Colaborador: *${liq.usuario_nombre}* (${liq.usuario_rol})`,
    `📅 Período liquidado: *${periodo}*`,
    `💳 Método de pago: ${liq.instrumento}${liq.referencia ? ` · Ref: ${liq.referencia}` : ""}`,
    `💵 *Monto pagado: ${formatearUsd(liq.monto_total_usd)} USD*`,
  ];
  if (liq.notas_liquidadas && liq.notas_liquidadas.length > 0) {
    lineas.push(`📋 Operaciones (${liq.cantidad_operaciones}): ${liq.notas_liquidadas.slice(0, 30).join(", ")}`);
  }
  if (liq.notas) {
    lineas.push(`📝 Nota: ${liq.notas}`);
  }
  return lineas.join("\n");
}

/**
 * 10. Resumen de Cierre de Caja Diario para grupo gerencial en WhatsApp.
 */
export function formatearWhatsAppCierreCaja(cierre: CierreCajaResumen): string {
  const dif = cierre.diferencia_usd;
  const estadoCaja =
    dif === 0 ? "✅ CUADRADO" : dif > 0 ? `🟢 SOBRANTE (+${formatearUsd(dif)})` : `🔴 FALTANTE (${formatearUsd(dif)})`;
  const lineas: string[] = [
    `🏦 *CIERRE DIARIO DE TIENDA · TEKIO ELECTRONICS*`,
    `📅 Fecha: *${formatearFechaLatam(cierre.fecha)}* · 🏪 Sucursal: *${cierre.sucursal}*`,
    `👤 Líder / Encargado: *${cierre.lider_encargado || cierre.usuario}* · Elaborado por: ${cierre.usuario}`,
  ];

  if (cierre.tasas_dia) {
    lineas.push(
      `💱 Tasas: BCV *${formatearBs(cierre.tasas_dia.tasa_bcv)}* · USDT *${formatearBs(cierre.tasas_dia.tasa_usdt)}* · Recargo *${cierre.tasas_dia.recargo_porcentaje.toFixed(2)}%*`
    );
  }

  lineas.push(
    "",
    `🧾 Ventas emitidas: *${cierre.cantidad_ventas}* (Anulaciones/Dev.: ${cierre.cantidad_anulaciones})`,
    `💵 Total Ventas Promo: *${formatearUsd(cierre.total_ventas_usd)}*`,
    `📥 Ingresos: *${formatearUsd(cierre.total_ingresos_usd)} USD* / ${formatearBs(cierre.total_ingresos_bs)}`,
    `🟣 Cashea Financiado: *${formatearUsd(cierre.total_cashea_usd)} USD*`,
    `📤 Egresos del día: *${formatearUsd(cierre.total_egresos_usd)} USD* / ${formatearBs(cierre.total_egresos_bs)}`,
    "",
    `💰 *Cuadre Efectivo USD:*`,
    `• Esperado: ${formatearUsd(cierre.efectivo_esperado_usd)}`,
    `• Declarado: ${formatearUsd(cierre.efectivo_declarado_usd)}`,
    `• Resultado: *${estadoCaja}*`
  );

  if (cierre.inventario) {
    lineas.push(
      "",
      `📦 *Inventario y Almacén:*`,
      `• Recepciones hoy: *${cierre.inventario.recepciones_dia}* · Traslados recibidos: *${cierre.inventario.traslados_recibidos_dia}*`,
      `• Salientes hoy: *${cierre.inventario.unidades_salientes_dia}* (Ventas: ${cierre.inventario.unidades_vendidas_dia} / Traslados: ${cierre.inventario.traslados_despachados_dia})`,
      `• Stock disponible (LISTO): *${cierre.inventario.stock_disponible_listo}* equipos`
    );
  }

  if (cierre.taller) {
    lineas.push(
      "",
      `🛠️ *Taller y Garantías (GT / ST):*`,
      `• Recibidos hoy: *${cierre.taller.recibidos_dia}* · Resueltos/Entregados hoy: *${cierre.taller.resueltos_dia}*`,
      `• Pendientes activos: *${cierre.taller.pendientes_total}* (GT: ${cierre.taller.gt_pendientes} / ST: ${cierre.taller.st_pendientes})`
    );
  }

  if (cierre.desglose_instrumentos && cierre.desglose_instrumentos.length > 0) {
    lineas.push("", "💳 *Desglose por Instrumento:*");
    for (const d of cierre.desglose_instrumentos) {
      const montoTxt =
        d.moneda === "BS"
          ? `${formatearBs(d.neto_origen)} (≈ ${formatearUsd(d.neto_usd)})`
          : `${formatearUsd(d.neto_origen)} ${d.moneda}`;
      lineas.push(`• ${d.instrumento}: *${montoTxt}*`);
    }
  }
  if (cierre.desglose_asesores && cierre.desglose_asesores.length > 0) {
    lineas.push("", "🤝 *Ventas por Asesor (Promo USD):*");
    for (const a of cierre.desglose_asesores) {
      lineas.push(
        `• ${a.asesor} (${a.cantidad_ventas}): *${formatearUsd(a.total_promo_usd)}*`
      );
    }
  }
  if (cierre.observaciones) {
    lineas.push("", `📝 Observaciones: ${cierre.observaciones}`);
  }
  return lineas.join("\n");
}

export interface ResumenEjecutivoPL {
  mes: string;
  mes_anterior: string;
  fecha_inicio: string;
  fecha_fin: string;
  sucursal_id: number | null;
  sucursal: string;
  emitido_en: string;
  resultados: {
    cantidad_ventas: number;
    ingresos_ventas_usd: number;
    costo_mercancia_usd: number;
    utilidad_bruta_usd: number;
    margen_bruto_pct: number;
    gastos_operativos_usd: number;
    comisiones_liquidadas_usd: number;
    nomina_pagada_usd: number;
    diferencial_cambiario_usd: number;
    utilidad_neta_usd: number;
    margen_neto_pct: number;
    utilidad_neta_mes_anterior_usd: number;
    variacion_neta_pct: number;
    top_gastos: { categoria: string; cantidad: number; total_usd: number }[];
  };
  desglose_sucursales: {
    sucursal: string;
    cantidad_ventas: number;
    ventas_usd: number;
    contribucion_usd: number;
  }[];
  salud_caja: {
    liquidez_total_usd: number;
    cxc_clientes_usd: number;
    cxc_cashea_usd: number;
    cxc_total_usd: number;
    cxp_total_usd: number;
  };
  directores: { id: number; nombre: string; telefono: string }[];
}

const MESES_ES = [
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
];

/**
 * 11. Resumen Ejecutivo Mensual del Estado de Resultados (P&L) para Directores por WhatsApp.
 */
export function formatearResumenEjecutivoPL(
  datos: ResumenEjecutivoPL,
  opciones: { incluirPosicionFinanciera?: boolean } = {}
): string {
  const incluirPosicion = opciones.incluirPosicionFinanciera ?? true;
  const [anioStr, mesStr] = (datos.mes || "").split("-");
  const idxMes = Number(mesStr) - 1;
  const nombreMes =
    idxMes >= 0 && idxMes < 12 ? `${MESES_ES[idxMes]} ${anioStr}` : datos.mes;
  const alcance = datos.sucursal_id ? datos.sucursal : "Consolidado";
  const r = datos.resultados;
  const iconoVar = r.variacion_neta_pct >= 0 ? "📈" : "📉";
  const signoVar = r.variacion_neta_pct >= 0 ? "+" : "";
  const signoDif = r.diferencial_cambiario_usd >= 0 ? "+" : "";

  const lineas: string[] = [
    `📊 *RESUMEN EJECUTIVO MENSUAL — TEKIO ELECTRONICS*`,
    `📅 Período: *${nombreMes}* · 🏪 Alcance: *${alcance}*`,
    "",
    `💼 *1. Resultados del Mes (${r.cantidad_ventas} ventas):*`,
    `• Ingresos Totales: *${formatearUsd(r.ingresos_ventas_usd)}*`,
    `• Costo Mercancía (COGS): -${formatearUsd(r.costo_mercancia_usd)}`,
    `• Utilidad Bruta: *${formatearUsd(r.utilidad_bruta_usd)}* (${r.margen_bruto_pct.toFixed(1)}%)`,
    `• Gastos Operativos: -${formatearUsd(r.gastos_operativos_usd)}`,
    `• Nómina y Comisiones: -${formatearUsd(r.nomina_pagada_usd + r.comisiones_liquidadas_usd)}`,
    `• Diferencial Cambiario: ${signoDif}${formatearUsd(r.diferencial_cambiario_usd)}`,
    `• *UTILIDAD NETA: ${formatearUsd(r.utilidad_neta_usd)} (${r.margen_neto_pct.toFixed(1)}%)*`,
    `  ${iconoVar} Variación vs. ${datos.mes_anterior}: *${signoVar}${r.variacion_neta_pct.toFixed(1)}%*`,
  ];

  if (r.top_gastos && r.top_gastos.length > 0) {
    lineas.push(
      `• Top Gastos: ${r.top_gastos
        .map((g) => `${g.categoria} (${formatearUsd(g.total_usd)})`)
        .join(", ")}`
    );
  }

  if (datos.desglose_sucursales && datos.desglose_sucursales.length > 0) {
    lineas.push("", "🏪 *2. Rendimiento por Sucursal:*");
    for (const s of datos.desglose_sucursales) {
      lineas.push(
        `• ${s.sucursal} (${s.cantidad_ventas}): Ventas *${formatearUsd(s.ventas_usd)}* · Contrib. *${formatearUsd(s.contribucion_usd)}*`
      );
    }
  }

  if (incluirPosicion) {
    const sc = datos.salud_caja;
    lineas.push(
      "",
      "🏦 *3. Posición Financiera al Cierre:*",
      `• Liquidez Cajas y Bancos: *${formatearUsd(sc.liquidez_total_usd)}*`,
      `• CxC Pendientes: *${formatearUsd(sc.cxc_total_usd)}* (Cashea: ${formatearUsd(sc.cxc_cashea_usd)})`,
      `• CxP Proveedores: *${formatearUsd(sc.cxp_total_usd)}*`
    );
  }

  lineas.push(
    "",
    `🕒 Emitido: ${datos.emitido_en} (Caracas)`,
    "🔒 _Confidencial · Uso exclusivo Dirección_"
  );
  return lineas.join("\n");
}
