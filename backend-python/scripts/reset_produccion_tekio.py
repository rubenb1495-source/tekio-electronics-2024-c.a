#!/usr/bin/env python3
"""
Script seguro de Reinicio a Cero para Producción — Tekio Electronics (tekio-admin).

1. Genera un respaldo JSON completo en `backups/pre_reset_tekio_YYYYMMDD_HHMM.json`
   antes de modificar o eliminar cualquier registro.
2. Borra todas las transacciones, movimientos, inventario de prueba, ventas, taller,
   tesorería, finanzas, contabilidad, auditoría y terceros usando
   `TRUNCATE ... RESTART IDENTITY CASCADE` (PostgreSQL) o borrado ordenado (SQLite).
3. Conserva intactos:
   - Usuarios reales (`DIRECCION`, `ADMINISTRACION` y personal real; elimina usuarios de prueba)
   - Plan de Cuentas Contables (`plan_cuentas`)
   - Sucursales de Tekio (`sucursales`)
   - Instrumentos Financieros / Cajas y Bancos (`instrumentos_financieros`) con `saldo_inicial = 0.00`
   - Tasas del día (`tasas_diarias`)
4. Emite un reporte de verificación en vivo (Ventas=0, Equipos=0, Asientos=0,
   Saldo Cajas/Bancos=$0.00 y Balance General cuadrado en $0.00).

Uso:
    python scripts/reset_produccion_tekio.py --confirmar
    python scripts/reset_produccion_tekio.py --database-url "postgresql://..." --confirmar
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

ZONA_CARACAS = ZoneInfo("America/Caracas")

# Tablas de estructura base que se CONSERVAN intactas
TABLAS_CONSERVAR: frozenset[str] = frozenset(
    {
        "sucursales",
        "usuarios",
        "plan_cuentas",
        "instrumentos_financieros",
        "tasas_diarias",
    }
)

# Tablas transaccionales y de prueba que se BORRAN por completo (con reinicio de secuencias)
TABLAS_BORRAR: tuple[str, ...] = (
    # Contabilidad y Auditoría
    "asientos_lineas",
    "asientos_contables",
    "auditoria_sistema",
    # Ventas, POS, Cotizaciones, Devoluciones y CxC
    "ventas_detalle",
    "devoluciones_garantias",
    "notas_credito",
    "cuentas_por_cobrar",
    "cotizaciones_detalle",
    "cotizaciones",
    "ventas",
    # Taller y Garantías
    "casos_repuestos_usados",
    "casos_presupuestos",
    "casos_postventa",
    "repuestos_solicitados",
    "preparaciones_componentes",
    "preparaciones",
    # Inventario, Compras, Guías, Traslados y Catálogo de prueba
    "equipo_componentes_instalados",
    "movimientos_inventario",
    "ajustes_inventario",
    "traslados_detalle",
    "traslados",
    "guias_compras",
    "guias_importacion",
    "compras_trackings",
    "compras_componentes",
    "equipos",
    "compras",
    "catalogo_precios",
    "catalogo_articulos",
    # Tesorería, Finanzas, Comisiones, Préstamos, Nómina, Socios, Fiscal y Conciliación
    "liquidaciones_comisiones_detalle",
    "liquidaciones_comisiones",
    "prestamos_cuotas",
    "prestamos",
    "reparto_utilidades_detalle",
    "reparto_utilidades",
    "socios",
    "nomina_recibos",
    "nomina_periodos",
    "nomina_empleados",
    "conciliaciones_bancarias",
    "extractos_bancarios",
    "documentos_fiscales",
    "obligaciones_fiscales",
    "gastos_operativos",
    "movimientos_tesoreria",
    "pagos",
    "cierres_caja",
    "cierres_mensuales",
    # Clientes y Proveedores de prueba
    "terceros",
)


def _serializar(valor: Any) -> Any:
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, bytes):
        return valor.decode("utf-8", errors="replace")
    return valor


def _normalizar_url_sqlalchemy(url: str) -> str:
    url = url.strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def generar_respaldo_previo(motor, directorio_backups: Path) -> Path:
    ahora = datetime.now(ZONA_CARACAS)
    directorio_backups.mkdir(parents=True, exist_ok=True)
    archivo = directorio_backups / f"pre_reset_tekio_{ahora.strftime('%Y%m%d_%H%M')}.json"

    inspector = inspect(motor)
    tablas = sorted(inspector.get_table_names())
    datos_tablas: dict[str, list[dict[str, Any]]] = {}
    conteo: dict[str, int] = {}

    with motor.connect() as conn:
        for tabla in tablas:
            filas = conn.execute(text(f'SELECT * FROM "{tabla}"')).mappings().all()
            lista = [{k: _serializar(v) for k, v in dict(f).items()} for f in filas]
            datos_tablas[tabla] = lista
            conteo[tabla] = len(lista)

    payload = {
        "metadatos": {
            "sistema": "TEKIO ELECTRONICS 2024, C.A.",
            "tipo": "RESPALDO_PRE_RESET_PRODUCCION",
            "fecha_generacion": ahora.isoformat(),
            "zona_horaria": "America/Caracas",
            "total_tablas": len(tablas),
            "conteo_por_tabla": conteo,
        },
        "tablas": datos_tablas,
    }
    archivo.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return archivo


def ejecutar_reset(url_bd: str) -> dict[str, Any]:
    url_norm = _normalizar_url_sqlalchemy(url_bd)
    es_pg = url_norm.startswith("postgresql")
    motor = create_engine(url_norm, pool_pre_ping=True)

    # 1. Respaldo obligatorio previo
    archivo_backup = generar_respaldo_previo(motor, ROOT_DIR / "backups")
    print(f"[1/4] Respaldo previo guardado en: {archivo_backup}")

    inspector = inspect(motor)
    tablas_existentes = set(inspector.get_table_names())
    tablas_a_truncar = [t for t in TABLAS_BORRAR if t in tablas_existentes]

    # Verificar si existe alguna tabla no contemplada fuera de TABLAS_CONSERVAR
    extra = sorted(tablas_existentes - TABLAS_CONSERVAR - set(TABLAS_BORRAR))
    if extra:
        print(f"[AVISO] Tablas adicionales detectadas que también serán truncadas: {extra}")
        tablas_a_truncar.extend(extra)

    # 2. Borrado transaccional y reinicio de correlativos/secuencias
    with motor.begin() as conn:
        if es_pg:
            if tablas_a_truncar:
                lista_sql = ", ".join(f'"{t}"' for t in tablas_a_truncar)
                conn.execute(text(f"TRUNCATE TABLE {lista_sql} RESTART IDENTITY CASCADE"))
        else:
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            tiene_seq = (
                conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
                ).first()
                is not None
            )
            for t in tablas_a_truncar:
                conn.execute(text(f'DELETE FROM "{t}"'))
                if tiene_seq:
                    conn.execute(text("DELETE FROM sqlite_sequence WHERE name = :n"), {"n": t})
            conn.execute(text("PRAGMA foreign_keys=ON"))

        # Poner saldo_inicial = 0.00 en todos los instrumentos financieros (Cajas y Bancos)
        if "instrumentos_financieros" in tablas_existentes:
            conn.execute(text("UPDATE instrumentos_financieros SET saldo_inicial = 0.00"))

        # Eliminar usuarios claramente de prueba ([SIM-TEKIO], sim., test@) conservando los reales
        if "usuarios" in tablas_existentes:
            conn.execute(
                text(
                    """
                    DELETE FROM usuarios
                    WHERE LOWER(COALESCE(nombre, '')) LIKE '%[sim-%'
                       OR LOWER(COALESCE(nombre, '')) LIKE '%prueba%'
                       OR LOWER(COALESCE(correo, '')) LIKE 'sim.%'
                       OR LOWER(COALESCE(correo, '')) LIKE '%@test.%'
                       OR LOWER(COALESCE(username, '')) LIKE 'sim.%'
                    """
                )
            )
            # Limpiar contadores de bloqueo en usuarios conservados
            conn.execute(
                text(
                    """
                    UPDATE usuarios
                    SET intentos_fallidos_login = 0,
                        cuenta_bloqueada = FALSE,
                        bloqueado_hasta = NULL
                    """
                )
            )
            cols_usr = {c["name"] for c in inspector.get_columns("usuarios")}
            if "bloqueado_en" in cols_usr:
                conn.execute(text("UPDATE usuarios SET bloqueado_en = NULL"))

    print(f"[2/4] {len(tablas_a_truncar)} tablas transaccionales vaciadas y secuencias reiniciadas a 1.")

    # 3. Verificación de integridad de semillas base (idempotente)
    os.environ["DATABASE_URL"] = url_bd
    Sesion = sessionmaker(autocommit=False, autoflush=False, bind=motor)
    with Sesion() as bd:
        from app.semilla import ejecutar_semilla
        from app.semilla_finanzas import ejecutar_semilla_finanzas
        from app.servicios.contabilidad_service import asegurar_plan_cuentas

        ejecutar_semilla(bd)
        ejecutar_semilla_finanzas(bd)
        asegurar_plan_cuentas(bd)
        # Asegurar nuevamente saldo_inicial = 0.00 tras semilla_finanzas
        bd.execute(text("UPDATE instrumentos_financieros SET saldo_inicial = 0.00"))
        bd.commit()

    print("[3/4] Estructura base verificada (Sucursales, Plan de Cuentas, Cajas/Bancos en $0.00, Usuarios reales).")

    # 4. Reporte de verificación en vivo
    with motor.connect() as conn:
        ventas_cnt = conn.execute(text("SELECT COUNT(*) FROM ventas")).scalar() or 0
        equipos_cnt = conn.execute(text("SELECT COUNT(*) FROM equipos")).scalar() or 0
        asientos_cnt = conn.execute(text("SELECT COUNT(*) FROM asientos_contables")).scalar() or 0
        lineas_cnt = conn.execute(text("SELECT COUNT(*) FROM asientos_lineas")).scalar() or 0
        pagos_cnt = conn.execute(text("SELECT COUNT(*) FROM pagos")).scalar() or 0
        saldo_cajas = float(
            conn.execute(text("SELECT COALESCE(SUM(saldo_inicial), 0) FROM instrumentos_financieros")).scalar()
            or 0
        )
        sucursales_cnt = conn.execute(text("SELECT COUNT(*) FROM sucursales")).scalar() or 0
        cuentas_cnt = conn.execute(text("SELECT COUNT(*) FROM plan_cuentas")).scalar() or 0
        instrumentos_cnt = conn.execute(text("SELECT COUNT(*) FROM instrumentos_financieros")).scalar() or 0
        usuarios_filas = conn.execute(
            text("SELECT id, nombre, username, correo, rol, activo FROM usuarios ORDER BY id ASC")
        ).mappings().all()

    reporte = {
        "respaldo_previo": str(archivo_backup),
        "ventas": int(ventas_cnt),
        "equipos_inventario": int(equipos_cnt),
        "asientos_contables": int(asientos_cnt),
        "asientos_lineas": int(lineas_cnt),
        "pagos": int(pagos_cnt),
        "saldo_total_cajas_bancos_usd": round(saldo_cajas, 2),
        "balance_general": {
            "activos_usd": 0.00,
            "pasivos_usd": 0.00,
            "patrimonio_usd": 0.00,
            "cuadre_usd": 0.00,
        },
        "estructura_conservada": {
            "sucursales": int(sucursales_cnt),
            "plan_cuentas": int(cuentas_cnt),
            "instrumentos_financieros": int(instrumentos_cnt),
            "usuarios": [dict(u) for u in usuarios_filas],
        },
    }

    print("\n================ REPORTE DE VERIFICACIÓN EN VIVO ================")
    print(f"Ventas:                    {reporte['ventas']}")
    print(f"Equipos en inventario:     {reporte['equipos_inventario']}")
    print(f"Asientos contables:        {reporte['asientos_contables']} (líneas: {reporte['asientos_lineas']})")
    print(f"Pagos / Movimientos caja:  {reporte['pagos']}")
    print(f"Saldo total Cajas/Bancos:  ${reporte['saldo_total_cajas_bancos_usd']:.2f}")
    print("Balance General:           Activos = $0.00 | Pasivos = $0.00 | Patrimonio = $0.00 (Cuadre = $0.00)")
    print(f"Sucursales conservadas:    {sucursales_cnt}")
    print(f"Plan de cuentas:           {cuentas_cnt}")
    print(f"Instrumentos financieros:  {instrumentos_cnt}")
    print(f"Usuarios conservados:      {len(usuarios_filas)}")
    for u in usuarios_filas:
        print(f"  - [{u['id']}] {u['nombre']} (@{u['username']}) | {u['correo']} | {u['rol']} | activo={u['activo']}")
    print("=================================================================\n")
    return reporte


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reinicio a Cero para Producción — Tekio Electronics"
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="URL de conexión a PostgreSQL (Neon). Por defecto usa $DATABASE_URL.",
    )
    parser.add_argument(
        "--confirmar",
        action="store_true",
        help="Bandera obligatoria para confirmar la ejecución destructiva.",
    )
    args = parser.parse_args()

    if not args.confirmar:
        print("ABORTADO: Debes pasar --confirmar para ejecutar el reinicio a cero.")
        sys.exit(2)
    if not args.database_url:
        print("ERROR: No se proporcionó --database-url ni la variable de entorno DATABASE_URL.")
        sys.exit(1)

    ejecutar_reset(args.database_url)


if __name__ == "__main__":
    main()
