from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

_DIR_TESTS = str(Path(__file__).resolve().parent)
if _DIR_TESTS not in sys.path:
    sys.path.insert(0, _DIR_TESTS)

from test_fase5 import (  # noqa: E402
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def test_compartir_acceso_temporal_rbac_desbloqueo_y_login(cliente: TestClient) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]
    cab_as = ctx["headers_as"]

    # 1. Crear usuario ADMINISTRACION para validar también su acceso al endpoint
    r_adm = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": "Admin Accesos",
            "username": "admin.accesos",
            "correo": "admin.accesos@tekio.com",
            "clave": "AdminClave2026!",
            "rol": "ADMINISTRACION",
            "tiene_acceso_sistema": True,
            "telefono": "0414-5550101",
            "sucursal_id": 1,
        },
    )
    assert r_adm.status_code == 201, r_adm.text
    adm_json = r_adm.json()
    # POST /api/usuarios con acceso devuelve datos listos para el modal Compartir Acceso
    assert adm_json["acceso_compartir"] is not None
    assert adm_json["acceso_compartir"]["username"] == "admin.accesos"
    assert adm_json["acceso_compartir"]["password_temporal"] == "AdminClave2026!"
    assert "tekio-admin-two.vercel.app" in adm_json["acceso_compartir"]["url_app"]

    r_log_adm = cliente.post(
        "/api/auth/login",
        json={"username": "admin.accesos", "password": "AdminClave2026!"},
    )
    assert r_log_adm.status_code == 200, r_log_adm.text
    cab_adm = {"Authorization": f"Bearer {r_log_adm.json()['token']}"}

    # 2. Crear usuario operativo con acceso y usuario SIN acceso
    r_op = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": "Andrea Ventas",
            "username": "andrea.ventas",
            "correo": "andrea.ventas@tekio.com",
            "clave": "Inicial2026!",
            "rol": "ASESORA",
            "tiene_acceso_sistema": True,
            "telefono": "0424-9991122",
            "sucursal_id": 1,
        },
    )
    assert r_op.status_code == 201, r_op.text
    op_id = r_op.json()["id"]

    r_sin = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": "Luis Sin Acceso",
            "rol": "TECNICO",
            "tiene_acceso_sistema": False,
            "sucursal_id": 1,
        },
    )
    assert r_sin.status_code == 201, r_sin.text
    sin_id = r_sin.json()["id"]
    assert r_sin.json()["acceso_compartir"] is None

    # 3. 403 Forbidden para roles operativos (ASESORA)
    r_403 = cliente.post(f"/api/usuarios/{op_id}/generar-acceso-temporal", headers=cab_as)
    assert r_403.status_code == 403, r_403.text

    # 4. 400 Bad Request si el colaborador no tiene acceso al sistema
    r_400 = cliente.post(f"/api/usuarios/{sin_id}/generar-acceso-temporal", headers=cab_dir)
    assert r_400.status_code == 400, r_400.text

    # 5. Bloquear la cuenta de Andrea con 5 intentos fallidos
    for _ in range(5):
        cliente.post(
            "/api/auth/login",
            json={"username": "andrea.ventas", "password": "clave-errada"},
        )
    r_bloq = cliente.post(
        "/api/auth/login",
        json={"username": "andrea.ventas", "password": "Inicial2026!"},
    )
    assert r_bloq.status_code == 423, r_bloq.text

    # 6. ADMINISTRACION genera acceso temporal -> 200, desbloquea cuenta y devuelve contraseña sin ambiguos
    r_gen = cliente.post(f"/api/usuarios/{op_id}/generar-acceso-temporal", headers=cab_adm)
    assert r_gen.status_code == 200, r_gen.text
    datos = r_gen.json()
    pwd_temp = datos["password_temporal"]
    assert 8 <= len(pwd_temp) <= 12
    for ambiguo in ("O", "0", "I", "l", "1"):
        assert ambiguo not in pwd_temp
    assert datos["username"] == "andrea.ventas"
    assert datos["telefono"] == "0424-9991122"
    assert datos["url_app"].startswith("https://")

    # 7. Login exitoso con la nueva contraseña temporal (cuenta desbloqueada)
    r_ok = cliente.post(
        "/api/auth/login",
        json={"username": "andrea.ventas", "password": pwd_temp},
    )
    assert r_ok.status_code == 200, r_ok.text
    assert r_ok.json()["usuario"]["cuenta_bloqueada"] is False

    # 8. Auditoría registrada sin guardar la contraseña en texto plano
    r_aud = cliente.get("/api/finanzas/auditoria?modulo=SEGURIDAD", headers=cab_dir)
    assert r_aud.status_code == 200, r_aud.text
    eventos = [ev for ev in r_aud.json() if ev.get("accion") == "GENERAR_ACCESO_TEMPORAL"]
    assert len(eventos) >= 1
    assert pwd_temp not in str(eventos)

    # 9. DIRECCION también puede generar acceso temporal (200)
    r_dir_gen = cliente.post(f"/api/usuarios/{op_id}/generar-acceso-temporal", headers=cab_dir)
    assert r_dir_gen.status_code == 200, r_dir_gen.text
