"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CalendarClock,
  CheckCircle2,
  FileDown,
  FileSpreadsheet,
  Plus,
} from "lucide-react";
import {
  ErrorApi,
  descargarPdfApi,
  fechaHoyCaracas,
  formatearUsd,
  solicitarApi,
} from "@/servicios/api";

interface DocFiscal {
  id: number;
  tipo_libro: "COMPRA" | "VENTA";
  fecha: string;
  numero_factura: string;
  numero_control: string;
  rif_tercero: string;
  nombre_tercero: string;
  base_imponible: number;
  monto_exento: number;
  iva_monto: number;
  igtf_monto: number;
  total_documento: number;
  retencion_iva_monto: number;
  retencion_islr_monto: number;
  moneda: string;
}

interface ObligacionItem {
  id: number;
  tipo: string;
  periodo: string;
  descripcion: string;
  fecha_vencimiento: string;
  monto_estimado_usd: number;
  estado: "PENDIENTE" | "DECLARADO" | "PAGADO";
  referencia_pago: string;
}

export default function PaginaFiscalSeniat() {
  const hoy = fechaHoyCaracas();
  const inicioMes = `${hoy.slice(0, 8)}01`;

  const [fechaInicio, setFechaInicio] = useState(inicioMes);
  const [fechaFin, setFechaFin] = useState(hoy);
  const [docs, setDocs] = useState<DocFiscal[]>([]);
  const [obligaciones, setObligaciones] = useState<ObligacionItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  // Form documento fiscal
  const [tipoLibro, setTipoLibro] = useState<"COMPRA" | "VENTA">("COMPRA");
  const [fechaDoc, setFechaDoc] = useState(hoy);
  const [numFactura, setNumFactura] = useState("");
  const [numControl, setNumControl] = useState("");
  const [rifTercero, setRifTercero] = useState("");
  const [nombreTercero, setNombreTercero] = useState("");
  const [baseImp, setBaseImp] = useState("");
  const [exento, setExento] = useState("0");
  const [ivaPct, setIvaPct] = useState("16");
  const [igtfPct, setIgtfPct] = useState("0");
  const [retIvaPct, setRetIvaPct] = useState("0");
  const [retIslr, setRetIslr] = useState("0");
  const [moneda, setMoneda] = useState<"BS" | "USD">("BS");

  // Form obligación
  const [obTipo, setObTipo] = useState("IVA");
  const [obPeriodo, setObPeriodo] = useState(hoy.slice(0, 7));
  const [obVence, setObVence] = useState(hoy);
  const [obMonto, setObMonto] = useState("0");
  const [obDesc, setObDesc] = useState("");

  const cargar = useCallback(async () => {
    setError(null);
    try {
      const [d, o] = await Promise.all([
        solicitarApi<DocFiscal[]>(`/api/finanzas/fiscal/documentos?fecha_inicio=${fechaInicio}&fecha_fin=${fechaFin}`),
        solicitarApi<ObligacionItem[]>("/api/finanzas/fiscal/obligaciones"),
      ]);
      setDocs(d);
      setObligaciones(o);
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "Error cargando módulo fiscal.");
    }
  }, [fechaInicio, fechaFin]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const crearDoc = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setExito(null);
    try {
      await solicitarApi("/api/finanzas/fiscal/documentos", {
        method: "POST",
        body: JSON.stringify({
          tipo_libro: tipoLibro,
          fecha: fechaDoc,
          numero_factura: numFactura.trim(),
          numero_control: numControl.trim(),
          rif_tercero: rifTercero.trim(),
          nombre_tercero: nombreTercero.trim(),
          base_imponible: Number(baseImp || 0),
          monto_exento: Number(exento || 0),
          iva_pct: Number(ivaPct || 16),
          igtf_pct: Number(igtfPct || 0),
          retencion_iva_pct: Number(retIvaPct || 0),
          retencion_islr_monto: Number(retIslr || 0),
          moneda,
        }),
      });
      setExito(`Factura fiscal ${numFactura} registrada en Libro de ${tipoLibro === "COMPRA" ? "Compras" : "Ventas"}.`);
      setNumFactura("");
      setNumControl("");
      setBaseImp("");
      await cargar();
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo registrar el documento fiscal.");
    }
  };

  const crearObligacion = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    try {
      await solicitarApi("/api/finanzas/fiscal/obligaciones", {
        method: "POST",
        body: JSON.stringify({
          tipo: obTipo,
          periodo: obPeriodo,
          descripcion: obDesc.trim(),
          fecha_vencimiento: obVence,
          monto_estimado_usd: Number(obMonto || 0),
        }),
      });
      setExito("Obligación fiscal agregada al calendario.");
      setObDesc("");
      await cargar();
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo crear la obligación.");
    }
  };

  const cambiarEstadoOb = async (id: number, estado: "PENDIENTE" | "DECLARADO" | "PAGADO") => {
    await solicitarApi(`/api/finanzas/fiscal/obligaciones/${id}/estado`, {
      method: "PATCH",
      body: JSON.stringify({ estado }),
    });
    await cargar();
  };

  const qs = `fecha_inicio=${fechaInicio}&fecha_fin=${fechaFin}`;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-black text-[#191818]">
            Gestión Fiscal · Venezuela / SENIAT
          </h2>
          <p className="text-sm text-neutral-500">
            Libros de Compras y Ventas (IVA 16%, IGTF 3%, Retenciones) y Calendario de Obligaciones.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <input type="date" value={fechaInicio} onChange={(e) => setFechaInicio(e.target.value)} className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white" />
          <input type="date" value={fechaFin} onChange={(e) => setFechaFin(e.target.value)} className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white" />
          <button type="button" onClick={() => void descargarPdfApi(`/api/finanzas/fiscal/libro/COMPRA/xlsx?${qs}`, `Libro_Compras_${fechaInicio}.xlsx`)} className="inline-flex items-center gap-1 px-3 py-2 rounded-xl bg-[#191818] text-white font-bold cursor-pointer">
            <FileSpreadsheet className="w-3.5 h-3.5" /> Libro Compras .xlsx
          </button>
          <button type="button" onClick={() => void descargarPdfApi(`/api/finanzas/fiscal/libro/VENTA/xlsx?${qs}`, `Libro_Ventas_${fechaInicio}.xlsx`)} className="inline-flex items-center gap-1 px-3 py-2 rounded-xl bg-[#E85A28] text-white font-bold cursor-pointer">
            <FileSpreadsheet className="w-3.5 h-3.5" /> Libro Ventas .xlsx
          </button>
          <button type="button" onClick={() => void descargarPdfApi(`/api/finanzas/fiscal/libro/COMPRA/pdf?${qs}`, `Libro_Compras_${fechaInicio}.pdf`)} className="inline-flex items-center gap-1 px-3 py-2 rounded-xl border border-neutral-300 bg-white font-bold cursor-pointer">
            <FileDown className="w-3.5 h-3.5" /> PDF Compras
          </button>
          <button type="button" onClick={() => void descargarPdfApi(`/api/finanzas/fiscal/libro/VENTA/pdf?${qs}`, `Libro_Ventas_${fechaInicio}.pdf`)} className="inline-flex items-center gap-1 px-3 py-2 rounded-xl border border-neutral-300 bg-white font-bold cursor-pointer">
            <FileDown className="w-3.5 h-3.5" /> PDF Ventas
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3.5 rounded-2xl bg-red-50 border border-red-200 text-xs text-red-700 font-semibold">
          <AlertCircle className="w-4 h-4 shrink-0" /> <span>{error}</span>
        </div>
      )}
      {exito && (
        <div className="flex items-center gap-2 p-3.5 rounded-2xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 font-semibold">
          <CheckCircle2 className="w-4 h-4 shrink-0" /> <span>{exito}</span>
        </div>
      )}

      {/* Registrar Factura Fiscal */}
      <form onSubmit={crearDoc} className="bg-white/80 backdrop-blur-md border border-white/70 rounded-2xl p-5 shadow-xs space-y-3 text-xs">
        <h3 className="text-sm font-black text-[#191818] flex items-center gap-1.5">
          <Plus className="w-4 h-4 text-[#E85A28]" /> Registrar Documento Fiscal
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-6 gap-2.5">
          <select value={tipoLibro} onChange={(e) => setTipoLibro(e.target.value as "COMPRA" | "VENTA")} className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white font-bold">
            <option value="COMPRA">Libro Compras</option>
            <option value="VENTA">Libro Ventas</option>
          </select>
          <input type="date" required value={fechaDoc} onChange={(e) => setFechaDoc(e.target.value)} className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white" />
          <input type="text" required value={numFactura} onChange={(e) => setNumFactura(e.target.value)} placeholder="Nro. Factura" className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white" />
          <input type="text" value={numControl} onChange={(e) => setNumControl(e.target.value)} placeholder="Nro. Control" className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white" />
          <input type="text" required value={rifTercero} onChange={(e) => setRifTercero(e.target.value)} placeholder="RIF (J-12345678-9)" className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white" />
          <input type="text" required value={nombreTercero} onChange={(e) => setNombreTercero(e.target.value)} placeholder="Razón Social" className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white" />
          <input type="number" step="0.01" required value={baseImp} onChange={(e) => setBaseImp(e.target.value)} placeholder="Base Imponible" className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white tabular-nums" />
          <input type="number" step="0.01" value={exento} onChange={(e) => setExento(e.target.value)} placeholder="Monto Exento" className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white tabular-nums" />
          <input type="number" step="0.01" value={ivaPct} onChange={(e) => setIvaPct(e.target.value)} placeholder="IVA % (16)" className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white tabular-nums" />
          <input type="number" step="0.01" value={igtfPct} onChange={(e) => setIgtfPct(e.target.value)} placeholder="IGTF % (0 ó 3)" className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white tabular-nums" />
          <select value={retIvaPct} onChange={(e) => setRetIvaPct(e.target.value)} className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white">
            <option value="0">Sin Ret. IVA</option>
            <option value="75">Ret. IVA 75%</option>
            <option value="100">Ret. IVA 100%</option>
          </select>
          <div className="flex gap-1.5">
            <select value={moneda} onChange={(e) => setMoneda(e.target.value as "BS" | "USD")} className="px-2 py-2 rounded-xl border border-neutral-200 bg-white">
              <option value="BS">Bs</option>
              <option value="USD">USD</option>
            </select>
            <button type="submit" className="flex-1 px-3 py-2 rounded-xl bg-[#E85A28] text-white font-bold cursor-pointer">
              Registrar
            </button>
          </div>
        </div>
      </form>

      {/* Tabla Documentos */}
      <div className="bg-white/80 backdrop-blur-md border border-white/70 rounded-2xl p-5 shadow-xs space-y-3">
        <h3 className="text-sm font-black text-[#191818]">Documentos Fiscales ({docs.length})</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left tabular-nums">
            <thead className="bg-neutral-50 border-b border-neutral-200 uppercase text-[10px] text-neutral-500">
              <tr>
                <th className="px-3 py-2">Libro / Fecha</th>
                <th className="px-3 py-2">Factura / Control</th>
                <th className="px-3 py-2">RIF / Tercero</th>
                <th className="px-3 py-2 text-right">Base</th>
                <th className="px-3 py-2 text-right">IVA</th>
                <th className="px-3 py-2 text-right">IGTF</th>
                <th className="px-3 py-2 text-right">Total</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100">
              {docs.map((d) => (
                <tr key={d.id}>
                  <td className="px-3 py-2">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${d.tipo_libro === "COMPRA" ? "bg-blue-50 text-blue-700" : "bg-emerald-50 text-emerald-700"}`}>
                      {d.tipo_libro}
                    </span>
                    <p className="text-[11px] text-neutral-500 mt-0.5">{d.fecha}</p>
                  </td>
                  <td className="px-3 py-2 font-mono">{d.numero_factura} / {d.numero_control || "—"}</td>
                  <td className="px-3 py-2"><strong>{d.rif_tercero}</strong> · {d.nombre_tercero}</td>
                  <td className="px-3 py-2 text-right">{d.base_imponible.toFixed(2)}</td>
                  <td className="px-3 py-2 text-right">{d.iva_monto.toFixed(2)}</td>
                  <td className="px-3 py-2 text-right">{d.igtf_monto.toFixed(2)}</td>
                  <td className="px-3 py-2 text-right font-black">{d.total_documento.toFixed(2)} {d.moneda}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Calendario de Obligaciones Fiscales */}
      <div className="bg-white/80 backdrop-blur-md border border-white/70 rounded-2xl p-5 shadow-xs space-y-4">
        <h3 className="text-sm font-black text-[#191818] flex items-center gap-1.5">
          <CalendarClock className="w-4 h-4 text-[#E85A28]" /> Calendario de Obligaciones Fiscales
        </h3>
        <form onSubmit={crearObligacion} className="grid grid-cols-2 md:grid-cols-6 gap-2 text-xs">
          <select value={obTipo} onChange={(e) => setObTipo(e.target.value)} className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white font-bold">
            <option value="IVA">IVA</option>
            <option value="ISLR">ISLR</option>
            <option value="RETENCIONES">Retenciones</option>
            <option value="PATENTE_MUNICIPAL">Patente Municipal</option>
          </select>
          <input type="text" required value={obPeriodo} onChange={(e) => setObPeriodo(e.target.value)} placeholder="Período (2026-11)" className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white" />
          <input type="date" required value={obVence} onChange={(e) => setObVence(e.target.value)} className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white" />
          <input type="number" step="0.01" value={obMonto} onChange={(e) => setObMonto(e.target.value)} placeholder="Est. USD" className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white tabular-nums" />
          <input type="text" value={obDesc} onChange={(e) => setObDesc(e.target.value)} placeholder="Descripción..." className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white" />
          <button type="submit" className="px-3 py-2 rounded-xl bg-[#191818] text-white font-bold cursor-pointer">Agregar</button>
        </form>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          {obligaciones.map((o) => (
            <div key={o.id} className="p-3 rounded-xl border border-neutral-200 bg-white/70 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-black text-[#191818]">{o.tipo} · {o.periodo}</span>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${o.estado === "PAGADO" ? "bg-emerald-50 text-emerald-700" : o.estado === "DECLARADO" ? "bg-blue-50 text-blue-700" : "bg-amber-50 text-amber-800"}`}>
                  {o.estado}
                </span>
              </div>
              <p className="text-neutral-500">Vence: <strong>{o.fecha_vencimiento}</strong> · Est.: <strong className="tabular-nums">{formatearUsd(o.monto_estimado_usd)}</strong></p>
              <div className="flex gap-1.5">
                {(["PENDIENTE", "DECLARADO", "PAGADO"] as const).map((est) => (
                  <button key={est} type="button" onClick={() => void cambiarEstadoOb(o.id, est)} className={`px-2 py-1 rounded-lg text-[10px] font-bold cursor-pointer ${o.estado === est ? "bg-[#E85A28] text-white" : "bg-neutral-100 text-neutral-600"}`}>
                    {est}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
