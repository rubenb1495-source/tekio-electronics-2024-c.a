from __future__ import annotations

from collections.abc import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.configuracion import configuracion


es_sqlite = configuracion.url_sqlalchemy.startswith("sqlite")

if es_sqlite:
    motor = create_engine(
        configuracion.url_sqlalchemy,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

    @event.listens_for(motor, "connect")
    def activar_claves_foraneas_sqlite(conexion_dbapi, _registro_conexion) -> None:
        cursor = conexion_dbapi.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
elif configuracion.es_vercel_serverless:
    # En Vercel Serverless usar NullPool evita agotar conexiones en PostgreSQL/Neon
    motor = create_engine(
        configuracion.url_sqlalchemy,
        poolclass=NullPool,
    )
else:
    motor = create_engine(
        configuracion.url_sqlalchemy,
        pool_pre_ping=True,
    )


SesionLocal = sessionmaker(autocommit=False, autoflush=False, bind=motor)


class Base(DeclarativeBase):
    """Clase base para todos los modelos ORM."""


def obtener_bd() -> Generator[Session, None, None]:
    """Dependencia FastAPI que provee una sesión de base de datos por solicitud."""
    bd = SesionLocal()
    try:
        yield bd
    finally:
        bd.close()
