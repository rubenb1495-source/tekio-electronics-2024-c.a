from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, joinedload

from app.base_datos import obtener_bd
from app.configuracion import configuracion
from app.modelos import RolUsuario, Usuario


esquema_bearer = HTTPBearer(auto_error=False)

ROLES_SIN_COSTOS: frozenset[str] = frozenset({
    RolUsuario.ASESORA.value,
    RolUsuario.TECNICO.value,
})

ROLES_ADMINISTRATIVOS: tuple[str, ...] = (
    RolUsuario.DIRECCION.value,
    RolUsuario.ADMINISTRACION.value,
)


def generar_hash_clave(clave_plana: str) -> str:
    """Genera hash seguro con scrypt y sal aleatoria."""
    sal = secrets.token_hex(16)
    derivada = hashlib.scrypt(
        clave_plana.encode("utf-8"),
        salt=sal.encode("utf-8"),
        n=16384,
        r=8,
        p=1,
        dklen=64,
    ).hex()
    return f"scrypt${sal}${derivada}"


def verificar_clave(clave_plana: str, clave_hash: str) -> bool:
    """Verifica la contraseña en tiempo constante."""
    try:
        prefijo, sal, hash_guardado = clave_hash.split("$", 2)
        if prefijo != "scrypt":
            return False
    except ValueError:
        return False

    derivada = hashlib.scrypt(
        clave_plana.encode("utf-8"),
        salt=sal.encode("utf-8"),
        n=16384,
        r=8,
        p=1,
        dklen=64,
    ).hex()
    return hmac.compare_digest(derivada, hash_guardado)


def crear_token_acceso(usuario: Usuario) -> str:
    """Firma un JWT con expiración y rol del usuario."""
    ahora = datetime.now(timezone.utc)
    expiracion = ahora + timedelta(hours=configuracion.EXPIRACION_JWT_HORAS)
    carga = {
        "sub": str(usuario.id),
        "correo": usuario.correo,
        "rol": usuario.rol,
        "iat": int(ahora.timestamp()),
        "exp": int(expiracion.timestamp()),
    }
    return jwt.encode(carga, configuracion.secreto_jwt_efectivo, algorithm=configuracion.ALGORITMO_JWT)


def puede_ver_costos(rol: str) -> bool:
    """Determina si el rol puede recibir campos de costos desde el backend."""
    return rol not in ROLES_SIN_COSTOS


def obtener_usuario_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(esquema_bearer),
    bd: Session = Depends(obtener_bd),
) -> Usuario:
    """Valida el JWT Bearer y devuelve el usuario activo."""
    if credenciales is None or not credenciales.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida. Inicia sesión para continuar.",
        )

    try:
        carga = jwt.decode(
            credenciales.credentials,
            configuracion.secreto_jwt_efectivo,
            algorithms=[configuracion.ALGORITMO_JWT],
        )
        usuario_id = int(carga["sub"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de sesión inválido o expirado.",
        )

    usuario = (
        bd.query(Usuario)
        .options(joinedload(Usuario.sucursal))
        .filter(Usuario.id == usuario_id)
        .first()
    )
    if usuario is None or not usuario.activo or not usuario.tiene_acceso:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo, sin acceso al sistema o inexistente.",
        )
    return usuario


def requerir_roles(*roles_permitidos: str) -> Callable[[Usuario], Usuario]:
    """Dependencia RBAC que restringe el endpoint a los roles indicados."""
    conjunto_roles = set(roles_permitidos)

    def validador(usuario_actual: Usuario = Depends(obtener_usuario_actual)) -> Usuario:
        if usuario_actual.rol not in conjunto_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos suficientes para realizar esta operación.",
            )
        return usuario_actual

    return validador
