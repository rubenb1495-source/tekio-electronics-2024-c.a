"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Building2,
  Check,
  CheckCircle2,
  Copy,
  FileDown,
  Landmark,
  Loader2,
  Receipt,
  Save,
} from "lucide-react";
import BuscadorTabla from "@/componentes/BuscadorTabla";
import { usePermisos } from "@/lib/permisos";
import {
  copiarTextoPortapapeles,
  formatearWhatsAppCierreCaja,
} from "@/lib/whatsapp";
import {
  ErrorApi,
  descargarPdfApi,
  fechaHoyCaracas,
  formatearBs,
  formatearUsd,
  solicitarApi,
} from "@/servicios/api";
import type { Sucursal } from "@/tipos/dominio";
import type { CierreCajaResumen, PreviewCierreCaja } from "@/tipos/finanzas";

interface SaldoInstrumentoItem {
  id: number;
  nombre: string;
  moneda: string;
  saldo_moneda_origen: number;
  saldo_usd: number;
}

interface TableroSaldosCierre {
  fecha: string;
  sucursal_id: number | null;
  ambito_usuario: "ADMINISTRACION_GENERAL" | "TIENDA";
  tienda: {
    sucursal: string;
    efectivo_esperado_dia_usd: number;
    ventas_del_dia_usd: number;
    cantidad_ventas: number;
    vueltos_entregados_usd: number;
    canales_locales: SaldoInstrumentoItem[];
    total_saldos_locales_usd: number;
  };
  administracion_general: {
    cuentas_corporativas: SaldoInstrumentoItem[];
    total_liquidez_corporativa_usd: number;
    total_liquidez_consolidada_usd: number;
    cashea_por_cobrar_usd: number;
    cxc_clientes_usd: number;
    cxp_proveedores_usd: number;
  } | null;
}

