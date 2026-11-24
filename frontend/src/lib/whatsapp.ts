import { formatearBs, formatearUsd } from "@/servicios/api";
import type { PagoBandeja, VentaResumen } from "@/tipos/finanzas";
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
