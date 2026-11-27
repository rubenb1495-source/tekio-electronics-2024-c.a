from __future__ import annotations

import io
from datetime import date

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.base_datos import Base, obtener_bd
from app.main import app
from app.semilla import ejecutar_semilla


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
    sucursal_id: int = 1,
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


def test_prorrateo_flete_y_doble_verificacion_en_guia(cliente: TestClient) -> None:
    cab_dir, dir_user = login(cliente, "direccion@tekioelectronics.com", "Tekio2026!")
    cab_log, log_user = crear_usuario_rol(
        cliente, cab_dir, "Luis Logística", "logistica@tekioelectronics.com", "LOGISTICA", 1
    )

    # 1. Crear compra de importación con 2 equipos de $100 y $300
    resp_cmp = cliente.post(
        "/api/logistica/compras",
        headers=cab_log,
        json={
            "origen": "IMPORTACION",
            "fecha": date.today().isoformat(),
            "factura_orden": "EBAY-001",
            "monto_mercancia_usd": 400.0,
            "llega_preparada": False,
            "equipos": [
                {
                    "serial": "  sn 100 ",
                    "modelo": "Dell Latitude 5420",
                    "costo_compra_usd": 100.0,
                    "precio_promo_usd": 250.0,
                },
                {
                    "serial": "sn300",
                    "modelo": "MacBook Pro M2",
                    "costo_compra_usd": 300.0,
                    "precio_promo_usd": 600.0,
                },
            ],
        },
    )
    assert resp_cmp.status_code == 201, resp_cmp.text
    compra_id = resp_cmp.json()["id"]

    # 2. Crear guía con $100 de flete
    resp_guia = cliente.post(
        "/api/logistica/guias",
        headers=cab_log,
        json={
            "numero_guia": "MIA-9001",
            "casillero": "Liberty Express",
            "modalidad": "AEREO",
            "flete_usd": 100.0,
            "otros_gastos_usd": 0.0,
            "compras_ids": [compra_id],
        },
    )
    assert resp_guia.status_code == 201, resp_guia.text
    guia_id = resp_guia.json()["id"]

    # 3. Doble control: intentar recibir con el mismo usuario como verificador -> 400
    resp_mismo = cliente.post(
        f"/api/logistica/guias/{guia_id}/recibir",
        headers=cab_log,
        json={
            "fecha_llegada_real": date.today().isoformat(),
            "verificado_por_id": log_user["id"],
            "seriales_recibidos": ["SN100", "SN300"],
        },
    )
    assert resp_mismo.status_code == 400

    # 4. Recibir con segundo usuario verificador (Dirección) -> flete prorrateado $25 y $75
    resp_ok = cliente.post(
        f"/api/logistica/guias/{guia_id}/recibir",
        headers=cab_log,
        json={
            "fecha_llegada_real": date.today().isoformat(),
            "verificado_por_id": dir_user["id"],
            "seriales_recibidos": ["SN100", "SN300"],
        },
    )
    assert resp_ok.status_code == 200, resp_ok.text
    prorrateo = {item["serial"]: item["costo_flete_usd"] for item in resp_ok.json()["prorrateo"]}
    assert prorrateo["SN100"] == 25.0
    assert prorrateo["SN300"] == 75.0


