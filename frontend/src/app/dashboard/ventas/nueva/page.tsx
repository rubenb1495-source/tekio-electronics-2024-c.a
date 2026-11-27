"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronDown,
  Copy,
  ExternalLink,
  FileDown,
  Gift,
  MessageSquare,
  Plus,
  Printer,
  Search,
  ShoppingCart,
  Trash2,
  UserPlus,
  Wrench,
  X,
} from "lucide-react";
import { usarSesion } from "@/contexto/SesionContexto";
import {
  copiarTextoPortapapeles,
  formatearWhatsAppVenta,
} from "@/lib/whatsapp";
import {
  ErrorApi,
  abrirPdfEnPestanaApi,
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
  UsuarioOperativo,
  VentaResumen,
} from "@/tipos/finanzas";
import type { EquipoInventario, Tercero } from "@/tipos/logistica";

interface ItemCarrito {
  tipo: "EQUIPO" | "ARTICULO" | "SERVICIO";
  equipo_id?: number;
  articulo_id?: number;
  etiqueta: string;
  descripcion_servicio?: string;
  cantidad: number;
  precio_promo_usd: number;
  precio_pactado_usd?: number;
  precio_regular_fijo_usd?: number | null;
}

interface FilaPago {
  instrumento_id: string;
  monto_moneda_origen: string;
  referencia: string;
  parte_pago_serial: string;
  parte_pago_modelo: string;
}

