from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
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


class SolicitarRecuperacionEntrada(BaseModel):
    usuario: str = Field(min_length=1, max_length=180)


class ConfirmarRecuperacionEntrada(BaseModel):
    usuario: str = Field(min_length=1, max_length=180)
    codigo: str = Field(min_length=4, max_length=32)
    nueva_clave: str = Field(min_length=8, max_length=128)
    confirmar_clave: str = Field(min_length=8, max_length=128)


def _enviar_codigo_smtp(destinatario: str, nombre: str, codigo: str) -> bool:
    import os
    import smtplib
    from email.message import EmailMessage

    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    pwd = os.getenv("SMTP_PASSWORD", "").strip()
    port = int(os.getenv("SMTP_PORT", "587") or "587")
    remitente = os.getenv("SMTP_FROM", user).strip() or user
    if not host or not user or not pwd or not destinatario:
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = "Código de recuperación de contraseña — Tekio Electronics"
        msg["From"] = remitente
        msg["To"] = destinatario
        msg.set_content(
            f"Hola {nombre},\n\n"
            f"Tu código temporal de recuperación es: {codigo}\n"
            "Este código vence en 15 minutos.\n\n"
            "Si no solicitaste este cambio, ignora este mensaje.\n"
            "— Tekio Electronics 2024, C.A."
        )
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(user, pwd)
            smtp.send_message(msg)
        return True
    except Exception:
        return False


@enrutador.post("/solicitar-recuperacion")
def solicitar_recuperacion_clave(
    datos: SolicitarRecuperacionEntrada,
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    import secrets

    ident = datos.usuario.strip().lower()
    usuario = (
        bd.query(Usuario)
        .filter(
            or_(
                func.lower(Usuario.username) == ident,
                func.lower(Usuario.correo) == ident,
                func.lower(Usuario.nombre) == ident,
            )
        )
        .first()
    )
    if usuario is None or not usuario.activo or not usuario.tiene_acceso:
        return {
            "modo": "ALERTA_ADMIN",
            "mensaje": (
                "Si el usuario existe, se notificó a Administración / Dirección. "
                "Contacta a tu supervisor para recibir tu clave temporal."
            ),
        }

    codigo = "".join(secrets.choice("0123456789") for _ in range(6))
    enviado_smtp = _enviar_codigo_smtp(usuario.correo or "", usuario.nombre, codigo)
    if enviado_smtp:
        usuario.recuperacion_token_hash = generar_hash_clave(codigo)
        usuario.recuperacion_expira_en = datetime.now(timezone.utc) + timedelta(minutes=15)
        registrar_auditoria(
            bd,
            usuario=usuario,
            modulo="SEGURIDAD",
            accion="SOLICITUD_RECUPERACION_SMTP",
            entidad_id=usuario.username or usuario.nombre or str(usuario.id),
            detalle_anterior={},
            detalle_nuevo={"canal": "SMTP", "expira_minutos": 15},
        )
        bd.commit()
        return {
            "modo": "SMTP",
            "mensaje": "Enviamos un código de 6 dígitos a tu correo registrado (válido por 15 minutos).",
        }

    registrar_auditoria(
        bd,
        usuario=usuario,
        modulo="SEGURIDAD",
        accion="SOLICITUD_RECUPERACION_CLAVE",
        entidad_id=usuario.username or usuario.nombre or str(usuario.id),
        detalle_anterior={},
        detalle_nuevo={
            "usuario_id": usuario.id,
            "nombre": usuario.nombre,
            "username": usuario.username or "",
            "motivo": "Usuario solicitó recuperación de clave desde Login",
        },
    )
    bd.commit()
    return {
        "modo": "ALERTA_ADMIN",
        "mensaje": (
            "Se registró una alerta para Administración / Dirección. "
            "Contacta a tu supervisor para que te genere y envíe una clave temporal."
        ),
    }


@enrutador.post("/confirmar-recuperacion")
def confirmar_recuperacion_clave(
    datos: ConfirmarRecuperacionEntrada,
    bd: Session = Depends(obtener_bd),
) -> dict[str, str]:
    if datos.nueva_clave != datos.confirmar_clave:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La confirmación no coincide con la nueva contraseña.",
        )
    ident = datos.usuario.strip().lower()
    usuario = (
        bd.query(Usuario)
        .filter(
            or_(
                func.lower(Usuario.username) == ident,
                func.lower(Usuario.correo) == ident,
                func.lower(Usuario.nombre) == ident,
            )
        )
        .first()
    )
    if (
        usuario is None
        or not usuario.recuperacion_token_hash
        or not usuario.recuperacion_expira_en
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No hay un código de recuperación activo para este usuario.",
        )
    expira = usuario.recuperacion_expira_en
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expira:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El código de recuperación ha expirado (15 minutos). Solicita uno nuevo.",
        )
    if not verificar_clave(datos.codigo.strip(), usuario.recuperacion_token_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El código de recuperación es incorrecto.",
        )

    usuario.clave_hash = generar_hash_clave(datos.nueva_clave)
    usuario.intentos_fallidos_login = 0
    usuario.cuenta_bloqueada = False
    usuario.bloqueado_hasta = None
    usuario.bloqueado_en = None
    usuario.debe_cambiar_clave = False
    usuario.recuperacion_token_hash = None
    usuario.recuperacion_expira_en = None
    registrar_auditoria(
        bd,
        usuario=usuario,
        modulo="SEGURIDAD",
        accion="RECUPERACION_CLAVE_CONFIRMADA",
        entidad_id=usuario.username or usuario.nombre or str(usuario.id),
        detalle_anterior={},
        detalle_nuevo={"desbloqueado": True},
    )
    bd.commit()
    return {"mensaje": "Contraseña restablecida correctamente. Ya puedes iniciar sesión."}
