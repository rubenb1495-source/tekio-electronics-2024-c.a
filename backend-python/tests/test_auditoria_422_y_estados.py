from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

_DIR_TESTS = str(Path(__file__).resolve().parent)
if _DIR_TESTS not in sys.path:
    sys.path.insert(0, _DIR_TESTS)

from app.base_datos import obtener_bd  # noqa: E402
from app.main import app  # noqa: E402
from app.modelos_logistica import Equipo, EstadoEquipo  # noqa: E402
from app.rutas.tasas import obtener_fecha_hoy  # noqa: E402
from test_fase5 import (  # noqa: E402
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def test_blindaje_422_campos_vacios_y_mensajes_espanol(cliente: TestClient) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]
    hoy_str = obtener_fecha_hoy().isoformat()

    # 1. Ingreso de inventario enviando "" en múltiples campos opcionales (sin 422)
    r_ok = cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "tipo_compra": "",
            "proveedor_id": "",
            "fecha": hoy_str,
            "fecha_vencimiento": "",
            "saldo_pendiente_usd": "",
            "factura_orden": "",
            "numero_guia": "",
            "monto_mercancia_usd": "300",
            "envio_usd": "",
            "aduana_usd": "",
            "otros_gastos_usd": "",
            "nota": "",
            "equipos": [
                {
                    "serial": "AUD-422-001",
                    "articulo_id": "",
                    "modelo": "Lenovo ThinkPad T14",
                    "configuracion": "i5 / 16GB / 512GB",
                    "ubicacion_id": "",
                    "estado": "",
                    "costo_compra_usd": "",
                    "precio_promo_usd": "450",
                    "nota": "",
                }
            ],
        },
    )
    assert r_ok.status_code == 201, r_ok.text
    assert r_ok.json()["total_equipos"] == 1

    # 2. Error real de validación 422 devuelve mensaje claro en español + lista `errores`
    r_422 = cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "fecha": "no-es-fecha",
            "equipos": [{"serial": "X"}],
        },
    )
    assert r_422.status_code == 422, r_422.text
    cuerpo = r_422.json()
    assert isinstance(cuerpo.get("detail"), str) and len(cuerpo["detail"]) > 10
    assert "obligatorio" in cuerpo["detail"].lower() or "fecha" in cuerpo["detail"].lower()
    assert isinstance(cuerpo.get("errores"), list) and len(cuerpo["errores"]) >= 1
    assert all("campo" in e and "mensaje" in e for e in cuerpo["errores"])


def test_cambio_estado_individual_masivo_y_auditoria(cliente: TestClient) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]
    hoy_str = obtener_fecha_hoy().isoformat()

    # Crear 2 equipos en inventario
    r_comp = cliente.post(
        "/api/logistica/compras",
        headers=cab_dir,
        json={
            "origen": "NACIONAL",
            "fecha": hoy_str,
            "monto_mercancia_usd": 600,
            "equipos": [
                {
                    "serial": "EST-IND-001",
                    "modelo": "HP EliteBook 840",
                    "costo_compra_usd": 300,
                    "precio_promo_usd": 480,
                },
                {
                    "serial": "EST-MAS-002",
                    "modelo": "Dell Latitude 5420",
                    "costo_compra_usd": 300,
                    "precio_promo_usd": 490,
                },
            ],
        },
    )
    assert r_comp.status_code == 201, r_comp.text

    r_inv = cliente.get("/api/logistica/inventario/equipos", headers=cab_dir)
    assert r_inv.status_code == 200
    por_serial = {e["serial"]: e for e in r_inv.json()}
    eq1_id = por_serial["EST-IND-001"]["id"]
    eq2_id = por_serial["EST-MAS-002"]["id"]

    # 1. Cambio individual: POR_PREPARAR -> EN_PREPARACION -> RESERVADO -> LISTO
    for nuevo_est in ("EN_PREPARACION", "RESERVADO", "LISTO"):
        r_patch = cliente.patch(
            f"/api/inventario/equipos/{eq1_id}/estado",
            headers=cab_dir,
            json={"nuevo_estado": nuevo_est, "motivo": f"Paso a {nuevo_est}"},
        )
        assert r_patch.status_code == 200, r_patch.text
        data = r_patch.json()
        assert data["actualizados"] == 1
        assert data["nuevo_estado"] == nuevo_est
        assert data["equipos"][0]["estado"] == nuevo_est
        assert "fecha_hora_caracas" in data

    # 2. Verificar que EN_PREPARACION aparece en la cola de taller
    r_en_prep = cliente.patch(
        f"/api/inventario/equipos/{eq2_id}/estado",
        headers=cab_dir,
        json={"nuevo_estado": "EN_PREPARACION", "motivo": "Técnico inició revisión"},
    )
    assert r_en_prep.status_code == 200, r_en_prep.text
    r_cola = cliente.get("/api/taller/cola", headers=cab_dir)
    assert r_cola.status_code == 200
    assert any(item["id"] == eq2_id and item["estado"] == "EN_PREPARACION" for item in r_cola.json())

    # 3. Cambio masivo PATCH /api/inventario/equipos/estado-masivo
    r_masivo = cliente.patch(
        "/api/inventario/equipos/estado-masivo",
        headers=cab_dir,
        json={
            "equipo_ids": [eq1_id, eq2_id],
            "nuevo_estado": "HOSPITAL",
            "motivo": "Revisión técnica masiva",
        },
    )
    assert r_masivo.status_code == 200, r_masivo.text
    assert r_masivo.json()["actualizados"] == 2
    assert r_masivo.json()["nuevo_estado"] == "HOSPITAL"

    # 4. Bloquear asignación manual de VENDIDO
    r_vendido_err = cliente.patch(
        f"/api/inventario/equipos/{eq1_id}/estado",
        headers=cab_dir,
        json={"nuevo_estado": "VENDIDO", "motivo": "Intento inválido"},
    )
    assert r_vendido_err.status_code == 400

    # 5. Bloquear cambio de estado sobre equipo que ya está VENDIDO
    override_bd = app.dependency_overrides[obtener_bd]
    gen_bd = override_bd()
    bd = next(gen_bd)
    try:
        eq_db = bd.query(Equipo).filter(Equipo.id == eq1_id).first()
        assert eq_db is not None
        eq_db.estado = EstadoEquipo.VENDIDO.value
        bd.commit()
    finally:
        try:
            next(gen_bd)
        except StopIteration:
            pass

    r_bloq = cliente.patch(
        f"/api/inventario/equipos/{eq1_id}/estado",
        headers=cab_dir,
        json={"nuevo_estado": "LISTO", "motivo": "No debería permitirse"},
    )
    assert r_bloq.status_code == 400
    assert "VENDIDO" in r_bloq.json()["detail"]

    # 6. Verificar registro en auditoria_sistema
    r_aud = cliente.get("/api/finanzas/auditoria?modulo=INVENTARIO", headers=cab_dir)
    assert r_aud.status_code == 200, r_aud.text
    eventos = r_aud.json()
    assert any(
        ev["accion"] == "CAMBIAR_ESTADO_EQUIPO" and ev["entidad_id"] == "EST-IND-001"
        for ev in eventos
    )