export default function PaginaCierreCajaDiario() {
  const permisos = usePermisos();
  const [vistaAmbito, setVistaAmbito] = useState<"TIENDA" | "ADMIN_GENERAL">("TIENDA");
  const [tableroSaldos, setTableroSaldos] = useState<TableroSaldosCierre | null>(null);
  const [fecha, setFecha] = useState(fechaHoyCaracas());
  const [sucursalId, setSucursalId] = useState(
    permisos.sucursalRestringidaId ? String(permisos.sucursalRestringidaId) : ""
  );
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);

  useEffect(() => {
    if (permisos.sucursalRestringidaId) {
      setSucursalId(String(permisos.sucursalRestringidaId));
    }
  }, [permisos.sucursalRestringidaId]);

  const [preview, setPreview] = useState<PreviewCierreCaja | null>(null);
  const [cierres, setCierres] = useState<CierreCajaResumen[]>([]);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cierreReciente, setCierreReciente] = useState<CierreCajaResumen | null>(
    null
  );

  // Formulario de conteo físico
  const [efectivoDeclarado, setEfectivoDeclarado] = useState("");
  const [observaciones, setObservaciones] = useState("");
  const [busqueda, setBusqueda] = useState("");
  const [copiadoId, setCopiadoId] = useState<number | null>(null);

  useEffect(() => {
    solicitarApi<Sucursal[]>("/api/sucursales")
      .then((res) => setSucursales(res))
      .catch(() => {});
  }, []);

  const cargarTodo = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const paramsPrev = new URLSearchParams();
      if (fecha) paramsPrev.set("fecha", fecha);
      if (sucursalId) paramsPrev.set("sucursal_id", sucursalId);

      const paramsHist = sucursalId ? `?sucursal_id=${sucursalId}` : "";
      const [respPrev, respHist, respTablero] = await Promise.all([
        solicitarApi<PreviewCierreCaja>(
          `/api/finanzas/cierre-caja/preview?${paramsPrev.toString()}`
        ),
        solicitarApi<CierreCajaResumen[]>(
          `/api/finanzas/cierre-caja${paramsHist}`
        ),
        solicitarApi<TableroSaldosCierre>(
          `/api/finanzas/cierre-caja/tablero-saldos?${paramsPrev.toString()}`
        ).catch(() => null),
      ]);
      setPreview(respPrev);
      setCierres(respHist);
      setTableroSaldos(respTablero);
      setEfectivoDeclarado(String(respPrev.efectivo_esperado_usd));
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo cargar el cierre de caja."
      );
    } finally {
      setCargando(false);
    }
  }, [fecha, sucursalId]);

  useEffect(() => {
    void cargarTodo();
  }, [cargarTodo]);

  const esperadoUsd = preview?.efectivo_esperado_usd ?? 0;
  const declaradoNum = Number(efectivoDeclarado || 0);
  const diferenciaEnVivo = Number.isFinite(declaradoNum)
    ? declaradoNum - esperadoUsd
    : 0;

  const guardarCierre = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setGuardando(true);
    try {
      const creado = await solicitarApi<CierreCajaResumen>(
        "/api/finanzas/cierre-caja",
        {
          method: "POST",
          body: JSON.stringify({
            fecha,
            sucursal_id: sucursalId ? Number(sucursalId) : null,
            efectivo_declarado_usd: Math.max(0, Number(efectivoDeclarado) || 0),
            observaciones: observaciones.trim(),
          }),
        }
      );
      setCierreReciente(creado);
      setObservaciones("");
      await cargarTodo();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo guardar el cierre de caja."
      );
    } finally {
      setGuardando(false);
    }
  };

  const copiarWa = async (cierre: CierreCajaResumen) => {
    const ok = await copiarTextoPortapapeles(formatearWhatsAppCierreCaja(cierre));
    if (ok) {
      setCopiadoId(cierre.id);
      setTimeout(() => setCopiadoId(null), 2400);
    }
  };

  const cierresFiltrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return cierres;
    return cierres.filter((c) =>
      [c.fecha, c.sucursal, c.usuario, c.observaciones]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [cierres, busqueda]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-[#191818] flex items-center gap-2">
            <Receipt className="w-6 h-6 text-[#E85A28]" />
            Cierre de Caja Diario
          </h2>
          <p className="text-sm text-neutral-500">
            Separación estricta entre caja operativa de Tienda y cuentas corporativas de Administración General.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {permisos.esAdmin && (
            <div className="inline-flex items-center gap-1 bg-[#F6F6F6] p-1 rounded-xl border border-neutral-200 mr-1">
              <button
                type="button"
                onClick={() => setVistaAmbito("TIENDA")}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer ${
                  vistaAmbito === "TIENDA"
                    ? "bg-[#E85A28] text-white shadow-xs"
                    : "text-neutral-600 hover:text-[#191818]"
                }`}
              >
                <Building2 className="w-3.5 h-3.5" />
                Cierre Tienda
              </button>
              <button
                type="button"
                onClick={() => setVistaAmbito("ADMIN_GENERAL")}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer ${
                  vistaAmbito === "ADMIN_GENERAL"
                    ? "bg-[#E85A28] text-white shadow-xs"
                    : "text-neutral-600 hover:text-[#191818]"
                }`}
              >
                <Landmark className="w-3.5 h-3.5" />
                Administración General
              </button>
            </div>
          )}
          <input
            type="date"
            value={fecha}
            onChange={(e) => setFecha(e.target.value)}
            className="px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm text-[#191818]"
          />
          <select
            value={sucursalId}
            onChange={(e) => setSucursalId(e.target.value)}
            disabled={permisos.sucursalRestringidaId !== null}
            className="px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm text-[#191818] disabled:bg-neutral-100 disabled:text-neutral-500"
          >
            {permisos.sucursalRestringidaId === null && (
              <option value="">Todas las sucursales</option>
            )}
            {sucursales.map((s) => (
              <option key={s.id} value={String(s.id)}>
                {s.nombre}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2.5 p-4 rounded-2xl bg-red-50/90 border border-red-200 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Tablero Visual de Saldos: Administración General vs Tienda */}
      {vistaAmbito === "ADMIN_GENERAL" &&
        permisos.esAdmin &&
        tableroSaldos?.administracion_general && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-4">
                <p className="text-[11px] font-bold uppercase text-neutral-500">
                  Saldos Locales (Tiendas)
                </p>
                <p className="text-2xl font-black text-[#191818] tabular-nums mt-1">
                  {formatearUsd(tableroSaldos.tienda.total_saldos_locales_usd)}
                </p>
              </div>
              <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-4">
                <p className="text-[11px] font-bold uppercase text-neutral-500">
                  Cuentas Corporativas (Admin)
                </p>
                <p className="text-2xl font-black text-[#E85A28] tabular-nums mt-1">
                  {formatearUsd(
                    tableroSaldos.administracion_general.total_liquidez_corporativa_usd
                  )}
                </p>
              </div>
              <div className="bg-[#FDF0EB]/80 backdrop-blur-md border-2 border-[#E85A28]/40 rounded-2xl p-4">
                <p className="text-[11px] font-bold uppercase text-[#E85A28]">
                  Liquidez Total Consolidada
                </p>
                <p className="text-2xl font-black text-[#191818] tabular-nums mt-1">
                  {formatearUsd(
                    tableroSaldos.administracion_general.total_liquidez_consolidada_usd
                  )}
                </p>
              </div>
              <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-4 text-xs space-y-1 tabular-nums">
                <p className="text-[11px] font-bold uppercase text-neutral-500">
                  Posición CxC / CxP
                </p>
                <p className="text-neutral-700">
                  Cashea por cobrar:{" "}
                  <strong className="text-[#191818]">
                    {formatearUsd(
                      tableroSaldos.administracion_general.cashea_por_cobrar_usd
                    )}
                  </strong>
                </p>
                <p className="text-neutral-700">
                  CxC Clientes:{" "}
                  <strong className="text-[#191818]">
                    {formatearUsd(
                      tableroSaldos.administracion_general.cxc_clientes_usd
                    )}
                  </strong>
                </p>
                <p className="text-red-700">
                  CxP Proveedores:{" "}
                  <strong>
                    {formatearUsd(
                      tableroSaldos.administracion_general.cxp_proveedores_usd
                    )}
                  </strong>
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 space-y-3">
                <h3 className="text-sm font-black text-[#191818] flex items-center gap-2">
                  <Building2 className="w-4 h-4 text-[#E85A28]" />
                  Canales Operativos de Tienda
                </h3>
                <div className="divide-y divide-neutral-100 text-xs">
                  {tableroSaldos.tienda.canales_locales.map((item) => (
                    <div key={item.id} className="py-2 flex items-center justify-between gap-2">
                      <span className="font-semibold text-[#191818]">
                        {item.nombre}{" "}
                        <span className="text-[10px] text-neutral-400">({item.moneda})</span>
                      </span>
                      <span className="font-black text-[#191818] tabular-nums">
                        {item.moneda === "BS"
                          ? `${formatearBs(item.saldo_moneda_origen)} · ${formatearUsd(item.saldo_usd)}`
                          : formatearUsd(item.saldo_usd)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 space-y-3">
                <h3 className="text-sm font-black text-[#191818] flex items-center gap-2">
                  <Landmark className="w-4 h-4 text-[#E85A28]" />
                  Cuentas Corporativas — Administración General
                </h3>
                <div className="divide-y divide-neutral-100 text-xs">
                  {tableroSaldos.administracion_general.cuentas_corporativas.map((item) => (
                    <div key={item.id} className="py-2 flex items-center justify-between gap-2">
                      <span className="font-semibold text-[#191818]">
                        {item.nombre}{" "}
                        <span className="text-[10px] text-neutral-400">({item.moneda})</span>
                      </span>
                      <span className="font-black text-[#E85A28] tabular-nums">
                        {item.moneda === "BS"
                          ? `${formatearBs(item.saldo_moneda_origen)} · ${formatearUsd(item.saldo_usd)}`
                          : formatearUsd(item.saldo_usd)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

      {cierreReciente && (
        <div className="bg-white/85 backdrop-blur-md border-2 border-[#E85A28]/40 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
            <div className="text-sm">
              <p className="font-black text-[#191818]">
                Cierre #{cierreReciente.id} guardado ({cierreReciente.fecha} ·{" "}
                {cierreReciente.sucursal})
              </p>
              <p className="text-xs text-neutral-600">
                Efectivo declarado:{" "}
                <strong className="tabular-nums">
                  {formatearUsd(cierreReciente.efectivo_declarado_usd)}
                </strong>{" "}
                · Diferencia:{" "}
                <strong className="tabular-nums">
                  {formatearUsd(cierreReciente.diferencia_usd)}
                </strong>
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() =>
                void descargarPdfApi(
                  `/api/finanzas/cierre-caja/${cierreReciente.id}/pdf`,
                  `Cierre_Caja_${cierreReciente.fecha}.pdf`
                )
              }
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] text-white text-xs font-bold cursor-pointer"
            >
              <FileDown className="w-3.5 h-3.5" />
              Descargar PDF
            </button>
            <button
              type="button"
              onClick={() => void copiarWa(cierreReciente)}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold cursor-pointer"
            >
              {copiadoId === cierreReciente.id ? (
                <Check className="w-3.5 h-3.5" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
              {copiadoId === cierreReciente.id
                ? "¡Copiado!"
                : "Copiar Cierre para WhatsApp"}
            </button>
          </div>
        </div>
      )}

      {/* Encabezado Operativo + Inventario + Taller */}
      {preview && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="bg-white/80 backdrop-blur-md p-4 rounded-2xl border border-white/70 shadow-[0_8px_30px_rgb(0,0,0,0.04)] space-y-1.5">
            <p className="text-[11px] font-bold uppercase tracking-wide text-[#E85A28]">
              Encabezado Operativo y Tasas
            </p>
            <p className="text-sm font-black text-[#191818]">
              Líder / Encargado: {preview.lider_encargado || "Sin asignar"}
            </p>
            {preview.tasas_dia && (
              <div className="flex flex-wrap gap-2 pt-1 text-xs tabular-nums">
                <span className="px-2 py-0.5 rounded-lg bg-neutral-100 font-bold text-[#191818]">
                  BCV: {formatearBs(preview.tasas_dia.tasa_bcv)}
                </span>
                <span className="px-2 py-0.5 rounded-lg bg-neutral-100 font-bold text-[#191818]">
                  USDT: {formatearBs(preview.tasas_dia.tasa_usdt)}
                </span>
                <span className="px-2 py-0.5 rounded-lg bg-[#FDF0EB] font-bold text-[#E85A28]">
                  Recargo: {preview.tasas_dia.recargo_porcentaje.toFixed(2)}%
                </span>
              </div>
            )}
          </div>

          {preview.inventario && (
            <div className="bg-white/80 backdrop-blur-md p-4 rounded-2xl border border-white/70 shadow-[0_8px_30px_rgb(0,0,0,0.04)] space-y-1.5">
              <p className="text-[11px] font-bold uppercase tracking-wide text-blue-700">
                Inventario y Almacén (Día)
              </p>
              <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs tabular-nums">
                <p className="text-neutral-600">
                  Recepciones:{" "}
                  <strong className="text-[#191818]">
                    {preview.inventario.recepciones_dia}
                  </strong>
                </p>
                <p className="text-neutral-600">
                  Traslados rec.:{" "}
                  <strong className="text-[#191818]">
                    {preview.inventario.traslados_recibidos_dia}
                  </strong>
                </p>
                <p className="text-neutral-600">
                  Salientes:{" "}
                  <strong className="text-[#191818]">
                    {preview.inventario.unidades_salientes_dia}
                  </strong>{" "}
                  <span className="text-[10px] text-neutral-400">
                    ({preview.inventario.unidades_vendidas_dia} vta /{" "}
                    {preview.inventario.traslados_despachados_dia} trs)
                  </span>
                </p>
                <p className="text-neutral-600">
                  Stock LISTO:{" "}
                  <strong className="text-emerald-700">
                    {preview.inventario.stock_disponible_listo}
                  </strong>
                </p>
              </div>
            </div>
          )}

          {preview.taller && (
            <div className="bg-white/80 backdrop-blur-md p-4 rounded-2xl border border-white/70 shadow-[0_8px_30px_rgb(0,0,0,0.04)] space-y-1.5">
              <p className="text-[11px] font-bold uppercase tracking-wide text-amber-700">
                Taller y Garantías (GT / ST)
              </p>
              <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs tabular-nums">
                <p className="text-neutral-600">
                  Recibidos hoy:{" "}
                  <strong className="text-[#191818]">
                    {preview.taller.recibidos_dia}
                  </strong>
                </p>
                <p className="text-neutral-600">
                  Resueltos hoy:{" "}
                  <strong className="text-emerald-700">
                    {preview.taller.resueltos_dia}
                  </strong>
                </p>
                <p className="text-neutral-600 col-span-2">
                  Pendientes activos:{" "}
                  <strong className="text-amber-700">
                    {preview.taller.pendientes_total}
                  </strong>{" "}
                  <span className="text-[11px] text-neutral-500">
                    (GT: {preview.taller.gt_pendientes} · ST:{" "}
                    {preview.taller.st_pendientes})
                  </span>
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* KPIs del día */}
      {preview && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <div className="bg-white/75 backdrop-blur-md p-4 rounded-2xl border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border-t-2 border-t-[#191818]">
            <p className="text-[11px] font-bold uppercase text-neutral-500">
              Ventas del Día ({preview.cantidad_ventas})
            </p>
            <p className="text-xl font-black text-[#191818] mt-1 tabular-nums">
              {formatearUsd(preview.total_ventas_usd)}
            </p>
            <p className="text-[11px] text-neutral-400">
              Anulaciones / Dev.: {preview.cantidad_anulaciones}
            </p>
          </div>

          <div className="bg-white/75 backdrop-blur-md p-4 rounded-2xl border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border-t-2 border-t-emerald-600">
            <p className="text-[11px] font-bold uppercase text-neutral-500">
              Ingresos Cobrados
            </p>
            <p className="text-xl font-black text-emerald-700 mt-1 tabular-nums">
              {formatearUsd(preview.total_ingresos_usd)}
            </p>
            <p className="text-[11px] text-neutral-500 tabular-nums">
              {formatearBs(preview.total_ingresos_bs)}
            </p>
          </div>

          <div className="bg-white/75 backdrop-blur-md p-4 rounded-2xl border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border-t-2 border-t-purple-600">
            <p className="text-[11px] font-bold uppercase text-neutral-500">
              Cashea Financiado
            </p>
            <p className="text-xl font-black text-purple-700 mt-1 tabular-nums">
              {formatearUsd(preview.total_cashea_usd)}
            </p>
          </div>

          <div className="bg-white/75 backdrop-blur-md p-4 rounded-2xl border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border-t-2 border-t-red-500">
            <p className="text-[11px] font-bold uppercase text-neutral-500">
              Egresos del Día
            </p>
            <p className="text-xl font-black text-red-600 mt-1 tabular-nums">
              {formatearUsd(preview.total_egresos_usd)}
            </p>
            <p className="text-[11px] text-neutral-500 tabular-nums">
              {formatearBs(preview.total_egresos_bs)}
            </p>
          </div>

          <div className="bg-white/75 backdrop-blur-md p-4 rounded-2xl border border-[#E85A28]/30 bg-gradient-to-br from-[#FDF0EB]/90 to-white/80 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
            <p className="text-[11px] font-bold uppercase text-[#E85A28]">
              Efectivo Esperado USD
            </p>
            <p className="text-xl font-black text-[#191818] mt-1 tabular-nums">
              {formatearUsd(preview.efectivo_esperado_usd)}
            </p>
            <p className="text-[11px] text-neutral-500 tabular-nums">
              Saldo neto: {formatearUsd(preview.saldo_neto_esperado_usd)}
            </p>
          </div>
        </div>
      )}

      {/* Desglose por instrumento + Formulario de conteo físico */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        <div className="lg:col-span-7 bg-white/75 backdrop-blur-md border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl overflow-hidden">
          <div className="px-5 py-3.5 border-b border-neutral-200/80 font-bold text-sm text-[#191818]">
            Desglose por Instrumento / Banco ({fecha})
          </div>
          {cargando ? (
            <div className="p-8 text-center text-sm text-neutral-500">
              Calculando movimientos del día...
            </div>
          ) : !preview || preview.desglose_instrumentos.length === 0 ? (
            <div className="p-8 text-center text-sm text-neutral-500">
              No hay movimientos registrados para esta fecha y sucursal.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="bg-neutral-50/90 border-b border-neutral-200 text-xs uppercase text-neutral-500">
                  <tr>
                    <th className="px-4 py-2.5">Instrumento</th>
                    <th className="px-4 py-2.5 text-center">Mon.</th>
                    <th className="px-4 py-2.5 text-right">Ingresos</th>
                    <th className="px-4 py-2.5 text-right">Egresos</th>
                    <th className="px-4 py-2.5 text-right">Neto USD</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-100">
                  {preview.desglose_instrumentos.map((d) => (
                    <tr key={d.instrumento_id} className="hover:bg-white/60">
                      <td className="px-4 py-2.5 font-semibold text-[#191818]">
                        {d.instrumento}
                        <span className="block text-[11px] font-normal text-neutral-400">
                          {d.cantidad_movimientos} mov.
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-center text-xs font-bold text-neutral-600">
                        {d.moneda}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-emerald-700 font-semibold">
                        {d.moneda === "BS"
                          ? formatearBs(d.ingresos_origen)
                          : formatearUsd(d.ingresos_origen)}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-red-600 font-semibold">
                        {d.moneda === "BS"
                          ? formatearBs(d.egresos_origen)
                          : formatearUsd(d.egresos_origen)}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums font-black text-[#191818]">
                        {formatearUsd(d.neto_usd)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Formulario de conteo físico */}
        <form
          onSubmit={guardarCierre}
          className="lg:col-span-5 bg-white/75 backdrop-blur-md border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl p-5 space-y-4"
        >
          <h3 className="text-base font-black text-[#191818]">
            Arqueo de Efectivo Físico
          </h3>

          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Efectivo físico contado / declarado (USD) *
            </label>
            <input
              type="number"
              step="0.01"
              min={0}
              required
              value={efectivoDeclarado}
              onChange={(e) => setEfectivoDeclarado(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl border border-neutral-300 bg-white text-base font-black text-[#191818] tabular-nums"
            />
          </div>

          <div
            className={`rounded-xl p-3 border text-xs font-bold flex items-center justify-between ${
              Math.abs(diferenciaEnVivo) < 0.01
                ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                : diferenciaEnVivo > 0
                ? "bg-blue-50 border-blue-200 text-blue-800"
                : "bg-red-50 border-red-200 text-red-700"
            }`}
          >
            <span>
              {Math.abs(diferenciaEnVivo) < 0.01
                ? "✅ Caja cuadrada"
                : diferenciaEnVivo > 0
                ? "Sobrante detectado"
                : "Faltante detectado"}
            </span>
            <span className="tabular-nums text-sm">
              {diferenciaEnVivo >= 0 ? "+" : ""}
              {formatearUsd(diferenciaEnVivo)}
            </span>
          </div>

          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Observaciones del cierre
            </label>
            <textarea
              rows={3}
              value={observaciones}
              onChange={(e) => setObservaciones(e.target.value)}
              placeholder="Ej. Todo cuadrado, billetes en sobre sellado..."
              className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
            />
          </div>

          <button
            type="submit"
            disabled={guardando}
            className="w-full inline-flex items-center justify-center gap-2 py-3 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] disabled:opacity-60 text-white text-sm font-black cursor-pointer transition-colors"
          >
            {guardando ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {guardando ? "Guardando cierre..." : "Guardar Cierre de Caja"}
          </button>
        </form>
      </div>

      {/* Tabla de Ventas por Asesor */}
      {preview && preview.desglose_asesores && preview.desglose_asesores.length > 0 && (
        <div className="bg-white/75 backdrop-blur-md border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl overflow-hidden">
          <div className="px-5 py-3.5 border-b border-neutral-200/80 font-bold text-sm text-[#191818]">
            Ventas por Asesor ({fecha})
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-neutral-50/90 border-b border-neutral-200 text-xs uppercase text-neutral-500">
                <tr>
                  <th className="px-4 py-2.5">Asesor</th>
                  <th className="px-4 py-2.5 text-center">Cant. Ventas</th>
                  <th className="px-4 py-2.5 text-right">Total Promo USD</th>
                  <th className="px-4 py-2.5 text-right">Total Regular USD</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {preview.desglose_asesores.map((a, idx) => (
                  <tr
                    key={`${a.asesor_id ?? "tienda"}-${idx}`}
                    className="hover:bg-white/60"
                  >
                    <td className="px-4 py-2.5 font-semibold text-[#191818]">
                      {a.asesor}
                    </td>
                    <td className="px-4 py-2.5 text-center tabular-nums font-bold">
                      {a.cantidad_ventas}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums font-black text-emerald-700">
                      {formatearUsd(a.total_promo_usd)}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-neutral-600">
                      {formatearUsd(a.total_regular_usd)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Historial de cierres */}
      <div className="bg-white/75 backdrop-blur-md border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-base font-bold text-[#191818]">
            Historial de Cierres de Caja ({cierresFiltrados.length})
          </h3>
          <div className="w-full sm:w-80">
            <BuscadorTabla
              valor={busqueda}
              alCambiar={setBusqueda}
              placeholder="Buscar por fecha, sucursal o responsable..."
            />
          </div>
        </div>

        {cierresFiltrados.length === 0 ? (
          <p className="text-sm text-neutral-500 text-center py-6">
            Aún no hay cierres de caja guardados.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-neutral-50/90 border-b border-neutral-200 text-xs uppercase text-neutral-500">
                <tr>
                  <th className="px-4 py-2.5">Fecha / Sede</th>
                  <th className="px-4 py-2.5">Responsable</th>
                  <th className="px-4 py-2.5 text-right">Ingresos USD</th>
                  <th className="px-4 py-2.5 text-right">Egresos USD</th>
                  <th className="px-4 py-2.5 text-right">Efectivo Decl.</th>
                  <th className="px-4 py-2.5 text-right">Diferencia</th>
                  <th className="px-4 py-2.5 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {cierresFiltrados.map((c) => (
                  <tr key={c.id} className="hover:bg-white/60">
                    <td className="px-4 py-3">
                      <p className="font-bold text-[#191818]">{c.fecha}</p>
                      <p className="text-xs text-neutral-500">{c.sucursal}</p>
                    </td>
                    <td className="px-4 py-3 text-xs font-semibold text-[#191818]">
                      {c.usuario}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums font-semibold text-emerald-700">
                      {formatearUsd(c.total_ingresos_usd)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums font-semibold text-red-600">
                      {formatearUsd(c.total_egresos_usd)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums font-bold">
                      {formatearUsd(c.efectivo_declarado_usd)}
                    </td>
                    <td
                      className={`px-4 py-3 text-right tabular-nums font-black ${
                        c.diferencia_usd === 0
                          ? "text-emerald-700"
                          : c.diferencia_usd > 0
                          ? "text-blue-700"
                          : "text-red-600"
                      }`}
                    >
                      {c.diferencia_usd >= 0 ? "+" : ""}
                      {formatearUsd(c.diferencia_usd)}
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap space-x-1.5">
                      <button
                        type="button"
                        onClick={() =>
                          void descargarPdfApi(
                            `/api/finanzas/cierre-caja/${c.id}/pdf`,
                            `Cierre_Caja_${c.fecha}.pdf`
                          )
                        }
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-neutral-200 bg-white hover:bg-neutral-50 text-xs font-bold text-[#191818] cursor-pointer"
                      >
                        <FileDown className="w-3.5 h-3.5 text-[#E85A28]" />
                        PDF
                      </button>
                      <button
                        type="button"
                        onClick={() => void copiarWa(c)}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 text-xs font-bold cursor-pointer"
                      >
                        {copiadoId === c.id ? (
                          <Check className="w-3.5 h-3.5" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                        WA
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
