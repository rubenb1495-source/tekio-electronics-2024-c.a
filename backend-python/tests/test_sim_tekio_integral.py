from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

_DIR_TESTS = str(Path(__file__).resolve().parent)
if _DIR_TESTS not in sys.path:
    sys.path.insert(0, _DIR_TESTS)

from app.base_datos import obtener_bd  # noqa: E402
from app.main import app  # noqa: E402
from app.modelos_finanzas import (  # noqa: E402
    EstadoVerificacionPago,
    Pago,
    TipoMovimientoPago,
)
from app.rutas.tasas import obtener_fecha_hoy  # noqa: E402
from app.servicios.contabilidad_service import registrar_asiento  # noqa: E402
from test_fase5 import (  # noqa: E402
    _login,
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def test_sim_tekio_ciclo_integral_completo_y_cuadre_cero(cliente: TestClient) -> None:
    """
    [SIM-TEKIO] Simulación integral reproducible de un ciclo completo de negocio:
    1. Apertura de cajas (incluyendo Caja Chica $60 USD contra Capital Inicial -> impacto $0 en P&L).
    2. Descarga de las 3 plantillas Excel (.xlsx) de apertura.
    3. Ingreso de inventario (2 equipos + 1 componente RAM).
    4. Traslado de equipo de Bodega/Sucursal 1 a Sucursal 2 + Planilla PDF + Confirmación formal de recepción.
    5. Preparación agregando componente RAM ($20 -> costo equipo sube $120 -> $140).
    6. Venta contado ($250 Promo) + Venta Cashea ($400 Promo -> Regular con 4%+4%+16%+2% deducciones).
    7. Cambio de divisa en Tesorería (con diferencial cambiario).
    8. Registro de gasto operativo (ALQUILER_TIENDA) y liquidación de comisión a asesora (1%).
    9. Verificación final:
       - Auditoría de todos los asientos contables: 0 descuadrados, diferencia global $0.00.
       - Estado de Resultados (P&L) refleja ingresos, COGS, gastos, comisiones y utilidad neta exacta.
       - Balance General cuadra con varianza EXACTA $0.00 (Total Activos == Total Pasivos + Patrimonio).
    """
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]
    cab_as = ctx["headers_as"]
    hoy = obtener_fecha_hoy()
    hoy_str = hoy.isoformat()

    # Crear Técnico y Líder para el ciclo completo
    for u in (
        {
            "nombre": "[SIM-TEKIO] Técnico Taller",
            "correo": "sim.tec@tekio.com",
            "clave": "Password123!",
            "rol": "TECNICO",
            "sucursal_id": 1,
        },
        {
            "nombre": "[SIM-TEKIO] Líder Sucursal 2",
            "correo": "sim.lider@tekio.com",
            "clave": "Password123!",
            "rol": "LIDER",
            "sucursal_id": 2,
        },
    ):
        assert cliente.post("/api/usuarios", headers=cab_dir, json=u).status_code == 201
    cab_tec = _login(cliente, "sim.tec@tekio.com", "Password123!")
    cab_lider = _login(cliente, "sim.lider@tekio.com", "Password123!")

    # 1. Plantillas Excel de apertura (.xlsx)
    for tipo_pl in ("saldos_iniciales", "inventario_inicial", "cxc_cxp_iniciales"):
        r_pl_x = cliente.get(f"/api/finanzas/apertura/plantillas/{tipo_pl}", headers=cab_dir)
        assert r_pl_x.status_code == 200, r_pl_x.text
        assert r_pl_x.content[:2] == b"PK"  # Firma ZIP/XLSX válida
        assert cliente.get(f"/api/finanzas/apertura/plantillas/{tipo_pl}", headers=cab_as).status_code == 403

    # 2. Apertura de Caja Chica ($60 USD) contra Capital Inicial (3.1.01) — impacto $0 en P&L
    insts = cliente.get("/api/finanzas/instrumentos", headers=cab_dir).json()
    inst_usd = next(i for i in insts if i["moneda"] == "USD" and "parte de pago" not in i["nombre"].lower())
    inst_bs = next(i for i in insts if i["moneda"] == "BS")
    inst_cashea = next(i for i in insts if "cashea" in i["nombre"].lower())

    override_bd = app.dependency_overrides[obtener_bd]
    gen_bd = override_bd()
    bd = next(gen_bd)
    try:
        bd.add(
            Pago(
                venta_id=None,
                instrumento_id=inst_usd["id"],
                fecha=hoy,
                tipo_movimiento=TipoMovimientoPago.INGRESO.value,
                tipo_documento="APERTURA_CAJA_CHICA",
                monto_moneda_origen=Decimal("60.00"),
                moneda="USD",
                usd_nominal=Decimal("60.00"),
                usd_real=Decimal("60.00"),
                referencia="[SIM-TEKIO]-CAJA-CHICA-60",
                estado_verificacion=EstadoVerificacionPago.CONFIRMADO.value,
                nota="[SIM-TEKIO] Apertura caja chica $60 USD",
            )
        )
        registrar_asiento(
            bd,
            fecha=hoy,
            referencia="[SIM-TEKIO]-APE-60",
            modulo_origen="APERTURA",
            entidad_id="CAJA-CHICA",
            descripcion="[SIM-TEKIO] Apertura Caja Chica $60 USD contra Capital Inicial",
            lineas=[
                {"codigo_cuenta": "1.1.01", "debe_usd": Decimal("60.00"), "descripcion": "Caja Chica $60"},
                {"codigo_cuenta": "3.1.01", "haber_usd": Decimal("60.00"), "descripcion": "Capital Inicial"},
            ],
        )
        bd.commit()
    finally:
        try:
            next(gen_bd)
        except StopIteration:
            pass

    # 3. Ingreso de inventario: 2 equipos ($120 y $250) + 1 RAM ($20)
    r_ram = cliente.post(
        "/api/catalogo",
        headers=cab_dir,
        json={
            "sku": "SIM-RAM-8GB",
            "descripcion": "[SIM-TEKIO] RAM 8GB DDR4",
            "tipo": "COMPONENTE",
            "categoria": "Memoria",
            "precio_promo_usd": 35,
            "costo_referencia_usd": 20,
        },
    )
    assert r_ram.status_code == 201
    ram_id = r_ram.json()["id"]

    r_cmp = cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "fecha": hoy_str,
            "factura_orden": "[SIM-TEKIO]-FAC-01",
            "monto_mercancia_usd": 390,
            "equipos": [
                {
                    "serial": "SIM-EQ-CONTADO",
                    "modelo": "[SIM-TEKIO] Laptop Contado",
                    "costo_compra_usd": 120,
                    "precio_promo_usd": 250,
                    "ubicacion_id": 1,
                },
                {
                    "serial": "SIM-EQ-CASHEA",
                    "modelo": "[SIM-TEKIO] Laptop Cashea",
                    "costo_compra_usd": 250,
                    "precio_promo_usd": 400,
                    "ubicacion_id": 1,
                },
            ],
            "componentes": [
                {
                    "articulo_id": ram_id,
                    "cantidad": 1,
                    "costo_unitario_usd": 20,
                    "ubicacion_id": 1,
                }
            ],
        },
    )
    assert r_cmp.status_code == 201, r_cmp.text

    equipos = cliente.get("/api/logistica/inventario/equipos", headers=cab_dir).json()
    eq1_id = next(e["id"] for e in equipos if e["serial"] == "SIM-EQ-CONTADO")
    eq2_id = next(e["id"] for e in equipos if e["serial"] == "SIM-EQ-CASHEA")

    # 4. Preparación agregando componente RAM ($20 -> eq1 costo $120 -> $140) y pasar ambos a LISTO
    assert (
        cliente.post(
            f"/api/taller/preparaciones/{eq1_id}/componentes",
            headers=cab_tec,
            json={"articulo_id": ram_id, "cantidad": 1, "nota": "[SIM-TEKIO] Upgrade RAM"},
        ).status_code
        == 201
    )
    assert (
        cliente.patch(
            "/api/inventario/equipos/estado-masivo",
            headers=cab_dir,
            json={"equipo_ids": [eq1_id, eq2_id], "nuevo_estado": "LISTO"},
        ).status_code
        == 200
    )

    # 5. Traslado de eq2 de Sucursal 1 -> Sucursal 2 + Planilla PDF + Confirmación formal de recepción
    r_trs = cliente.post(
        "/api/logistica/traslados",
        headers=cab_dir,
        json={
            "origen_id": 1,
            "destino_id": 2,
            "equipos_ids": [eq2_id],
            "nota": "[SIM-TEKIO] Traslado a Sucursal 2",
        },
    )
    assert r_trs.status_code == 201, r_trs.text
    trs_id = r_trs.json()["id"]

    r_trs_pdf = cliente.get(f"/api/logistica/traslados/{trs_id}/pdf", headers=cab_lider)
    assert r_trs_pdf.status_code == 200
    assert r_trs_pdf.content.startswith(b"%PDF")

    r_conf = cliente.post(
        f"/api/logistica/traslados/{trs_id}/confirmar-recepcion",
        headers=cab_lider,
        json={"nota_recepcion": "[SIM-TEKIO] Recibido conforme en sucursal 2"},
    )
    assert r_conf.status_code == 200, r_conf.text
    assert r_conf.json()["estado"] == "RECIBIDO"

    # 6. Venta contado ($250) en Sucursal 1 + Venta Cashea ($400 Promo) en Sucursal 2
    r_v1 = cliente.post(
        "/api/ventas",
        headers=cab_as,
        json={
            "sucursal_id": 1,
            "fecha": hoy_str,
            "asesor_id": ctx["asesora_id"],
            "sin_cargador": True,
            "items": [{"equipo_id": eq1_id, "cantidad": 1, "precio_pactado_usd": 250}],
            "pagos": [{"instrumento_id": inst_usd["id"], "monto_moneda_origen": 250}],
        },
    )
    assert r_v1.status_code == 201, r_v1.text

    r_sim_c = cliente.post(
        "/api/ventas/simular",
        headers=cab_dir,
        json={
            "sucursal_id": 2,
            "items": [{"equipo_id": eq2_id, "cantidad": 1, "precio_pactado_usd": 400}],
            "pagos": [{"instrumento_id": inst_cashea["id"], "monto_moneda_origen": 240}],
        },
    )
    assert r_sim_c.status_code == 200
    total_reg_c = r_sim_c.json()["total_regular_usd"]
    inicial_c = round(total_reg_c - 240.0, 2)

    r_v2 = cliente.post(
        "/api/ventas",
        headers=cab_dir,
        json={
            "sucursal_id": 2,
            "fecha": hoy_str,
            "asesor_id": ctx["asesora_id"],
            "cashea_numero_orden": "CSH-SIM-001",
            "sin_cargador": True,
            "items": [{"equipo_id": eq2_id, "cantidad": 1, "precio_pactado_usd": 400}],
            "pagos": [
                {"instrumento_id": inst_usd["id"], "monto_moneda_origen": inicial_c},
                {"instrumento_id": inst_cashea["id"], "monto_moneda_origen": 240},
            ],
        },
    )
    assert r_v2.status_code == 201, r_v2.text

    # Verificar panel financiero Cashea (solo Finanzas)
    r_cxc_cashea = cliente.get(
        "/api/finanzas/cuentas-por-cobrar?tipo=CASHEA&estado=PENDIENTE",
        headers=cab_dir,
    )
    assert r_cxc_cashea.status_code == 200
    assert len(r_cxc_cashea.json()) >= 1
    assert r_cxc_cashea.json()[0]["total_deducciones_cashea_usd"] > 0

    # 7. Cambio de divisa en Tesorería + Gasto Operativo + Liquidación de Comisión a Asesora
    r_tes = cliente.post(
        "/api/finanzas/tesoreria",
        headers=cab_dir,
        json={
            "tipo": "CAMBIO_DIVISA",
            "fecha": hoy_str,
            "instrumento_origen_id": inst_usd["id"],
            "monto_origen": 50,
            "instrumento_destino_id": inst_bs["id"],
            "monto_destino": 2500,
            "referencia": "[SIM-TEKIO]-CAMBIO",
        },
    )
    assert r_tes.status_code == 201, r_tes.text

    r_gasto = cliente.post(
        "/api/finanzas/gastos",
        headers=cab_dir,
        json={
            "fecha": hoy_str,
            "categoria": "ALQUILER_TIENDA",
            "sucursal_id": 1,
            "proveedor": "[SIM-TEKIO] Arrendador",
            "descripcion": "[SIM-TEKIO] Alquiler mensual",
            "moneda": "USD",
            "monto_origen": 50,
            "instrumento_id": inst_usd["id"],
        },
    )
    assert r_gasto.status_code == 201, r_gasto.text

    r_liq = cliente.post(
        "/api/finanzas/liquidaciones",
        headers=cab_dir,
        json={
            "usuario_id": ctx["asesora_id"],
            "fecha_inicio": hoy_str,
            "fecha_fin": hoy_str,
            "instrumento_id": inst_usd["id"],
            "referencia": "[SIM-TEKIO]-LIQ-COM",
            "notas": "[SIM-TEKIO] Liquidación comisiones asesora",
        },
    )
    assert r_liq.status_code == 201, r_liq.text

    # 8. VERIFICACIÓN INTEGRAL FINAL: Auditoría de Asientos + P&L + Balance General (varianza $0.00)
    r_aud_as = cliente.get("/api/finanzas/contabilidad/auditoria-asientos", headers=cab_dir)
    assert r_aud_as.status_code == 200, r_aud_as.text
    aud = r_aud_as.json()
    assert aud["integridad_ok"] is True
    assert aud["asientos_descuadrados"] == 0
    assert aud["diferencia_global_usd"] == 0.0
    assert aud["total_asientos"] >= 8

    r_pl = cliente.get(
        f"/api/finanzas/estados/pl-escalonado?fecha_inicio={hoy_str}&fecha_fin={hoy_str}",
        headers=cab_dir,
    )
    assert r_pl.status_code == 200, r_pl.text
    pl = r_pl.json()
    assert pl["ingresos_netos_usd"] == 650.0  # 250 + 400
    assert pl["costo_ventas_usd"] == 390.0  # 140 + 250
    assert pl["utilidad_bruta_usd"] == 260.0
    assert pl["gastos_operativos_usd"] == 50.0
    assert pl["comisiones_cashea_usd"] > 0

    r_bal = cliente.get(
        f"/api/finanzas/estados/balance-general?fecha_corte={hoy_str}",
        headers=cab_dir,
    )
    assert r_bal.status_code == 200, r_bal.text
    bal = r_bal.json()
    assert bal["cuadrado"] is True
    assert bal["diferencia_cuadre_usd"] == 0.0
    assert bal["activos"]["total_activos_usd"] == bal["total_pasivo_mas_patrimonio_usd"]
