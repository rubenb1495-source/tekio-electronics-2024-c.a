"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Copy,
  FileDown,
  Loader2,
  RotateCcw,
  ShieldAlert,
  Wrench,
} from "lucide-react";
import BuscadorTabla from "@/componentes/BuscadorTabla";
import { usarSesion } from "@/contexto/SesionContexto";
import {
  copiarTextoPortapapeles,
  formatearWhatsAppDevolucion,
} from "@/lib/whatsapp";
import {
  descargarPdfApi,
  ErrorApi,
  esRolAdministrativo,
  formatearUsd,
  puedeVerCostos,
  solicitarApi,
} from "@/servicios/api";
import type { ArticuloCatalogo, CatalogoPaginado } from "@/tipos/dominio";
import type { InstrumentoFinanciero, VentaResumen } from "@/tipos/finanzas";
import type { EquipoInventario } from "@/tipos/logistica";
import type {
  DevolucionGarantiaResumen,
  TipoResolucionDevolucion,
} from "@/tipos/operaciones";

const ESCENARIOS: {
  valor: TipoResolucionDevolucion;
  titulo: string;
  descripcion: string;
  soloAdmin?: boolean;
}[] = [
  {
    valor: "CAMBIO_IGUAL",
    titulo: "1. Cambio por Equipo Igual",
    descripcion: "Reemplaza el serial por otro LISTO del mismo modelo ($0.00).",
  },
  {
    valor: "GARANTIA_COMPONENTE",
    titulo: "2. Garantía de Componente",
    descripcion: "Abre caso GT en Taller y descuenta repuesto sin cargo al cliente.",
  },
  {
    valor: "CAMBIO_UPGRADE",
    titulo: "3. Cambio con Upgrade",
    descripcion: "Cliente sube a un equipo de mayor valor y paga la diferencia.",
  },
  {
    valor: "CAMBIO_DOWNGRADE",
    titulo: "4. Cambio con Downgrade",
    descripcion: "Cliente cambia por equipo más económico (Saldo a favor o reembolso).",
  },
  {
    valor: "REEMBOLSO_TOTAL",
    titulo: "5. Reembolso Total",
    descripcion: "Devuelve el equipo, registra egreso y marca venta DEVUELTA.",
    soloAdmin: true,
  },
];

