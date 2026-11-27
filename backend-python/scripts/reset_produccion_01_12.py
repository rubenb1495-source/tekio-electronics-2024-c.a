#!/usr/bin/env python3
"""
Script seguro de Reinicio a Cero de Producción para Apertura 01/12/2026 — Tekio Electronics.

Uso:
    python scripts/reset_produccion_01_12.py --frase "REINICIAR TEKIO 01-12"
    python scripts/reset_produccion_01_12.py --database-url "postgresql://..." --frase "REINICIAR TEKIO 01-12"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.servicios.reset_apertura_service import (  # noqa: E402
    FRASE_CONFIRMACION_RESET,
    ejecutar_reset_apertura,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reinicio a Cero seguro de Producción para Apertura 01/12/2026 (Tekio Electronics)."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL") or os.getenv("URL_BASE_DATOS") or "",
        help="URL de conexión PostgreSQL/SQLite (default: POSTGRES_URL / DATABASE_URL).",
    )
    parser.add_argument(
        "--frase",
        required=True,
        help=f'Frase de confirmación exacta: "{FRASE_CONFIRMACION_RESET}"',
    )
    args = parser.parse_args()

    if args.frase.strip() != FRASE_CONFIRMACION_RESET:
        print(
            f'[ERROR] Frase de confirmación inválida. Debe ser exactamente: "{FRASE_CONFIRMACION_RESET}"',
            file=sys.stderr,
        )
        return 2

    db_url = args.database_url.strip() or f"sqlite:///{(ROOT_DIR / 'tekio_local.db').as_posix()}"
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    motor = create_engine(db_url, pool_pre_ping=True)
    Sesion = sessionmaker(autocommit=False, autoflush=False, bind=motor)
    with Sesion() as bd:
        resultado = ejecutar_reset_apertura(bd, ruta_backups=ROOT_DIR / "backups")

    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
