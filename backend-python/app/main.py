from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.base_datos import Base, SesionLocal, motor
from app.configuracion import configuracion
from app import modelos_finanzas as _modelos_finanzas  # noqa: F401
from app import modelos_logistica as _modelos_logistica  # noqa: F401
from app import modelos_operaciones as _modelos_operaciones  # noqa: F401
from app import modelos_taller as _modelos_taller  # noqa: F401
from app.rutas import autenticacion, catalogo, finanzas, logistica, operaciones, taller, tasas, usuarios, ventas
from app.semilla import ejecutar_semilla
from app.semilla_finanzas import ejecutar_semilla_finanzas


def asegurar_columnas_compatibles() -> None:
    """Agrega columnas nuevas de forma idempotente en PostgreSQL y SQLite sin perder datos."""
    inspector = inspect(motor)
    if inspector.has_table("ventas_detalle"):
        columnas = {col["name"] for col in inspector.get_columns("ventas_detalle")}
        if "descripcion_servicio" not in columnas:
            with motor.begin() as conexion:
                conexion.execute(
                    text(
                        "ALTER TABLE ventas_detalle "
                        "ADD COLUMN descripcion_servicio TEXT NOT NULL DEFAULT ''"
                    )
                )
    if inspector.has_table("terceros"):
        columnas_ter = {col["name"] for col in inspector.get_columns("terceros")}
        nuevas_terceros = [
            ("tipo_persona", "VARCHAR(20) NOT NULL DEFAULT 'NATURAL'"),
            ("tipo_documento", "VARCHAR(5) NOT NULL DEFAULT ''"),
            ("documento", "VARCHAR(40) NOT NULL DEFAULT ''"),
            ("direccion", "VARCHAR(255) NOT NULL DEFAULT ''"),
            ("saldo_favor_usd", "NUMERIC(14, 2) NOT NULL DEFAULT 0"),
        ]
        for nombre_col, ddl_col in nuevas_terceros:
            if nombre_col not in columnas_ter:
                with motor.begin() as conexion:
                    conexion.execute(
                        text(f"ALTER TABLE terceros ADD COLUMN {nombre_col} {ddl_col}")
                    )
    if inspector.has_table("ventas"):
        columnas_vta = {col["name"] for col in inspector.get_columns("ventas")}
        if "datos_entrega_json" not in columnas_vta:
            with motor.begin() as conexion:
                conexion.execute(
                    text(
                        "ALTER TABLE ventas "
                        "ADD COLUMN datos_entrega_json TEXT NOT NULL DEFAULT ''"
                    )
                )
    if inspector.has_table("usuarios"):
        columnas_usr = {col["name"] for col in inspector.get_columns("usuarios")}
        nuevas_usuarios = [
            ("telefono", "VARCHAR(40) NOT NULL DEFAULT ''"),
            ("modalidad", "VARCHAR(20) NOT NULL DEFAULT 'PRESENCIAL'"),
            ("cedula", "VARCHAR(40) NOT NULL DEFAULT ''"),
            ("tiene_acceso", "BOOLEAN NOT NULL DEFAULT TRUE"),
        ]
        for nombre_col, ddl_col in nuevas_usuarios:
            if nombre_col not in columnas_usr:
                with motor.begin() as conexion:
                    conexion.execute(
                        text(f"ALTER TABLE usuarios ADD COLUMN {nombre_col} {ddl_col}")
                    )
        if motor.dialect.name == "postgresql":
            with motor.begin() as conexion:
                conexion.execute(
                    text("ALTER TABLE usuarios ALTER COLUMN correo DROP NOT NULL")
                )
                conexion.execute(
                    text("ALTER TABLE usuarios ALTER COLUMN clave_hash DROP NOT NULL")
                )
    if inspector.has_table("tasas_diarias"):
        columnas_tasas = {col["name"] for col in inspector.get_columns("tasas_diarias")}
        tipo_ts = "TIMESTAMPTZ" if motor.dialect.name == "postgresql" else "DATETIME"
        nuevas_tasas = [
            ("recargo_confirmado_hoy", "BOOLEAN NOT NULL DEFAULT TRUE"),
            ("fuente", "VARCHAR(80) NOT NULL DEFAULT 'manual'"),
            ("ultima_sincronizacion", f"{tipo_ts} NULL"),
        ]
        for nombre_col, ddl_col in nuevas_tasas:
            if nombre_col not in columnas_tasas:
                with motor.begin() as conexion:
                    conexion.execute(
                        text(f"ALTER TABLE tasas_diarias ADD COLUMN {nombre_col} {ddl_col}")
                    )


@asynccontextmanager
async def ciclo_vida(_app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=motor)
    asegurar_columnas_compatibles()
    bd = SesionLocal()
    try:
        ejecutar_semilla(bd)
        ejecutar_semilla_finanzas(bd)
    finally:
        bd.close()
    yield


app = FastAPI(
    title=configuracion.NOMBRE_APP,
    version="1.0.0",
    lifespan=ciclo_vida,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=configuracion.lista_origenes_cors,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/salud", tags=["Sistema"])
def verificar_salud() -> dict[str, str]:
    return {"estado": "activo", "servicio": "Tekio Electronics API - Fase 1"}


app.include_router(autenticacion.enrutador)
app.include_router(usuarios.enrutador)
app.include_router(tasas.enrutador)
app.include_router(catalogo.enrutador)
app.include_router(logistica.enrutador)
app.include_router(taller.enrutador)
app.include_router(ventas.enrutador)
app.include_router(finanzas.enrutador)
app.include_router(operaciones.enrutador)
