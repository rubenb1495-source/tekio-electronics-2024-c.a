"use client";

import React, { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  AlertCircle,
  ArrowRightLeft,
  CheckCircle2,
  ClipboardList,
  Package,
  Plane,
  Search,
  ShoppingBag,
  ShieldAlert,
  Wrench,
} from "lucide-react";
import { ErrorApi, formatearUsd, solicitarApi } from "@/servicios/api";

interface TrazabilidadRespuesta {
  equipo: {
    id: number;
    serial: string;
    sku: string | null;
    modelo: string;
    configuracion: string;
    categoria: string;
    ubicacion: string | null;
    estado: string;
    proceso_inicial?: string;
    precio_promo_usd: number;
    primer_costo_usd?: number;
    comision_preparacion_usd?: number;
    costo_final_usd?: number;
    costo_total_usd?: number;
  };
  compra_internacional: {
    numero_compra: string;
    fecha: string | null;
    tipo_compra: string;
    origen: string;
    proveedor: string;
    factura_orden: string;
    descripcion_lote: string;
    cantidad_esperada: number;
    monto_mercancia_usd?: number;
    taxes_usd?: number;
    envio_miami_usd?: number;
    subtotal_miami_usd?: number;
    gastos_envio_venezuela_usd?: number;
  } | null;
  recepcion: {
    fecha_recepcion: string | null;
    ubicacion: string | null;
    recibido_por: string | null;
    condicion_llegada: string;
    incluye_cargador: boolean;
    observaciones_llegada: string;
    proceso_inicial: string;
    primer_costo_usd?: number;
  };
  historial_procesos: {
    fecha: string | null;
    evento: string;
    usuario: string | null;
    sucursal: string | null;
    notas: string;
  }[];
  preparacion: {
    componentes_agregados: {
      sku: string | null;
      descripcion: string;
      cantidad: number;
      fecha: string | null;
      tecnico: string | null;
      costo_unitario_usd?: number;
      costo_total_usd?: number;
    }[];
    cantidad_preparaciones: number;
    estado_actual: string;
    primer_costo_usd?: number;
    total_componentes_usd?: number;
    comision_preparacion_usd?: number;
    costo_final_usd?: number;
  };
  traslados: {
    numero_traslado: string;
    fecha_envio: string | null;
    fecha_recepcion: string | null;
    origen: string | null;
    destino: string | null;
    estado: string;
  }[];
  venta: {
    venta_id: number;
    numero_venta: string;
    fecha: string | null;
    sede: string | null;
    asesor: string;
    cliente: string;
    precio_venta_usd: number;
    estado: string;
    costo_final_usd?: number;
    ganancia_real_usd?: number;
  } | null;
  incidentes_postventa: {
    origen: string;
    codigo: string;
    tipo: string;
    fecha: string | null;
    falla_reportada: string;
    tecnico: string | null;
    estado: string;
    resolucion: string;
  }[];
}

