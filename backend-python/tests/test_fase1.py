from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.base_datos import Base, obtener_bd
from app.main import app
from app.rutas.tasas import obtener_fecha_hoy
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


def iniciar_sesion_como(cliente: TestClient, correo: str, clave: str) -> dict[str, str]:
    resp = cliente.post("/api/auth/login", json={"correo": correo, "clave": clave})
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_semilla_sucursales_y_login_direccion(cliente: TestClient) -> None:
    cabeceras = iniciar_sesion_como(cliente, "direccion@tekioelectronics.com", "Tekio2026!")

    resp = cliente.get("/api/sucursales", headers=cabeceras)
    assert resp.status_code == 200
    sucursales = {s["nombre"]: s for s in resp.json()}

    assert set(sucursales.keys()) == {
        "Depósito / Tekio Support (Taller)",
        "Tekio Central",
        "Tekio Gran Bazar",
        "INFOT",
        "Free Market C13",
    }
    assert sucursales["Depósito / Tekio Support (Taller)"]["estado"] == "ACTIVA"
    assert sucursales["Depósito / Tekio Support (Taller)"]["telefono"] == "0422-5284961"
    assert sucursales["Tekio Central"]["estado"] == "ACTIVA"
    assert sucursales["Tekio Central"]["telefono"] == "0412-5284961"
    assert sucursales["Tekio Gran Bazar"]["estado"] == "ACTIVA"
    assert sucursales["Tekio Gran Bazar"]["telefono"] == "0422-5556609"
    assert sucursales["INFOT"]["estado"] == "CERRADA"
    assert sucursales["INFOT"]["fecha_cierre"] == "2026-11-08"
    assert sucursales["Free Market C13"]["estado"] == "CERRADA"
    assert sucursales["Free Market C13"]["fecha_cierre"] == "2026-11-16"


def test_rbac_oculta_costos_y_bloquea_usuarios_para_asesora_y_tecnico(cliente: TestClient) -> None:
    cab_dir = iniciar_sesion_como(cliente, "direccion@tekioelectronics.com", "Tekio2026!")

    # Crear usuaria ASESORA y usuario TECNICO
    resp_asesora = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": "Caira Asesora",
            "correo": "caira@tekioelectronics.com",
            "clave": "ClaveSegura123",
            "rol": "ASESORA",
            "sucursal_id": 2,
        },
    )
    assert resp_asesora.status_code == 201

    resp_tecnico = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": "Cristihan Técnico",
            "correo": "cristihan@tekioelectronics.com",
            "clave": "ClaveSegura123",
            "rol": "TECNICO",
            "sucursal_id": 1,
        },
    )
    assert resp_tecnico.status_code == 201

    # Crear artículo con costo de referencia
    resp_art = cliente.post(
        "/api/catalogo",
        headers=cab_dir,
        json={
            "sku": "  bat 33ydh ",
            "descripcion": "Batería Dell 33YDH Original",
            "tipo": "COMPONENTE",
            "categoria": "Baterías",
            "precio_promo_usd": 45.0,
            "costo_referencia_usd": 22.5,
        },
    )
    assert resp_art.status_code == 201
    datos_art = resp_art.json()
    assert datos_art["sku"] == "BAT-33YDH"
    assert datos_art["costo_referencia_usd"] == 22.5

    # Verificar que ASESORA y TECNICO no acceden a /api/usuarios ni ven costo_referencia_usd
    for correo in ("caira@tekioelectronics.com", "cristihan@tekioelectronics.com"):
        cab = iniciar_sesion_como(cliente, correo, "ClaveSegura123")
        assert cliente.get("/api/usuarios", headers=cab).status_code == 403

        resp_cat = cliente.get("/api/catalogo", headers=cab)
        assert resp_cat.status_code == 200
        elemento = resp_cat.json()["elementos"][0]
        assert "costo_referencia_usd" not in elemento

        resp_hist = cliente.get(f"/api/catalogo/{datos_art['id']}/precios", headers=cab)
        assert resp_hist.status_code == 200
        assert "costo_referencia_usd" not in resp_hist.json()[0]


def test_borrado_logico_usuario(cliente: TestClient) -> None:
    cab_dir = iniciar_sesion_como(cliente, "direccion@tekioelectronics.com", "Tekio2026!")
    resp_u = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": "Usuario Temporal",
            "correo": "temporal@tekioelectronics.com",
            "clave": "ClaveSegura123",
            "rol": "LOGISTICA",
        },
    )
    uid = resp_u.json()["id"]

    resp_off = cliente.patch(
        f"/api/usuarios/{uid}/estado",
        headers=cab_dir,
        json={"activo": False, "motivo": "Cese de funciones"},
    )
    assert resp_off.status_code == 200
    assert resp_off.json()["activo"] is False

    resp_login = cliente.post(
        "/api/auth/login",
        json={"correo": "temporal@tekioelectronics.com", "clave": "ClaveSegura123"},
    )
    assert resp_login.status_code == 403


