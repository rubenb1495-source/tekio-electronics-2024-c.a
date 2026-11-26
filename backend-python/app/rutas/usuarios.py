from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.configuracion import configuracion
from app.servicios.auditoria_service import registrar_auditoria
from app.esquemas import (
    AccesoTemporalSalida,
    DesbloquearUsuarioEntrada,
    SucursalSalida,
    UsuarioActualizarEntrada,
    UsuarioCrearEntrada,
    UsuarioEstadoEntrada,
    UsuarioSalida,
)
from app.modelos import RolUsuario, Sucursal, Usuario
from app.core.permisos import Permiso, require_permiso
from app.seguridad import (
    ROLES_ADMINISTRATIVOS,
    generar_hash_clave,
    obtener_usuario_actual,
    requerir_roles,
)


enrutador = APIRouter(prefix="/api", tags=["Usuarios y Sucursales"])


_ALFABETO_MAYUS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_ALFABETO_MINUS = "abcdefghjkmnpqrstuvwxyz"
_ALFABETO_DIGITOS = "23456789"
_ALFABETO_COMPLETO = _ALFABETO_MAYUS + _ALFABETO_MINUS + _ALFABETO_DIGITOS


def generar_password_temporal(longitud: int = 10) -> str:
    """Genera una contraseña temporal legible y segura sin caracteres ambiguos (O/0, I/l/1)."""
    longitud_efectiva = max(8, min(longitud, 16))
    caracteres = [
        secrets.choice(_ALFABETO_MAYUS),
        secrets.choice(_ALFABETO_MAYUS),
        secrets.choice(_ALFABETO_MINUS),
        secrets.choice(_ALFABETO_MINUS),
        secrets.choice(_ALFABETO_DIGITOS),
        secrets.choice(_ALFABETO_DIGITOS),
    ]
    while len(caracteres) < longitud_efectiva:
        caracteres.append(secrets.choice(_ALFABETO_COMPLETO))
    secrets.SystemRandom().shuffle(caracteres)
    return "".join(caracteres)


def generar_username_unico(
    bd: Session,
    *,
    deseado: str | None,
    correo: str | None,
    nombre: str,
    excluir_id: int | None = None,
) -> str:
    base_raw = (deseado or "").strip().lower()
    if not base_raw and correo and "@" in correo:
        base_raw = correo.split("@", 1)[0].strip().lower()
    if not base_raw:
        base_raw = nombre.strip().lower()
    base = re.sub(r"[^a-z0-9._-]+", "", base_raw.replace(" ", "."))[:60] or "usuario"

    candidato = base
    sufijo = 1
    while True:
        q = bd.query(Usuario.id).filter(func.lower(Usuario.username) == candidato)
        if excluir_id is not None:
            q = q.filter(Usuario.id != excluir_id)
        if q.first() is None:
            return candidato
        sufijo += 1
        candidato = f"{base[:54]}{sufijo}"


