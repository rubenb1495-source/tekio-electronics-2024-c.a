from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

_DIR_TESTS = str(Path(__file__).resolve().parent)
if _DIR_TESTS not in sys.path:
    sys.path.insert(0, _DIR_TESTS)

from app.base_datos import SesionLocal  # noqa: E402
from app.modelos_finanzas import CuentaPorCobrar, EstadoCuentaPorCobrar, TipoCuentaPorCobrar  # noqa: E402
from app.rutas.tasas import obtener_fecha_hoy  # noqa: E402
from test_fase5 import (  # noqa: E402
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def test_conciliacion_cashea_una_fila_por_nota_con_multiples_articulos_y_pagos(
    cliente: TestClient,
) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]
    hoy_str = obtener_fecha_hoy().isoformat()

    # 1. Crear 2 artículos en catálogo y stock (1 equipo serializado + 1 accesorio)
    r_cat1 = cliente.post(
        "/api/catalogo",
        headers=cab_dir,
        json={
            "sku": "CASHEA-LAP-01",
            "descripcion": "Laptop Cashea Regresión",
            "tipo": "EQUIPO",
            "categoria": "Laptops",
            "precio_promo_usd": 400,
            "precio_regular_fijo_usd": 500,
            "costo_referencia_usd": 250,
            "fecha_vigencia": hoy_str,
        },
    )
    assert r_cat1.status_code == 201, r_cat1.text
    art_eq_id = r_cat1.json()["id"]

    r_cat2 = cliente.post(
        "/api/catalogo",
        headers=cab_dir,
        json={
            "sku": "CASHEA-ACC-01",
            "descripcion": "Mouse Inalámbrico Regresión",
            "tipo": "ACCESORIO",
            "categoria": "Accesorios",
            "precio_promo_usd": 40,
            "precio_regular_fijo_usd": 50,
            "costo_referencia_usd": 15,
            "fecha_vigencia": hoy_str,
        },
    )
    assert r_cat2.status_code == 201, r_cat2.text
    art_acc_id = r_cat2.json()["id"]

    r_comp = cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "fecha": hoy_str,
            "monto_mercancia_usd": 280,
            "envio_usd": 0,
            "llega_preparada": True,
            "equipos": [
                {
                    "serial": "SN-CASHEA-DUP-001",
                    "modelo": "Laptop Cashea Regresión",
                    "articulo_id": art_eq_id,
                    "costo_compra_usd": 250,
                    "precio_promo_usd": 400,
                    "ubicacion_id": 2,
                }
            ],
            "componentes": [
                {
                    "articulo_id": art_acc_id,
                    "cantidad": 2,
                    "costo_unitario_usd": 15,
                    "ubicacion_id": 2,
                }
            ],
        },
    )
    assert r_comp.status_code == 201, r_comp.text
    r_eqs = cliente.get("/api/logistica/inventario/equipos?buscar=SN-CASHEA-DUP-001", headers=cab_dir)
    assert r_eqs.status_code == 200
    eq_lista = r_eqs.json()
    eq_id = (eq_lista["elementos"][0] if isinstance(eq_lista, dict) else eq_lista[0])["id"]

    # Obtener instrumentos: Efectivo USD (inicial) y Cashea (financiado)
    r_inst = cliente.get("/api/finanzas/instrumentos", headers=cab_dir)
    assert r_inst.status_code == 200
    insts = r_inst.json()
    inst_efectivo = next(i for i in insts if "efectivo" in i["nombre"].lower() and i["moneda"] == "USD")
    inst_cashea = next(i for i in insts if "cashea" in i["nombre"].lower())

    # 2. Emitir 1 sola venta Cashea con 2 artículos y 2 pagos (inicial efectivo + financiado Cashea)
    # Total Regular = $500 + $50 = $550 -> Inicial $220 Efectivo USD + Financiado $330 Cashea
    r_vta = cliente.post(
        "/api/ventas",
        headers=cab_dir,
        json={
            "sucursal_id": 2,
            "cliente_id": ctx["cliente_id"],
            "asesor_id": ctx["asesora_id"],
            "tipo_entrega": "TIENDA",
            "canal_visita": "TIENDA",
            "fecha": hoy_str,
            "sin_cargador": True,
            "items": [
                {"tipo_item": "EQUIPO", "equipo_id": eq_id, "cantidad": 1},
                {"tipo_item": "COMPONENTE", "articulo_id": art_acc_id, "cantidad": 1},
            ],
            "pagos": [
                {"instrumento_id": inst_efectivo["id"], "monto_moneda_origen": 220, "referencia": "INI-01"},
                {"instrumento_id": inst_cashea["id"], "monto_moneda_origen": 330, "referencia": "CAS-01"},
            ],
        },
    )
    assert r_vta.status_code == 201, r_vta.text
    venta = r_vta.json()
    venta_id = venta["id"]
    numero_venta = venta["numero_venta"]

    # 3. Verificar en GET /api/finanzas/cuentas-por-cobrar?tipo=CASHEA&estado=PENDIENTE
    r_cxc = cliente.get(
        "/api/finanzas/cuentas-por-cobrar?tipo=CASHEA&estado=PENDIENTE",
        headers=cab_dir,
    )
    assert r_cxc.status_code == 200, r_cxc.text
    filas_nota = [f for f in r_cxc.json() if f["venta_id"] == venta_id]
    assert len(filas_nota) == 1
    assert filas_nota[0]["numero_venta"] == numero_venta
    assert filas_nota[0]["saldo_pendiente_usd"] == 330.0

    # 4. Verificar en GET /api/finanzas/cashea (items y KPIs sin duplicación)
    r_cas = cliente.get("/api/finanzas/cashea?estado=PENDIENTE", headers=cab_dir)
    assert r_cas.status_code == 200, r_cas.text
    body = r_cas.json()
    assert body["total_notas"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["numero_venta"] == numero_venta
    assert body["kpis"]["financiado_bruto_usd"] == 330.0
    total_reg = float(venta["total_regular_usd"])
    com_tot_esp = round(total_reg * 0.04, 2)
    com_fin_esp = round(330.0 * 0.04, 2)
    iva_esp = round(com_tot_esp * 0.16, 2)
    islr_esp = round(com_tot_esp * 0.02, 2)
    ded_esp = round(com_tot_esp + com_fin_esp + iva_esp + islr_esp, 2)
    neto_esp = round(330.0 - ded_esp, 2)

    assert body["kpis"]["comision_venta_total_usd"] == com_tot_esp
    assert body["kpis"]["comision_financiado_usd"] == com_fin_esp
    assert body["kpis"]["iva_cashea_usd"] == iva_esp
    assert body["kpis"]["islr_cashea_usd"] == islr_esp
    assert body["kpis"]["total_deducciones_usd"] == ded_esp
    assert body["kpis"]["neto_real_esperado_usd"] == neto_esp

    # 5. Robustez: incluso si existiera un registro CxC Cashea duplicado en BD para la misma venta,
    # el endpoint consolida en exactamente 1 fila única por venta_id sin duplicar comisiones ni notas.
    with SesionLocal() as bd:
        bd.add(
            CuentaPorCobrar(
                venta_id=venta_id,
                tipo=TipoCuentaPorCobrar.CASHEA.value,
                cliente_id=ctx["cliente_id"],
                monto_original_usd=Decimal("0.00"),
                saldo_pendiente_usd=Decimal("0.00"),
                estado=EstadoCuentaPorCobrar.PENDIENTE.value,
            )
        )
        bd.commit()

    r_cas_dedup = cliente.get("/api/finanzas/cashea?estado=PENDIENTE", headers=cab_dir)
    assert r_cas_dedup.status_code == 200
    assert r_cas_dedup.json()["total_notas"] == 1
    assert len(r_cas_dedup.json()["items"]) == 1
    assert r_cas_dedup.json()["kpis"]["total_deducciones_usd"] == ded_esp
