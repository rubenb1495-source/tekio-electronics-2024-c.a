from __future__ import annotations

import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_DIR_TESTS = str(Path(__file__).resolve().parent)
if _DIR_TESTS not in sys.path:
    sys.path.insert(0, _DIR_TESTS)

from app.base_datos import obtener_bd  # noqa: E402
from app.main import app  # noqa: E402
from app.rutas.tasas import obtener_fecha_hoy  # noqa: E402
from app.servicios.contabilidad_service import ErrorPartidaDoble, registrar_asiento  # noqa: E402
from test_fase5 import (  # noqa: E402
    _login,
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def test_partida_doble_estricta_rechaza_descuadre(cliente: TestClient) -> None:
    _preparar_escenario_base(cliente)
    override_bd = app.dependency_overrides[obtener_bd]
    gen_bd = override_bd()
    bd = next(gen_bd)
    try:
        with pytest.raises(ErrorPartidaDoble):
            registrar_asiento(
                bd,
                fecha=obtener_fecha_hoy(),
                referencia="TEST-DESC-001",
                modulo_origen="PRUEBA",
                entidad_id=1,
                descripcion="Asiento intencionalmente descuadrado",
                lineas=[
                    {"codigo_cuenta": "1.1.01", "debe_usd": Decimal("100.00")},
                    {"codigo_cuenta": "4.1.01", "haber_usd": Decimal("99.50")},
                ],
            )
    finally:
        try:
            next(gen_bd)
        except StopIteration:
            pass


def test_componente_en_preparacion_margen_real_prestamos_y_estados_financieros(
    cliente: TestClient,
) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]
    cab_as = ctx["headers_as"]
    hoy = obtener_fecha_hoy()
    hoy_str = hoy.isoformat()

    # Crear Técnico para validar RBAC en componentes y vistas contables
    r_tec = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": "Carlos Técnico Cont",
            "correo": "carlos.tec.cont@tekio.com",
            "clave": "Password123!",
            "rol": "TECNICO",
            "sucursal_id": 1,
        },
    )
    assert r_tec.status_code == 201, r_tec.text
    cab_tec = _login(cliente, "carlos.tec.cont@tekio.com", "Password123!")

    # 1. RBAC 403 en rutas contables/préstamos/estados para ASESORA y TECNICO
    for cab_op in (cab_as, cab_tec):
        for ruta in (
            "/api/finanzas/contabilidad/plan-cuentas",
            "/api/finanzas/contabilidad/asientos",
            "/api/finanzas/prestamos",
            "/api/finanzas/estados/pl-escalonado",
            "/api/finanzas/estados/balance-general",
        ):
            assert cliente.get(ruta, headers=cab_op).status_code == 403, f"Falló RBAC en {ruta}"

    # 2. Crear componente SSD en catálogo e ingresar stock + 1 equipo en compra
    r_art = cliente.post(
        "/api/catalogo",
        headers=cab_dir,
        json={
            "sku": "SSD-512-NVME-CONT",
            "descripcion": "SSD 512GB NVMe",
            "tipo": "COMPONENTE",
            "categoria": "Almacenamiento",
            "precio_promo_usd": 45,
            "costo_referencia_usd": 30,
        },
    )
    assert r_art.status_code == 201, r_art.text
    ssd_id = r_art.json()["id"]

    r_comp = cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "fecha": hoy_str,
            "monto_mercancia_usd": 360,
            "equipos": [
                {
                    "serial": "CONT-EQ-001",
                    "modelo": "ThinkPad X1 Carbon",
                    "configuracion": "i7 / 16GB",
                    "costo_compra_usd": 300,
                    "precio_promo_usd": 500,
                    "ubicacion_id": 1,
                }
            ],
            "componentes": [
                {
                    "articulo_id": ssd_id,
                    "cantidad": 2,
                    "costo_unitario_usd": 30,
                    "ubicacion_id": 1,
                }
            ],
        },
    )
    assert r_comp.status_code == 201, r_comp.text

    eq = next(
        e
        for e in cliente.get("/api/logistica/inventario/equipos", headers=cab_dir).json()
        if e["serial"] == "CONT-EQ-001"
    )
    eq_id = eq["id"]
    assert eq["costo_total_usd"] == 300.0

    # 3. Técnico instala 1x SSD ($30) en preparación: no ve costos, pero suma al costo del equipo
    r_inst = cliente.post(
        f"/api/taller/preparaciones/{eq_id}/componentes",
        headers=cab_tec,
        json={"articulo_id": ssd_id, "cantidad": 1, "nota": "Upgrade SSD"},
    )
    assert r_inst.status_code == 201, r_inst.text
    body_tec = r_inst.json()
    assert "costo_unitario_usd" not in body_tec
    assert "costo_total_equipo_usd" not in body_tec
    assert "SSD 512GB NVMe" in body_tec["configuracion_actualizada"]

    # Dirección verifica que el costo total del equipo subió de $300 a $330
    eq_despues = next(
        e
        for e in cliente.get("/api/logistica/inventario/equipos", headers=cab_dir).json()
        if e["id"] == eq_id
    )
    assert eq_despues["costo_total_usd"] == 330.0

    # Pasar equipo a LISTO y venderlo en POS ($500 Promo) con asesora (1% = $5) + líder (0.5% = $2.50)
    assert (
        cliente.patch(
            f"/api/inventario/equipos/{eq_id}/estado",
            headers=cab_dir,
            json={"nuevo_estado": "LISTO"},
        ).status_code
        == 200
    )

    inst_usd = next(
        i
        for i in cliente.get("/api/finanzas/instrumentos", headers=cab_dir).json()
        if i["moneda"] == "USD" and "parte de pago" not in i["nombre"].lower()
    )
    r_vta = cliente.post(
        "/api/ventas",
        headers=cab_dir,
        json={
            "sucursal_id": 1,
            "fecha": hoy_str,
            "asesor_id": ctx["asesora_id"],
            "sin_cargador": True,
            "items": [{"equipo_id": eq_id, "cantidad": 1, "precio_pactado_usd": 500}],
            "pagos": [{"instrumento_id": inst_usd["id"], "monto_moneda_origen": 500}],
        },
    )
    assert r_vta.status_code == 201, r_vta.text
    vta = r_vta.json()
    # Costo final = 330, Comisiones = 1% ($5) + 0.5% ($2.50) = $7.50, Margen neto real = 500 - 330 - 7.50 = 162.50
    assert vta["costo_equipo_final_usd"] == 330.0
    assert vta["comision_total_venta_usd"] == 7.5
    assert vta["margen_neto_real_usd"] == 162.5
    assert vta["margen_neto_real_pct"] == 32.5

    # 4. Módulo de Préstamos: crear préstamo, verificar tabla amortización, alertas 7d y pago de cuota
    fecha_prestamo = (hoy - timedelta(days=27)).isoformat()  # Primera cuota vence en ~3-4 días (dentro de 7d)
    r_prest = cliente.post(
        "/api/finanzas/prestamos",
        headers=cab_dir,
        json={
            "acreedor": "Banco Prueba Tekio",
            "monto_principal_usd": 1200,
            "tasa_interes_anual_pct": 12,
            "plazo_meses": 6,
            "fecha_inicio": fecha_prestamo,
            "instrumento_desembolso_id": inst_usd["id"],
        },
    )
    assert r_prest.status_code == 201, r_prest.text
    prest = r_prest.json()
    assert len(prest["cuotas"]) == 6
    suma_capital = round(sum(c["capital_usd"] for c in prest["cuotas"]), 2)
    assert suma_capital == 1200.0

    # Verificar alerta inteligente de cuota próxima a vencer (<= 7 días)
    r_al = cliente.get("/api/alertas", headers=cab_dir)
    assert r_al.status_code == 200
    assert any(a["origen"] == "PRESTAMO" for a in r_al.json()["cxp_por_vencer"])

    # Pagar primera cuota y verificar asiento contable (Debe 2.1.03 + 6.3.01 / Haber 1.1.01)
    primera_cuota = prest["cuotas"][0]
    r_pag = cliente.post(
        f"/api/finanzas/prestamos/{prest['id']}/cuotas/{primera_cuota['id']}/pagar",
        headers=cab_dir,
        json={
            "instrumento_id": inst_usd["id"],
            "fecha_pago": hoy_str,
            "referencia_pago": "TRF-CUOTA-1",
        },
    )
    assert r_pag.status_code == 200, r_pag.text
    assert r_pag.json()["cuotas_pagadas"] == 1

    # 5. Verificar P&L Escalonado, Balance General cuadrado y Libro Diario
    r_pl = cliente.get(
        f"/api/finanzas/estados/pl-escalonado?fecha_inicio={hoy_str}&fecha_fin={hoy_str}",
        headers=cab_dir,
    )
    assert r_pl.status_code == 200, r_pl.text
    pl = r_pl.json()
    assert pl["ingresos_netos_usd"] >= 500.0
    assert pl["costo_ventas_usd"] >= 330.0
    assert pl["intereses_prestamos_usd"] == primera_cuota["interes_usd"]

    r_bal = cliente.get(
        f"/api/finanzas/estados/balance-general?fecha_corte={hoy_str}",
        headers=cab_dir,
    )
    assert r_bal.status_code == 200, r_bal.text
    bal = r_bal.json()
    assert bal["cuadrado"] is True
    assert bal["diferencia_cuadre_usd"] == 0.0
    assert bal["activos"]["total_activos_usd"] == bal["total_pasivo_mas_patrimonio_usd"]
    assert bal["pasivos"]["prestamos_por_pagar_usd"] > 0

    # Exportaciones PDF y XLSX
    assert (
        cliente.get(
            f"/api/finanzas/estados/pl-escalonado/export?formato=pdf&fecha_inicio={hoy_str}&fecha_fin={hoy_str}",
            headers=cab_dir,
        ).status_code
        == 200
    )
    assert (
        cliente.get(
            f"/api/finanzas/estados/balance-general/export?formato=xlsx&fecha_corte={hoy_str}",
            headers=cab_dir,
        ).status_code
        == 200
    )

    # Todos los asientos del Libro Diario cumplen partida doble (debe == haber)
    r_asientos = cliente.get("/api/finanzas/contabilidad/asientos", headers=cab_dir)
    assert r_asientos.status_code == 200
    asientos = r_asientos.json()
    assert len(asientos) >= 5
    assert all(a["cuadrado"] is True and a["total_debe_usd"] == a["total_haber_usd"] for a in asientos)