@enrutador.get("/sucursales", response_model=list[SucursalSalida])
def listar_sucursales(
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[SucursalSalida]:
    sucursales = bd.query(Sucursal).order_by(Sucursal.id.asc()).all()
    return [SucursalSalida.model_validate(s) for s in sucursales]


@enrutador.get("/usuarios/operativos")
def listar_usuarios_operativos(
    _usuario: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> list[dict[str, object]]:
    """Lista todo el personal activo (con y sin acceso al sistema) para selectores del POS, cotizaciones y comisiones."""
    usuarios = (
        bd.query(Usuario)
        .filter(Usuario.activo.is_(True))
        .order_by(Usuario.nombre.asc(), Usuario.id.asc())
        .all()
    )
    return [
        {
            "id": u.id,
            "nombre": u.nombre,
            "rol": u.rol,
            "modalidad": u.modalidad,
            "tiene_acceso": u.tiene_acceso,
            "es_lider": u.rol == RolUsuario.LIDER.value,
            "sucursal_id": u.sucursal_id,
        }
        for u in usuarios
    ]


@enrutador.get("/usuarios", response_model=list[UsuarioSalida])
def listar_usuarios(
    rol: RolUsuario | None = Query(default=None),
    activo: bool | None = Query(default=None),
    tiene_acceso: bool | None = Query(default=None),
    _usuario: Usuario = Depends(require_permiso(Permiso.GESTIONAR_USUARIOS)),
    bd: Session = Depends(obtener_bd),
) -> list[UsuarioSalida]:
    consulta = bd.query(Usuario).options(joinedload(Usuario.sucursal))
    if rol is not None:
        consulta = consulta.filter(Usuario.rol == rol.value)
    if activo is not None:
        consulta = consulta.filter(Usuario.activo == activo)
    if tiene_acceso is not None:
        consulta = consulta.filter(Usuario.tiene_acceso == tiene_acceso)
    usuarios = consulta.order_by(Usuario.id.asc()).all()
    return [UsuarioSalida.model_validate(u) for u in usuarios]


@enrutador.post("/usuarios", response_model=UsuarioSalida, status_code=status.HTTP_201_CREATED)
def crear_usuario(
    datos: UsuarioCrearEntrada,
    _usuario: Usuario = Depends(require_permiso(Permiso.GESTIONAR_USUARIOS)),
    bd: Session = Depends(obtener_bd),
) -> UsuarioSalida:
    acceso = bool(datos.tiene_acceso)
    correo_normalizado: str | None = None
    clave_hash: str | None = None

    if acceso:
        assert datos.clave is not None
        if datos.correo:
            correo_normalizado = datos.correo.strip().lower()
            existente = bd.query(Usuario).filter(Usuario.correo == correo_normalizado).first()
            if existente is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Ya existe un usuario registrado con el correo '{correo_normalizado}'.",
                )
        clave_hash = generar_hash_clave(datos.clave)

    if datos.sucursal_id is not None:
        sucursal = bd.query(Sucursal).filter(Sucursal.id == datos.sucursal_id).first()
        if sucursal is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="La sucursal indicada no existe.",
            )

    username_final: str | None = None
    if acceso:
        if datos.username:
            u_norm = re.sub(r"[^a-z0-9._-]+", "", datos.username.strip().lower())
            if len(u_norm) < 3:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El nombre de usuario debe tener al menos 3 caracteres válidos.",
                )
            if bd.query(Usuario.id).filter(func.lower(Usuario.username) == u_norm).first() is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"El nombre de usuario '{u_norm}' ya está en uso.",
                )
            username_final = u_norm
        else:
            username_final = generar_username_unico(
                bd, deseado=None, correo=correo_normalizado, nombre=datos.nombre
            )

    nuevo = Usuario(
        nombre=datos.nombre,
        username=username_final,
        correo=correo_normalizado,
        clave_hash=clave_hash,
        rol=datos.rol.value,
        modalidad=datos.modalidad,
        telefono=datos.telefono.strip(),
        cedula=datos.cedula.strip(),
        tiene_acceso=acceso,
        sucursal_id=datos.sucursal_id,
        activo=True,
    )
    bd.add(nuevo)
    bd.commit()
    bd.refresh(nuevo)

    usuario_completo = (
        bd.query(Usuario)
        .options(joinedload(Usuario.sucursal))
        .filter(Usuario.id == nuevo.id)
        .first()
    )
    salida = UsuarioSalida.model_validate(usuario_completo)
    if acceso and usuario_completo is not None and datos.clave:
        salida.acceso_compartir = AccesoTemporalSalida(
            usuario_id=usuario_completo.id,
            nombre=usuario_completo.nombre,
            username=usuario_completo.username or usuario_completo.nombre,
            email=usuario_completo.correo,
            rol=RolUsuario(usuario_completo.rol),
            sucursal=usuario_completo.sucursal.nombre if usuario_completo.sucursal else "Multi-tienda",
            telefono=usuario_completo.telefono or "",
            password_temporal=datos.clave,
            url_app=configuracion.url_frontend_efectiva,
        )
    return salida


