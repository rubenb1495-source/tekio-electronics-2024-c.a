"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  History,
  Package,
  Plus,
  Search,
  Tag,
} from "lucide-react";
import { usarSesion } from "@/contexto/SesionContexto";
import {
  ErrorApi,
  fechaHoyCaracas,
  formatearBs,
  formatearPorcentaje,
  formatearUsd,
  normalizarSkuCliente,
  puedeGestionarCatalogo,
  puedeVerCostos,
  solicitarApi,
} from "@/servicios/api";
import type {
  ArticuloCatalogo,
  CatalogoPaginado,
  PrecioHistorial,
  TipoArticulo,
} from "@/tipos/dominio";

const TIPOS_ARTICULO: TipoArticulo[] = [
  "EQUIPO",
  "COMPONENTE",
  "ACCESORIO",
  "SERVICIO",
];

export default function PaginaCatalogo() {
  const { usuario } = usarSesion();
  const verCostos = usuario ? puedeVerCostos(usuario.rol) : false;
  const gestionar = usuario ? puedeGestionarCatalogo(usuario.rol) : false;

  const [articulos, setArticulos] = useState<ArticuloCatalogo[]>([]);
  const [total, setTotal] = useState(0);
  const [recargoAplicado, setRecargoAplicado] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [busqueda, setBusqueda] = useState("");
  const [filtroTipo, setFiltroTipo] = useState("");
  const [filtroCategoria, setFiltroCategoria] = useState("");

  // Modal crear artículo
  const [modalCrear, setModalCrear] = useState(false);
  const [sku, setSku] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [tipo, setTipo] = useState<TipoArticulo>("COMPONENTE");
  const [categoria, setCategoria] = useState("General");
  const [precioPromo, setPrecioPromo] = useState("");
  const [precioRegularFijo, setPrecioRegularFijo] = useState("");
  const [costoReferencia, setCostoReferencia] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [errorModal, setErrorModal] = useState<string | null>(null);

  // Modal actualizar precio + historial
  const [articuloSeleccionado, setArticuloSeleccionado] =
    useState<ArticuloCatalogo | null>(null);
  const [historialPrecios, setHistorialPrecios] = useState<PrecioHistorial[]>(
    []
  );
  const [cargandoHistorial, setCargandoHistorial] = useState(false);
  const [nuevoPromo, setNuevoPromo] = useState("");
  const [nuevoRegularFijo, setNuevoRegularFijo] = useState("");
  const [nuevoCosto, setNuevoCosto] = useState("");
  const [fechaVigencia, setFechaVigencia] = useState(
    fechaHoyCaracas()
  );

  const cargarCatalogo = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const parametros = new URLSearchParams();
      if (busqueda.trim()) parametros.set("busqueda", busqueda.trim());
      if (filtroTipo) parametros.set("tipo", filtroTipo);
      if (filtroCategoria.trim()) {
        parametros.set("categoria", filtroCategoria.trim());
      }
      const qs = parametros.toString() ? `?${parametros.toString()}` : "";
      const datos = await solicitarApi<CatalogoPaginado>(`/api/catalogo${qs}`);
      setArticulos(datos.elementos);
      setTotal(datos.total);
      setRecargoAplicado(datos.recargo_aplicado_porcentaje);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo cargar el catálogo de artículos."
      );
    } finally {
      setCargando(false);
    }
  }, [busqueda, filtroTipo, filtroCategoria]);

  useEffect(() => {
    const temporizador = setTimeout(() => {
      void cargarCatalogo();
    }, 200);
    return () => clearTimeout(temporizador);
  }, [cargarCatalogo]);

  const abrirModalPrecios = async (articulo: ArticuloCatalogo) => {
    setArticuloSeleccionado(articulo);
    setNuevoPromo(String(articulo.precio_promo_usd));
    setNuevoRegularFijo(
      articulo.precio_regular_fijo_usd !== null
        ? String(articulo.precio_regular_fijo_usd)
        : ""
    );
    setNuevoCosto(
      articulo.costo_referencia_usd !== undefined &&
        articulo.costo_referencia_usd !== null
        ? String(articulo.costo_referencia_usd)
        : ""
    );
    setFechaVigencia(fechaHoyCaracas());
    setErrorModal(null);
    setCargandoHistorial(true);
    try {
      const hist = await solicitarApi<PrecioHistorial[]>(
        `/api/catalogo/${articulo.id}/precios`
      );
      setHistorialPrecios(hist);
    } catch (err) {
      setErrorModal(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo cargar el historial de precios."
      );
    } finally {
      setCargandoHistorial(false);
    }
  };

  const manejarCrearArticulo = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorModal(null);
    const promoNum = Number(precioPromo);
    if (!Number.isFinite(promoNum) || promoNum < 0) {
      setErrorModal("Ingresa un Precio Promo USD válido.");
      return;
    }

    setGuardando(true);
    try {
      await solicitarApi<ArticuloCatalogo>("/api/catalogo", {
        method: "POST",
        body: JSON.stringify({
          sku,
          descripcion: descripcion.trim(),
          tipo,
          categoria: categoria.trim() || "General",
          precio_promo_usd: promoNum,
          precio_regular_fijo_usd:
            precioRegularFijo.trim() === "" ? null : Number(precioRegularFijo),
          costo_referencia_usd:
            verCostos && costoReferencia.trim() !== ""
              ? Number(costoReferencia)
              : null,
        }),
      });
      setModalCrear(false);
      setSku("");
      setDescripcion("");
      setPrecioPromo("");
      setPrecioRegularFijo("");
      setCostoReferencia("");
      await cargarCatalogo();
    } catch (err) {
      setErrorModal(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo registrar el artículo."
      );
    } finally {
      setGuardando(false);
    }
  };

  const manejarGuardarNuevoPrecio = async (
    e: React.FormEvent<HTMLFormElement>
  ) => {
    e.preventDefault();
    if (!articuloSeleccionado) return;
    setErrorModal(null);

    const promoNum = Number(nuevoPromo);
    if (!Number.isFinite(promoNum) || promoNum < 0) {
      setErrorModal("Ingresa un Precio Promo USD válido.");
      return;
    }

    setGuardando(true);
    try {
      await solicitarApi<PrecioHistorial>(
        `/api/catalogo/${articuloSeleccionado.id}/precios`,
        {
          method: "POST",
          body: JSON.stringify({
            precio_promo_usd: promoNum,
            precio_regular_fijo_usd:
              nuevoRegularFijo.trim() === "" ? null : Number(nuevoRegularFijo),
            costo_referencia_usd:
              verCostos && nuevoCosto.trim() !== ""
                ? Number(nuevoCosto)
                : null,
            fecha_vigencia: fechaVigencia,
          }),
        }
      );
      const hist = await solicitarApi<PrecioHistorial[]>(
        `/api/catalogo/${articuloSeleccionado.id}/precios`
      );
      setHistorialPrecios(hist);
      await cargarCatalogo();
    } catch (err) {
      setErrorModal(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo registrar la nueva versión de precio."
      );
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900">
            Catálogo Maestro y Precios
          </h2>
          <p className="text-sm text-slate-500">
            SKUs normalizados en MAYÚSCULAS e historial inmutable de precios ·
            Recargo aplicado: {formatearPorcentaje(recargoAplicado)}
          </p>
        </div>

        {gestionar && (
          <button
            type="button"
            onClick={() => {
              setErrorModal(null);
              setModalCrear(true);
            }}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            Nuevo artículo
          </button>
        )}
      </div>

      {/* Buscador y filtros */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200 grid grid-cols-1 md:grid-cols-4 gap-3">
        <div className="md:col-span-2 relative">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder="Buscar por SKU (ej. BAT-33YDH) o descripción..."
            className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-300 text-sm"
          />
        </div>
        <select
          value={filtroTipo}
          onChange={(e) => setFiltroTipo(e.target.value)}
          className="px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
        >
          <option value="">Todos los tipos</option>
          {TIPOS_ARTICULO.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <input
          type="text"
          value={filtroCategoria}
          onChange={(e) => setFiltroCategoria(e.target.value)}
          placeholder="Filtrar categoría..."
          className="px-3 py-2 rounded-xl border border-slate-300 text-sm"
        />
      </div>

      {error && (
        <div className="flex items-center gap-2.5 p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Tabla */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        {cargando ? (
          <div className="p-6 space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="h-12 rounded-xl bg-slate-100 animate-pulse"
              />
            ))}
          </div>
        ) : articulos.length === 0 ? (
          <div className="p-10 text-center space-y-3">
            <Package className="w-10 h-10 text-slate-300 mx-auto" />
            <p className="text-sm font-semibold text-slate-600">
              No se encontraron artículos en el catálogo.
            </p>
            {gestionar && (
              <button
                type="button"
                onClick={() => setModalCrear(true)}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#E85A28] text-white text-xs font-bold cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                Crear primer artículo
              </button>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">SKU</th>
                  <th className="px-4 py-3">Descripción</th>
                  <th className="px-4 py-3">Tipo / Categoría</th>
                  <th className="px-4 py-3 text-right">Promo USD</th>
                  <th className="px-4 py-3 text-right">Regular USD</th>
                  <th className="px-4 py-3 text-right">Regular Bs</th>
                  {verCostos && (
                    <th className="px-4 py-3 text-right">Costo Ref.</th>
                  )}
                  <th className="px-4 py-3 text-right">Precios</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {articulos.map((art) => (
                  <tr key={art.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-mono font-bold text-slate-900">
                      {art.sku}
                    </td>
                    <td className="px-4 py-3 text-slate-800">
                      {art.descripcion}
                    </td>
                    <td className="px-4 py-3 text-xs">
                      <span className="px-2 py-0.5 rounded-md bg-slate-100 font-bold text-slate-700">
                        {art.tipo}
                      </span>
                      <span className="ml-1.5 text-slate-500">
                        {art.categoria}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-bold text-emerald-700">
                      {formatearUsd(art.precio_promo_usd)}
                    </td>
                    <td className="px-4 py-3 text-right font-bold text-[#C9461A]">
                      {formatearUsd(art.precio_regular_usd)}
                    </td>
                    <td className="px-4 py-3 text-right font-semibold text-slate-700">
                      {formatearBs(art.precio_regular_bs)}
                    </td>
                    {verCostos && (
                      <td className="px-4 py-3 text-right text-slate-500">
                        {formatearUsd(art.costo_referencia_usd)}
                      </td>
                    )}
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => void abrirModalPrecios(art)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 text-xs font-semibold hover:bg-slate-100 cursor-pointer"
                      >
                        <History className="w-3.5 h-3.5 text-[#E85A28]" />
                        {gestionar ? "Actualizar precio" : "Historial"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="px-4 py-2.5 bg-slate-50 border-t border-slate-200 text-xs text-slate-500">
              Mostrando {articulos.length} de {total} artículos activos
            </div>
          </div>
        )}
      </div>

      {/* Modal crear artículo */}
      {modalCrear && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl space-y-4">
            <h3 className="text-lg font-black text-slate-900">
              Registrar artículo en catálogo
            </h3>
            {errorModal && (
              <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700">
                {errorModal}
              </div>
            )}
            <form onSubmit={manejarCrearArticulo} className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  SKU (se normaliza automáticamente)
                </label>
                <input
                  type="text"
                  required
                  value={sku}
                  onChange={(e) => setSku(e.target.value)}
                  placeholder="Ej: bat 33ydh"
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm font-mono"
                />
                {sku.trim() && (
                  <p className="text-[11px] text-slate-500 mt-1">
                    Se guardará como:{" "}
                    <strong className="font-mono text-[#C9461A]">
                      {normalizarSkuCliente(sku)}
                    </strong>
                  </p>
                )}
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Descripción
                </label>
                <input
                  type="text"
                  required
                  value={descripcion}
                  onChange={(e) => setDescripcion(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Tipo
                  </label>
                  <select
                    value={tipo}
                    onChange={(e) => setTipo(e.target.value as TipoArticulo)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                  >
                    {TIPOS_ARTICULO.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Categoría
                  </label>
                  <input
                    type="text"
                    required
                    value={categoria}
                    onChange={(e) => setCategoria(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Precio Promo USD
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    required
                    value={precioPromo}
                    onChange={(e) => setPrecioPromo(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Regular Fijo USD (opcional)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={precioRegularFijo}
                    onChange={(e) => setPrecioRegularFijo(e.target.value)}
                    placeholder="Auto con % recargo"
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                  />
                </div>
              </div>

              {verCostos && (
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Costo de referencia USD (opcional)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={costoReferencia}
                    onChange={(e) => setCostoReferencia(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                  />
                </div>
              )}

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
                  className="px-4 py-2 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold disabled:opacity-60 cursor-pointer"
                >
                  {guardando ? "Guardando..." : "Crear artículo"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal actualizar precio e historial */}
      {articuloSeleccionado && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-xl space-y-5 max-h-[90vh] overflow-y-auto">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-mono font-bold text-[#E85A28]">
                  {articuloSeleccionado.sku}
                </p>
                <h3 className="text-lg font-black text-slate-900">
                  {articuloSeleccionado.descripcion}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setArticuloSeleccionado(null)}
                className="px-3 py-1 rounded-lg border border-slate-300 text-xs font-semibold cursor-pointer"
              >
                Cerrar
              </button>
            </div>

            {errorModal && (
              <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700">
                {errorModal}
              </div>
            )}

            {gestionar && (
              <form
                onSubmit={manejarGuardarNuevoPrecio}
                className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3"
              >
                <p className="text-xs font-bold uppercase text-slate-700 flex items-center gap-1.5">
                  <Tag className="w-3.5 h-3.5 text-[#E85A28]" />
                  Registrar nueva versión de precio (conserva historial)
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">
                      Nuevo Promo USD
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      required
                      value={nuevoPromo}
                      onChange={(e) => setNuevoPromo(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">
                      Regular Fijo USD
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={nuevoRegularFijo}
                      onChange={(e) => setNuevoRegularFijo(e.target.value)}
                      placeholder="Auto"
                      className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">
                      Fecha de vigencia
                    </label>
                    <input
                      type="date"
                      required
                      value={fechaVigencia}
                      onChange={(e) => setFechaVigencia(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                    />
                  </div>
                </div>
                {verCostos && (
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">
                      Costo de referencia USD (opcional)
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={nuevoCosto}
                      onChange={(e) => setNuevoCosto(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                    />
                  </div>
                )}
                <div className="flex justify-end">
                  <button
                    type="submit"
                    disabled={guardando}
                    className="px-4 py-2 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-xs font-bold disabled:opacity-60 cursor-pointer"
                  >
                    {guardando ? "Registrando..." : "Guardar nuevo precio"}
                  </button>
                </div>
              </form>
            )}

            <div>
              <h4 className="text-xs font-bold uppercase text-slate-500 mb-2">
                Historial completo de precios
              </h4>
              {cargandoHistorial ? (
                <div className="h-20 rounded-xl bg-slate-100 animate-pulse" />
              ) : historialPrecios.length === 0 ? (
                <p className="text-xs text-slate-500">
                  Sin registros de precios.
                </p>
              ) : (
                <div className="border border-slate-200 rounded-xl overflow-hidden">
                  <table className="w-full text-xs text-left">
                    <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase">
                      <tr>
                        <th className="px-3 py-2">Vigencia</th>
                        <th className="px-3 py-2 text-right">Promo USD</th>
                        <th className="px-3 py-2 text-right">Regular Fijo</th>
                        {verCostos && (
                          <th className="px-3 py-2 text-right">Costo Ref.</th>
                        )}
                        <th className="px-3 py-2">Registrado por</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {historialPrecios.map((p) => (
                        <tr key={p.id}>
                          <td className="px-3 py-2 font-bold text-slate-800">
                            {p.fecha_vigencia}
                          </td>
                          <td className="px-3 py-2 text-right font-semibold text-emerald-700">
                            {formatearUsd(p.precio_promo_usd)}
                          </td>
                          <td className="px-3 py-2 text-right">
                            {formatearUsd(p.precio_regular_fijo_usd)}
                          </td>
                          {verCostos && (
                            <td className="px-3 py-2 text-right text-slate-500">
                              {formatearUsd(p.costo_referencia_usd)}
                            </td>
                          )}
                          <td className="px-3 py-2 text-slate-600">
                            {p.creado_por || "Sistema"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
