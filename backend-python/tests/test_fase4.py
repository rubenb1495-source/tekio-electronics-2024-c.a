from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.base_datos import Base, obtener_bd
from app.main import app
from app.rutas.tasas import obtener_fecha_hoy
from app.semilla import ejecutar_semilla
from app.semilla_finanzas import ejecutar_semilla_finanzas


@pytest.fixture()
def cliente() -> TestClient:
    motor_pruebas = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SesionPruebas = sessionmaker(autocommit=False, autoflush=False, bind=motor_pruebas)
    Base.metadata.create_all(bind=motor_pruebas)

    bd_seed = SesionPruebas()
    try:
        ejecutar_semilla(bd_seed)
        ejecutar_semilla_finanzas(bd_seed)
    finally:
        bd_seed.close()

    def obtener_bd_prueba():
        bd = SesionPruebas()
        try:
            yield bd
        finally:
            bd.close()

    app.dependency_overrides[obtener_bd] = obtener_bd_prueba
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def login(cliente: TestClient, correo: str, clave: str) -> tuple[dict[str, str], dict]:
    resp = cliente.post("/api/auth/login", json={"correo": correo, "clave": clave})
    assert resp.status_code == 200, resp.text
    datos = resp.json()
    return {"Authorization": f"Bearer {datos['token']}"}, datos["usuario"]


def crear_usuario_rol(
    cliente: TestClient,
    cab_dir: dict[str, str],
    nombre: str,
    correo: str,
    rol: str,
    sucursal_id: int = 2,
) -> tuple[dict[str, str], dict]:
    resp = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": nombre,
            "correo": correo,
            "clave": "ClaveSegura123",
            "rol": rol,
            "sucursal_id": sucursal_id,
        },
    )
    assert resp.status_code == 201, resp.text
    return login(cliente, correo, "ClaveSegura123")