@enrutador.put("/usuarios/{usuario_id}", response_model=UsuarioSalida)
def actualizar_usuario(
    usuario_id: int,
    datos: UsuarioActualizarEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.GESTIONAR_USUARIOS)),
    bd: Session = Depends(obtener_bd),
) -> UsuarioSalida:
    usuario = (
        bd.query(Usuario)
        .options(joinedload(Usuario.sucursal))
        .filter(Usuario.id == usuario_id)
        .first()
    )
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Colaborador no encontrado.",
        )

    if usuario.id == usuario_actual.id and not datos.tiene_acceso:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes revocar tu propio acceso mientras tienes sesión activa.",
        )

    if datos.sucursal_id is not None:
        sucursal = bd.query(Sucursal).filter(Sucursal.id == datos.sucursal_id).first()
        if sucursal is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="La sucursal indicada no existe.",
            )

    usuario.nombre = datos.nombre
    usuario.rol = datos.rol.value
    usuario.modalidad = datos.modalidad
    usuario.telefono = datos.telefono.strip()
    usuario.cedula = datos.cedula.strip()
    usuario.sucursal_id = datos.sucursal_id
    acceso_edicion = bool(datos.tiene_acceso)
    usuario.tiene_acceso = acceso_edicion

    if acceso_edicion:
        if datos.username is not None and datos.username.strip():
            u_norm = re.sub(r"[^a-z0-9._-]+", "", datos.username.strip().lower())
            if len(u_norm) < 3:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El nombre de usuario debe tener al menos 3 caracteres válidos.",
                )
            dup_u = (
                bd.query(Usuario.id)
                .filter(func.lower(Usuario.username) == u_norm, Usuario.id != usuario_id)
                .first()
            )
            if dup_u is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"El nombre de usuario '{u_norm}' ya está en uso.",
                )
            usuario.username = u_norm
        elif not usuario.username:
            usuario.username = generar_username_unico(
                bd, deseado=None, correo=datos.correo, nombre=datos.nombre, excluir_id=usuario_id
            )
        if datos.correo:
            correo_norm = datos.correo.strip().lower()
            duplicado = (
                bd.query(Usuario)
                .filter(Usuario.correo == correo_norm, Usuario.id != usuario.id)
                .first()
            )
            if duplicado is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Ya existe otro usuario registrado con el correo '{correo_norm}'.",
                )
            usuario.correo = correo_norm
        else:
            usuario.correo = None
        if datos.clave:
            usuario.clave_hash = generar_hash_clave(datos.clave)
        elif not usuario.clave_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes asignar una contraseña (mínimo 6 caracteres) al habilitar el acceso por primera vez.",
            )
    else:
        usuario.username = None
        usuario.correo = None
        usuario.clave_hash = None

    bd.commit()
    bd.refresh(usuario)
    usuario_completo = (
        bd.query(Usuario)
        .options(joinedload(Usuario.sucursal))
        .filter(Usuario.id == usuario.id)
        .first()
    )
    return UsuarioSalida.model_validate(usuario_completo)


@enrutador.patch("/usuarios/{usuario_id}/estado", response_model=UsuarioSalida)
def cambiar_estado_usuario(
    usuario_id: int,
    datos: UsuarioEstadoEntrada,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.GESTIONAR_USUARIOS)),
    bd: Session = Depends(obtener_bd),
) -> UsuarioSalida:
    usuario = (
        bd.query(Usuario)
        .options(joinedload(Usuario.sucursal))
        .filter(Usuario.id == usuario_id)
        .first()
    )
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado.",
        )

    if usuario.id == usuario_actual.id and not datos.activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propia cuenta mientras tienes sesión activa.",
        )

    usuario.activo = datos.activo
    usuario.motivo_estado = datos.motivo
    bd.commit()
    bd.refresh(usuario)
    return UsuarioSalida.model_validate(usuario)


