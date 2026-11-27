from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
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
) -> tuple[dict[str, str], dict]:
    resp = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": nombre,
            "correo": correo,
            "clave": "ClaveSegura123",
            "rol": rol,
            "sucursal_id": 1,
        },
    )
    assert resp.status_code == 201, resp.text
    return login(cliente, correo, "ClaveSegura123")


def test_preparacion_listo_descuenta_ram_actualiza_costo_y_oculta_al_tecnico(cliente: TestClient) -> None:
    cab_dir, _ = login(cliente, "direccion@tekioelectronics.com", "Tekio2026!")
    cab_tec, _ = crear_usuario_rol(
        cliente, cab_dir, "Cristihan Técnico", "cristihan@tekioelectronics.com", "TECNICO"
    )

    sucs = {s["nombre"]: s["id"] for s in cliente.get("/api/sucursales", headers=cab_dir).json()}
    bodega_id = sucs["Depósito / Tekio Support (Taller)"]

    # 1. Crear componente RAM en catálogo con costo_referencia_usd = 15.00
    ram = cliente.post(
        "/api/catalogo",
        headers=cab_dir,
        json={
            "sku": "RAM-8GB-DDR4",
            "descripcion": "Memoria RAM 8GB DDR4",
            "tipo": "COMPONENTE",
            "categoria": "Memorias",
            "precio_promo_usd": 30.0,
            "costo_referencia_usd": 15.0,
        },
    ).json()

    # 2. Ingresar 5 unidades de RAM + 1 equipo POR_PREPARAR en Bodega
    cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "fecha": date.today().isoformat(),
            "llega_preparada": False,
            "equipos": [
                {
                    "serial": "LAP-TALLER-1",
                    "modelo": "Dell Latitude 7410",
                    "ubicacion_id": bodega_id,
                    "costo_compra_usd": 200.0,
                    "precio_promo_usd": 380.0,
                }
            ],
            "componentes": [
                {
                    "articulo_id": ram["id"],
                    "cantidad": 5,
                    "costo_unitario_usd": 15.0,
                    "ubicacion_id": bodega_id,
                }
            ],
        },
    )

    cola_tec = cliente.get("/api/taller/cola", headers=cab_tec).json()
    assert len(cola_tec) == 1
    assert "costo_taller_usd" not in cola_tec[0]
    equipo_id = cola_tec[0]["id"]

    # 3. Técnico registra preparación estándar ($1) usando 1 RAM ($15) -> resultado LISTO
    resp_prep = cliente.post(
        "/api/taller/preparaciones",
        headers=cab_tec,
        json={
            "equipo_id": equipo_id,
            "tipo": "ESTANDAR",
            "componentes_usados": [{"articulo_id": ram["id"], "cantidad": 1}],
            "resultado": "LISTO",
            "nota": "Instalación de RAM y sistema operativo",
        },
    )
    assert resp_prep.status_code == 201, resp_prep.text
    datos_prep = resp_prep.json()
    assert datos_prep["resultado"] == "LISTO"
    assert datos_prep["pago_tecnico_usd"] == 1.0
    # RBAC: técnico NO recibe costo_taller_usd
    assert "costo_taller_usd" not in datos_prep

    # 4. Verificar que en inventario (visto por DIRECCION) el equipo es LISTO y costo_taller_usd = 16.0 ($1 + $15)
    eq_dir = cliente.get("/api/logistica/inventario/equipos?busqueda=LAP-TALLER-1", headers=cab_dir).json()[0]
    assert eq_dir["estado"] == "LISTO"
    assert eq_dir["costo_taller_usd"] == 16.0
    assert eq_dir["costo_total_usd"] == 216.0

    # 5. Verificar que stock de RAM en Bodega bajó de 5 a 4
    kardex = cliente.get("/api/logistica/inventario/kardex", headers=cab_dir).json()
    saldo_ram = [s for s in kardex["saldos"] if s["articulo_id"] == ram["id"]][0]
    assert saldo_ram["stock_actual"] == 4


