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
    central_id = sucs["Tekio Central"]
    bodega_id = sucs["Depósito / Tekio Support (Taller)"]
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
            "sin_cargador": True,
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
            "sin_cargador": True,
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
            "sin_cargador": True,
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
            "sin_cargador": True,
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
    central_id = sucs["Tekio Central"]
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
            "sin_cargador": True,
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
            "sin_cargador": True,
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
            "sin_cargador": True,
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
    central_id = sucs["Tekio Central"]
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
            "cashea_numero_orden": "CSH-FASE4-001",
            "sin_cargador": True,
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
            "cashea_numero_orden": "CSH-FASE4-001",
            "sin_cargador": True,
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


def test_servicio_tecnico_combinado_con_repuesto_tecnico_obligatorio_y_comisiones_promo(
    cliente: TestClient,
) -> None:
    cab_dir, _ = login(cliente, "direccion@tekioelectronics.com", "Tekio2026!")
    cab_asesora, _ = crear_usuario_rol(
        cliente, cab_dir, "Asesora ST", "asesora_st@tekioelectronics.com", "ASESORA", 2
    )
    cab_lider, lider_u = crear_usuario_rol(
        cliente, cab_dir, "Líder ST", "lider_st@tekioelectronics.com", "LIDER", 2
    )
    cab_tecnico, tecnico_u = crear_usuario_rol(
        cliente, cab_dir, "Técnico Luis", "tecnico_st@tekioelectronics.com", "TECNICO", 2
    )
    hoy = obtener_fecha_hoy()

    # 1. Endpoint GET /api/usuarios/operativos accesible para ASESORA
    resp_ops = cliente.get("/api/usuarios/operativos", headers=cab_asesora)
    assert resp_ops.status_code == 200, resp_ops.text
    ops = resp_ops.json()
    assert any(u["id"] == tecnico_u["id"] and u["rol"] == "TECNICO" for u in ops)
    assert any(u["id"] == lider_u["id"] and u["es_lider"] is True for u in ops)
    assert set(ops[0].keys()) == {"id", "nombre", "rol", "es_lider", "sucursal_id", "modalidad", "tiene_acceso"}

    # 2. Tasa del día: BCV = 60, USDT = 72, Recargo = 30%
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
    central_id = sucs["Tekio Central"]
    insts = {
        i["nombre"]: i["id"]
        for i in cliente.get("/api/finanzas/instrumentos", headers=cab_dir).json()
    }

    # 3. Crear servicio técnico (SER-REPARACION) y componente (BAT-33YDH) en catálogo
    resp_srv = cliente.post(
        "/api/catalogo",
        headers=cab_dir,
        json={
            "sku": "SER-REPARACION",
            "descripcion": "Reparación de hardware / placa",
            "tipo": "SERVICIO",
            "categoria": "Taller",
            "precio_promo_usd": 25.0,
        },
    )
    assert resp_srv.status_code == 201, resp_srv.text
    srv_id = resp_srv.json()["id"]

    resp_bat = cliente.post(
        "/api/catalogo",
        headers=cab_dir,
        json={
            "sku": "BAT-33YDH",
            "descripcion": "Batería Dell 33YDH",
            "tipo": "COMPONENTE",
            "categoria": "Baterías",
            "precio_promo_usd": 60.0,
            "costo_referencia_usd": 30.0,
        },
    )
    assert resp_bat.status_code == 201, resp_bat.text
    bat_id = resp_bat.json()["id"]

    # Cargar stock de 2 baterías en Tekio central vía compra nacional
    resp_cmp = cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "fecha": hoy.isoformat(),
            "llega_preparada": True,
            "componentes": [
                {
                    "articulo_id": bat_id,
                    "ubicacion_id": central_id,
                    "cantidad": 2,
                    "costo_unitario_usd": 30.0,
                }
            ],
        },
    )
    assert resp_cmp.status_code == 201, resp_cmp.text

    # 4. Intentar vender servicio técnico SIN tecnico_id -> 400
    resp_sin_tec = cliente.post(
        "/api/ventas",
        headers=cab_asesora,
        json={
            "sucursal_id": central_id,
            "asesor_id": tecnico_u["id"],
            "items": [
                {
                    "articulo_id": srv_id,
                    "cantidad": 1,
                    "precio_pactado_usd": 40.0,
                    "descripcion_servicio": "Cambio de pin de carga",
                }
            ],
            "pagos": [{"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 40.0}],
        },
    )
    assert resp_sin_tec.status_code == 400
    assert "Técnico" in resp_sin_tec.json()["detail"]

    # 5. Venta combinada: $40 Promo mano de obra + $60 Promo batería = $100 Promo / $130 Regular (pagada en Bs: 7,800 Bs)
    resp_ok = cliente.post(
        "/api/ventas",
        headers=cab_asesora,
        json={
            "sucursal_id": central_id,
            "asesor_id": tecnico_u["id"],
            "tecnico_id": tecnico_u["id"],
            "items": [
                {
                    "articulo_id": srv_id,
                    "cantidad": 1,
                    "precio_pactado_usd": 40.0,
                    "descripcion_servicio": "Cambio de pin de carga y mantenimiento preventivo",
                },
                {
                    "articulo_id": bat_id,
                    "cantidad": 1,
                },
            ],
            "pagos": [
                {
                    "instrumento_id": insts["Pago móvil Mercantil (Bs)"],
                    "monto_moneda_origen": 7800.0,
                    "referencia": "PM-ST-01",
                }
            ],
        },
    )
    assert resp_ok.status_code == 201, resp_ok.text
    vta = resp_ok.json()
    assert vta["estado"] == "CUADRADA"
    assert vta["total_promo_usd"] == 100.0
    assert vta["total_regular_usd"] == 130.0
    assert vta["tecnico"] == "Técnico Luis"
    det_srv = next(d for d in vta["detalles"] if d["es_servicio_tecnico"])
    assert det_srv["descripcion_servicio"] == "Cambio de pin de carga y mantenimiento preventivo"

    # PDF se genera sin errores con descripcion_servicio
    resp_pdf = cliente.get(f"/api/ventas/{vta['id']}/nota-pdf", headers=cab_asesora)
    assert resp_pdf.status_code == 200
    assert resp_pdf.content.startswith(b"%PDF-")

    # Stock de BAT-33YDH bajó de 2 a 1
    kardex = cliente.get(
        f"/api/logistica/inventario/kardex?sucursal_id={central_id}", headers=cab_dir
    ).json()
    fila_bat = next(k for k in kardex["saldos"] if k["articulo_id"] == bat_id)
    assert fila_bat["stock_actual"] == 1

    # 6. Comisiones estrictamente sobre Precio Promo USD (NO sobre $130 Regular):
    # - Técnico Luis: 50% de $40 servicio ($20.00) + 1% de $60 batería como asesor ($0.60) = $20.60
    # - Líder ST: 0.5% de $60 batería ($0.30) — excluye la línea de servicio técnico
    com = cliente.get(
        f"/api/finanzas/comisiones?mes={hoy.month}&anio={hoy.year}", headers=cab_dir
    ).json()
    com_map = {c["usuario_id"]: c for c in com["comisiones"]}
    assert com_map[tecnico_u["id"]]["comision_servicios_50_usd"] == 20.0
    assert com_map[tecnico_u["id"]]["comision_ventas_1_usd"] == 0.6
    assert com_map[tecnico_u["id"]]["total_comision_usd"] == 20.6
    assert com_map[lider_u["id"]]["comision_lider_05_usd"] == 0.3

    # 7. Resumen del técnico refleja 50% servicio POS + 1% ventas como asesor
    resumen_tec = cliente.get(
        f"/api/taller/resumen-tecnico?mes={hoy.month}&anio={hoy.year}", headers=cab_tecnico
    ).json()
    assert resumen_tec["comision_servicios_usd"] == 20.0
    assert resumen_tec["comision_asesor_usd"] == 0.6
    assert resumen_tec["total_mes_usd"] == 20.6


def test_obsequio_imputa_costo_al_equipo_descuenta_stock_y_rbac(cliente: TestClient) -> None:
    cab_dir, _ = login(cliente, "direccion@tekioelectronics.com", "Tekio2026!")
    cab_asesora, asesora_u = crear_usuario_rol(
        cliente, cab_dir, "Asesora Obsequio", "asesora_obs@tekioelectronics.com", "ASESORA", 2
    )
    hoy = obtener_fecha_hoy()

    sucs = {s["nombre"]: s["id"] for s in cliente.get("/api/sucursales", headers=cab_dir).json()}
    central_id = sucs["Tekio Central"]
    insts = {
        i["nombre"]: i["id"]
        for i in cliente.get("/api/finanzas/instrumentos", headers=cab_dir).json()
    }

    # Crear cargador ($35 Promo, costo $18) e ingresar 3 unidades + 1 equipo ($350 Promo, costo $200)
    resp_carg = cliente.post(
        "/api/catalogo",
        headers=cab_dir,
        json={
            "sku": "CARG-65W-OBS",
            "descripcion": "Cargador USB-C 65W",
            "tipo": "ACCESORIO",
            "categoria": "Cargadores",
            "precio_promo_usd": 35.0,
            "costo_referencia_usd": 18.0,
        },
    )
    assert resp_carg.status_code == 201, resp_carg.text
    carg_id = resp_carg.json()["id"]

    resp_cmp = cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "fecha": hoy.isoformat(),
            "llega_preparada": True,
            "equipos": [
                {
                    "serial": "OBS-EQ-1",
                    "modelo": "Dell Latitude 7420",
                    "ubicacion_id": central_id,
                    "costo_compra_usd": 200.0,
                    "precio_promo_usd": 350.0,
                }
            ],
            "componentes": [
                {
                    "articulo_id": carg_id,
                    "ubicacion_id": central_id,
                    "cantidad": 3,
                    "costo_unitario_usd": 18.0,
                }
            ],
        },
    )
    assert resp_cmp.status_code == 201, resp_cmp.text
    eq = cliente.get("/api/logistica/inventario/equipos?busqueda=OBS-EQ-1", headers=cab_dir).json()[0]

    # Venta con descuento ($350 -> $320) + cargador como OBSEQUIO ($0.00)
    resp_vta = cliente.post(
        "/api/ventas",
        headers=cab_asesora,
        json={
            "sucursal_id": central_id,
            "asesor_id": asesora_u["id"],
            "sin_cargador": True,
            "items": [
                {"equipo_id": eq["id"], "precio_pactado_usd": 320.0},
                {"articulo_id": carg_id, "cantidad": 1, "precio_pactado_usd": 0.0},
            ],
            "pagos": [{"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 320.0}],
        },
    )
    assert resp_vta.status_code == 201, resp_vta.text
    vta_asesora = resp_vta.json()
    assert vta_asesora["estado"] == "CUADRADA"
    assert vta_asesora["total_promo_usd"] == 320.0
    # RBAC: asesora NO ve costos
    assert "costo_total_usd" not in vta_asesora
    assert "utilidad_real_usd" not in vta_asesora
    assert all("costo_total_snapshot_usd" not in d for d in vta_asesora["detalles"])

    # Stock del cargador bajó de 3 a 2
    kardex = cliente.get(
        f"/api/logistica/inventario/kardex?sucursal_id={central_id}", headers=cab_dir
    ).json()
    fila_carg = next(k for k in kardex["saldos"] if k["articulo_id"] == carg_id)
    assert fila_carg["stock_actual"] == 2

    # Vista de DIRECCION: costo del cargador ($18) sumado al equipo ($200 -> $218), $0 en cargador, utilidad = $102
    ventas_dir = cliente.get("/api/ventas", headers=cab_dir).json()
    vta_dir = next(v for v in ventas_dir if v["id"] == vta_asesora["id"])
    det_eq = next(d for d in vta_dir["detalles"] if d["equipo_id"] == eq["id"])
    det_carg = next(d for d in vta_dir["detalles"] if d["articulo_id"] == carg_id)
    assert det_eq["costo_total_snapshot_usd"] == 218.0
    assert det_carg["costo_total_snapshot_usd"] == 0.0
    assert vta_dir["costo_total_usd"] == 218.0
    assert vta_dir["utilidad_real_usd"] == 102.0

    # Comisión de asesora sobre $320 pactados ($3.20; obsequio $0 genera $0)
    com = cliente.get(
        f"/api/finanzas/comisiones?mes={hoy.month}&anio={hoy.year}", headers=cab_dir
    ).json()
    com_asesora = next(c for c in com["comisiones"] if c["usuario_id"] == asesora_u["id"])
    assert com_asesora["ventas_promo_usd"] == 320.0
    assert com_asesora["comision_ventas_1_usd"] == 3.2

    # Nota PDF válida con políticas de garantía (180 días), obsequio y líneas de firma
    resp_pdf = cliente.get(f"/api/ventas/{vta_asesora['id']}/nota-pdf", headers=cab_asesora)
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers["content-type"] == "application/pdf"
    assert resp_pdf.content.startswith(b"%PDF-")
    import base64, re, zlib

    texto_pdf = resp_pdf.content.decode("latin-1", errors="ignore")
    for bloque in re.findall(rb"stream\r?\n(.*?)\s*endstream", resp_pdf.content, flags=re.S):
        crudo = bloque.strip()
        if crudo.endswith(b"~>"):
            crudo = base64.a85decode(crudo, adobe=True)
        try:
            texto_pdf += zlib.decompress(crudo).decode("latin-1", errors="ignore")
        except zlib.error:
            pass
    texto_pdf = texto_pdf.replace("\\(", "(").replace("\\)", ")")
    assert "J-50637518-4" in texto_pdf
    assert "180" in texto_pdf
    assert "OBSEQUIO" in texto_pdf
    assert "Entregado por (Tekio Electronics)" in texto_pdf
    assert "Firma del Cliente" in texto_pdf


def test_lider_multitienda_comision_en_multiples_sucursales(cliente: TestClient) -> None:
    cab_dir, _ = login(cliente, "direccion@tekioelectronics.com", "Tekio2026!")
    sucs = {s["nombre"]: s["id"] for s in cliente.get("/api/sucursales", headers=cab_dir).json()}
    central_id = sucs["Tekio Central"]
    gran_bazar_id = sucs["Tekio Gran Bazar"]

    _, lider_u = crear_usuario_rol(
        cliente, cab_dir, "Líder Multi", "lider_multi@tekioelectronics.com", "LIDER", central_id
    )
    _, asesora_c = crear_usuario_rol(
        cliente, cab_dir, "Asesora Central", "asesora_c@tekioelectronics.com", "ASESORA", central_id
    )
    _, asesora_gb = crear_usuario_rol(
        cliente, cab_dir, "Asesora GB", "asesora_gb@tekioelectronics.com", "ASESORA", gran_bazar_id
    )
    hoy = obtener_fecha_hoy()
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
                {"serial": "MULTI-1", "modelo": "HP 1", "ubicacion_id": central_id, "costo_compra_usd": 300.0, "precio_promo_usd": 500.0},
                {"serial": "MULTI-2", "modelo": "HP 2", "ubicacion_id": central_id, "costo_compra_usd": 250.0, "precio_promo_usd": 400.0},
                {"serial": "MULTI-3", "modelo": "HP 3", "ubicacion_id": gran_bazar_id, "costo_compra_usd": 350.0, "precio_promo_usd": 600.0},
            ],
        },
    )
    eqs = {
        e["serial"]: e["id"]
        for e in cliente.get("/api/logistica/inventario/equipos", headers=cab_dir).json()
    }

    # Venta 1: Líder $500 en Tekio central -> 1% = $5.00
    assert cliente.post(
        "/api/ventas",
        headers=cab_dir,
        json={
            "sucursal_id": central_id,
            "asesor_id": lider_u["id"],
            "sin_cargador": True,
            "items": [{"equipo_id": eqs["MULTI-1"]}],
            "pagos": [{"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 500.0}],
        },
    ).status_code == 201

    # Venta 2: Asesora Central $400 en Tekio central -> 0.5% al Líder = $2.00
    assert cliente.post(
        "/api/ventas",
        headers=cab_dir,
        json={
            "sucursal_id": central_id,
            "asesor_id": asesora_c["id"],
            "sin_cargador": True,
            "items": [{"equipo_id": eqs["MULTI-2"]}],
            "pagos": [{"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 400.0}],
        },
    ).status_code == 201

    # Venta 3: Asesora Gran Bazar $600 en Gran Bazar -> 0.5% al Líder = $3.00
    assert cliente.post(
        "/api/ventas",
        headers=cab_dir,
        json={
            "sucursal_id": gran_bazar_id,
            "asesor_id": asesora_gb["id"],
            "sin_cargador": True,
            "items": [{"equipo_id": eqs["MULTI-3"]}],
            "pagos": [{"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 600.0}],
        },
    ).status_code == 201

    # Comisiones: Líder suma 1% propio ($5.00) + 0.5% de otras asesoras en AMBAS tiendas ($2.00 + $3.00 = $5.00) = $10.00
    com = cliente.get(
        f"/api/finanzas/comisiones?mes={hoy.month}&anio={hoy.year}", headers=cab_dir
    ).json()
    com_map = {c["usuario_id"]: c for c in com["comisiones"]}
    assert com_map[lider_u["id"]]["comision_ventas_1_usd"] == 5.0
    assert com_map[lider_u["id"]]["comision_lider_05_usd"] == 5.0
    assert com_map[lider_u["id"]]["total_comision_usd"] == 10.0
    assert com_map[asesora_c["id"]]["comision_ventas_1_usd"] == 4.0
    assert com_map[asesora_gb["id"]]["comision_ventas_1_usd"] == 6.0


def test_creacion_rapida_clientes_natural_juridico_duplicado_409_y_pdf(
    cliente: TestClient,
) -> None:
    cab_dir, _ = login(cliente, "direccion@tekioelectronics.com", "Tekio2026!")
    cab_asesora, asesora_u = crear_usuario_rol(
        cliente, cab_dir, "Asesora Clientes", "asesora_cli@tekioelectronics.com", "ASESORA", 2
    )
    hoy = obtener_fecha_hoy()

    # 1. Crear cliente Persona Natural (V-) con rol ASESORA -> 201
    resp_nat = cliente.post(
        "/api/clientes",
        headers=cab_asesora,
        json={
            "tipo_persona": "NATURAL",
            "tipo_documento": "V",
            "documento": "V-24 567 890",
            "nombre": "María Alejandra Pérez",
            "telefono": "0414-5551234",
            "direccion": "Av. Bolívar Norte, Valencia",
        },
    )
    assert resp_nat.status_code == 201, resp_nat.text
    cli_nat = resp_nat.json()
    assert cli_nat["tipo_persona"] == "NATURAL"
    assert cli_nat["tipo_documento"] == "V"
    assert cli_nat["documento"] == "24567890"
    assert cli_nat["rif_cedula"] == "V-24567890"
    assert cli_nat["direccion"] == "Av. Bolívar Norte, Valencia"

    # 2. Intentar duplicar el mismo documento V-24567890 -> 409 Conflict con el nombre del cliente
    resp_dup = cliente.post(
        "/api/clientes",
        headers=cab_asesora,
        json={
            "tipo_persona": "NATURAL",
            "tipo_documento": "V",
            "documento": "24567890",
            "nombre": "Otra Persona",
        },
    )
    assert resp_dup.status_code == 409
    assert "María Alejandra Pérez" in resp_dup.json()["detail"]

    # 3. Crear cliente Persona Jurídica (J-) con rol ASESORA -> 201
    resp_jur = cliente.post(
        "/api/terceros",
        headers=cab_asesora,
        json={
            "tipo_persona": "JURIDICO",
            "tipo_documento": "J",
            "documento": "501234567",
            "nombre": "Inversiones Carabobo, C.A.",
            "telefono": "0241-8229900",
            "direccion": "Zona Industrial Norte, Galpón 4, Valencia",
        },
    )
    assert resp_jur.status_code == 201, resp_jur.text
    cli_jur = resp_jur.json()
    assert cli_jur["tipo_persona"] == "JURIDICO"
    assert cli_jur["rif_cedula"] == "J-501234567"

    # 4. Registrar venta con el cliente Jurídico y verificar que el PDF incluye documento, teléfono y dirección
    sucs = {s["nombre"]: s["id"] for s in cliente.get("/api/sucursales", headers=cab_dir).json()}
    central_id = sucs["Tekio Central"]
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
                    "serial": "CLI-PDF-1",
                    "modelo": "HP EliteBook 840",
                    "ubicacion_id": central_id,
                    "costo_compra_usd": 200.0,
                    "precio_promo_usd": 350.0,
                }
            ],
        },
    )
    eq = cliente.get("/api/logistica/inventario/equipos?busqueda=CLI-PDF-1", headers=cab_dir).json()[0]

    resp_vta = cliente.post(
        "/api/ventas",
        headers=cab_asesora,
        json={
            "sucursal_id": central_id,
            "cliente_id": cli_jur["id"],
            "asesor_id": asesora_u["id"],
            "sin_cargador": True,
            "items": [{"equipo_id": eq["id"]}],
            "pagos": [{"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 350.0}],
        },
    )
    assert resp_vta.status_code == 201, resp_vta.text
    vta = resp_vta.json()
    assert vta["cliente_rif"] == "J-501234567"
    assert vta["cliente_telefono"] == "0241-8229900"
    assert vta["cliente_direccion"] == "Zona Industrial Norte, Galpón 4, Valencia"

    resp_pdf = cliente.get(f"/api/ventas/{vta['id']}/nota-pdf", headers=cab_asesora)
    assert resp_pdf.status_code == 200
    import base64, re, zlib

    texto_pdf = resp_pdf.content.decode("latin-1", errors="ignore")
    for bloque in re.findall(rb"stream\r?\n(.*?)\s*endstream", resp_pdf.content, flags=re.S):
        crudo = bloque.strip()
        if crudo.endswith(b"~>"):
            crudo = base64.a85decode(crudo, adobe=True)
        try:
            texto_pdf += zlib.decompress(crudo).decode("latin-1", errors="ignore")
        except zlib.error:
            pass
    texto_pdf = texto_pdf.replace("\\(", "(").replace("\\)", ")")
    assert "J-501234567" in texto_pdf
    assert "0241-8229900" in texto_pdf
    assert "Zona Industrial Norte" in texto_pdf


def _extraer_texto_pdf(pdf_bytes: bytes) -> str:
    import base64
    import re
    import zlib

    texto = pdf_bytes.decode("latin-1", errors="ignore")
    for bloque in re.findall(rb"stream\r?\n(.*?)\s*endstream", pdf_bytes, flags=re.S):
        crudo = bloque.strip()
        if crudo.endswith(b"~>"):
            crudo = base64.a85decode(crudo, adobe=True)
        try:
            texto += zlib.decompress(crudo).decode("latin-1", errors="ignore")
        except zlib.error:
            pass
    return texto.replace("\\(", "(").replace("\\)", ")")


def test_pdf_sin_etiquetas_internas_monto_total_regular_bs_y_envio_nacional(
    cliente: TestClient,
) -> None:
    cab_dir, _ = login(cliente, "direccion@tekioelectronics.com", "Tekio2026!")
    cab_asesora, asesora_u = crear_usuario_rol(
        cliente, cab_dir, "Asesora PDF", "asesora_pdf@tekioelectronics.com", "ASESORA", 2
    )
    hoy = obtener_fecha_hoy()

    # Tasa BCV = 60, USDT = 72, Recargo = 30% -> $200 Promo / $260 Regular (15,600 Bs)
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
    central_id = sucs["Tekio Central"]
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
                    "serial": "PDF-PROMO-1",
                    "modelo": "Dell Latitude 5420",
                    "ubicacion_id": central_id,
                    "costo_compra_usd": 120.0,
                    "precio_promo_usd": 200.0,
                },
                {
                    "serial": "PDF-REG-1",
                    "modelo": "Lenovo ThinkPad T14",
                    "ubicacion_id": central_id,
                    "costo_compra_usd": 120.0,
                    "precio_promo_usd": 200.0,
                },
            ],
        },
    )
    eq_promo = cliente.get("/api/logistica/inventario/equipos?busqueda=PDF-PROMO-1", headers=cab_dir).json()[0]
    eq_reg = cliente.get("/api/logistica/inventario/equipos?busqueda=PDF-REG-1", headers=cab_dir).json()[0]

    # 1. Venta Promo (divisas) -> PDF sin "Precio Promo", sin "Precio Regular", sin "CUADRADA"
    vta_promo = cliente.post(
        "/api/ventas",
        headers=cab_asesora,
        json={
            "sucursal_id": central_id,
            "asesor_id": asesora_u["id"],
            "canal_visita": "Instagram",
            "sin_cargador": True,
            "items": [{"equipo_id": eq_promo["id"]}],
            "pagos": [{"instrumento_id": insts["Efectivo divisas"], "monto_moneda_origen": 200.0}],
        },
    ).json()
    pdf_promo = _extraer_texto_pdf(
        cliente.get(f"/api/ventas/{vta_promo['id']}/nota-pdf", headers=cab_asesora).content
    )
    assert "Precio Unitario" in pdf_promo
    assert "Subtotal" in pdf_promo
    assert "Monto Total: $200.00 USD" in pdf_promo
    assert "PRUEBA DE FUNCIONALIDAD DEL EQUIPO" in pdf_promo
    assert "[X] Instagram" in pdf_promo
    assert "Firma del Cliente" in pdf_promo
    assert "Precio Promo" not in pdf_promo
    assert "Precio Regular" not in pdf_promo
    assert "CUADRADA" not in pdf_promo

    # Confirmar estilo justificado (TA_JUSTIFY) y marca de agua presente en el PDF
    from reportlab.lib.enums import TA_JUSTIFY
    from app.servicios.pdf_nota import ESTILO_GARANTIA_JUSTIFICADO

    assert ESTILO_GARANTIA_JUSTIFICADO.alignment == TA_JUSTIFY
    assert "/Subtype /Image" in pdf_promo

    # 2. Venta Regular (Bs) + ENVIO nacional -> guarda empresa_envio y direccion_oficina, PDF muestra USD y Bs
    resp_envio = cliente.post(
        "/api/ventas",
        headers=cab_asesora,
        json={
            "sucursal_id": central_id,
            "asesor_id": asesora_u["id"],
            "entrega": "ENVIO",
            "datos_entrega": {
                "destinatario": "Carlos Mendoza",
                "cedula": "V-18765432",
                "telefono": "0412-9998877",
                "empresa_envio": "MRW",
                "estado_ciudad": "Caracas / Chacao",
                "agencia_oficina": "Agencia Chacao 0104",
                "direccion_oficina": "Av. Francisco de Miranda, Edif. Centro Plaza",
                "modalidad": "Cobro en destino",
            },
            "sin_cargador": True,
            "items": [{"equipo_id": eq_reg["id"]}],
            "pagos": [
                {
                    "instrumento_id": insts["Pago móvil Mercantil (Bs)"],
                    "monto_moneda_origen": 15600.0,
                    "referencia": "PM-ENV-01",
                }
            ],
        },
    )
    assert resp_envio.status_code == 201, resp_envio.text
    vta_reg = resp_envio.json()
    assert vta_reg["datos_entrega"]["empresa_envio"] == "MRW"
    assert (
        vta_reg["datos_entrega"]["direccion_oficina"]
        == "Av. Francisco de Miranda, Edif. Centro Plaza"
    )

    pdf_reg = _extraer_texto_pdf(
        cliente.get(f"/api/ventas/{vta_reg['id']}/nota-pdf", headers=cab_asesora).content
    )
    assert "Monto Total: $260.00 USD" in pdf_reg
    assert "Bs. 15,600.00" in pdf_reg
    assert "MRW" in pdf_reg
    assert "Av. Francisco de Miranda, Edif. Centro Plaza" in pdf_reg
    assert "Precio Promo" not in pdf_reg
    assert "Precio Regular" not in pdf_reg
    assert "CUADRADA" not in pdf_reg