def test_tasas_bloqueo_sin_tasa_inmutabilidad_y_actualizacion_hoy(cliente: TestClient) -> None:
    cab_dir = iniciar_sesion_como(cliente, "direccion@tekioelectronics.com", "Tekio2026!")
    hoy = obtener_fecha_hoy()
    ayer = hoy - timedelta(days=1)

    # Sin tasa hoy -> permite_bolivares False
    resp_hoy_vacio = cliente.get("/api/tasas/hoy", headers=cab_dir)
    assert resp_hoy_vacio.status_code == 200
    assert resp_hoy_vacio.json()["permite_bolivares"] is False
    assert resp_hoy_vacio.json()["alerta"] is not None

    # Bloquear creación de tasa de ayer
    resp_ayer = cliente.post(
        "/api/tasas",
        headers=cab_dir,
        json={
            "fecha": ayer.isoformat(),
            "tasa_bcv": 50.0,
            "tasa_usdt": 55.0,
            "recargo_porcentaje": 20.0,
            "nota": "Intento retroactivo",
        },
    )
    assert resp_ayer.status_code == 403

    # Crear tasa de hoy
    resp_hoy = cliente.post(
        "/api/tasas",
        headers=cab_dir,
        json={
            "fecha": hoy.isoformat(),
            "tasa_bcv": 60.0,
            "tasa_usdt": 72.0,
            "recargo_porcentaje": 30.0,
            "nota": "Tasa oficial mañana",
        },
    )
    assert resp_hoy.status_code == 201
    assert resp_hoy.json()["brecha_porcentaje"] == 20.0

    # Consultar hoy -> permite_bolivares True
    resp_get_hoy = cliente.get("/api/tasas/hoy", headers=cab_dir)
    assert resp_get_hoy.status_code == 200
    assert resp_get_hoy.json()["permite_bolivares"] is True

    # Actualizar tasa de hoy -> origen MANUAL
    resp_put = cliente.put(
        "/api/tasas/hoy",
        headers=cab_dir,
        json={"tasa_usdt": 75.0, "nota": "Ajuste tarde"},
    )
    assert resp_put.status_code == 200
    assert resp_put.json()["tasa_usdt"] == 75.0
    assert resp_put.json()["origen"] == "MANUAL"


def test_sku_duplicado_409_e_historial_precios_inmutable(cliente: TestClient) -> None:
    cab_dir = iniciar_sesion_como(cliente, "direccion@tekioelectronics.com", "Tekio2026!")
    hoy = obtener_fecha_hoy()

    # Registrar tasa hoy (BCV = 60, Recargo = 30%)
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

    resp1 = cliente.post(
        "/api/catalogo",
        headers=cab_dir,
        json={
            "sku": "BAT-33YDH",
            "descripcion": "Batería Dell",
            "tipo": "COMPONENTE",
            "categoria": "Baterías",
            "precio_promo_usd": 100.0,
            "costo_referencia_usd": 50.0,
        },
    )
    assert resp1.status_code == 201
    art_id = resp1.json()["id"]
    # Regular = 100 * 1.30 = 130 USD; Regular Bs = 130 * 60 = 7800 Bs
    assert resp1.json()["precio_regular_usd"] == 130.0
    assert resp1.json()["precio_regular_bs"] == 7800.0

    # Duplicado con minúsculas/espacios -> 409 Conflict
    resp_dup = cliente.post(
        "/api/catalogo",
        headers=cab_dir,
        json={
            "sku": "  bat-33ydh ",
            "descripcion": "Batería duplicada",
            "tipo": "COMPONENTE",
            "categoria": "Baterías",
            "precio_promo_usd": 90.0,
        },
    )
    assert resp_dup.status_code == 409

    # Agregar nuevo precio -> historial conserva ambos registros
    resp_p2 = cliente.post(
        f"/api/catalogo/{art_id}/precios",
        headers=cab_dir,
        json={
            "precio_promo_usd": 110.0,
            "costo_referencia_usd": 55.0,
            "fecha_vigencia": hoy.isoformat(),
        },
    )
    assert resp_p2.status_code == 201

    resp_hist = cliente.get(f"/api/catalogo/{art_id}/precios", headers=cab_dir)
    assert resp_hist.status_code == 200
    historial = resp_hist.json()
    assert len(historial) == 2
    assert historial[0]["precio_promo_usd"] == 110.0
    assert historial[1]["precio_promo_usd"] == 100.0
