"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  Boxes,
  CheckCircle2,
  Clock,
  Plus,
  Search,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { usarSesion } from "@/contexto/SesionContexto";
import BarraListaPrecios from "@/components/BarraListaPrecios";
import PanelImportacionMasiva from "@/components/PanelImportacionMasiva";
import {
  ErrorApi,
  extraerMensajeError,
  formatearUsd,
  puedeVerCostos,
  solicitarApi,
} from "@/servicios/api";
import type { Sucursal } from "@/tipos/dominio";
import type {
  AjusteResumen,
  EquipoInventario,
  EstadoEquipo,
  KardexRespuesta,
  TipoAjuste,
  TrazabilidadEquipo,
} from "@/tipos/logistica";

const ESTADOS_EQUIPO: EstadoEquipo[] = [
  "EN_TRANSITO",
  "POR_PREPARAR",
  "EN_PREPARACION",
  "LISTO",
  "HOSPITAL",
  "RESERVADO",
  "CEMENTERIO",
  "VENDIDO",
];

const ESTADOS_EDITABLES: EstadoEquipo[] = [
  "EN_TRANSITO",
  "POR_PREPARAR",
  "EN_PREPARACION",
  "LISTO",
  "HOSPITAL",
  "RESERVADO",
  "CEMENTERIO",
];

