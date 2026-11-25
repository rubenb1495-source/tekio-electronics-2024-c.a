from __future__ import annotations

import sys
from datetime import timedelta
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


def test_panel_direccion_tesoreria_y_alertas_inteligentes(cliente: TestClient) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]
    cab_as = ctx["headers_as"]
    hoy = obtener_fecha_hoy()

    # Crear técnico para verificar RBAC 403
    r_tec = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": "Pedro Técnico",
            "correo": "pedro.tec.dir@tekio.com",
            "clave": "Password123!",
            "rol": "TECNICO",
            "sucursal_id": 1,
        },
    )
    assert r_tec.status_code == 201
    cab_tec = _login(cliente, "pedro.tec.dir@tekio.com", "Password123!")

    # 1. RBAC: ASESORA y TECNICO reciben 403 en /direccion/resumen, /finanzas/tesoreria y /alertas
    for cab_op in (cab_as, cab_tec):
        assert cliente.get("/api/direccion/resumen", headers=cab_op).status_code == 403
        assert cliente.get("/api/alertas", headers=cab_op).status_code == 403
        assert cliente.get("/api/finanzas/tesoreria", headers=cab_op).status_code == 403

    # 2. Alertas Inteligentes: crear SKU sin stock (stock_actual=0 <= stock_minimo=2) y Compra CxP por vencer en 3 días
    r_sku = cliente.post(
        "/api/catalogo",
        headers=cab_dir,
        json={
            "sku": "ACC-BATERIA-LOW",
            "descripcion": "Batería Original HP (Stock Bajo)",
            "tipo": "COMPONENTE",
            "categoria": "Repuestos",
            "precio_promo_usd": 45.0,
            "costo_referencia_usd": 20.0,
        },
    )
    assert r_sku.status_code == 201, r_sku.text

    r_prov = cliente.post(
        "/api/logistica/terceros",
        headers=cab_dir,
        json={"nombre": "Distribuidora Crédito", "tipo": "PROVEEDOR", "rif_cedula": "J-888888"},
    )
    assert r_prov.status_code == 201
    prov_id = r_prov.json()["id"]

    vence_3d = (hoy + timedelta(days=3)).isoformat()
    r_cxp = cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "proveedor_id": prov_id,
            "fecha": hoy.isoformat(),
            "fecha_vencimiento": vence_3d,
            "saldo_pendiente_usd": 750.0,
            "factura_orden": "FAC-CRED-01",
            "monto_mercancia_usd": 750.0,
            "equipos": [],
        },
    )
    assert r_cxp.status_code == 201, r_cxp.text

    r_alertas = cliente.get("/api/alertas", headers=cab_dir)
    assert r_alertas.status_code == 200, r_alertas.text
    al = r_alertas.json()
    assert any(s["sku"] == "ACC-BATERIA-LOW" and s["criticidad"] == "AGOTADO" for s in al["stock_bajo"])
    assert any(
        c["factura_orden"] == "FAC-CRED-01"
        and c["estado"] == "POR_VENCER"
        and c["saldo_pendiente_usd"] == 750.0
        for c in al["cxp_por_vencer"]
    )

    # 3. Tesorería: Transferencia atómica misma moneda y Cambio de Divisa con diferencial exacto
    insts = cliente.get("/api/finanzas/instrumentos", headers=cab_dir).json()
    usd_list = [i for i in insts if i["moneda"] == "USD" and "parte" not in i["nombre"].lower()]
    bs_inst = next(i for i in insts if i["moneda"] == "BS")
    assert len(usd_list) >= 2

    # 3.1 Transferencia USD -> USD
    r_tr = cliente.post(
        "/api/finanzas/tesoreria",
        headers=cab_dir,
        json={
            "tipo": "TRANSFERENCIA",
            "instrumento_origen_id": usd_list[0]["id"],
            "monto_origen": 200.0,
            "instrumento_destino_id": usd_list[1]["id"],
            "monto_destino": 200.0,
            "referencia": "TR-INT-001",
        },
    )
    assert r_tr.status_code == 201, r_tr.text
    tr_data = r_tr.json()
    assert tr_data["diferencia_usd"] == 0.0
    assert tr_data["pago_egreso_id"] is not None
    assert tr_data["pago_ingreso_id"] is not None

    # 3.2 Cambio de Divisa USD -> BS con ganancia cambiaria
    # En escenario base tasa_usdt = 60.00; vendemos $100 a tasa 66.00 -> recibimos Bs 6,600.00
    # Valor recibido a tasa ref 60.00 = 6600 / 60 = $110.00 -> ganancia = +$10.00 (+10.00%)
    r_cambio = cliente.post(
        "/api/finanzas/tesoreria",
        headers=cab_dir,
        json={
            "tipo": "CAMBIO_DIVISA",
            "instrumento_origen_id": usd_list[0]["id"],
            "monto_origen": 100.0,
            "instrumento_destino_id": bs_inst["id"],
            "monto_destino": 6600.0,
            "tasa_pactada": 66.0,
            "referencia": "CAMBIO-GAN-01",
        },
    )
    assert r_cambio.status_code == 201, r_cambio.text
    c_data = r_cambio.json()
    assert c_data["diferencia_usd"] == 10.0
    assert c_data["diferencia_pct"] == 10.0

    # 4. Panel Ejecutivo de Dirección (200 para DIRECCION)
    r_dir = cliente.get("/api/direccion/resumen", headers=cab_dir)
    assert r_dir.status_code == 200, r_dir.text
    res_dir = r_dir.json()
    assert len(res_dir["tesoreria"]["cuentas"]) >= 2
    assert res_dir["inventario"]["unidades_listo"] >= 1
    assert res_dir["cartera"]["cxp_total_usd"] == 750.0
    assert res_dir["cartera"]["cxp_proximas_7d_usd"] == 750.0
    assert res_dir["alertas"]["total_alertas"] >= 2
