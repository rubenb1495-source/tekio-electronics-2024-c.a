"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowRightCircle,
  Check,
  CheckCircle2,
  ClipboardList,
  Copy,
  FileDown,
  Gift,
  Loader2,
  Plus,
  Trash2,
  XCircle,
} from "lucide-react";
import BuscadorTabla from "@/componentes/BuscadorTabla";
import { usarSesion } from "@/contexto/SesionContexto";
import {
  copiarTextoPortapapeles,
  formatearWhatsAppCotizacion,
} from "@/lib/whatsapp";
import {
  descargarPdfApi,
  ErrorApi,
  formatearBs,
  formatearUsd,
  solicitarApi,
} from "@/servicios/api";
import type {
  ArticuloCatalogo,
  CatalogoPaginado,
  Sucursal,
} from "@/tipos/dominio";
import type { EquipoInventario, Tercero } from "@/tipos/logistica";
import type {
  CotizacionResumen,
  ModalidadCotizacion,
} from "@/tipos/operaciones";

interface UsuarioOperativo {
  id: number;
  nombre: string;
  rol: string;
  es_lider?: boolean;
  sucursal_id: number | null;
}

interface LineaCotizacionForm {
  uid: string;
  equipo_id: number | null;
  articulo_id: number | null;
  descripcion: string;
  cantidad: number;
  precio_promo_usd: number;
  es_obsequio: boolean;
}

const BADGE_ESTADO: Record<string, string> = {
  VIGENTE: "bg-emerald-50 text-emerald-700 border-emerald-200",
  CONVERTIDA: "bg-blue-50 text-blue-700 border-blue-200",
  VENCIDA: "bg-amber-50 text-amber-700 border-amber-200",
  ANULADA: "bg-neutral-100 text-neutral-500 border-neutral-200",
};