export default function PaginaDevolucionesGarantias() {
  const { usuario } = usarSesion();
  const esAdmin = usuario ? esRolAdministrativo(usuario.rol) : false;
  const verCostos = usuario ? puedeVerCostos(usuario.rol) : false;

  const [devoluciones, setDevoluciones] = useState<DevolucionGarantiaResumen[]>([]);
  const [ventas, setVentas] = useState<VentaResumen[]>([]);
  const [equiposListos, setEquiposListos] = useState<EquipoInventario[]>([]);
  const [repuestos, setRepuestos] = useState<ArticuloCatalogo[]>([]);
  const [instrumentos, setInstrumentos] = useState<InstrumentoFinanciero[]>([]);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);
  const [busqueda, setBusqueda] = useState("");
  const [copiadoId, setCopiadoId] = useState<number | null>(null);

  // Estado del formulario guiado
  const [ventaId, setVentaId] = useState("");
  const [tipoResolucion, setTipoResolucion] =
    useState<TipoResolucionDevolucion>("CAMBIO_IGUAL");
  const [equipoOrigenId, setEquipoOrigenId] = useState("");
  const [equipoDestinoId, setEquipoDestinoId] = useState("");
  const [estadoReingreso, setEstadoReingreso] = useState<
    "POR_PREPARAR" | "HOSPITAL" | "LISTO"
  >("POR_PREPARAR");
  const [componenteAfectado, setComponenteAfectado] = useState("");
  const [articuloRepuestoId, setArticuloRepuestoId] = useState("");
  const [cantidadRepuesto, setCantidadRepuesto] = useState("1");
  const [instrumentoId, setInstrumentoId] = useState("");
  const [montoPagadoOrigen, setMontoPagadoOrigen] = useState("");
  const [referenciaPago, setReferenciaPago] = useState("");
  const [dejarSaldoFavor, setDejarSaldoFavor] = useState(true);
  const [motivo, setMotivo] = useState("");

  const cargarTodo = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [respDev, respVentas, respEq, respCat, respInst] = await Promise.all([
        solicitarApi<DevolucionGarantiaResumen[]>("/api/devoluciones-garantias"),
        solicitarApi<VentaResumen[]>("/api/ventas"),
        solicitarApi<EquipoInventario[]>("/api/logistica/inventario/equipos?estado=LISTO"),
        solicitarApi<CatalogoPaginado>("/api/catalogo?limite=200"),
        solicitarApi<InstrumentoFinanciero[]>("/api/finanzas/instrumentos"),
      ]);
      setDevoluciones(respDev);
      setVentas(
        respVentas.filter((v) => v.estado !== "ANULADA" && v.estado !== "DEVUELTA")
      );
      setEquiposListos(respEq);
      setRepuestos(
        respCat.elementos.filter(
          (a) => a.tipo === "COMPONENTE" || a.tipo === "ACCESORIO"
        )
      );
      setInstrumentos(respInst.filter((i) => i.activo !== false));
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudieron cargar los datos de devoluciones y garantías."
      );
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void cargarTodo();
  }, [cargarTodo]);

  // Preseleccionar venta si llega por ?venta_id=
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const vId = params.get("venta_id");
    if (vId) {
      setVentaId(vId);
    }
  }, []);

  const ventaSeleccionada = useMemo(
    () => ventas.find((v) => String(v.id) === ventaId) || null,
    [ventas, ventaId]
  );

  const equiposDeVenta = useMemo(() => {
    if (!ventaSeleccionada) return [];
    return ventaSeleccionada.detalles.filter((d) => d.equipo_id !== null);
  }, [ventaSeleccionada]);

  useEffect(() => {
    if (equiposDeVenta.length === 1 && equiposDeVenta[0].equipo_id) {
      setEquipoOrigenId(String(equiposDeVenta[0].equipo_id));
    } else if (equiposDeVenta.length === 0) {
      setEquipoOrigenId("");
    }
  }, [equiposDeVenta]);

  const manejarRegistrar = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setExito(null);

    if (!ventaId) {
      setError("Selecciona la venta original a procesar.");
      return;
    }
    if (motivo.trim().length < 3) {
      setError("Describe el motivo de la garantía, cambio o devolución.");
      return;
    }

    setGuardando(true);
    try {
      const payload: Record<string, unknown> = {
        venta_id: Number(ventaId),
        tipo_resolucion: tipoResolucion,
        estado_reingreso_origen: estadoReingreso,
        motivo: motivo.trim(),
      };
      if (equipoOrigenId) payload.equipo_origen_id = Number(equipoOrigenId);
      if (
        (tipoResolucion === "CAMBIO_IGUAL" ||
          tipoResolucion === "CAMBIO_UPGRADE" ||
          tipoResolucion === "CAMBIO_DOWNGRADE") &&
        equipoDestinoId
      ) {
        payload.equipo_destino_id = Number(equipoDestinoId);
      }
      if (tipoResolucion === "GARANTIA_COMPONENTE") {
        payload.componente_afectado = componenteAfectado.trim();
        if (articuloRepuestoId) {
          payload.articulo_repuesto_id = Number(articuloRepuestoId);
          payload.cantidad_repuesto = Number(cantidadRepuesto) || 1;
        }
      }
      if (tipoResolucion === "CAMBIO_DOWNGRADE") {
        payload.dejar_saldo_favor = esAdmin ? dejarSaldoFavor : true;
      }
      if (
        tipoResolucion === "CAMBIO_UPGRADE" ||
        tipoResolucion === "REEMBOLSO_TOTAL" ||
        (tipoResolucion === "CAMBIO_DOWNGRADE" && esAdmin && !dejarSaldoFavor)
      ) {
        if (instrumentoId) payload.instrumento_id = Number(instrumentoId);
        if (montoPagadoOrigen.trim() !== "") {
          payload.monto_pagado_origen = Number(montoPagadoOrigen);
        }
        payload.referencia_pago = referenciaPago.trim();
      }

      const res = await solicitarApi<DevolucionGarantiaResumen>(
        "/api/devoluciones-garantias",
        {
          method: "POST",
          body: JSON.stringify(payload),
        }
      );
      setExito(
        `Operación ${res.numero_operacion} registrada correctamente (${res.tipo_resolucion}).`
      );
      setMotivo("");
      setEquipoDestinoId("");
      setReferenciaPago("");
      setMontoPagadoOrigen("");
      setComponenteAfectado("");
      setArticuloRepuestoId("");
      await cargarTodo();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo registrar la operación."
      );
    } finally {
      setGuardando(false);
    }
  };

  const abrirPdf = async (dev: DevolucionGarantiaResumen) => {
    await descargarPdfApi(
      `/api/devoluciones-garantias/${dev.id}/pdf`,
      `Comprobante_${dev.numero_operacion}.pdf`
    );
  };

  const copiarWa = async (dev: DevolucionGarantiaResumen) => {
    const ok = await copiarTextoPortapapeles(formatearWhatsAppDevolucion(dev));
    if (ok) {
      setCopiadoId(dev.id);
      setTimeout(() => setCopiadoId(null), 2200);
    }
  };

  const filtradas = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return devoluciones;
    return devoluciones.filter((d) =>
      [
        d.numero_operacion,
        d.numero_venta,
        d.cliente,
        d.tipo_resolucion,
        d.equipo_origen_serial,
        d.equipo_destino_serial,
        d.caso_taller_numero,
        d.motivo,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [devoluciones, busqueda]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-black text-tekio-carbon flex items-center gap-2">
            <RotateCcw className="w-6 h-6 text-tekio-naranja" />
            Devoluciones, Cambios y Garantías
          </h2>
          <p className="text-sm text-neutral-500">
            Flujo guiado para cambios iguales, garantías de componentes, upgrades, downgrades y reembolsos totales.
          </p>
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

      {/* Formulario guiado */}
      <form
        onSubmit={manejarRegistrar}
        className="bg-white/75 backdrop-blur-md border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl p-5 space-y-5"
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-bold uppercase tracking-wide text-neutral-600 mb-1.5">
              1. Venta Original *
            </label>
            <select
              value={ventaId}
              onChange={(e) => setVentaId(e.target.value)}
              className="w-full rounded-xl border border-neutral-200 bg-white px-3 py-2.5 text-sm text-tekio-carbon"
              required
            >
              <option value="">Selecciona una venta...</option>
              {ventas.map((v) => (
                <option key={v.id} value={String(v.id)}>
                  {v.numero_venta} · {v.cliente} · {formatearUsd(v.total_promo_usd)} ({v.fecha})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wide text-neutral-600 mb-1.5">
              Equipo de la venta (Origen)
            </label>
            <select
              value={equipoOrigenId}
              onChange={(e) => setEquipoOrigenId(e.target.value)}
              className="w-full rounded-xl border border-neutral-200 bg-white px-3 py-2.5 text-sm text-tekio-carbon"
              disabled={!ventaSeleccionada || equiposDeVenta.length === 0}
            >
              <option value="">
                {equiposDeVenta.length === 0
                  ? "Sin seriales asociados"
                  : "Selecciona el equipo..."}
              </option>
              {equiposDeVenta.map((d) => (
                <option key={d.id} value={String(d.equipo_id || "")}>
                  {d.descripcion} · Serial: {d.serial} ({formatearUsd(d.precio_promo_usd)})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Selector visual de los 5 escenarios */}
        <div>
          <label className="block text-xs font-bold uppercase tracking-wide text-neutral-600 mb-2">
            2. Escenario de Resolución *
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2.5">
            {ESCENARIOS.map((esc) => {
              const bloqueado = Boolean(esc.soloAdmin && !esAdmin);
              const activo = tipoResolucion === esc.valor;
              return (
                <button
                  key={esc.valor}
                  type="button"
                  disabled={bloqueado}
                  onClick={() => setTipoResolucion(esc.valor)}
                  className={`text-left p-3 rounded-xl border transition-all ${
                    activo
                      ? "border-tekio-naranja bg-tekio-naranja-suave/70 shadow-sm"
                      : "border-neutral-200 bg-white/80 hover:border-neutral-300"
                  } ${bloqueado ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
                >
                  <p className="text-xs font-bold text-tekio-carbon flex items-center justify-between gap-1">
                    <span>{esc.titulo}</span>
                    {esc.soloAdmin && (
                      <ShieldAlert className="w-3.5 h-3.5 text-tekio-naranja shrink-0" />
                    )}
                  </p>
                  <p className="text-[11px] text-neutral-500 mt-1 leading-snug">
                    {esc.descripcion}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Campos dinámicos según escenario */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-1">
          {tipoResolucion !== "GARANTIA_COMPONENTE" && (
            <div>
              <label className="block text-xs font-bold text-neutral-600 mb-1">
                Estado de reingreso del equipo original
              </label>
              <select
                value={estadoReingreso}
                onChange={(e) =>
                  setEstadoReingreso(
                    e.target.value as "POR_PREPARAR" | "HOSPITAL" | "LISTO"
                  )
                }
                className="w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm"
              >
                <option value="POR_PREPARAR">POR_PREPARAR (Revisión / Limpieza)</option>
                <option value="HOSPITAL">HOSPITAL (Falla técnica)</option>
                <option value="LISTO">LISTO (Intacto para venta)</option>
              </select>
            </div>
          )}

          {(tipoResolucion === "CAMBIO_IGUAL" ||
            tipoResolucion === "CAMBIO_UPGRADE" ||
            tipoResolucion === "CAMBIO_DOWNGRADE") && (
            <div className="md:col-span-2">
              <label className="block text-xs font-bold text-neutral-600 mb-1">
                Equipo de reemplazo (Serial en estado LISTO) *
              </label>
              <select
                value={equipoDestinoId}
                onChange={(e) => setEquipoDestinoId(e.target.value)}
                className="w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm"
                required
              >
                <option value="">Selecciona el serial LISTO a entregar...</option>
                {equiposListos.map((eq) => (
                  <option key={eq.id} value={String(eq.id)}>
                    {eq.modelo} · Serial: {eq.serial} · {eq.ubicacion || "Sucursal"}
                  </option>
                ))}
              </select>
            </div>
          )}

          {tipoResolucion === "GARANTIA_COMPONENTE" && (
            <>
              <div>
                <label className="block text-xs font-bold text-neutral-600 mb-1">
                  Componente afectado
                </label>
                <input
                  type="text"
                  value={componenteAfectado}
                  onChange={(e) => setComponenteAfectado(e.target.value)}
                  placeholder="Ej. Cargador, Teclado, Batería, SSD..."
                  className="w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-neutral-600 mb-1">
                  Descontar repuesto del stock (Opcional)
                </label>
                <select
                  value={articuloRepuestoId}
                  onChange={(e) => setArticuloRepuestoId(e.target.value)}
                  className="w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm"
                >
                  <option value="">Solo abrir caso GT en Taller</option>
                  {repuestos.map((r) => (
                    <option key={r.id} value={String(r.id)}>
                      {r.sku} · {r.descripcion}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-bold text-neutral-600 mb-1">
                  Cantidad repuesto
                </label>
                <input
                  type="number"
                  min={1}
                  value={cantidadRepuesto}
                  onChange={(e) => setCantidadRepuesto(e.target.value)}
                  className="w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm"
                />
              </div>
            </>
          )}

          {tipoResolucion === "CAMBIO_DOWNGRADE" && (
            <div className="md:col-span-3 flex flex-wrap items-center gap-4 rounded-xl bg-neutral-50 border border-neutral-200 px-4 py-3">
              <label className="inline-flex items-center gap-2 text-sm font-medium text-tekio-carbon cursor-pointer">
                <input
                  type="radio"
                  checked={dejarSaldoFavor || !esAdmin}
                  onChange={() => setDejarSaldoFavor(true)}
                />
                Acreditar diferencia como Saldo a Favor del cliente
              </label>
              {esAdmin && (
                <label className="inline-flex items-center gap-2 text-sm font-medium text-tekio-carbon cursor-pointer">
                  <input
                    type="radio"
                    checked={!dejarSaldoFavor}
                    onChange={() => setDejarSaldoFavor(false)}
                  />
                  Reembolsar dinero al cliente (Egreso de Caja/Banco)
                </label>
              )}
            </div>
          )}

          {(tipoResolucion === "CAMBIO_UPGRADE" ||
            tipoResolucion === "REEMBOLSO_TOTAL" ||
            (tipoResolucion === "CAMBIO_DOWNGRADE" && esAdmin && !dejarSaldoFavor)) && (
            <>
              <div>
                <label className="block text-xs font-bold text-neutral-600 mb-1">
                  Instrumento financiero *
                </label>
                <select
                  value={instrumentoId}
                  onChange={(e) => setInstrumentoId(e.target.value)}
                  className="w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm"
                  required
                >
                  <option value="">Selecciona caja o banco...</option>
                  {instrumentos.map((i) => (
                    <option key={i.id} value={String(i.id)}>
                      {i.nombre} ({i.moneda})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-bold text-neutral-600 mb-1">
                  Monto exacto (Opcional — auto-calculado si vacío)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min={0}
                  value={montoPagadoOrigen}
                  onChange={(e) => setMontoPagadoOrigen(e.target.value)}
                  placeholder="Automático según diferencia"
                  className="w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm tabular-nums"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-neutral-600 mb-1">
                  Referencia de pago / egreso
                </label>
                <input
                  type="text"
                  value={referenciaPago}
                  onChange={(e) => setReferenciaPago(e.target.value)}
                  placeholder="Nro. referencia bancaria o recibo"
                  className="w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm"
                />
              </div>
            </>
          )}
        </div>

        <div>
          <label className="block text-xs font-bold text-neutral-600 mb-1">
            Motivo / Observaciones *
          </label>
          <textarea
            rows={2}
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Describe el motivo del cambio, garantía o devolución..."
            className="w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm"
            required
          />
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={guardando}
            className="inline-flex items-center gap-2 rounded-xl bg-tekio-naranja hover:bg-tekio-naranja-hover text-white px-5 py-2.5 text-sm font-bold transition-colors disabled:opacity-60"
          >
            {guardando ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RotateCcw className="w-4 h-4" />
            )}
            Registrar Resolución
          </button>
        </div>
      </form>

      {/* Historial */}
      <div className="bg-white/75 backdrop-blur-md border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-base font-bold text-tekio-carbon">
            Historial de Devoluciones y Garantías ({filtradas.length})
          </h3>
          <div className="w-full sm:w-80">
            <BuscadorTabla
              valor={busqueda}
              alCambiar={setBusqueda}
              placeholder="Buscar por Nro, venta, cliente, serial o GT..."
            />
          </div>
        </div>

        {cargando ? (
          <p className="text-sm text-neutral-500 py-6 text-center">
            Cargando operaciones...
          </p>
        ) : filtradas.length === 0 ? (
          <p className="text-sm text-neutral-500 py-6 text-center">
            No hay devoluciones ni garantías registradas.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="border-b border-neutral-200 text-xs uppercase text-neutral-500">
                  <th className="py-2.5 px-3">Operación</th>
                  <th className="py-2.5 px-3">Venta / Cliente</th>
                  <th className="py-2.5 px-3">Resolución</th>
                  <th className="py-2.5 px-3">Equipos / Taller</th>
                  <th className="py-2.5 px-3 text-right">Diferencia</th>
                  {verCostos && (
                    <th className="py-2.5 px-3 text-right">Costo Gar.</th>
                  )}
                  <th className="py-2.5 px-3 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {filtradas.map((d) => (
                  <tr key={d.id} className="hover:bg-white/60">
                    <td className="py-3 px-3">
                      <p className="font-bold text-tekio-carbon">
                        {d.numero_operacion}
                      </p>
                      <p className="text-xs text-neutral-500">{d.fecha}</p>
                    </td>
                    <td className="py-3 px-3">
                      <p className="font-semibold text-tekio-carbon">
                        {d.numero_venta}
                      </p>
                      <p className="text-xs text-neutral-500">{d.cliente}</p>
                    </td>
                    <td className="py-3 px-3">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-tekio-naranja-suave text-tekio-naranja">
                        {d.tipo_resolucion}
                      </span>
                      <p className="text-xs text-neutral-500 mt-0.5 max-w-xs truncate">
                        {d.motivo}
                      </p>
                    </td>
                    <td className="py-3 px-3 text-xs space-y-0.5">
                      {d.equipo_origen_serial && (
                        <p>
                          <span className="text-neutral-400">Origen:</span>{" "}
                          <span className="font-mono font-semibold">
                            {d.equipo_origen_serial}
                          </span>{" "}
                          ({d.estado_reingreso_origen})
                        </p>
                      )}
                      {d.equipo_destino_serial && (
                        <p>
                          <span className="text-neutral-400">Nuevo:</span>{" "}
                          <span className="font-mono font-semibold text-emerald-700">
                            {d.equipo_destino_serial}
                          </span>
                        </p>
                      )}
                      {d.caso_taller_numero && (
                        <p className="inline-flex items-center gap-1 text-tekio-naranja font-semibold">
                          <Wrench className="w-3 h-3" /> {d.caso_taller_numero}
                        </p>
                      )}
                    </td>
                    <td className="py-3 px-3 text-right tabular-nums font-bold">
                      {formatearUsd(d.diferencia_usd)}
                      {d.dejar_saldo_favor && (
                        <span className="block text-[10px] font-medium text-emerald-700">
                          Saldo a favor
                        </span>
                      )}
                    </td>
                    {verCostos && (
                      <td className="py-3 px-3 text-right tabular-nums text-xs text-neutral-600">
                        {formatearUsd(d.costo_garantia_usd || 0)}
                      </td>
                    )}
                    <td className="py-3 px-3 text-right">
                      <div className="inline-flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => void abrirPdf(d)}
                          className="inline-flex items-center gap-1 rounded-lg border border-neutral-200 bg-white hover:bg-neutral-50 px-2.5 py-1.5 text-xs font-semibold text-tekio-carbon"
                          title="Descargar Comprobante PDF"
                        >
                          <FileDown className="w-3.5 h-3.5 text-tekio-naranja" />
                          PDF
                        </button>
                        <button
                          type="button"
                          onClick={() => void copiarWa(d)}
                          className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 px-2.5 py-1.5 text-xs font-semibold text-emerald-800"
                          title="Copiar resumen para WhatsApp"
                        >
                          {copiadoId === d.id ? (
                            <Check className="w-3.5 h-3.5" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                          WA
                        </button>
                      </div>
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
