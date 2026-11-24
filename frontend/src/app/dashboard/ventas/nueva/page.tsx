"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Copy,
  FileDown,
  Plus,
  Search,
  ShoppingCart,
  Trash2,
  X,
} from "lucide-react";
import { usarSesion } from "@/contexto/SesionContexto";
import {
  ErrorApi,
  descargarPdfApi,
  formatearBs,
  formatearUsd,
  solicitarApi,
} from "@/servicios/api";
import type {
  ArticuloCatalogo,
  CatalogoPaginado,
  Sucursal,
  TasaHoy,
} from "@/tipos/dominio";
import type {
  InstrumentoFinanciero,
  SimulacionVenta,
  VentaResumen,
} from "@/tipos/finanzas";
import type { EquipoInventario } from "@/tipos/logistica";

interface ItemCarrito {
  tipo: "EQUIPO" | "ARTICULO";
  equipo_id?: number;
  articulo_id?: number;
  etiqueta: string;
  cantidad: number;
  precio_promo_usd: number;
  precio_regular_fijo_usd?: number | null;
}

interface FilaPago {
  instrumento_id: string;
  monto_moneda_origen: string;
  referencia: string;
  parte_pago_serial: string;
  parte_pago_modelo: string;
}

function redondear2(valor: number): number {
  return Math.round((valor + Number.EPSILON) * 100) / 100;
}

function esInstrumentoCashea(inst?: InstrumentoFinanciero): boolean {
  return inst ? inst.nombre.toLowerCase().includes("cashea") : false;
}

