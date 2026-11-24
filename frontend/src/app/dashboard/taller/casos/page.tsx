"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Copy,
  FileText,
  Plus,
  Wrench,
} from "lucide-react";
import BuscadorTabla from "@/componentes/BuscadorTabla";
import { ErrorApi, formatearUsd, solicitarApi } from "@/servicios/api";
import type { Sucursal } from "@/tipos/dominio";
import type { CasoPostventa, EstadoCaso, TipoCaso } from "@/tipos/taller";

const ESTADOS_CASO: EstadoCaso[] = [
  "RECIBIDO",
  "EN_DIAGNOSTICO",
  "ESPERANDO_PRESUPUESTO",
  "ESPERANDO_APROBACION",
  "AUTORIZADO",
  "ESPERANDO_REPUESTO",
  "TERMINADO",
  "LISTO_PARA_ENTREGAR",
  "ENTREGADO",
  "RECHAZADO",
];

export default function PaginaCasosTaller() {
  const [casos, setCasos] = useState<CasoPostventa[]>([]);
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  const [filtroTipo, setFiltroTipo] = useState("");
  const [filtroEstado, setFiltroEstado] = useState("");
  const [busqueda, setBusqueda] = useState("");

  // Modal nuevo caso
  const [modalCrear, setModalCrear] = useState(false);
  const [tipoCaso, setTipoCaso] = useState<TipoCaso>("SERVICIO");
  const [sucursalId, setSucursalId] = useState("");
  const [serialCodigo, setSerialCodigo] = useState("");
  const [descripcionEquipo, setDescripcionEquipo] = useState("");
  const [accesorios, setAccesorios] = useState("");
  const [estadoFisico, setEstadoFisico] = useState("");
  const [claveEquipo, setClaveEquipo] = useState("");
  const [falla, setFalla] = useState("");
  const [guardando, setGuardando] = useState(false);

  // Modal presupuesto ST (con texto WhatsApp)
  const [casoPresupuesto, setCasoPresupuesto] = useState<CasoPostventa | null>(
    null
  );
  const [manoObra, setManoObra] = useState("25");
  const [repuestoDesc, setRepuestoDesc] = useState("");
  const [repuestoPrecio, setRepuestoPrecio] = useState("");

  // Modal actualizar caso
  const [casoEditar, setCasoEditar] = useState<CasoPostventa | null>(null);
  const [diagnostico, setDiagnostico] = useState("");
  const [trabajo, setTrabajo] = useState("");
  const [estadoNuevo, setEstadoNuevo] = useState<EstadoCaso>("EN_DIAGNOSTICO");

  const cargarDatos = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (filtroTipo) params.set("tipo", filtroTipo);
      if (filtroEstado) params.set("estado", filtroEstado);
      const qs = params.toString() ? `?${params.toString()}` : "";

      const [respCasos, respSuc] = await Promise.all([
        solicitarApi<CasoPostventa[]>(`/api/taller/casos${qs}`),
        solicitarApi<Sucursal[]>("/api/sucursales"),
      ]);
      setCasos(respCasos);
      setSucursales(respSuc);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudieron cargar los casos de taller."
      );
    } finally {
      setCargando(false);
    }
  }, [filtroTipo, filtroEstado]);

  useEffect(() => {
    void cargarDatos();
  }, [cargarDatos]);

  const manejarCrearCaso = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setExito(null);
    setGuardando(true);
    try {
      await solicitarApi("/api/taller/casos", {
        method: "POST",
        body: JSON.stringify({
          tipo: tipoCaso,
          sucursal_id: Number(sucursalId),
          serial_o_codigo: serialCodigo.trim(),
          descripcion_equipo: descripcionEquipo.trim(),
          accesorios_recibidos: accesorios.trim(),
          estado_fisico: estadoFisico.trim(),
          clave_equipo: claveEquipo.trim(),
          falla_reportada: falla.trim(),
        }),
      });
      setModalCrear(false);
      setSerialCodigo("");
      setDescripcionEquipo("");
      setAccesorios("");
      setEstadoFisico("");
      setClaveEquipo("");
      setFalla("");
      setExito("Caso registrado correctamente en estado RECIBIDO.");
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "No se pudo crear el caso."
      );
    } finally {
      setGuardando(false);
    }
  };

  const manejarEnviarPresupuesto = async (
    e: React.FormEvent<HTMLFormElement>
  ) => {
    e.preventDefault();
    if (!casoPresupuesto) return;
    setError(null);
    setExito(null);
    setGuardando(true);
    try {
      const repuestos =
        repuestoDesc.trim() !== ""
          ? [
              {
                descripcion: repuestoDesc.trim(),
                cantidad: 1,
                precio_promo_usd: Number(repuestoPrecio || 0),
              },
            ]
          : [];

      await solicitarApi(`/api/taller/casos/${casoPresupuesto.id}/presupuesto`, {
        method: "POST",
        body: JSON.stringify({
          mano_obra_usd: Number(manoObra || 0),
          repuestos,
        }),
      });
      setCasoPresupuesto(null);
      setRepuestoDesc("");
      setRepuestoPrecio("");
      setExito("Presupuesto registrado. Caso en ESPERANDO_APROBACION.");
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo guardar el presupuesto."
      );
    } finally {
      setGuardando(false);
    }
  };

  const registrarAprobacion = async (casoId: number, aprobado: boolean) => {
    setError(null);
    setExito(null);
    try {
      await solicitarApi(`/api/taller/casos/${casoId}/aprobar-presupuesto`, {
        method: "PATCH",
        body: JSON.stringify({
          aprobado,
          nota_cliente: aprobado
            ? "Aprobado por cliente"
            : "Cliente rechazó presupuesto",
        }),
      });
      setExito(
        aprobado
          ? "Presupuesto aprobado → Caso AUTORIZADO."
          : "Presupuesto rechazado → Caso LISTO_PARA_ENTREGAR (sin reparar)."
      );
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo registrar la decisión del cliente."
      );
    }
  };

  const manejarActualizarCaso = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!casoEditar) return;
    setError(null);
    setExito(null);
    setGuardando(true);
    try {
      await solicitarApi(`/api/taller/casos/${casoEditar.id}/actualizar`, {
        method: "PATCH",
        body: JSON.stringify({
          diagnostico: diagnostico.trim(),
          trabajo_realizado: trabajo.trim(),
          resultado_estado: estadoNuevo,
        }),
      });
      setCasoEditar(null);
      setExito("Caso actualizado correctamente.");
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo actualizar el caso."
      );
    } finally {
      setGuardando(false);
    }
  };

  const copiarPresupuestoWhatsApp = (caso: CasoPostventa) => {
    const total =
      Number(manoObra || 0) +
      (repuestoDesc.trim() ? Number(repuestoPrecio || 0) : 0);
    const texto = [
      `*TEKIO ELECTRONICS · Presupuesto ${caso.numero_caso}*`,
      `Equipo: ${caso.descripcion_equipo}`,
      `Mano de obra: ${formatearUsd(Number(manoObra || 0))}`,
      repuestoDesc.trim()
        ? `Repuesto (${repuestoDesc.trim()}): ${formatearUsd(Number(repuestoPrecio || 0))}`
        : null,
      `*Total Promo USD:* ${formatearUsd(total)}`,
      `Responde *APROBADO* para autorizar la reparación.`,
    ]
      .filter(Boolean)
      .join("\n");
    void navigator.clipboard?.writeText(texto);
    setExito("Texto del presupuesto copiado para WhatsApp.");
  };

  const casosFiltrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return casos;
    return casos.filter((c) =>
      [
        c.numero_caso,
        c.tipo,
        c.serial_o_codigo || "",
        c.descripcion_equipo || "",
        c.cliente || "",
        c.falla_reportada || "",
        c.estado,
        c.tecnico || "",
      ]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [casos, busqueda]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900">
            Casos de Garantía (GT) y Servicio Técnico (ST)
          </h2>
          <p className="text-sm text-slate-500">
            Seguimiento de diagnóstico, presupuestos aprobados por cliente y
            control de 180 días de garantía.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setModalCrear(true)}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold cursor-pointer"
        >
          <Plus className="w-4 h-4" />
          Nuevo caso GT / ST
        </button>
      </div>

      {/* Filtros */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200 flex flex-wrap gap-3 items-center">
        <BuscadorTabla
          valor={busqueda}
          alCambiar={setBusqueda}
          placeholder="Buscar por nro. de caso (GT/ST), serial, equipo, cliente, falla o técnico..."
          totalRegistros={casos.length}
          totalFiltrados={casosFiltrados.length}
        />
        <select
          value={filtroTipo}
          onChange={(e) => setFiltroTipo(e.target.value)}
          className="px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
        >
          <option value="">Todos los tipos</option>
          <option value="GARANTIA">Garantía (GT)</option>
          <option value="SERVICIO">Servicio Técnico (ST)</option>
        </select>

        <select
          value={filtroEstado}
          onChange={(e) => setFiltroEstado(e.target.value)}
          className="px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
        >
          <option value="">Todos los estados</option>
          {ESTADOS_CASO.map((e) => (
            <option key={e} value={e}>
              {e}
            </option>
          ))}
        </select>
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

      {/* Lista de casos */}
      {cargando ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 rounded-2xl bg-slate-200 animate-pulse" />
          ))}
        </div>
      ) : casosFiltrados.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-10 text-center space-y-2">
          <ClipboardList className="w-10 h-10 text-slate-300 mx-auto" />
          <p className="text-sm font-semibold text-slate-600">
            No hay casos registrados que coincidan con la búsqueda.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {casosFiltrados.map((c) => (
            <div
              key={c.id}
              className="bg-white rounded-2xl border border-slate-200 p-5 space-y-3"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono font-black text-slate-900">
                      {c.numero_caso}
                    </span>
                    <span className="px-2 py-0.5 rounded-md bg-orange-100 text-[#C9461A] text-xs font-bold">
                      {c.estado}
                    </span>
                    <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 text-xs font-bold">
                      {c.dias_abiertos} días abiertos
                    </span>
                  </div>
                  <p className="text-sm font-bold text-slate-800 mt-1">
                    {c.descripcion_equipo}{" "}
                    {c.serial_o_codigo ? `· Serial: ${c.serial_o_codigo}` : ""}
                  </p>
                  <p className="text-xs text-slate-600 mt-0.5">
                    Falla: {c.falla_reportada} · Sucursal: {c.sucursal}
                  </p>
                </div>

                <div className="flex flex-wrap gap-2">
                  {c.tipo === "SERVICIO" && (
                    <button
                      type="button"
                      onClick={() => {
                        setCasoPresupuesto(c);
                        setManoObra(
                          c.presupuesto
                            ? String(c.presupuesto.mano_obra_usd)
                            : "25"
                        );
                      }}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-sky-600 text-white text-xs font-bold cursor-pointer"
                    >
                      <FileText className="w-3.5 h-3.5" />
                      Enviar presupuesto
                    </button>
                  )}

                  {c.tipo === "SERVICIO" &&
                    c.presupuesto &&
                    c.presupuesto.aprobado_cliente === null && (
                      <>
                        <button
                          type="button"
                          onClick={() => void registrarAprobacion(c.id, true)}
                          className="px-3 py-1.5 rounded-xl bg-emerald-600 text-white text-xs font-bold cursor-pointer"
                        >
                          Aprobar presupuesto
                        </button>
                        <button
                          type="button"
                          onClick={() => void registrarAprobacion(c.id, false)}
                          className="px-3 py-1.5 rounded-xl border border-red-300 text-red-700 text-xs font-bold cursor-pointer"
                        >
                          Rechazar
                        </button>
                      </>
                    )}

                  <button
                    type="button"
                    onClick={() => {
                      setCasoEditar(c);
                      setDiagnostico(c.diagnostico);
                      setTrabajo(c.trabajo_realizado);
                      setEstadoNuevo(c.estado);
                    }}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-300 text-xs font-bold hover:bg-slate-50 cursor-pointer"
                  >
                    <Wrench className="w-3.5 h-3.5 text-[#E85A28]" />
                    Actualizar caso
                  </button>
                </div>
              </div>

              {c.alerta_garantia && (
                <div className="flex items-center gap-2 p-2.5 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-800 font-semibold">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>{c.alerta_garantia}</span>
                </div>
              )}

              {c.presupuesto && (
                <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs flex flex-wrap gap-4">
                  <span>
                    Mano de obra:{" "}
                    <strong>{formatearUsd(c.presupuesto.mano_obra_usd)}</strong>
                  </span>
                  <span>
                    Total Promo:{" "}
                    <strong className="text-emerald-700">
                      {formatearUsd(c.presupuesto.total_promo_usd)}
                    </strong>
                  </span>
                  <span>
                    Decisión cliente:{" "}
                    <strong>
                      {c.presupuesto.aprobado_cliente === true
                        ? "APROBADO"
                        : c.presupuesto.aprobado_cliente === false
                        ? "RECHAZADO"
                        : "PENDIENTE"}
                    </strong>
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Modal nuevo caso */}
      {modalCrear && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl space-y-4">
            <h3 className="text-lg font-black text-slate-900">
              Recepción de caso GT / ST
            </h3>
            <form onSubmit={manejarCrearCaso} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Tipo de caso
                  </label>
                  <select
                    value={tipoCaso}
                    onChange={(e) => setTipoCaso(e.target.value as TipoCaso)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                  >
                    <option value="SERVICIO">Servicio Técnico (ST)</option>
                    <option value="GARANTIA">Garantía (GT)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Sucursal
                  </label>
                  <select
                    required
                    value={sucursalId}
                    onChange={(e) => setSucursalId(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                  >
                    <option value="">Seleccionar...</option>
                    {sucursales
                      .filter((s) => s.estado === "ACTIVA")
                      .map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.nombre}
                        </option>
                      ))}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Serial / Código
                  </label>
                  <input
                    type="text"
                    value={serialCodigo}
                    onChange={(e) => setSerialCodigo(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Clave del equipo
                  </label>
                  <input
                    type="text"
                    value={claveEquipo}
                    onChange={(e) => setClaveEquipo(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Descripción del equipo
                </label>
                <input
                  type="text"
                  required
                  value={descripcionEquipo}
                  onChange={(e) => setDescripcionEquipo(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Falla reportada
                </label>
                <textarea
                  required
                  rows={2}
                  value={falla}
                  onChange={(e) => setFalla(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setModalCrear(false)}
                  className="px-4 py-2 rounded-xl border border-slate-300 text-sm font-semibold cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={guardando}
                  className="px-4 py-2 rounded-xl bg-[#E85A28] text-white text-sm font-bold cursor-pointer"
                >
                  Registrar caso
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal presupuesto ST */}
      {casoPresupuesto && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4">
            <h3 className="text-lg font-black text-slate-900">
              Presupuesto · {casoPresupuesto.numero_caso}
            </h3>
            <form onSubmit={manejarEnviarPresupuesto} className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Mano de obra (USD)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  required
                  value={manoObra}
                  onChange={(e) => setManoObra(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>
              <div className="grid grid-cols-3 gap-2">
                <input
                  type="text"
                  placeholder="Repuesto (opcional)"
                  value={repuestoDesc}
                  onChange={(e) => setRepuestoDesc(e.target.value)}
                  className="col-span-2 px-3 py-2 rounded-xl border border-slate-300 text-xs"
                />
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder="Precio USD"
                  value={repuestoPrecio}
                  onChange={(e) => setRepuestoPrecio(e.target.value)}
                  className="px-3 py-2 rounded-xl border border-slate-300 text-xs"
                />
              </div>
              <div className="flex items-center justify-between pt-2">
                <button
                  type="button"
                  onClick={() => copiarPresupuestoWhatsApp(casoPresupuesto)}
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-emerald-300 text-emerald-700 text-xs font-bold cursor-pointer"
                >
                  <Copy className="w-3.5 h-3.5" />
                  Copiar WhatsApp
                </button>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setCasoPresupuesto(null)}
                    className="px-3 py-2 rounded-xl border border-slate-300 text-xs font-semibold cursor-pointer"
                  >
                    Cancelar
                  </button>
                  <button
                    type="submit"
                    disabled={guardando}
                    className="px-4 py-2 rounded-xl bg-[#E85A28] text-white text-xs font-bold cursor-pointer"
                  >
                    Guardar presupuesto
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal actualizar caso */}
      {casoEditar && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4">
            <h3 className="text-lg font-black text-slate-900">
              Actualizar {casoEditar.numero_caso}
            </h3>
            <form onSubmit={manejarActualizarCaso} className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Estado
                </label>
                <select
                  value={estadoNuevo}
                  onChange={(e) => setEstadoNuevo(e.target.value as EstadoCaso)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                >
                  {ESTADOS_CASO.map((e) => (
                    <option key={e} value={e}>
                      {e}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Diagnóstico técnico
                </label>
                <textarea
                  rows={2}
                  value={diagnostico}
                  onChange={(e) => setDiagnostico(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Trabajo realizado
                </label>
                <textarea
                  rows={2}
                  value={trabajo}
                  onChange={(e) => setTrabajo(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setCasoEditar(null)}
                  className="px-4 py-2 rounded-xl border border-slate-300 text-sm font-semibold cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={guardando}
                  className="px-4 py-2 rounded-xl bg-[#E85A28] text-white text-sm font-bold cursor-pointer"
                >
                  Guardar cambios
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
