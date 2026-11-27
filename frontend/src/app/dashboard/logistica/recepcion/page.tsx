"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  PackagePlus,
  Plus,
  ScanBarcode,
  ShieldCheck,
  Trash2,
  Truck,
  Upload,
  X,
} from "lucide-react";
import {
  descargarPdfApi,
  ErrorApi,
  fechaHoyCaracas,
  formatearUsd,
  solicitarApi,
  subirArchivoApi,
} from "@/servicios/api";
import type { ArticuloCatalogo, CatalogoPaginado, Sucursal } from "@/tipos/dominio";
import type {
  GuiaResumen,
  ResultadoRecepcionGuia,
  Verificador,
} from "@/tipos/logistica";

type OrigenRecepcion = "COMPRA" | "TRASLADO_GUIA";
type ModoCarga = "UNO_A_UNO" | "MASIVA";
type CondicionLlegada = "EXCELENTE" | "BUENO" | "CON_DETALLES" | "CON_FALLA";
type EstadoInicialEquipo = "POR_PREPARAR" | "HOSPITAL";

interface CompraPendienteRecepcion {
  id: number;
  numero_compra: string;
  origen: string;
  tipo_compra: string;
  proveedor: string;
  fecha: string;
  factura_orden: string;
  numero_guia: string;
  estado: string;
  equipos_recibidos: number;
  cantidad_esperada: number;
  trackings: {
    id: number;
    numero_tracking: string;
    courier: string;
    estado: string;
  }[];
}

interface FilaEquipoEscaneado {
  uid: string;
  serial: string;
  modelo: string;
  articulo_id: string;
  ram: string;
  almacenamiento: string;
  condicion_llegada: CondicionLlegada;
  incluye_cargador: boolean;
  observaciones_llegada: string;
  estado_inicial: EstadoInicialEquipo;
}

interface FilaComponenteRecepcion {
  uid: string;
  articulo_id: string;
  cantidad: string;
  costo_unitario_usd: string;
}

interface FilaPreviewMasiva {
  fila: number;
  tipo: "EQUIPO" | "COMPONENTE";
  valida: boolean;
  errores: string[];
  serial: string;
  sku_o_modelo: string;
  articulo_id: number | null;
  ram: string;
  almacenamiento: string;
  condicion_llegada: CondicionLlegada;
  incluye_cargador: boolean;
  observaciones_llegada: string;
  estado_inicial: EstadoInicialEquipo;
  cantidad: number;
}

interface RespuestaPreviewMasiva {
  compra_id: number;
  numero_compra: string;
  total_filas: number;
  validas: number;
  con_errores: number;
  filas: FilaPreviewMasiva[];
}

