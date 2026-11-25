from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.esquemas import (
    SucursalSalida,
    UsuarioActualizarEntrada,
    UsuarioCrearEntrada,
    UsuarioEstadoEntrada,
    UsuarioSalida,
)
from app.modelos import RolUsuario, Sucursal, Usuario
from app.seguridad import (
    ROLES_ADMINISTRATIVOS,
    generar_hash_clave,
    obtener_usuario_actual,
    requerir_roles,
)


enrutador = APIRouter(prefix="/api", tags=["Usuarios y Sucursales"])


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
    _usuario: Usuario = Depends(requerir_roles(*ROLES_ADMINISTRATIVOS)),
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
    _usuario: Usuario = Depends(requerir_roles(*ROLES_ADMINISTRATIVOS)),
    bd: Session = Depends(obtener_bd),
) -> UsuarioSalida:
    acceso = bool(datos.tiene_acceso)
    correo_normalizado: str | None = None
    clave_hash: str | None = None

    if acceso:
        assert datos.correo is not None and datos.clave is not None
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

    nuevo = Usuario(
        nombre=datos.nombre,
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
    return UsuarioSalida.model_validate(usuario_completo)


@enrutador.put("/usuarios/{usuario_id}", response_model=UsuarioSalida)
def actualizar_usuario(
    usuario_id: int,
    datos: UsuarioActualizarEntrada,
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_ADMINISTRATIVOS)),
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
    usuario.tiene_acceso = datos.tiene_acceso

    if datos.tiene_acceso:
        assert datos.correo is not None
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
        if datos.clave:
            usuario.clave_hash = generar_hash_clave(datos.clave)
        elif not usuario.clave_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes asignar una contraseña (mínimo 6 caracteres) al habilitar el acceso por primera vez.",
            )
    else:
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
    usuario_actual: Usuario = Depends(requerir_roles(*ROLES_ADMINISTRATIVOS)),
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
