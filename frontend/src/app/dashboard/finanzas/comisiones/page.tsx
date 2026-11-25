"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  BarChart3,
  Calendar,
  Check,
  CheckCircle2,
  Copy,
  ExternalLink,
  Lock,
  MessageSquare,
} from "lucide-react";
import BuscadorTabla from "@/componentes/BuscadorTabla";
import { usarSesion } from "@/contexto/SesionContexto";
import {
  construirUrlWhatsApp,
  copiarTextoPortapapeles,
  formatearWhatsAppComisionesGeneral,
  formatearWhatsAppComisionIndividual,
} from "@/lib/whatsapp";
import { ErrorApi, formatearUsd, solicitarApi } from "@/servicios/api";
import type { Sucursal } from "@/tipos/dominio";
import type {
  ComisionPersona,
  ReporteComisiones,
  TableroFinanciero,
  UsuarioOperativo,
} from "@/tipos/finanzas";

function aIsoFecha(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function rangoEsteMes(): { inicio: string; fin: string } {
  const hoy = new Date();
  const inicio = new Date(hoy.getFullYear(), hoy.getMonth(), 1);
  const fin = new Date(hoy.getFullYear(), hoy.getMonth() + 1, 0);
  return { inicio: aIsoFecha(inicio), fin: aIsoFecha(fin) };
}

function rangoEstaQuincena(): { inicio: string; fin: string } {
  const hoy = new Date();
  if (hoy.getDate() <= 15) {
    return {
      inicio: aIsoFecha(new Date(hoy.getFullYear(), hoy.getMonth(), 1)),
      fin: aIsoFecha(new Date(hoy.getFullYear(), hoy.getMonth(), 15)),
    };
  }
  return {
    inicio: aIsoFecha(new Date(hoy.getFullYear(), hoy.getMonth(), 16)),
    fin: aIsoFecha(new Date(hoy.getFullYear(), hoy.getMonth() + 1, 0)),
  };
}

function rangoQuincenaAnterior(): { inicio: string; fin: string } {
  const hoy = new Date();
  if (hoy.getDate() <= 15) {
    const mesAntFin = new Date(hoy.getFullYear(), hoy.getMonth(), 0);
    return {
      inicio: aIsoFecha(
        new Date(mesAntFin.getFullYear(), mesAntFin.getMonth(), 16)
      ),
      fin: aIsoFecha(mesAntFin),
    };
  }
  return {
    inicio: aIsoFecha(new Date(hoy.getFullYear(), hoy.getMonth(), 1)),
    fin: aIsoFecha(new Date(hoy.getFullYear(), hoy.getMonth(), 15)),
  };
}

export default function PaginaComisionesYCierre() {
  const { usuario } = usarSesion();
  const esDireccion = usuario?.rol === "DIRECCION";

  const inicial = useMemo(() => rangoEstaQuincena(), []);
  const [fechaInicio, setFechaInicio] = useState(inicial.inicio);
  const [fechaFin, setFechaFin] = useState(inicial.fin);
  const [usuarioFiltroId, setUsuarioFiltroId] = useState("");
  const [sucursalFiltroId, setSucursalFiltroId] = useState("");
  const [incluirNotasWa, setIncluirNotasWa] = useState(true);
  const [busqueda, setBusqueda] = useState("");

  const [operativos, setOperativos] = useState<UsuarioOperativo[]>([]);
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [reporte, setReporte] = useState<ReporteComisiones | null>(null);
  const [tablero, setTablero] = useState<TableroFinanciero | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);
  const [modalCierre, setModalCierre] = useState(false);

  const [copiadoGeneral, setCopiadoGeneral] = useState(false);
  const [copiadoPersonaId, setCopiadoPersonaId] = useState<number | null>(null);

  useEffect(() => {
    Promise.all([
      solicitarApi<UsuarioOperativo[]>("/api/usuarios/operativos").catch(
        () => []
      ),
      solicitarApi<Sucursal[]>("/api/sucursales").catch(() => []),
    ]).then(([ops, sucs]) => {
      setOperativos(ops);
      setSucursales(sucs);
    });
  }, []);

  const cargarDatos = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const paramsCom = new URLSearchParams();
      if (fechaInicio) paramsCom.set("fecha_inicio", fechaInicio);
      if (fechaFin) paramsCom.set("fecha_fin", fechaFin);
      if (usuarioFiltroId) paramsCom.set("usuario_id", usuarioFiltroId);
      if (sucursalFiltroId) paramsCom.set("sucursal_id", sucursalFiltroId);

      const paramsTab = new URLSearchParams();
      if (fechaInicio) paramsTab.set("desde", fechaInicio);
      if (fechaFin) paramsTab.set("hasta", fechaFin);
      if (sucursalFiltroId) paramsTab.set("sucursal_id", sucursalFiltroId);

      const [respCom, respTab] = await Promise.all([
        solicitarApi<ReporteComisiones>(
          `/api/finanzas/comisiones?${paramsCom.toString()}`
        ),
        solicitarApi<TableroFinanciero>(
          `/api/finanzas/tablero?${paramsTab.toString()}`
        ),
      ]);
      setReporte(respCom);
      setTablero(respTab);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudieron cargar las comisiones y el tablero."
      );
    } finally {
      setCargando(false);
    }
  }, [fechaInicio, fechaFin, usuarioFiltroId, sucursalFiltroId]);

  useEffect(() => {
    void cargarDatos();
  }, [cargarDatos]);

  const mesCierre = reporte?.mes ?? Number(fechaInicio.slice(5, 7));
  const anioCierre = reporte?.anio ?? Number(fechaInicio.slice(0, 4));

  const confirmarCierreMes = async () => {
    setError(null);
    setExito(null);
    try {
      await solicitarApi("/api/finanzas/cierres-mensuales", {
        method: "POST",
        body: JSON.stringify({ anio: anioCierre, mes: mesCierre }),
      });
      setModalCierre(false);
      setExito(
        `Período ${String(mesCierre).padStart(2, "0")}/${anioCierre} cerrado y bloqueado correctamente.`
      );
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "No se pudo cerrar el mes."
      );
    }
  };

  const comisionesFiltradas = useMemo(() => {
    const lista = reporte?.comisiones ?? [];
    const q = busqueda.trim().toLowerCase();
    if (!q) return lista;
    return lista.filter((c) =>
      [c.nombre, c.rol, ...(c.notas ?? [])]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [reporte, busqueda]);

  const operacionesFiltradas = useMemo(() => {
    const lista = reporte?.operaciones ?? [];
    const q = busqueda.trim().toLowerCase();
    if (!q) return lista;
    return lista.filter((op) =>
      [
        op.numero_nota,
        op.cliente,
        op.usuario_nombre,
        op.rol,
        op.tipo,
        op.sucursal,
      ]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [reporte, busqueda]);

  const kpisComision = useMemo(() => {
    const totalBase = comisionesFiltradas.reduce(
      (acc, c) => acc + c.ventas_promo_usd,
      0
    );
    const totalPagar = comisionesFiltradas.reduce(
      (acc, c) => acc + c.total_comision_usd,
      0
    );
    return {
      totalBase,
      totalPagar,
      cantidadOperaciones: operacionesFiltradas.length,
    };
  }, [comisionesFiltradas, operacionesFiltradas]);

  const copiarResumenGeneral = async () => {
    const texto = formatearWhatsAppComisionesGeneral(
      comisionesFiltradas,
      reporte?.fecha_inicio || fechaInicio,
      reporte?.fecha_fin || fechaFin,
      incluirNotasWa
    );
    const ok = await copiarTextoPortapapeles(texto);
    if (ok) {
      setCopiadoGeneral(true);
      setTimeout(() => setCopiadoGeneral(false), 2400);
    }
  };

  const urlWhatsAppGeneral = useMemo(() => {
    const texto = formatearWhatsAppComisionesGeneral(
      comisionesFiltradas,
      reporte?.fecha_inicio || fechaInicio,
      reporte?.fecha_fin || fechaFin,
      incluirNotasWa
    );
    return construirUrlWhatsApp(texto);
  }, [comisionesFiltradas, reporte, fechaInicio, fechaFin, incluirNotasWa]);

  const copiarIndividual = async (persona: ComisionPersona) => {
    const texto = formatearWhatsAppComisionIndividual(
      persona,
      reporte?.fecha_inicio || fechaInicio,
      reporte?.fecha_fin || fechaFin,
      incluirNotasWa
    );
    const ok = await copiarTextoPortapapeles(texto);
    if (ok) {
      setCopiadoPersonaId(persona.usuario_id);
      setTimeout(() => setCopiadoPersonaId(null), 2400);
    }
  };

  const urlWhatsAppIndividual = (persona: ComisionPersona): string => {
    const texto = formatearWhatsAppComisionIndividual(
      persona,
      reporte?.fecha_inicio || fechaInicio,
      reporte?.fecha_fin || fechaFin,
      incluirNotasWa
    );
    return construirUrlWhatsApp(texto, persona.telefono);
  };

  return (
    <div className="space-y-6">
      {/* Encabezado */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-[#191818] flex items-center gap-2">
            <BarChart3 className="w-6 h-6 text-[#E85A28]" />
            Reporte de Comisiones y Tablero Financiero
          </h2>
          <p className="text-sm text-neutral-500">
            Cálculo exacto sobre Precio Promo USD (1% Asesores · 0,5% Líder
            multi-tienda · 50% ST Técnico), excluyendo ventas anuladas o
            devueltas.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void copiarResumenGeneral()}
            disabled={comisionesFiltradas.length === 0}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-xs font-bold cursor-pointer transition-colors"
          >
            {copiadoGeneral ? (
              <Check className="w-3.5 h-3.5" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
            {copiadoGeneral ? "¡Copiado!" : "Copiar para WhatsApp"}
          </button>
          <a
            href={urlWhatsAppGeneral}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-emerald-300 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 text-xs font-bold transition-colors"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            Enviar por WhatsApp
          </a>
          {esDireccion && !reporte?.mes_cerrado && (
            <button
              type="button"
              onClick={() => setModalCierre(true)}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#191818] hover:bg-[#2E2D2D] text-white text-xs font-bold cursor-pointer transition-colors"
            >
              <Lock className="w-3.5 h-3.5" />
              Cerrar mes
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2.5 p-4 rounded-2xl bg-red-50/90 border border-red-200 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}
      {exito && (
        <div className="flex items-center gap-2.5 p-4 rounded-2xl bg-emerald-50/90 border border-emerald-200 text-sm text-emerald-800">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{exito}</span>
        </div>
      )}

      {/* Barra de Filtros Avanzados */}
      <div className="bg-white/75 backdrop-blur-md border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-wide text-neutral-500 flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5 text-[#E85A28]" />
              Accesos rápidos:
            </span>
            <button
              type="button"
              onClick={() => {
                const r = rangoEstaQuincena();
                setFechaInicio(r.inicio);
                setFechaFin(r.fin);
              }}
              className="px-3 py-1.5 rounded-lg border border-neutral-200 bg-white hover:border-[#E85A28] hover:text-[#E85A28] text-xs font-bold text-[#191818] cursor-pointer transition-colors"
            >
              Esta quincena
            </button>
            <button
              type="button"
              onClick={() => {
                const r = rangoQuincenaAnterior();
                setFechaInicio(r.inicio);
                setFechaFin(r.fin);
              }}
              className="px-3 py-1.5 rounded-lg border border-neutral-200 bg-white hover:border-[#E85A28] hover:text-[#E85A28] text-xs font-bold text-[#191818] cursor-pointer transition-colors"
            >
              Quincena anterior
            </button>
            <button
              type="button"
              onClick={() => {
                const r = rangoEsteMes();
                setFechaInicio(r.inicio);
                setFechaFin(r.fin);
              }}
              className="px-3 py-1.5 rounded-lg border border-neutral-200 bg-white hover:border-[#E85A28] hover:text-[#E85A28] text-xs font-bold text-[#191818] cursor-pointer transition-colors"
            >
              Este mes
            </button>
          </div>

          <label className="inline-flex items-center gap-2 text-xs font-semibold text-neutral-700 cursor-pointer">
            <input
              type="checkbox"
              checked={incluirNotasWa}
              onChange={(e) => setIncluirNotasWa(e.target.checked)}
              className="rounded accent-[#E85A28]"
            />
            <MessageSquare className="w-3.5 h-3.5 text-emerald-600" />
            Incluir listado de notas en WhatsApp
          </label>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          <div>
            <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
              Desde
            </label>
            <input
              type="date"
              value={fechaInicio}
              onChange={(e) => setFechaInicio(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm text-[#191818]"
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
              className="w-full px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm text-[#191818]"
            />
          </div>
          <div>
            <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
              Asesor / Líder / Técnico
            </label>
            <select
              value={usuarioFiltroId}
              onChange={(e) => setUsuarioFiltroId(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm text-[#191818]"
            >
              <option value="">Todos los colaboradores</option>
              {operativos.map((u) => (
                <option key={u.id} value={String(u.id)}>
                  {u.nombre} ({u.rol})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
              Sucursal
            </label>
            <select
              value={sucursalFiltroId}
              onChange={(e) => setSucursalFiltroId(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm text-[#191818]"
            >
              <option value="">Todas las sucursales</option>
              {sucursales.map((s) => (
                <option key={s.id} value={String(s.id)}>
                  {s.nombre}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col justify-end">
            <BuscadorTabla
              valor={busqueda}
              alCambiar={setBusqueda}
              placeholder="Buscar nombre, rol o nota N-..."
            />
          </div>
        </div>
      </div>

      {/* KPIs dinámicos de Comisiones del filtro activo */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white/75 backdrop-blur-md p-4 rounded-2xl border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border-t-2 border-t-[#191818]">
          <p className="text-[11px] font-bold uppercase tracking-wider text-neutral-500">
            Total Base Promo USD
          </p>
          <p className="text-2xl font-black text-[#191818] mt-1 tabular-nums">
            {formatearUsd(kpisComision.totalBase)}
          </p>
          <p className="text-[11px] text-neutral-500 mt-0.5">
            Del {fechaInicio} al {fechaFin}
          </p>
        </div>

        <div className="bg-white/75 backdrop-blur-md p-4 rounded-2xl border border-[#E85A28]/30 bg-gradient-to-br from-[#FDF0EB]/90 to-white/80 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
          <p className="text-[11px] font-bold uppercase tracking-wider text-[#E85A28]">
            Total Comisiones a Pagar
          </p>
          <p className="text-2xl font-black text-[#191818] mt-1 tabular-nums">
            {formatearUsd(kpisComision.totalPagar)}
          </p>
          <p className="text-[11px] text-neutral-500 mt-0.5">
            {comisionesFiltradas.length} colaborador(es) en vista
          </p>
        </div>

        <div className="bg-white/75 backdrop-blur-md p-4 rounded-2xl border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border-t-2 border-t-emerald-600">
          <p className="text-[11px] font-bold uppercase tracking-wider text-neutral-500">
            Cantidad de Operaciones
          </p>
          <p className="text-2xl font-black text-emerald-700 mt-1 tabular-nums">
            {kpisComision.cantidadOperaciones}
          </p>
          <p className="text-[11px] text-neutral-500 mt-0.5">
            Ventas, ST, ajustes y preparaciones
          </p>
        </div>
      </div>

      {/* KPIs del Tablero Financiero */}
      {tablero && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          <div className="bg-white/75 backdrop-blur-md p-3.5 rounded-2xl border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
            <p className="text-[10px] font-bold uppercase tracking-wider text-neutral-500">
              Venta Promo Período
            </p>
            <p className="text-lg font-black text-[#191818] mt-0.5 tabular-nums">
              {formatearUsd(tablero.venta_promo_usd)}
            </p>
          </div>
          <div className="bg-white/75 backdrop-blur-md p-3.5 rounded-2xl border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
            <p className="text-[10px] font-bold uppercase tracking-wider text-neutral-500">
              USD Real
            </p>
            <p className="text-lg font-black text-emerald-700 mt-0.5 tabular-nums">
              {formatearUsd(tablero.usd_real)}
            </p>
          </div>
          <div className="bg-white/75 backdrop-blur-md p-3.5 rounded-2xl border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
            <p className="text-[10px] font-bold uppercase tracking-wider text-neutral-500">
              Diferencial
            </p>
            <p className="text-lg font-black text-[#E85A28] mt-0.5 tabular-nums">
              {formatearUsd(tablero.diferencial_cambiario_usd)}
            </p>
          </div>
          <div className="bg-white/75 backdrop-blur-md p-3.5 rounded-2xl border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
            <p className="text-[10px] font-bold uppercase tracking-wider text-neutral-500">
              Cashea x Cobrar
            </p>
            <p className="text-lg font-black text-[#191818] mt-0.5 tabular-nums">
              {formatearUsd(tablero.cashea_por_cobrar_usd)}
            </p>
          </div>
          <div className="bg-white/75 backdrop-blur-md p-3.5 rounded-2xl border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
            <p className="text-[10px] font-bold uppercase tracking-wider text-neutral-500">
              Utilidad Real Neta
            </p>
            <p className="text-lg font-black text-[#191818] mt-0.5 tabular-nums">
              {formatearUsd(tablero.utilidad_real_neta_usd)}
            </p>
          </div>
        </div>
      )}

      {/* Tabla consolidada por colaborador */}
      <div className="bg-white/75 backdrop-blur-md rounded-2xl border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] overflow-hidden">
        <div className="px-5 py-3.5 border-b border-neutral-200/80 flex flex-wrap items-center justify-between gap-3">
          <span className="font-bold text-sm text-[#191818]">
            Consolidado por Colaborador ({fechaInicio} al {fechaFin})
          </span>
          {reporte?.mes_cerrado && (
            <span className="px-2.5 py-1 rounded-full bg-[#191818] text-white text-xs font-bold">
              MES CERRADO Y BLOQUEADO
            </span>
          )}
        </div>

        {cargando ? (
          <div className="p-6 h-24 bg-neutral-100/60 animate-pulse" />
        ) : comisionesFiltradas.length === 0 ? (
          <p className="p-8 text-center text-sm text-neutral-500">
            No hay comisiones que coincidan con los filtros seleccionados.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-neutral-50/90 border-b border-neutral-200 text-xs uppercase text-neutral-500">
                <tr>
                  <th className="px-4 py-3">Colaborador</th>
                  <th className="px-4 py-3 text-center">Ventas</th>
                  <th className="px-4 py-3 text-right">Base Promo</th>
                  <th className="px-4 py-3 text-right">1% Ventas</th>
                  <th className="px-4 py-3 text-right">0,5% Líder</th>
                  <th className="px-4 py-3 text-right">50% ST</th>
                  <th className="px-4 py-3 text-right">Preps</th>
                  <th className="px-4 py-3 text-right">Total a Pagar</th>
                  <th className="px-4 py-3 text-right">WhatsApp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {comisionesFiltradas.map((c) => (
                  <tr key={c.usuario_id} className="hover:bg-white/60">
                    <td className="px-4 py-3">
                      <p className="font-bold text-[#191818]">{c.nombre}</p>
                      <p className="text-[11px] text-neutral-500">{c.rol}</p>
                    </td>
                    <td className="px-4 py-3 text-center tabular-nums font-semibold">
                      {c.cantidad_ventas ?? 0}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {formatearUsd(c.ventas_promo_usd)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {formatearUsd(c.comision_ventas_1_usd)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {formatearUsd(c.comision_lider_05_usd)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {formatearUsd(c.comision_servicios_50_usd)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {formatearUsd(c.pago_preparaciones_usd)}
                    </td>
                    <td className="px-4 py-3 text-right font-black text-emerald-700 tabular-nums">
                      {formatearUsd(c.total_comision_usd)}
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      <div className="inline-flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => void copiarIndividual(c)}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 text-xs font-bold cursor-pointer"
                          title="Copiar resumen individual para WhatsApp"
                        >
                          {copiadoPersonaId === c.usuario_id ? (
                            <Check className="w-3.5 h-3.5" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                          {copiadoPersonaId === c.usuario_id
                            ? "¡Copiado!"
                            : "Copiar"}
                        </button>
                        <a
                          href={urlWhatsAppIndividual(c)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold"
                          title="Enviar resumen individual por WhatsApp"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                          Enviar
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Detalle de operaciones incluidas */}
      <div className="bg-white/75 backdrop-blur-md rounded-2xl border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] overflow-hidden">
        <div className="px-5 py-3.5 border-b border-neutral-200/80 flex items-center justify-between">
          <span className="font-bold text-sm text-[#191818]">
            Detalle de Operaciones Incluidas ({operacionesFiltradas.length})
          </span>
        </div>

        {operacionesFiltradas.length === 0 ? (
          <p className="p-6 text-center text-sm text-neutral-500">
            No hay operaciones comisionables en este rango.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-neutral-50/90 border-b border-neutral-200 uppercase text-neutral-500">
                <tr>
                  <th className="px-4 py-2.5">Nota / Ref.</th>
                  <th className="px-4 py-2.5">Fecha</th>
                  <th className="px-4 py-2.5">Cliente</th>
                  <th className="px-4 py-2.5">Colaborador</th>
                  <th className="px-4 py-2.5">Tipo</th>
                  <th className="px-4 py-2.5 text-right">Base Promo USD</th>
                  <th className="px-4 py-2.5 text-right">Comisión USD</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {operacionesFiltradas.map((op, idx) => (
                  <tr
                    key={`${op.numero_nota}-${op.usuario_id}-${op.tipo}-${idx}`}
                    className="hover:bg-white/60"
                  >
                    <td className="px-4 py-2.5 font-mono font-bold text-[#191818]">
                      {op.numero_nota}
                    </td>
                    <td className="px-4 py-2.5 text-neutral-600">{op.fecha}</td>
                    <td className="px-4 py-2.5 text-[#191818]">{op.cliente}</td>
                    <td className="px-4 py-2.5">
                      <span className="font-semibold text-[#191818]">
                        {op.usuario_nombre}
                      </span>{" "}
                      <span className="text-neutral-400">({op.rol})</span>
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="inline-flex px-2 py-0.5 rounded-full bg-[#FDF0EB] text-[#E85A28] font-bold">
                        {op.tipo}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      {formatearUsd(op.base_promo_usd)}
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold text-emerald-700 tabular-nums">
                      {formatearUsd(op.comision_usd)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal de confirmación de cierre de mes */}
      {modalCierre && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white/95 backdrop-blur-md rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4 border border-white/60">
            <h3 className="text-lg font-black text-[#191818]">
              Cerrar período {String(mesCierre).padStart(2, "0")}/{anioCierre}
            </h3>
            <p className="text-sm text-neutral-600">
              Al cerrar el mes se guardará una fotografía inmutable de las
              comisiones y quedará bloqueada cualquier venta, devolución o abono
              en ese período.
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setModalCierre(false)}
                className="px-4 py-2 rounded-xl border border-neutral-300 text-xs font-bold cursor-pointer"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={() => void confirmarCierreMes()}
                className="px-4 py-2 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] text-white text-xs font-bold cursor-pointer"
              >
                Confirmar cierre
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
