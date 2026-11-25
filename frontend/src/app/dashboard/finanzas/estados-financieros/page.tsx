"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Scale,
  TrendingUp,
} from "lucide-react";
import {
  descargarPdfApi,
  extraerMensajeError,
  fechaHoyCaracas,
  formatearPorcentaje,
  formatearUsd,
  solicitarApi,
} from "@/servicios/api";
import type { Sucursal } from "@/tipos/dominio";

interface PlEscalonado {
  fecha_inicio: string;
  fecha_fin: string;
  sucursal: string;
  cantidad_ventas: number;
  ingresos_equipos_componentes_usd: number;
  ingresos_servicios_usd: number;
  ingresos_netos_usd: number;
  costo_ventas_usd: number;
  utilidad_bruta_usd: number;
  margen_bruto_pct: number;
  comisiones_venta_usd: number;
  gastos_operativos_usd: number;
  gastos_nomina_usd: number;
  utilidad_operativa_ebit_usd: number;
  margen_operativo_pct: number;
  diferencial_cambiario_usd: number;
  intereses_prestamos_usd: number;
  comisiones_cashea_usd?: number;
  utilidad_neta_usd: number;
  margen_neto_pct: number;
}

interface BalanceGeneral {
  fecha_corte: string;
  activos: {
    cajas_bancos_usd: number;
    cxc_clientes_usd: number;
    cashea_por_cobrar_usd: number;
    inventario_equipos_usd: number;
    inventario_componentes_usd: number;
    total_activos_usd: number;
  };
  pasivos: {
    cxp_proveedores_usd: number;
    prestamos_por_pagar_usd: number;
    obligaciones_fiscales_usd: number;
    total_pasivos_usd: number;
  };
  patrimonio: {
    capital_social_y_reservas_usd: number;
    resultado_ejercicio_usd: number;
    total_patrimonio_usd: number;
  };
  total_pasivo_mas_patrimonio_usd: number;
  diferencia_cuadre_usd: number;
  cuadrado: boolean;
}

interface AsientoContable {
  id: number;
  fecha: string;
  referencia: string;
  modulo_origen: string;
  descripcion: string;
  creado_por: string;
  total_debe_usd: number;
  total_haber_usd: number;
  cuadrado: boolean;
  lineas: Array<{
    id: number;
    cuenta_codigo: string;
    cuenta_nombre: string;
    debe_usd: number;
    haber_usd: number;
    descripcion: string;
  }>;
}

interface PlanCuentaItem {
  id: number;
  codigo: string;
  nombre: string;
  tipo: string;
  activa: boolean;
}