export default function PaginaCotizaciones() {
  const { usuario, tasaHoy } = usarSesion();

  const [cotizaciones, setCotizaciones] = useState<CotizacionResumen[]>([]);
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [clientes, setClientes] = useState<Tercero[]>([]);
  const [operativos, setOperativos] = useState<UsuarioOperativo[]>([]);
  const [equiposListos, setEquiposListos] = useState<EquipoInventario[]>([]);
  const [articulos, setArticulos] = useState<ArticuloCatalogo[]>([]);

  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);
  const [busqueda, setBusqueda] = useState("");
  const [copiadoId, setCopiadoId] = useState<number | null>(null);

  // Formulario nueva cotización
  const [sucursalId, setSucursalId] = useState("");
  const [clienteId, setClienteId] = useState("");
  const [asesorId, setAsesorId] = useState("");
  const [vigenciaHoras, setVigenciaHoras] = useState("48");
  const [modalidad, setModalidad] = useState<ModalidadCotizacion>("DIVISAS");
  const [nota, setNota] = useState("");
  const [lineas, setLineas] = useState<LineaCotizacionForm[]>([]);
  const [selectorEquipo, setSelectorEquipo] = useState("");
  const [selectorArticulo, setSelectorArticulo] = useState("");

  const cargarTodo = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [respCot, respSuc, respCli, respOp, respEq, respCat] =
        await Promise.all([
          solicitarApi<CotizacionResumen[]>("/api/cotizaciones"),
          solicitarApi<Sucursal[]>("/api/sucursales"),
          solicitarApi<Tercero[]>("/api/logistica/terceros?tipo=CLIENTE"),
          solicitarApi<UsuarioOperativo[]>("/api/usuarios/operativos"),
          solicitarApi<EquipoInventario[]>(
            "/api/logistica/inventario/equipos?estado=LISTO"
          ),
          solicitarApi<CatalogoPaginado>("/api/catalogo?limite=200"),
        ]);
      setCotizaciones(respCot);
      setSucursales(respSuc);
      setClientes(respCli);
      setOperativos(respOp);
      setEquiposListos(respEq);
      setArticulos(respCat.elementos);

      if (!sucursalId && respSuc.length > 0) {
        const sucUser = usuario?.sucursal?.id
          ? respSuc.find((s) => s.id === usuario.sucursal?.id)
          : respSuc[0];
        setSucursalId(String((sucUser || respSuc[0]).id));
      }
      if (!asesorId && usuario) {
        if (
          usuario.rol === "ASESORA" ||
          usuario.rol === "LIDER" ||
          usuario.rol === "TECNICO"
        ) {
          setAsesorId(String(usuario.id));
        }
      }
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudieron cargar las cotizaciones."
      );
    } finally {
      setCargando(false);
    }
  }, [usuario, sucursalId, asesorId]);

  useEffect(() => {
    void cargarTodo();
  }, [cargarTodo]);

  const agregarEquipo = () => {
    if (!selectorEquipo) return;
    const eq = equiposListos.find((e) => String(e.id) === selectorEquipo);
    if (!eq) return;
    const art = articulos.find((a) => a.id === eq.articulo_id);
    const precioBase = art?.precio_promo_usd ?? 0;
    setLineas((prev) => [
      ...prev,
      {
        uid: `eq-${eq.id}-${Date.now()}`,
        equipo_id: eq.id,
        articulo_id: eq.articulo_id,
        descripcion: art ? art.descripcion : eq.modelo,
        cantidad: 1,
        precio_promo_usd: precioBase,
        es_obsequio: false,
      },
    ]);
    setSelectorEquipo("");
  };

  const agregarArticulo = () => {
    if (!selectorArticulo) return;
    const art = articulos.find((a) => String(a.id) === selectorArticulo);
    if (!art) return;
    setLineas((prev) => [
      ...prev,
      {
        uid: `art-${art.id}-${Date.now()}`,
        equipo_id: null,
        articulo_id: art.id,
        descripcion: art.descripcion,
        cantidad: 1,
        precio_promo_usd: art.precio_promo_usd ?? 0,
        es_obsequio: false,
      },
    ]);
    setSelectorArticulo("");
  };

  const recargoPct = tasaHoy?.recargo_porcentaje ?? 20;
  const tasaBcv = tasaHoy?.tasa_bcv ?? 0;

  const totalesEstimados = useMemo(() => {
    const promo = lineas.reduce(
      (acc, l) => acc + (l.es_obsequio ? 0 : l.precio_promo_usd) * l.cantidad,
      0
    );
    const regular = promo * (1 + recargoPct / 100);
    const bs = tasaBcv > 0 ? regular * tasaBcv : 0;
    return { promo, regular, bs };
  }, [lineas, recargoPct, tasaBcv]);

  const crearCotizacion = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setExito(null);

    if (!sucursalId) {
      setError("Selecciona la sucursal.");
      return;
    }
    if (lineas.length === 0) {
      setError("Agrega al menos un equipo, componente o servicio a la cotización.");
      return;
    }

    setGuardando(true);
    try {
      const res = await solicitarApi<CotizacionResumen>("/api/cotizaciones", {
        method: "POST",
        body: JSON.stringify({
          sucursal_id: Number(sucursalId),
          cliente_id: clienteId ? Number(clienteId) : null,
          asesor_id: asesorId ? Number(asesorId) : null,
          vigencia_horas: Number(vigenciaHoras) || 48,
          modalidad_precio: modalidad,
          nota: nota.trim(),
          items: lineas.map((l) => ({
            equipo_id: l.equipo_id,
            articulo_id: l.articulo_id,
            descripcion_libre: l.descripcion,
            cantidad: l.cantidad,
            precio_pactado_usd: l.es_obsequio ? 0 : l.precio_promo_usd,
          })),
        }),
      });
      setExito(`Cotización ${res.numero_cotizacion} creada correctamente (no descuenta inventario).`);
      setLineas([]);
      setNota("");
      await cargarTodo();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo crear la cotización."
      );
    } finally {
      setGuardando(false);
    }
  };

  const abrirPdf = async (cot: CotizacionResumen) => {
    await descargarPdfApi(
      `/api/cotizaciones/${cot.id}/pdf`,
      `Cotizacion_${cot.numero_cotizacion}.pdf`
    );
  };

  const copiarWa = async (cot: CotizacionResumen) => {
    const ok = await copiarTextoPortapapeles(formatearWhatsAppCotizacion(cot));
    if (ok) {
      setCopiadoId(cot.id);
      setTimeout(() => setCopiadoId(null), 2200);
    }
  };

  const anularCotizacion = async (cot: CotizacionResumen) => {
    try {
      await solicitarApi(`/api/cotizaciones/${cot.id}/estado`, {
        method: "PATCH",
        body: JSON.stringify({ estado: "ANULADA" }),
      });
      await cargarTodo();
    } catch {
      setError("No se pudo anular la cotización.");
    }
  };

  const filtradas = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return cotizaciones;
    return cotizaciones.filter((c) =>
      [
        c.numero_cotizacion,
        c.cliente,
        c.cliente_rif,
        c.asesor,
        c.sucursal,
        c.estado,
        c.modalidad_precio,
        ...c.detalles.map((d) => d.descripcion),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [cotizaciones, busqueda]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-black text-tekio-carbon flex items-center gap-2">
          <ClipboardList className="w-6 h-6 text-tekio-naranja" />
          Cotizaciones de Equipos
        </h2>
        <p className="text-sm text-neutral-500">
          Genera presupuestos formales en PDF o WhatsApp sin descontar inventario, y conviértelos en venta con 1 clic.
        </p>
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

      {/* Formulario crear cotización */}
      <form
        onSubmit={crearCotizacion}
        className="bg-white/75 backdrop-blur-md border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl p-5 space-y-5"
      >
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <div>
            <label className="block text-xs font-bold text-neutral-600 mb-1">
              Sucursal *
            </label>
            <select
              value={sucursalId}
              onChange={(e) => setSucursalId(e.target.value)}
              className="w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm"
              required
            >
              {sucursales.map((s) => (
                <option key={s.id} value={String(s.id)}>
                  {s.nombre}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-bold text-neutral-600 mb-1">
              Cliente
            </label>
            <select
              value={clienteId}
              onChange={(e) => setClienteId(e.target.value)}
              className="w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm"
            >
              <option value="">Cliente general</option>
              {clientes.map((c) => (
                <option key={c.id} value={String(c.id)}>
                  {c.nombre}
                  {c.rif_cedula ? ` (${c.rif_cedula})` : ""}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-bold text-neutral-600 mb-1">
              Asesor
            </label>
            <select
              value={asesorId}
              onChange={(e) => setAsesorId(e.target.value)}
              className="w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm"
            >
              <option value="">Tienda (Sin comisión)</option>
              {operativos.map((u) => (
                <option key={u.id} value={String(u.id)}>
                  {u.nombre} ({u.rol})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-bold text-neutral-600 mb-1">
              Modalidad de precio
            </label>
            <select
              value={modalidad}
              onChange={(e) =>
                setModalidad(e.target.value as ModalidadCotizacion)
              }
              className="w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm"
            >
              <option value="DIVISAS">Divisas / USDT (Promo)</option>
              <option value="REGULAR">Bolívares / Mixto (Regular)</option>
              <option value="CASHEA">Cashea (Regular + Cuotas)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-bold text-neutral-600 mb-1">
              Vigencia
            </label>
            <select
              value={vigenciaHoras}
              onChange={(e) => setVigenciaHoras(e.target.value)}
              className="w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm"
            >
              <option value="24">24 horas</option>
              <option value="48">48 horas</option>
              <option value="72">72 horas</option>
            </select>
          </div>
        </div>

        {/* Selectores de equipos y artículos */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="flex gap-2">
            <select
              value={selectorEquipo}
              onChange={(e) => setSelectorEquipo(e.target.value)}
              className="flex-1 min-w-0 rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm"
            >
              <option value="">Agregar equipo disponible (LISTO)...</option>
              {equiposListos.map((eq) => (
                <option key={eq.id} value={String(eq.id)}>
                  {eq.modelo} · Serial: {eq.serial}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={agregarEquipo}
              className="inline-flex items-center gap-1 rounded-xl bg-tekio-naranja hover:bg-tekio-naranja-hover text-white px-3.5 py-2 text-xs font-bold shrink-0"
            >
              <Plus className="w-4 h-4" />
              Equipo
            </button>
          </div>

          <div className="flex gap-2">
            <select
              value={selectorArticulo}
              onChange={(e) => setSelectorArticulo(e.target.value)}
              className="flex-1 min-w-0 rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm"
            >
              <option value="">Agregar artículo / accesorio / servicio...</option>
              {articulos.map((a) => (
                <option key={a.id} value={String(a.id)}>
                  {a.sku} · {a.descripcion} ({formatearUsd(a.precio_promo_usd || 0)})
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={agregarArticulo}
              className="inline-flex items-center gap-1 rounded-xl border border-neutral-300 bg-white hover:bg-neutral-50 text-tekio-carbon px-3.5 py-2 text-xs font-bold shrink-0"
            >
              <Plus className="w-4 h-4" />
              Ítem
            </button>
          </div>
        </div>

        {/* Líneas de la cotización */}
        {lineas.length > 0 && (
          <div className="rounded-xl border border-neutral-200 bg-white/80 divide-y divide-neutral-100">
            {lineas.map((l) => (
              <div
                key={l.uid}
                className="p-3 flex flex-wrap items-center justify-between gap-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-tekio-carbon">
                    {l.descripcion}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <input
                    type="number"
                    min={1}
                    value={l.cantidad}
                    disabled={l.equipo_id !== null}
                    onChange={(e) => {
                      const val = Math.max(1, Number(e.target.value) || 1);
                      setLineas((prev) =>
                        prev.map((x) =>
                          x.uid === l.uid ? { ...x, cantidad: val } : x
                        )
                      );
                    }}
                    className="w-16 rounded-lg border border-neutral-200 px-2 py-1 text-xs text-center tabular-nums"
                  />
                  <input
                    type="number"
                    step="0.01"
                    min={0}
                    disabled={l.es_obsequio}
                    value={l.es_obsequio ? 0 : l.precio_promo_usd}
                    onChange={(e) => {
                      const val = Math.max(0, Number(e.target.value) || 0);
                      setLineas((prev) =>
                        prev.map((x) =>
                          x.uid === l.uid ? { ...x, precio_promo_usd: val } : x
                        )
                      );
                    }}
                    className="w-24 rounded-lg border border-neutral-200 px-2 py-1 text-xs text-right tabular-nums"
                    title="Precio Divisas USD"
                  />
                  <button
                    type="button"
                    onClick={() =>
                      setLineas((prev) =>
                        prev.map((x) =>
                          x.uid === l.uid
                            ? { ...x, es_obsequio: !x.es_obsequio }
                            : x
                        )
                      )
                    }
                    className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold border ${
                      l.es_obsequio
                        ? "bg-tekio-naranja-suave border-tekio-naranja text-tekio-naranja"
                        : "bg-white border-neutral-200 text-neutral-600"
                    }`}
                  >
                    <Gift className="w-3 h-3" />
                    Obsequio
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setLineas((prev) => prev.filter((x) => x.uid !== l.uid))
                    }
                    className="p-1.5 text-neutral-400 hover:text-red-600"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-4 pt-1">
          <input
            type="text"
            value={nota}
            onChange={(e) => setNota(e.target.value)}
            placeholder="Nota opcional para el cliente (ej. Incluye bolso y mouse de cortesía)..."
            className="flex-1 min-w-[240px] rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm"
          />

          <div className="flex items-center gap-4">
            <div className="text-right tabular-nums">
              <p className="text-xs text-neutral-500">
                Total{" "}
                {modalidad === "DIVISAS" ? "Divisas (USD)" : "Regular (USD / Bs)"}
              </p>
              <p className="text-lg font-black text-tekio-naranja">
                {formatearUsd(
                  modalidad === "DIVISAS"
                    ? totalesEstimados.promo
                    : totalesEstimados.regular
                )}
              </p>
              {modalidad !== "DIVISAS" && totalesEstimados.bs > 0 && (
                <p className="text-xs font-semibold text-neutral-600">
                  {formatearBs(totalesEstimados.bs)}
                </p>
              )}
            </div>

            <button
              type="submit"
              disabled={guardando}
              className="inline-flex items-center gap-2 rounded-xl bg-tekio-naranja hover:bg-tekio-naranja-hover text-white px-5 py-2.5 text-sm font-bold transition-colors disabled:opacity-60"
            >
              {guardando ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <ClipboardList className="w-4 h-4" />
              )}
              Guardar Cotización
            </button>
          </div>
        </div>
      </form>

      {/* Historial de cotizaciones */}
      <div className="bg-white/75 backdrop-blur-md border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-base font-bold text-tekio-carbon">
            Historial de Cotizaciones ({filtradas.length})
          </h3>
          <div className="w-full sm:w-80">
            <BuscadorTabla
              valor={busqueda}
              alCambiar={setBusqueda}
              placeholder="Buscar por COT, cliente, asesor o modelo..."
            />
          </div>
        </div>

        {cargando ? (
          <p className="text-sm text-neutral-500 py-6 text-center">
            Cargando cotizaciones...
          </p>
        ) : filtradas.length === 0 ? (
          <p className="text-sm text-neutral-500 py-6 text-center">
            Aún no hay cotizaciones registradas.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="border-b border-neutral-200 text-xs uppercase text-neutral-500">
                  <th className="py-2.5 px-3">Cotización</th>
                  <th className="py-2.5 px-3">Cliente / Asesor</th>
                  <th className="py-2.5 px-3">Modalidad / Estado</th>
                  <th className="py-2.5 px-3 text-right">Monto Total</th>
                  <th className="py-2.5 px-3 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {filtradas.map((c) => {
                  const esDivisas = c.modalidad_precio === "DIVISAS";
                  const totalUsd = esDivisas
                    ? c.total_promo_usd
                    : c.total_regular_usd;
                  return (
                    <tr key={c.id} className="hover:bg-white/60">
                      <td className="py-3 px-3">
                        <p className="font-bold text-tekio-carbon">
                          {c.numero_cotizacion}
                        </p>
                        <p className="text-xs text-neutral-500">
                          {c.fecha} · {c.vigencia_horas}h
                        </p>
                      </td>
                      <td className="py-3 px-3">
                        <p className="font-semibold text-tekio-carbon">
                          {c.cliente}
                        </p>
                        <p className="text-xs text-neutral-500">
                          {c.asesor} · {c.sucursal}
                        </p>
                      </td>
                      <td className="py-3 px-3 space-y-1">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold border ${
                            BADGE_ESTADO[c.estado] ||
                            "bg-neutral-100 text-neutral-600"
                          }`}
                        >
                          {c.estado}
                          {c.numero_venta ? ` (${c.numero_venta})` : ""}
                        </span>
                        <p className="text-xs text-neutral-500">
                          {c.modalidad_precio} · {c.detalles.length} ítem(s)
                        </p>
                      </td>
                      <td className="py-3 px-3 text-right tabular-nums">
                        <p className="font-bold text-tekio-carbon">
                          {formatearUsd(totalUsd)}
                        </p>
                        {!esDivisas && c.total_regular_bs > 0 && (
                          <p className="text-xs text-neutral-500">
                            {formatearBs(c.total_regular_bs)}
                          </p>
                        )}
                      </td>
                      <td className="py-3 px-3 text-right">
                        <div className="inline-flex flex-wrap items-center justify-end gap-1.5">
                          <button
                            type="button"
                            onClick={() => void abrirPdf(c)}
                            className="inline-flex items-center gap-1 rounded-lg border border-neutral-200 bg-white hover:bg-neutral-50 px-2.5 py-1.5 text-xs font-semibold text-tekio-carbon"
                          >
                            <FileDown className="w-3.5 h-3.5 text-tekio-naranja" />
                            PDF
                          </button>
                          <button
                            type="button"
                            onClick={() => void copiarWa(c)}
                            className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 px-2.5 py-1.5 text-xs font-semibold text-emerald-800"
                          >
                            {copiadoId === c.id ? (
                              <Check className="w-3.5 h-3.5" />
                            ) : (
                              <Copy className="w-3.5 h-3.5" />
                            )}
                            WA
                          </button>
                          {c.estado === "VIGENTE" && (
                            <>
                              <Link
                                href={`/dashboard/ventas/nueva?cotizacion_id=${c.id}`}
                                className="inline-flex items-center gap-1 rounded-lg bg-tekio-naranja hover:bg-tekio-naranja-hover text-white px-2.5 py-1.5 text-xs font-bold"
                              >
                                <ArrowRightCircle className="w-3.5 h-3.5" />
                                Convertir a Venta
                              </Link>
                              <button
                                type="button"
                                onClick={() => void anularCotizacion(c)}
                                className="inline-flex items-center gap-1 rounded-lg border border-neutral-200 bg-white hover:bg-red-50 hover:text-red-600 px-2 py-1.5 text-xs text-neutral-500"
                                title="Anular cotización"
                              >
                                <XCircle className="w-3.5 h-3.5" />
                              </button>
                            </>
                          )}
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
    </div>
  );
}
