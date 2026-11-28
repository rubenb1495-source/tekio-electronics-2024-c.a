#!/usr/bin/env python3
"""
Respaldo de emergencia CLI para regenerar la clave del Administrador/Director
directamente en Neon PostgreSQL o SQLite.

Uso:
  python scripts/regenerar_clave_admin.py --usuario admin
  python scripts/regenerar_clave_admin.py --usuario admin --database-url "postgresql://..."
"""
from __future__ import annotations

import argparse
import os
import secrets
import string
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenera la clave de acceso de un administrador en BD.")
    parser.add_argument("--usuario", default="admin", help="Usuario, nombre o correo del administrador (default: admin)")
    parser.add_argument("--clave", default=None, help="Clave manual opcional (si se omite, genera 12 caracteres seguros)")
    parser.add_argument("--database-url", default=None, help="URL de conexión PostgreSQL/SQLite (sobrescribe DATABASE_URL)")
    args = parser.parse_args()

    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url

    from sqlalchemy import func, or_
    from app.base_datos import SesionLocal
    from app.modelos import Usuario
    from app.seguridad import generar_hash_clave

    bd = SesionLocal()
    try:
        ident = args.usuario.strip().lower()
        filtros = [
            func.lower(Usuario.nombre) == ident,
            func.lower(Usuario.correo) == ident,
        ]
        if hasattr(Usuario, "usuario"):
            filtros.append(func.lower(Usuario.usuario) == ident)
        if hasattr(Usuario, "username"):
            filtros.append(func.lower(Usuario.username) == ident)

        user = bd.query(Usuario).filter(or_(*filtros)).first()
        if user is None:
            print(f"[ERROR] No se encontró ningún usuario que coincida con '{args.usuario}'.")
            sys.exit(1)

        if args.clave and len(args.clave.strip()) >= 6:
            nueva = args.clave.strip()
        else:
            alfabeto = string.ascii_uppercase + string.digits
            sufijo = "".join(secrets.choice(alfabeto) for _ in range(6))
            nueva = f"Adm-{sufijo}!"

        user.clave_hash = generar_hash_clave(nueva)
        user.debe_cambiar_clave = True
        if hasattr(user, "cuenta_bloqueada"):
            user.cuenta_bloqueada = False
        if hasattr(user, "intentos_fallidos"):
            user.intentos_fallidos = 0
        if hasattr(user, "intentos_fallidos_login"):
            user.intentos_fallidos_login = 0
        if hasattr(user, "fecha_bloqueo"):
            user.fecha_bloqueo = None
        if hasattr(user, "bloqueado_hasta"):
            user.bloqueado_hasta = None
        if hasattr(user, "bloqueado_en"):
            user.bloqueado_en = None
        bd.commit()

        login_id = getattr(user, "usuario", None) or getattr(user, "username", None) or user.nombre
        print("=" * 64)
        print("  CLAVE DE EMERGENCIA REGENERADA CORRECTAMENTE")
        print("=" * 64)
        print(f"  Nombre:           {user.nombre}")
        print(f"  Usuario:          {login_id}")
        print(f"  Rol:              {user.rol}")
        print(f"  Clave temporal:   {nueva}")
        print("  Cuenta bloqueada: False (intentos reiniciados a 0)")
        print("  Cambio obligado:  True (debe cambiarla al iniciar sesión)")
        print("=" * 64)
    finally:
        bd.close()


if __name__ == "__main__":
    main()
