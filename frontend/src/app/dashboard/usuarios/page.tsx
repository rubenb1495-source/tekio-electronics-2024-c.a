"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  KeyRound,
  Pencil,
  Plus,
  Share2,
  ShieldAlert,
  UserCheck,
  UserX,
  Users,
  X,
} from "lucide-react";
import BuscadorTabla from "@/componentes/BuscadorTabla";
import ModalCompartirAcceso from "@/components/ModalCompartirAcceso";
import TarjetaRespaldoBD from "@/components/TarjetaRespaldoBD";
import { usarSesion } from "@/contexto/SesionContexto";
import { ErrorApi, esRolAdministrativo, solicitarApi } from "@/servicios/api";
import type { AccesoTemporalUsuario, RolUsuario, Sucursal, Usuario } from "@/tipos/dominio";

const ROLES_DISPONIBLES: RolUsuario[] = [
  "ASESORA",
  "ENCARGADO",
  "LIDER",
  "TECNICO",
  "LOGISTICA",
  "ADMINISTRACION",
  "DIRECCION",
];

export default function PaginaPersonalYUsuarios() {
  const { usuario } = usarSesion();
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState<string | null>(null);

  // Filtros
  const [filtroRol, setFiltroRol] = useState<string>("");
  const [filtroAcceso, setFiltroAcceso] = useState<string>("");
  const [filtroActivo, setFiltroActivo] = useState<string>("");
  const [busqueda, setBusqueda] = useState<string>("");

  // Modal Crear / Editar Personal
  const [modalAbierto, setModalAbierto] = useState(false);
  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [teniaAccesoAntes, setTeniaAccesoAntes] = useState(false);
  const [nombre, setNombre] = useState("");
  const [rolForm, setRolForm] = useState<RolUsuario>("ASESORA");
  const [modalidad, setModalidad] = useState<"PRESENCIAL" | "ONLINE">("PRESENCIAL");
  const [telefono, setTelefono] = useState("");
  const [cedula, setCedula] = useState("");
  const [sucursalId, setSucursalId] = useState<string>("");
  const [tieneAcceso, setTieneAcceso] = useState(false);
  const [usernameForm, setUsernameForm] = useState("");
  const [correo, setCorreo] = useState("");
  const [clave, setClave] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [errorModal, setErrorModal] = useState<string | null>(null);

  // Modal cambio de estado (activar/desactivar sin borrar historial)
  const [usuarioEstado, setUsuarioEstado] = useState<Usuario | null>(null);
  const [motivoEstado, setMotivoEstado] = useState("");

  // Modal compartir acceso (WhatsApp / copiar credenciales)
  const [usuarioCompartir, setUsuarioCompartir] = useState<Usuario | null>(null);
  const [accesoCompartir, setAccesoCompartir] = useState<AccesoTemporalUsuario | null>(null);

  const permitido = usuario ? esRolAdministrativo(usuario.rol) : false;

  const cargarDatos = useCallback(async () => {
    if (!permitido) {
      setCargando(false);
      return;
    }
    setCargando(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (filtroRol) params.set("rol", filtroRol);
      if (filtroAcceso) params.set("tiene_acceso", filtroAcceso);
      if (filtroActivo) params.set("activo", filtroActivo);
      const qs = params.toString() ? `?${params.toString()}` : "";

      const [listaUsuarios, listaSucursales] = await Promise.all([
        solicitarApi<Usuario[]>(`/api/usuarios${qs}`),
        solicitarApi<Sucursal[]>("/api/sucursales"),
      ]);
      setUsuarios(listaUsuarios);
      setSucursales(listaSucursales);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo cargar el listado de personal y usuarios."
      );
    } finally {
      setCargando(false);
    }
  }, [permitido, filtroRol, filtroAcceso, filtroActivo]);

  useEffect(() => {
    void cargarDatos();
  }, [cargarDatos]);

  const usuariosFiltrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return usuarios;
    return usuarios.filter((u) =>
      [
        u.nombre,
        u.username || "",
        u.correo || "",
        u.telefono || "",
        u.cedula || "",
        u.rol,
        u.modalidad || "",
        u.sucursal?.nombre || "",
      ]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [usuarios, busqueda]);

  const abrirModalCrear = () => {
    setEditandoId(null);
    setTeniaAccesoAntes(false);
    setNombre("");
    setRolForm("ASESORA");
    setModalidad("PRESENCIAL");
    setTelefono("");
    setCedula("");
    setSucursalId(sucursales[0] ? String(sucursales[0].id) : "");
    setTieneAcceso(false); // Desactivado por defecto para registrar personal sin acceso rápidamente
    setUsernameForm("");
    setCorreo("");
    setClave("");
    setErrorModal(null);
    setModalAbierto(true);
  };

  const abrirModalEditar = (u: Usuario) => {
    setEditandoId(u.id);
    const accesoActual = u.tiene_acceso !== false;
    setTeniaAccesoAntes(accesoActual);
    setNombre(u.nombre);
    setRolForm(u.rol);
    setModalidad(u.modalidad === "ONLINE" ? "ONLINE" : "PRESENCIAL");
    setTelefono(u.telefono || "");
    setCedula(u.cedula || "");
    setSucursalId(u.sucursal ? String(u.sucursal.id) : "");
    setTieneAcceso(accesoActual);
    setUsernameForm(u.username || u.nombre || "");
    setCorreo(u.correo || "");
    setClave("");
    setErrorModal(null);
    setModalAbierto(true);
  };

  const guardarPersonal = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorModal(null);
    setExito(null);

    if (nombre.trim().length < 2) {
      setErrorModal("Ingresa el nombre completo (mínimo 2 caracteres).");
      return;
    }
    if (tieneAcceso) {
      const usrFinal = (usernameForm || nombre).trim();
      if (!usrFinal && !correo.trim()) {
        setErrorModal("Indica un Usuario de acceso o correo electrónico.");
        return;
      }
      if ((!editandoId || !teniaAccesoAntes) && clave.trim().length < 6) {
        setErrorModal("Asigna una contraseña de al menos 6 caracteres.");
        return;
      }
      if (clave.trim() && clave.trim().length < 6) {
        setErrorModal("La nueva contraseña debe tener al menos 6 caracteres.");
        return;
      }
    }

    setGuardando(true);
    try {
      const payload: Record<string, unknown> = {
        nombre: nombre.trim(),
        rol: rolForm,
        modalidad,
        telefono: telefono.trim(),
        cedula: cedula.trim(),
        sucursal_id: sucursalId ? Number(sucursalId) : null,
        tiene_acceso: tieneAcceso,
      };
      if (tieneAcceso) {
        payload.username = (usernameForm || nombre).trim().toLowerCase();
        if (correo.trim()) {
          payload.correo = correo.trim().toLowerCase();
        }
        if (clave.trim()) {
          payload.clave = clave.trim();
        }
      }

      if (editandoId) {
        await solicitarApi<Usuario>(`/api/usuarios/${editandoId}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        setExito(`Colaborador "${nombre.trim()}" actualizado correctamente.`);
      } else {
        const creado = await solicitarApi<Usuario>("/api/usuarios", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        setExito(
          `Colaborador "${nombre.trim()}" registrado correctamente${
            tieneAcceso ? " con acceso al sistema" : " (sin acceso al sistema)"
          }.`
        );
        if (creado.acceso_compartir) {
          setUsuarioCompartir(creado);
          setAccesoCompartir(creado.acceso_compartir);
        }
      }

      setModalAbierto(false);
      await cargarDatos();
    } catch (err) {
      setErrorModal(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo guardar el colaborador."
      );
    } finally {
      setGuardando(false);
    }
  };

  const confirmarCambioEstado = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!usuarioEstado) return;
    setErrorModal(null);
    setGuardando(true);
    try {
      await solicitarApi<Usuario>(`/api/usuarios/${usuarioEstado.id}/estado`, {
        method: "PATCH",
        body: JSON.stringify({
          activo: !usuarioEstado.activo,
          motivo: motivoEstado.trim(),
        }),
      });
      setUsuarioEstado(null);
      setMotivoEstado("");
      setExito("Estado del colaborador actualizado (historial preservado).");
      await cargarDatos();
    } catch (err) {
      setErrorModal(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo cambiar el estado."
      );
    } finally {
      setGuardando(false);
    }
  };

  if (!permitido) {
    return (
      <div className="bg-white/80 backdrop-blur-md rounded-2xl border border-red-200 p-8 text-center max-w-lg mx-auto mt-10">
        <ShieldAlert className="w-10 h-10 text-red-600 mx-auto mb-3" />
        <h2 className="text-lg font-bold text-[#191818]">Acceso restringido</h2>
        <p className="text-sm text-neutral-600 mt-1">
          Solo los roles <strong>DIRECCION</strong> y{" "}
          <strong>ADMINISTRACION</strong> pueden gestionar personal y usuarios.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Cabecera */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-[#191818] flex items-center gap-2">
            <Users className="w-6 h-6 text-[#E85A28]" />
            Personal y Usuarios
          </h2>
          <p className="text-sm text-neutral-500">
            Registra asesores online, líderes, técnicos y equipo con o sin acceso al sistema para el POS y comisiones.
          </p>
        </div>

        <button
          type="button"
          onClick={abrirModalCrear}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] text-white text-sm font-bold cursor-pointer transition-colors"
        >
          <Plus className="w-4 h-4" />
          Nuevo colaborador
        </button>
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

      {/* Respaldo completo de Base de Datos (visible solo para ADMINISTRACION) */}
      <TarjetaRespaldoBD />

      {/* Filtros */}
      <div className="bg-white/75 backdrop-blur-md border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        <div className="lg:col-span-2">
          <BuscadorTabla
            valor={busqueda}
            alCambiar={setBusqueda}
            placeholder="Buscar por nombre, teléfono, cédula o correo..."
            totalRegistros={usuarios.length}
            totalFiltrados={usuariosFiltrados.length}
          />
        </div>
        <select
          value={filtroRol}
          onChange={(e) => setFiltroRol(e.target.value)}
          className="px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm text-[#191818]"
        >
          <option value="">Todos los roles</option>
          {ROLES_DISPONIBLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <select
          value={filtroAcceso}
          onChange={(e) => setFiltroAcceso(e.target.value)}
          className="px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm text-[#191818]"
        >
          <option value="">Acceso: Todos</option>
          <option value="true">Con acceso al sistema</option>
          <option value="false">Sin acceso al sistema</option>
        </select>
        <select
          value={filtroActivo}
          onChange={(e) => setFiltroActivo(e.target.value)}
          className="px-3 py-2 rounded-xl border border-neutral-200 bg-white text-sm text-[#191818]"
        >
          <option value="">Estado: Todos</option>
          <option value="true">Activos</option>
          <option value="false">Inactivos</option>
        </select>
      </div>

      {/* Tabla de personal */}
      <div className="bg-white/75 backdrop-blur-md border border-white/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl overflow-hidden">
        {cargando ? (
          <div className="p-8 text-center text-sm text-neutral-500">
            Cargando personal...
          </div>
        ) : usuariosFiltrados.length === 0 ? (
          <div className="p-8 text-center text-sm text-neutral-500">
            No se encontraron colaboradores con esos filtros.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-neutral-50/90 border-b border-neutral-200 text-xs uppercase text-neutral-500">
                <tr>
                  <th className="px-4 py-3">Nombre</th>
                  <th className="px-4 py-3">Rol</th>
                  <th className="px-4 py-3">Modalidad</th>
                  <th className="px-4 py-3">Teléfono</th>
                  <th className="px-4 py-3">Acceso</th>
                  <th className="px-4 py-3">Estado</th>
                  <th className="px-4 py-3 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {usuariosFiltrados.map((u) => {
                  const conAcceso = u.tiene_acceso !== false;
                  const esOnline = u.modalidad === "ONLINE";
                  return (
                    <tr key={u.id} className="hover:bg-white/60">
                      <td className="px-4 py-3">
                        <p className="font-bold text-[#191818]">
                          {u.nombre}
                          {u.username && (
                            <span className="ml-1.5 font-mono text-[11px] font-semibold text-[#E85A28]">
                              @{u.username}
                            </span>
                          )}
                        </p>
                        <p className="text-xs text-neutral-500">
                          {u.correo || "Sin correo"}
                          {u.cedula ? ` · C.I.: ${u.cedula}` : ""}
                          {u.sucursal ? ` · ${u.sucursal.nombre}` : ""}
                        </p>
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-flex px-2.5 py-0.5 rounded-full text-xs font-bold bg-[#FDF0EB] text-[#E85A28]">
                          {u.rol}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                            esOnline
                              ? "bg-indigo-50 text-indigo-700 border-indigo-200"
                              : "bg-neutral-100 text-neutral-700 border-neutral-200"
                          }`}
                        >
                          {esOnline ? "Online" : "Presencial"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-neutral-700 font-mono">
                        {u.telefono || "—"}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold border ${
                            conAcceso
                              ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                              : "bg-amber-50 text-amber-800 border-amber-200"
                          }`}
                        >
                          {conAcceso ? "Con acceso" : "Solo comisiones"}
                        </span>
                      </td>
                      <td className="px-4 py-3 space-y-1">
                        <span
                          className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-bold ${
                            u.activo
                              ? "bg-emerald-50 text-emerald-700"
                              : "bg-red-50 text-red-700"
                          }`}
                        >
                          {u.activo ? "Activo" : "Inactivo"}
                        </span>
                        {u.cuenta_bloqueada && (
                          <div className="flex items-center gap-1.5">
                            <span className="inline-flex px-2 py-0.5 rounded-full text-[10px] font-black bg-red-600 text-white">
                              Bloqueada
                            </span>
                            <button
                              type="button"
                              onClick={async () => {
                                try {
                                  await solicitarApi(`/api/usuarios/${u.id}/desbloquear`, {
                                    method: "POST",
                                  });
                                  setExito(`Cuenta de "${u.nombre}" desbloqueada correctamente.`);
                                  await cargarDatos();
                                } catch (err) {
                                  setError(
                                    err instanceof ErrorApi
                                      ? err.message
                                      : "No se pudo desbloquear la cuenta."
                                  );
                                }
                              }}
                              className="px-2 py-0.5 rounded-lg bg-[#E85A28] hover:bg-[#D14D1F] text-white text-[10px] font-bold cursor-pointer"
                            >
                              Desbloquear
                            </button>
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right whitespace-nowrap space-x-1.5">
                        {conAcceso && (
                          <button
                            type="button"
                            onClick={() => {
                              setUsuarioCompartir(u);
                              setAccesoCompartir(null);
                            }}
                            title="Generar clave temporal y compartir acceso por WhatsApp"
                            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 text-xs font-bold text-emerald-700 cursor-pointer"
                          >
                            <Share2 className="w-3.5 h-3.5" />
                            Regenerar clave temporal
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => abrirModalEditar(u)}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-neutral-200 bg-white hover:bg-neutral-50 text-xs font-bold text-[#191818] cursor-pointer"
                        >
                          <Pencil className="w-3.5 h-3.5 text-[#E85A28]" />
                          Editar
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setErrorModal(null);
                            setMotivoEstado("");
                            setUsuarioEstado(u);
                          }}
                          className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border text-xs font-bold cursor-pointer ${
                            u.activo
                              ? "border-red-200 bg-red-50 text-red-700 hover:bg-red-100"
                              : "border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                          }`}
                        >
                          {u.activo ? (
                            <>
                              <UserX className="w-3.5 h-3.5" />
                              Desactivar
                            </>
                          ) : (
                            <>
                              <UserCheck className="w-3.5 h-3.5" />
                              Activar
                            </>
                          )}
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

      {/* Modal Crear / Editar Personal */}
      {modalAbierto && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white/95 backdrop-blur-md border border-white/60 rounded-2xl max-w-lg w-full p-6 shadow-xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-black text-[#191818]">
                {editandoId ? "Editar colaborador" : "Nuevo colaborador"}
              </h3>
              <button
                type="button"
                onClick={() => setModalAbierto(false)}
                className="text-neutral-400 hover:text-neutral-700 cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {errorModal && (
              <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700">
                {errorModal}
              </div>
            )}

            <form onSubmit={guardarPersonal} className="space-y-3.5">
              <div>
                <label className="block text-xs font-bold text-neutral-700 mb-1">
                  Nombre completo *
                </label>
                <input
                  type="text"
                  required
                  minLength={2}
                  value={nombre}
                  onChange={(e) => setNombre(e.target.value)}
                  placeholder="Ej. María Gómez"
                  className="w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-neutral-700 mb-1">
                    Rol *
                  </label>
                  <select
                    value={rolForm}
                    onChange={(e) => setRolForm(e.target.value as RolUsuario)}
                    className="w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm bg-white"
                  >
                    {ROLES_DISPONIBLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-bold text-neutral-700 mb-1">
                    Modalidad
                  </label>
                  <select
                    value={modalidad}
                    onChange={(e) =>
                      setModalidad(e.target.value as "PRESENCIAL" | "ONLINE")
                    }
                    className="w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm bg-white"
                  >
                    <option value="PRESENCIAL">Presencial (Tienda)</option>
                    <option value="ONLINE">Online (Asesor Remoto)</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-neutral-700 mb-1">
                    Teléfono / WhatsApp (opcional)
                  </label>
                  <input
                    type="text"
                    value={telefono}
                    onChange={(e) => setTelefono(e.target.value)}
                    placeholder="Ej. 0414-1234567"
                    className="w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-neutral-700 mb-1">
                    Cédula (opcional)
                  </label>
                  <input
                    type="text"
                    value={cedula}
                    onChange={(e) => setCedula(e.target.value)}
                    placeholder="Ej. V-24567890"
                    className="w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-neutral-700 mb-1">
                  Sucursal asignada (opcional)
                </label>
                <select
                  value={sucursalId}
                  onChange={(e) => setSucursalId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm bg-white"
                >
                  <option value="">Multi-tienda / Sin sede fija</option>
                  {sucursales.map((s) => (
                    <option key={s.id} value={String(s.id)}>
                      {s.nombre}
                    </option>
                  ))}
                </select>
              </div>

              {/* Switch / Toggle Dar acceso al sistema */}
              <div className="rounded-xl border border-neutral-200 bg-neutral-50/80 p-3.5 space-y-3">
                <label className="flex items-center justify-between gap-3 cursor-pointer">
                  <div className="flex items-center gap-2">
                    <KeyRound className="w-4 h-4 text-[#E85A28]" />
                    <div>
                      <p className="text-xs font-bold text-[#191818]">
                        Tiene acceso al sistema
                      </p>
                      <p className="text-[11px] text-neutral-500">
                        {tieneAcceso
                          ? "Podrá iniciar sesión con su usuario (nombre) o correo y contraseña."
                          : "Sin acceso: aparecerá en POS, taller y comisiones sin necesidad de usuario ni correo."}
                      </p>
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={tieneAcceso}
                    onChange={(e) => {
                      const activo = e.target.checked;
                      setTieneAcceso(activo);
                      if (activo && !usernameForm.trim() && nombre.trim()) {
                        setUsernameForm(nombre.trim());
                      }
                    }}
                    className="w-4 h-4 accent-[#E85A28]"
                  />
                </label>

                {tieneAcceso && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-neutral-200">
                    <div className="sm:col-span-2">
                      <label className="block text-xs font-bold text-neutral-700 mb-1">
                        Usuario de acceso (Nombre) *
                      </label>
                      <input
                        type="text"
                        required
                        value={usernameForm}
                        onChange={(e) => setUsernameForm(e.target.value)}
                        placeholder={nombre || "Ej. carlos.perez"}
                        className="w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm bg-white"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-neutral-700 mb-1">
                        Correo electrónico (opcional)
                      </label>
                      <input
                        type="email"
                        value={correo}
                        onChange={(e) => setCorreo(e.target.value)}
                        placeholder="opcional@tekioelectronics.com"
                        className="w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm bg-white"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-neutral-700 mb-1">
                        {editandoId && teniaAccesoAntes
                          ? "Nueva contraseña (opcional)"
                          : "Contraseña *"}
                      </label>
                      <input
                        type="password"
                        required={!editandoId || !teniaAccesoAntes}
                        minLength={6}
                        value={clave}
                        onChange={(e) => setClave(e.target.value)}
                        placeholder="Mínimo 6 caracteres"
                        className="w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm bg-white"
                      />
                    </div>
                  </div>
                )}
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setModalAbierto(false)}
                  className="px-4 py-2 rounded-xl border border-neutral-300 text-xs font-bold cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={guardando}
                  className="px-4 py-2 rounded-xl bg-[#E85A28] hover:bg-[#D14D1F] disabled:opacity-50 text-white text-xs font-bold cursor-pointer"
                >
                  {guardando
                    ? "Guardando..."
                    : editandoId
                    ? "Guardar cambios"
                    : "Registrar colaborador"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal Activar / Desactivar */}
      {usuarioEstado && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white/95 backdrop-blur-md border border-white/60 rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4">
            <h3 className="text-lg font-black text-[#191818]">
              {usuarioEstado.activo
                ? `Desactivar a ${usuarioEstado.nombre}`
                : `Reactivar a ${usuarioEstado.nombre}`}
            </h3>
            <p className="text-xs text-neutral-600">
              Su historial de ventas y comisiones se conservará intacto.
            </p>
            {errorModal && (
              <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700">
                {errorModal}
              </div>
            )}
            <form onSubmit={confirmarCambioEstado} className="space-y-3">
              <input
                type="text"
                required
                minLength={3}
                value={motivoEstado}
                onChange={(e) => setMotivoEstado(e.target.value)}
                placeholder="Motivo del cambio de estado..."
                className="w-full px-3 py-2 rounded-xl border border-neutral-300 text-sm"
              />
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setUsuarioEstado(null)}
                  className="px-4 py-2 rounded-xl border border-neutral-300 text-xs font-bold cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={guardando}
                  className="px-4 py-2 rounded-xl bg-[#E85A28] hover:bg-[#D14D20] text-white text-xs font-bold cursor-pointer"
                >
                  Confirmar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {/* Modal Compartir Acceso (WhatsApp / Copiar credenciales) */}
      <ModalCompartirAcceso
        abierto={Boolean(usuarioCompartir || accesoCompartir)}
        usuarioObjetivo={usuarioCompartir}
        accesoInicial={accesoCompartir}
        alCerrar={() => {
          setUsuarioCompartir(null);
          setAccesoCompartir(null);
        }}
        alRegenerar={() => void cargarDatos()}
      />
    </div>
  );
}
