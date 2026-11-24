from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.esquemas import LoginEntrada, LoginSalida, UsuarioSalida
from app.modelos import Usuario
from app.seguridad import crear_token_acceso, obtener_usuario_actual, verificar_clave


enrutador = APIRouter(prefix="/api/auth", tags=["Autenticación"])


@enrutador.post("/login", response_model=LoginSalida)
def iniciar_sesion(datos: LoginEntrada, bd: Session = Depends(obtener_bd)) -> LoginSalida:
    correo_normalizado = datos.correo.strip().lower()
    usuario = (
        bd.query(Usuario)
        .options(joinedload(Usuario.sucursal))
        .filter(Usuario.correo == correo_normalizado)
        .first()
    )

    if usuario is None or not verificar_clave(datos.clave, usuario.clave_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o clave incorrectos.",
        )

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu cuenta se encuentra desactivada. Contacta a Dirección o Administración.",
        )

    token = crear_token_acceso(usuario)
    return LoginSalida(
        token=token,
        usuario=UsuarioSalida.model_validate(usuario),
    )


@enrutador.get("/perfil", response_model=UsuarioSalida)
def obtener_perfil(usuario_actual: Usuario = Depends(obtener_usuario_actual)) -> UsuarioSalida:
    return UsuarioSalida.model_validate(usuario_actual)
