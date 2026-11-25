from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

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
ZONA_CARACAS = ZoneInfo("America/Caracas")


@enrutador.post("/login", response_model=LoginSalida)
def iniciar_sesion(datos: LoginEntrada, bd: Session = Depends(obtener_bd)) -> LoginSalida:
    ident = (datos.identificador or "").strip().lower()
    usuario = (
        bd.query(Usuario)
        .options(joinedload(Usuario.sucursal))
        .filter(
            (func.lower(func.trim(Usuario.nombre)) == ident)
            | (func.lower(Usuario.username) == ident)
            | (func.lower(Usuario.correo) == ident)
        )
        .first()
    )

    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o clave incorrectos.",
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
            detail="Cuenta bloqueada por 5 intentos fallidos. Acceso bloqueado: contacte a Administración o Dirección.",
        )

    clave_ingresada = datos.clave or ""
    if not usuario.clave_hash or not verificar_clave(clave_ingresada, usuario.clave_hash):
        intentos = int(usuario.intentos_fallidos_login or 0) + 1
        usuario.intentos_fallidos_login = intentos
        if intentos >= MAX_INTENTOS_FALLIDOS:
            ahora_caracas = datetime.now(ZONA_CARACAS)
            usuario.cuenta_bloqueada = True
            usuario.bloqueado_hasta = ahora_caracas
            usuario.bloqueado_en = ahora_caracas
            registrar_auditoria(
                bd,
                usuario=usuario,
                modulo="SEGURIDAD",
                accion="BLOQUEO_ACCESO",
                entidad_id=usuario.username or usuario.nombre or str(usuario.id),
                detalle_anterior={"cuenta_bloqueada": False, "intentos_fallidos": intentos - 1},
                detalle_nuevo={
                    "cuenta_bloqueada": True,
                    "intentos_fallidos": intentos,
                    "bloqueado_en": ahora_caracas.isoformat(),
                    "fecha_bloqueo": ahora_caracas.isoformat(),
                },
            )
            bd.commit()
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Cuenta bloqueada por 5 intentos fallidos. Acceso bloqueado: contacte a Administración o Dirección.",
            )
        bd.commit()
        restantes = MAX_INTENTOS_FALLIDOS - intentos
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Clave incorrecta. Te quedan {restantes} intento(s) antes de bloquear tu acceso.",
        )

    if usuario.intentos_fallidos_login or usuario.cuenta_bloqueada or usuario.bloqueado_hasta or usuario.bloqueado_en:
        usuario.intentos_fallidos_login = 0
        usuario.cuenta_bloqueada = False
        usuario.bloqueado_hasta = None
        usuario.bloqueado_en = None
        bd.commit()

    token = crear_token_acceso(usuario)
    return LoginSalida(
        token=token,
        usuario=UsuarioSalida.model_validate(usuario),
    )


@enrutador.post("/cambiar-clave")
@enrutador.post("/cambiar-password")
def cambiar_password_propio(
    datos: CambiarPasswordEntrada,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, str]:
    actual = datos.clave_actual or ""
    nueva = datos.clave_nueva or ""
    if not usuario_actual.clave_hash or not verificar_clave(
        actual, usuario_actual.clave_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual ingresada es incorrecta.",
        )
    if actual == nueva:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La nueva contraseña debe ser diferente a la actual.",
        )

    usuario_actual.clave_hash = generar_hash_clave(nueva)
    usuario_actual.debe_cambiar_clave = False
    registrar_auditoria(
        bd,
        usuario=usuario_actual,
        modulo="SEGURIDAD",
        accion="CAMBIAR_CLAVE",
        entidad_id=usuario_actual.username or usuario_actual.nombre or str(usuario_actual.id),
        detalle_anterior={},
        detalle_nuevo={"cambio_exitoso": True},
    )
    bd.commit()
    return {"mensaje": "Clave actualizada correctamente."}


@enrutador.get("/perfil", response_model=UsuarioSalida)
def obtener_perfil(usuario_actual: Usuario = Depends(obtener_usuario_actual)) -> UsuarioSalida:
    return UsuarioSalida.model_validate(usuario_actual)
