from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

_DIR_TESTS = str(Path(__file__).resolve().parent)
if _DIR_TESTS not in sys.path:
    sys.path.insert(0, _DIR_TESTS)

from app.rutas.tasas import obtener_fecha_hoy  # noqa: E402
from test_fase5 import (  # noqa: E402
    _login,
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def _instrumento_divisas(cliente: TestClient, headers: dict[str, str]) -> int:
    resp = cliente.get("/api/finanzas/instrumentos", headers=headers)
    assert resp.status_code == 200, resp.text
    for inst in resp.json():
        if inst["moneda"] == "USD" and "efectivo" in inst["nombre"].lower():
            return int(inst["id"])
    return int(resp.json()[0]["id"])


def test_ciclo_completo_compra_internacional_primer_costo_preparacion_costo_final_y_trazabilidad(
    cliente: TestClient,
) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]
    hoy_str = obtener_fecha_hoy().isoformat()
    inst_usd = _instrumento_divisas(cliente, cab_dir)

    # Crear técnico para probar RBAC en trazabilidad
    r_tec = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": "Andres Tecnico",
            "username": "andres.tec",
            "correo": "andres.tec@tekio.com",
            "clave": "Password123!",
            "rol": "TECNICO",
            "sucursal_id": 1,
        },
    )
    assert r_tec.status_code == 201, r_tec.text
    cab_tec = _login(cliente, "andres.tec", "Password123!")

    # Crear 2 componentes en catálogo: SSD ($35) y Batería ($25) + stock en Bodega (sucursal 1)
    r_ssd = cliente.post(
        "/api/catalogo",
        headers=cab_dir,
        json={
            "sku": "SSD-NVME-512-E2E",
            "descripcion": "SSD NVMe 512GB",
            "tipo": "COMPONENTE",
            "categoria": "SSD",
            "precio_promo_usd": 60.0,
            "costo_estandar_usd": 35.0,
        },
    )
    assert r_ssd.status_code == 201, r_ssd.text
    ssd_id = r_ssd.json()["id"]

    r_bat = cliente.post(
        "/api/catalogo",
        headers=cab_dir,
        json={
            "sku": "BAT-T14-E2E",
            "descripcion": "Batería Interna ThinkPad T14",
            "tipo": "COMPONENTE",
            "categoria": "Baterias",
            "precio_promo_usd": 50.0,
            "costo_estandar_usd": 25.0,
        },
    )
    assert r_bat.status_code == 201, r_bat.text
    bat_id = r_bat.json()["id"]

    # Ingresar stock de componentes en Bodega
    r_stock = cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "tipo_compra": "NACIONAL",
            "fecha": hoy_str,
            "componentes": [
                {"articulo_id": ssd_id, "cantidad": 2, "costo_unitario_usd": 35.0, "ubicacion_id": 1},
                {"articulo_id": bat_id, "cantidad": 2, "costo_unitario_usd": 25.0, "ubicacion_id": 1},
            ],
        },
    )
    assert r_stock.status_code == 201, r_stock.text

    # 1. Compra Internacional de 3 equipos sin seriales: $900 compra + $60 taxes + $30 Miami = $990 Subtotal Miami
    r_comp = cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "INTERNACIONAL",
            "tipo_compra": "INTERNACIONAL",
            "fecha": hoy_str,
            "factura_orden": "USA-LOT-2026-01",
            "descripcion_lote": "Lote 3 Lenovo ThinkPad T14 Gen 2 Grade A",
            "cantidad_esperada": 3,
            "monto_mercancia_usd": 900.0,
            "taxes_usd": 60.0,
            "envio_miami_usd": 30.0,
            "equipos": [],
            "componentes": [],
        },
    )
    assert r_comp.status_code == 201, r_comp.text
    comp = r_comp.json()
    assert comp["estado"] == "EN_TRANSITO"
    assert comp["subtotal_miami_usd"] == 990.0
    assert comp["cantidad_esperada"] == 3
    compra_id = comp["id"]

    # 2. Recepción en Venezuela con $90 envío a Venezuela -> Total lote = $1080 / 3 = $360.00 Primer Costo c/u
    #    1 a Preparación, 1 a Hospital, 1 a Revisión
    r_rec = cliente.post(
        f"/api/logistica/compras/{compra_id}/recibir",
        headers=cab_dir,
        json={
            "sucursal_destino_id": 1,
            "gastos_envio_venezuela_usd": 90.0,
            "cerrar_compra": True,
            "equipos": [
                {
                    "serial": "SN-E2E-INT-01",
                    "modelo": "Lenovo ThinkPad T14 Gen 2",
                    "ram": "16GB",
                    "almacenamiento": "256GB",
                    "condicion_llegada": "EXCELENTE",
                    "proceso_inicial": "PREPARACION",
                    "observaciones_llegada": "Lote USA excelente",
                    "precio_promo_usd": 600.0,
                },
                {
                    "serial": "SN-E2E-INT-02",
                    "modelo": "Lenovo ThinkPad T14 Gen 2",
                    "condicion_llegada": "CON_FALLA",
                    "proceso_inicial": "HOSPITAL",
                    "observaciones_llegada": "No da video",
                },
                {
                    "serial": "SN-E2E-INT-03",
                    "modelo": "Lenovo ThinkPad T14 Gen 2",
                    "condicion_llegada": "BUENO",
                    "proceso_inicial": "REVISION",
                    "observaciones_llegada": "Pendiente diagnóstico inicial",
                },
            ],
        },
    )
    assert r_rec.status_code == 201, r_rec.text
    rec_body = r_rec.json()
    assert rec_body["estado_compra"] == "RECIBIDA"
    eq1 = next(e for e in rec_body["equipos"] if e["serial"] == "SN-E2E-INT-01")
    eq2 = next(e for e in rec_body["equipos"] if e["serial"] == "SN-E2E-INT-02")
    eq3 = next(e for e in rec_body["equipos"] if e["serial"] == "SN-E2E-INT-03")
    assert eq1["estado"] == "POR_PREPARAR"
    assert eq2["estado"] == "HOSPITAL"
    assert eq3["estado"] == "EN_REVISION"
    assert eq1["primer_costo_usd"] == 360.0

    # 3. Preparación de SN-E2E-INT-01: agregar SSD ($35) + Batería ($25) + Comisión ($15) -> Costo Final = $435.00
    r_inst_ssd = cliente.post(
        f"/api/taller/preparaciones/{eq1['id']}/componentes",
        headers=cab_dir,
        json={"articulo_id": ssd_id, "cantidad": 1, "nota": "Upgrade SSD 512GB"},
    )
    assert r_inst_ssd.status_code == 201, r_inst_ssd.text

    r_inst_bat = cliente.post(
        f"/api/taller/preparaciones/{eq1['id']}/componentes",
        headers=cab_dir,
        json={"articulo_id": bat_id, "cantidad": 1, "nota": "Cambio batería nueva"},
    )
    assert r_inst_bat.status_code == 201, r_inst_bat.text

    r_prep = cliente.post(
        "/api/taller/preparaciones",
        headers=cab_dir,
        json={
            "equipo_id": eq1["id"],
            "tipo": "ESTANDAR",
            "comision_preparacion_usd": 15.0,
            "resultado": "LISTO",
            "nota": "Preparación completa con SSD + batería",
        },
    )
    assert r_prep.status_code == 201, r_prep.text

    # 4. Vender SN-E2E-INT-01 por $600.00 (sin_cargador=True) -> Ganancia Real = $600 - $435 = $165.00
    r_vta = cliente.post(
        "/api/ventas",
        headers=cab_dir,
        json={
            "sucursal_id": 1,
            "sin_cargador": True,
            "motivo_sin_cargador": "Venta E2E prueba",
            "items": [{"equipo_id": eq1["id"], "cantidad": 1, "precio_pactado_usd": 600.0}],
            "pagos": [{"instrumento_id": inst_usd, "monto_moneda_origen": 600.0}],
        },
    )
    assert r_vta.status_code == 201, r_vta.text

    # 5. Registrar 1 incidente de garantía sobre SN-E2E-INT-01
    r_gt = cliente.post(
        "/api/taller/casos",
        headers=cab_dir,
        json={
            "tipo": "GARANTIA",
            "sucursal_id": 1,
            "equipo_id": eq1["id"],
            "serial_o_codigo": "SN-E2E-INT-01",
            "descripcion_equipo": "Lenovo ThinkPad T14 Gen 2",
            "falla_reportada": "Tecla Enter floja tras 10 días",
        },
    )
    assert r_gt.status_code == 201, r_gt.text

    # 6. Consultar Trazabilidad Total por Serial (GET /api/inventario/trazabilidad/SN-E2E-INT-01)
    r_traz = cliente.get("/api/inventario/trazabilidad/SN-E2E-INT-01", headers=cab_dir)
    assert r_traz.status_code == 200, r_traz.text
    t = r_traz.json()

    # Verificar las 7 secciones y exactitud financiera
    assert t["compra_internacional"]["subtotal_miami_usd"] == 990.0
    assert t["compra_internacional"]["taxes_usd"] == 60.0
    assert t["compra_internacional"]["envio_miami_usd"] == 30.0
    assert t["compra_internacional"]["gastos_envio_venezuela_usd"] == 90.0
    assert t["recepcion"]["primer_costo_usd"] == 360.0
    assert t["recepcion"]["proceso_inicial"] == "PREPARACION"
    assert len(t["historial_procesos"]) >= 2
    assert len(t["preparacion"]["componentes_agregados"]) == 2
    assert t["preparacion"]["total_componentes_usd"] == 60.0
    assert t["preparacion"]["comision_preparacion_usd"] == 15.0
    assert t["preparacion"]["costo_final_usd"] == 435.0
    assert t["venta"]["precio_venta_usd"] == 600.0
    assert t["venta"]["costo_final_usd"] == 435.0
    assert t["venta"]["ganancia_real_usd"] == 165.0
    assert len(t["incidentes_postventa"]) == 1
    assert "Tecla Enter" in t["incidentes_postventa"][0]["falla_reportada"]

    # RBAC: TECNICO ve la trazabilidad operativa pero SIN costos internos
    r_traz_tec = cliente.get("/api/inventario/trazabilidad/SN-E2E-INT-01", headers=cab_tec)
    assert r_traz_tec.status_code == 200
    t_tec = r_traz_tec.json()
    assert "primer_costo_usd" not in t_tec["recepcion"]
    assert "costo_final_usd" not in t_tec["preparacion"]
    assert "ganancia_real_usd" not in (t_tec["venta"] or {})
