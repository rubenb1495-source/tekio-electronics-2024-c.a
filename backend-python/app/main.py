from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text

from app.base_datos import Base, SesionLocal, motor
from app.configuracion import configuracion
from app.core.validacion import formatear_error_validacion_es
from app import modelos_admin_finanzas as _modelos_admin_finanzas  # noqa: F401
from app import modelos_contabilidad as _modelos_contabilidad  # noqa: F401
from app import modelos_finanzas as _modelos_finanzas  # noqa: F401
from app import modelos_logistica as _modelos_logistica  # noqa: F401
from app import modelos_operaciones as _modelos_operaciones  # noqa: F401
from app import modelos_taller as _modelos_taller  # noqa: F401
from app.rutas import admin_finanzas, autenticacion, catalogo, contabilidad_prestamos, direccion_tesoreria, finanzas, liquidaciones_caja, logistica, operaciones, respaldo, taller, tasas, usuarios, ventas
from app.semilla import ejecutar_semilla
from app.semilla_finanzas import ejecutar_semilla_finanzas
from app.servicios.contabilidad_service import asegurar_plan_cuentas


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
        nuevas_ventas = [
            ("datos_entrega_json", "TEXT NOT NULL DEFAULT ''"),
            ("precio_regular_bs", "NUMERIC(16, 2) NOT NULL DEFAULT 0"),
            ("monto_financiado_cashea_usd", "NUMERIC(14, 2) NOT NULL DEFAULT 0"),
            ("comision_cashea_venta_total_usd", "NUMERIC(14, 2) NOT NULL DEFAULT 0"),
            ("comision_cashea_financiado_usd", "NUMERIC(14, 2) NOT NULL DEFAULT 0"),
            ("iva_cashea_usd", "NUMERIC(14, 2) NOT NULL DEFAULT 0"),
            ("islr_cashea_usd", "NUMERIC(14, 2) NOT NULL DEFAULT 0"),
            ("total_deducciones_cashea_usd", "NUMERIC(14, 2) NOT NULL DEFAULT 0"),
            ("neto_esperado_cashea_usd", "NUMERIC(14, 2) NOT NULL DEFAULT 0"),
        ]
        for nombre_col, ddl_col in nuevas_ventas:
            if nombre_col not in columnas_vta:
                with motor.begin() as conexion:
                    conexion.execute(
                        text(f"ALTER TABLE ventas ADD COLUMN {nombre_col} {ddl_col}")
                    )
    if inspector.has_table("usuarios"):
        columnas_usr = {col["name"] for col in inspector.get_columns("usuarios")}
        tipo_ts_usr = "TIMESTAMPTZ" if motor.dialect.name == "postgresql" else "DATETIME"
        nuevas_usuarios = [
            ("username", "VARCHAR(80) NULL"),
            ("telefono", "VARCHAR(40) NOT NULL DEFAULT ''"),
            ("modalidad", "VARCHAR(20) NOT NULL DEFAULT 'PRESENCIAL'"),
            ("cedula", "VARCHAR(40) NOT NULL DEFAULT ''"),
            ("tiene_acceso", "BOOLEAN NOT NULL DEFAULT TRUE"),
            ("intentos_fallidos_login", "INTEGER NOT NULL DEFAULT 0"),
            ("bloqueado_hasta", f"{tipo_ts_usr} NULL"),
            ("bloqueado_en", f"{tipo_ts_usr} NULL"),
            ("cuenta_bloqueada", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("debe_cambiar_clave", "BOOLEAN NOT NULL DEFAULT FALSE"),
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
    if inspector.has_table("catalogo_articulos"):
        columnas_cat = {col["name"] for col in inspector.get_columns("catalogo_articulos")}
        if "stock_minimo" not in columnas_cat:
            with motor.begin() as conexion:
                conexion.execute(
                    text("ALTER TABLE catalogo_articulos ADD COLUMN stock_minimo INTEGER NOT NULL DEFAULT 2")
                )
    if inspector.has_table("cierres_caja"):
        columnas_cc = {col["name"] for col in inspector.get_columns("cierres_caja")}
        nuevas_cc = [
            ("desglose_asesores_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("resumen_operativo_json", "TEXT NOT NULL DEFAULT '{}'"),
        ]
        for nombre_col, ddl_col in nuevas_cc:
            if nombre_col not in columnas_cc:
                with motor.begin() as conexion:
                    conexion.execute(
                        text(f"ALTER TABLE cierres_caja ADD COLUMN {nombre_col} {ddl_col}")
                    )
    if inspector.has_table("compras"):
        columnas_comp = {col["name"] for col in inspector.get_columns("compras")}
        nuevas_comp = [
            ("tipo_compra", "VARCHAR(20) NOT NULL DEFAULT 'NACIONAL'"),
            ("moneda", "VARCHAR(10) NOT NULL DEFAULT 'USD'"),
            ("numero_guia", "VARCHAR(100) NOT NULL DEFAULT ''"),
            ("aduana_usd", "NUMERIC(14, 2) NOT NULL DEFAULT 0"),
            ("fecha_vencimiento", "DATE NULL"),
            ("saldo_pendiente_usd", "NUMERIC(14, 2) NOT NULL DEFAULT 0"),
        ]
        for nombre_col, ddl_col in nuevas_comp:
            if nombre_col not in columnas_comp:
                with motor.begin() as conexion:
                    conexion.execute(
                        text(f"ALTER TABLE compras ADD COLUMN {nombre_col} {ddl_col}")
                    )
    if inspector.has_table("equipos"):
        columnas_eq = {col["name"] for col in inspector.get_columns("equipos")}
        nuevas_eq = [
            ("es_consignacion", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("proveedor_consignacion_id", "INTEGER NULL"),
        ]
        for nombre_col, ddl_col in nuevas_eq:
            if nombre_col not in columnas_eq:
                with motor.begin() as conexion:
                    conexion.execute(
                        text(f"ALTER TABLE equipos ADD COLUMN {nombre_col} {ddl_col}")
                    )
    if inspector.has_table("liquidaciones_comisiones"):
        columnas_liq = {col["name"] for col in inspector.get_columns("liquidaciones_comisiones")}
        tipo_ts = "TIMESTAMPTZ" if motor.dialect.name == "postgresql" else "DATETIME"
        nuevas_liq = [
            ("estado", "VARCHAR(20) NOT NULL DEFAULT 'ACTIVA'"),
            ("anulada_por_id", "INTEGER NULL"),
            ("fecha_anulacion", f"{tipo_ts} NULL"),
            ("motivo_anulacion", "TEXT NOT NULL DEFAULT ''"),
            ("detalle_anulado_json", "TEXT NOT NULL DEFAULT '[]'"),
        ]
        for nombre_col, ddl_col in nuevas_liq:
            if nombre_col not in columnas_liq:
                with motor.begin() as conexion:
                    conexion.execute(
                        text(f"ALTER TABLE liquidaciones_comisiones ADD COLUMN {nombre_col} {ddl_col}")
                    )
    if inspector.has_table("casos_postventa"):
        columnas_cp = {col["name"] for col in inspector.get_columns("casos_postventa")}
        nuevas_cp = [
            ("numero_nota_entrega", "VARCHAR(40) NOT NULL DEFAULT ''"),
            ("venta_id", "INTEGER NULL"),
            ("ingresa_apagado", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("recibido_por_id", "INTEGER NULL"),
            ("cliente_nombre_manual", "VARCHAR(160) NOT NULL DEFAULT ''"),
            ("cliente_telefono_manual", "VARCHAR(40) NOT NULL DEFAULT ''"),
        ]
        for nombre_col, ddl_col in nuevas_cp:
            if nombre_col not in columnas_cp:
                with motor.begin() as conexion:
                    conexion.execute(
                        text(f"ALTER TABLE casos_postventa ADD COLUMN {nombre_col} {ddl_col}")
                    )
    if inspector.has_table("nomina_empleados"):
        columnas_ne = {col["name"] for col in inspector.get_columns("nomina_empleados")}
        if "categoria_laboral" not in columnas_ne:
            with motor.begin() as conexion:
                conexion.execute(
                    text("ALTER TABLE nomina_empleados ADD COLUMN categoria_laboral VARCHAR(40) NOT NULL DEFAULT 'ASESOR'")
                )


@asynccontextmanager
async def ciclo_vida(_app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=motor)
    asegurar_columnas_compatibles()
    bd = SesionLocal()
    try:
        ejecutar_semilla(bd)
        ejecutar_semilla_finanzas(bd)
        asegurar_plan_cuentas(bd)
        # Completar username automático en minúsculas para usuarios existentes que aún no lo tengan
        from app.modelos import Usuario as _Usuario
        from app.rutas.usuarios import generar_username_unico

        sin_user = (
            bd.query(_Usuario)
            .filter(
                _Usuario.tiene_acceso.is_(True),
                (_Usuario.username.is_(None)) | (_Usuario.username == ""),
            )
            .all()
        )
        for u in sin_user:
            u.username = generar_username_unico(
                bd, deseado=None, correo=u.correo, nombre=u.nombre, excluir_id=u.id
            )
            bd.flush()
        bd.commit()
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


@app.exception_handler(RequestValidationError)
async def manejar_error_validacion_422(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    resumen, detalles = formatear_error_validacion_es(list(exc.errors()))
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": resumen, "errores": detalles},
    )


@app.get("/api/salud", tags=["Sistema"])
def verificar_salud() -> dict[str, str]:
    return {"estado": "activo", "servicio": "Tekio Electronics API - Fase 1"}


app.include_router(autenticacion.enrutador)
app.include_router(usuarios.enrutador)
app.include_router(tasas.enrutador)
app.include_router(catalogo.enrutador)
app.include_router(logistica.enrutador)
app.include_router(logistica.enrutador_inventario)
app.include_router(taller.enrutador)
app.include_router(ventas.enrutador)
app.include_router(finanzas.enrutador)
app.include_router(liquidaciones_caja.enrutador)
app.include_router(operaciones.enrutador)
app.include_router(direccion_tesoreria.enrutador)
app.include_router(admin_finanzas.enrutador)
app.include_router(contabilidad_prestamos.enrutador)
app.include_router(respaldo.enrutador)
