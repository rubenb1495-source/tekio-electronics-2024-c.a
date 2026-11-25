"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Banknote,
  BarChart3,
  Calendar,
  Check,
  CheckCircle2,
  Copy,
  ExternalLink,
  FileDown,
  Lock,
  MessageSquare,
  X,
} from "lucide-react";
import BuscadorTabla from "@/componentes/BuscadorTabla";
import { usarSesion } from "@/contexto/SesionContexto";
import { usePermisos } from "@/lib/permisos";
import {
  construirUrlWhatsApp,
  copiarTextoPortapapeles,
  formatearWhatsAppComisionesGeneral,
  formatearWhatsAppComisionIndividual,
  formatearWhatsAppLiquidacion,
} from "@/lib/whatsapp";
import {
  ErrorApi,
  descargarPdfApi,
  formatearUsd,
  solicitarApi,
} from "@/servicios/api";
import type { Sucursal } from "@/tipos/dominio";
import type {
  ComisionPersona,
  InstrumentoFinanciero,
  LiquidacionComisionResumen,
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
  const permisos = usePermisos();
  const esDireccion = permisos.esDireccion;

  const inicial = useMemo(() => rangoEstaQuincena(), []);
  const [fechaInicio, setFechaInicio] = useState(inicial.inicio);
  const [fechaFin, setFechaFin] = useState(inicial.fin);
  const [usuarioFiltroId, setUsuarioFiltroId] = useState("");
  const [sucursalFiltroId, setSucursalFiltroId] = useState(
    permisos.sucursalRestringidaId ? String(permisos.sucursalRestringidaId) : ""
  );
  const [estadoFiltro, setEstadoFiltro] = useState<"TODAS" | "PENDIENTE" | "PAGADA">("TODAS");
  const [incluirNotasWa, setIncluirNotasWa] = useState(true);
  const [busqueda, setBusqueda] = useState("");
  const [busquedaLiq, setBusquedaLiq] = useState("");

  const [operativos, setOperativos] = useState<UsuarioOperativo[]>([]);
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [instrumentos, setInstrumentos] = useState<InstrumentoFinanciero[]>([]);
  const [liquidaciones, setLiquidaciones] = useState<LiquidacionComisionResumen[]>([]);
  const [reporte, setReporte] = useState<ReporteComisiones | null>(null);
  const [tablero, setTablero] = useState<TableroFinanciero | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);
  const [modalCierre, setModalCierre] = useState(false);

  // Modal liquidar pendientes
  const [personaLiquidar, setPersonaLiquidar] = useState<ComisionPersona | null>(null);
  const [instrumentoLiqId, setInstrumentoLiqId] = useState("");
  const [referenciaLiq, setReferenciaLiq] = useState("");
  const [notasLiq, setNotasLiq] = useState("");
  const [liquidando, setLiquidando] = useState(false);
  const [liqReciente, setLiqReciente] = useState<LiquidacionComisionResumen | null>(null);

  // Modal anular liquidación
  const [liqAnular, setLiqAnular] = useState<LiquidacionComisionResumen | null>(null);
  const [motivoAnulacionLiq, setMotivoAnulacionLiq] = useState("");
  const [anulandoLiq, setAnulandoLiq] = useState(false);

  const confirmarAnulacionLiq = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!liqAnular || motivoAnulacionLiq.trim().length < 3) return;
    setAnulandoLiq(true);
    setError(null);
    setExito(null);
    try {
      await solicitarApi(`/api/finanzas/liquidaciones/${liqAnular.id}/anular`, {
        method: "POST",
        body: JSON.stringify({ motivo_anulacion: motivoAnulacionLiq.trim() }),
      });
      setExito(
        `Liquidación ${liqAnular.codigo} anulada. Egreso revertido y comisiones devueltas a PENDIENTE.`
      );
      setLiqAnular(null);
      setMotivoAnulacionLiq("");
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo anular la liquidación."
      );
    } finally {
      setAnulandoLiq(false);
    }
  };

  const [copiadoGeneral, setCopiadoGeneral] = useState(false);
  const [copiadoPersonaId, setCopiadoPersonaId] = useState<number | null>(null);

  useEffect(() => {
    Promise.all([
      solicitarApi<UsuarioOperativo[]>("/api/usuarios/operativos").catch(
        () => []
      ),
      solicitarApi<Sucursal[]>("/api/sucursales").catch(() => []),
      solicitarApi<InstrumentoFinanciero[]>("/api/finanzas/instrumentos").catch(
        () => []
      ),
    ]).then(([ops, sucs, insts]) => {
      setOperativos(ops);
      setSucursales(sucs);
      setInstrumentos(insts.filter((i) => i.activo !== false));
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
      paramsCom.set("estado", estadoFiltro);

      const paramsTab = new URLSearchParams();
      if (fechaInicio) paramsTab.set("desde", fechaInicio);
      if (fechaFin) paramsTab.set("hasta", fechaFin);
      if (sucursalFiltroId) paramsTab.set("sucursal_id", sucursalFiltroId);

      const [respCom, respTab, respLiq] = await Promise.all([
        solicitarApi<ReporteComisiones>(
          `/api/finanzas/comisiones?${paramsCom.toString()}`
        ),
        permisos.puedeVerFinanzasGlobales
          ? solicitarApi<TableroFinanciero>(
              `/api/finanzas/tablero?${paramsTab.toString()}`
            ).catch(() => null)
          : Promise.resolve(null),
        permisos.puedeLiquidar
          ? solicitarApi<LiquidacionComisionResumen[]>(
              "/api/finanzas/liquidaciones"
            ).catch(() => [])
          : Promise.resolve([]),
      ]);
      setReporte(respCom);
      setTablero(respTab);
      setLiquidaciones(respLiq);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudieron cargar las comisiones y el tablero."
      );
    } finally {
      setCargando(false);
    }
  }, [
    fechaInicio,
    fechaFin,
    usuarioFiltroId,
    sucursalFiltroId,
    estadoFiltro,
    permisos.puedeVerFinanzasGlobales,
    permisos.puedeLiquidar,
  ]);

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

  const liquidacionesFiltradas = useMemo(() => {
    const q = busquedaLiq.trim().toLowerCase();
    if (!q) return liquidaciones;
    return liquidaciones.filter((l) =>
      [l.codigo, l.usuario_nombre, l.instrumento, l.referencia, l.fecha_pago]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [liquidaciones, busquedaLiq]);

  const abrirModalLiquidar = (persona: ComisionPersona) => {
    setPersonaLiquidar(persona);
    setInstrumentoLiqId(instrumentos[0] ? String(instrumentos[0].id) : "");
    setReferenciaLiq("");
    setNotasLiq("");
    setLiqReciente(null);
    setError(null);
  };

  const ejecutarLiquidacion = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!personaLiquidar || !instrumentoLiqId) return;
    setLiquidando(true);
    setError(null);
    try {
      const creada = await solicitarApi<LiquidacionComisionResumen>(
        "/api/finanzas/liquidaciones",
        {
          method: "POST",
          body: JSON.stringify({
            usuario_id: personaLiquidar.usuario_id,
            fecha_inicio: fechaInicio,
            fecha_fin: fechaFin,
            instrumento_id: Number(instrumentoLiqId),
            referencia: referenciaLiq.trim(),
            notas: notasLiq.trim(),
          }),
        }
      );
      setLiqReciente(creada);
      setExito(
        `Liquidación ${creada.codigo} por ${formatearUsd(creada.monto_total_usd)} registrada con egreso automático.`
      );
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo liquidar las comisiones pendientes."
      );
    } finally {
      setLiquidando(false);
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

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3">
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
              <option value="">Todos</option>
              {operativos.map((u) => (
                <option key={u.id} value={String(u.id)}>
                  {u.nombre} ({u.rol})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-[11px] font-bold uppercase text-neutral-500 mb-1">
              Estado Comisión
            </label>
            <select
              value={estadoFiltro}
              onChange={(e) =>
                setEstadoFiltro(e.target.value as "TODAS" | "PENDIENTE" | "PAGADA")
              }
              className="w-full px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm text-[#191818]"
            >
              <option value="TODAS">Todas</option>
              <option value="PENDIENTE">Pendientes</option>
              <option value="PAGADA">Pagadas</option>
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
              <option value="">Todas</option>
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
              placeholder="Buscar nombre, rol o nota..."
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
                  <th className="px-4 py-3 text-right">Total / Estado</th>
                  <th className="px-4 py-3 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {comisionesFiltradas.map((c) => {
                  const pendiente = c.monto_pendiente_usd ?? c.total_comision_usd;
                  const pagado = c.monto_pagado_usd ?? 0;
                  const esPagada = c.estado_comision === "PAGADA";
                  return (
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
                    <td className="px-4 py-3 text-right tabular-nums">
                      <p className="font-black text-emerald-700">
                        {formatearUsd(c.total_comision_usd)}
                      </p>
                      <span
                        className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold mt-0.5 ${
                          esPagada
                            ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                            : "bg-amber-50 text-amber-800 border border-amber-200"
                        }`}
                      >
                        {esPagada
                          ? `PAGADA (${formatearUsd(pagado)})`
                          : `PENDIENTE (${formatearUsd(pendiente)})`}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      <div className="inline-flex items-center gap-1.5">
                        {permisos.puedeLiquidar && pendiente > 0 && (
                          <button
                            type="button"
                            onClick={() => abrirModalLiquidar(c)}
                            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[#E85A28] hover:bg-[#D14D1F] text-white text-xs font-bold cursor-pointer"
                            title="Liquidar comisiones pendientes con egreso automático"
                          >
                            <Banknote className="w-3.5 h-3.5" />
                            Liquidar
                          </button>
                        )}
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
                          WA
                        </a>
                      </div>
                    </td>
                  </tr>
                  );
                })}
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
                  <th className="px-4 py-2.5">Estado</th>
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
                    <td className="px-4 py-2.5">
                      <span
                        className={`inline-flex px-2 py-0.5 rounded-full font-bold ${
                          op.estado_comision === "PAGADA"
                            ? "bg-emerald-50 text-emerald-700"
                            : "bg-amber-50 text-amber-800"
                        }`}
                      >
                        {op.estado_comision || "PENDIENTE"}
                        {op.liquidacion_codigo ? ` (${op.liquidacion_codigo})` : ""}
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

      {/* Historial de Liquidaciones */}
      {permisos.puedeLiquidar && (
      <div className="bg-white/75 backdrop-blur-md rounded-2xl border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-base font-bold text-[#191818]">
            Historial de Liquidaciones ({liquidacionesFiltradas.length})
          </h3>
          <div className="w-full sm:w-80">
            <BuscadorTabla
              valor={busquedaLiq}
              alCambiar={setBusquedaLiq}
              placeholder="Buscar por LIQ, colaborador o referencia..."
            />
          </div>
        </div>

        {liquidacionesFiltradas.length === 0 ? (
          <p className="text-sm text-neutral-500 text-center py-6">
            Aún no se han registrado liquidaciones de comisiones.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-neutral-50/90 border-b border-neutral-200 text-xs uppercase text-neutral-500">
                <tr>
                  <th className="px-4 py-2.5">Código / Pago</th>
                  <th className="px-4 py-2.5">Colaborador</th>
                  <th className="px-4 py-2.5">Período</th>
                  <th className="px-4 py-2.5">Instrumento / Ref.</th>
                  <th className="px-4 py-2.5 text-right">Monto USD</th>
                  <th className="px-4 py-2.5 text-right">Comprobante</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {liquidacionesFiltradas.map((l) => (
                  <tr key={l.id} className="hover:bg-white/60">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <p className="font-mono font-bold text-[#191818]">{l.codigo}</p>
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            l.estado === "ANULADA"
                              ? "bg-red-100 text-red-700"
                              : "bg-emerald-50 text-emerald-700"
                          }`}
                        >
                          {l.estado || "ACTIVA"}
                        </span>
                      </div>
                      <p className="text-xs text-neutral-500">{l.fecha_pago}</p>
                      {l.estado === "ANULADA" && l.motivo_anulacion && (
                        <p className="text-[11px] text-red-600 mt-0.5">
                          Motivo: {l.motivo_anulacion}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-semibold text-[#191818]">{l.usuario_nombre}</p>
                      <p className="text-xs text-neutral-500">
                        {l.usuario_rol} · {l.cantidad_operaciones} op.
                      </p>
                    </td>
                    <td className="px-4 py-3 text-xs text-neutral-600">
                      {l.fecha_inicio} al {l.fecha_fin}
                    </td>
                    <td className="px-4 py-3 text-xs">
                      <p className="font-semibold text-[#191818]">{l.instrumento}</p>
                      <p className="text-neutral-500">{l.referencia || "—"}</p>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums font-black text-emerald-700">
                      {formatearUsd(l.monto_total_usd)}
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap space-x-1.5">
                      <button
                        type="button"
                        onClick={() =>
                          void descargarPdfApi(
                            `/api/finanzas/liquidaciones/${l.id}/pdf`,
                            `Liquidacion_${l.codigo}.pdf`
                          )
                        }
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-neutral-200 bg-white hover:bg-neutral-50 text-xs font-bold text-[#191818] cursor-pointer"
                      >
                        <FileDown className="w-3.5 h-3.5 text-[#E85A28]" />
                        PDF
                      </button>
                      <a
                        href={construirUrlWhatsApp(
                          formatearWhatsAppLiquidacion(l),
                          l.usuario_telefono
                        )}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                        WA
                      </a>
                      {permisos.esAdmin && (l.estado || "ACTIVA") !== "ANULADA" && (
                        <button
                          type="button"
                          onClick={() => {
                            setLiqAnular(l);
                            setMotivoAnulacionLiq("");
                          }}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-red-200 bg-red-50 hover:bg-red-100 text-red-700 text-xs font-bold cursor-pointer"
                        >
                          Anular
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      )}

      {/* Modal Anular Liquidación */}
      {liqAnular && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <form
            onSubmit={confirmarAnulacionLiq}
            className="bg-white/95 backdrop-blur-md rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4 border border-white/60"
          >
            <h3 className="text-lg font-black text-red-700">
              Anular Liquidación {liqAnular.codigo}
            </h3>
            <p className="text-xs text-neutral-600">
              Esta acción marcará la liquidación de{" "}
              <strong>{liqAnular.usuario_nombre}</strong> ({formatearUsd(liqAnular.monto_total_usd)})
              como <strong>ANULADA</strong>, revertirá automáticamente el egreso financiero
              asociado y devolverá las comisiones a estado <strong>PENDIENTE</strong>.
            </p>
            <div>
              <label className="block text-xs font-bold text-neutral-700 mb-1">
                Motivo de anulación (obligatorio)
              </label>
              <textarea
                required
                minLength={3}
                rows={3}
                value={motivoAnulacionLiq}
                onChange={(e) => setMotivoAnulacionLiq(e.target.value)}
                placeholder="Ej: Error en el método de pago o monto seleccionado..."
                className="w-full px-3 py-2 rounded-xl border border-neutral-200 text-sm"
              />
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setLiqAnular(null)}
                className="px-4 py-2 rounded-xl border border-neutral-200 text-xs font-bold text-neutral-700 cursor-pointer"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={anulandoLiq || motivoAnulacionLiq.trim().length < 3}
                className="px-4 py-2 rounded-xl bg-red-600 hover:bg-red-700 text-white text-xs font-bold disabled:opacity-50 cursor-pointer"
              >
                {anulandoLiq ? "Anulando..." : "Confirmar Anulación"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Modal Liquidar Pendientes */}
      {personaLiquidar && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white/95 backdrop-blur-md rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4 border border-white/60">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-black text-[#191818]">
                Liquidar Comisiones Pendientes
              </h3>
              <button
                type="button"
                onClick={() => setPersonaLiquidar(null)}
                className="text-neutral-400 hover:text-neutral-700 cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {liqReciente ? (
              <div className="space-y-4 text-center py-2">
                <CheckCircle2 className="w-11 h-11 text-emerald-600 mx-auto" />
                <div>
                  <p className="font-black text-[#191818] text-base">
                    ¡Liquidación {liqReciente.codigo} registrada!
                  </p>
                  <p className="text-xs text-neutral-600 mt-1">
                    Egreso automático creado por{" "}
                    <strong>{formatearUsd(liqReciente.monto_total_usd)}</strong> en{" "}
                    <strong>{liqReciente.instrumento}</strong>.
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() =>
                      void descargarPdfApi(
                        `/api/finanzas/liquidaciones/${liqReciente.id}/pdf`,
                        `Liquidacion_${liqReciente.codigo}.pdf`
                      )
                    }
                    className="inline-flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] text-white text-xs font-bold cursor-pointer"
                  >
                    <FileDown className="w-4 h-4" />
                    Descargar Recibo PDF
                  </button>
                  <a
                    href={construirUrlWhatsApp(
                      formatearWhatsAppLiquidacion(liqReciente),
                      liqReciente.usuario_telefono
                    )}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold"
                  >
                    <ExternalLink className="w-4 h-4" />
                    Enviar por WhatsApp
                  </a>
                </div>
                <button
                  type="button"
                  onClick={() => setPersonaLiquidar(null)}
                  className="w-full py-2 rounded-xl border border-neutral-300 text-xs font-bold cursor-pointer"
                >
                  Cerrar
                </button>
              </div>
            ) : (
              <form onSubmit={ejecutarLiquidacion} className="space-y-3.5">
                <div className="rounded-xl bg-[#FDF0EB]/80 border border-[#E85A28]/30 p-3.5">
                  <p className="text-xs text-neutral-600">
                    Colaborador:{" "}
                    <strong className="text-[#191818]">
                      {personaLiquidar.nombre} ({personaLiquidar.rol})
                    </strong>
                  </p>
                  <p className="text-xs text-neutral-600">
                    Período: {fechaInicio} al {fechaFin}
                  </p>
                  <p className="text-lg font-black text-[#E85A28] mt-1 tabular-nums">
                    Pendiente por pagar:{" "}
                    {formatearUsd(
                      personaLiquidar.monto_pendiente_usd ??
                        personaLiquidar.total_comision_usd
                    )}
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-bold text-neutral-700 mb-1">
                    Cuenta / Caja de salida (Egreso) *
                  </label>
                  <select
                    required
                    value={instrumentoLiqId}
                    onChange={(e) => setInstrumentoLiqId(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm bg-white"
                  >
                    <option value="">Selecciona instrumento...</option>
                    {instrumentos.map((i) => (
                      <option key={i.id} value={String(i.id)}>
                        {i.nombre} ({i.moneda})
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-bold text-neutral-700 mb-1">
                    Referencia de pago
                  </label>
                  <input
                    type="text"
                    value={referenciaLiq}
                    onChange={(e) => setReferenciaLiq(e.target.value)}
                    placeholder="Nro. referencia bancaria o recibo"
                    className="w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold text-neutral-700 mb-1">
                    Notas
                  </label>
                  <input
                    type="text"
                    value={notasLiq}
                    onChange={(e) => setNotasLiq(e.target.value)}
                    placeholder="Ej. Pago quincena 1 de noviembre"
                    className="w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm"
                  />
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setPersonaLiquidar(null)}
                    className="px-4 py-2 rounded-xl border border-neutral-300 text-xs font-bold cursor-pointer"
                  >
                    Cancelar
                  </button>
                  <button
                    type="submit"
                    disabled={liquidando}
                    className="px-4 py-2 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] disabled:opacity-50 text-white text-xs font-bold cursor-pointer"
                  >
                    {liquidando ? "Liquidando..." : "Confirmar Pago y Egreso"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

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