export default function PaginaEstadosFinancieros() {
  const hoy = fechaHoyCaracas();
  const inicioMes = `${hoy.slice(0, 8)}01`;

  const [pestana, setPestana] = useState<"pl" | "balance" | "diario">("pl");
  const [fechaInicio, setFechaInicio] = useState(inicioMes);
  const [fechaFin, setFechaFin] = useState(hoy);
  const [fechaCorte, setFechaCorte] = useState(hoy);
  const [sucursalId, setSucursalId] = useState("");
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);

  const [pl, setPl] = useState<PlEscalonado | null>(null);
  const [balance, setBalance] = useState<BalanceGeneral | null>(null);
  const [asientos, setAsientos] = useState<AsientoContable[]>([]);
  const [cuentas, setCuentas] = useState<PlanCuentaItem[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const cargarTodo = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const qsPl = new URLSearchParams({
        fecha_inicio: fechaInicio,
        fecha_fin: fechaFin,
      });
      if (sucursalId) qsPl.set("sucursal_id", sucursalId);

      const [rPl, rBal, rAs, rCtas, rSuc] = await Promise.all([
        solicitarApi<PlEscalonado>(
          `/api/finanzas/estados/pl-escalonado?${qsPl.toString()}`
        ),
        solicitarApi<BalanceGeneral>(
          `/api/finanzas/estados/balance-general?fecha_corte=${fechaCorte}`
        ),
        solicitarApi<AsientoContable[]>(
          `/api/finanzas/contabilidad/asientos?fecha_inicio=${fechaInicio}&fecha_fin=${fechaFin}`
        ),
        solicitarApi<PlanCuentaItem[]>("/api/finanzas/contabilidad/plan-cuentas"),
        solicitarApi<Sucursal[]>("/api/sucursales"),
      ]);
      setPl(rPl);
      setBalance(rBal);
      setAsientos(rAs);
      setCuentas(rCtas);
      setSucursales(rSuc);
    } catch (err) {
      setError(
        extraerMensajeError(err, "No se pudieron cargar los estados financieros.")
      );
    } finally {
      setCargando(false);
    }
  }, [fechaInicio, fechaFin, fechaCorte, sucursalId]);

  useEffect(() => {
    void cargarTodo();
  }, [cargarTodo]);

  const exportarPl = async (formato: "pdf" | "xlsx") => {
    try {
      const qs = new URLSearchParams({
        formato,
        fecha_inicio: fechaInicio,
        fecha_fin: fechaFin,
      });
      if (sucursalId) qs.set("sucursal_id", sucursalId);
      await descargarPdfApi(
        `/api/finanzas/estados/pl-escalonado/export?${qs.toString()}`,
        `tekio_pl_escalonado_${fechaInicio}_${fechaFin}.${formato}`
      );
    } catch (err) {
      setError(extraerMensajeError(err, "No se pudo exportar el P&L."));
    }
  };

  const exportarBalance = async (formato: "pdf" | "xlsx") => {
    try {
      await descargarPdfApi(
        `/api/finanzas/estados/balance-general/export?formato=${formato}&fecha_corte=${fechaCorte}`,
        `tekio_balance_general_${fechaCorte}.${formato}`
      );
    } catch (err) {
      setError(extraerMensajeError(err, "No se pudo exportar el Balance General."));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-[#191818]">
            Estados Financieros y Motor Contable
          </h2>
          <p className="text-sm text-neutral-500">
            Estado de Resultados (P&L) escalonado, Balance General cuadrado y Libro Diario por partida doble.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {[
            { id: "pl", label: "P&L Escalonado", icon: TrendingUp },
            { id: "balance", label: "Balance General", icon: Scale },
            { id: "diario", label: `Libro Diario (${asientos.length})`, icon: BookOpen },
          ].map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setPestana(t.id as "pl" | "balance" | "diario")}
                className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold cursor-pointer ${
                  pestana === t.id
                    ? "bg-[#E85A28] text-white"
                    : "bg-white/80 border border-neutral-200 text-neutral-700"
                }`}
              >
                <Icon className="w-4 h-4" />
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2.5 p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* PESTAÑA 1: P&L ESCALONADO */}
      {pestana === "pl" && (
        <div className="space-y-4">
          <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-4 flex flex-wrap items-end justify-between gap-3">
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
                  Desde
                </label>
                <input
                  type="date"
                  value={fechaInicio}
                  onChange={(e) => setFechaInicio(e.target.value)}
                  className="px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
                />
              </div>
              <div>
                <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
                  Hasta
                </label>
                <input
                  type="date"
                  value={fechaFin}
                  onChange={(e) => setFechaFin(e.target.value)}
                  className="px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
                />
              </div>
              <div>
                <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
                  Sucursal
                </label>
                <select
                  value={sucursalId}
                  onChange={(e) => setSucursalId(e.target.value)}
                  className="px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
                >
                  <option value="">Todas (Consolidado)</option>
                  {sucursales.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.nombre}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void exportarPl("pdf")}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#191818] text-white text-xs font-bold cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                PDF Marca de Agua
              </button>
              <button
                type="button"
                onClick={() => void exportarPl("xlsx")}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-600 text-white text-xs font-bold cursor-pointer"
              >
                <FileSpreadsheet className="w-3.5 h-3.5" />
                Excel .xlsx
              </button>
            </div>
          </div>

          {cargando || !pl ? (
            <div className="bg-white/80 rounded-2xl border border-neutral-200 p-8 animate-pulse h-64" />
          ) : (
            <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-[#191818] text-white text-xs uppercase">
                  <tr>
                    <th className="px-5 py-3 text-left">Rubro Contable</th>
                    <th className="px-5 py-3 text-right">Monto (USD)</th>
                    <th className="px-5 py-3 text-right">% / Ingresos</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-100 tabular-nums">
                  <tr>
                    <td className="px-5 py-3">Ingresos por Ventas de Equipos y Componentes</td>
                    <td className="px-5 py-3 text-right">{formatearUsd(pl.ingresos_equipos_componentes_usd)}</td>
                    <td className="px-5 py-3 text-right text-neutral-400">—</td>
                  </tr>
                  <tr>
                    <td className="px-5 py-3">Ingresos por Servicios Técnicos y Taller</td>
                    <td className="px-5 py-3 text-right">{formatearUsd(pl.ingresos_servicios_usd)}</td>
                    <td className="px-5 py-3 text-right text-neutral-400">—</td>
                  </tr>
                  <tr className="bg-neutral-50 font-bold">
                    <td className="px-5 py-3">INGRESOS NETOS TOTALES</td>
                    <td className="px-5 py-3 text-right">{formatearUsd(pl.ingresos_netos_usd)}</td>
                    <td className="px-5 py-3 text-right">100,00%</td>
                  </tr>
                  <tr>
                    <td className="px-5 py-3 text-red-700">(-) Costo de Ventas (incl. flete y componentes de preparación)</td>
                    <td className="px-5 py-3 text-right text-red-700">-{formatearUsd(pl.costo_ventas_usd)}</td>
                    <td className="px-5 py-3 text-right text-neutral-400">—</td>
                  </tr>
                  <tr className="bg-[#FDF0EB] font-black text-[#191818]">
                    <td className="px-5 py-3.5">(=) UTILIDAD BRUTA</td>
                    <td className="px-5 py-3.5 text-right">{formatearUsd(pl.utilidad_bruta_usd)}</td>
                    <td className="px-5 py-3.5 text-right">{formatearPorcentaje(pl.margen_bruto_pct)}</td>
                  </tr>
                  <tr>
                    <td className="px-5 py-3 text-red-700">(-) Comisiones y Gastos de Venta</td>
                    <td className="px-5 py-3 text-right text-red-700">-{formatearUsd(pl.comisiones_venta_usd)}</td>
                    <td className="px-5 py-3 text-right text-neutral-400">—</td>
                  </tr>
                  <tr>
                    <td className="px-5 py-3 text-red-700">(-) Gastos Operativos Administrativos</td>
                    <td className="px-5 py-3 text-right text-red-700">-{formatearUsd(pl.gastos_operativos_usd)}</td>
                    <td className="px-5 py-3 text-right text-neutral-400">—</td>
                  </tr>
                  <tr>
                    <td className="px-5 py-3 text-red-700">(-) Gastos de Nómina</td>
                    <td className="px-5 py-3 text-right text-red-700">-{formatearUsd(pl.gastos_nomina_usd)}</td>
                    <td className="px-5 py-3 text-right text-neutral-400">—</td>
                  </tr>
                  <tr className="bg-neutral-50 font-black text-[#191818]">
                    <td className="px-5 py-3.5">(=) UTILIDAD OPERATIVA (EBIT)</td>
                    <td className="px-5 py-3.5 text-right">{formatearUsd(pl.utilidad_operativa_ebit_usd)}</td>
                    <td className="px-5 py-3.5 text-right">{formatearPorcentaje(pl.margen_operativo_pct)}</td>
                  </tr>
                  <tr>
                    <td className="px-5 py-3">(+/-) Diferencial Cambiario (Tesorería)</td>
                    <td className="px-5 py-3 text-right">{formatearUsd(pl.diferencial_cambiario_usd)}</td>
                    <td className="px-5 py-3 text-right text-neutral-400">—</td>
                  </tr>
                  <tr>
                    <td className="px-5 py-3 text-red-700">(-) Intereses Financieros de Préstamos</td>
                    <td className="px-5 py-3 text-right text-red-700">-{formatearUsd(pl.intereses_prestamos_usd)}</td>
                    <td className="px-5 py-3 text-right text-neutral-400">—</td>
                  </tr>
                  <tr>
                    <td className="px-5 py-3 text-red-700">(-) Comisiones e Impuestos Financieros Cashea</td>
                    <td className="px-5 py-3 text-right text-red-700">-{formatearUsd(pl.comisiones_cashea_usd ?? 0)}</td>
                    <td className="px-5 py-3 text-right text-neutral-400">—</td>
                  </tr>
                  <tr className="bg-[#E85A28] text-white font-black text-base">
                    <td className="px-5 py-4">(=) UTILIDAD NETA DEL PERÍODO</td>
                    <td className="px-5 py-4 text-right">{formatearUsd(pl.utilidad_neta_usd)}</td>
                    <td className="px-5 py-4 text-right">{formatearPorcentaje(pl.margen_neto_pct)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* PESTAÑA 2: BALANCE GENERAL */}
      {pestana === "balance" && (
        <div className="space-y-4">
          <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-4 flex flex-wrap items-end justify-between gap-3">
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
                  Fecha de corte
                </label>
                <input
                  type="date"
                  value={fechaCorte}
                  onChange={(e) => setFechaCorte(e.target.value)}
                  className="px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
                />
              </div>
              {balance && (
                <div
                  className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-black ${
                    balance.cuadrado
                      ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                      : "bg-red-100 text-red-800 border border-red-200"
                  }`}
                >
                  <CheckCircle2 className="w-4 h-4" />
                  {balance.cuadrado
                    ? "CUADRADO EXACTO (Activos = Pasivos + Patrimonio)"
                    : `DESCUADRE: ${formatearUsd(balance.diferencia_cuadre_usd)}`}
                </div>
              )}
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void exportarBalance("pdf")}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#191818] text-white text-xs font-bold cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                PDF Marca de Agua
              </button>
              <button
                type="button"
                onClick={() => void exportarBalance("xlsx")}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-600 text-white text-xs font-bold cursor-pointer"
              >
                <FileSpreadsheet className="w-3.5 h-3.5" />
                Excel .xlsx
              </button>
            </div>
          </div>

          {cargando || !balance ? (
            <div className="bg-white/80 rounded-2xl border border-neutral-200 p-8 animate-pulse h-64" />
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 tabular-nums">
              {/* ACTIVOS */}
              <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl overflow-hidden">
                <div className="bg-[#191818] text-white px-5 py-3 text-xs font-black uppercase">
                  Activos
                </div>
                <div className="divide-y divide-neutral-100 text-sm">
                  <div className="px-5 py-3 flex justify-between">
                    <span>Caja y Bancos (Equivalente USD)</span>
                    <span className="font-semibold">{formatearUsd(balance.activos.cajas_bancos_usd)}</span>
                  </div>
                  <div className="px-5 py-3 flex justify-between">
                    <span>Cuentas por Cobrar Clientes</span>
                    <span className="font-semibold">{formatearUsd(balance.activos.cxc_clientes_usd)}</span>
                  </div>
                  <div className="px-5 py-3 flex justify-between">
                    <span>Cashea por Cobrar</span>
                    <span className="font-semibold">{formatearUsd(balance.activos.cashea_por_cobrar_usd)}</span>
                  </div>
                  <div className="px-5 py-3 flex justify-between">
                    <span>Inventario de Equipos (Costo Total)</span>
                    <span className="font-semibold">{formatearUsd(balance.activos.inventario_equipos_usd)}</span>
                  </div>
                  <div className="px-5 py-3 flex justify-between">
                    <span>Inventario de Componentes</span>
                    <span className="font-semibold">{formatearUsd(balance.activos.inventario_componentes_usd)}</span>
                  </div>
                  <div className="px-5 py-4 bg-[#FDF0EB] flex justify-between font-black text-base text-[#191818]">
                    <span>TOTAL ACTIVOS</span>
                    <span>{formatearUsd(balance.activos.total_activos_usd)}</span>
                  </div>
                </div>
              </div>

              {/* PASIVOS + PATRIMONIO */}
              <div className="space-y-4">
                <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl overflow-hidden">
                  <div className="bg-[#191818] text-white px-5 py-3 text-xs font-black uppercase">
                    Pasivos
                  </div>
                  <div className="divide-y divide-neutral-100 text-sm">
                    <div className="px-5 py-3 flex justify-between">
                      <span>Cuentas por Pagar Proveedores</span>
                      <span className="font-semibold">{formatearUsd(balance.pasivos.cxp_proveedores_usd)}</span>
                    </div>
                    <div className="px-5 py-3 flex justify-between">
                      <span>Préstamos por Pagar (Capital Pendiente)</span>
                      <span className="font-semibold">{formatearUsd(balance.pasivos.prestamos_por_pagar_usd)}</span>
                    </div>
                    <div className="px-5 py-3 flex justify-between">
                      <span>Obligaciones Fiscales por Pagar</span>
                      <span className="font-semibold">{formatearUsd(balance.pasivos.obligaciones_fiscales_usd)}</span>
                    </div>
                    <div className="px-5 py-3 bg-neutral-50 flex justify-between font-bold">
                      <span>TOTAL PASIVOS</span>
                      <span>{formatearUsd(balance.pasivos.total_pasivos_usd)}</span>
                    </div>
                  </div>
                </div>

                <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl overflow-hidden">
                  <div className="bg-[#191818] text-white px-5 py-3 text-xs font-black uppercase">
                    Patrimonio
                  </div>
                  <div className="divide-y divide-neutral-100 text-sm">
                    <div className="px-5 py-3 flex justify-between">
                      <span>Capital Social y Resultados Acumulados</span>
                      <span className="font-semibold">{formatearUsd(balance.patrimonio.capital_social_y_reservas_usd)}</span>
                    </div>
                    <div className="px-5 py-3 flex justify-between">
                      <span>Resultado del Ejercicio (YTD)</span>
                      <span className="font-semibold">{formatearUsd(balance.patrimonio.resultado_ejercicio_usd)}</span>
                    </div>
                    <div className="px-5 py-3 bg-neutral-50 flex justify-between font-bold">
                      <span>TOTAL PATRIMONIO</span>
                      <span>{formatearUsd(balance.patrimonio.total_patrimonio_usd)}</span>
                    </div>
                    <div className="px-5 py-4 bg-[#E85A28] text-white flex justify-between font-black text-base">
                      <span>TOTAL PASIVOS + PATRIMONIO</span>
                      <span>{formatearUsd(balance.total_pasivo_mas_patrimonio_usd)}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* PESTAÑA 3: LIBRO DIARIO Y PLAN DE CUENTAS */}
      {pestana === "diario" && (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          <div className="xl:col-span-2 space-y-3">
            {asientos.length === 0 ? (
              <div className="bg-white/80 border border-neutral-200 rounded-2xl p-8 text-center text-sm text-neutral-500">
                No hay asientos contables registrados en el rango seleccionado.
              </div>
            ) : (
              asientos.map((a) => (
                <div
                  key={a.id}
                  className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl overflow-hidden"
                >
                  <div className="px-4 py-3 bg-neutral-50 border-b border-neutral-100 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <span className="text-xs font-black text-[#E85A28] mr-2">
                        #{a.id} · {a.modulo_origen}
                      </span>
                      <span className="text-xs font-bold text-[#191818]">
                        {a.descripcion}
                      </span>
                      <p className="text-[11px] text-neutral-500">
                        {a.fecha} · Ref: {a.referencia} · Por: {a.creado_por}
                      </p>
                    </div>
                    <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-black tabular-nums">
                      Debe {formatearUsd(a.total_debe_usd)} = Haber {formatearUsd(a.total_haber_usd)}
                    </span>
                  </div>
                  <table className="w-full text-xs tabular-nums">
                    <tbody className="divide-y divide-neutral-100">
                      {a.lineas.map((l) => (
                        <tr key={l.id}>
                          <td className="px-4 py-2 font-mono font-bold text-neutral-600 w-20">
                            {l.cuenta_codigo}
                          </td>
                          <td className="px-4 py-2">
                            <p className="font-semibold text-[#191818]">{l.cuenta_nombre}</p>
                            {l.descripcion && (
                              <p className="text-[11px] text-neutral-500">{l.descripcion}</p>
                            )}
                          </td>
                          <td className="px-4 py-2 text-right font-semibold text-[#191818] w-28">
                            {l.debe_usd > 0 ? formatearUsd(l.debe_usd) : ""}
                          </td>
                          <td className="px-4 py-2 text-right font-semibold text-neutral-600 w-28">
                            {l.haber_usd > 0 ? formatearUsd(l.haber_usd) : ""}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))
            )}
          </div>

          <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl overflow-hidden h-fit">
            <div className="px-4 py-3 bg-[#191818] text-white text-xs font-black uppercase">
              Plan de Cuentas Tekio ({cuentas.length})
            </div>
            <div className="divide-y divide-neutral-100 text-xs">
              {cuentas.map((c) => (
                <div key={c.id} className="px-4 py-2.5 flex items-center justify-between gap-2">
                  <div>
                    <span className="font-mono font-bold text-[#E85A28] mr-2">
                      {c.codigo}
                    </span>
                    <span className="font-semibold text-[#191818]">{c.nombre}</span>
                  </div>
                  <span className="px-2 py-0.5 rounded bg-neutral-100 text-[10px] font-bold text-neutral-600">
                    {c.tipo}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
