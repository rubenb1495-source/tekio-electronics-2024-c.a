from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.esquemas import CambiarPasswordEntrada, LoginEntrada, LoginSalida, UsuarioSalida
from app.modelos import Usuario
from app.seguridad import (
    crear_token_acceso,
    generar_hash_clave,
    obtener_usuario_actual,
    verificar_clave,
)
from app.servicios.auditoria_service import registrar_auditoria


enrutador = APIRouter(prefix="/api/auth", tags=["Autenticación"])
MAX_INTENTOS_FALLIDOS = 5


@enrutador.post("/login", response_model=LoginSalida)
def iniciar_sesion(datos: LoginEntrada, bd: Session = Depends(obtener_bd)) -> LoginSalida:
    ident = (datos.identificador or "").strip().lower()
    usuario = (
        bd.query(Usuario)
        .options(joinedload(Usuario.sucursal))
        .filter(
            (func.lower(Usuario.correo) == ident)
            | (func.lower(Usuario.username) == ident)
        )
        .first()
    )

    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario/correo o contraseña incorrectos.",
        )

    if not usuario.tiene_acceso:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este colaborador no tiene acceso habilitado al sistema.",
        )

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu cuenta se encuentra desactivada. Contacta a Dirección o Administración.",
        )

    if usuario.cuenta_bloqueada:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Tu cuenta está bloqueada por exceder 5 intentos fallidos de acceso. Contacta a Dirección o Administración para desbloquearla.",
        )

    if not usuario.clave_hash or not verificar_clave(datos.clave, usuario.clave_hash):
        intentos = int(usuario.intentos_fallidos_login or 0) + 1
        usuario.intentos_fallidos_login = intentos
        if intentos >= MAX_INTENTOS_FALLIDOS:
            usuario.cuenta_bloqueada = True
            usuario.bloqueado_hasta = datetime.now(timezone.utc)
            registrar_auditoria(
                bd,
                usuario=usuario,
                modulo="SEGURIDAD",
                accion="CUENTA_BLOQUEADA_LOGIN",
                entidad_id=usuario.username or usuario.correo or str(usuario.id),
                detalle_anterior={"cuenta_bloqueada": False, "intentos_fallidos_login": intentos - 1},
                detalle_nuevo={"cuenta_bloqueada": True, "intentos_fallidos_login": intentos},
            )
            bd.commit()
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Cuenta bloqueada automáticamente tras 5 intentos fallidos de acceso. Se notificó a Dirección/Administración.",
            )
        bd.commit()
        restantes = MAX_INTENTOS_FALLIDOS - intentos
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Usuario/correo o contraseña incorrectos. Te quedan {restantes} intento(s) antes del bloqueo.",
        )

    if usuario.intentos_fallidos_login or usuario.cuenta_bloqueada or usuario.bloqueado_hasta:
        usuario.intentos_fallidos_login = 0
        usuario.cuenta_bloqueada = False
        usuario.bloqueado_hasta = None
        bd.commit()

    token = crear_token_acceso(usuario)
    return LoginSalida(
        token=token,
        usuario=UsuarioSalida.model_validate(usuario),
    )


@enrutador.post("/cambiar-password")
def cambiar_password_propio(
    datos: CambiarPasswordEntrada,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, str]:
    if not usuario_actual.clave_hash or not verificar_clave(
        datos.clave_actual, usuario_actual.clave_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual ingresada es incorrecta.",
        )
    if datos.clave_actual == datos.clave_nueva:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La nueva contraseña debe ser diferente a la actual.",
        )

    usuario_actual.clave_hash = generar_hash_clave(datos.clave_nueva)
    registrar_auditoria(
        bd,
        usuario=usuario_actual,
        modulo="SEGURIDAD",
        accion="CAMBIAR_PASSWORD",
        entidad_id=usuario_actual.username or usuario_actual.correo or str(usuario_actual.id),
        detalle_anterior={},
        detalle_nuevo={"cambio_exitoso": True},
    )
    bd.commit()
    return {"mensaje": "Contraseña actualizada correctamente."}


@enrutador.get("/perfil", response_model=UsuarioSalida)
def obtener_perfil(usuario_actual: Usuario = Depends(obtener_usuario_actual)) -> UsuarioSalida:
    return UsuarioSalida.model_validate(usuario_actual)
