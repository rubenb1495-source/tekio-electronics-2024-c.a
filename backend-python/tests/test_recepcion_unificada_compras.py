from __future__ import annotations

import io
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

_DIR_TESTS = str(Path(__file__).resolve().parent)
if _DIR_TESTS not in sys.path:
    sys.path.insert(0, _DIR_TESTS)

from app.rutas.tasas import obtener_fecha_hoy  # noqa: E402
from test_fase5 import (  # noqa: E402
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def _crear_xlsx_recepcion(filas: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(
        [
            "serial",
            "sku_o_modelo",
            "ram",
            "almacenamiento",
            "condicion_llegada",
            "incluye_cargador",
            "observaciones_llegada",
            "estado_inicial",
            "cantidad",
        ]
    )
    for f in filas:
        ws.append(f)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def test_recepcion_unificada_uno_a_uno_y_masiva_xlsx_con_prorrateo_y_duplicados(
    cliente: TestClient,
) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]
    cab_as = ctx["headers_as"]
    hoy_str = obtener_fecha_hoy().isoformat()

    # 1. Crear compra internacional de 4 equipos ($800 mercancía + $60 envío + $20 aduana = $80 gastos / 4 = $20 flete c/u)
    r_comp = cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "INTERNACIONAL",
            "tipo_compra": "INTERNACIONAL",
            "fecha": hoy_str,
            "monto_mercancia_usd": 800,
            "envio_usd": 60,
            "aduana_usd": 20,
            "llega_preparada": False,
            "equipos": [],
            "componentes": [],
        },
    )
    assert r_comp.status_code == 201, r_comp.text
    compra_id = r_comp.json()["id"]

    # 2. RBAC: ASESORA recibe 403 en plantilla y recepción
    assert cliente.get("/api/logistica/compras/plantilla-recepcion.xlsx", headers=cab_as).status_code == 403
    assert cliente.get("/api/logistica/compras/pendientes-recepcion", headers=cab_as).status_code == 403

    # 3. Plantilla oficial .xlsx válida
    r_tpl = cliente.get("/api/logistica/compras/plantilla-recepcion.xlsx", headers=cab_dir)
    assert r_tpl.status_code == 200, r_tpl.text
    wb_tpl = load_workbook(io.BytesIO(r_tpl.content))
    headers_tpl = [wb_tpl.active.cell(row=2, column=c).value for c in range(1, 10)]
    assert headers_tpl == [
        "serial",
        "sku_o_modelo",
        "ram",
        "almacenamiento",
        "condicion_llegada",
        "incluye_cargador",
        "observaciones_llegada",
        "estado_inicial",
        "cantidad",
    ]

    # 4. Modo 1 — Recepción parcial UNO A UNO (2 equipos con serial, condición y observaciones)
    r_rec1 = cliente.post(
        f"/api/logistica/compras/{compra_id}/recibir",
        headers=cab_dir,
        json={
            "sucursal_destino_id": 1,
            "equipos": [
                {
                    "serial": "SN-REC-INT-001",
                    "modelo": "Lenovo ThinkPad T14",
                    "ram": "16GB",
                    "almacenamiento": "512GB SSD",
                    "condicion_llegada": "EXCELENTE",
                    "incluye_cargador": True,
                    "observaciones_llegada": "Caja sellada",
                    "estado_inicial": "POR_PREPARAR",
                },
                {
                    "serial": "SN-REC-INT-002",
                    "modelo": "Lenovo ThinkPad T14",
                    "ram": "16GB",
                    "almacenamiento": "512GB SSD",
                    "condicion_llegada": "CON_DETALLES",
                    "incluye_cargador": False,
                    "observaciones_llegada": "Rayón en tapa, sin cargador",
                    "estado_inicial": "POR_PREPARAR",
                },
            ],
        },
    )
    assert r_rec1.status_code == 201, r_rec1.text
    body1 = r_rec1.json()
    assert body1["estado_compra"] == "RECIBIDA_PARCIAL"
    assert body1["equipos_recibidos"] == 2
    assert body1["equipos"][0]["estado"] == "POR_PREPARAR"
    # Costo prorrateado: $800 / 2 = $400 base + $80 / 2 = $40 flete/aduana = $440 total
    assert body1["equipos"][0]["costo_compra_usd"] == 400.0
    assert body1["equipos"][0]["costo_flete_usd"] == 40.0
    assert body1["equipos"][0]["costo_total_usd"] == 440.0

    # Verificar que en Taller (/api/taller/cola) aparecen condición y observaciones de llegada
    r_cola = cliente.get("/api/taller/cola", headers=cab_dir)
    assert r_cola.status_code == 200, r_cola.text
    eq2_taller = next(e for e in r_cola.json() if e["serial"] == "SN-REC-INT-002")
    assert eq2_taller["condicion_llegada"] == "CON_DETALLES"
    assert eq2_taller["incluye_cargador"] is False
    assert "Rayón en tapa" in eq2_taller["observaciones_llegada"]

    # 5. Modo 2 — Preview masivo .xlsx con 1 serial duplicado + 2 seriales nuevos válidos
    xlsx_dup = _crear_xlsx_recepcion(
        [
            ["SN-REC-INT-001", "Lenovo ThinkPad T14", "16GB", "512GB", "BUENO", "SI", "Duplicado", "POR_PREPARAR", 1],
            ["SN-REC-INT-003", "Lenovo ThinkPad T14", "16GB", "512GB", "BUENO", "SI", "OK", "POR_PREPARAR", 1],
            ["SN-REC-INT-004", "Lenovo ThinkPad T14", "16GB", "512GB", "EXCELENTE", "SI", "OK", "POR_PREPARAR", 1],
        ]
    )
    r_prev = cliente.post(
        f"/api/logistica/compras/{compra_id}/recibir/preview",
        headers=cab_dir,
        files={
            "archivo": (
                "recepcion_lote.xlsx",
                xlsx_dup,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert r_prev.status_code == 200, r_prev.text
    prev = r_prev.json()
    assert prev["validas"] == 2
    assert prev["con_errores"] == 1
    assert any("ya existe" in " ".join(f["errores"]).lower() for f in prev["filas"] if not f["valida"])

    # Intentar confirmar con serial duplicado -> 409 Conflict (rollback atómico)
    r_conf_dup = cliente.post(
        f"/api/logistica/compras/{compra_id}/recibir/confirmar",
        headers=cab_dir,
        json={
            "sucursal_destino_id": 1,
            "equipos": [
                {"serial": "SN-REC-INT-001", "modelo": "Lenovo ThinkPad T14"},
                {"serial": "SN-REC-INT-003", "modelo": "Lenovo ThinkPad T14"},
            ],
        },
    )
    assert r_conf_dup.status_code == 409, r_conf_dup.text

    # 6. Confirmación atómica con los 2 equipos restantes válidos -> cierra compra en RECIBIDA
    r_conf_ok = cliente.post(
        f"/api/logistica/compras/{compra_id}/recibir/confirmar",
        headers=cab_dir,
        json={
            "sucursal_destino_id": 1,
            "cerrar_compra": True,
            "equipos": [
                {
                    "serial": "SN-REC-INT-003",
                    "modelo": "Lenovo ThinkPad T14",
                    "ram": "16GB",
                    "almacenamiento": "512GB",
                    "condicion_llegada": "BUENO",
                    "incluye_cargador": True,
                    "observaciones_llegada": "OK masivo",
                    "estado_inicial": "POR_PREPARAR",
                },
                {
                    "serial": "SN-REC-INT-004",
                    "modelo": "Lenovo ThinkPad T14",
                    "ram": "16GB",
                    "almacenamiento": "512GB",
                    "condicion_llegada": "EXCELENTE",
                    "incluye_cargador": True,
                    "observaciones_llegada": "OK masivo",
                    "estado_inicial": "POR_PREPARAR",
                },
            ],
        },
    )
    assert r_conf_ok.status_code == 201, r_conf_ok.text
    body2 = r_conf_ok.json()
    assert body2["estado_compra"] == "RECIBIDA"
    assert body2["total_equipos_compra"] == 4
    assert body2["asiento_id"] is not None

    # Verificar auditoría contable cuadrada (0 asientos descuadrados)
    r_aud = cliente.get("/api/finanzas/contabilidad/auditoria-asientos", headers=cab_dir)
    assert r_aud.status_code == 200
    assert r_aud.json()["asientos_descuadrados"] == 0