function ContenidoTrazabilidadSerial() {
  const searchParams = useSearchParams();
  const serialInicial = searchParams.get("serial") || "";

  const [serialInput, setSerialInput] = useState(serialInicial);
  const [data, setData] = useState<TrazabilidadRespuesta | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buscar = useCallback(async (sn: string) => {
    const limpio = sn.trim().toUpperCase();
    if (!limpio) return;
    setCargando(true);
    setError(null);
    try {
      const resp = await solicitarApi<TrazabilidadRespuesta>(
        `/api/inventario/trazabilidad/${encodeURIComponent(limpio)}`
      );
      setData(resp);
    } catch (err) {
      setData(null);
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se encontró trazabilidad para ese serial."
      );
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    if (serialInicial) {
      void buscar(serialInicial);
    }
  }, [serialInicial, buscar]);

  const verCostos = data?.preparacion.costo_final_usd !== undefined;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-black text-[#191818] flex items-center gap-2">
          <Search className="w-6 h-6 text-[#E85A28]" />
          Trazabilidad Total por Serial (Hoja de Vida)
        </h2>
        <p className="text-sm text-neutral-500">
          Consulta cronológica completa: Compra Internacional, Recepción y Primer Costo, Preparación y Costo Final, Traslados, Venta y Post-venta.
        </p>
      </div>

      {/* Buscador de serial */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void buscar(serialInput);
        }}
        className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-4 flex flex-wrap items-center gap-3"
      >
        <input
          type="text"
          value={serialInput}
          onChange={(e) => setSerialInput(e.target.value.toUpperCase())}
          placeholder="Ingresa o escanea el serial del equipo (ej. SN-INT-001)..."
          className="flex-1 min-w-[240px] px-4 py-2.5 rounded-xl border-2 border-[#E85A28]/40 bg-white font-mono text-sm font-bold text-[#191818]"
        />
        <button
          type="submit"
          disabled={cargando || !serialInput.trim()}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#D14D20] disabled:opacity-50 text-white text-xs font-black cursor-pointer"
        >
          <Search className="w-4 h-4" />
          {cargando ? "Buscando..." : "Consultar Hoja de Vida"}
        </button>
      </form>

      {error && (
        <div className="flex items-center gap-2.5 p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {data && (
        <div className="space-y-5">
          {/* Resumen del Equipo */}
          <div className="bg-white/90 backdrop-blur-md border-2 border-[#E85A28]/35 rounded-2xl p-5 flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-lg font-black text-[#191818]">
                  {data.equipo.serial}
                </span>
                <span className="px-2.5 py-0.5 rounded-full bg-[#FDF0EB] text-[#E85A28] text-xs font-black">
                  {data.equipo.estado}
                </span>
              </div>
              <p className="text-sm font-bold text-neutral-700 mt-0.5">
                {data.equipo.modelo}{" "}
                {data.equipo.configuracion ? `· ${data.equipo.configuracion}` : ""}
              </p>
              <p className="text-xs text-neutral-500">
                Ubicación actual: <strong>{data.equipo.ubicacion || "—"}</strong> · Precio Promo:{" "}
                <strong className="tabular-nums">{formatearUsd(data.equipo.precio_promo_usd)}</strong>
              </p>
            </div>

            {verCostos && (
              <div className="flex flex-wrap gap-3 tabular-nums">
                <div className="px-4 py-2 rounded-xl bg-[#F6F6F6] border border-neutral-200 text-right">
                  <p className="text-[10px] font-bold uppercase text-neutral-500">Primer Costo</p>
                  <p className="text-base font-black text-[#191818]">
                    {formatearUsd(data.preparacion.primer_costo_usd)}
                  </p>
                </div>
                <div className="px-4 py-2 rounded-xl bg-[#FDF0EB] border border-[#E85A28]/40 text-right">
                  <p className="text-[10px] font-bold uppercase text-[#E85A28]">Costo Final</p>
                  <p className="text-base font-black text-[#191818]">
                    {formatearUsd(data.preparacion.costo_final_usd)}
                  </p>
                </div>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* 1. Compra Internacional */}
            <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 space-y-2.5">
              <h3 className="text-sm font-black text-[#191818] flex items-center gap-2">
                <Plane className="w-4 h-4 text-[#E85A28]" />
                1. Compra Internacional / Origen
              </h3>
              {data.compra_internacional ? (
                <div className="text-xs space-y-1 text-neutral-700 tabular-nums">
                  <p>
                    Lote: <strong className="font-mono text-[#191818]">{data.compra_internacional.numero_compra}</strong>{" "}
                    ({data.compra_internacional.tipo_compra}) · Fecha: <strong>{data.compra_internacional.fecha}</strong>
                  </p>
                  <p>Proveedor: <strong>{data.compra_internacional.proveedor}</strong></p>
                  {data.compra_internacional.descripcion_lote && (
                    <p>Descripción previa: {data.compra_internacional.descripcion_lote}</p>
                  )}
                  {verCostos && (
                    <div className="grid grid-cols-2 gap-1.5 pt-2 border-t border-neutral-100 text-[11px]">
                      <p>Compra: <strong>{formatearUsd(data.compra_internacional.monto_mercancia_usd)}</strong></p>
                      <p>Taxes USA: <strong>{formatearUsd(data.compra_internacional.taxes_usd)}</strong></p>
                      <p>Envío a Miami: <strong>{formatearUsd(data.compra_internacional.envio_miami_usd)}</strong></p>
                      <p>Subtotal Miami: <strong>{formatearUsd(data.compra_internacional.subtotal_miami_usd)}</strong></p>
                      <p className="col-span-2 text-[#E85A28]">
                        Gastos envío a Venezuela: <strong>{formatearUsd(data.compra_internacional.gastos_envio_venezuela_usd)}</strong>
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-xs text-neutral-500">Sin lote de compra vinculado.</p>
              )}
            </div>

            {/* 2. Recepción */}
            <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 space-y-2.5">
              <h3 className="text-sm font-black text-[#191818] flex items-center gap-2">
                <Package className="w-4 h-4 text-[#E85A28]" />
                2. Recepción en Venezuela y Primer Costo
              </h3>
              <div className="text-xs space-y-1 text-neutral-700 tabular-nums">
                <p>Fecha: <strong>{data.recepcion.fecha_recepcion || "—"}</strong> · Ubicación: <strong>{data.recepcion.ubicacion || "—"}</strong></p>
                <p>Proceso inicial asignado: <strong className="text-[#E85A28]">{data.recepcion.proceso_inicial}</strong></p>
                <p>
                  Condición: <strong>{data.recepcion.condicion_llegada}</strong> · Cargador:{" "}
                  <strong>{data.recepcion.incluye_cargador ? "Sí" : "No"}</strong>
                </p>
                {data.recepcion.observaciones_llegada && (
                  <p>Observaciones: {data.recepcion.observaciones_llegada}</p>
                )}
                {verCostos && (
                  <p className="pt-2 border-t border-neutral-100 font-bold text-[#191818]">
                    Primer Costo (Aterrizado): {formatearUsd(data.recepcion.primer_costo_usd)}
                  </p>
                )}
              </div>
            </div>

            {/* 4. Preparación y Costo Final */}
            <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 space-y-2.5">
              <h3 className="text-sm font-black text-[#191818] flex items-center gap-2">
                <Wrench className="w-4 h-4 text-[#E85A28]" />
                4. Preparación y Desglose de Costo Final
              </h3>
              {data.preparacion.componentes_agregados.length > 0 ? (
                <div className="divide-y divide-neutral-100 text-xs">
                  {data.preparacion.componentes_agregados.map((c, idx) => (
                    <div key={idx} className="py-1.5 flex items-center justify-between gap-2">
                      <span>
                        <strong className="font-mono">{c.sku || "COMP"}</strong> — {c.descripcion} (x{c.cantidad})
                      </span>
                      {verCostos && (
                        <span className="font-bold tabular-nums">{formatearUsd(c.costo_total_usd)}</span>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-neutral-500">Sin componentes instalados.</p>
              )}
              {verCostos && (
                <div className="pt-2 border-t border-neutral-100 text-xs space-y-1 tabular-nums">
                  <p>Componentes agregados: <strong>{formatearUsd(data.preparacion.total_componentes_usd)}</strong></p>
                  <p>Comisión de preparación: <strong>{formatearUsd(data.preparacion.comision_preparacion_usd)}</strong></p>
                  <p className="text-sm font-black text-[#E85A28]">
                    Costo Final Oficial: {formatearUsd(data.preparacion.costo_final_usd)}
                  </p>
                </div>
              )}
            </div>

            {/* 6. Venta y Ganancia Real */}
            <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 space-y-2.5">
              <h3 className="text-sm font-black text-[#191818] flex items-center gap-2">
                <ShoppingBag className="w-4 h-4 text-[#E85A28]" />
                6. Venta y Ganancia Real
              </h3>
              {data.venta ? (
                <div className="text-xs space-y-1 text-neutral-700 tabular-nums">
                  <p>
                    Nota: <strong className="font-mono text-[#191818]">{data.venta.numero_venta}</strong> · Fecha:{" "}
                    <strong>{data.venta.fecha}</strong> · Sede: <strong>{data.venta.sede}</strong>
                  </p>
                  <p>Asesor: <strong>{data.venta.asesor}</strong> · Cliente: <strong>{data.venta.cliente}</strong></p>
                  <p>Precio de venta: <strong className="text-[#191818]">{formatearUsd(data.venta.precio_venta_usd)}</strong></p>
                  {verCostos && (
                    <p className="pt-1 text-sm font-black text-emerald-700">
                      Ganancia Real (vs Costo Final): {formatearUsd(data.venta.ganancia_real_usd)}
                    </p>
                  )}
                </div>
              ) : (
                <p className="text-xs text-neutral-500">Equipo aún no vendido.</p>
              )}
            </div>
          </div>

          {/* 3. Historial de Procesos + 5. Traslados + 7. Incidentes Post-venta */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 space-y-2.5">
              <h3 className="text-sm font-black text-[#191818] flex items-center gap-2">
                <ClipboardList className="w-4 h-4 text-[#E85A28]" />
                3. Historial de Procesos
              </h3>
              <div className="max-h-56 overflow-y-auto divide-y divide-neutral-100 text-xs">
                {data.historial_procesos.map((h, i) => (
                  <div key={i} className="py-1.5">
                    <p className="font-bold text-[#191818]">
                      {h.evento} <span className="font-normal text-neutral-400">· {h.fecha?.slice(0, 16).replace("T", " ")}</span>
                    </p>
                    <p className="text-[11px] text-neutral-600">{h.notas || "—"}</p>
                    {h.usuario && <p className="text-[10px] text-neutral-400">Por: {h.usuario}</p>}
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 space-y-2.5">
              <h3 className="text-sm font-black text-[#191818] flex items-center gap-2">
                <ArrowRightLeft className="w-4 h-4 text-[#E85A28]" />
                5. Traslados
              </h3>
              {data.traslados.length > 0 ? (
                <div className="divide-y divide-neutral-100 text-xs">
                  {data.traslados.map((t, i) => (
                    <div key={i} className="py-1.5">
                      <p className="font-mono font-bold text-[#191818]">{t.numero_traslado} · {t.estado}</p>
                      <p className="text-[11px] text-neutral-600">{t.origen} → {t.destino}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-neutral-500">Sin traslados registrados.</p>
              )}
            </div>

            <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 space-y-2.5">
              <h3 className="text-sm font-black text-[#191818] flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-[#E85A28]" />
                7. Incidentes Post-venta
              </h3>
              {data.incidentes_postventa.length > 0 ? (
                <div className="divide-y divide-neutral-100 text-xs">
                  {data.incidentes_postventa.map((inc, i) => (
                    <div key={i} className="py-1.5">
                      <p className="font-bold text-[#191818]">
                        {inc.codigo} ({inc.tipo}) · {inc.estado}
                      </p>
                      <p className="text-[11px] text-neutral-600">Falla: {inc.falla_reportada || "—"}</p>
                      {inc.resolucion && (
                        <p className="text-[11px] text-emerald-700 flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" /> {inc.resolucion}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-neutral-500">Sin garantías ni incidentes registrados.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function PaginaTrazabilidadSerial() {
  return (
    <Suspense fallback={<div className="h-40 rounded-2xl bg-white/70 animate-pulse" />}>
      <ContenidoTrazabilidadSerial />
    </Suspense>
  );
}