export default function PaginaInventario() {
  const { usuario } = usarSesion();
  const verCostos = usuario ? puedeVerCostos(usuario.rol) : false;
  const esDireccion = usuario?.rol === "DIRECCION";
  const puedeSolicitarAjuste = usuario ? usuario.rol !== "ASESORA" : false;

  const [pestana, setPestana] = useState<
    "equipos" | "kardex" | "trazabilidad" | "ajustes"
  >("equipos");

  const [equipos, setEquipos] = useState<EquipoInventario[]>([]);
  const [kardex, setKardex] = useState<KardexRespuesta | null>(null);
  const [ajustes, setAjustes] = useState<AjusteResumen[]>([]);
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  // Filtros equipos
  const [busqueda, setBusqueda] = useState("");
  const [filtroSucursal, setFiltroSucursal] = useState("");
  const [filtroEstado, setFiltroEstado] = useState("");

  // Trazabilidad
  const [serialBuscar, setSerialBuscar] = useState("");
  const [trazabilidad, setTrazabilidad] = useState<TrazabilidadEquipo | null>(
    null
  );
  const [buscandoTraz, setBuscandoTraz] = useState(false);

  // Selección múltiple y cambio de estado individual/masivo
  const [seleccionadosIds, setSeleccionadosIds] = useState<number[]>([]);
  const [estadoMasivo, setEstadoMasivo] = useState<EstadoEquipo>("LISTO");
  const [motivoMasivo, setMotivoMasivo] = useState("");
  const [aplicandoMasivo, setAplicandoMasivo] = useState(false);
  const [actualizandoEquipoId, setActualizandoEquipoId] = useState<number | null>(
    null
  );

  const alternarSeleccion = (id: number) => {
    setSeleccionadosIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const cambiarEstadoIndividual = async (
    eq: EquipoInventario,
    nuevoEstado: EstadoEquipo
  ) => {
    if (eq.estado === nuevoEstado) return;
    setActualizandoEquipoId(eq.id);
    setError(null);
    setExito(null);
    try {
      await solicitarApi<{ actualizados: number; nuevo_estado: string }>(
        `/api/inventario/equipos/${eq.id}/estado`,
        {
          method: "PATCH",
          body: JSON.stringify({
            nuevo_estado: nuevoEstado,
            motivo: "Cambio individual desde Inventario",
          }),
        }
      );
      setEquipos((prev) =>
        prev
          .map((item) =>
            item.id === eq.id ? { ...item, estado: nuevoEstado } : item
          )
          .filter((item) => !filtroEstado || item.estado === filtroEstado)
      );
      setExito(`Equipo ${eq.serial} actualizado a ${nuevoEstado}.`);
    } catch (err) {
      setError(
        extraerMensajeError(err, "No se pudo actualizar el estado del equipo.")
      );
    } finally {
      setActualizandoEquipoId(null);
    }
  };

  const aplicarEstadoMasivo = async () => {
    if (seleccionadosIds.length === 0) return;
    setAplicandoMasivo(true);
    setError(null);
    setExito(null);
    try {
      const ids = [...seleccionadosIds];
      const res = await solicitarApi<{ actualizados: number; nuevo_estado: string }>(
        "/api/inventario/equipos/estado-masivo",
        {
          method: "PATCH",
          body: JSON.stringify({
            equipo_ids: ids,
            nuevo_estado: estadoMasivo,
            motivo: motivoMasivo.trim() || "Cambio masivo desde Inventario",
          }),
        }
      );
      const conjunto = new Set(ids);
      setEquipos((prev) =>
        prev
          .map((item) =>
            conjunto.has(item.id) ? { ...item, estado: estadoMasivo } : item
          )
          .filter((item) => !filtroEstado || item.estado === filtroEstado)
      );
      setExito(
        `Se actualizaron ${res.actualizados} equipos a estado ${res.nuevo_estado}.`
      );
      setSeleccionadosIds([]);
      setMotivoMasivo("");
    } catch (err) {
      setError(
        extraerMensajeError(err, "No se pudo actualizar el estado masivo.")
      );
    } finally {
      setAplicandoMasivo(false);
    }
  };

  // Modal ajuste
  const [modalAjuste, setModalAjuste] = useState(false);
  const [tipoAjuste, setTipoAjuste] = useState<TipoAjuste>("BAJA_EQUIPO");
  const [sucursalAjuste, setSucursalAjuste] = useState("");
  const [equipoAjuste, setEquipoAjuste] = useState("");
  const [motivoAjuste, setMotivoAjuste] = useState("");

  const cargarTodo = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (busqueda.trim()) params.set("busqueda", busqueda.trim());
      if (filtroSucursal) params.set("sucursal_id", filtroSucursal);
      if (filtroEstado) params.set("estado", filtroEstado);
      const qs = params.toString() ? `?${params.toString()}` : "";

      const [respEq, respKar, respAju, respSuc] = await Promise.all([
        solicitarApi<EquipoInventario[]>(
          `/api/logistica/inventario/equipos${qs}`
        ),
        solicitarApi<KardexRespuesta>("/api/logistica/inventario/kardex"),
        solicitarApi<AjusteResumen[]>("/api/logistica/ajustes"),
        solicitarApi<Sucursal[]>("/api/sucursales"),
      ]);
      setEquipos(respEq);
      setKardex(respKar);
      setAjustes(respAju);
      setSucursales(respSuc);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo cargar el inventario."
      );
    } finally {
      setCargando(false);
    }
  }, [busqueda, filtroSucursal, filtroEstado]);

  useEffect(() => {
    const t = setTimeout(() => {
      void cargarTodo();
    }, 200);
    return () => clearTimeout(t);
  }, [cargarTodo]);

  const buscarTrazabilidad = async (serialParam?: string) => {
    const objetivo = (serialParam ?? serialBuscar).trim();
    if (!objetivo) return;
    setError(null);
    setBuscandoTraz(true);
    setPestana("trazabilidad");
    setSerialBuscar(objetivo.toUpperCase());
    try {
      const resp = await solicitarApi<TrazabilidadEquipo>(
        `/api/logistica/trazabilidad/${encodeURIComponent(objetivo)}`
      );
      setTrazabilidad(resp);
    } catch (err) {
      setTrazabilidad(null);
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se encontró el serial indicado."
      );
    } finally {
      setBuscandoTraz(false);
    }
  };

  const manejarCrearAjuste = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setExito(null);
    try {
      await solicitarApi("/api/logistica/ajustes", {
        method: "POST",
        body: JSON.stringify({
          sucursal_id: Number(sucursalAjuste),
          tipo: tipoAjuste,
          equipo_id: equipoAjuste ? Number(equipoAjuste) : null,
          cantidad: 1,
          motivo: motivoAjuste.trim(),
        }),
      });
      setModalAjuste(false);
      setMotivoAjuste("");
      setExito("Solicitud de ajuste creada (PENDIENTE de aprobación por Dirección).");
      await cargarTodo();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo solicitar el ajuste."
      );
    }
  };

  const revisarAjuste = async (
    id: number,
    decision: "APROBADO" | "RECHAZADO"
  ) => {
    setError(null);
    setExito(null);
    try {
      await solicitarApi(`/api/logistica/ajustes/${id}/revisar`, {
        method: "PATCH",
        body: JSON.stringify({ decision }),
      });
      setExito(`Ajuste marcado como ${decision}.`);
      await cargarTodo();
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "No se pudo revisar el ajuste."
      );
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900">
            Inventario, Kardex, Trazabilidad y Ajustes
          </h2>
          <p className="text-sm text-slate-500">
            Stock por serial, Kardex de componentes y aprobaciones de Dirección.
          </p>
        </div>

        {puedeSolicitarAjuste && (
          <button
            type="button"
            onClick={() => setModalAjuste(true)}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            Solicitar ajuste
          </button>
        )}
      </div>

      {/* Lista de precios exportable (solo LISTO, sin costos) */}
      <BarraListaPrecios sucursalInicialId={filtroSucursal} />

      <PanelImportacionMasiva
        flujoInicial="cambio_estado"
        alCompletar={() => void cargarTodo()}
      />

      {/* Pestañas */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-2">
        {[
          { id: "equipos", label: `Equipos por Serial (${equipos.length})` },
          { id: "kardex", label: "Kardex por SKU" },
          { id: "trazabilidad", label: "Trazabilidad" },
          {
            id: "ajustes",
            label: `Ajustes (${ajustes.filter((a) => a.estado === "PENDIENTE").length} pendientes)`,
          },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() =>
              setPestana(
                tab.id as "equipos" | "kardex" | "trazabilidad" | "ajustes"
              )
            }
            className={`px-4 py-2 rounded-xl text-sm font-bold cursor-pointer ${
              pestana === tab.id
                ? "bg-[#E85A28] text-white"
                : "bg-white border border-slate-200 text-slate-700"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="flex items-center gap-2.5 p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}
      {exito && (
        <div className="flex items-center gap-2.5 p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-sm text-emerald-700">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{exito}</span>
        </div>
      )}

      {/* Pestaña 1: Equipos por serial */}
      {pestana === "equipos" && (
        <div className="space-y-4">
          <div className="bg-white p-4 rounded-2xl border border-slate-200 grid grid-cols-1 md:grid-cols-4 gap-3">
            <div className="md:col-span-2 relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
                placeholder="Buscar por serial, modelo o configuración..."
                className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-300 text-sm"
              />
            </div>
            <select
              value={filtroSucursal}
              onChange={(e) => setFiltroSucursal(e.target.value)}
              className="px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
            >
              <option value="">Todas las sucursales</option>
              {sucursales.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nombre}
                </option>
              ))}
            </select>
            <select
              value={filtroEstado}
              onChange={(e) => setFiltroEstado(e.target.value)}
              className="px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
            >
              <option value="">Todos los estados</option>
              {ESTADOS_EQUIPO.map((e) => (
                <option key={e} value={e}>
                  {e}
                </option>
              ))}
            </select>
          </div>

          {seleccionadosIds.length > 0 && (
            <div className="bg-[#FDF0EB] border border-[#E85A28]/30 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs font-black text-[#191818]">
                {seleccionadosIds.length} equipo(s) seleccionado(s) para cambio de estado masivo
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={estadoMasivo}
                  onChange={(e) => setEstadoMasivo(e.target.value as EstadoEquipo)}
                  className="px-3 py-1.5 rounded-xl border border-neutral-200 bg-white text-xs font-bold"
                >
                  {ESTADOS_EDITABLES.map((est) => (
                    <option key={est} value={est}>
                      {est}
                    </option>
                  ))}
                </select>
                <input
                  type="text"
                  value={motivoMasivo}
                  onChange={(e) => setMotivoMasivo(e.target.value)}
                  placeholder="Motivo (opcional)..."
                  className="px-3 py-1.5 rounded-xl border border-neutral-200 bg-white text-xs"
                />
                <button
                  type="button"
                  disabled={aplicandoMasivo}
                  onClick={() => void aplicarEstadoMasivo()}
                  className="px-3.5 py-1.5 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] text-white text-xs font-bold cursor-pointer disabled:opacity-50"
                >
                  {aplicandoMasivo ? "Aplicando..." : "Aplicar Estado"}
                </button>
              </div>
            </div>
          )}

          <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
            {cargando ? (
              <div className="p-6 space-y-3">
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="h-12 rounded-xl bg-slate-100 animate-pulse"
                  />
                ))}
              </div>
            ) : equipos.length === 0 ? (
              <div className="p-10 text-center space-y-2">
                <Boxes className="w-10 h-10 text-slate-300 mx-auto" />
                <p className="text-sm font-semibold text-slate-600">
                  No hay equipos registrados con los filtros seleccionados.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                    <tr>
                      <th className="px-3 py-3 w-8">Sel.</th>
                      <th className="px-4 py-3">Serial</th>
                      <th className="px-4 py-3">Modelo</th>
                      <th className="px-4 py-3">Ubicación</th>
                      <th className="px-4 py-3">Estado</th>
                      <th className="px-4 py-3 text-right">Promo USD</th>
                      {verCostos && (
                        <>
                          <th className="px-4 py-3 text-right">Compra</th>
                          <th className="px-4 py-3 text-right">Flete</th>
                          <th className="px-4 py-3 text-right">Costo Total</th>
                        </>
                      )}
                      <th className="px-4 py-3 text-right">Vida</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {equipos.map((eq) => (
                      <tr key={eq.id} className="hover:bg-slate-50">
                        <td className="px-3 py-3">
                          {eq.estado !== "VENDIDO" && (
                            <input
                              type="checkbox"
                              checked={seleccionadosIds.includes(eq.id)}
                              onChange={() => alternarSeleccion(eq.id)}
                              aria-label={`Seleccionar ${eq.serial}`}
                              className="rounded border-neutral-300"
                            />
                          )}
                        </td>
                        <td className="px-4 py-3 font-mono font-bold text-slate-900">
                          <div>{eq.serial}</div>
                          {eq.es_consignacion && (
                            <span className="inline-block mt-0.5 px-1.5 py-0.5 rounded bg-violet-100 text-violet-800 text-[10px] font-sans font-bold">
                              CONSIGNACIÓN
                              {verCostos && eq.proveedor_consignacion
                                ? ` · ${eq.proveedor_consignacion}`
                                : ""}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <p className="font-semibold">{eq.modelo || "—"}</p>
                          <p className="text-xs text-slate-500">
                            {eq.configuracion}
                          </p>
                        </td>
                        <td className="px-4 py-3">{eq.ubicacion}</td>
                        <td className="px-4 py-3">
                          {eq.estado === "VENDIDO" || usuario?.rol === "ASESORA" ? (
                            <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-slate-100 text-slate-800">
                              {eq.estado}
                            </span>
                          ) : (
                            <select
                              aria-label={`Cambiar estado de ${eq.serial}`}
                              value={eq.estado}
                              disabled={actualizandoEquipoId === eq.id}
                              onChange={(e) =>
                                void cambiarEstadoIndividual(
                                  eq,
                                  e.target.value as EstadoEquipo
                                )
                              }
                              className="px-2.5 py-1 rounded-lg border border-slate-200 bg-white text-xs font-bold text-slate-800 cursor-pointer disabled:opacity-50"
                            >
                              {ESTADOS_EDITABLES.map((est) => (
                                <option key={est} value={est}>
                                  {est}
                                </option>
                              ))}
                            </select>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right font-bold text-emerald-700">
                          {formatearUsd(eq.precio_promo_usd)}
                        </td>
                        {verCostos && (
                          <>
                            <td className="px-4 py-3 text-right text-slate-600">
                              {formatearUsd(eq.costo_compra_usd)}
                            </td>
                            <td className="px-4 py-3 text-right text-slate-600">
                              {formatearUsd(eq.costo_flete_usd)}
                            </td>
                            <td className="px-4 py-3 text-right font-bold text-slate-900">
                              {formatearUsd(eq.costo_total_usd)}
                            </td>
                          </>
                        )}
                        <td className="px-4 py-3 text-right">
                          <button
                            type="button"
                            onClick={() => void buscarTrazabilidad(eq.serial)}
                            className="text-xs font-bold text-[#E85A28] hover:underline cursor-pointer"
                          >
                            Ver línea de tiempo
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
      )}

      {/* Pestaña 2: Kardex por SKU */}
      {pestana === "kardex" && (
        <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
          {!kardex || kardex.saldos.length === 0 ? (
            <div className="p-10 text-center text-sm text-slate-500">
              No hay saldos de componentes/accesorios registrados todavía.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-3">SKU</th>
                    <th className="px-4 py-3">Descripción</th>
                    <th className="px-4 py-3">Sucursal</th>
                    <th className="px-4 py-3 text-right">Stock actual</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {kardex.saldos.map((s) => (
                    <tr key={`${s.articulo_id}-${s.sucursal_id}`}>
                      <td className="px-4 py-3 font-mono font-bold">{s.sku}</td>
                      <td className="px-4 py-3">{s.descripcion}</td>
                      <td className="px-4 py-3">{s.sucursal}</td>
                      <td className="px-4 py-3 text-right font-black">
                        {s.stock_actual}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Pestaña 3: Trazabilidad por Serial */}
      {pestana === "trazabilidad" && (
        <div className="space-y-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void buscarTrazabilidad();
            }}
            className="bg-white p-4 rounded-2xl border border-slate-200 flex gap-2"
          >
            <input
              type="text"
              value={serialBuscar}
              onChange={(e) => setSerialBuscar(e.target.value)}
              placeholder="Ingresa el número de serial exacto..."
              className="flex-1 px-3 py-2 rounded-xl border border-slate-300 text-sm font-mono"
            />
            <button
              type="submit"
              disabled={buscandoTraz}
              className="px-5 py-2 rounded-xl bg-[#E85A28] text-white text-sm font-bold cursor-pointer"
            >
              {buscandoTraz ? "Buscando..." : "Rastrear"}
            </button>
          </form>

          {trazabilidad && (
            <div className="bg-white rounded-2xl border border-slate-200 p-6 space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4">
                <div>
                  <p className="text-xs font-mono font-bold text-[#E85A28]">
                    {trazabilidad.equipo.serial}
                  </p>
                  <h3 className="text-lg font-black text-slate-900">
                    {trazabilidad.equipo.modelo || "Equipo"} ·{" "}
                    {trazabilidad.equipo.ubicacion}
                  </h3>
                </div>
                <span className="px-3 py-1 rounded-full bg-orange-100 text-[#C9461A] text-xs font-black">
                  {trazabilidad.equipo.estado}
                </span>
              </div>

              <div className="space-y-3">
                {trazabilidad.linea_tiempo.length === 0 ? (
                  <p className="text-xs text-slate-500">
                    Sin movimientos registrados aún.
                  </p>
                ) : (
                  trazabilidad.linea_tiempo.map((ev, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-3 p-3 rounded-xl bg-slate-50 border border-slate-200"
                    >
                      <Clock className="w-4 h-4 text-[#E85A28] mt-0.5 shrink-0" />
                      <div className="text-xs space-y-0.5">
                        <p className="font-bold text-slate-900">
                          {ev.tipo} · {ev.sucursal}{" "}
                          {ev.documento_ref ? `(${ev.documento_ref})` : ""}
                        </p>
                        <p className="text-slate-600">{ev.motivo}</p>
                        <p className="text-[11px] text-slate-400">
                          {ev.fecha.slice(0, 19).replace("T", " ")} ·{" "}
                          {ev.usuario || "Sistema"}
                        </p>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Pestaña 4: Ajustes */}
      {pestana === "ajustes" && (
        <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
          {ajustes.length === 0 ? (
            <div className="p-10 text-center text-sm text-slate-500">
              No hay solicitudes de ajuste registradas.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-3">Ajuste</th>
                    <th className="px-4 py-3">Tipo / Ítem</th>
                    <th className="px-4 py-3">Motivo</th>
                    <th className="px-4 py-3">Estado</th>
                    <th className="px-4 py-3 text-right">Revisión Dirección</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {ajustes.map((a) => (
                    <tr key={a.id}>
                      <td className="px-4 py-3">
                        <p className="font-mono font-bold">{a.numero_ajuste}</p>
                        <p className="text-xs text-slate-500">
                          Por: {a.solicitado_por}
                        </p>
                      </td>
                      <td className="px-4 py-3 text-xs">
                        <span className="font-bold">{a.tipo}</span> ·{" "}
                        {a.serial || a.sku}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-600">
                        {a.motivo}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                            a.estado === "APROBADO"
                              ? "bg-emerald-50 text-emerald-700"
                              : a.estado === "RECHAZADO"
                              ? "bg-red-50 text-red-700"
                              : "bg-amber-50 text-amber-800"
                          }`}
                        >
                          {a.estado}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right space-x-2">
                        {esDireccion && a.estado === "PENDIENTE" ? (
                          <>
                            <button
                              type="button"
                              onClick={() =>
                                void revisarAjuste(a.id, "APROBADO")
                              }
                              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-bold cursor-pointer"
                            >
                              <ShieldCheck className="w-3.5 h-3.5" />
                              Aprobar
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                void revisarAjuste(a.id, "RECHAZADO")
                              }
                              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-red-300 text-red-700 text-xs font-bold cursor-pointer"
                            >
                              <XCircle className="w-3.5 h-3.5" />
                              Rechazar
                            </button>
                          </>
                        ) : (
                          <span className="text-xs text-slate-400">
                            {a.revisado_por || "Esperando Dirección"}
                          </span>
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

      {/* Modal solicitar ajuste */}
      {modalAjuste && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4">
            <h3 className="text-lg font-black text-slate-900">
              Solicitar ajuste de inventario
            </h3>
            <form onSubmit={manejarCrearAjuste} className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Sucursal
                </label>
                <select
                  required
                  value={sucursalAjuste}
                  onChange={(e) => setSucursalAjuste(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                >
                  <option value="">Seleccionar...</option>
                  {sucursales.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.nombre}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Tipo de ajuste
                </label>
                <select
                  value={tipoAjuste}
                  onChange={(e) => setTipoAjuste(e.target.value as TipoAjuste)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                >
                  <option value="BAJA_EQUIPO">BAJA_EQUIPO (Cementerio)</option>
                  <option value="CORRECCION_MAS">CORRECCION_MAS</option>
                  <option value="CORRECCION_MENOS">CORRECCION_MENOS</option>
                </select>
              </div>
              {tipoAjuste === "BAJA_EQUIPO" && (
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Equipo
                  </label>
                  <select
                    required
                    value={equipoAjuste}
                    onChange={(e) => setEquipoAjuste(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                  >
                    <option value="">Seleccionar serial...</option>
                    {equipos
                      .filter((e) => e.estado !== "CEMENTERIO")
                      .map((e) => (
                        <option key={e.id} value={e.id}>
                          {e.serial} — {e.modelo}
                        </option>
                      ))}
                  </select>
                </div>
              )}
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Motivo obligatorio
                </label>
                <input
                  type="text"
                  required
                  minLength={3}
                  value={motivoAjuste}
                  onChange={(e) => setMotivoAjuste(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setModalAjuste(false)}
                  className="px-4 py-2 rounded-xl border border-slate-300 text-sm font-semibold cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-xl bg-[#E85A28] text-white text-sm font-bold cursor-pointer"
                >
                  Enviar a Dirección
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
