"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  BellRing,
  CheckCircle2,
  Plus,
  Trash2,
  Wrench,
} from "lucide-react";
import { ErrorApi, solicitarApi } from "@/servicios/api";
import type { ArticuloCatalogo, CatalogoPaginado } from "@/tipos/dominio";
import type {
  EquipoColaTaller,
  ResultadoPreparacion,
  TipoPreparacion,
} from "@/tipos/taller";

interface ComponenteFila {
  articulo_id: string;
  cantidad: string;
}

interface RepuestoFaltanteFila {
  descripcion: string;
  cantidad: string;
}

export default function PaginaPreparaciones() {
  const [cola, setCola] = useState<EquipoColaTaller[]>([]);
  const [componentesCatalogo, setComponentesCatalogo] = useState<
    ArticuloCatalogo[]
  >([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  // Formulario de preparación
  const [equipoId, setEquipoId] = useState("");
  const [busquedaSerial, setBusquedaSerial] = useState("");
  const [tipo, setTipo] = useState<TipoPreparacion>("ESTANDAR");
  const [pagoEspecial, setPagoEspecial] = useState("");
  const [resultado, setResultado] = useState<ResultadoPreparacion>("LISTO");
  const [nota, setNota] = useState("");
  const [componentesUsados, setComponentesUsados] = useState<ComponenteFila[]>(
    []
  );
  const [repuestosFaltantes, setRepuestosFaltantes] = useState<
    RepuestoFaltanteFila[]
  >([{ descripcion: "", cantidad: "1" }]);
  const [guardando, setGuardando] = useState(false);

  const cargarDatos = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [respCola, respCat] = await Promise.all([
        solicitarApi<EquipoColaTaller[]>("/api/taller/cola"),
        solicitarApi<CatalogoPaginado>("/api/catalogo?tipo=COMPONENTE&por_pagina=100"),
      ]);
      setCola(respCola);
      setComponentesCatalogo(respCat.elementos);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo cargar la cola de taller."
      );
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void cargarDatos();
  }, [cargarDatos]);

  const porPreparar = cola.filter((e) => e.estado === "POR_PREPARAR");
  const enHospital = cola.filter((e) => e.estado === "HOSPITAL");
  const repuestosLlegaron = cola.filter((e) => e.repuesto_disponible);

  const colaFiltrada = busquedaSerial.trim()
    ? cola.filter(
        (e) =>
          e.serial.includes(busquedaSerial.trim().toUpperCase()) ||
          e.modelo.toLowerCase().includes(busquedaSerial.trim().toLowerCase())
      )
    : cola;

  const manejarRegistrar = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setExito(null);

    if (!equipoId) {
      setError("Selecciona un equipo de la cola.");
      return;
    }

    const compsValidos = componentesUsados
      .filter((c) => c.articulo_id !== "")
      .map((c) => ({
        articulo_id: Number(c.articulo_id),
        cantidad: Number(c.cantidad || 1),
      }));

    const faltantesValidos =
      resultado === "HOSPITAL"
        ? repuestosFaltantes
            .filter((r) => r.descripcion.trim() !== "")
            .map((r) => ({
              descripcion: r.descripcion.trim(),
              cantidad: Number(r.cantidad || 1),
            }))
        : [];

    setGuardando(true);
    try {
      await solicitarApi("/api/taller/preparaciones", {
        method: "POST",
        body: JSON.stringify({
          equipo_id: Number(equipoId),
          tipo,
          pago_tecnico_usd:
            tipo === "ESPECIAL" && pagoEspecial !== ""
              ? Number(pagoEspecial)
              : null,
          componentes_usados: compsValidos,
          resultado,
          repuestos_faltantes: faltantesValidos,
          nota: nota.trim(),
        }),
      });
      setExito("Preparación registrada correctamente.");
      setEquipoId("");
      setNota("");
      setComponentesUsados([]);
      setRepuestosFaltantes([{ descripcion: "", cantidad: "1" }]);
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "Error al registrar la preparación."
      );
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-black text-slate-900">
          Taller · Preparaciones por Serial
        </h2>
        <p className="text-sm text-slate-500">
          Atiende equipos por preparar, descuenta componentes de Bodega y
          reporta repuestos faltantes a Logística.
        </p>
      </div>

      {/* Tarjetas superiores */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white p-5 rounded-2xl border border-slate-200">
          <p className="text-xs font-bold uppercase text-slate-500">
            Por preparar
          </p>
          <p className="text-3xl font-black text-slate-900 mt-1">
            {porPreparar.length}
          </p>
        </div>
        <div className="bg-white p-5 rounded-2xl border border-amber-200">
          <p className="text-xs font-bold uppercase text-amber-700">
            En Hospital
          </p>
          <p className="text-3xl font-black text-amber-700 mt-1">
            {enHospital.length}
          </p>
        </div>
        <div className="bg-emerald-50 p-5 rounded-2xl border-2 border-emerald-300">
          <p className="text-xs font-bold uppercase text-emerald-800 flex items-center gap-1.5">
            <BellRing className="w-4 h-4" />
            Repuestos que llegaron
          </p>
          <p className="text-3xl font-black text-emerald-800 mt-1">
            {repuestosLlegaron.length}
          </p>
        </div>
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

      {/* Formulario de preparación */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4">
        <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
          <Wrench className="w-4 h-4 text-[#E85A28]" />
          Registrar preparación de equipo
        </h3>

        <form onSubmit={manejarRegistrar} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Filtrar serial en cola
              </label>
              <input
                type="text"
                value={busquedaSerial}
                onChange={(e) => setBusquedaSerial(e.target.value)}
                placeholder="Buscar serial..."
                className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm font-mono"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Equipo en cola ({colaFiltrada.length})
              </label>
              <select
                required
                value={equipoId}
                onChange={(e) => setEquipoId(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
              >
                <option value="">Seleccionar equipo...</option>
                {colaFiltrada.map((eq) => (
                  <option key={eq.id} value={eq.id}>
                    {eq.repuesto_disponible ? "🟢 [REPUESTO LLEGÓ] " : ""}
                    {eq.serial} — {eq.modelo || "Equipo"} ({eq.estado} ·{" "}
                    {eq.dias_en_taller}d)
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Tipo de preparación
              </label>
              <select
                value={tipo}
                onChange={(e) => setTipo(e.target.value as TipoPreparacion)}
                className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
              >
                <option value="ESTANDAR">ESTANDAR ($1.00)</option>
                <option value="ESPECIAL">ESPECIAL (monto personalizado)</option>
              </select>
            </div>

            {tipo === "ESPECIAL" && (
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Pago especial técnico (USD)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  required
                  value={pagoEspecial}
                  onChange={(e) => setPagoEspecial(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>
            )}

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Resultado
              </label>
              <select
                value={resultado}
                onChange={(e) =>
                  setResultado(e.target.value as ResultadoPreparacion)
                }
                className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
              >
                <option value="LISTO">LISTO (vendible)</option>
                <option value="HOSPITAL">HOSPITAL (esperando repuesto)</option>
                <option value="CEMENTERIO">CEMENTERIO (baja)</option>
              </select>
            </div>
          </div>

          {/* Componentes usados */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-xs font-bold uppercase text-slate-600">
                Componentes instalados (descuento automático en Bodega)
              </p>
              <button
                type="button"
                onClick={() =>
                  setComponentesUsados((prev) => [
                    ...prev,
                    { articulo_id: "", cantidad: "1" },
                  ])
                }
                className="inline-flex items-center gap-1 text-xs font-bold text-[#E85A28] cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                Agregar componente
              </button>
            </div>
            {componentesUsados.map((comp, idx) => (
              <div key={idx} className="flex gap-2 items-center">
                <select
                  value={comp.articulo_id}
                  onChange={(e) => {
                    const copia = [...componentesUsados];
                    copia[idx] = { ...copia[idx], articulo_id: e.target.value };
                    setComponentesUsados(copia);
                  }}
                  className="flex-1 px-3 py-2 rounded-xl border border-slate-300 text-xs bg-white"
                >
                  <option value="">Seleccionar componente...</option>
                  {componentesCatalogo.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.sku} — {c.descripcion}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  min="1"
                  value={comp.cantidad}
                  onChange={(e) => {
                    const copia = [...componentesUsados];
                    copia[idx] = { ...copia[idx], cantidad: e.target.value };
                    setComponentesUsados(copia);
                  }}
                  className="w-20 px-3 py-2 rounded-xl border border-slate-300 text-xs"
                />
                <button
                  type="button"
                  onClick={() =>
                    setComponentesUsados((prev) =>
                      prev.filter((_, i) => i !== idx)
                    )
                  }
                  className="p-2 text-red-600 hover:bg-red-50 rounded-lg cursor-pointer"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>

          {/* Repuestos faltantes si HOSPITAL */}
          {resultado === "HOSPITAL" && (
            <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-xs font-bold uppercase text-amber-800">
                  Repuestos que faltan (se enviará alerta automática a Logística)
                </p>
                <button
                  type="button"
                  onClick={() =>
                    setRepuestosFaltantes((prev) => [
                      ...prev,
                      { descripcion: "", cantidad: "1" },
                    ])
                  }
                  className="text-xs font-bold text-amber-900 cursor-pointer"
                >
                  + Otro repuesto
                </button>
              </div>
              {repuestosFaltantes.map((rep, idx) => (
                <div key={idx} className="flex gap-2">
                  <input
                    type="text"
                    placeholder="Ej: Pantalla 14 FHD 30 pines"
                    value={rep.descripcion}
                    onChange={(e) => {
                      const copia = [...repuestosFaltantes];
                      copia[idx] = { ...copia[idx], descripcion: e.target.value };
                      setRepuestosFaltantes(copia);
                    }}
                    className="flex-1 px-3 py-2 rounded-xl border border-amber-300 bg-white text-xs"
                  />
                  <input
                    type="number"
                    min="1"
                    value={rep.cantidad}
                    onChange={(e) => {
                      const copia = [...repuestosFaltantes];
                      copia[idx] = { ...copia[idx], cantidad: e.target.value };
                      setRepuestosFaltantes(copia);
                    }}
                    className="w-20 px-3 py-2 rounded-xl border border-amber-300 bg-white text-xs"
                  />
                </div>
              ))}
            </div>
          )}

          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">
              Nota técnica
            </label>
            <input
              type="text"
              value={nota}
              onChange={(e) => setNota(e.target.value)}
              placeholder="Ej: Cambio de pasta térmica, pruebas de batería OK"
              className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
            />
          </div>

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={guardando}
              className="px-5 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold disabled:opacity-60 cursor-pointer"
            >
              {guardando ? "Guardando..." : "Registrar preparación"}
            </button>
          </div>
        </form>
      </div>

      {/* Cola actual */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        {cargando ? (
          <div className="p-6 space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 rounded-xl bg-slate-100 animate-pulse" />
            ))}
          </div>
        ) : cola.length === 0 ? (
          <div className="p-10 text-center text-sm text-slate-500">
            No hay equipos pendientes en la cola de taller.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Serial</th>
                  <th className="px-4 py-3">Modelo</th>
                  <th className="px-4 py-3">Estado</th>
                  <th className="px-4 py-3">Días en taller</th>
                  <th className="px-4 py-3">Alertas</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {cola.map((eq) => (
                  <tr
                    key={eq.id}
                    className={
                      eq.repuesto_disponible ? "bg-emerald-50/70" : "hover:bg-slate-50"
                    }
                  >
                    <td className="px-4 py-3 font-mono font-bold">
                      {eq.serial}
                    </td>
                    <td className="px-4 py-3">{eq.modelo || "—"}</td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-slate-100">
                        {eq.estado}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-semibold">
                      {eq.dias_en_taller} días
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {eq.repuesto_disponible ? (
                        <span className="px-2.5 py-1 rounded-full bg-emerald-600 text-white font-bold">
                          Repuesto llegó · Atención inmediata
                        </span>
                      ) : eq.repuestos_pendientes.length > 0 ? (
                        <span className="text-amber-700 font-semibold">
                          Esperando: {eq.repuestos_pendientes.join(", ")}
                        </span>
                      ) : (
                        "—"
                      )}
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
