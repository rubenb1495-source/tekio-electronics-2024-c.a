"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  Banknote,
  CheckCircle2,
  ExternalLink,
  FileDown,
  Plus,
  Users,
} from "lucide-react";
import PanelImportacionAdmin from "@/components/PanelImportacionAdmin";
import { construirUrlWhatsApp } from "@/lib/whatsapp";
import {
  ErrorApi,
  descargarPdfApi,
  fechaHoyCaracas,
  formatearUsd,
  solicitarApi,
} from "@/servicios/api";
import type { InstrumentoFinanciero, UsuarioOperativo } from "@/tipos/finanzas";

interface EmpleadoNomina {
  id: number;
  usuario_id: number;
  usuario_nombre: string;
  usuario_rol: string;
  cedula: string;
  cargo: string;
  sucursal: string;
  salario_base_usd: number;
  bono_cestaticket_usd: number;
  datos_bancarios: string;
}

interface ReciboNomina {
  id: number;
  usuario_nombre: string;
  usuario_telefono?: string;
  cargo: string;
  salario_base_usd: number;
  bonos_usd: number;
  adelantos_usd: number;
  deduccion_ivss_usd: number;
  deduccion_faov_usd: number;
  deduccion_rpe_usd: number;
  neto_pagar_usd: number;
  comisiones_informativas_usd: number;
}

interface PeriodoNomina {
  id: number;
  codigo: string;
  tipo_periodo: string;
  fecha_inicio: string;
  fecha_fin: string;
  estado: "BORRADOR" | "PAGADA";
  total_neto_usd: number;
  instrumento: string;
  referencia_pago: string;
  fecha_pago: string | null;
  recibos: ReciboNomina[];
}

