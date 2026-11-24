from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.esquemas import (
    SucursalSalida,
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


@enrutador.get("/usuarios", response_model=list[UsuarioSalida])
def listar_usuarios(
    rol: RolUsuario | None = Query(default=None),
    activo: bool | None = Query(default=None),
    _usuario: Usuario = Depends(requerir_roles(*ROLES_ADMINISTRATIVOS)),
    bd: Session = Depends(obtener_bd),
) -> list[UsuarioSalida]:
    consulta = bd.query(Usuario).options(joinedload(Usuario.sucursal))
    if rol is not None:
        consulta = consulta.filter(Usuario.rol == rol.value)
    if activo is not None:
        consulta = consulta.filter(Usuario.activo == activo)
    usuarios = consulta.order_by(Usuario.id.asc()).all()
    return [UsuarioSalida.model_validate(u) for u in usuarios]


@enrutador.post("/usuarios", response_model=UsuarioSalida, status_code=status.HTTP_201_CREATED)
def crear_usuario(
    datos: UsuarioCrearEntrada,
    _usuario: Usuario = Depends(requerir_roles(*ROLES_ADMINISTRATIVOS)),
    bd: Session = Depends(obtener_bd),
) -> UsuarioSalida:
    correo_normalizado = datos.correo.strip().lower()
    existente = bd.query(Usuario).filter(Usuario.correo == correo_normalizado).first()
    if existente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un usuario registrado con el correo '{correo_normalizado}'.",
        )

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
        clave_hash=generar_hash_clave(datos.clave),
        rol=datos.rol.value,
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