export default function PaginaNuevaVentaPOS() {
  const { usuario } = usarSesion();
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [equiposListos, setEquiposListos] = useState<EquipoInventario[]>([]);
  const [catalogo, setCatalogo] = useState<ArticuloCatalogo[]>([]);
  const [instrumentos, setInstrumentos] = useState<InstrumentoFinanciero[]>([]);
  const [tasaHoy, setTasaHoy] = useState<TasaHoy | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [sucursalId, setSucursalId] = useState("");
  const [canalVisita, setCanalVisita] = useState("Tienda");
  const [entrega, setEntrega] = useState("Tienda");
  const [quedaConSaldo, setQuedaConSaldo] = useState(false);
  const [nota, setNota] = useState("");

  const [carrito, setCarrito] = useState<ItemCarrito[]>([]);
  const [equipoSel, setEquipoSel] = useState("");
  const [busquedaEquipo, setBusquedaEquipo] = useState("");
  const [menuEquiposAbierto, setMenuEquiposAbierto] = useState(false);
  const contenedorSelectorEquiposRef = useRef<HTMLDivElement | null>(null);
  const [articuloSel, setArticuloSel] = useState("");

  const [pagos, setPagos] = useState<FilaPago[]>([
    {
      instrumento_id: "",
      monto_moneda_origen: "",
      referencia: "",
      parte_pago_serial: "",
      parte_pago_modelo: "",
    },
  ]);

  const [simulacion, setSimulacion] = useState<SimulacionVenta | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [ventaCreada, setVentaCreada] = useState<VentaResumen | null>(null);
  const [copiado, setCopiado] = useState(false);

  // Cerrar el desplegable de equipos al hacer clic fuera
  useEffect(() => {
    const manejarClickFuera = (ev: MouseEvent) => {
      if (
        contenedorSelectorEquiposRef.current &&
        !contenedorSelectorEquiposRef.current.contains(ev.target as Node)
      ) {
        setMenuEquiposAbierto(false);
      }
    };
    document.addEventListener("mousedown", manejarClickFuera);
    return () => document.removeEventListener("mousedown", manejarClickFuera);
  }, []);

  const cargarBase = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [respSuc, respInst, respCat, respTasa] = await Promise.all([
        solicitarApi<Sucursal[]>("/api/sucursales"),
        solicitarApi<InstrumentoFinanciero[]>("/api/finanzas/instrumentos"),
        solicitarApi<CatalogoPaginado>("/api/catalogo?por_pagina=100"),
        solicitarApi<TasaHoy>("/api/tasas/hoy").catch(() => null),
      ]);
      const activas = respSuc.filter((s) => s.estado === "ACTIVA");
      setSucursales(activas);
      setInstrumentos(respInst);
      setCatalogo(respCat.elementos);
      setTasaHoy(respTasa);
      if (usuario?.sucursal && usuario.sucursal.estado === "ACTIVA") {
        setSucursalId(String(usuario.sucursal.id));
      } else if (activas[0]) {
        setSucursalId(String(activas[0].id));
      }
      if (respInst[0]) {
        setPagos([
          {
            instrumento_id: String(respInst[0].id),
            monto_moneda_origen: "",
            referencia: "",
            parte_pago_serial: "",
            parte_pago_modelo: "",
          },
        ]);
      }
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "No se pudo inicializar el POS."
      );
    } finally {
      setCargando(false);
    }
  }, [usuario]);

  useEffect(() => {
    void cargarBase();
  }, [cargarBase]);

  useEffect(() => {
    if (!sucursalId) return;
    const cargarEquipos = async () => {
      try {
        const lista = await solicitarApi<EquipoInventario[]>(
          `/api/logistica/inventario/equipos?sucursal_id=${sucursalId}&estado=LISTO`
        );
        setEquiposListos(lista);
      } catch {
        setEquiposListos([]);
      }
    };
    void cargarEquipos();
  }, [sucursalId]);

  const mapaInstrumentos = useMemo(() => {
    const mapa = new Map<string, InstrumentoFinanciero>();
    for (const inst of instrumentos) {
      mapa.set(String(inst.id), inst);
    }
    return mapa;
  }, [instrumentos]);

  const indiceCashea = useMemo(
    () =>
      pagos.findIndex((p) =>
        esInstrumentoCashea(mapaInstrumentos.get(p.instrumento_id))
      ),
    [pagos, mapaInstrumentos]
  );

  const usaCasheaLocal = indiceCashea >= 0;

  const tasaBcvActual = useMemo(
    () => simulacion?.tasa_bcv || tasaHoy?.tasa_bcv || 0,
    [simulacion?.tasa_bcv, tasaHoy?.tasa_bcv]
  );

  const recargoPctActual = useMemo(
    () =>
      simulacion?.recargo_porcentaje ??
      tasaHoy?.recargo_porcentaje ??
      0,
    [simulacion?.recargo_porcentaje, tasaHoy?.recargo_porcentaje]
  );

  const totalRegularLocal = useMemo(() => {
    const factor = 1 + recargoPctActual / 100;
    return redondear2(
      carrito.reduce((acc, item) => {
        const unitRegular =
          item.precio_regular_fijo_usd != null
            ? item.precio_regular_fijo_usd
            : redondear2(item.precio_promo_usd * factor);
        return acc + unitRegular * item.cantidad;
      }, 0)
    );
  }, [carrito, recargoPctActual]);

  const totalRegularBase =
    simulacion && carrito.length > 0
      ? simulacion.total_regular_usd
      : totalRegularLocal;

  const inicialesRegularUsd = useMemo(() => {
    let suma = 0;
    for (let i = 0; i < pagos.length; i += 1) {
      const p = pagos[i];
      const inst = mapaInstrumentos.get(p.instrumento_id);
      if (esInstrumentoCashea(inst)) continue;
      const monto = Number(p.monto_moneda_origen);
      if (!Number.isFinite(monto) || monto <= 0) continue;
      if (inst?.moneda === "BS") {
        if (tasaBcvActual > 0) {
          suma += redondear2(monto / tasaBcvActual);
        }
      } else {
        suma += redondear2(monto);
      }
    }
    return redondear2(suma);
  }, [pagos, mapaInstrumentos, tasaBcvActual]);

  const casheaFinanciadoAutoUsd = useMemo(() => {
    if (!usaCasheaLocal || carrito.length === 0) return 0;
    return Math.max(0, redondear2(totalRegularBase - inicialesRegularUsd));
  }, [usaCasheaLocal, carrito.length, totalRegularBase, inicialesRegularUsd]);

  const casheaFinanciadoAutoBs = useMemo(() => {
    if (!usaCasheaLocal || tasaBcvActual <= 0) return null;
    return redondear2(casheaFinanciadoAutoUsd * tasaBcvActual);
  }, [usaCasheaLocal, tasaBcvActual, casheaFinanciadoAutoUsd]);

  // Recalcular automáticamente el monto financiado por Cashea al cambiar carrito o iniciales
  useEffect(() => {
    if (indiceCashea < 0) return;
    const montoCalculadoStr =
      carrito.length > 0 ? casheaFinanciadoAutoUsd.toFixed(2) : "";
    setPagos((prev) => {
      const idx = prev.findIndex((p) =>
        esInstrumentoCashea(mapaInstrumentos.get(p.instrumento_id))
      );
      if (idx < 0 || prev[idx].monto_moneda_origen === montoCalculadoStr) {
        return prev;
      }
      const copia = [...prev];
      copia[idx] = {
        ...copia[idx],
        monto_moneda_origen: montoCalculadoStr,
      };
      return copia;
    });
  }, [indiceCashea, carrito.length, casheaFinanciadoAutoUsd, mapaInstrumentos]);

  // Simulación en vivo de pagos mixtos y Cashea
  useEffect(() => {
    if (!sucursalId || carrito.length === 0) {
      setSimulacion(null);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const pagosValidos = pagos
          .filter(
            (p) =>
              p.instrumento_id !== "" && Number(p.monto_moneda_origen) > 0
          )
          .map((p) => ({
            instrumento_id: Number(p.instrumento_id),
            monto_moneda_origen: Number(p.monto_moneda_origen),
            referencia: p.referencia,
          }));

        const resp = await solicitarApi<SimulacionVenta>("/api/ventas/simular", {
          method: "POST",
          body: JSON.stringify({
            sucursal_id: Number(sucursalId),
            items: carrito.map((c) => ({
              equipo_id: c.equipo_id ?? null,
              articulo_id: c.articulo_id ?? null,
              cantidad: c.cantidad,
            })),
            pagos: pagosValidos,
          }),
        });
        setSimulacion(resp);
        setError(null);
      } catch (err) {
        if (err instanceof ErrorApi) setError(err.message);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [sucursalId, carrito, pagos]);

  const equiposFiltrados = useMemo(() => {
    const q = busquedaEquipo.trim().toLowerCase();
    return equiposListos.filter((eq) => {
      if (carrito.some((c) => c.equipo_id === eq.id)) return false;
      if (!q) return true;
      return (
        eq.serial.toLowerCase().includes(q) ||
        eq.modelo.toLowerCase().includes(q)
      );
    });
  }, [equiposListos, carrito, busquedaEquipo]);

  const equipoSeleccionadoObj = useMemo(
    () => equiposListos.find((e) => String(e.id) === equipoSel) ?? null,
    [equiposListos, equipoSel]
  );

  const agregarEquipoPorObj = (eq: EquipoInventario) => {
    if (carrito.some((c) => c.equipo_id === eq.id)) return;
    setCarrito((prev) => [
      ...prev,
      {
        tipo: "EQUIPO",
        equipo_id: eq.id,
        etiqueta: `${eq.serial} — ${eq.modelo}`,
        cantidad: 1,
        precio_promo_usd: eq.precio_promo_usd,
      },
    ]);
    setEquipoSel("");
    setBusquedaEquipo("");
    setMenuEquiposAbierto(false);
  };

  const agregarEquipo = () => {
    if (!equipoSeleccionadoObj) return;
    agregarEquipoPorObj(equipoSeleccionadoObj);
  };

  const agregarArticulo = () => {
    const art = catalogo.find((a) => String(a.id) === articuloSel);
    if (!art) return;
    setCarrito((prev) => [
      ...prev,
      {
        tipo: "ARTICULO",
        articulo_id: art.id,
        etiqueta: `${art.sku} — ${art.descripcion}`,
        cantidad: 1,
        precio_promo_usd: art.precio_promo_usd,
        precio_regular_fijo_usd: art.precio_regular_fijo_usd,
      },
    ]);
    setArticuloSel("");
  };

  const registrarVenta = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    if (carrito.length === 0) {
      setError("Agrega al menos un equipo o artículo al carrito.");
      return;
    }

    const pagosValidos = pagos
      .filter(
        (p) => p.instrumento_id !== "" && Number(p.monto_moneda_origen) > 0
      )
      .map((p) => ({
        instrumento_id: Number(p.instrumento_id),
        monto_moneda_origen: Number(p.monto_moneda_origen),
        referencia: p.referencia.trim(),
        parte_pago_serial: p.parte_pago_serial.trim() || null,
        parte_pago_modelo: p.parte_pago_modelo.trim() || null,
      }));

    setGuardando(true);
    try {
      const creada = await solicitarApi<VentaResumen>("/api/ventas", {
        method: "POST",
        body: JSON.stringify({
          sucursal_id: Number(sucursalId),
          asesor_id: usuario?.id ?? null,
          canal_visita: canalVisita,
          entrega,
          items: carrito.map((c) => ({
            equipo_id: c.equipo_id ?? null,
            articulo_id: c.articulo_id ?? null,
            cantidad: c.cantidad,
          })),
          pagos: pagosValidos,
          queda_con_saldo: quedaConSaldo,
          nota: nota.trim(),
        }),
      });
      setVentaCreada(creada);
      setCarrito([]);
      setNota("");
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "No se pudo registrar la venta."
      );
    } finally {
      setGuardando(false);
    }
  };

  const copiarWhatsApp = (venta: VentaResumen) => {
    const lineas = [
      `*TEKIO ELECTRONICS · Nota ${venta.numero_venta}*`,
      `Fecha: ${venta.fecha} · Sucursal: ${venta.sucursal}`,
      `Asesor: ${venta.asesor} · Estado: ${venta.estado}`,
      ...venta.detalles.map(
        (d) =>
          `• ${d.cantidad}x ${d.descripcion}${d.serial ? ` [${d.serial}]` : ""} — ${formatearUsd(d.precio_promo_usd)}`
      ),
      `*Total Promo:* ${formatearUsd(venta.total_promo_usd)} | *Regular:* ${formatearUsd(venta.total_regular_usd)}`,
    ].join("\n");
    void navigator.clipboard?.writeText(lineas);
    setCopiado(true);
    setTimeout(() => setCopiado(false), 2500);
  };

  if (cargando) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-7 h-72 rounded-2xl bg-slate-200 animate-pulse" />
        <div className="lg:col-span-5 h-72 rounded-2xl bg-slate-200 animate-pulse" />
      </div>
    );
  }

  const usaCasheaEfectivo = simulacion?.usa_cashea || usaCasheaLocal;

  return (
    <div className="space-y-6 min-w-0">
      <div>
        <h2 className="text-2xl font-black text-slate-900 flex items-center gap-2">
          <ShoppingCart className="w-6 h-6 text-[#E85A28] shrink-0" />
          Punto de Venta (POS) · Pagos Mixtos
        </h2>
        <p className="text-sm text-slate-500">
          Carrito ilimitado con cálculo en vivo de Precio Promo (divisas/USDT) y
          Precio Regular (Bs/Cashea).
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2.5 p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <form
        onSubmit={registrarVenta}
        className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start min-w-0"
      >
        {/* Columna izquierda: Datos y Carrito */}
        <div className="lg:col-span-7 min-w-0 overflow-visible bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="min-w-0">
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Sucursal activa
              </label>
              <select
                required
                value={sucursalId}
                onChange={(e) => {
                  setSucursalId(e.target.value);
                  setCarrito([]);
                  setEquipoSel("");
                  setBusquedaEquipo("");
                }}
                className="w-full min-w-0 px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
              >
                {sucursales.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.nombre}
                  </option>
                ))}
              </select>
            </div>
            <div className="min-w-0">
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Canal visita
              </label>
              <select
                value={canalVisita}
                onChange={(e) => setCanalVisita(e.target.value)}
                className="w-full min-w-0 px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
              >
                <option value="Tienda">Tienda / Pasillo</option>
                <option value="WhatsApp">WhatsApp / Leads</option>
                <option value="Instagram">Instagram</option>
              </select>
            </div>
            <div className="min-w-0">
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Entrega
              </label>
              <select
                value={entrega}
                onChange={(e) => setEntrega(e.target.value)}
                className="w-full min-w-0 px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
              >
                <option value="Tienda">Retiro en tienda</option>
                <option value="Delivery">Delivery</option>
                <option value="Envío nacional">Envío nacional</option>
              </select>
            </div>
          </div>

          {/* Agregar equipo LISTO por serial (desplegable con búsqueda y z-50) */}
          <div
            ref={contenedorSelectorEquiposRef}
            className="relative z-40 space-y-1.5 min-w-0"
          >
            <label className="block text-xs font-bold text-slate-700">
              Equipo LISTO por serial ({equiposFiltrados.length} disponibles)
            </label>
            <div className="flex gap-2 min-w-0">
              <div className="relative flex-1 min-w-0">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="text"
                  value={
                    equipoSeleccionadoObj && !menuEquiposAbierto
                      ? `${equipoSeleccionadoObj.serial} — ${equipoSeleccionadoObj.modelo}`
                      : busquedaEquipo
                  }
                  onFocus={() => setMenuEquiposAbierto(true)}
                  onChange={(e) => {
                    setEquipoSel("");
                    setBusquedaEquipo(e.target.value);
                    setMenuEquiposAbierto(true);
                  }}
                  placeholder={`Buscar por serial o modelo (${equiposListos.length} en sucursal)...`}
                  className="w-full min-w-0 pl-9 pr-16 py-2 rounded-xl border border-slate-300 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#E85A28]/30 focus:border-[#E85A28]"
                />
                {(busquedaEquipo || equipoSel) && (
                  <button
                    type="button"
                    onClick={() => {
                      setEquipoSel("");
                      setBusquedaEquipo("");
                      setMenuEquiposAbierto(true);
                    }}
                    aria-label="Limpiar búsqueda"
                    className="absolute right-8 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 cursor-pointer"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setMenuEquiposAbierto((prev) => !prev)}
                  aria-label="Desplegar equipos"
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-500 hover:text-slate-700 cursor-pointer"
                >
                  <ChevronDown className="w-4 h-4" />
                </button>
              </div>
              <button
                type="button"
                onClick={agregarEquipo}
                disabled={!equipoSeleccionadoObj}
                className="shrink-0 px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 disabled:opacity-40 text-white text-xs font-bold cursor-pointer"
              >
                + Equipo
              </button>
            </div>

            {menuEquiposAbierto && (
              <div className="absolute left-0 right-0 top-full mt-1 z-50 bg-white border border-slate-200 rounded-xl shadow-xl max-h-72 overflow-y-auto divide-y divide-slate-100">
                {equiposFiltrados.length === 0 ? (
                  <div className="p-4 text-center text-xs text-slate-500">
                    No se encontraron equipos LISTO que coincidan.
                  </div>
                ) : (
                  equiposFiltrados.map((eq) => (
                    <div
                      key={eq.id}
                      className="flex items-start justify-between gap-3 p-3 hover:bg-orange-50/70 transition-colors"
                    >
                      <button
                        type="button"
                        onClick={() => {
                          setEquipoSel(String(eq.id));
                          setBusquedaEquipo(`${eq.serial} — ${eq.modelo}`);
                          setMenuEquiposAbierto(false);
                        }}
                        className="flex-1 min-w-0 text-left cursor-pointer"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-xs font-bold text-slate-900 bg-slate-100 px-1.5 py-0.5 rounded">
                            {eq.serial}
                          </span>
                          <span className="text-xs font-bold text-emerald-700">
                            {formatearUsd(eq.precio_promo_usd)} Promo
                          </span>
                        </div>
                        <p className="text-xs text-slate-700 mt-1 whitespace-normal break-words leading-snug">
                          {eq.modelo}
                        </p>
                      </button>
                      <button
                        type="button"
                        onClick={() => agregarEquipoPorObj(eq)}
                        className="shrink-0 px-2.5 py-1.5 rounded-lg bg-[#E85A28] hover:bg-[#C9461A] text-white text-[11px] font-bold cursor-pointer"
                      >
                        + Añadir
                      </button>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Agregar artículo/componente/servicio */}
          <div className="flex gap-2 min-w-0">
            <select
              value={articuloSel}
              onChange={(e) => setArticuloSel(e.target.value)}
              className="flex-1 min-w-0 w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white truncate"
            >
              <option value="">Agregar SKU de catálogo...</option>
              {catalogo.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.sku} — {a.descripcion} ({formatearUsd(a.precio_promo_usd)})
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={agregarArticulo}
              className="shrink-0 px-4 py-2 rounded-xl border border-slate-300 text-xs font-bold hover:bg-slate-50 cursor-pointer"
            >
              + SKU
            </button>
          </div>

          {/* Lista del carrito */}
          <div className="border border-slate-200 rounded-xl overflow-hidden">
            {carrito.length === 0 ? (
              <p className="p-6 text-center text-xs text-slate-500">
                El carrito está vacío. Agrega equipos por serial o SKUs del
                catálogo.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-50 border-b border-slate-200 uppercase text-slate-500">
                    <tr>
                      <th className="px-3 py-2">Ítem</th>
                      <th className="px-3 py-2 text-right whitespace-nowrap">
                        Cant.
                      </th>
                      <th className="px-3 py-2 text-right whitespace-nowrap">
                        Promo USD
                      </th>
                      <th className="px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {carrito.map((c, idx) => (
                      <tr key={idx}>
                        <td className="px-3 py-2 font-semibold text-slate-800 whitespace-normal break-words">
                          {c.etiqueta}
                        </td>
                        <td className="px-3 py-2 text-right whitespace-nowrap">
                          {c.cantidad}
                        </td>
                        <td className="px-3 py-2 text-right font-bold text-emerald-700 whitespace-nowrap">
                          {formatearUsd(c.precio_promo_usd * c.cantidad)}
                        </td>
                        <td className="px-3 py-2 text-right whitespace-nowrap">
                          <button
                            type="button"
                            onClick={() =>
                              setCarrito((prev) =>
                                prev.filter((_, i) => i !== idx)
                              )
                            }
                            className="text-red-600 cursor-pointer"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <input
            type="text"
            value={nota}
            onChange={(e) => setNota(e.target.value)}
            placeholder="Nota u observaciones de la venta..."
            className="w-full min-w-0 px-3 py-2 rounded-xl border border-slate-300 text-sm"
          />
        </div>

        {/* Columna derecha: Pagos Mixtos y Simulador */}
        <div className="lg:col-span-5 min-w-0 bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-black uppercase text-slate-800">
              Métodos de pago
            </h3>
            <button
              type="button"
              onClick={() =>
                setPagos((prev) => [
                  ...prev,
                  {
                    instrumento_id: instrumentos[0]
                      ? String(instrumentos[0].id)
                      : "",
                    monto_moneda_origen: "",
                    referencia: "",
                    parte_pago_serial: "",
                    parte_pago_modelo: "",
                  },
                ])
              }
              className="inline-flex items-center gap-1 text-xs font-bold text-[#E85A28] cursor-pointer shrink-0"
            >
              <Plus className="w-3.5 h-3.5" />
              Añadir pago
            </button>
          </div>

          {usaCasheaLocal && (
            <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-900 space-y-0.5">
              <p className="font-bold">
                Modo Cashea activo · Precio Regular obligatorio
              </p>
              <p className="text-[11px] text-amber-800">
                Toda la venta se cobra a <strong>Precio Regular</strong> sin
                importar el método de la inicial. El monto financiado por Cashea
                se calcula automáticamente.
              </p>
            </div>
          )}

          <div className="space-y-3">
            {pagos.map((p, idx) => {
              const inst = mapaInstrumentos.get(p.instrumento_id);
              const esPartePago =
                inst?.nombre.toLowerCase().includes("parte de pago") ?? false;
              const esCasheaFila = esInstrumentoCashea(inst);
              return (
                <div
                  key={idx}
                  className={`p-3 rounded-xl border space-y-2 min-w-0 ${
                    esCasheaFila
                      ? "bg-orange-50/60 border-orange-200"
                      : "bg-slate-50 border-slate-200"
                  }`}
                >
                  <div className="flex gap-2 items-center min-w-0">
                    <select
                      value={p.instrumento_id}
                      onChange={(e) => {
                        const copia = [...pagos];
                        copia[idx] = {
                          ...copia[idx],
                          instrumento_id: e.target.value,
                        };
                        setPagos(copia);
                      }}
                      className="flex-1 min-w-0 w-full px-2.5 py-1.5 rounded-lg border border-slate-300 text-xs bg-white truncate"
                    >
                      {instrumentos.map((i) => (
                        <option key={i.id} value={i.id}>
                          {i.nombre} ({i.moneda})
                        </option>
                      ))}
                    </select>
                    {pagos.length > 1 && (
                      <button
                        type="button"
                        onClick={() =>
                          setPagos((prev) => prev.filter((_, i) => i !== idx))
                        }
                        className="text-red-600 cursor-pointer shrink-0"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <div className="min-w-0">
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        readOnly={esCasheaFila}
                        placeholder={
                          esCasheaFila
                            ? "Calculado automáticamente"
                            : `Monto (${inst?.moneda || "USD"})`
                        }
                        value={p.monto_moneda_origen}
                        onChange={(e) => {
                          if (esCasheaFila) return;
                          const copia = [...pagos];
                          copia[idx] = {
                            ...copia[idx],
                            monto_moneda_origen: e.target.value,
                          };
                          setPagos(copia);
                        }}
                        className={`w-full min-w-0 px-2.5 py-1.5 rounded-lg border text-xs ${
                          esCasheaFila
                            ? "border-orange-300 bg-orange-100/60 font-bold text-slate-900 cursor-not-allowed"
                            : "border-slate-300 bg-white"
                        }`}
                      />
                    </div>
                    <input
                      type="text"
                      placeholder="Referencia"
                      value={p.referencia}
                      onChange={(e) => {
                        const copia = [...pagos];
                        copia[idx] = {
                          ...copia[idx],
                          referencia: e.target.value,
                        };
                        setPagos(copia);
                      }}
                      className="w-full min-w-0 px-2.5 py-1.5 rounded-lg border border-slate-300 text-xs bg-white"
                    />
                  </div>

                  {esCasheaFila && carrito.length > 0 && (
                    <div className="flex flex-wrap items-center justify-between gap-1 text-[11px] font-semibold text-orange-900 bg-white/80 rounded-lg px-2.5 py-1.5 border border-orange-200">
                      <span>
                        Financiado auto:{" "}
                        <strong>{formatearUsd(casheaFinanciadoAutoUsd)}</strong>{" "}
                        USD Regular
                      </span>
                      <span>
                        {casheaFinanciadoAutoBs !== null
                          ? `≈ ${formatearBs(casheaFinanciadoAutoBs)} (BCV)`
                          : "Registra tasa BCV"}
                      </span>
                    </div>
                  )}

                  {esPartePago && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      <input
                        type="text"
                        required
                        placeholder="Serial recibido *"
                        value={p.parte_pago_serial}
                        onChange={(e) => {
                          const copia = [...pagos];
                          copia[idx] = {
                            ...copia[idx],
                            parte_pago_serial: e.target.value,
                          };
                          setPagos(copia);
                        }}
                        className="w-full min-w-0 px-2.5 py-1.5 rounded-lg border border-amber-300 text-xs bg-white font-mono"
                      />
                      <input
                        type="text"
                        required
                        placeholder="Modelo recibido *"
                        value={p.parte_pago_modelo}
                        onChange={(e) => {
                          const copia = [...pagos];
                          copia[idx] = {
                            ...copia[idx],
                            parte_pago_modelo: e.target.value,
                          };
                          setPagos(copia);
                        }}
                        className="w-full min-w-0 px-2.5 py-1.5 rounded-lg border border-amber-300 text-xs bg-white"
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Panel en vivo de cuadre */}
          {simulacion && (
            <div
              className={`p-4 rounded-xl border-2 space-y-1.5 text-xs ${
                simulacion.estado === "CUADRADA"
                  ? "bg-emerald-50 border-emerald-300 text-emerald-900"
                  : "bg-amber-50 border-amber-300 text-amber-900"
              }`}
            >
              {usaCasheaEfectivo ? (
                <>
                  <div className="flex justify-between font-bold text-sm">
                    <span>Total Regular ({simulacion.recargo_porcentaje}%):</span>
                    <span>{formatearUsd(simulacion.total_regular_usd)}</span>
                  </div>
                  <div className="flex justify-between text-[11px] opacity-80">
                    <span>Referencia Precio Promo (no aplica con Cashea):</span>
                    <span>{formatearUsd(simulacion.total_promo_usd)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Inicial(es) recibida(s):</span>
                    <span className="font-semibold">
                      {formatearUsd(inicialesRegularUsd)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Financiado Cashea:</span>
                    <span className="font-bold">
                      {formatearUsd(casheaFinanciadoAutoUsd)}
                      {casheaFinanciadoAutoBs !== null
                        ? ` (${formatearBs(casheaFinanciadoAutoBs)})`
                        : ""}
                    </span>
                  </div>
                  <div className="pt-2 border-t border-current/20 font-black text-sm">
                    {simulacion.estado === "CUADRADA"
                      ? "✅ Venta CUADRADA (Precio Regular)"
                      : `Falta ${formatearUsd(simulacion.falta_usd_regular)} USD Regular (${formatearBs(simulacion.falta_bs)})`}
                  </div>
                </>
              ) : (
                <>
                  <div className="flex justify-between font-bold text-sm">
                    <span>Total Promo:</span>
                    <span>{formatearUsd(simulacion.total_promo_usd)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Total Regular ({simulacion.recargo_porcentaje}%):</span>
                    <span className="font-semibold">
                      {formatearUsd(simulacion.total_regular_usd)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Cubierto (equiv. Promo):</span>
                    <span className="font-bold">
                      {formatearUsd(simulacion.cubierto_promo_usd)}
                    </span>
                  </div>
                  <div className="pt-2 border-t border-current/20 font-black text-sm">
                    {simulacion.estado === "CUADRADA"
                      ? "✅ Venta CUADRADA"
                      : `Falta ${formatearUsd(simulacion.falta_usd_promo)} en divisas o ${formatearBs(simulacion.falta_bs)}`}
                  </div>
                </>
              )}
            </div>
          )}

          <label className="inline-flex items-center gap-2 text-xs font-semibold text-slate-700">
            <input
              type="checkbox"
              checked={quedaConSaldo}
              onChange={(e) => setQuedaConSaldo(e.target.checked)}
            />
            Permitir registrar como Cuenta por Cobrar (CON_SALDO)
          </label>

          <button
            type="submit"
            disabled={guardando || carrito.length === 0}
            className="w-full py-3 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] disabled:opacity-50 text-white font-black text-sm cursor-pointer"
          >
            {guardando ? "Registrando venta..." : "Confirmar y Emitir Nota"}
          </button>
        </div>
      </form>

      {/* Modal de éxito: PDF + WhatsApp */}
      {ventaCreada && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4 text-center">
            <CheckCircle2 className="w-12 h-12 text-emerald-600 mx-auto" />
            <h3 className="text-xl font-black text-slate-900">
              ¡Venta {ventaCreada.numero_venta} registrada!
            </h3>
            <p className="text-sm text-slate-600">
              Estado: <strong>{ventaCreada.estado}</strong> · Total Promo:{" "}
              <strong>{formatearUsd(ventaCreada.total_promo_usd)}</strong> ·
              Regular:{" "}
              <strong>{formatearUsd(ventaCreada.total_regular_usd)}</strong>
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2">
              <button
                type="button"
                onClick={() =>
                  void descargarPdfApi(
                    `/api/ventas/${ventaCreada.id}/nota-pdf`,
                    `Nota_${ventaCreada.numero_venta}.pdf`
                  )
                }
                className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-[#E85A28] text-white text-xs font-bold cursor-pointer"
              >
                <FileDown className="w-4 h-4" />
                Descargar Nota PDF
              </button>
              <button
                type="button"
                onClick={() => copiarWhatsApp(ventaCreada)}
                className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-600 text-white text-xs font-bold cursor-pointer"
              >
                <Copy className="w-4 h-4" />
                {copiado ? "¡Copiado!" : "Copiar WhatsApp"}
              </button>
            </div>
            <button
              type="button"
              onClick={() => setVentaCreada(null)}
              className="w-full py-2 rounded-xl border border-slate-300 text-xs font-semibold cursor-pointer"
            >
              Registrar otra venta
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
