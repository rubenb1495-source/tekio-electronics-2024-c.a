from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.empresa import (
    FECHA_CORTE_APERTURA as FECHA_APERTURA_OFICIAL,
    RAZON_SOCIAL,
    RIF,
    SEDES_OFICIALES,
    TELEFONO_ADMIN,
)
from app.modelos import Sucursal, Usuario
from app.modelos_finanzas import InstrumentoFinanciero
from app.semilla import ejecutar_semilla
from app.semilla_finanzas import ejecutar_semilla_finanzas
from app.servicios.contabilidad_service import asegurar_plan_cuentas

ZONA_CARACAS = ZoneInfo("America/Caracas")
FRASE_CONFIRMACION_RESET = "REINICIAR TEKIO 01-12"

# Tablas transaccionales que se limpian por completo (reiniciando secuencias a 1)
TABLAS_TRANSACCIONALES_RESET: tuple[str, ...] = (
    # Contabilidad y Auditoría
    "asientos_lineas",
    "asientos_contables",
    "auditoria_sistema",
    # Ventas, POS, Cotizaciones, Devoluciones, CxC y Lotes Cashea
    "ventas_detalle",
    "devoluciones_garantias",
    "notas_credito",
    "cuentas_por_cobrar",
    "cotizaciones_detalle",
    "cotizaciones",
    "ventas",
    "cashea_lotes_liquidacion",
    # Taller y Garantías
    "casos_repuestos_usados",
    "casos_presupuestos",
    "casos_postventa",
    "repuestos_solicitados",
    "preparaciones_componentes",
    "preparaciones",
    "recepciones_taller",
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
    # Terceros (clientes y proveedores de prueba)
    "terceros",
)


def _serializar(valor: Any) -> Any:
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, (bytes, bytearray)):
        return valor.hex()
    return valor


def generar_respaldo_pre_reset(bd: Session, ruta_directorio: Path | None = None) -> dict[str, Any]:
    """Genera un respaldo JSON completo de todas las tablas antes de ejecutar el reset."""
    ahora = datetime.now(ZONA_CARACAS)
    insp = inspect(bd.get_bind())
    tablas = sorted(insp.get_table_names())
    datos_tablas: dict[str, list[dict[str, Any]]] = {}
    conteo: dict[str, int] = {}

    for tabla in tablas:
        filas = bd.execute(text(f'SELECT * FROM "{tabla}"')).mappings().all()
        registros = [{k: _serializar(v) for k, v in dict(f).items()} for f in filas]
        datos_tablas[tabla] = registros
        conteo[tabla] = len(registros)

    payload = {
        "empresa": RAZON_SOCIAL,
        "rif": RIF,
        "fecha_respaldo_caracas": ahora.isoformat(),
        "fecha_apertura_objetivo": FECHA_APERTURA_OFICIAL,
        "total_tablas": len(tablas),
        "conteo_por_tabla": conteo,
        "tablas": datos_tablas,
    }

    nombre = f"pre_reset_tekio_01_12_{ahora.strftime('%Y%m%d_%H%M%S')}.json"
    destino_dir = ruta_directorio
    if destino_dir is None:
        try:
            candidato = Path(__file__).resolve().parents[2] / "backups"
            candidato.mkdir(parents=True, exist_ok=True)
            destino_dir = candidato
        except OSError:
            destino_dir = Path(tempfile.gettempdir()) / "tekio_backups"
            destino_dir.mkdir(parents=True, exist_ok=True)
    else:
        destino_dir.mkdir(parents=True, exist_ok=True)

    ruta_archivo = destino_dir / nombre
    ruta_archivo.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "archivo": str(ruta_archivo),
        "nombre_archivo": nombre,
        "total_tablas": len(tablas),
        "total_registros_respaldados": sum(conteo.values()),
    }


def ejecutar_reset_apertura(
    bd: Session,
    *,
    ruta_backups: Path | None = None,
) -> dict[str, Any]:
    """
    Ejecuta el Reinicio a Cero para Apertura 01/12/2026:
    1. Genera respaldo JSON automático obligatorio.
    2. Limpia todas las tablas transaccionales y reinicia secuencias/correlativos a 1.
    3. Conserva las 3 sedes oficiales con teléfonos exactos, RIF/empresa, plan de cuentas,
       estructura de instrumentos con saldo_inicial = 0.00 y usuarios activos (reseteando bloqueos).
    """
    respaldo = generar_respaldo_pre_reset(bd, ruta_directorio=ruta_backups)

    motor = bd.get_bind()
    es_pg = motor.dialect.name == "postgresql"
    existentes = set(inspect(motor).get_table_names())
    tablas_a_limpiar = [t for t in TABLAS_TRANSACCIONALES_RESET if t in existentes]

    if tablas_a_limpiar:
        if es_pg:
            lista_sql = ", ".join(f'"{t}"' for t in tablas_a_limpiar)
            bd.execute(text(f"TRUNCATE TABLE {lista_sql} RESTART IDENTITY CASCADE"))
        else:
            bd.execute(text("PRAGMA foreign_keys = OFF"))
            for t in tablas_a_limpiar:
                bd.execute(text(f'DELETE FROM "{t}"'))
            if "sqlite_sequence" in existentes:
                for t in tablas_a_limpiar:
                    bd.execute(
                        text("DELETE FROM sqlite_sequence WHERE name = :t"),
                        {"t": t},
                    )
            bd.execute(text("PRAGMA foreign_keys = ON"))

    # Reiniciar saldos iniciales de instrumentos a 0.00 sin borrar su estructura
    for inst in bd.query(InstrumentoFinanciero).all():
        inst.saldo_inicial = Decimal("0.00")

    # Conservar usuarios activos y desbloquear todos los accesos
    usuarios_conservados = 0
    for u in bd.query(Usuario).all():
        u.intentos_fallidos_login = 0
        u.cuenta_bloqueada = False
        if hasattr(u, "bloqueado_hasta"):
            u.bloqueado_hasta = None
        if hasattr(u, "bloqueado_en"):
            u.bloqueado_en = None
        if u.activo:
            usuarios_conservados += 1

    bd.flush()

    # Garantizar que las 3 sedes oficiales, plan de cuentas e instrumentos base estén intactos
    ejecutar_semilla(bd)
    ejecutar_semilla_finanzas(bd)
    asegurar_plan_cuentas(bd)
    bd.commit()

    sedes = [
        {"id": s.id, "nombre": s.nombre, "telefono": s.telefono, "tipo": s.tipo}
        for s in bd.query(Sucursal).filter(Sucursal.estado == "ACTIVA").order_by(Sucursal.id.asc()).all()
    ]
    return {
        "estado": "REINICIADO_APERTURA",
        "empresa": RAZON_SOCIAL,
        "rif": RIF,
        "telefono_administracion": TELEFONO_ADMIN,
        "fecha_corte_apertura": FECHA_APERTURA_OFICIAL,
        "respaldo_previo": respaldo,
        "tablas_limpiadas": len(tablas_a_limpiar),
        "sedes_conservadas": sedes,
        "usuarios_activos_conservados": usuarios_conservados,
        "instrumentos_en_cero": bd.query(InstrumentoFinanciero).count(),
        "correlativos_reiniciados": True,
        "sedes_oficiales_esperadas": len(SEDES_OFICIALES),
    }
