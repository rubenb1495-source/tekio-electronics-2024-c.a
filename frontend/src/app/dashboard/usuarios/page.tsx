"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Plus,
  ShieldAlert,
  UserCheck,
  UserX,
  Users,
} from "lucide-react";
import BuscadorTabla from "@/componentes/BuscadorTabla";
import { usarSesion } from "@/contexto/SesionContexto";
import { ErrorApi, esRolAdministrativo, solicitarApi } from "@/servicios/api";
import type { RolUsuario, Sucursal, Usuario } from "@/tipos/dominio";

const ROLES_DISPONIBLES: RolUsuario[] = [
  "DIRECCION",
  "ADMINISTRACION",
  "LOGISTICA",
  "LIDER",
  "ASESORA",
  "TECNICO",
];

export default function PaginaUsuarios() {
  const { usuario } = usarSesion();
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [filtroRol, setFiltroRol] = useState<string>("");
  const [filtroActivo, setFiltroActivo] = useState<string>("");
  const [busqueda, setBusqueda] = useState<string>("");

  // Modal crear usuario
  const [modalCrear, setModalCrear] = useState(false);
  const [nombre, setNombre] = useState("");
  const [correo, setCorreo] = useState("");
  const [clave, setClave] = useState("");
  const [rolNuevo, setRolNuevo] = useState<RolUsuario>("ASESORA");
  const [sucursalId, setSucursalId] = useState<string>("");
  const [guardando, setGuardando] = useState(false);
  const [errorModal, setErrorModal] = useState<string | null>(null);

  // Modal cambio de estado (borrado lógico)
  const [usuarioEstado, setUsuarioEstado] = useState<Usuario | null>(null);
  const [motivoEstado, setMotivoEstado] = useState("");

  const permitido = usuario ? esRolAdministrativo(usuario.rol) : false;

  const cargarDatos = useCallback(async () => {
    if (!permitido) {
      setCargando(false);
      return;
    }
    setCargando(true);
    setError(null);
    try {
      const parametros = new URLSearchParams();
      if (filtroRol) parametros.set("rol", filtroRol);
      if (filtroActivo) parametros.set("activo", filtroActivo);
      const qs = parametros.toString() ? `?${parametros.toString()}` : "";

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
          : "No se pudieron cargar los usuarios."
      );
    } finally {
      setCargando(false);
    }
  }, [permitido, filtroRol, filtroActivo]);

  useEffect(() => {
    void cargarDatos();
  }, [cargarDatos]);

  const usuariosFiltrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return usuarios;
    return usuarios.filter((u) =>
      [u.nombre, u.correo, u.rol, u.sucursal?.nombre || ""]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [usuarios, busqueda]);

  if (!permitido) {
    return (
      <div className="bg-white rounded-2xl border border-red-200 p-8 text-center max-w-lg mx-auto mt-10">
        <ShieldAlert className="w-10 h-10 text-red-600 mx-auto mb-3" />
        <h2 className="text-lg font-bold text-slate-900">Acceso restringido</h2>
        <p className="text-sm text-slate-600 mt-1">
          Solo los roles <strong>DIRECCION</strong> y{" "}
          <strong>ADMINISTRACION</strong> pueden gestionar usuarios y sucursales.
        </p>
      </div>
    );
  }

  const manejarCrearUsuario = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorModal(null);
    if (clave.length < 6) {
      setErrorModal("La clave debe tener al menos 6 caracteres.");
      return;
    }

    setGuardando(true);
    try {
      await solicitarApi<Usuario>("/api/usuarios", {
        method: "POST",
        body: JSON.stringify({
          nombre: nombre.trim(),
          correo: correo.trim(),
          clave,
          rol: rolNuevo,
          sucursal_id: sucursalId ? Number(sucursalId) : null,
        }),
      });
      setModalCrear(false);
      setNombre("");
      setCorreo("");
      setClave("");
      setSucursalId("");
      await cargarDatos();
    } catch (err) {
      setErrorModal(
        err instanceof ErrorApi ? err.message : "Error al crear usuario."
      );
    } finally {
      setGuardando(false);
    }
  };

  const manejarCambioEstado = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!usuarioEstado) return;
    setErrorModal(null);
    if (motivoEstado.trim().length < 3) {
      setErrorModal("Indica un motivo obligatorio de al menos 3 caracteres.");
      return;
    }

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
      await cargarDatos();
    } catch (err) {
      setErrorModal(
        err instanceof ErrorApi ? err.message : "Error al actualizar estado."
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
            Usuarios, Roles y Sucursales
          </h2>
          <p className="text-sm text-slate-500">
            Control de acceso RBAC. Las asesoras y técnicos no reciben campos de
            costos desde el servidor.
          </p>
        </div>

        <button
          type="button"
          onClick={() => {
            setErrorModal(null);
            setModalCrear(true);
          }}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold cursor-pointer"
        >
          <Plus className="w-4 h-4" />
          Nuevo usuario
        </button>
      </div>

      {/* Filtros */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200 flex flex-wrap gap-3 items-center">
        <BuscadorTabla
          valor={busqueda}
          alCambiar={setBusqueda}
          placeholder="Buscar por nombre, correo, rol o sucursal..."
          totalRegistros={usuarios.length}
          totalFiltrados={usuariosFiltrados.length}
        />
        <select
          value={filtroRol}
          onChange={(e) => setFiltroRol(e.target.value)}
          className="px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
        >
          <option value="">Todos los roles</option>
          {ROLES_DISPONIBLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>

        <select
          value={filtroActivo}
          onChange={(e) => setFiltroActivo(e.target.value)}
          className="px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
        >
          <option value="">Todos los estados</option>
          <option value="true">Activos</option>
          <option value="false">Inactivos</option>
        </select>
      </div>

      {error && (
        <div className="flex items-center gap-2.5 p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Tabla de usuarios */}
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
        ) : usuariosFiltrados.length === 0 ? (
          <div className="p-10 text-center">
            <Users className="w-10 h-10 text-slate-300 mx-auto mb-2" />
            <p className="text-sm font-semibold text-slate-600">
              No hay usuarios que coincidan con los filtros.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Nombre</th>
                  <th className="px-4 py-3">Correo</th>
                  <th className="px-4 py-3">Rol</th>
                  <th className="px-4 py-3">Sucursal</th>
                  <th className="px-4 py-3">Estado</th>
                  <th className="px-4 py-3 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {usuariosFiltrados.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-semibold text-slate-900">
                      {u.nombre}
                    </td>
                    <td className="px-4 py-3 text-slate-600">{u.correo}</td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded-md bg-orange-50 text-[#C9461A] font-bold text-xs">
                        {u.rol}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {u.sucursal ? u.sucursal.nombre : "Sin asignar"}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold ${
                          u.activo
                            ? "bg-emerald-50 text-emerald-700"
                            : "bg-slate-200 text-slate-600"
                        }`}
                      >
                        {u.activo ? "Activo" : "Inactivo"}
                      </span>
                      {u.motivo_estado && (
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          {u.motivo_estado}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => {
                          setErrorModal(null);
                          setMotivoEstado("");
                          setUsuarioEstado(u);
                        }}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 text-xs font-semibold hover:bg-slate-100 cursor-pointer"
                      >
                        {u.activo ? (
                          <>
                            <UserX className="w-3.5 h-3.5 text-red-600" />
                            Desactivar
                          </>
                        ) : (
                          <>
                            <UserCheck className="w-3.5 h-3.5 text-emerald-600" />
                            Reactivar
                          </>
                        )}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Sucursales precargadas */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5">
        <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wide mb-3">
          Sucursales registradas ({sucursales.length})
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {sucursales.map((s) => (
            <div
              key={s.id}
              className="p-3 rounded-xl border border-slate-200 bg-slate-50 text-xs"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-bold text-slate-900">{s.nombre}</span>
                <span
                  className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                    s.estado === "ACTIVA"
                      ? "bg-emerald-100 text-emerald-800"
                      : "bg-slate-200 text-slate-600"
                  }`}
                >
                  {s.estado}
                </span>
              </div>
              <p className="text-slate-600 mt-1">{s.direccion}</p>
              {s.fecha_cierre && (
                <p className="text-[11px] text-red-600 font-medium mt-1">
                  Cerrada desde: {s.fecha_cierre}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Modal crear usuario */}
      {modalCrear && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4">
            <h3 className="text-lg font-black text-slate-900">
              Crear nuevo usuario
            </h3>
            {errorModal && (
              <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700">
                {errorModal}
              </div>
            )}
            <form onSubmit={manejarCrearUsuario} className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Nombre completo
                </label>
                <input
                  type="text"
                  required
                  value={nombre}
                  onChange={(e) => setNombre(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Correo electrónico
                </label>
                <input
                  type="email"
                  required
                  value={correo}
                  onChange={(e) => setCorreo(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Clave inicial (mín. 6 caracteres)
                </label>
                <input
                  type="password"
                  required
                  minLength={6}
                  value={clave}
                  onChange={(e) => setClave(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Rol
                  </label>
                  <select
                    value={rolNuevo}
                    onChange={(e) => setRolNuevo(e.target.value as RolUsuario)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                  >
                    {ROLES_DISPONIBLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Sucursal
                  </label>
                  <select
                    value={sucursalId}
                    onChange={(e) => setSucursalId(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white"
                  >
                    <option value="">Sin asignar</option>
                    {sucursales
                      .filter((s) => s.estado === "ACTIVA")
                      .map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.nombre}
                        </option>
                      ))}
                  </select>
                </div>
              </div>
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
                  {guardando ? "Guardando..." : "Crear usuario"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal cambio de estado */}
      {usuarioEstado && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4">
            <h3 className="text-lg font-black text-slate-900">
              {usuarioEstado.activo ? "Desactivar" : "Reactivar"} usuario
            </h3>
            <p className="text-sm text-slate-600">
              Usuario: <strong>{usuarioEstado.nombre}</strong> (
              {usuarioEstado.correo})
            </p>
            {errorModal && (
              <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700">
                {errorModal}
              </div>
            )}
            <form onSubmit={manejarCambioEstado} className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Motivo obligatorio
                </label>
                <input
                  type="text"
                  required
                  minLength={3}
                  value={motivoEstado}
                  onChange={(e) => setMotivoEstado(e.target.value)}
                  placeholder="Ej: Cambio de cargo o fin de relación laboral"
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setUsuarioEstado(null)}
                  className="px-4 py-2 rounded-xl border border-slate-300 text-sm font-semibold cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={guardando}
                  className="px-4 py-2 rounded-xl bg-[#E85A28] hover:bg-[#C9461A] text-white text-sm font-bold disabled:opacity-60 cursor-pointer"
                >
                  {guardando ? "Actualizando..." : "Confirmar"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