export default function PaginaNominaLaboral() {
  const hoy = fechaHoyCaracas();
  const [empleados, setEmpleados] = useState<EmpleadoNomina[]>([]);
  const [periodos, setPeriodos] = useState<PeriodoNomina[]>([]);
  const [usuarios, setUsuarios] = useState<UsuarioOperativo[]>([]);
  const [instrumentos, setInstrumentos] = useState<InstrumentoFinanciero[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  // Ficha laboral
  const [usuarioId, setUsuarioId] = useState("");
  const [cedula, setCedula] = useState("");
  const [cargo, setCargo] = useState("");
  const [salarioBase, setSalarioBase] = useState("");
  const [bono, setBono] = useState("40");
  const [datosBanco, setDatosBanco] = useState("");

  // Generar período
  const [tipoPeriodo, setTipoPeriodo] = useState<"QUINCENAL" | "MENSUAL">("QUINCENAL");
  const [fechaInicio, setFechaInicio] = useState(`${hoy.slice(0, 8)}01`);
  const [fechaFin, setFechaFin] = useState(hoy);
  const [instPagoId, setInstPagoId] = useState("");
  const [refPago, setRefPago] = useState("");

  const cargar = useCallback(async () => {
    setError(null);
    try {
      const [emps, pers, ops, insts] = await Promise.all([
        solicitarApi<EmpleadoNomina[]>("/api/finanzas/nomina/empleados"),
        solicitarApi<PeriodoNomina[]>("/api/finanzas/nomina/periodos"),
        solicitarApi<UsuarioOperativo[]>("/api/usuarios/operativos"),
        solicitarApi<InstrumentoFinanciero[]>("/api/finanzas/instrumentos"),
      ]);
      setEmpleados(emps);
      setPeriodos(pers);
      setUsuarios(ops);
      setInstrumentos(insts);
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "Error cargando nómina.");
    }
  }, []);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const guardarFicha = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setExito(null);
    try {
      await solicitarApi("/api/finanzas/nomina/empleados", {
        method: "POST",
        body: JSON.stringify({
          usuario_id: Number(usuarioId),
          cedula: cedula.trim(),
          cargo: cargo.trim(),
          salario_base_usd: Number(salarioBase || 0),
          bono_cestaticket_usd: Number(bono || 0),
          datos_bancarios: datosBanco.trim(),
        }),
      });
      setExito("Ficha laboral guardada correctamente.");
      setUsuarioId("");
      setSalarioBase("");
      await cargar();
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo guardar la ficha laboral.");
    }
  };

  const generarPeriodo = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setExito(null);
    try {
      const res = await solicitarApi<{ codigo: string; total_neto_usd: number }>(
        "/api/finanzas/nomina/periodos",
        {
          method: "POST",
          body: JSON.stringify({
            tipo_periodo: tipoPeriodo,
            fecha_inicio: fechaInicio,
            fecha_fin: fechaFin,
          }),
        }
      );
      setExito(`Nómina ${res.codigo} generada en BORRADOR por ${formatearUsd(res.total_neto_usd)}.`);
      await cargar();
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo generar el período.");
    }
  };

  const pagarPeriodo = async (periodoId: number) => {
    if (!instPagoId) {
      setError("Selecciona primero la cuenta/banco de pago en la barra de nómina.");
      return;
    }
    setError(null);
    setExito(null);
    try {
      const res = await solicitarApi<{ codigo: string }>(
        `/api/finanzas/nomina/periodos/${periodoId}/pagar`,
        {
          method: "POST",
          body: JSON.stringify({
            instrumento_id: Number(instPagoId),
            referencia_pago: refPago.trim(),
          }),
        }
      );
      setExito(`Nómina ${res.codigo} aprobada y pagada con egreso automático en caja/banco.`);
      setRefPago("");
      await cargar();
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo pagar la nómina.");
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-black text-[#191818] flex items-center gap-2">
          <Users className="w-6 h-6 text-[#E85A28]" />
          Gestión Laboral y Nómina
        </h2>
        <p className="text-sm text-neutral-500">
          Fichas laborales, cálculo quincenal/mensual (IVSS, FAOV, RPE), pago automático en bancos y recibos PDF + WhatsApp.
        </p>
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

      {/* Ficha Laboral */}
      <form onSubmit={guardarFicha} className="bg-white/80 backdrop-blur-md border border-white/70 rounded-2xl p-5 shadow-xs space-y-3 text-xs">
        <h3 className="text-sm font-black text-[#191818] flex items-center gap-1.5">
          <Plus className="w-4 h-4 text-[#E85A28]" /> Registrar / Actualizar Ficha Laboral
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-6 gap-2.5">
          <select required value={usuarioId} onChange={(e) => setUsuarioId(e.target.value)} className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white font-semibold">
            <option value="">Colaborador...</option>
            {usuarios.map((u) => <option key={u.id} value={String(u.id)}>{u.nombre} ({u.rol})</option>)}
          </select>
          <input type="text" value={cedula} onChange={(e) => setCedula(e.target.value)} placeholder="Cédula (V-...)" className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white" />
          <input type="text" value={cargo} onChange={(e) => setCargo(e.target.value)} placeholder="Cargo" className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white" />
          <input type="number" step="0.01" required value={salarioBase} onChange={(e) => setSalarioBase(e.target.value)} placeholder="Salario Mensual USD" className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white tabular-nums" />
          <input type="number" step="0.01" value={bono} onChange={(e) => setBono(e.target.value)} placeholder="Bono/Cestaticket USD" className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white tabular-nums" />
          <div className="flex gap-1.5">
            <input type="text" value={datosBanco} onChange={(e) => setDatosBanco(e.target.value)} placeholder="Datos pago" className="flex-1 px-2.5 py-2 rounded-xl border border-neutral-200 bg-white" />
            <button type="submit" className="px-3 py-2 rounded-xl bg-[#191818] text-white font-bold cursor-pointer">Guardar</button>
          </div>
        </div>
        {empleados.length > 0 && (
          <div className="flex flex-wrap gap-2 pt-1">
            {empleados.map((e) => (
              <span key={e.id} className="px-2.5 py-1 rounded-xl bg-neutral-100 text-[11px] font-semibold tabular-nums">
                <strong>{e.usuario_nombre}</strong> · {e.cargo} · Base {formatearUsd(e.salario_base_usd)} + Bono {formatearUsd(e.bono_cestaticket_usd)}
              </span>
            ))}
          </div>
        )}
      </form>

      <PanelImportacionAdmin flujoInicial="nomina_adelantos" alCompletar={() => void cargar()} />

      {/* Generar y Pagar Nómina */}
      <form onSubmit={generarPeriodo} className="bg-white/80 backdrop-blur-md border border-white/70 rounded-2xl p-5 shadow-xs space-y-3 text-xs">
        <h3 className="text-sm font-black text-[#191818]">Generar Lote de Nómina y Cuenta de Pago</h3>
        <div className="grid grid-cols-1 md:grid-cols-6 gap-2.5">
          <select value={tipoPeriodo} onChange={(e) => setTipoPeriodo(e.target.value as "QUINCENAL" | "MENSUAL")} className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white font-bold">
            <option value="QUINCENAL">Quincenal</option>
            <option value="MENSUAL">Mensual</option>
          </select>
          <input type="date" required value={fechaInicio} onChange={(e) => setFechaInicio(e.target.value)} className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white" />
          <input type="date" required value={fechaFin} onChange={(e) => setFechaFin(e.target.value)} className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white" />
          <select value={instPagoId} onChange={(e) => setInstPagoId(e.target.value)} className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white">
            <option value="">Banco para aprobar pago...</option>
            {instrumentos.map((i) => <option key={i.id} value={String(i.id)}>{i.nombre} ({i.moneda})</option>)}
          </select>
          <input type="text" value={refPago} onChange={(e) => setRefPago(e.target.value)} placeholder="Referencia pago" className="px-2.5 py-2 rounded-xl border border-neutral-200 bg-white" />
          <button type="submit" className="px-4 py-2 rounded-xl bg-[#E85A28] text-white font-bold cursor-pointer">
            Generar Lote
          </button>
        </div>
      </form>

      {/* Períodos de Nómina */}
      <div className="space-y-4">
        {periodos.map((p) => (
          <div key={p.id} className="bg-white/80 backdrop-blur-md border border-white/70 rounded-2xl p-5 shadow-xs space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono font-black text-[#191818]">{p.codigo}</span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${p.estado === "PAGADA" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-800"}`}>
                    {p.estado}
                  </span>
                </div>
                <p className="text-xs text-neutral-500">
                  {p.tipo_periodo}: {p.fecha_inicio} al {p.fecha_fin} · Total Neto:{" "}
                  <strong className="text-[#191818] tabular-nums">{formatearUsd(p.total_neto_usd)}</strong>
                  {p.instrumento ? ` · Pagado vía ${p.instrumento}` : ""}
                </p>
              </div>
              {p.estado === "BORRADOR" && (
                <button
                  type="button"
                  onClick={() => void pagarPeriodo(p.id)}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold cursor-pointer"
                >
                  <Banknote className="w-3.5 h-3.5" />
                  Aprobar y Pagar Nómina
                </button>
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left tabular-nums">
                <thead className="bg-neutral-50 border-b border-neutral-200 uppercase text-[10px] text-neutral-500">
                  <tr>
                    <th className="px-3 py-2">Colaborador</th>
                    <th className="px-3 py-2 text-right">Base + Bonos</th>
                    <th className="px-3 py-2 text-right">Deducciones</th>
                    <th className="px-3 py-2 text-right">Comis. (Info)</th>
                    <th className="px-3 py-2 text-right">Neto Pagar</th>
                    <th className="px-3 py-2 text-right">Recibo</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-100">
                  {p.recibos.map((r) => (
                    <tr key={r.id}>
                      <td className="px-3 py-2 font-semibold">{r.usuario_nombre} <span className="text-neutral-400">({r.cargo})</span></td>
                      <td className="px-3 py-2 text-right">{formatearUsd(r.salario_base_usd + r.bonos_usd)}</td>
                      <td className="px-3 py-2 text-right text-red-700">
                        -{formatearUsd(r.adelantos_usd + r.deduccion_ivss_usd + r.deduccion_faov_usd + r.deduccion_rpe_usd)}
                      </td>
                      <td className="px-3 py-2 text-right text-neutral-500">{formatearUsd(r.comisiones_informativas_usd)}</td>
                      <td className="px-3 py-2 text-right font-black text-emerald-700">{formatearUsd(r.neto_pagar_usd)}</td>
                      <td className="px-3 py-2 text-right space-x-1.5 whitespace-nowrap">
                        <button
                          type="button"
                          onClick={() => void descargarPdfApi(`/api/finanzas/nomina/recibos/${r.id}/pdf`, `Recibo_${p.codigo}_${r.id}.pdf`)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-neutral-200 bg-white font-bold cursor-pointer"
                        >
                          <FileDown className="w-3 h-3 text-[#E85A28]" /> PDF
                        </button>
                        <a
                          href={construirUrlWhatsApp(
                            `🧾 *RECIBO DE NÓMINA · TEKIO ELECTRONICS (${p.codigo})*\n👤 Colaborador: *${r.usuario_nombre}*\n📅 Período: ${p.fecha_inicio} al ${p.fecha_fin}\n💵 Neto pagado: *${formatearUsd(r.neto_pagar_usd)} USD*`,
                            r.usuario_telefono
                          )}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-600 text-white font-bold"
                        >
                          <ExternalLink className="w-3 h-3" /> WA
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
