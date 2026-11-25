"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  FileSpreadsheet,
  Plus,
  ShoppingBag,
  Trash2,
  Upload,
} from "lucide-react";
import BuscadorTabla from "@/componentes/BuscadorTabla";
import PanelImportacionMasiva from "@/components/PanelImportacionMasiva";
import {
  ErrorApi,
  fechaHoyCaracas,
  formatearUsd,
  solicitarApi,
  subirArchivoApi,
} from "@/servicios/api";
import type { Sucursal } from "@/tipos/dominio";
import type {
  CompraResumen,
  ComprasPaginadas,
  EstadoEquipo,
  OrigenCompra,
  Tercero,
  ValidacionArchivo,
} from "@/tipos/logistica";

const ORIGENES: OrigenCompra[] = [
  "NACIONAL",
  "INTERNACIONAL",
  "CONSIGNACION",
  "IMPORTACION",
  "INVENTARIO_EXISTENTE",
  "PARTE_DE_PAGO",
];

interface EquipoFormulario {
  serial: string;
  modelo: string;
  configuracion: string;
  costo_compra_usd: string;
  precio_promo_usd: string;
  ubicacion_id: string;
  estado: EstadoEquipo;
}

export default function PaginaCompras() {
  const [compras, setCompras] = useState<CompraResumen[]>([]);
  const [busqueda, setBusqueda] = useState("");
  const [proveedores, setProveedores] = useState<Tercero[]>([]);
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  // Validación Excel/CSV
  const [validacion, setValidacion] = useState<ValidacionArchivo | null>(null);
  const [validandoArchivo, setValidandoArchivo] = useState(false);

  // Modal nueva compra
  const [modalNueva, setModalNueva] = useState(false);
  const [origen, setOrigen] = useState<OrigenCompra>("IMPORTACION");
  const [proveedorId, setProveedorId] = useState("");
  const [fecha, setFecha] = useState(fechaHoyCaracas());
  const [facturaOrden, setFacturaOrden] = useState("");
  const [llegaPreparada, setLlegaPreparada] = useState(false);
  const [nota, setNota] = useState("");
  const [equipos, setEquipos] = useState<EquipoFormulario[]>([
    {
      serial: "",
      modelo: "",
      configuracion: "",
      costo_compra_usd: "",
      precio_promo_usd: "",
      ubicacion_id: "",
      estado: "POR_PREPARAR",
    },
  ]);
  const [guardando, setGuardando] = useState(false);

  // Proveedor rápido
  const [nuevoProveedor, setNuevoProveedor] = useState("");

  const cargarDatos = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [respCompras, respProv, respSuc] = await Promise.all([
        solicitarApi<ComprasPaginadas>("/api/logistica/compras"),
        solicitarApi<Tercero[]>("/api/logistica/terceros"),
        solicitarApi<Sucursal[]>("/api/sucursales"),
      ]);
      setCompras(respCompras.elementos);
      setProveedores(respProv);
      setSucursales(respSuc);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudieron cargar las compras."
      );
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void cargarDatos();
  }, [cargarDatos]);

  const manejarSubirArchivo = async (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const archivo = e.target.files?.[0];
    if (!archivo) return;
    setError(null);
    setExito(null);
    setValidandoArchivo(true);
    try {
      const form = new FormData();
      form.append("archivo", archivo);
      const resultado = await subirArchivoApi<ValidacionArchivo>(
        "/api/logistica/compras/validar-archivo",
        form
      );
      setValidacion(resultado);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo validar el archivo."
      );
    } finally {
      setValidandoArchivo(false);
      e.target.value = "";
    }
  };

  const confirmarCargaDesdeArchivo = async () => {
    if (!validacion || !validacion.puede_confirmar) return;
    setGuardando(true);
    setError(null);
    setExito(null);
    try {
      const bodega = sucursales.find((s) => s.nombre === "Bodega");
      const equiposValidos = validacion.filas
        .filter((f) => f.serial)
        .map((f) => ({
          serial: f.serial,
          modelo: f.modelo,
          configuracion: f.configuracion,
          categoria: f.categoria,
          costo_compra_usd: f.costo_compra_usd ?? 0,
          precio_promo_usd: f.precio_promo_usd,
          ubicacion_id: bodega?.id ?? null,
        }));

      const montoTotal = equiposValidos.reduce(
        (acc, it) => acc + Number(it.costo_compra_usd || 0),
        0
      );

      await solicitarApi("/api/logistica/compras", {
        method: "POST",
        body: JSON.stringify({
          origen: "IMPORTACION",
          fecha: fechaHoyCaracas(),
          factura_orden: validacion.nombre_archivo,
          monto_mercancia_usd: montoTotal,
          equipos: equiposValidos,
        }),
      });
      setValidacion(null);
      setExito("Carga masiva confirmada y registrada en compras.");
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "Error al confirmar carga masiva."
      );
    } finally {
      setGuardando(false);
    }
  };

  const crearProveedorRapido = async () => {
    if (nuevoProveedor.trim().length < 2) return;
    try {
      const creado = await solicitarApi<Tercero>("/api/logistica/terceros", {
        method: "POST",
        body: JSON.stringify({
          nombre: nuevoProveedor.trim(),
          tipo: "PROVEEDOR",
        }),
      });
      setProveedores((prev) => [...prev, creado]);
      setProveedorId(String(creado.id));
      setNuevoProveedor("");
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "Error al crear proveedor."
      );
    }
  };

  const manejarCrearCompra = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setExito(null);

    const equiposLimpios = equipos
      .filter((eq) => eq.serial.trim() !== "")
      .map((eq) => ({
        serial: eq.serial.trim(),
        modelo: eq.modelo.trim(),
        configuracion: eq.configuracion.trim(),
        costo_compra_usd:
          eq.costo_compra_usd === "" ? null : Number(eq.costo_compra_usd),
        precio_promo_usd: Number(eq.precio_promo_usd || 0),
        ubicacion_id: eq.ubicacion_id ? Number(eq.ubicacion_id) : null,
        estado:
          origen === "INVENTARIO_EXISTENTE" ? eq.estado : undefined,
      }));

    if (equiposLimpios.length === 0) {
      setError("Agrega al menos un equipo con serial.");
      return;
    }

    const monto = equiposLimpios.reduce(
      (acc, eq) => acc + Number(eq.costo_compra_usd || 0),
      0
    );

    setGuardando(true);
    try {
      await solicitarApi("/api/logistica/compras", {
        method: "POST",
        body: JSON.stringify({
          origen,
          proveedor_id: proveedorId ? Number(proveedorId) : null,
          fecha,
          factura_orden: facturaOrden.trim(),
          monto_mercancia_usd: monto,
          llega_preparada: llegaPreparada,
          nota: nota.trim(),
          equipos: equiposLimpios,
        }),
      });
      setModalNueva(false);
      setFacturaOrden("");
      setNota("");
      setEquipos([
        {
          serial: "",
          modelo: "",
          configuracion: "",
          costo_compra_usd: "",
          precio_promo_usd: "",
          ubicacion_id: "",
          estado: "POR_PREPARAR",
        },
      ]);
      setExito("Compra registrada correctamente.");
      await cargarDatos();
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "No se pudo crear la compra."
      );
    } finally {
      setGuardando(false);
    }
  };

  const comprasFiltradas = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return compras;
    return compras.filter((c) =>
      [
        c.numero_compra,
        c.origen,
        c.proveedor || "",
        c.factura_orden || "",
        c.estado,
        c.fecha,
      ]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [compras, busqueda]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900">
            Compras e Importación Masiva
          </h2>
          <p className="text-sm text-slate-500">
            Registra compras manuales o importa archivos Excel/CSV con
            validación previa de seriales y costos.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white border border-slate-300 hover:bg-slate-50 text-sm font-bold text-slate-800 cursor-pointer">
            <Upload className="w-4 h-4 text-[#E85A28]" />
            <span>
              {validandoArchivo ? "Validando..." : "Importar Excel/CSV"}
            </span>
            <input
              type="file"
              accept=".xlsx,.csv"
              onChange={manejarSubirArchivo}
              className="hidden"
            />
          </label>

          <button
            type="button"
            onClick={() => setModalNueva(true)}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            Nueva compra
          </button>
        </div>
      </div>

      <PanelImportacionMasiva
        flujoInicial="compras_internacionales"
        alCompletar={() => void cargarDatos()}
      />

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

      {/* Previsualización de archivo Excel/CSV */}
      {validacion && (
        <div className="bg-white rounded-2xl border-2 border-slate-300 p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <FileSpreadsheet className="w-5 h-5 text-[#E85A28]" />
              <div>
                <h3 className="font-bold text-slate-900">
                  Previsualización: {validacion.nombre_archivo}
                </h3>
                <p className="text-xs text-slate-500">
                  Válidas: <strong>{validacion.filas_validas}</strong> · Con
                  errores:{" "}
                  <strong className="text-red-600">
                    {validacion.filas_con_error}
                  </strong>
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setValidacion(null)}
                className="px-3 py-2 rounded-xl border border-slate-300 text-xs font-bold cursor-pointer"
              >
                Descartar
              </button>
              <button
                type="button"
                disabled={!validacion.puede_confirmar || guardando}
                onClick={() => void confirmarCargaDesdeArchivo()}
                className="px-4 py-2 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] disabled:opacity-40 text-white text-xs font-bold cursor-pointer"
              >
                {guardando ? "Procesando..." : "Confirmar carga"}
              </button>
            </div>
          </div>

          <div className="overflow-x-auto border border-slate-200 rounded-xl">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 border-b border-slate-200 uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-2">Fila</th>
                  <th className="px-3 py-2">Serial</th>
                  <th className="px-3 py-2">Modelo</th>
                  <th className="px-3 py-2 text-right">Costo USD</th>
                  <th className="px-3 py-2">Validación</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {validacion.filas.map((f) => (
                  <tr
                    key={f.fila}
                    className={f.valida ? "bg-white" : "bg-red-50 text-red-800"}
                  >
                    <td className="px-3 py-2 font-bold">{f.fila}</td>
                    <td className="px-3 py-2 font-mono font-bold">
                      {f.serial || "—"}
                    </td>
                    <td className="px-3 py-2">{f.modelo || "—"}</td>
                    <td className="px-3 py-2 text-right">
                      {formatearUsd(f.costo_compra_usd)}
                    </td>
                    <td className="px-3 py-2">
                      {f.valida ? (
                        <span className="text-emerald-700 font-bold">OK</span>
                      ) : (
                        <span className="font-bold">
                          {f.errores.join(" · ")}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Buscador de compras */}
      <div className="bg-white rounded-2xl border border-slate-200 p-4">
        <BuscadorTabla
          valor={busqueda}
          alCambiar={setBusqueda}
          placeholder="Buscar por nro. de compra, proveedor, factura/orden, origen, fecha o estado..."
          totalRegistros={compras.length}
          totalFiltrados={comprasFiltradas.length}
        />
      </div>

      {/* Tabla de compras */}
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
        ) : comprasFiltradas.length === 0 ? (
          <div className="p-10 text-center space-y-2">
            <ShoppingBag className="w-10 h-10 text-slate-300 mx-auto" />
            <p className="text-sm font-semibold text-slate-600">
              No hay compras que coincidan.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Nro. Compra</th>
                  <th className="px-4 py-3">Fecha</th>
                  <th className="px-4 py-3">Origen</th>
                  <th className="px-4 py-3">Proveedor / Factura</th>
                  <th className="px-4 py-3 text-right">Equipos</th>
                  <th className="px-4 py-3 text-right">Monto USD</th>
                  <th className="px-4 py-3">Estado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {comprasFiltradas.map((c) => (
                  <tr key={c.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-mono font-bold text-slate-900">
                      {c.numero_compra}
                    </td>
                    <td className="px-4 py-3">{c.fecha}</td>
                    <td className="px-4 py-3 text-xs font-bold">{c.origen}</td>
                    <td className="px-4 py-3">
                      <p className="font-semibold">{c.proveedor}</p>
                      <p className="text-xs text-slate-500">
                        {c.factura_orden || "Sin factura"}
                      </p>
                    </td>
                    <td className="px-4 py-3 text-right font-bold">
                      {c.total_equipos}
                    </td>
                    <td className="px-4 py-3 text-right font-bold text-emerald-700">
                      {formatearUsd(c.monto_mercancia_usd)}
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-orange-50 text-[#C9461A]">
                        {c.estado}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal nueva compra */}
      {modalNueva && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-3xl w-full p-6 shadow-xl space-y-4 max-h-[90vh] overflow-y-auto">
            <h3 className="text-lg font-black text-slate-900">
              Registrar compra / ingreso de equipos
            </h3>
            <form onSubmit={manejarCrearCompra} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Origen
                  </label>
                  <select
                    value={origen}
                    onChange={(e) => setOrigen(e.target.value as OrigenCompra)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                  >
                    {ORIGENES.map((o) => (
                      <option key={o} value={o}>
                        {o}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Fecha
                  </label>
                  <input
                    type="date"
                    required
                    value={fecha}
                    onChange={(e) => setFecha(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Factura / Orden
                  </label>
                  <input
                    type="text"
                    value={facturaOrden}
                    onChange={(e) => setFacturaOrden(e.target.value)}
                    placeholder="Ej: EBAY-2026-01"
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 items-end">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Proveedor
                  </label>
                  <select
                    value={proveedorId}
                    onChange={(e) => setProveedorId(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                  >
                    <option value="">Sin proveedor</option>
                    {proveedores.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.nombre}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={nuevoProveedor}
                    onChange={(e) => setNuevoProveedor(e.target.value)}
                    placeholder="Crear proveedor rápido..."
                    className="flex-1 px-3 py-2 rounded-xl border border-slate-300 text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => void crearProveedorRapido()}
                    className="px-3 py-2 rounded-xl border border-slate-300 text-xs font-bold hover:bg-slate-100 cursor-pointer"
                  >
                    + Agregar
                  </button>
                </div>
              </div>

              <label className="inline-flex items-center gap-2 text-xs font-semibold text-slate-700">
                <input
                  type="checkbox"
                  checked={llegaPreparada}
                  onChange={(e) => setLlegaPreparada(e.target.checked)}
                />
                Llega preparada (entra directo como LISTO en lugar de POR_PREPARAR)
              </label>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-bold uppercase text-slate-600">
                    Equipos por serial
                  </p>
                  <button
                    type="button"
                    onClick={() =>
                      setEquipos((prev) => [
                        ...prev,
                        {
                          serial: "",
                          modelo: "",
                          configuracion: "",
                          costo_compra_usd: "",
                          precio_promo_usd: "",
                          ubicacion_id: "",
                          estado: "POR_PREPARAR",
                        },
                      ])
                    }
                    className="text-xs font-bold text-[#E85A28] cursor-pointer"
                  >
                    + Añadir fila
                  </button>
                </div>

                {equipos.map((eq, idx) => (
                  <div
                    key={idx}
                    className="grid grid-cols-1 sm:grid-cols-6 gap-2 p-3 rounded-xl bg-slate-50 border border-slate-200"
                  >
                    <input
                      type="text"
                      required
                      placeholder="Serial *"
                      value={eq.serial}
                      onChange={(e) => {
                        const copia = [...equipos];
                        copia[idx] = { ...copia[idx], serial: e.target.value };
                        setEquipos(copia);
                      }}
                      className="px-2.5 py-1.5 rounded-lg border border-slate-300 text-xs font-mono bg-white"
                    />
                    <input
                      type="text"
                      placeholder="Modelo"
                      value={eq.modelo}
                      onChange={(e) => {
                        const copia = [...equipos];
                        copia[idx] = { ...copia[idx], modelo: e.target.value };
                        setEquipos(copia);
                      }}
                      className="px-2.5 py-1.5 rounded-lg border border-slate-300 text-xs bg-white"
                    />
                    <input
                      type="number"
                      step="0.01"
                      placeholder="Costo USD *"
                      required={origen === "INVENTARIO_EXISTENTE"}
                      value={eq.costo_compra_usd}
                      onChange={(e) => {
                        const copia = [...equipos];
                        copia[idx] = {
                          ...copia[idx],
                          costo_compra_usd: e.target.value,
                        };
                        setEquipos(copia);
                      }}
                      className="px-2.5 py-1.5 rounded-lg border border-slate-300 text-xs bg-white"
                    />
                    <input
                      type="number"
                      step="0.01"
                      placeholder="Promo USD"
                      value={eq.precio_promo_usd}
                      onChange={(e) => {
                        const copia = [...equipos];
                        copia[idx] = {
                          ...copia[idx],
                          precio_promo_usd: e.target.value,
                        };
                        setEquipos(copia);
                      }}
                      className="px-2.5 py-1.5 rounded-lg border border-slate-300 text-xs bg-white"
                    />
                    <select
                      value={eq.ubicacion_id}
                      required={origen === "INVENTARIO_EXISTENTE"}
                      onChange={(e) => {
                        const copia = [...equipos];
                        copia[idx] = {
                          ...copia[idx],
                          ubicacion_id: e.target.value,
                        };
                        setEquipos(copia);
                      }}
                      className="px-2 py-1.5 rounded-lg border border-slate-300 text-xs bg-white"
                    >
                      <option value="">Ubicación (Bodega)</option>
                      {sucursales
                        .filter((s) => s.estado === "ACTIVA")
                        .map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.nombre}
                          </option>
                        ))}
                    </select>
                    <button
                      type="button"
                      onClick={() =>
                        setEquipos((prev) =>
                          prev.length > 1
                            ? prev.filter((_, i) => i !== idx)
                            : prev
                        )
                      }
                      className="inline-flex items-center justify-center p-1.5 rounded-lg text-red-600 hover:bg-red-50 cursor-pointer"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setModalNueva(false)}
                  className="px-4 py-2 rounded-xl border border-slate-300 text-sm font-semibold cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={guardando}
                  className="px-4 py-2 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold disabled:opacity-60 cursor-pointer"
                >
                  {guardando ? "Guardando..." : "Registrar compra"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
