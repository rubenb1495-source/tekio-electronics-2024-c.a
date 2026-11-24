import { formatearBs, formatearUsd } from "@/servicios/api";
import type { PagoBandeja, VentaResumen } from "@/tipos/finanzas";
import type { TrasladoResumen } from "@/tipos/logistica";

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
  const lineas: string[] = [
    `🧾 *TEKIO ELECTRONICS · Nota ${venta.numero_venta}*`,
    `📅 Fecha: ${formatearFechaHora(venta.fecha, venta.creado_en)}`,
    `🏪 Sucursal: ${venta.sucursal || "Tekio central"} · Entrega: ${venta.tipo_entrega} · Canal: ${venta.canal_visita}`,
    `👤 Cliente: ${venta.cliente}${venta.cliente_rif ? ` (${venta.cliente_rif})` : ""}${venta.cliente_telefono ? ` · Tel: ${venta.cliente_telefono}` : ""}`,
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
