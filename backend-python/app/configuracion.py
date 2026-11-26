from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


DIRECTORIO_BASE = Path(__file__).resolve().parent.parent
RUTA_SQLITE_LOCAL = DIRECTORIO_BASE / "datos" / "tekio_desarrollo.db"


def normalizar_url_base_datos(url: str) -> str:
    """Convierte URLs de Vercel Postgres / Neon al formato SQLAlchemy + psycopg."""
    url_limpia = url.strip()
    if url_limpia.startswith("postgres://"):
        return url_limpia.replace("postgres://", "postgresql+psycopg://", 1)
    if url_limpia.startswith("postgresql://") and "+psycopg" not in url_limpia:
        return url_limpia.replace("postgresql://", "postgresql+psycopg://", 1)
    return url_limpia


class Configuracion(BaseSettings):
    """Configuración centralizada del backend Tekio Electronics (local y Vercel)."""

    model_config = SettingsConfigDict(
        env_file=(str(DIRECTORIO_BASE / ".env"), str(DIRECTORIO_BASE.parent / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    NOMBRE_APP: str = "Sistema Administrativo Tekio Electronics - API"
    ENTORNO: str = "desarrollo"

    # Base de datos (soporta Vercel Postgres / Neon / VPS)
    URL_BASE_DATOS: str = ""
    POSTGRES_URL: str = ""

    # Seguridad JWT (soporta JWT_SECRET y SECRETO_JWT)
    JWT_SECRET: str = ""
    SECRETO_JWT: str = "tekio-dev-secreto-cambiar-en-produccion-2026"
    ALGORITMO_JWT: str = "HS256"
    EXPIRACION_JWT_HORAS: int = 12

    # CORS (soporta CORS_ORIGINS y ORIGENES_CORS)
    CORS_ORIGINS: str = ""
    ORIGENES_CORS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Zona horaria oficial de Venezuela (UTC-4)
    ZONA_HORARIA: str = "America/Caracas"

    # URL pública del frontend para enlaces de acceso compartible
    FRONTEND_URL: str = "https://tekio-admin-two.vercel.app"

    @property
    def url_frontend_efectiva(self) -> str:
        return (self.FRONTEND_URL.strip() or "https://tekio-admin-two.vercel.app").rstrip("/")

    @property
    def es_vercel_serverless(self) -> bool:
        return os.getenv("VERCEL") == "1" or bool(os.getenv("VERCEL_ENV"))

    @property
    def url_sqlalchemy(self) -> str:
        url_remota = self.POSTGRES_URL or self.URL_BASE_DATOS or os.getenv("DATABASE_URL", "")
        if url_remota:
            return normalizar_url_base_datos(url_remota)
        RUTA_SQLITE_LOCAL.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{RUTA_SQLITE_LOCAL.as_posix()}"

    @property
    def secreto_jwt_efectivo(self) -> str:
        return self.JWT_SECRET.strip() or self.SECRETO_JWT.strip()

    @property
    def lista_origenes_cors(self) -> list[str]:
        crudo = self.CORS_ORIGINS.strip() or self.ORIGENES_CORS.strip()
        return [origen.strip().rstrip("/") for origen in crudo.split(",") if origen.strip()]


configuracion = Configuracion()