function ContenidoRecepcionUnificada() {
  const searchParams = useSearchParams();
  const compraIdQuery = searchParams.get("compra_id") || "";

  // Selectores principales
  const [origen, setOrigen] = useState<OrigenRecepcion>("COMPRA");
  const [modoCarga, setModoCarga] = useState<ModoCarga>("UNO_A_UNO");

  // Catálogos y datos compartidos
  const [comprasPendientes, setComprasPendientes] = useState<CompraPendienteRecepcion[]>([]);
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [articulos, setArticulos] = useState<ArticuloCatalogo[]>([]);
  const [guias, setGuias] = useState<GuiaResumen[]>([]);
  const [verificadores, setVerificadores] = useState<Verificador[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  // Estado para Origen: COMPRA
  const [compraId, setCompraId] = useState<string>(compraIdQuery);
  const [sucursalDestinoId, setSucursalDestinoId] = useState<string>("");
  const [trackingId, setTrackingId] = useState<string>("");
  const [cerrarCompra, setCerrarCompra] = useState(false);

  // Modo 1: Uno a Uno (Escáner / Manual)
  const [inputEscaner, setInputEscaner] = useState("");
  const [modeloDefault, setModeloDefault] = useState("");
  const [equiposLista, setEquiposLista] = useState<FilaEquipoEscaneado[]>([]);
  const [componentesLista, setComponentesLista] = useState<FilaComponenteRecepcion[]>([]);
  const [procesandoCompra, setProcesandoCompra] = useState(false);
  const refEscanerCompra = useRef<HTMLInputElement>(null);

  // Modo 2: Carga Masiva (.xlsx / .csv)
  const [archivoMasivo, setArchivoMasivo] = useState<File | null>(null);
  const [previewMasiva, setPreviewMasiva] = useState<RespuestaPreviewMasiva | null>(null);
  const [analizandoMasiva, setAnalizandoMasiva] = useState(false);

  // Estado para Origen: TRASLADO_GUIA (flujo existente de Guías con Doble Verificación)
  const [guiaId, setGuiaId] = useState("");
  const [verificadorId, setVerificadorId] = useState("");
  const [fechaReal, setFechaReal] = useState(fechaHoyCaracas());
  const [inputSerialGuia, setInputSerialGuia] = useState("");
  const [serialesGuia, setSerialesGuia] = useState<string[]>([]);
  const [procesandoGuia, setProcesandoGuia] = useState(false);
  const [resultadoGuia, setResultadoGuia] = useState<ResultadoRecepcionGuia | null>(null);
  const refInputGuia = useRef<HTMLInputElement>(null);

  const cargarTodo = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [respComp, respSuc, respArt, respGuias, respVerif] = await Promise.all([
        solicitarApi<CompraPendienteRecepcion[]>("/api/logistica/compras/pendientes-recepcion"),
        solicitarApi<Sucursal[]>("/api/sucursales"),
        solicitarApi<CatalogoPaginado>("/api/catalogo?por_pagina=100"),
        solicitarApi<GuiaResumen[]>("/api/logistica/guias?estado=EN_TRANSITO"),
        solicitarApi<Verificador[]>("/api/logistica/verificadores"),
      ]);
      const listaCompras = Array.isArray(respComp) ? respComp : [];
      const listaSuc = Array.isArray(respSuc) ? respSuc : [];
      const listaArt = Array.isArray(respArt?.elementos)
        ? respArt.elementos
        : Array.isArray(respArt)
          ? (respArt as unknown as ArticuloCatalogo[])
          : [];
      const listaGuias = Array.isArray(respGuias) ? respGuias : [];
      const listaVerif = Array.isArray(respVerif) ? respVerif : [];

      setComprasPendientes(listaCompras);
      const activas = listaSuc.filter((s) => s.estado === "ACTIVA");
      setSucursales(activas);
      setArticulos(listaArt);
      setGuias(listaGuias);
      setVerificadores(listaVerif);

      // Preseleccionar Depósito / Tekio Support (Taller)
      const deposito =
        activas.find((s) => s.tipo === "DEPOSITO_TALLER" || s.nombre.toLowerCase().includes("support")) ||
        activas[0];
      if (deposito) {
        setSucursalDestinoId((prev) => prev || String(deposito.id));
      }
      if (compraIdQuery) {
        setCompraId(compraIdQuery);
        setOrigen("COMPRA");
      } else if (listaCompras[0]) {
        setCompraId((prev) => prev || String(listaCompras[0].id));
      }
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo cargar la información de recepción."
      );
    } finally {
      setCargando(false);
    }
  }, [compraIdQuery]);

  useEffect(() => {
    void cargarTodo();
  }, [cargarTodo]);

  const compraActual = useMemo(
    () => comprasPendientes.find((c) => String(c.id) === compraId) || null,
    [comprasPendientes, compraId]
  );

  const articulosComponentes = useMemo(
    () => articulos.filter((a) => a.tipo === "COMPONENTE" || a.tipo === "ACCESORIO"),
    [articulos]
  );

  const agregarEquipoEscaneado = (serialRaw: string) => {
    const sn = serialRaw.trim().replace(/\s+/g, "").toUpperCase();
    if (!sn) return;
    if (equiposLista.some((e) => e.serial === sn)) {
      setError(`El serial '${sn}' ya fue escaneado en esta sesión.`);
      setInputEscaner("");
      refEscanerCompra.current?.focus();
      return;
    }
    setError(null);
    setEquiposLista((prev) => [
      ...prev,
      {
        uid: `${Date.now()}-${Math.random()}`,
        serial: sn,
        modelo: modeloDefault.trim(),
        articulo_id: "",
        ram: "",
        almacenamiento: "",
        condicion_llegada: "BUENO",
        incluye_cargador: true,
        observaciones_llegada: "",
        estado_inicial: "POR_PREPARAR",
      },
    ]);
    setInputEscaner("");
    refEscanerCompra.current?.focus();
  };

  const agregarEquipoManual = () => {
    setEquiposLista((prev) => [
      ...prev,
      {
        uid: `${Date.now()}-${Math.random()}`,
        serial: "",
        modelo: modeloDefault.trim(),
        articulo_id: "",
        ram: "",
        almacenamiento: "",
        condicion_llegada: "BUENO",
        incluye_cargador: true,
        observaciones_llegada: "",
        estado_inicial: "POR_PREPARAR",
      },
    ]);
  };

  const confirmarRecepcionUnoAUno = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setExito(null);
    if (!compraId) {
      setError("Selecciona una compra antes de confirmar la recepción.");
      return;
    }
    if (!sucursalDestinoId) {
      setError("Selecciona la sede destino.");
      return;
    }
    const eqValidos = equiposLista.filter((eq) => eq.serial.trim().length >= 2);
    const compValidos = componentesLista.filter(
      (c) => c.articulo_id && Number(c.cantidad) > 0
    );
    if (eqValidos.length === 0 && compValidos.length === 0) {
      setError("Escanea o agrega al menos un equipo serializado o un componente.");
      return;
    }

    setProcesandoCompra(true);
    try {
      const resp = await solicitarApi<{
        numero_compra: string;
        estado_compra: string;
        equipos_recibidos: number;
        componentes_recibidos: number;
        sucursal_destino: string;
      }>(`/api/logistica/compras/${compraId}/recibir`, {
        method: "POST",
        body: JSON.stringify({
          sucursal_destino_id: Number(sucursalDestinoId),
          tracking_id: trackingId ? Number(trackingId) : null,
          cerrar_compra: cerrarCompra,
          equipos: eqValidos.map((eq) => ({
            serial: eq.serial.trim().toUpperCase(),
            modelo: eq.modelo.trim(),
            articulo_id: eq.articulo_id ? Number(eq.articulo_id) : null,
            ram: eq.ram.trim(),
            almacenamiento: eq.almacenamiento.trim(),
            condicion_llegada: eq.condicion_llegada,
            incluye_cargador: eq.incluye_cargador,
            observaciones_llegada: eq.observaciones_llegada.trim(),
            estado_inicial: eq.estado_inicial,
          })),
          componentes: compValidos.map((c) => ({
            articulo_id: Number(c.articulo_id),
            cantidad: Number(c.cantidad),
            costo_unitario_usd: Number(c.costo_unitario_usd || 0),
          })),
        }),
      });
      setExito(
        `Compra ${resp.numero_compra} recibida (${resp.estado_compra}): ${resp.equipos_recibidos} equipo(s) y ${resp.componentes_recibidos} componente(s) ingresados en ${resp.sucursal_destino}.`
      );
      setEquiposLista([]);
      setComponentesLista([]);
      setCerrarCompra(false);
      await cargarTodo();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo confirmar la recepción de la compra."
      );
    } finally {
      setProcesandoCompra(false);
    }
  };

  const analizarArchivoMasivo = async (archivo: File) => {
    if (!compraId) {
      setError("Selecciona primero la compra que vas a recibir.");
      return;
    }
    setAnalizandoMasiva(true);
    setError(null);
    setExito(null);
    try {
      const fd = new FormData();
      fd.append("archivo", archivo);
      const resp = await subirArchivoApi<RespuestaPreviewMasiva>(
        `/api/logistica/compras/${compraId}/recibir/preview`,
        fd
      );
      setPreviewMasiva(resp);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo validar el archivo masivo."
      );
    } finally {
      setAnalizandoMasiva(false);
    }
  };

  const confirmarRecepcionMasiva = async () => {
    if (!previewMasiva || !compraId || !sucursalDestinoId) return;
    const filasValidas = previewMasiva.filas.filter((f) => f.valida);
    if (filasValidas.length === 0) {
      setError("No hay filas válidas para confirmar.");
      return;
    }
    setProcesandoCompra(true);
    setError(null);
    setExito(null);
    try {
      const resp = await solicitarApi<{
        numero_compra: string;
        estado_compra: string;
        equipos_recibidos: number;
        componentes_recibidos: number;
        sucursal_destino: string;
      }>(`/api/logistica/compras/${compraId}/recibir/confirmar`, {
        method: "POST",
        body: JSON.stringify({
          sucursal_destino_id: Number(sucursalDestinoId),
          tracking_id: trackingId ? Number(trackingId) : null,
          cerrar_compra: cerrarCompra,
          equipos: filasValidas
            .filter((f) => f.tipo === "EQUIPO")
            .map((f) => ({
              serial: f.serial,
              modelo: f.sku_o_modelo,
              articulo_id: f.articulo_id,
              ram: f.ram,
              almacenamiento: f.almacenamiento,
              condicion_llegada: f.condicion_llegada,
              incluye_cargador: f.incluye_cargador,
              observaciones_llegada: f.observaciones_llegada,
              estado_inicial: f.estado_inicial,
            })),
          componentes: filasValidas
            .filter((f) => f.tipo === "COMPONENTE" && f.articulo_id !== null)
            .map((f) => ({
              articulo_id: f.articulo_id,
              cantidad: f.cantidad,
              costo_unitario_usd: 0,
            })),
        }),
      });
      setExito(
        `Carga masiva confirmada en ${resp.numero_compra} (${resp.estado_compra}): ${resp.equipos_recibidos} equipo(s) y ${resp.componentes_recibidos} componente(s) en ${resp.sucursal_destino}.`
      );
      setPreviewMasiva(null);
      setArchivoMasivo(null);
      setCerrarCompra(false);
      await cargarTodo();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo confirmar la carga masiva."
      );
    } finally {
      setProcesandoCompra(false);
    }
  };

  // Flujo existente de Guías (Doble Verificación)
  const agregarSerialGuia = (valor: string) => {
    const limpio = valor.trim().replace(/\s+/g, "").toUpperCase();
    if (!limpio) return;
    if (!serialesGuia.includes(limpio)) {
      setSerialesGuia((prev) => [...prev, limpio]);
    }
    setInputSerialGuia("");
    refInputGuia.current?.focus();
  };

  const manejarConfirmarGuia = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setResultadoGuia(null);
    if (!guiaId || !verificadorId) {
      setError("Selecciona la guía y un segundo usuario verificador.");
      return;
    }
    setProcesandoGuia(true);
    try {
      const resp = await solicitarApi<ResultadoRecepcionGuia>(
        `/api/logistica/guias/${guiaId}/recibir`,
        {
          method: "POST",
          body: JSON.stringify({
            fecha_llegada_real: fechaReal,
            verificado_por_id: Number(verificadorId),
            seriales_recibidos: serialesGuia,
          }),
        }
      );
      setResultadoGuia(resp);
      setSerialesGuia([]);
      setGuiaId("");
      await cargarTodo();
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo confirmar la recepción de la guía."
      );
    } finally {
      setProcesandoGuia(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Cabecera Light-First */}
      <div>
        <h2 className="text-2xl font-black text-[#191818] flex items-center gap-2">
          <ScanBarcode className="w-6 h-6 text-[#E85A28]" />
          Recepción con Escáner y Carga Masiva
        </h2>
        <p className="text-sm text-neutral-500">
          Recibe compras nacionales/internacionales o guías de casillero en modo Uno a Uno o Masivo (.xlsx/.csv) con prorrateo automático de costos.
        </p>
      </div>

      {/* Selector 1: Origen de la recepción */}
      <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex items-center gap-1.5 bg-[#F6F6F6] p-1 rounded-xl border border-neutral-200">
          <button
            type="button"
            onClick={() => setOrigen("COMPRA")}
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-colors cursor-pointer ${
              origen === "COMPRA"
                ? "bg-[#E85A28] text-white shadow-xs"
                : "text-neutral-600 hover:text-[#191818]"
            }`}
          >
            <PackagePlus className="w-4 h-4" />
            Compra (Nacional / Internacional)
          </button>
          <button
            type="button"
            onClick={() => setOrigen("TRASLADO_GUIA")}
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-colors cursor-pointer ${
              origen === "TRASLADO_GUIA"
                ? "bg-[#E85A28] text-white shadow-xs"
                : "text-neutral-600 hover:text-[#191818]"
            }`}
          >
            <Truck className="w-4 h-4" />
            Guía de Casillero / Ingreso Directo
          </button>
        </div>

        {origen === "COMPRA" && (
          <div className="inline-flex items-center gap-1.5 bg-[#F6F6F6] p-1 rounded-xl border border-neutral-200">
            <button
              type="button"
              onClick={() => setModoCarga("UNO_A_UNO")}
              className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold transition-colors cursor-pointer ${
                modoCarga === "UNO_A_UNO"
                  ? "bg-[#E85A28] text-white shadow-xs"
                  : "text-neutral-600 hover:text-[#191818]"
              }`}
            >
              <ScanBarcode className="w-3.5 h-3.5" />
              Modo 1 · Uno a Uno (Escáner)
            </button>
            <button
              type="button"
              onClick={() => setModoCarga("MASIVA")}
              className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold transition-colors cursor-pointer ${
                modoCarga === "MASIVA"
                  ? "bg-[#E85A28] text-white shadow-xs"
                  : "text-neutral-600 hover:text-[#191818]"
              }`}
            >
              <FileSpreadsheet className="w-3.5 h-3.5" />
              Modo 2 · Carga Masiva (.xlsx / .csv)
            </button>
          </div>
        )}
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

      {cargando ? (
        <div className="h-40 rounded-2xl bg-white/70 animate-pulse border border-neutral-200" />
      ) : origen === "COMPRA" ? (
        <div className="space-y-5">
          {/* Selección de Compra, Sede Destino y Tracking */}
          <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
            <div className="md:col-span-2">
              <label className="block text-xs font-bold text-[#191818] mb-1">
                Compra pendiente de recepción *
              </label>
              <select
                value={compraId}
                onChange={(e) => {
                  setCompraId(e.target.value);
                  setTrackingId("");
                  setPreviewMasiva(null);
                }}
                className="w-full px-3 py-2.5 rounded-xl border border-neutral-300 bg-white text-xs font-semibold text-[#191818]"
              >
                <option value="">Selecciona una compra...</option>
                {comprasPendientes.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.numero_compra} · {c.proveedor} ({c.tipo_compra}) · Recibidos {c.equipos_recibidos} de {c.cantidad_esperada}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-bold text-[#191818] mb-1">
                Sede destino *
              </label>
              <select
                value={sucursalDestinoId}
                onChange={(e) => setSucursalDestinoId(e.target.value)}
                className="w-full px-3 py-2.5 rounded-xl border border-neutral-300 bg-white text-xs font-semibold text-[#191818]"
              >
                {sucursales.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.nombre}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-bold text-[#191818] mb-1">
                Tracking asociado (opcional)
              </label>
              <select
                value={trackingId}
                onChange={(e) => setTrackingId(e.target.value)}
                className="w-full px-3 py-2.5 rounded-xl border border-neutral-300 bg-white text-xs text-[#191818]"
              >
                <option value="">Sin tracking específico</option>
                {(compraActual?.trackings || []).map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.numero_tracking} ({t.courier || "Courier"}) · {t.estado}
                  </option>
                ))}
              </select>
            </div>

            {compraActual && (
              <div className="md:col-span-4 flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-neutral-100 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="px-2.5 py-1 rounded-full bg-[#FDF0EB] text-[#E85A28] font-bold">
                    {compraActual.numero_compra} · {compraActual.estado}
                  </span>
                  <span className="text-neutral-600">
                    Progreso: <strong className="text-[#191818]">{compraActual.equipos_recibidos} de {compraActual.cantidad_esperada}</strong> recibidos
                  </span>
                </div>
                <label className="inline-flex items-center gap-2 font-semibold text-neutral-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={cerrarCompra}
                    onChange={(e) => setCerrarCompra(e.target.checked)}
                    className="accent-[#E85A28]"
                  />
                  Marcar compra como RECIBIDA (completa) al confirmar
                </label>
              </div>
            )}
          </div>

          {modoCarga === "UNO_A_UNO" ? (
            <form onSubmit={confirmarRecepcionUnoAUno} className="space-y-5">
              {/* Barra de escáner */}
              <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
                  <div className="md:col-span-2">
                    <label className="block text-xs font-bold text-[#191818] mb-1">
                      Escáner de Seriales (pistola láser + Enter)
                    </label>
                    <input
                      ref={refEscanerCompra}
                      type="text"
                      value={inputEscaner}
                      onChange={(e) => setInputEscaner(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          agregarEquipoEscaneado(inputEscaner);
                        }
                      }}
                      placeholder="Escanea el código de barras del serial y presiona Enter..."
                      className="w-full px-3.5 py-2.5 rounded-xl border-2 border-[#E85A28]/50 bg-white font-mono text-sm font-bold text-[#191818]"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-neutral-600 mb-1">
                      Modelo por defecto (opcional)
                    </label>
                    <input
                      type="text"
                      value={modeloDefault}
                      onChange={(e) => setModeloDefault(e.target.value)}
                      placeholder="Ej. Lenovo ThinkPad T14"
                      className="w-full px-3 py-2.5 rounded-xl border border-neutral-300 bg-white text-xs"
                    />
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs font-bold text-neutral-600">
                    Equipos en esta recepción: <strong className="text-[#E85A28]">{equiposLista.length}</strong>
                  </span>
                  <button
                    type="button"
                    onClick={agregarEquipoManual}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-[#E85A28]/40 bg-[#FDF0EB] text-[#E85A28] text-xs font-bold cursor-pointer"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Agregar equipo manualmente
                  </button>
                </div>

                {equiposLista.length > 0 && (
                  <div className="overflow-x-auto border border-neutral-200 rounded-xl">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-[#F6F6F6] border-b border-neutral-200 text-[10px] uppercase text-neutral-600">
                        <tr>
                          <th className="px-2.5 py-2">Serial *</th>
                          <th className="px-2.5 py-2">Modelo / SKU</th>
                          <th className="px-2.5 py-2">RAM / SSD</th>
                          <th className="px-2.5 py-2">Condición</th>
                          <th className="px-2.5 py-2 text-center">Cargador</th>
                          <th className="px-2.5 py-2">Observaciones de llegada</th>
                          <th className="px-2.5 py-2">Estado inicial</th>
                          <th className="px-2.5 py-2 w-8" />
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-neutral-100">
                        {equiposLista.map((eq, idx) => (
                          <tr key={eq.uid} className="bg-white">
                            <td className="px-2 py-2">
                              <input
                                type="text"
                                required
                                value={eq.serial}
                                onChange={(e) => {
                                  const copia = [...equiposLista];
                                  copia[idx] = { ...eq, serial: e.target.value.toUpperCase() };
                                  setEquiposLista(copia);
                                }}
                                className="w-32 px-2 py-1 rounded-lg border border-neutral-300 font-mono font-bold text-xs"
                              />
                            </td>
                            <td className="px-2 py-2">
                              <input
                                type="text"
                                value={eq.modelo}
                                placeholder="Modelo"
                                onChange={(e) => {
                                  const copia = [...equiposLista];
                                  copia[idx] = { ...eq, modelo: e.target.value };
                                  setEquiposLista(copia);
                                }}
                                className="w-36 px-2 py-1 rounded-lg border border-neutral-300 text-xs"
                              />
                            </td>
                            <td className="px-2 py-2 flex gap-1">
                              <input
                                type="text"
                                value={eq.ram}
                                placeholder="RAM"
                                onChange={(e) => {
                                  const copia = [...equiposLista];
                                  copia[idx] = { ...eq, ram: e.target.value };
                                  setEquiposLista(copia);
                                }}
                                className="w-16 px-2 py-1 rounded-lg border border-neutral-300 text-xs"
                              />
                              <input
                                type="text"
                                value={eq.almacenamiento}
                                placeholder="SSD"
                                onChange={(e) => {
                                  const copia = [...equiposLista];
                                  copia[idx] = { ...eq, almacenamiento: e.target.value };
                                  setEquiposLista(copia);
                                }}
                                className="w-20 px-2 py-1 rounded-lg border border-neutral-300 text-xs"
                              />
                            </td>
                            <td className="px-2 py-2">
                              <select
                                value={eq.condicion_llegada}
                                onChange={(e) => {
                                  const copia = [...equiposLista];
                                  copia[idx] = { ...eq, condicion_llegada: e.target.value as CondicionLlegada };
                                  setEquiposLista(copia);
                                }}
                                className="px-2 py-1 rounded-lg border border-neutral-300 bg-white text-xs"
                              >
                                <option value="EXCELENTE">Excelente</option>
                                <option value="BUENO">Bueno</option>
                                <option value="CON_DETALLES">Con detalles</option>
                                <option value="CON_FALLA">Con falla</option>
                              </select>
                            </td>
                            <td className="px-2 py-2 text-center">
                              <input
                                type="checkbox"
                                checked={eq.incluye_cargador}
                                onChange={(e) => {
                                  const copia = [...equiposLista];
                                  copia[idx] = { ...eq, incluye_cargador: e.target.checked };
                                  setEquiposLista(copia);
                                }}
                                className="accent-[#E85A28]"
                                title="¿Trae cargador?"
                              />
                            </td>
                            <td className="px-2 py-2">
                              <input
                                type="text"
                                value={eq.observaciones_llegada}
                                placeholder="Ej. rayón en tapa, sin cargador..."
                                onChange={(e) => {
                                  const copia = [...equiposLista];
                                  copia[idx] = { ...eq, observaciones_llegada: e.target.value };
                                  setEquiposLista(copia);
                                }}
                                className="w-44 px-2 py-1 rounded-lg border border-neutral-300 text-xs"
                              />
                            </td>
                            <td className="px-2 py-2">
                              <select
                                value={eq.estado_inicial}
                                onChange={(e) => {
                                  const copia = [...equiposLista];
                                  copia[idx] = { ...eq, estado_inicial: e.target.value as EstadoInicialEquipo };
                                  setEquiposLista(copia);
                                }}
                                className="px-2 py-1 rounded-lg border border-neutral-300 bg-white text-xs font-semibold"
                              >
                                <option value="POR_PREPARAR">POR_PREPARAR</option>
                                <option value="HOSPITAL">HOSPITAL</option>
                              </select>
                            </td>
                            <td className="px-2 py-2 text-right">
                              <button
                                type="button"
                                onClick={() => setEquiposLista((prev) => prev.filter((x) => x.uid !== eq.uid))}
                                className="p-1 rounded-lg text-red-600 hover:bg-red-50 cursor-pointer"
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

                {/* Bloque de componentes / repuestos por cantidad */}
                <div className="pt-3 border-t border-neutral-100 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-bold text-[#191818]">
                      Componentes, Repuestos o Accesorios por cantidad (opcional)
                    </p>
                    <button
                      type="button"
                      onClick={() =>
                        setComponentesLista((prev) => [
                          ...prev,
                          { uid: `${Date.now()}-${Math.random()}`, articulo_id: "", cantidad: "1", costo_unitario_usd: "0" },
                        ])
                      }
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-neutral-300 bg-white text-xs font-bold text-[#191818] cursor-pointer"
                    >
                      <Plus className="w-3 h-3 text-[#E85A28]" />
                      Agregar componente
                    </button>
                  </div>
                  {componentesLista.map((comp, idx) => (
                    <div key={comp.uid} className="grid grid-cols-1 sm:grid-cols-4 gap-2 items-center">
                      <select
                        value={comp.articulo_id}
                        onChange={(e) => {
                          const copia = [...componentesLista];
                          copia[idx] = { ...comp, articulo_id: e.target.value };
                          setComponentesLista(copia);
                        }}
                        className="sm:col-span-2 px-2.5 py-1.5 rounded-lg border border-neutral-300 bg-white text-xs"
                      >
                        <option value="">Selecciona componente / accesorio...</option>
                        {articulosComponentes.map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.sku} — {a.descripcion}
                          </option>
                        ))}
                      </select>
                      <input
                        type="number"
                        min={1}
                        value={comp.cantidad}
                        onChange={(e) => {
                          const copia = [...componentesLista];
                          copia[idx] = { ...comp, cantidad: e.target.value };
                          setComponentesLista(copia);
                        }}
                        placeholder="Cantidad"
                        className="px-2.5 py-1.5 rounded-lg border border-neutral-300 text-xs"
                      />
                      <div className="flex items-center gap-1.5">
                        <input
                          type="number"
                          step="0.01"
                          min={0}
                          value={comp.costo_unitario_usd}
                          onChange={(e) => {
                            const copia = [...componentesLista];
                            copia[idx] = { ...comp, costo_unitario_usd: e.target.value };
                            setComponentesLista(copia);
                          }}
                          placeholder="Costo USD"
                          className="w-full px-2.5 py-1.5 rounded-lg border border-neutral-300 text-xs"
                        />
                        <button
                          type="button"
                          onClick={() => setComponentesLista((prev) => prev.filter((x) => x.uid !== comp.uid))}
                          className="p-1.5 rounded-lg text-red-600 hover:bg-red-50 cursor-pointer"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    type="submit"
                    disabled={procesandoCompra || !compraId}
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#D14D20] disabled:opacity-50 text-white text-xs font-black shadow-sm cursor-pointer"
                  >
                    <CheckCircle2 className="w-4 h-4" />
                    {procesandoCompra ? "Registrando recepción..." : "Confirmar Recepción Uno a Uno"}
                  </button>
                </div>
              </div>
            </form>
          ) : (
            /* Modo 2: Carga Masiva (.xlsx / .csv) */
            <div className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-black text-[#191818]">
                    Carga Masiva desde Excel (.xlsx) o CSV
                  </h3>
                  <p className="text-xs text-neutral-500">
                    Paso 1: descarga la plantilla y sube tu archivo para validar seriales duplicados y SKUs. Paso 2: confirma atómicamente.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    void descargarPdfApi(
                      "/api/logistica/compras/plantilla-recepcion.xlsx",
                      "tekio_plantilla_recepcion_compras.xlsx"
                    )
                  }
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-neutral-300 bg-white hover:bg-neutral-50 text-xs font-bold text-[#191818] cursor-pointer"
                >
                  <Download className="w-4 h-4 text-[#E85A28]" />
                  Descargar Plantilla .xlsx
                </button>
              </div>

              <div className="rounded-2xl border-2 border-dashed border-neutral-300 bg-[#F6F6F6]/70 p-6 flex flex-wrap items-center justify-between gap-4">
                <div className="text-xs text-neutral-600">
                  {archivoMasivo
                    ? `Archivo seleccionado: ${archivoMasivo.name}`
                    : "Columnas: serial, sku_o_modelo, ram, almacenamiento, condicion_llegada, incluye_cargador, observaciones_llegada, estado_inicial, cantidad"}
                </div>
                <label className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#D14D20] text-white text-xs font-bold cursor-pointer">
                  <Upload className="w-4 h-4" />
                  <span>{analizandoMasiva ? "Validando..." : "Subir .xlsx / .csv"}</span>
                  <input
                    type="file"
                    accept=".xlsx,.csv"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) {
                        setArchivoMasivo(f);
                        void analizarArchivoMasivo(f);
                      }
                    }}
                  />
                </label>
              </div>

              {previewMasiva && (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-bold">
                        Válidas: {previewMasiva.validas}
                      </span>
                      <span className="px-2.5 py-1 rounded-full bg-red-50 text-red-700 border border-red-200 font-bold">
                        Con errores: {previewMasiva.con_errores}
                      </span>
                    </div>
                    <button
                      type="button"
                      disabled={procesandoCompra || previewMasiva.validas === 0 || previewMasiva.con_errores > 0}
                      onClick={() => void confirmarRecepcionMasiva()}
                      className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#D14D20] disabled:opacity-40 text-white text-xs font-black cursor-pointer"
                    >
                      <CheckCircle2 className="w-4 h-4" />
                      {procesandoCompra
                        ? "Guardando lote..."
                        : `Confirmar Carga Masiva (${previewMasiva.validas} filas)`}
                    </button>
                  </div>

                  <div className="overflow-x-auto border border-neutral-200 rounded-xl max-h-72">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-[#F6F6F6] border-b border-neutral-200 text-[10px] uppercase text-neutral-600 sticky top-0">
                        <tr>
                          <th className="px-3 py-2">Fila</th>
                          <th className="px-3 py-2">Tipo</th>
                          <th className="px-3 py-2">Serial / SKU</th>
                          <th className="px-3 py-2">Specs / Condición</th>
                          <th className="px-3 py-2">Estado</th>
                          <th className="px-3 py-2">Validación</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-neutral-100">
                        {previewMasiva.filas.map((f) => (
                          <tr key={f.fila} className={f.valida ? "bg-white" : "bg-red-50/70"}>
                            <td className="px-3 py-2 font-mono">{f.fila}</td>
                            <td className="px-3 py-2 font-bold">{f.tipo}</td>
                            <td className="px-3 py-2">
                              <p className="font-mono font-bold text-[#191818]">{f.serial || "Por cantidad"}</p>
                              <p className="text-[10px] text-neutral-500">{f.sku_o_modelo}</p>
                            </td>
                            <td className="px-3 py-2 text-[11px]">
                              {[f.ram, f.almacenamiento, f.condicion_llegada].filter(Boolean).join(" · ")}
                            </td>
                            <td className="px-3 py-2 font-semibold">{f.estado_inicial}</td>
                            <td className="px-3 py-2">
                              {f.valida ? (
                                <span className="text-emerald-700 font-bold">OK</span>
                              ) : (
                                <span className="text-red-700 font-bold">{f.errores.join(" · ")}</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        /* Flujo existente: Guía de Casillero / Doble Verificación */
        <div className="space-y-4">
          {resultadoGuia && (
            <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-5 space-y-2 text-xs text-emerald-800">
              <div className="flex items-center gap-2 font-bold text-sm">
                <CheckCircle2 className="w-5 h-5" />
                <span>
                  Guía {resultadoGuia.numero_guia} recibida · {resultadoGuia.equipos_recibidos} equipo(s) · Verificado por {resultadoGuia.verificado_por}
                </span>
              </div>
            </div>
          )}

          <form onSubmit={manejarConfirmarGuia} className="bg-white/85 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-5 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-bold text-[#191818] mb-1">Guía en tránsito *</label>
                <select
                  value={guiaId}
                  onChange={(e) => setGuiaId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-xs"
                >
                  <option value="">Selecciona una guía...</option>
                  {guias.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.numero_guia} · {g.casillero || "Casillero"} ({g.modalidad})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-bold text-[#191818] mb-1">Verificador (doble control) *</label>
                <select
                  value={verificadorId}
                  onChange={(e) => setVerificadorId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-xs"
                >
                  <option value="">Selecciona verificador...</option>
                  {verificadores.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.nombre} ({v.rol})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-bold text-[#191818] mb-1">Fecha real llegada</label>
                <input
                  type="date"
                  value={fechaReal}
                  onChange={(e) => setFechaReal(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-xs"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-[#191818] mb-1">Escanear seriales de la guía</label>
              <input
                ref={refInputGuia}
                type="text"
                value={inputSerialGuia}
                onChange={(e) => setInputSerialGuia(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    agregarSerialGuia(inputSerialGuia);
                  }
                }}
                placeholder="Escanea serial + Enter..."
                className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white font-mono text-xs"
              />
            </div>

            {serialesGuia.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {serialesGuia.map((sn) => (
                  <span
                    key={sn}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-[#FDF0EB] text-[#E85A28] font-mono text-xs font-bold"
                  >
                    {sn}
                    <button
                      type="button"
                      onClick={() => setSerialesGuia((prev) => prev.filter((x) => x !== sn))}
                      className="cursor-pointer"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={procesandoGuia || !guiaId || !verificadorId}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#D14D20] disabled:opacity-50 text-white text-xs font-black cursor-pointer"
              >
                <ShieldCheck className="w-4 h-4" />
                {procesandoGuia ? "Confirmando guía..." : "Confirmar Recepción de Guía"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

export default function PaginaRecepcion() {
  return (
    <Suspense fallback={<div className="h-40 rounded-2xl bg-white/70 animate-pulse" />}>
      <ContenidoRecepcionUnificada />
    </Suspense>
  );
}