def test_hospital_crea_repuesto_y_logistica_activa_alerta_en_cola(cliente: TestClient) -> None:
    cab_dir, _ = login(cliente, "direccion@tekioelectronics.com", "Tekio2026!")
    cab_tec, _ = crear_usuario_rol(
        cliente, cab_dir, "Técnico Hospital", "tec_hosp@tekioelectronics.com", "TECNICO"
    )
    cab_log, _ = crear_usuario_rol(
        cliente, cab_dir, "Logística Repuestos", "log_rep@tekioelectronics.com", "LOGISTICA"
    )

    sucs = {s["nombre"]: s["id"] for s in cliente.get("/api/sucursales", headers=cab_dir).json()}
    cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "fecha": date.today().isoformat(),
            "equipos": [
                {
                    "serial": "LAP-HOSP-1",
                    "modelo": "HP EliteBook",
                    "ubicacion_id": sucs["Depósito / Tekio Support (Taller)"],
                    "costo_compra_usd": 180.0,
                }
            ],
        },
    )
    eq_id = cliente.get("/api/taller/cola", headers=cab_tec).json()[0]["id"]

    # Técnico envía equipo a HOSPITAL con repuesto faltante
    resp_hosp = cliente.post(
        "/api/taller/preparaciones",
        headers=cab_tec,
        json={
            "equipo_id": eq_id,
            "tipo": "ESTANDAR",
            "resultado": "HOSPITAL",
            "repuestos_faltantes": [
                {"descripcion": "Pantalla 14 pulgadas FHD 30 pines", "cantidad": 1}
            ],
            "nota": "Pantalla con líneas verticales",
        },
    )
    assert resp_hosp.status_code == 201, resp_hosp.text
    rep_ids = resp_hosp.json()["repuestos_solicitados_ids"]
    assert len(rep_ids) == 1

    # Antes de recibir el repuesto -> repuesto_disponible es False
    cola_antes = cliente.get("/api/taller/cola?estado=HOSPITAL", headers=cab_tec).json()
    assert cola_antes[0]["repuesto_disponible"] is False

    # Logística marca el repuesto como RECIBIDO
    resp_rec = cliente.patch(
        f"/api/taller/repuestos-solicitados/{rep_ids[0]}/estado",
        headers=cab_log,
        json={"estado": "RECIBIDO"},
    )
    assert resp_rec.status_code == 200
    assert resp_rec.json()["notificado_tecnico"] is True

    # Ahora aparece resaltado en la cola del técnico con repuesto_disponible = True
    cola_despues = cliente.get("/api/taller/cola?estado=HOSPITAL", headers=cab_tec).json()
    assert cola_despues[0]["repuesto_disponible"] is True


