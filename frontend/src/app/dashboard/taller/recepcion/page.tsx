"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ClipboardList,
  MessageCircle,
  Printer,
  ShieldAlert,
} from "lucide-react";
import {
  abrirPdfEnPestanaApi,
  extraerMensajeError,
  solicitarApi,
} from "@/servicios/api";
import { construirUrlWhatsApp } from "@/lib/whatsapp";
import type { Sucursal } from "@/tipos/dominio";

interface RecepcionItem {
  id: number;
  numero_caso: string;
  tipo: "GARANTIA" | "SERVICIO_TECNICO";
  sucursal_id: number;
  sucursal: string;
  numero_nota_entrega: string;
  cliente_nombre: string;
  cliente_telefono: string;
  serial_o_codigo: string;
  descripcion_equipo: string;
  tipo_marca_color: string;
  accesorios_recibidos: string;
  estado_fisico: string;
  ingresa_apagado: boolean;
  falla_reportada: string;
  estado: string;
  tecnico: string;
  recibido_por: string;
  fecha_ingreso: string | null;
}

interface UsuarioOperativo {
  id: number;
  nombre: string;
  rol: string;
}

export default function PaginaRecepcionTaller() {
  const [recepciones, setRecepciones] = useState<RecepcionItem[]>([]);
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [tecnicos, setTecnicos] = useState<UsuarioOperativo[]>([]);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  // Formulario
  const [tipo, setTipo] = useState<"GARANTIA" | "SERVICIO_TECNICO">("SERVICIO_TECNICO");
  const [sucursalId, setSucursalId] = useState("");
  const [numeroNota, setNumeroNota] = useState("");
  const [clienteNombre, setClienteNombre] = useState("");
  const [clienteTelefono, setClienteTelefono] = useState("");
  const [serial, setSerial] = useState("");
  const [descripcionEquipo, setDescripcionEquipo] = useState("");
  const [marcaColor, setMarcaColor] = useState("");
  const [accesorios, setAccesorios] = useState("");
  const [estadoFisico, setEstadoFisico] = useState("");
  const [claveEquipo, setClaveEquipo] = useState("");
  const [ingresaApagado, setIngresaApagado] = useState(false);
  const [fallaReportada, setFallaReportada] = useState("");
  const [tecnicoId, setTecnicoId] = useState("");

  const cargarDatos = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [rRec, rSuc, rUsr] = await Promise.all([
        solicitarApi<RecepcionItem[]>("/api/taller/recepciones"),
        solicitarApi<Sucursal[]>("/api/sucursales"),
        solicitarApi<UsuarioOperativo[]>("/api/usuarios/operativos"),
      ]);
      setRecepciones(rRec);
      setSucursales(rSuc);
      setTecnicos(rUsr.filter((u) => u.rol === "TECNICO"));
      if (rSuc.length > 0 && !sucursalId) {
        setSucursalId(String(rSuc[0].id));
      }
    } catch (err) {
      setError(extraerMensajeError(err, "No se pudieron cargar las recepciones."));
    } finally {
      setCargando(false);
    }
  }, [sucursalId]);

  useEffect(() => {
    void cargarDatos();
  }, [cargarDatos]);

  const registrarRecepcion = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setExito(null);
    setGuardando(true);
    try {
      const creada = await solicitarApi<RecepcionItem>("/api/taller/recepciones", {
        method: "POST",
        body: JSON.stringify({
          tipo,
          sucursal_id: Number(sucursalId),
          numero_nota_entrega: tipo === "GARANTIA" ? numeroNota.trim().toUpperCase() : "",
          cliente_nombre: clienteNombre.trim(),
          cliente_telefono: clienteTelefono.trim(),
          serial_o_codigo: serial.trim(),
          descripcion_equipo: descripcionEquipo.trim(),
          tipo_marca_color: marcaColor.trim(),
          accesorios_recibidos: accesorios.trim(),
          estado_fisico: estadoFisico.trim(),
          clave_equipo: claveEquipo.trim(),
          ingresa_apagado: tipo === "SERVICIO_TECNICO" ? ingresaApagado : false,
          falla_reportada: fallaReportada.trim(),
          tecnico_id: tecnicoId ? Number(tecnicoId) : null,
        }),
      });
      setExito(`Recepción ${creada.numero_caso} registrada y asignada a Taller.`);
      setNumeroNota("");
      setClienteNombre("");
      setClienteTelefono("");
      setSerial("");
      setDescripcionEquipo("");
      setMarcaColor("");
      setAccesorios("");
      setEstadoFisico("");
      setClaveEquipo("");
      setIngresaApagado(false);
      setFallaReportada("");
      await cargarDatos();
    } catch (err) {
      setError(extraerMensajeError(err, "No se pudo registrar la recepción."));
    } finally {
      setGuardando(false);
    }
  };

  const enviarPorWhatsApp = (rec: RecepcionItem) => {
    const esServ = rec.tipo === "SERVICIO_TECNICO";
    const lineas = [
      `*TEKIO ELECTRONICS · COMPROBANTE DE RECEPCIÓN (${rec.numero_caso})*`,
      `Tipo: ${esServ ? "SERVICIO TÉCNICO" : `GARANTÍA (Nota ${rec.numero_nota_entrega})`}`,
      `Cliente: ${rec.cliente_nombre}`,
      `Equipo: ${rec.descripcion_equipo}${rec.serial_o_codigo ? ` · Serial: ${rec.serial_o_codigo}` : ""}`,
      `Accesorios: ${rec.accesorios_recibidos || "Ninguno"}`,
      `Falla reportada: ${rec.falla_reportada}`,
    ];
    if (esServ) {
      lineas.push(
        "",
        "Condiciones:",
        "• Diagnóstico/revisión técnica: $10 USD (100% exonerados al aprobar la reparación).",
        rec.ingresa_apagado
          ? "• Equipo recibido APAGADO: Tekio Electronics no se hace responsable por fallas ocultas no verificables al ingreso."
          : "• Si el equipo ingresa apagado sin verificación de encendido, Tekio Electronics no responde por fallas ocultas."
      );
    }
    const url = construirUrlWhatsApp(lineas.join("\n"), rec.cliente_telefono);
    window.open(url, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-black text-[#191818]">
          Recepción de Garantías y Servicio Técnico
        </h2>
        <p className="text-sm text-neutral-500">
          Registro formal de equipos recibidos por Líder/Encargado hacia Taller con comprobante PDF imprimible y cláusulas automáticas.
        </p>
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

      {/* Formulario de recepción */}
      <form
        onSubmit={registrarRecepcion}
        className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl p-6 space-y-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-base font-black text-[#191818] flex items-center gap-2">
            <ClipboardList className="w-4 h-4 text-[#E85A28]" />
            Nueva recepción de equipo
          </h3>
          <div className="flex gap-2">
            {(["SERVICIO_TECNICO", "GARANTIA"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTipo(t)}
                className={`px-3.5 py-1.5 rounded-xl text-xs font-black cursor-pointer ${
                  tipo === t
                    ? "bg-[#E85A28] text-white"
                    : "bg-neutral-100 text-neutral-700"
                }`}
              >
                {t === "GARANTIA" ? "GARANTÍA (Con Nota)" : "SERVICIO TÉCNICO"}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Sucursal de recepción
            </label>
            <select
              required
              value={sucursalId}
              onChange={(e) => setSucursalId(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
            >
              {sucursales.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nombre}
                </option>
              ))}
            </select>
          </div>

          {tipo === "GARANTIA" && (
            <div>
              <label className="block text-xs font-bold text-[#E85A28] mb-1">
                Nro. Nota de Entrega (Obligatorio · ej. N-0001)
              </label>
              <input
                type="text"
                required
                value={numeroNota}
                onChange={(e) => setNumeroNota(e.target.value)}
                placeholder="N-0001"
                className="w-full px-3 py-2 rounded-xl border-2 border-[#E85A28]/40 bg-white text-sm font-mono uppercase"
              />
            </div>
          )}

          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Nombre del cliente
            </label>
            <input
              type="text"
              value={clienteNombre}
              onChange={(e) => setClienteNombre(e.target.value)}
              placeholder="Ej: María Pérez"
              className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Teléfono WhatsApp del cliente
            </label>
            <input
              type="text"
              value={clienteTelefono}
              onChange={(e) => setClienteTelefono(e.target.value)}
              placeholder="0414-1234567"
              className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Equipo / Modelo (obligatorio)
            </label>
            <input
              type="text"
              required
              value={descripcionEquipo}
              onChange={(e) => setDescripcionEquipo(e.target.value)}
              placeholder="Ej: Laptop HP Pavilion 15"
              className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Serial / Código
            </label>
            <input
              type="text"
              value={serial}
              onChange={(e) => setSerial(e.target.value)}
              placeholder="SN-..."
              className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm font-mono uppercase"
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Accesorios recibidos
            </label>
            <input
              type="text"
              value={accesorios}
              onChange={(e) => setAccesorios(e.target.value)}
              placeholder="Cargador original, bolso, mouse..."
              className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Estado físico al recibir
            </label>
            <input
              type="text"
              value={estadoFisico}
              onChange={(e) => setEstadoFisico(e.target.value)}
              placeholder="Carcasa con rayones leves, bisagras OK"
              className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-neutral-700 mb-1">
              Técnico asignado (opcional)
            </label>
            <select
              value={tecnicoId}
              onChange={(e) => setTecnicoId(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
            >
              <option value="">Cola general de Taller</option>
              {tecnicos.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.nombre}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className="block text-xs font-bold text-neutral-700 mb-1">
            Falla reportada por el cliente (obligatorio)
          </label>
          <textarea
            required
            rows={2}
            value={fallaReportada}
            onChange={(e) => setFallaReportada(e.target.value)}
            placeholder="Describe detalladamente la falla reportada..."
            className="w-full px-3 py-2 rounded-xl border border-neutral-300 bg-white text-sm"
          />
        </div>

        {tipo === "SERVICIO_TECNICO" && (
          <div className="rounded-xl bg-amber-50/90 border border-amber-200 p-4 space-y-2">
            <label className="flex items-center gap-2.5 text-xs font-black text-amber-900 cursor-pointer">
              <input
                type="checkbox"
                checked={ingresaApagado}
                onChange={(e) => setIngresaApagado(e.target.checked)}
                className="rounded border-amber-400"
              />
              El equipo ingresa APAGADO (sin posibilidad de verificar encendido previo)
            </label>
            <p className="text-[11px] text-amber-800 flex items-start gap-1.5">
              <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                El comprobante PDF incluirá automáticamente la cláusula de revisión técnica (<strong>$10 USD</strong>, 100% exonerados al aprobar reparación) y descargo de responsabilidad por equipo apagado.
              </span>
            </p>
          </div>
        )}

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={guardando}
            className="px-5 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold cursor-pointer disabled:opacity-50"
          >
            {guardando ? "Registrando..." : "Registrar Recepción y Enviar a Taller"}
          </button>
        </div>
      </form>

      {/* Historial de recepciones */}
      <div className="bg-white/80 backdrop-blur-md border border-neutral-200/80 rounded-2xl overflow-hidden">
        <div className="px-5 py-3.5 border-b border-neutral-100 font-black text-sm text-[#191818]">
          Recepciones Recientes ({recepciones.length})
        </div>
        {cargando ? (
          <div className="p-6 space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 rounded-xl bg-neutral-100 animate-pulse" />
            ))}
          </div>
        ) : recepciones.length === 0 ? (
          <div className="p-10 text-center text-sm text-neutral-500">
            No hay recepciones registradas aún.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-neutral-50 text-neutral-500 uppercase">
                <tr>
                  <th className="px-4 py-3">Caso</th>
                  <th className="px-4 py-3">Tipo</th>
                  <th className="px-4 py-3">Cliente</th>
                  <th className="px-4 py-3">Equipo / Serial</th>
                  <th className="px-4 py-3">Condición</th>
                  <th className="px-4 py-3 text-right">Comprobante</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {recepciones.map((r) => (
                  <tr key={r.id} className="hover:bg-neutral-50/70">
                    <td className="px-4 py-3 font-mono font-black text-[#E85A28]">
                      {r.numero_caso}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          r.tipo === "GARANTIA"
                            ? "bg-blue-100 text-blue-800"
                            : "bg-amber-100 text-amber-800"
                        }`}
                      >
                        {r.tipo === "GARANTIA"
                          ? `GARANTÍA · ${r.numero_nota_entrega}`
                          : "SERVICIO TÉCNICO"}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-bold text-[#191818]">{r.cliente_nombre}</p>
                      <p className="text-[11px] text-neutral-500">{r.cliente_telefono}</p>
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-semibold">{r.descripcion_equipo}</p>
                      <p className="font-mono text-[11px] text-neutral-500">
                        {r.serial_o_codigo || "Sin serial"}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      {r.ingresa_apagado ? (
                        <span className="px-2 py-0.5 rounded bg-red-100 text-red-800 font-bold text-[10px]">
                          APAGADO
                        </span>
                      ) : (
                        <span className="text-neutral-600">Encendido</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="inline-flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() =>
                            void abrirPdfEnPestanaApi(`/api/taller/recepciones/${r.id}/pdf`)
                          }
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[#191818] text-white font-bold cursor-pointer"
                        >
                          <Printer className="w-3.5 h-3.5" />
                          Imprimir / PDF
                        </button>
                        <button
                          type="button"
                          onClick={() => enviarPorWhatsApp(r)}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-emerald-600 text-white font-bold cursor-pointer"
                        >
                          <MessageCircle className="w-3.5 h-3.5" />
                          WhatsApp
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