const ROLES_VENDEDORES = new Set([
  "ASESORA",
  "LIDER",
  "TECNICO",
  "ADMINISTRACION",
  "DIRECCION",
]);

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
  const [usuariosOperativos, setUsuariosOperativos] = useState<
    UsuarioOperativo[]
  >([]);
  const [clientes, setClientes] = useState<Tercero[]>([]);
  const [clienteId, setClienteId] = useState("");
  const [busquedaCliente, setBusquedaCliente] = useState("");
  const [menuClientesAbierto, setMenuClientesAbierto] = useState(false);
  const contenedorClientesRef = useRef<HTMLDivElement | null>(null);

  // Modal + Nuevo Cliente (Natural / Jurídico)
  const [modalCliente, setModalCliente] = useState(false);
  const [cliTipoPersona, setCliTipoPersona] = useState<"NATURAL" | "JURIDICO">(
    "NATURAL"
  );
  const [cliTipoDoc, setCliTipoDoc] = useState<"V" | "E" | "P" | "J" | "G">(
    "V"
  );
  const [cliDocumento, setCliDocumento] = useState("");
  const [cliNombre, setCliNombre] = useState("");
  const [cliTelefono, setCliTelefono] = useState("");
  const [cliDireccion, setCliDireccion] = useState("");
  const [guardandoCliente, setGuardandoCliente] = useState(false);
  const [errorModalCliente, setErrorModalCliente] = useState<string | null>(
    null
  );
  const [tasaHoy, setTasaHoy] = useState<TasaHoy | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [sucursalId, setSucursalId] = useState("");
  const [asesorId, setAsesorId] = useState("");
  const [tecnicoId, setTecnicoId] = useState("");
  const [canalVisita, setCanalVisita] = useState("Tienda");
  const [entrega, setEntrega] = useState("Tienda");
  const [quedaConSaldo, setQuedaConSaldo] = useState(false);
  const [nota, setNota] = useState("");
  const [cotizacionOrigenId, setCotizacionOrigenId] = useState<number | null>(null);
  const [cotizacionNumero, setCotizacionNumero] = useState<string | null>(null);

  // Planilla Delivery
  const [delNombre, setDelNombre] = useState("");
  const [delTelefono, setDelTelefono] = useState("");
  const [delDireccion, setDelDireccion] = useState("");
  const [delReferencia, setDelReferencia] = useState("");
  const [delZona, setDelZona] = useState("");
  const [delHorario, setDelHorario] = useState("");

  // Planilla Envío Nacional (Encomienda)
  const [envDestinatario, setEnvDestinatario] = useState("");
  const [envCedula, setEnvCedula] = useState("");
  const [envTelefono, setEnvTelefono] = useState("");
  const [envEmpresa, setEnvEmpresa] = useState("MRW");
  const [envEmpresaOtra, setEnvEmpresaOtra] = useState("");
  const [envEstadoCiudad, setEnvEstadoCiudad] = useState("");
  const [envAgencia, setEnvAgencia] = useState("");
  const [envDireccionOficina, setEnvDireccionOficina] = useState("");
  const [envModalidad, setEnvModalidad] = useState("Cobro en destino");

  const [carrito, setCarrito] = useState<ItemCarrito[]>([]);
  const [equipoSel, setEquipoSel] = useState("");
  const [busquedaEquipo, setBusquedaEquipo] = useState("");
  const [menuEquiposAbierto, setMenuEquiposAbierto] = useState(false);
  const contenedorSelectorEquiposRef = useRef<HTMLDivElement | null>(null);
  const [articuloSel, setArticuloSel] = useState("");
  const [busquedaSku, setBusquedaSku] = useState("");
  const [menuSkuAbierto, setMenuSkuAbierto] = useState(false);
  const contenedorSkuRef = useRef<HTMLDivElement | null>(null);

  // Panel rápido de Servicio Técnico / Mano de Obra
  const [panelServicioAbierto, setPanelServicioAbierto] = useState(false);
  const [servicioSel, setServicioSel] = useState("");
  const [servicioDescripcion, setServicioDescripcion] = useState("");
  const [servicioMontoPromo, setServicioMontoPromo] = useState("");

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
  const [casheaNumeroOrden, setCasheaNumeroOrden] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [ventaCreada, setVentaCreada] = useState<VentaResumen | null>(null);
  const [copiado, setCopiado] = useState(false);
  const [abriendoPdf, setAbriendoPdf] = useState(false);
  const inicioPosRef = useRef<HTMLDivElement | null>(null);
  const panelPostVentaRef = useRef<HTMLDivElement | null>(null);

  // Cerrar los desplegables al hacer clic fuera
  useEffect(() => {
    const manejarClickFuera = (ev: MouseEvent) => {
      const target = ev.target as Node;
      if (
        contenedorSelectorEquiposRef.current &&
        !contenedorSelectorEquiposRef.current.contains(target)
      ) {
        setMenuEquiposAbierto(false);
      }
      if (
        contenedorClientesRef.current &&
        !contenedorClientesRef.current.contains(target)
      ) {
        setMenuClientesAbierto(false);
      }
      if (
        contenedorSkuRef.current &&
        !contenedorSkuRef.current.contains(target)
      ) {
        setMenuSkuAbierto(false);
      }
    };
    document.addEventListener("mousedown", manejarClickFuera);
    return () => document.removeEventListener("mousedown", manejarClickFuera);
  }, []);

  const cargarBase = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [respSuc, respInst, respCat, respOps, respCli, respTasa] =
        await Promise.all([
          solicitarApi<Sucursal[]>("/api/sucursales"),
          solicitarApi<InstrumentoFinanciero[]>("/api/finanzas/instrumentos"),
          solicitarApi<CatalogoPaginado>("/api/catalogo?por_pagina=100"),
          solicitarApi<UsuarioOperativo[]>("/api/usuarios/operativos").catch(
            () => []
          ),
          solicitarApi<Tercero[]>("/api/clientes").catch(() =>
            solicitarApi<Tercero[]>("/api/logistica/terceros?tipo=CLIENTE").catch(
              () => []
            )
          ),
          solicitarApi<TasaHoy>("/api/tasas/hoy").catch(() => null),
        ]);
      const activas = respSuc.filter((s) => s.estado === "ACTIVA");
      setSucursales(activas);
      setInstrumentos(respInst);
      setCatalogo(respCat.elementos);
      setUsuariosOperativos(respOps);
      setClientes(respCli);
      setTasaHoy(respTasa);

      if (usuario?.sucursal && usuario.sucursal.estado === "ACTIVA") {
        setSucursalId(String(usuario.sucursal.id));
      } else if (activas[0]) {
        setSucursalId(String(activas[0].id));
      }

      // Preseleccionar Asesor si el usuario autenticado es ASESORA, LIDER o TECNICO
      if (
        usuario &&
        (usuario.rol === "ASESORA" ||
          usuario.rol === "LIDER" ||
          usuario.rol === "TECNICO")
      ) {
        setAsesorId(String(usuario.id));
      } else {
        setAsesorId("");
      }

      if (usuario && usuario.rol === "TECNICO") {
        setTecnicoId(String(usuario.id));
      }

      const primerServicio = respCat.elementos.find(
        (a) => a.tipo === "SERVICIO"
      );
      if (primerServicio) {
        setServicioSel(String(primerServicio.id));
        setServicioMontoPromo(
          primerServicio.precio_promo_usd > 0
            ? String(primerServicio.precio_promo_usd)
            : ""
        );
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

  // Precargar datos si se llega desde "Convertir a Venta" (?cotizacion_id=ID)
  useEffect(() => {
    if (cargando || typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const cotIdStr = params.get("cotizacion_id");
    if (!cotIdStr || cotizacionOrigenId !== null) return;
    const cotIdNum = Number(cotIdStr);
    if (!Number.isFinite(cotIdNum) || cotIdNum <= 0) return;

    solicitarApi<{
      id: number;
      numero_cotizacion: string;
      sucursal_id: number;
      cliente_id: number | null;
      cliente: string;
      cliente_rif: string;
      asesor_id: number | null;
      nota: string;
      detalles: {
        equipo_id: number | null;
        serial: string | null;
        articulo_id: number | null;
        descripcion: string;
        descripcion_servicio: string;
        cantidad: number;
        precio_promo_usd: number;
        precio_pactado_usd: number | null;
      }[];
    }>(`/api/cotizaciones/${cotIdNum}`)
      .then((cot) => {
        setCotizacionOrigenId(cot.id);
        setCotizacionNumero(cot.numero_cotizacion);
        if (cot.sucursal_id) setSucursalId(String(cot.sucursal_id));
        if (cot.cliente_id) {
          setClienteId(String(cot.cliente_id));
          setBusquedaCliente(
            `${cot.cliente}${cot.cliente_rif ? ` (${cot.cliente_rif})` : ""}`
          );
        }
        if (cot.asesor_id) setAsesorId(String(cot.asesor_id));
        if (cot.nota) setNota(cot.nota);

        const itemsCargados: ItemCarrito[] = cot.detalles
          .filter((d) => d.equipo_id !== null || d.articulo_id !== null)
          .map((d) => ({
            tipo: d.equipo_id ? "EQUIPO" : "ARTICULO",
            equipo_id: d.equipo_id ?? undefined,
            articulo_id: d.articulo_id ?? undefined,
            etiqueta: d.serial
              ? `${d.serial} — ${d.descripcion}`
              : d.descripcion,
            descripcion_servicio: d.descripcion_servicio || "",
            cantidad: d.cantidad,
            precio_promo_usd: d.precio_promo_usd,
            precio_pactado_usd:
              d.precio_pactado_usd !== null
                ? d.precio_pactado_usd
                : d.precio_promo_usd,
          }));
        if (itemsCargados.length > 0) {
          setCarrito(itemsCargados);
        }
      })
      .catch(() => {});
  }, [cargando, cotizacionOrigenId]);

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

  const asesoresDisponibles = useMemo(
    () => usuariosOperativos.filter((u) => ROLES_VENDEDORES.has(u.rol)),
    [usuariosOperativos]
  );

  const tecnicosDisponibles = useMemo(
    () => usuariosOperativos.filter((u) => u.rol === "TECNICO"),
    [usuariosOperativos]
  );

  const serviciosCatalogo = useMemo(
    () => catalogo.filter((a) => a.tipo === "SERVICIO"),
    [catalogo]
  );

  const productosCatalogo = useMemo(
    () => catalogo.filter((a) => a.tipo !== "SERVICIO"),
    [catalogo]
  );

  const clientesFiltrados = useMemo(() => {
    const q = busquedaCliente.trim().toLowerCase();
    if (!q) return clientes.slice(0, 30);
    return clientes
      .filter((c) =>
        [
          c.nombre,
          c.rif_cedula || "",
          c.documento || "",
          c.telefono || "",
          c.direccion || "",
        ]
          .join(" ")
          .toLowerCase()
          .includes(q)
      )
      .slice(0, 30);
  }, [clientes, busquedaCliente]);

  const clienteSeleccionadoObj = useMemo(
    () => clientes.find((c) => String(c.id) === clienteId) ?? null,
    [clientes, clienteId]
  );

  const productosFiltrados = useMemo(() => {
    const q = busquedaSku.trim().toLowerCase();
    if (!q) return productosCatalogo;
    return productosCatalogo.filter((a) =>
      `${a.sku} ${a.descripcion} ${a.categoria}`.toLowerCase().includes(q)
    );
  }, [productosCatalogo, busquedaSku]);

  const tieneServicioTecnico = useMemo(
    () => carrito.some((item) => item.tipo === "SERVICIO"),
    [carrito]
  );

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
      simulacion?.recargo_porcentaje ?? tasaHoy?.recargo_porcentaje ?? 0,
    [simulacion?.recargo_porcentaje, tasaHoy?.recargo_porcentaje]
  );

  const totalRegularLocal = useMemo(() => {
    const factor = 1 + recargoPctActual / 100;
    return redondear2(
      carrito.reduce((acc, item) => {
        const promoUnit =
          item.precio_pactado_usd !== undefined
            ? item.precio_pactado_usd
            : item.precio_promo_usd;
        const unitRegular =
          item.precio_regular_fijo_usd != null &&
          item.precio_pactado_usd === undefined
            ? item.precio_regular_fijo_usd
            : redondear2(promoUnit * factor);
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
              precio_pactado_usd:
                c.precio_pactado_usd !== undefined
                  ? c.precio_pactado_usd
                  : null,
              descripcion_servicio: c.descripcion_servicio ?? "",
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
        tipo: art.tipo === "SERVICIO" ? "SERVICIO" : "ARTICULO",
        articulo_id: art.id,
        etiqueta: `${art.sku} — ${art.descripcion}`,
        descripcion_servicio: "",
        cantidad: 1,
        precio_promo_usd: art.precio_promo_usd,
        precio_regular_fijo_usd: art.precio_regular_fijo_usd,
      },
    ]);
    setArticuloSel("");
  };

  const agregarServicioTecnico = () => {
    const srv = serviciosCatalogo.find((s) => String(s.id) === servicioSel);
    if (!srv) {
      setError("Selecciona un código de Servicio Técnico del catálogo.");
      return;
    }
    const montoNum = Number(servicioMontoPromo);
    if (!Number.isFinite(montoNum) || montoNum < 0) {
      setError("Ingresa un monto válido en USD Promo para la mano de obra.");
      return;
    }
    setError(null);
    setCarrito((prev) => [
      ...prev,
      {
        tipo: "SERVICIO",
        articulo_id: srv.id,
        etiqueta: `${srv.sku} — ${srv.descripcion}`,
        descripcion_servicio: servicioDescripcion.trim(),
        cantidad: 1,
        precio_promo_usd: montoNum,
        precio_pactado_usd: montoNum,
      },
    ]);
    setServicioDescripcion("");
    setPanelServicioAbierto(false);
  };

  const registrarVenta = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (guardando || ventaCreada) return;
    setError(null);
    if (carrito.length === 0) {
      setError("Agrega al menos un equipo, repuesto o servicio al carrito.");
      return;
    }

    if (tieneServicioTecnico && !tecnicoId) {
      setError(
        "Debes seleccionar el Técnico responsable cuando la venta incluye Servicio Técnico / Mano de Obra."
      );
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

    const datosEntregaPayload =
      entrega === "DELIVERY"
        ? {
            nombre_recibe: delNombre.trim(),
            telefono: delTelefono.trim(),
            direccion: delDireccion.trim(),
            punto_referencia: delReferencia.trim(),
            zona_municipio: delZona.trim(),
            horario_instrucciones: delHorario.trim(),
          }
        : entrega === "ENVIO"
        ? {
            destinatario: envDestinatario.trim(),
            cedula: envCedula.trim(),
            telefono: envTelefono.trim(),
            empresa_envio:
              envEmpresa === "Otra"
                ? envEmpresaOtra.trim() || "Otra"
                : envEmpresa,
            estado_ciudad: envEstadoCiudad.trim(),
            agencia_oficina: envAgencia.trim(),
            direccion_oficina: envDireccionOficina.trim(),
            modalidad: envModalidad,
          }
        : null;

    setGuardando(true);
    try {
      const creada = await solicitarApi<VentaResumen>("/api/ventas", {
        method: "POST",
        body: JSON.stringify({
          sucursal_id: Number(sucursalId),
          cliente_id: clienteId ? Number(clienteId) : null,
          asesor_id: asesorId ? Number(asesorId) : null,
          tecnico_id: tecnicoId ? Number(tecnicoId) : null,
          canal_visita: canalVisita,
          entrega,
          datos_entrega: datosEntregaPayload,
          items: carrito.map((c) => ({
            equipo_id: c.equipo_id ?? null,
            articulo_id: c.articulo_id ?? null,
            cantidad: c.cantidad,
            precio_pactado_usd:
              c.precio_pactado_usd !== undefined ? c.precio_pactado_usd : null,
            descripcion_servicio: (c.descripcion_servicio ?? "").trim(),
          })),
          pagos: pagosValidos,
          queda_con_saldo: quedaConSaldo,
          cashea_numero_orden: usaCasheaLocal ? casheaNumeroOrden.trim().toUpperCase() : null,
          nota: nota.trim(),
          cotizacion_id: cotizacionOrigenId,
        }),
      });
      setVentaCreada(creada);
      setCopiado(false);
      // Refrescar equipos disponibles de la sucursal para excluir seriales recién vendidos
      if (sucursalId) {
        solicitarApi<EquipoInventario[]>(
          `/api/logistica/inventario/equipos?sucursal_id=${sucursalId}&estado=LISTO`
        )
          .then((lista) => setEquiposListos(lista))
          .catch(() => {});
      }
      // Desplazar suavemente hacia el panel fijo de acciones post-venta
      setTimeout(() => {
        panelPostVentaRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      }, 80);
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "No se pudo registrar la venta."
      );
    } finally {
      setGuardando(false);
    }
  };

  const normalizarTelefonoWa = (telefono?: string | null): string | null => {
    if (!telefono) return null;
    const soloDigitos = telefono.replace(/\D/g, "");
    if (soloDigitos.length < 10) return null;
    if (soloDigitos.startsWith("0") && soloDigitos.length === 11) {
      return `58${soloDigitos.slice(1)}`;
    }
    if (soloDigitos.length === 10 && soloDigitos.startsWith("4")) {
      return `58${soloDigitos}`;
    }
    return soloDigitos;
  };

  const abrirNotaParaImprimir = async (venta: VentaResumen) => {
    setAbriendoPdf(true);
    setError(null);
    try {
      await abrirPdfEnPestanaApi(`/api/ventas/${venta.id}/nota-pdf`);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo abrir la Nota de Entrega para imprimir."
      );
    } finally {
      setAbriendoPdf(false);
    }
  };

  const iniciarNuevaVenta = () => {
    setVentaCreada(null);
    setCasheaNumeroOrden("");
    setCopiado(false);
    setError(null);
    setCarrito([]);
    setSimulacion(null);
    setClienteId("");
    setBusquedaCliente("");
    setMenuClientesAbierto(false);
    setEquipoSel("");
    setBusquedaEquipo("");
    setMenuEquiposAbierto(false);
    setArticuloSel("");
    setBusquedaSku("");
    setMenuSkuAbierto(false);
    setServicioDescripcion("");
    setPanelServicioAbierto(false);
    setCanalVisita("Tienda");
    setEntrega("Tienda");
    setQuedaConSaldo(false);
    setNota("");
    setCotizacionOrigenId(null);
    setCotizacionNumero(null);
    setDelNombre("");
    setDelTelefono("");
    setDelDireccion("");
    setDelReferencia("");
    setDelZona("");
    setDelHorario("");
    setEnvDestinatario("");
    setEnvCedula("");
    setEnvTelefono("");
    setEnvEmpresa("MRW");
    setEnvEmpresaOtra("");
    setEnvEstadoCiudad("");
    setEnvAgencia("");
    setEnvDireccionOficina("");
    setEnvModalidad("Cobro en destino");
    if (
      usuario &&
      (usuario.rol === "ASESORA" ||
        usuario.rol === "LIDER" ||
        usuario.rol === "TECNICO")
    ) {
      setAsesorId(String(usuario.id));
    } else {
      setAsesorId("");
    }
    setTecnicoId(usuario && usuario.rol === "TECNICO" ? String(usuario.id) : "");
    setPagos([
      {
        instrumento_id: instrumentos[0] ? String(instrumentos[0].id) : "",
        monto_moneda_origen: "",
        referencia: "",
        parte_pago_serial: "",
        parte_pago_modelo: "",
      },
    ]);
    setTimeout(() => {
      if (inicioPosRef.current) {
        inicioPosRef.current.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      } else {
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    }, 40);
  };

  const copiarWhatsApp = async (venta: VentaResumen) => {
    const texto = formatearWhatsAppVenta(venta);
    await copiarTextoPortapapeles(texto);
    setCopiado(true);
    setTimeout(() => setCopiado(false), 2500);
  };

  const abrirModalNuevoCliente = () => {
    setErrorModalCliente(null);
    setCliTipoPersona("NATURAL");
    setCliTipoDoc("V");
    setCliDocumento("");
    setCliNombre("");
    setCliTelefono("");
    setCliDireccion("");
    setModalCliente(true);
  };

  const manejarCrearCliente = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorModalCliente(null);
    setGuardandoCliente(true);
    try {
      const creado = await solicitarApi<Tercero>("/api/clientes", {
        method: "POST",
        body: JSON.stringify({
          tipo_persona: cliTipoPersona,
          tipo_documento: cliTipoDoc,
          documento: cliDocumento.trim(),
          nombre: cliNombre.trim(),
          telefono: cliTelefono.trim(),
          direccion: cliDireccion.trim(),
        }),
      });
      setClientes((prev) => [creado, ...prev]);
      setClienteId(String(creado.id));
      setBusquedaCliente(
        `${creado.nombre}${creado.rif_cedula ? ` (${creado.rif_cedula})` : ""}`
      );
      setMenuClientesAbierto(false);
      setModalCliente(false);
    } catch (err) {
      setErrorModalCliente(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo registrar el cliente."
      );
    } finally {
      setGuardandoCliente(false);
    }
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
    <div ref={inicioPosRef} className="space-y-6 min-w-0">
      <div>
        <h2 className="text-2xl font-black text-slate-900 flex items-center gap-2">
          <ShoppingCart className="w-6 h-6 text-[#E85A28] shrink-0" />
          Punto de Venta (POS) · Pagos Mixtos y Servicio Técnico
        </h2>
        <p className="text-sm text-slate-500">
          Combina equipos por serial, repuestos/componentes y mano de obra de
          servicio técnico con cálculo en vivo de Precio Promo y Regular.
        </p>
      </div>

      {cotizacionNumero && (
        <div className="flex items-center justify-between gap-2.5 p-3.5 rounded-xl bg-tekio-naranja-suave/80 border border-tekio-naranja/30 text-sm text-tekio-carbon">
          <span>
            Convirtiendo cotización <strong>{cotizacionNumero}</strong> a venta. Al registrar el pago se marcará automáticamente como <strong>CONVERTIDA</strong>.
          </span>
        </div>
      )}

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
        {/* Columna izquierda: Datos, Asesor/Técnico y Carrito */}
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
                <option value="TikTok">TikTok</option>
                <option value="Facebook">Facebook</option>
                <option value="Otros">Otros</option>
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
                <option value="DELIVERY">Delivery</option>
                <option value="ENVIO">Envío nacional (Encomienda)</option>
              </select>
            </div>
          </div>

          {/* Planilla Delivery */}
          {entrega === "DELIVERY" && (
            <div className="p-4 rounded-xl bg-sky-50/70 border border-sky-200 space-y-2.5">
              <p className="text-xs font-black text-sky-900 uppercase">
                Planilla de Delivery
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                <input
                  type="text"
                  required
                  value={delNombre}
                  onChange={(e) => setDelNombre(e.target.value)}
                  placeholder="Nombre de quien recibe *"
                  className="w-full min-w-0 px-3 py-1.5 rounded-lg border border-sky-300 text-xs bg-white"
                />
                <input
                  type="text"
                  required
                  value={delTelefono}
                  onChange={(e) => setDelTelefono(e.target.value)}
                  placeholder="Teléfono de contacto *"
                  className="w-full min-w-0 px-3 py-1.5 rounded-lg border border-sky-300 text-xs bg-white"
                />
                <input
                  type="text"
                  required
                  value={delDireccion}
                  onChange={(e) => setDelDireccion(e.target.value)}
                  placeholder="Dirección exacta de entrega *"
                  className="sm:col-span-2 w-full min-w-0 px-3 py-1.5 rounded-lg border border-sky-300 text-xs bg-white"
                />
                <input
                  type="text"
                  value={delReferencia}
                  onChange={(e) => setDelReferencia(e.target.value)}
                  placeholder="Punto de referencia"
                  className="w-full min-w-0 px-3 py-1.5 rounded-lg border border-sky-300 text-xs bg-white"
                />
                <input
                  type="text"
                  value={delZona}
                  onChange={(e) => setDelZona(e.target.value)}
                  placeholder="Zona / Municipio"
                  className="w-full min-w-0 px-3 py-1.5 rounded-lg border border-sky-300 text-xs bg-white"
                />
                <input
                  type="text"
                  value={delHorario}
                  onChange={(e) => setDelHorario(e.target.value)}
                  placeholder="Horario / Instrucciones de entrega"
                  className="sm:col-span-2 w-full min-w-0 px-3 py-1.5 rounded-lg border border-sky-300 text-xs bg-white"
                />
              </div>
            </div>
          )}

          {/* Planilla Envío Nacional (Encomienda) */}
          {entrega === "ENVIO" && (
            <div className="p-4 rounded-xl bg-amber-50/70 border border-amber-200 space-y-2.5">
              <p className="text-xs font-black text-amber-900 uppercase">
                Planilla de Envío Nacional (Encomienda)
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                <input
                  type="text"
                  required
                  value={envDestinatario}
                  onChange={(e) => setEnvDestinatario(e.target.value)}
                  placeholder="Nombre completo del destinatario *"
                  className="w-full min-w-0 px-3 py-1.5 rounded-lg border border-amber-300 text-xs bg-white"
                />
                <input
                  type="text"
                  required
                  value={envCedula}
                  onChange={(e) => setEnvCedula(e.target.value)}
                  placeholder="Cédula de Identidad *"
                  className="w-full min-w-0 px-3 py-1.5 rounded-lg border border-amber-300 text-xs bg-white font-mono"
                />
                <input
                  type="text"
                  required
                  value={envTelefono}
                  onChange={(e) => setEnvTelefono(e.target.value)}
                  placeholder="Teléfono de contacto *"
                  className="w-full min-w-0 px-3 py-1.5 rounded-lg border border-amber-300 text-xs bg-white"
                />
                <select
                  value={envEmpresa}
                  onChange={(e) => setEnvEmpresa(e.target.value)}
                  className="w-full min-w-0 px-3 py-1.5 rounded-lg border border-amber-300 text-xs bg-white"
                >
                  <option value="MRW">MRW</option>
                  <option value="Zoom">Zoom</option>
                  <option value="Tealca">Tealca</option>
                  <option value="Domesa">Domesa</option>
                  <option value="Liberty Express">Liberty Express</option>
                  <option value="Otra">Otra empresa</option>
                </select>
                {envEmpresa === "Otra" && (
                  <input
                    type="text"
                    required
                    value={envEmpresaOtra}
                    onChange={(e) => setEnvEmpresaOtra(e.target.value)}
                    placeholder="Indicar nombre de la empresa *"
                    className="sm:col-span-2 w-full min-w-0 px-3 py-1.5 rounded-lg border border-amber-300 text-xs bg-white"
                  />
                )}
                <input
                  type="text"
                  required
                  value={envEstadoCiudad}
                  onChange={(e) => setEnvEstadoCiudad(e.target.value)}
                  placeholder="Estado / Ciudad *"
                  className="w-full min-w-0 px-3 py-1.5 rounded-lg border border-amber-300 text-xs bg-white"
                />
                <input
                  type="text"
                  required
                  value={envAgencia}
                  onChange={(e) => setEnvAgencia(e.target.value)}
                  placeholder="Código o nombre de la agencia/oficina *"
                  className="w-full min-w-0 px-3 py-1.5 rounded-lg border border-amber-300 text-xs bg-white"
                />
                <input
                  type="text"
                  required
                  value={envDireccionOficina}
                  onChange={(e) => setEnvDireccionOficina(e.target.value)}
                  placeholder="Dirección exacta de la oficina de envío *"
                  className="sm:col-span-2 w-full min-w-0 px-3 py-1.5 rounded-lg border border-amber-300 text-xs bg-white"
                />
                <select
                  value={envModalidad}
                  onChange={(e) => setEnvModalidad(e.target.value)}
                  className="sm:col-span-2 w-full min-w-0 px-3 py-1.5 rounded-lg border border-amber-300 text-xs bg-white"
                >
                  <option value="Cobro en destino">Cobro en destino</option>
                  <option value="Prepagado">Prepagado</option>
                  <option value="Asegurado">Asegurado</option>
                </select>
              </div>
            </div>
          )}

          {/* Buscador interactivo de Cliente */}
          <div
            ref={contenedorClientesRef}
            className="relative z-45 space-y-1 min-w-0"
          >
            <label className="block text-xs font-bold text-slate-700">
              Cliente{" "}
              <span className="text-slate-400 font-normal">
                (Opcional — por defecto Cliente general)
              </span>
            </label>
            <div className="flex gap-2 min-w-0">
              <div className="relative flex-1 min-w-0">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="text"
                  value={
                    clienteSeleccionadoObj && !menuClientesAbierto
                      ? `${clienteSeleccionadoObj.nombre}${clienteSeleccionadoObj.rif_cedula ? ` (${clienteSeleccionadoObj.rif_cedula})` : ""}`
                      : busquedaCliente
                  }
                  onFocus={() => setMenuClientesAbierto(true)}
                  onChange={(e) => {
                    setClienteId("");
                    setBusquedaCliente(e.target.value);
                    setMenuClientesAbierto(true);
                  }}
                  placeholder={`Buscar cliente por nombre, cédula/RIF o teléfono (${clientes.length})...`}
                  className="w-full min-w-0 pl-9 pr-14 py-2 rounded-xl border border-slate-300 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#E85A28]/30 focus:border-[#E85A28]"
                />
                {(clienteId || busquedaCliente) && (
                  <button
                    type="button"
                    onClick={() => {
                      setClienteId("");
                      setBusquedaCliente("");
                      setMenuClientesAbierto(false);
                    }}
                    aria-label="Limpiar cliente"
                    className="absolute right-8 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 cursor-pointer"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setMenuClientesAbierto((prev) => !prev)}
                  aria-label="Desplegar clientes"
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-500 hover:text-slate-700 cursor-pointer"
                >
                  <ChevronDown className="w-4 h-4" />
                </button>
              </div>
              <button
                type="button"
                onClick={abrirModalNuevoCliente}
                className="shrink-0 inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold cursor-pointer"
              >
                <UserPlus className="w-3.5 h-3.5" />
                + Nuevo Cliente
              </button>
            </div>
            {menuClientesAbierto && (
              <div className="absolute left-0 right-0 top-full mt-1 z-50 bg-white border border-slate-200 rounded-xl shadow-xl max-h-60 overflow-y-auto divide-y divide-slate-100">
                <button
                  type="button"
                  onClick={() => {
                    setClienteId("");
                    setBusquedaCliente("");
                    setMenuClientesAbierto(false);
                  }}
                  className="w-full text-left px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 cursor-pointer"
                >
                  Cliente general (sin ficha)
                </button>
                {clientesFiltrados.length === 0 ? (
                  <div className="p-3 text-center text-xs text-slate-500">
                    No se encontraron clientes que coincidan.
                  </div>
                ) : (
                  clientesFiltrados.map((cli) => (
                    <button
                      key={cli.id}
                      type="button"
                      onClick={() => {
                        setClienteId(String(cli.id));
                        setBusquedaCliente(
                          `${cli.nombre}${cli.rif_cedula ? ` (${cli.rif_cedula})` : ""}`
                        );
                        setMenuClientesAbierto(false);
                      }}
                      className="w-full text-left px-3 py-2 hover:bg-orange-50/70 cursor-pointer"
                    >
                      <p className="text-xs font-bold text-slate-900">
                        {cli.nombre}
                      </p>
                      <p className="text-[11px] text-slate-500">
                        {[
                          cli.rif_cedula
                            ? `${cli.tipo_persona === "JURIDICO" ? "RIF" : "Cédula de Identidad"}: ${cli.rif_cedula}`
                            : null,
                          cli.telefono,
                        ]
                          .filter(Boolean)
                          .join(" · ") || "Sin datos adicionales"}
                      </p>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Selectores de Asesor y Técnico */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
            <div className="min-w-0">
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Asesor de venta
              </label>
              <select
                value={asesorId}
                onChange={(e) => setAsesorId(e.target.value)}
                className="w-full min-w-0 px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
              >
                <option value="">Tienda (Sin comisión)</option>
                {asesoresDisponibles.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.nombre} (
                    {u.es_lider || u.rol === "LIDER"
                      ? "LÍDER · Multi-tienda"
                      : u.rol}
                    )
                  </option>
                ))}
              </select>
            </div>
            <div className="min-w-0">
              <label
                className={`block text-xs font-bold mb-1 ${
                  tieneServicioTecnico && !tecnicoId
                    ? "text-red-700"
                    : "text-slate-700"
                }`}
              >
                Técnico responsable{" "}
                {tieneServicioTecnico ? (
                  <span className="text-red-600">* (Obligatorio por ST)</span>
                ) : (
                  <span className="text-slate-400 font-normal">(Opcional)</span>
                )}
              </label>
              <select
                required={tieneServicioTecnico}
                value={tecnicoId}
                onChange={(e) => setTecnicoId(e.target.value)}
                className={`w-full min-w-0 px-3 py-2 rounded-xl border text-sm bg-white ${
                  tieneServicioTecnico && !tecnicoId
                    ? "border-red-400 ring-2 ring-red-100"
                    : "border-slate-300"
                }`}
              >
                <option value="">
                  {tieneServicioTecnico
                    ? "Seleccionar técnico obligatorio..."
                    : "Sin técnico asignado"}
                </option>
                {tecnicosDisponibles.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.nombre}
                  </option>
                ))}
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

          {/* Agregar componente / accesorio / repuesto del catálogo (buscador interactivo z-50) */}
          <div ref={contenedorSkuRef} className="relative z-30 space-y-1.5 min-w-0">
            <label className="block text-xs font-bold text-slate-700">
              Repuestos / accesorios / componentes ({productosFiltrados.length})
            </label>
            <div className="flex gap-2 min-w-0">
              <div className="relative flex-1 min-w-0">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="text"
                  value={busquedaSku}
                  onFocus={() => setMenuSkuAbierto(true)}
                  onChange={(e) => {
                    setArticuloSel("");
                    setBusquedaSku(e.target.value);
                    setMenuSkuAbierto(true);
                  }}
                  placeholder="Buscar repuesto o accesorio por SKU, descripción o categoría..."
                  className="w-full min-w-0 pl-9 pr-14 py-2 rounded-xl border border-slate-300 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#E85A28]/30 focus:border-[#E85A28]"
                />
                {(busquedaSku || articuloSel) && (
                  <button
                    type="button"
                    onClick={() => {
                      setArticuloSel("");
                      setBusquedaSku("");
                      setMenuSkuAbierto(true);
                    }}
                    aria-label="Limpiar SKU"
                    className="absolute right-8 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 cursor-pointer"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setMenuSkuAbierto((prev) => !prev)}
                  aria-label="Desplegar catálogo"
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-500 hover:text-slate-700 cursor-pointer"
                >
                  <ChevronDown className="w-4 h-4" />
                </button>
              </div>
              <button
                type="button"
                onClick={agregarArticulo}
                disabled={!articuloSel}
                className="shrink-0 px-4 py-2 rounded-xl border border-slate-300 disabled:opacity-40 text-xs font-bold hover:bg-slate-50 cursor-pointer"
              >
                + Repuesto / SKU
              </button>
            </div>
            {menuSkuAbierto && (
              <div className="absolute left-0 right-0 top-full mt-1 z-50 bg-white border border-slate-200 rounded-xl shadow-xl max-h-64 overflow-y-auto divide-y divide-slate-100">
                {productosFiltrados.length === 0 ? (
                  <div className="p-3 text-center text-xs text-slate-500">
                    No se encontraron repuestos o accesorios.
                  </div>
                ) : (
                  productosFiltrados.map((a) => (
                    <div
                      key={a.id}
                      className="flex items-start justify-between gap-2 p-2.5 hover:bg-orange-50/70"
                    >
                      <button
                        type="button"
                        onClick={() => {
                          setArticuloSel(String(a.id));
                          setBusquedaSku(`${a.sku} — ${a.descripcion}`);
                          setMenuSkuAbierto(false);
                        }}
                        className="flex-1 min-w-0 text-left cursor-pointer"
                      >
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="font-mono text-xs font-bold text-slate-900 bg-slate-100 px-1.5 py-0.5 rounded">
                            {a.sku}
                          </span>
                          <span className="text-xs font-bold text-emerald-700">
                            {formatearUsd(a.precio_promo_usd)} Promo
                          </span>
                        </div>
                        <p className="text-xs text-slate-700 mt-0.5 whitespace-normal break-words">
                          {a.descripcion}
                        </p>
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setCarrito((prev) => [
                            ...prev,
                            {
                              tipo: "ARTICULO",
                              articulo_id: a.id,
                              etiqueta: `${a.sku} — ${a.descripcion}`,
                              descripcion_servicio: "",
                              cantidad: 1,
                              precio_promo_usd: a.precio_promo_usd,
                              precio_regular_fijo_usd: a.precio_regular_fijo_usd,
                            },
                          ]);
                          setArticuloSel("");
                          setBusquedaSku("");
                          setMenuSkuAbierto(false);
                        }}
                        className="shrink-0 px-2.5 py-1 rounded-lg bg-[#E85A28] text-white text-[11px] font-bold cursor-pointer"
                      >
                        + Añadir
                      </button>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Acceso rápido: + Servicio Técnico / Mano de Obra */}
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => setPanelServicioAbierto((prev) => !prev)}
              className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 text-indigo-800 text-xs font-bold cursor-pointer"
            >
              <Wrench className="w-4 h-4 shrink-0" />
              + Servicio Técnico / Mano de Obra
            </button>

            {panelServicioAbierto && (
              <div className="p-4 rounded-xl bg-indigo-50/60 border border-indigo-200 space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-black text-indigo-900 uppercase">
                    Añadir Servicio Técnico / Mano de Obra (sin serial)
                  </p>
                  <button
                    type="button"
                    onClick={() => setPanelServicioAbierto(false)}
                    className="text-indigo-500 hover:text-indigo-700 cursor-pointer"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                {serviciosCatalogo.length === 0 ? (
                  <p className="text-xs text-red-700">
                    No hay SKUs de tipo SERVICIO en el catálogo.
                  </p>
                ) : (
                  <>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                      <div className="sm:col-span-2 min-w-0">
                        <label className="block text-[11px] font-bold text-indigo-900 mb-1">
                          Código de servicio
                        </label>
                        <select
                          value={servicioSel}
                          onChange={(e) => {
                            setServicioSel(e.target.value);
                            const found = serviciosCatalogo.find(
                              (s) => String(s.id) === e.target.value
                            );
                            if (found) {
                              setServicioMontoPromo(
                                String(found.precio_promo_usd)
                              );
                            }
                          }}
                          className="w-full min-w-0 px-2.5 py-1.5 rounded-lg border border-indigo-300 text-xs bg-white"
                        >
                          {serviciosCatalogo.map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.sku} — {s.descripcion} (base{" "}
                              {formatearUsd(s.precio_promo_usd)})
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="min-w-0">
                        <label className="block text-[11px] font-bold text-indigo-900 mb-1">
                          Monto Promo USD *
                        </label>
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          value={servicioMontoPromo}
                          onChange={(e) =>
                            setServicioMontoPromo(e.target.value)
                          }
                          placeholder="Ej: 35.00"
                          className="w-full min-w-0 px-2.5 py-1.5 rounded-lg border border-indigo-300 text-xs bg-white font-bold"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="block text-[11px] font-bold text-indigo-900 mb-1">
                        Descripción del servicio / trabajo realizado
                      </label>
                      <input
                        type="text"
                        value={servicioDescripcion}
                        onChange={(e) => setServicioDescripcion(e.target.value)}
                        placeholder="Ej: Cambio de pin de carga y mantenimiento preventivo"
                        className="w-full min-w-0 px-2.5 py-1.5 rounded-lg border border-indigo-300 text-xs bg-white"
                      />
                    </div>

                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11px] text-indigo-800">
                        Precio Regular estimado ({recargoPctActual}%):{" "}
                        <strong>
                          {formatearUsd(
                            redondear2(
                              (Number(servicioMontoPromo) || 0) *
                                (1 + recargoPctActual / 100)
                            )
                          )}
                        </strong>
                      </span>
                      <button
                        type="button"
                        onClick={agregarServicioTecnico}
                        className="px-3.5 py-1.5 rounded-lg bg-indigo-700 hover:bg-indigo-800 text-white text-xs font-bold cursor-pointer"
                      >
                        + Añadir servicio al carrito
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>

          {/* Lista del carrito */}
          <div className="border border-slate-200 rounded-xl overflow-hidden">
            {carrito.length === 0 ? (
              <p className="p-6 text-center text-xs text-slate-500">
                El carrito está vacío. Agrega equipos por serial, repuestos del
                catálogo o un servicio técnico.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-50 border-b border-slate-200 uppercase text-slate-500">
                    <tr>
                      <th className="px-3 py-2">Ítem / Trabajo</th>
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
                    {carrito.map((c, idx) => {
                      const precioUnitario =
                        c.precio_pactado_usd !== undefined
                          ? c.precio_pactado_usd
                          : c.precio_promo_usd;
                      const esObsequio = precioUnitario === 0;
                      const tieneDescuento =
                        c.precio_pactado_usd !== undefined &&
                        c.precio_pactado_usd > 0 &&
                        c.precio_pactado_usd < c.precio_promo_usd;

                      return (
                        <tr key={idx}>
                          <td className="px-3 py-2 font-semibold text-slate-800 whitespace-normal break-words space-y-1">
                            <div className="flex flex-wrap items-center gap-1.5">
                              {c.tipo === "SERVICIO" && (
                                <span className="px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-800 text-[10px] font-bold">
                                  SERVICIO
                                </span>
                              )}
                              {esObsequio && (
                                <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 text-[10px] font-bold">
                                  OBSEQUIO ($0.00)
                                </span>
                              )}
                              {tieneDescuento && (
                                <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 text-[10px] font-bold">
                                  DESC. (base {formatearUsd(c.precio_promo_usd)})
                                </span>
                              )}
                              <span>{c.etiqueta}</span>
                            </div>
                            <div className="flex flex-wrap items-center gap-2 pt-0.5">
                              <button
                                type="button"
                                onClick={() => {
                                  setCarrito((prev) =>
                                    prev.map((item, i) => {
                                      if (i !== idx) return item;
                                      const actual =
                                        item.precio_pactado_usd !== undefined
                                          ? item.precio_pactado_usd
                                          : item.precio_promo_usd;
                                      return {
                                        ...item,
                                        precio_pactado_usd:
                                          actual === 0 ? undefined : 0,
                                      };
                                    })
                                  );
                                }}
                                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[10px] font-bold cursor-pointer ${
                                  esObsequio
                                    ? "bg-emerald-600 border-emerald-600 text-white"
                                    : "bg-white border-slate-300 text-slate-600 hover:bg-slate-50"
                                }`}
                              >
                                <Gift className="w-3 h-3" />
                                {esObsequio ? "Quitar obsequio" : "Obsequio ($0)"}
                              </button>
                            </div>
                            {c.tipo === "SERVICIO" && (
                              <input
                                type="text"
                                value={c.descripcion_servicio ?? ""}
                                onChange={(e) => {
                                  const val = e.target.value;
                                  setCarrito((prev) =>
                                    prev.map((item, i) =>
                                      i === idx
                                        ? { ...item, descripcion_servicio: val }
                                        : item
                                    )
                                  );
                                }}
                                placeholder="Descripción del trabajo realizado..."
                                className="w-full px-2 py-1 rounded border border-indigo-200 text-[11px] font-normal text-slate-700 bg-indigo-50/30"
                              />
                            )}
                          </td>
                          <td className="px-3 py-2 text-right whitespace-nowrap align-top">
                            {c.tipo === "ARTICULO" ? (
                              <input
                                type="number"
                                min={1}
                                value={c.cantidad}
                                onChange={(e) => {
                                  const cant = Math.max(
                                    1,
                                    Number(e.target.value) || 1
                                  );
                                  setCarrito((prev) =>
                                    prev.map((item, i) =>
                                      i === idx
                                        ? { ...item, cantidad: cant }
                                        : item
                                    )
                                  );
                                }}
                                className="w-14 px-1.5 py-1 rounded border border-slate-300 text-right text-xs"
                              />
                            ) : (
                              c.cantidad
                            )}
                          </td>
                          <td className="px-3 py-2 text-right font-bold whitespace-nowrap align-top">
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              value={precioUnitario}
                              onChange={(e) => {
                                const monto = Math.max(
                                  0,
                                  Number(e.target.value) || 0
                                );
                                setCarrito((prev) =>
                                  prev.map((item, i) =>
                                    i === idx
                                      ? {
                                          ...item,
                                          precio_pactado_usd: monto,
                                        }
                                      : item
                                  )
                                );
                              }}
                              className={`w-20 px-1.5 py-1 rounded border text-right text-xs font-bold ${
                                esObsequio
                                  ? "border-emerald-300 text-emerald-700 bg-emerald-50"
                                  : "border-slate-300 text-slate-900 bg-white"
                              }`}
                            />
                            {c.cantidad > 1 && (
                              <div className="text-[10px] text-slate-500 mt-0.5">
                                Subt:{" "}
                                {formatearUsd(precioUnitario * c.cantidad)}
                              </div>
                            )}
                          </td>
                          <td className="px-3 py-2 text-right whitespace-nowrap align-top">
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
                      );
                    })}
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

                  {esCasheaFila && (
                    <div className="space-y-1.5 rounded-lg bg-white/90 border border-[#E85A28]/40 p-2.5">
                      <label className="block text-[11px] font-black uppercase tracking-wider text-[#E85A28]">
                        Nro. de Orden Cashea *
                      </label>
                      <input
                        type="text"
                        required
                        value={casheaNumeroOrden}
                        onChange={(e) => setCasheaNumeroOrden(e.target.value.toUpperCase())}
                        placeholder="Ej. CSH-984512 (obligatorio de la app/portal Cashea)"
                        className={`w-full px-2.5 py-1.5 rounded-lg border text-xs font-mono font-bold bg-white ${
                          !casheaNumeroOrden.trim()
                            ? "border-red-400 focus:border-[#E85A28]"
                            : "border-emerald-400"
                        }`}
                      />
                      {carrito.length > 0 && (
                        <div className="flex flex-wrap items-center justify-between gap-1 text-[11px] font-semibold text-orange-900 pt-1">
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
            disabled={
              guardando ||
              carrito.length === 0 ||
              ventaCreada !== null ||
              (usaCasheaLocal && !casheaNumeroOrden.trim())
            }
            className="w-full py-3 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] disabled:opacity-50 disabled:cursor-not-allowed text-white font-black text-sm cursor-pointer transition-colors"
          >
            {guardando
              ? "Registrando venta..."
              : ventaCreada
              ? `Nota ${ventaCreada.numero_venta} emitida · Usa el panel inferior`
              : usaCasheaLocal && !casheaNumeroOrden.trim()
              ? "Ingresa el Nro. de Orden Cashea para emitir"
              : "Confirmar y Emitir Nota"}
          </button>
        </div>
      </form>

      {/* Panel fijo de Acciones Post-Venta en la parte baja del POS */}
      {ventaCreada && (() => {
        const mensajeWa = formatearWhatsAppVenta(ventaCreada);
        const telefonoWa = normalizarTelefonoWa(ventaCreada.cliente_telefono);
        const urlWa = telefonoWa
          ? `https://wa.me/${telefonoWa}?text=${encodeURIComponent(mensajeWa)}`
          : null;

        return (
          <section
            ref={panelPostVentaRef}
            aria-label="Acciones post-venta"
            className="bg-white/80 backdrop-blur-md border-2 border-[#E85A28]/50 shadow-[0_12px_36px_rgb(232,90,40,0.08)] rounded-2xl p-5 sm:p-6 space-y-5"
          >
            {/* Encabezado de confirmación */}
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-neutral-200/80 pb-4">
              <div className="flex items-start gap-3">
                <div className="w-11 h-11 rounded-2xl bg-[#FDF0EB] border border-[#E85A28]/30 flex items-center justify-center shrink-0">
                  <CheckCircle2 className="w-6 h-6 text-[#E85A28]" />
                </div>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="inline-flex items-center px-3 py-1 rounded-full bg-[#E85A28] text-white text-xs font-black tracking-wide">
                      Nota {ventaCreada.numero_venta}
                    </span>
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-bold">
                      {ventaCreada.estado}
                    </span>
                  </div>
                  <h3 className="text-lg font-black text-[#191818] mt-1">
                    ¡Venta registrada correctamente!
                  </h3>
                  <p className="text-xs text-neutral-600 mt-0.5">
                    Cliente: <strong className="text-[#191818]">{ventaCreada.cliente}</strong>
                    {ventaCreada.cliente_rif ? ` (${ventaCreada.cliente_rif})` : ""} · Total Promo:{" "}
                    <strong className="tabular-nums text-[#191818]">
                      {formatearUsd(ventaCreada.total_promo_usd)}
                    </strong>{" "}
                    · Regular:{" "}
                    <strong className="tabular-nums text-[#191818]">
                      {formatearUsd(ventaCreada.total_regular_usd)}
                    </strong>
                  </p>
                </div>
              </div>

              {/* Botón + Nueva Venta */}
              <button
                type="button"
                onClick={iniciarNuevaVenta}
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#191818] hover:bg-[#2E2D2D] text-white text-xs font-bold transition-colors cursor-pointer shrink-0"
              >
                <Plus className="w-4 h-4" />
                + Nueva Venta
              </button>
            </div>

            {/* Acciones principales: Imprimir / Descargar + WhatsApp */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
              {/* Columna izquierda: Impresión y descarga PDF */}
              <div className="lg:col-span-5 space-y-3">
                <p className="text-xs font-bold uppercase tracking-wide text-neutral-500">
                  Documentos PDF para Imprimir
                </p>
                <div className="flex flex-col sm:flex-row lg:flex-col gap-2.5">
                  <button
                    type="button"
                    disabled={abriendoPdf}
                    onClick={() => void abrirNotaParaImprimir(ventaCreada)}
                    className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] disabled:opacity-60 text-white text-sm font-black shadow-sm transition-colors cursor-pointer"
                  >
                    <Printer className="w-4 h-4" />
                    {abriendoPdf ? "Abriendo PDF..." : "Imprimir Nota de Entrega (PDF)"}
                  </button>
                  {["DELIVERY", "ENVIO_NACIONAL", "ENVIO"].includes(
                    (ventaCreada.tipo_entrega || "").toUpperCase()
                  ) && (
                    <button
                      type="button"
                      disabled={abriendoPdf}
                      onClick={() => {
                        setError(null);
                        setAbriendoPdf(true);
                        void abrirPdfEnPestanaApi(
                          `/api/ventas/${ventaCreada.id}/etiqueta-envio-pdf`
                        )
                          .catch((err) => {
                            setError(
                              err instanceof ErrorApi
                                ? err.message
                                : "No se pudo abrir la Etiqueta de Envío."
                            );
                          })
                          .finally(() => setAbriendoPdf(false));
                      }}
                      className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] disabled:opacity-60 text-white text-xs sm:text-sm font-black shadow-sm ring-2 ring-[#E85A28]/25 transition-colors cursor-pointer"
                    >
                      <Printer className="w-4 h-4" />
                      Imprimir Etiqueta de Envío — Hoja Carta (FRÁGIL)
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() =>
                      void descargarPdfApi(
                        `/api/ventas/${ventaCreada.id}/nota-pdf`,
                        `Nota_${ventaCreada.numero_venta}.pdf`
                      )
                    }
                    className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-neutral-300 bg-white/90 hover:bg-neutral-50 text-[#191818] text-xs font-bold transition-colors cursor-pointer"
                  >
                    <FileDown className="w-4 h-4 text-[#E85A28]" />
                    Descargar PDF ({ventaCreada.numero_venta})
                  </button>
                </div>
                <p className="text-[11px] text-neutral-500 leading-relaxed">
                  Los botones de impresión abren cada documento oficial en una pestaña nueva listo para imprimir sin perder esta pantalla.
                </p>
              </div>

              {/* Columna derecha: Vista previa y envío por WhatsApp */}
              <div className="lg:col-span-7 space-y-2.5 min-w-0">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs font-bold uppercase tracking-wide text-neutral-500 flex items-center gap-1.5">
                    <MessageSquare className="w-3.5 h-3.5 text-emerald-600" />
                    Mensaje formateado para WhatsApp
                  </p>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void copiarWhatsApp(ventaCreada)}
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold transition-colors cursor-pointer"
                    >
                      {copiado ? (
                        <Check className="w-3.5 h-3.5" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                      {copiado ? "¡Copiado!" : "Copiar para WhatsApp"}
                    </button>
                    {urlWa && (
                      <a
                        href={urlWa}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-emerald-300 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 text-xs font-bold transition-colors"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                        Abrir en WhatsApp
                      </a>
                    )}
                  </div>
                </div>

                <div className="max-h-56 overflow-y-auto rounded-xl border border-neutral-200/90 bg-neutral-50/90 p-3.5 text-xs font-mono text-[#191818] whitespace-pre-wrap leading-relaxed select-all">
                  {mensajeWa}
                </div>
              </div>
            </div>
          </section>
        );
      })()}

      {/* Modal + Nuevo Cliente (Natural / Jurídico) */}
      {modalCliente && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-black text-slate-900 flex items-center gap-2">
                <UserPlus className="w-5 h-5 text-emerald-600" />
                Nuevo Cliente
              </h3>
              <button
                type="button"
                onClick={() => setModalCliente(false)}
                className="text-slate-400 hover:text-slate-600 cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {errorModalCliente && (
              <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700">
                {errorModalCliente}
              </div>
            )}

            <form onSubmit={manejarCrearCliente} className="space-y-3">
              {/* Tipo de persona */}
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setCliTipoPersona("NATURAL");
                    setCliTipoDoc("V");
                  }}
                  className={`py-2 rounded-xl text-xs font-bold border cursor-pointer ${
                    cliTipoPersona === "NATURAL"
                      ? "bg-[#E85A28] border-[#E85A28] text-white"
                      : "bg-white border-slate-300 text-slate-700"
                  }`}
                >
                  Persona Natural
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setCliTipoPersona("JURIDICO");
                    setCliTipoDoc("J");
                  }}
                  className={`py-2 rounded-xl text-xs font-bold border cursor-pointer ${
                    cliTipoPersona === "JURIDICO"
                      ? "bg-[#E85A28] border-[#E85A28] text-white"
                      : "bg-white border-slate-300 text-slate-700"
                  }`}
                >
                  Persona Jurídica
                </button>
              </div>

              {/* Documento */}
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  {cliTipoPersona === "NATURAL"
                    ? "Cédula de Identidad *"
                    : "RIF *"}
                </label>
                <div className="flex gap-2">
                  <select
                    value={cliTipoDoc}
                    onChange={(e) =>
                      setCliTipoDoc(
                        e.target.value as "V" | "E" | "P" | "J" | "G"
                      )
                    }
                    className="w-20 px-2.5 py-2 rounded-xl border border-slate-300 text-sm font-bold bg-white"
                  >
                    {cliTipoPersona === "NATURAL" ? (
                      <>
                        <option value="V">V-</option>
                        <option value="E">E-</option>
                        <option value="P">P-</option>
                      </>
                    ) : (
                      <>
                        <option value="J">J-</option>
                        <option value="G">G-</option>
                      </>
                    )}
                  </select>
                  <input
                    type="text"
                    required
                    minLength={4}
                    value={cliDocumento}
                    onChange={(e) => setCliDocumento(e.target.value)}
                    placeholder={
                      cliTipoPersona === "NATURAL"
                        ? "Ej: 24567890"
                        : "Ej: 506375184"
                    }
                    className="flex-1 px-3 py-2 rounded-xl border border-slate-300 text-sm font-mono"
                  />
                </div>
              </div>

              {/* Nombre o Razón Social */}
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  {cliTipoPersona === "NATURAL"
                    ? "Nombre y Apellido *"
                    : "Razón Social *"}
                </label>
                <input
                  type="text"
                  required
                  minLength={2}
                  value={cliNombre}
                  onChange={(e) => setCliNombre(e.target.value)}
                  placeholder={
                    cliTipoPersona === "NATURAL"
                      ? "Ej: María Alejandra Pérez"
                      : "Ej: Inversiones Globales, C.A."
                  }
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>

              {/* Teléfono */}
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Teléfono / WhatsApp
                </label>
                <input
                  type="text"
                  value={cliTelefono}
                  onChange={(e) => setCliTelefono(e.target.value)}
                  placeholder="Ej: 0414-1234567"
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>

              {/* Dirección */}
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  {cliTipoPersona === "NATURAL"
                    ? "Dirección"
                    : "Dirección fiscal"}
                </label>
                <input
                  type="text"
                  value={cliDireccion}
                  onChange={(e) => setCliDireccion(e.target.value)}
                  placeholder="Ej: Av. Bolívar Norte, Valencia, Edo. Carabobo"
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setModalCliente(false)}
                  className="px-4 py-2 rounded-xl border border-slate-300 text-sm font-semibold cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={guardandoCliente}
                  className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-sm font-bold cursor-pointer"
                >
                  {guardandoCliente ? "Guardando..." : "Guardar y seleccionar"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