def test_caso_st_bloquea_terminado_sin_presupuesto_y_calcula_resumen_tecnico(cliente: TestClient) -> None:
    cab_dir, _ = login(cliente, "direccion@tekioelectronics.com", "Tekio2026!")
    cab_tec, tec_user = crear_usuario_rol(
        cliente, cab_dir, "Técnico ST", "tec_st@tekioelectronics.com", "TECNICO"
    )
    sucs = {s["nombre"]: s["id"] for s in cliente.get("/api/sucursales", headers=cab_dir).json()}
    bodega_id = sucs["Depósito / Tekio Support (Taller)"]

    # Crear 1 equipo para preparación estándar ($1) y 1 repuesto con stock
    ssd = cliente.post(
        "/api/catalogo",
        headers=cab_dir,
        json={
            "sku": "SSD-256-NVME",
            "descripcion": "SSD NVMe 256GB",
            "tipo": "COMPONENTE",
            "categoria": "Almacenamiento",
            "precio_promo_usd": 35.0,
            "costo_referencia_usd": 18.0,
        },
    ).json()

    cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "fecha": date.today().isoformat(),
            "equipos": [
                {
                    "serial": "LAP-RES-1",
                    "modelo": "Lenovo T14",
                    "ubicacion_id": bodega_id,
                    "costo_compra_usd": 220.0,
                }
            ],
            "componentes": [
                {
                    "articulo_id": ssd["id"],
                    "cantidad": 3,
                    "costo_unitario_usd": 18.0,
                    "ubicacion_id": bodega_id,
                }
            ],
        },
    )
    eq_id = cliente.get("/api/taller/cola", headers=cab_tec).json()[0]["id"]
    cliente.post(
        "/api/taller/preparaciones",
        headers=cab_tec,
        json={"equipo_id": eq_id, "tipo": "ESTANDAR", "resultado": "LISTO"},
    )

    # Crear caso de Servicio Técnico (ST)
    caso = cliente.post(
        "/api/taller/casos",
        headers=cab_tec,
        json={
            "tipo": "SERVICIO",
            "sucursal_id": sucs["Tekio Central"],
            "descripcion_equipo": "Laptop ASUS VivoBook",
            "falla_reportada": "No enciende el sistema operativo",
        },
    ).json()
    assert caso["numero_caso"].startswith("ST-")

    # Intentar pasar a TERMINADO sin presupuesto aprobado -> 400
    resp_bloq = cliente.patch(
        f"/api/taller/casos/{caso['id']}/actualizar",
        headers=cab_tec,
        json={
            "tecnico_id": tec_user["id"],
            "diagnostico": "SSD dañado",
            "trabajo_realizado": "Cambio de SSD",
            "resultado_estado": "TERMINADO",
        },
    )
    assert resp_bloq.status_code == 400

    # Enviar presupuesto ($40 mano de obra + 1 SSD) y aprobarlo
    resp_pres = cliente.post(
        f"/api/taller/casos/{caso['id']}/presupuesto",
        headers=cab_tec,
        json={
            "mano_obra_usd": 40.0,
            "repuestos": [
                {
                    "articulo_id": ssd["id"],
                    "descripcion": "SSD NVMe 256GB",
                    "cantidad": 1,
                    "precio_promo_usd": 35.0,
                }
            ],
        },
    )
    assert resp_pres.status_code == 201
    assert resp_pres.json()["total_promo_usd"] == 75.0

    resp_aprob = cliente.patch(
        f"/api/taller/casos/{caso['id']}/aprobar-presupuesto",
        headers=cab_dir,
        json={"aprobado": True, "nota_cliente": "Aprobado por WhatsApp"},
    )
    assert resp_aprob.status_code == 200
    assert resp_aprob.json()["estado"] == "AUTORIZADO"

    # Ahora sí puede marcar TERMINADO (sin enviar repuestos_usados -> descuenta automáticamente el SSD del presupuesto)
    resp_term = cliente.patch(
        f"/api/taller/casos/{caso['id']}/actualizar",
        headers=cab_tec,
        json={
            "tecnico_id": tec_user["id"],
            "diagnostico": "SSD dañado",
            "trabajo_realizado": "Instalación de SSD NVMe y Windows 11",
            "resultado_estado": "TERMINADO",
        },
    )
    assert resp_term.status_code == 200, resp_term.text

    # Verificar descuento automático del SSD (3 -> 2)
    kardex = cliente.get("/api/logistica/inventario/kardex", headers=cab_dir).json()
    saldo_ssd = [s for s in kardex["saldos"] if s["articulo_id"] == ssd["id"]][0]
    assert saldo_ssd["stock_actual"] == 2

    # Verificar resumen mensual del técnico: $1 preparación + $20 (50% de $40 mano de obra) = $21.00, SIN costos
    resumen = cliente.get("/api/taller/resumen-tecnico", headers=cab_tec).json()
    assert resumen["cantidad_preparaciones"] == 1
    assert resumen["pago_preparaciones_usd"] == 1.0
    assert resumen["cantidad_servicios"] == 1
    assert resumen["comision_servicios_usd"] == 20.0
    assert resumen["total_mes_usd"] == 21.0
    assert "costo_taller_usd" not in resumen