def test_validar_archivo_excel_bloquea_serial_duplicado(cliente: TestClient) -> None:
    cab_dir, _ = login(cliente, "direccion@tekioelectronics.com", "Tekio2026!")

    # Crear equipo previo en inventario
    cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "fecha": date.today().isoformat(),
            "equipos": [
                {"serial": "DUP-001", "modelo": "HP ProBook", "costo_compra_usd": 200.0}
            ],
        },
    )

    # Construir .xlsx en memoria con 1 fila válida y 1 fila con serial duplicado + costo faltante
    wb = Workbook()
    ws = wb.active
    ws.append(["serial", "modelo", "costo_compra_usd", "precio_promo_usd"])
    ws.append(["NUEVO-001", "Lenovo ThinkPad", 180, 320])
    ws.append(["dup-001", "HP Duplicado", "", 300])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    resp = cliente.post(
        "/api/logistica/compras/validar-archivo",
        headers=cab_dir,
        files={
            "archivo": (
                "carga_test.xlsx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert resp.status_code == 200, resp.text
    datos = resp.json()
    assert datos["puede_confirmar"] is False
    assert datos["filas_validas"] == 1
    assert datos["filas_con_error"] == 1
    fila_error = [f for f in datos["filas"] if not f["valida"]][0]
    assert fila_error["fila"] == 3
    assert any("DUP-001" in e for e in fila_error["errores"])


def test_traslado_en_dos_pasos_bloqueo_y_confirmacion(cliente: TestClient) -> None:
    cab_dir, _ = login(cliente, "direccion@tekioelectronics.com", "Tekio2026!")

    # Obtener IDs de Bodega y Tekio central
    sucs = {s["nombre"]: s["id"] for s in cliente.get("/api/sucursales", headers=cab_dir).json()}
    bodega_id = sucs["Depósito / Tekio Support (Taller)"]
    central_id = sucs["Tekio Central"]

    # Crear equipo LISTO en Bodega
    cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "fecha": date.today().isoformat(),
            "llega_preparada": True,
            "equipos": [
                {
                    "serial": "TRS-EQ-1",
                    "modelo": "Dell XPS 13",
                    "ubicacion_id": bodega_id,
                    "costo_compra_usd": 400.0,
                    "precio_promo_usd": 650.0,
                }
            ],
        },
    )
    eq = cliente.get("/api/logistica/inventario/equipos?busqueda=TRS-EQ-1", headers=cab_dir).json()[0]
    assert eq["ubicacion_id"] == bodega_id
    assert eq["estado"] == "LISTO"

    # Paso 1: Crear traslado de Bodega -> Tekio central
    resp_trs = cliente.post(
        "/api/logistica/traslados",
        headers=cab_dir,
        json={
            "origen_id": bodega_id,
            "destino_id": central_id,
            "equipos_ids": [eq["id"]],
            "nota": "Envío matutino",
        },
    )
    assert resp_trs.status_code == 201, resp_trs.text
    trs_id = resp_trs.json()["id"]

    # Verificar que mientras está EN_TRANSITO sigue sin aparecer en Tekio central y estado = EN_TRANSITO
    eq_transito = cliente.get("/api/logistica/inventario/equipos?busqueda=TRS-EQ-1", headers=cab_dir).json()[0]
    assert eq_transito["estado"] == "EN_TRANSITO"
    assert eq_transito["ubicacion_id"] == bodega_id

    # Paso 2: Confirmar recepción en destino
    resp_conf = cliente.post(
        f"/api/logistica/traslados/{trs_id}/confirmar",
        headers=cab_dir,
        json={"nota_recepcion": "Recibido conforme"},
    )
    assert resp_conf.status_code == 200, resp_conf.text

    eq_final = cliente.get("/api/logistica/inventario/equipos?busqueda=TRS-EQ-1", headers=cab_dir).json()[0]
    assert eq_final["ubicacion_id"] == central_id
    assert eq_final["estado"] == "LISTO"


def test_ajuste_pendiente_solo_aprobable_por_direccion_y_rbac_oculta_costos(cliente: TestClient) -> None:
    cab_dir, _ = login(cliente, "direccion@tekioelectronics.com", "Tekio2026!")
    cab_log, _ = crear_usuario_rol(
        cliente, cab_dir, "Logística", "log2@tekioelectronics.com", "LOGISTICA", 1
    )
    cab_asesora, _ = crear_usuario_rol(
        cliente, cab_dir, "Asesora", "asesora2@tekioelectronics.com", "ASESORA", 2
    )
    cab_tecnico, _ = crear_usuario_rol(
        cliente, cab_dir, "Técnico", "tecnico2@tekioelectronics.com", "TECNICO", 1
    )

    sucs = {s["nombre"]: s["id"] for s in cliente.get("/api/sucursales", headers=cab_dir).json()}
    bodega_id = sucs["Depósito / Tekio Support (Taller)"]

    # Crear equipo
    cliente.post(
        "/api/logistica/compras",
        headers=cab_log,
        json={
            "origen": "NACIONAL",
            "fecha": date.today().isoformat(),
            "equipos": [
                {
                    "serial": "BAJA-001",
                    "modelo": "Acer Aspire",
                    "ubicacion_id": bodega_id,
                    "costo_compra_usd": 150.0,
                    "precio_promo_usd": 290.0,
                }
            ],
        },
    )
    eq = cliente.get("/api/logistica/inventario/equipos?busqueda=BAJA-001", headers=cab_dir).json()[0]

    # RBAC: ASESORA y TECNICO no deben recibir ningún campo costo_* en inventario ni trazabilidad
    for cab in (cab_asesora, cab_tecnico):
        inv_item = cliente.get("/api/logistica/inventario/equipos?busqueda=BAJA-001", headers=cab).json()[0]
        assert "costo_compra_usd" not in inv_item
        assert "costo_flete_usd" not in inv_item
        assert "costo_taller_usd" not in inv_item
        assert "costo_total_usd" not in inv_item

        traz = cliente.get("/api/logistica/trazabilidad/BAJA-001", headers=cab).json()
        assert "costo_compra_usd" not in traz["equipo"]
        assert "costo_flete_usd" not in traz["equipo"]
        for ev in traz["linea_tiempo"]:
            assert "costo_unitario_usd" not in ev

    # LOGISTICA solicita ajuste de baja -> queda PENDIENTE, equipo NO cambia de estado
    resp_aju = cliente.post(
        "/api/logistica/ajustes",
        headers=cab_log,
        json={
            "sucursal_id": bodega_id,
            "tipo": "BAJA_EQUIPO",
            "equipo_id": eq["id"],
            "cantidad": 1,
            "motivo": "Placa madre quemada irreparable",
        },
    )
    assert resp_aju.status_code == 201
    ajuste_id = resp_aju.json()["id"]

    # Verificar que el equipo NO cambió todavía
    eq_antes = cliente.get("/api/logistica/inventario/equipos?busqueda=BAJA-001", headers=cab_dir).json()[0]
    assert eq_antes["estado"] == "POR_PREPARAR"

    # LOGISTICA intenta aprobar su propio ajuste -> 403
    resp_forb = cliente.patch(
        f"/api/logistica/ajustes/{ajuste_id}/revisar",
        headers=cab_log,
        json={"decision": "APROBADO"},
    )
    assert resp_forb.status_code == 403

    # DIRECCION aprueba -> equipo pasa a CEMENTERIO
    resp_ok = cliente.patch(
        f"/api/logistica/ajustes/{ajuste_id}/revisar",
        headers=cab_dir,
        json={"decision": "APROBADO", "comentario": "Confirmado con taller"},
    )
    assert resp_ok.status_code == 200
    eq_despues = cliente.get("/api/logistica/inventario/equipos?busqueda=BAJA-001", headers=cab_dir).json()[0]
    assert eq_despues["estado"] == "CEMENTERIO"
