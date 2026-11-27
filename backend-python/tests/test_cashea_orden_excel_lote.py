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


def _construir_xlsx_cashea(filas: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Liquidacion Cashea"
    ws.append(["Order ID", "Monto Financiado", "Monto Pagado", "Comision", "IVA", "ISLR", "Referencia Bancaria"])
    for fila in filas:
        ws.append(fila)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def test_cashea_orden_obligatoria_filtro_xlsx_y_liquidacion_lote_atomica(
    cliente: TestClient,
) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]
    cab_as = ctx["headers_as"]
    hoy_str = obtener_fecha_hoy().isoformat()

    # Crear 2 equipos LISTO para probar validación y duplicado de cashea_numero_orden
    r_cat = cliente.post(
        "/api/catalogo",
        headers=cab_dir,
        json={
            "sku": "CASHEA-LOTE-LAP",
            "descripcion": "Laptop Lote Cashea",
            "tipo": "EQUIPO",
            "categoria": "Laptops",
            "precio_promo_usd": 400,
            "costo_referencia_usd": 220,
            "fecha_vigencia": hoy_str,
        },
    )
    assert r_cat.status_code == 201, r_cat.text
    art_id = r_cat.json()["id"]

    r_comp = cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "fecha": hoy_str,
            "monto_mercancia_usd": 440,
            "envio_usd": 0,
            "llega_preparada": True,
            "equipos": [
                {
                    "serial": "SN-CSH-LOT-1",
                    "modelo": "Laptop Lote Cashea",
                    "articulo_id": art_id,
                    "costo_compra_usd": 220,
                    "precio_promo_usd": 400,
                    "ubicacion_id": 2,
                },
                {
                    "serial": "SN-CSH-LOT-2",
                    "modelo": "Laptop Lote Cashea",
                    "articulo_id": art_id,
                    "costo_compra_usd": 220,
                    "precio_promo_usd": 400,
                    "ubicacion_id": 2,
                },
            ],
        },
    )
    assert r_comp.status_code == 201, r_comp.text
    eqs = cliente.get("/api/logistica/inventario/equipos?buscar=SN-CSH-LOT-", headers=cab_dir).json()
    eq1_id = next(e["id"] for e in eqs if e["serial"] == "SN-CSH-LOT-1")
    eq2_id = next(e["id"] for e in eqs if e["serial"] == "SN-CSH-LOT-2")

    insts = cliente.get("/api/finanzas/instrumentos", headers=cab_dir).json()
    inst_usd = next(i for i in insts if "efectivo" in i["nombre"].lower() and i["moneda"] == "USD")
    inst_cashea = next(i for i in insts if "cashea" in i["nombre"].lower())
    inst_banco = next(i for i in insts if "zelle" in i["nombre"].lower() or (i["moneda"] == "USD" and "cashea" not in i["nombre"].lower() and i["id"] != inst_usd["id"]))

    # Simular para calcular total regular exacto
    r_sim = cliente.post(
        "/api/ventas/simular",
        headers=cab_dir,
        json={
            "sucursal_id": 2,
            "items": [{"equipo_id": eq1_id, "cantidad": 1}],
            "pagos": [{"instrumento_id": inst_cashea["id"], "monto_moneda_origen": 300}],
        },
    )
    assert r_sim.status_code == 200, r_sim.text
    total_reg = r_sim.json()["total_regular_usd"]
    inicial = round(total_reg - 300.0, 2)

    # 1. Rechazo 422 si falta cashea_numero_orden en venta con Cashea
    r_sin_orden = cliente.post(
        "/api/ventas",
        headers=cab_as,
        json={
            "sucursal_id": 2,
            "cliente_id": ctx["cliente_id"],
            "asesor_id": ctx["asesora_id"],
            "fecha": hoy_str,
            "items": [{"equipo_id": eq1_id, "cantidad": 1}],
            "pagos": [
                {"instrumento_id": inst_usd["id"], "monto_moneda_origen": inicial},
                {"instrumento_id": inst_cashea["id"], "monto_moneda_origen": 300},
            ],
        },
    )
    assert r_sin_orden.status_code == 422, r_sin_orden.text
    assert "número de orden de cashea es obligatorio" in r_sin_orden.json()["detail"].lower()

    # 2. Emitir venta 1 con cashea_numero_orden válido (se normaliza sin espacios y mayúsculas)
    r_v1 = cliente.post(
        "/api/ventas",
        headers=cab_as,
        json={
            "sucursal_id": 2,
            "cliente_id": ctx["cliente_id"],
            "asesor_id": ctx["asesora_id"],
            "fecha": hoy_str,
            "cashea_numero_orden": "  csh-990011  ",
            "items": [{"equipo_id": eq1_id, "cantidad": 1}],
            "pagos": [
                {"instrumento_id": inst_usd["id"], "monto_moneda_origen": inicial},
                {"instrumento_id": inst_cashea["id"], "monto_moneda_origen": 300},
            ],
        },
    )
    assert r_v1.status_code == 201, r_v1.text
    v1 = r_v1.json()
    assert v1["cashea_numero_orden"] == "CSH-990011"

    # 3. Rechazo 409 si se intenta repetir el mismo cashea_numero_orden en otra venta activa
    r_dup = cliente.post(
        "/api/ventas",
        headers=cab_as,
        json={
            "sucursal_id": 2,
            "cliente_id": ctx["cliente_id"],
            "asesor_id": ctx["asesora_id"],
            "fecha": hoy_str,
            "cashea_numero_orden": "CSH-990011",
            "items": [{"equipo_id": eq2_id, "cantidad": 1}],
            "pagos": [
                {"instrumento_id": inst_usd["id"], "monto_moneda_origen": inicial},
                {"instrumento_id": inst_cashea["id"], "monto_moneda_origen": 300},
            ],
        },
    )
    assert r_dup.status_code == 409, r_dup.text
    assert v1["numero_venta"] in r_dup.json()["detail"]

    # 4. RBAC: ASESORA recibe 403 en todo el panel de conciliación Cashea
    assert cliente.get("/api/finanzas/cashea", headers=cab_as).status_code == 403
    assert cliente.get("/api/finanzas/cashea/exportar-xlsx", headers=cab_as).status_code == 403

    # 5. Filtro PENDIENTE vs CONCILIADO + Exportación Excel (.xlsx sin duplicados)
    r_pend = cliente.get("/api/finanzas/cashea?estado_conciliacion=PENDIENTE", headers=cab_dir)
    assert r_pend.status_code == 200, r_pend.text
    body_p = r_pend.json()
    assert body_p["conteo"]["pendientes"] == 1
    assert body_p["conteo"]["conciliados"] == 0
    assert len(body_p["items"]) == 1
    item_v1 = body_p["items"][0]
    assert item_v1["cashea_numero_orden"] == "CSH-990011"

    r_xlsx = cliente.get("/api/finanzas/cashea/exportar-xlsx?estado_conciliacion=PENDIENTE", headers=cab_dir)
    assert r_xlsx.status_code == 200, r_xlsx.text
    wb = load_workbook(io.BytesIO(r_xlsx.content))
    ws = wb.active
    notas_excel = [ws.cell(row=r, column=2).value for r in range(3, ws.max_row)]
    assert notas_excel == [v1["numero_venta"]]

    # 6. Carga de archivo .xlsx simulado con 2 órdenes: 1 PENDIENTE (CSH-990011) + 1 NO_ENCONTRADA (CSH-INEXISTENTE)
    # Simulamos que Cashea pagó $265.00 y descontó $35.00 (comisión 30 + IVA 4 + ISLR 1)
    xlsx_bytes = _construir_xlsx_cashea(
        [
            ["CSH-990011", 300.00, 265.00, 30.00, 4.00, 1.00, "REF-BNK-777"],
            ["CSH-INEXISTENTE", 150.00, 130.00, 20.00, 0.00, 0.00, "REF-BNK-777"],
        ]
    )
    r_prev = cliente.post(
        "/api/finanzas/cashea/importar-reporte/preview",
        headers=cab_dir,
        files={
            "archivo": (
                "liquidacion_cashea.xlsx",
                xlsx_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert r_prev.status_code == 200, r_prev.text
    prev = r_prev.json()
    assert prev["resumen"]["listas_para_conciliar"] == 1
    assert prev["resumen"]["no_encontradas"] == 1
    assert prev["resumen"]["total_a_cobrar_real_usd"] == 265.0
    assert prev["resumen"]["total_descuentos_reales_usd"] == 35.0
    fila_lista = next(f for f in prev["filas"] if f["estado_cruce"] == "LISTA_PARA_CONCILIAR")
    assert fila_lista["venta_id"] == v1["id"]
    diff_esperada = round(265.0 - item_v1["neto_esperado_cashea_usd"], 2)
    assert fila_lista["diferencia_usd"] == diff_esperada

    # 7. Confirmación atómica del lote: pasa a CONCILIADO, crea INGRESO en banco y asiento contable cuadrado
    r_conf = cliente.post(
        "/api/finanzas/cashea/importar-reporte/confirmar",
        headers=cab_dir,
        json={
            "nombre_archivo": "liquidacion_cashea.xlsx",
            "instrumento_destino_id": inst_banco["id"],
            "fecha_deposito": hoy_str,
            "referencia_bancaria": "REF-BNK-777",
            "ordenes": [
                {
                    "venta_id": v1["id"],
                    "cashea_numero_orden": "CSH-990011",
                    "monto_pagado_real_usd": 265.0,
                    "descuento_real_usd": 35.0,
                }
            ],
        },
    )
    assert r_conf.status_code == 200, r_conf.text
    conf = r_conf.json()
    assert conf["notas_conciliadas"] == 1
    assert conf["total_pagado_real_usd"] == 265.0
    assert conf["asiento_id"] > 0

    # Verificar que la nota ahora está en CONCILIADO y ya no en PENDIENTE
    r_post_p = cliente.get("/api/finanzas/cashea?estado_conciliacion=PENDIENTE", headers=cab_dir).json()
    r_post_c = cliente.get("/api/finanzas/cashea?estado_conciliacion=CONCILIADO", headers=cab_dir).json()
    assert r_post_p["total_notas"] == 0
    assert r_post_c["total_notas"] == 1
    assert r_post_c["items"][0]["cashea_monto_pagado_real_usd"] == 265.0
    assert r_post_c["items"][0]["cashea_descuento_real_usd"] == 35.0

    # Verificar que el asiento contable está cuadrado (auditoría de asientos sin descuadres)
    r_aud_as = cliente.get("/api/finanzas/contabilidad/auditoria-asientos", headers=cab_dir)
    assert r_aud_as.status_code == 200, r_aud_as.text
    assert r_aud_as.json()["asientos_descuadrados"] == 0

    # 8. Subir el mismo archivo una segunda vez -> clasifica CSH-990011 como YA_CONCILIADA sin duplicar ingresos
    r_prev2 = cliente.post(
        "/api/finanzas/cashea/importar-reporte/preview",
        headers=cab_dir,
        files={
            "archivo": (
                "liquidacion_cashea.xlsx",
                xlsx_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert r_prev2.status_code == 200, r_prev2.text
    prev2 = r_prev2.json()
    assert prev2["resumen"]["listas_para_conciliar"] == 0
    assert prev2["resumen"]["ya_conciliadas"] == 1
    assert prev2["resumen"]["no_encontradas"] == 1