@enrutador.post("/usuarios/{usuario_id}/desbloquear", response_model=UsuarioSalida)
@enrutador.post("/personal/{usuario_id}/desbloquear", response_model=UsuarioSalida)
def desbloquear_usuario(
    usuario_id: int,
    datos: DesbloquearUsuarioEntrada | None = None,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.GESTIONAR_USUARIOS)),
    bd: Session = Depends(obtener_bd),
) -> UsuarioSalida:
    usuario = (
        bd.query(Usuario)
        .options(joinedload(Usuario.sucursal))
        .filter(Usuario.id == usuario_id)
        .first()
    )
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado.",
        )

    usuario.intentos_fallidos_login = 0
    usuario.cuenta_bloqueada = False
    usuario.bloqueado_hasta = None
    usuario.bloqueado_en = None
    clave_asignada = False
    if datos and datos.nueva_clave_temporal:
        usuario.clave_hash = generar_hash_clave(datos.nueva_clave_temporal)
        usuario.debe_cambiar_clave = True
        clave_asignada = True

    registrar_auditoria(
        bd,
        usuario=usuario_actual,
        modulo="SEGURIDAD",
        accion="DESBLOQUEAR_CUENTA",
        entidad_id=usuario.username or usuario.nombre or str(usuario.id),
        detalle_anterior={"cuenta_bloqueada": True},
        detalle_nuevo={
            "cuenta_bloqueada": False,
            "intentos_fallidos_login": 0,
            "clave_temporal_asignada": clave_asignada,
        },
    )
    bd.commit()
    bd.refresh(usuario)
    return UsuarioSalida.model_validate(usuario)


@enrutador.post("/usuarios/{usuario_id}/generar-acceso-temporal", response_model=AccesoTemporalSalida)
def generar_acceso_temporal(
    usuario_id: int,
    usuario_actual: Usuario = Depends(require_permiso(Permiso.GESTIONAR_USUARIOS)),
    bd: Session = Depends(obtener_bd),
) -> AccesoTemporalSalida:
    """Genera una contraseña temporal segura, desbloquea la cuenta si estaba bloqueada y devuelve datos listos para compartir."""
    usuario = (
        bd.query(Usuario)
        .options(joinedload(Usuario.sucursal))
        .filter(Usuario.id == usuario_id)
        .first()
    )
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado.",
        )

    if not usuario.tiene_acceso:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este colaborador no tiene acceso habilitado al sistema. Activa primero 'Tiene acceso al sistema'.",
        )

    if not usuario.username or not usuario.username.strip():
        usuario.username = generar_username_unico(
            bd,
            deseado=None,
            correo=usuario.correo,
            nombre=usuario.nombre,
            excluir_id=usuario.id,
        )

    estaba_bloqueada = bool(usuario.cuenta_bloqueada)
    password_temporal = generar_password_temporal(10)
    usuario.clave_hash = generar_hash_clave(password_temporal)
    usuario.intentos_fallidos_login = 0
    usuario.cuenta_bloqueada = False
    usuario.bloqueado_hasta = None
    usuario.bloqueado_en = None
    usuario.debe_cambiar_clave = True

    registrar_auditoria(
        bd,
        usuario=usuario_actual,
        modulo="SEGURIDAD",
        accion="GENERAR_ACCESO_TEMPORAL",
        entidad_id=usuario.username or usuario.nombre or str(usuario.id),
        detalle_anterior={"cuenta_bloqueada": estaba_bloqueada},
        detalle_nuevo={
            "cuenta_bloqueada": False,
            "intentos_fallidos_login": 0,
            "acceso_temporal_generado": True,
        },
    )
    bd.commit()
    bd.refresh(usuario)

    return AccesoTemporalSalida(
        usuario_id=usuario.id,
        nombre=usuario.nombre,
        username=usuario.username or usuario.nombre,
        email=usuario.correo,
        rol=RolUsuario(usuario.rol),
        sucursal=usuario.sucursal.nombre if usuario.sucursal else "Multi-tienda",
        telefono=usuario.telefono or "",
        password_temporal=password_temporal,
        url_app=configuracion.url_frontend_efectiva,
    )