def test_venta_mixta_pdf_bloqueo_serial_sucursal_cerrada_y_rbac(cliente: TestClient) -> None:
    cab_dir, _ = login(cliente, "direccion@tekioelectronics.com", "Tekio2026!")
    cab_asesora, asesora_u = crear_usuario_rol(
        cliente, cab_dir, "Caira Asesora", "caira_v@tekioelectronics.com", "ASESORA", 2
    )
    hoy = obtener_fecha_hoy()

    # 1. Registrar tasa del día: BCV = 60, USDT = 72, Recargo = 30%
    cliente.post(
        "/api/tasas",
        headers=cab_dir,
        json={
            "fecha": hoy.isoformat(),
            "tasa_bcv": 60.0,
            "tasa_usdt": 72.0,
            "recargo_porcentaje": 30.0,
        },
    )

    sucs = {s["nombre"]: s["id"] for s in cliente.get("/api/sucursales", headers=cab_dir).json()}
    central_id = sucs["Tekio central"]
    bodega_id = sucs["Bodega"]
    infot_id = sucs["INFOT"]

    insts = {
        i["nombre"]: i["id"]
        for i in cliente.get("/api/finanzas/instrumentos", headers=cab_dir).json()
    }

    # 2. Ingresar 2 equipos LISTO: uno en Tekio central ($200 promo) y uno en Bodega
    cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "fecha": hoy.isoformat(),
            "llega_preparada": True,
            "equipos": [
                {
                    "serial": "VTA-MIX-1",
                    "modelo": "Dell Latitude 5430",
                    "ubicacion_id": central_id,
                    "costo_compra_usd": 120.0,
                    "precio_promo_usd": 200.0,
                },
                {
                    "serial": "VTA-BOD-1",
                    "modelo": "HP Envy",
                    "ubicacion_id": bodega_id,
                    "costo_compra_usd": 150.0,
                    "precio_promo_usd": 250.0,
                },
            ],
        },
    )
    eq_central = cliente.get("/api/logistica/inventario/equipos?busqueda=VTA-MIX-1", headers=cab_dir).json()[0]
    eq_bodega = cliente.get("/api/logistica/inventario/equipos?busqueda=VTA-BOD-1", headers=cab_dir).json()[0]

    # 3. Intentar vender en sucursal CERRADA (INFOT) -> 403
    resp_infot = cliente.post(
        "/api/ventas",
        headers=cab_asesora,
        json={
            "sucursal_id": infot_id,
            "items": [{"equipo_id": eq_central["id"]}],
            "pagos": [{"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 200.0}],
        },
    )
    assert resp_infot.status_code == 403

    # 4. Intentar vender equipo de Bodega desde Tekio central -> 400
    resp_otra_suc = cliente.post(
        "/api/ventas",
        headers=cab_asesora,
        json={
            "sucursal_id": central_id,
            "items": [{"equipo_id": eq_bodega["id"]}],
            "pagos": [{"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 250.0}],
        },
    )
    assert resp_otra_suc.status_code == 400

    # 5. Simular venta mixta: $200 Promo -> paga $100 Efectivo USD, faltan $100 Promo = $130 Regular = 7,800 Bs
    sim = cliente.post(
        "/api/ventas/simular",
        headers=cab_asesora,
        json={
            "sucursal_id": central_id,
            "items": [{"equipo_id": eq_central["id"]}],
            "pagos": [{"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 100.0}],
        },
    ).json()
    assert sim["falta_usd_promo"] == 100.0
    assert sim["falta_bs"] == 7800.0

    # 6. Registrar venta mixta completa ($100 Efectivo + 7,800 Bs Pago móvil) -> CUADRADA
    resp_vta = cliente.post(
        "/api/ventas",
        headers=cab_asesora,
        json={
            "sucursal_id": central_id,
            "asesor_id": asesora_u["id"],
            "items": [{"equipo_id": eq_central["id"]}],
            "pagos": [
                {"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 100.0},
                {
                    "instrumento_id": insts["Pago móvil Mercantil (Bs)"],
                    "monto_moneda_origen": 7800.0,
                    "referencia": "PM-998877",
                },
            ],
        },
    )
    assert resp_vta.status_code == 201, resp_vta.text
    vta = resp_vta.json()
    assert vta["estado"] == "CUADRADA"
    # RBAC: asesora NO recibe costos ni utilidad
    assert "costo_total_usd" not in vta
    assert "utilidad_real_usd" not in vta
    assert "costo_total_snapshot_usd" not in vta["detalles"][0]

    # RBAC: asesora no puede ver /api/finanzas/tablero -> 403
    assert cliente.get("/api/finanzas/tablero", headers=cab_asesora).status_code == 403

    # 7. Intentar vender el mismo serial ya VENDIDO -> 400
    resp_revender = cliente.post(
        "/api/ventas",
        headers=cab_asesora,
        json={
            "sucursal_id": central_id,
            "items": [{"equipo_id": eq_central["id"]}],
            "pagos": [{"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 200.0}],
        },
    )
    assert resp_revender.status_code == 400

    # 8. Descargar Nota de Entrega PDF válida
    resp_pdf = cliente.get(f"/api/ventas/{vta['id']}/nota-pdf", headers=cab_asesora)
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers["content-type"] == "application/pdf"
    assert resp_pdf.content.startswith(b"%PDF-")


def test_devolucion_comisiones_y_cierre_mensual_bloquea_periodo(cliente: TestClient) -> None:
    cab_dir, _ = login(cliente, "direccion@tekioelectronics.com", "Tekio2026!")
    cab_lider, lider_u = crear_usuario_rol(
        cliente, cab_dir, "Caira Líder", "lider@tekioelectronics.com", "LIDER", 2
    )
    cab_asesora, asesora_u = crear_usuario_rol(
        cliente, cab_dir, "Gabriela Asesora", "gabriela@tekioelectronics.com", "ASESORA", 2
    )
    hoy = obtener_fecha_hoy()

    sucs = {s["nombre"]: s["id"] for s in cliente.get("/api/sucursales", headers=cab_dir).json()}
    central_id = sucs["Tekio central"]
    insts = {
        i["nombre"]: i["id"]
        for i in cliente.get("/api/finanzas/instrumentos", headers=cab_dir).json()
    }

    # Crear 3 equipos LISTO ($1000, $500, $300)
    cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "fecha": hoy.isoformat(),
            "llega_preparada": True,
            "equipos": [
                {"serial": "COM-EQ-1", "modelo": "MacBook", "ubicacion_id": central_id, "costo_compra_usd": 600.0, "precio_promo_usd": 1000.0},
                {"serial": "COM-EQ-2", "modelo": "Dell", "ubicacion_id": central_id, "costo_compra_usd": 300.0, "precio_promo_usd": 500.0},
                {"serial": "COM-EQ-3", "modelo": "HP", "ubicacion_id": central_id, "costo_compra_usd": 150.0, "precio_promo_usd": 300.0},
            ],
        },
    )
    eqs = {
        e["serial"]: e["id"]
        for e in cliente.get("/api/logistica/inventario/equipos", headers=cab_dir).json()
    }

    # Venta 1: Asesora vende $1,000 Promo
    v1 = cliente.post(
        "/api/ventas",
        headers=cab_asesora,
        json={
            "sucursal_id": central_id,
            "asesor_id": asesora_u["id"],
            "items": [{"equipo_id": eqs["COM-EQ-1"]}],
            "pagos": [{"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 1000.0}],
        },
    ).json()

    # Venta 2: Líder vende $500 Promo
    v2 = cliente.post(
        "/api/ventas",
        headers=cab_lider,
        json={
            "sucursal_id": central_id,
            "asesor_id": lider_u["id"],
            "items": [{"equipo_id": eqs["COM-EQ-2"]}],
            "pagos": [{"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 500.0}],
        },
    ).json()

    # Venta 3: Asesora vende $300 y luego se ANULA (no debe sumar comisión)
    v3 = cliente.post(
        "/api/ventas",
        headers=cab_asesora,
        json={
            "sucursal_id": central_id,
            "asesor_id": asesora_u["id"],
            "items": [{"equipo_id": eqs["COM-EQ-3"]}],
            "pagos": [{"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 300.0}],
        },
    ).json()
    cliente.post(f"/api/ventas/{v3['id']}/anular", headers=cab_dir, json={"motivo": "Error de factura"})

    # Verificar comisiones:
    # Asesora: 1% de $1,000 = $10.00
    # Líder: 1% de $500 ($5.00) + 0.5% de $1,000 ($5.00) = $10.00
    com_resp = cliente.get(f"/api/finanzas/comisiones?mes={hoy.month}&anio={hoy.year}", headers=cab_dir).json()
    com_map = {c["usuario_id"]: c for c in com_resp["comisiones"]}
    assert com_map[asesora_u["id"]]["comision_ventas_1_usd"] == 10.0
    assert com_map[lider_u["id"]]["comision_ventas_1_usd"] == 5.0
    assert com_map[lider_u["id"]]["comision_lider_05_usd"] == 5.0
    assert com_map[lider_u["id"]]["total_comision_usd"] == 10.0

    # Devolución (Nota de Crédito) sobre v1 -> reingresa serial COM-EQ-1 a GARANTIA sin modificar v1
    resp_nc = cliente.post(
        "/api/devoluciones",
        headers=cab_dir,
        json={
            "venta_original_id": v1["id"],
            "equipo_id": eqs["COM-EQ-1"],
            "cantidad": 1,
            "motivo": "Falla de fábrica en pantalla",
            "estado_reingreso": "GARANTIA",
        },
    )
    assert resp_nc.status_code == 201
    assert resp_nc.json()["numero_nc"].startswith("NC-")
    eq_reingresado = cliente.get("/api/logistica/inventario/equipos?busqueda=COM-EQ-1", headers=cab_dir).json()[0]
    assert eq_reingresado["estado"] == "GARANTIA"

    # Cierre de mes por DIRECCION -> bloquea nuevas ventas o anulaciones en ese mes (403)
    resp_cierre = cliente.post(
        "/api/finanzas/cierres-mensuales",
        headers=cab_dir,
        json={"anio": hoy.year, "mes": hoy.month},
    )
    assert resp_cierre.status_code == 201

    resp_anular_cerrado = cliente.post(
        f"/api/ventas/{v2['id']}/anular",
        headers=cab_dir,
        json={"motivo": "Intento tras cierre"},
    )
    assert resp_anular_cerrado.status_code == 403


def test_venta_cashea_con_inicial_divisas_aplica_precio_regular_estricto(cliente: TestClient) -> None:
    cab_dir, _ = login(cliente, "direccion@tekioelectronics.com", "Tekio2026!")
    cab_asesora, asesora_u = crear_usuario_rol(
        cliente, cab_dir, "Asesora Cashea", "asesora_cashea@tekioelectronics.com", "ASESORA", 2
    )
    hoy = obtener_fecha_hoy()

    # Tasa del día: BCV = 60, USDT = 72, Recargo = 30% -> $200 Promo = $260 Regular
    cliente.post(
        "/api/tasas",
        headers=cab_dir,
        json={
            "fecha": hoy.isoformat(),
            "tasa_bcv": 60.0,
            "tasa_usdt": 72.0,
            "recargo_porcentaje": 30.0,
        },
    )

    sucs = {s["nombre"]: s["id"] for s in cliente.get("/api/sucursales", headers=cab_dir).json()}
    central_id = sucs["Tekio central"]
    insts = {
        i["nombre"]: i["id"]
        for i in cliente.get("/api/finanzas/instrumentos", headers=cab_dir).json()
    }

    cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "fecha": hoy.isoformat(),
            "llega_preparada": True,
            "equipos": [
                {
                    "serial": "CASHEA-REG-1",
                    "modelo": "Lenovo ThinkPad T14 Gen 2",
                    "ubicacion_id": central_id,
                    "costo_compra_usd": 130.0,
                    "precio_promo_usd": 200.0,
                }
            ],
        },
    )
    eq = cliente.get("/api/logistica/inventario/equipos?busqueda=CASHEA-REG-1", headers=cab_dir).json()[0]

    # 1. Inicial $100 Efectivo divisas + $100 Cashea (= $200 Promo) NO cuadra: faltan $60 USD Regular (3,600 Bs)
    sim_incompleta = cliente.post(
        "/api/ventas/simular",
        headers=cab_asesora,
        json={
            "sucursal_id": central_id,
            "items": [{"equipo_id": eq["id"]}],
            "pagos": [
                {"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 100.0},
                {"instrumento_id": insts["Cashea · financiado"], "monto_moneda_origen": 100.0},
            ],
        },
    ).json()
    assert sim_incompleta["usa_cashea"] is True
    assert sim_incompleta["total_promo_usd"] == 200.0
    assert sim_incompleta["total_regular_usd"] == 260.0
    assert sim_incompleta["cubierto_regular_usd"] == 200.0
    assert sim_incompleta["falta_usd_regular"] == 60.0
    assert sim_incompleta["falta_bs"] == 3600.0
    assert sim_incompleta["cashea_financiado_sugerido_usd"] == 160.0
    assert sim_incompleta["cashea_financiado_sugerido_bs"] == 9600.0
    assert sim_incompleta["estado"] == "CON_SALDO"

    # 2. Registrar con $200 totales debe fallar con 400 (no permite Precio Promo si hay Cashea)
    resp_rechazada = cliente.post(
        "/api/ventas",
        headers=cab_asesora,
        json={
            "sucursal_id": central_id,
            "asesor_id": asesora_u["id"],
            "items": [{"equipo_id": eq["id"]}],
            "pagos": [
                {"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 100.0},
                {"instrumento_id": insts["Cashea · financiado"], "monto_moneda_origen": 100.0},
            ],
        },
    )
    assert resp_rechazada.status_code == 400
    assert "Regular" in resp_rechazada.json()["detail"]

    # 3. Inicial $100 Efectivo divisas + $160 Cashea (= $260 Regular exacto) -> CUADRADA + CxC Cashea $160
    sim_ok = cliente.post(
        "/api/ventas/simular",
        headers=cab_asesora,
        json={
            "sucursal_id": central_id,
            "items": [{"equipo_id": eq["id"]}],
            "pagos": [
                {"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 100.0},
                {"instrumento_id": insts["Cashea · financiado"], "monto_moneda_origen": 160.0},
            ],
        },
    ).json()
    assert sim_ok["estado"] == "CUADRADA"
    assert sim_ok["falta_usd_regular"] == 0.0
    assert sim_ok["falta_bs"] == 0.0

    resp_ok = cliente.post(
        "/api/ventas",
        headers=cab_asesora,
        json={
            "sucursal_id": central_id,
            "asesor_id": asesora_u["id"],
            "items": [{"equipo_id": eq["id"]}],
            "pagos": [
                {"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 100.0},
                {"instrumento_id": insts["Cashea · financiado"], "monto_moneda_origen": 160.0},
            ],
        },
    )
    assert resp_ok.status_code == 201, resp_ok.text
    vta = resp_ok.json()
    assert vta["estado"] == "CUADRADA"
    assert vta["total_regular_usd"] == 260.0

    cxc_lista = cliente.get("/api/finanzas/cuentas-por-cobrar?tipo=CASHEA", headers=cab_dir).json()
    cxc_cashea = [c for c in cxc_lista if c["venta_id"] == vta["id"]]
    assert len(cxc_cashea) == 1
    assert cxc_cashea[0]["monto_original_usd"] == 160.0
    assert cxc_cashea[0]["saldo_pendiente_usd"] == 160.0
