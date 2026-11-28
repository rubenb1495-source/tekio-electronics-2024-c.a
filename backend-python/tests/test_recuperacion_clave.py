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


def test_recuperacion_clave_olvidada_alerta_y_regenerar_temporal(
    cliente: TestClient,
) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]

    r_usr = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": "Pedro Recuperacion",
            "username": "pedro.rec",
            "correo": "",
            "clave": "Password123!",
            "rol": "ASESORA",
            "sucursal_id": 1,
        },
    )
    assert r_usr.status_code == 201, r_usr.text
    uid = r_usr.json()["id"]

    # 1. Bloquear cuenta tras 5 intentos fallidos
    for _ in range(5):
        cliente.post("/api/auth/login", json={"usuario": "pedro.rec", "clave": "WrongPassword!"})

    # 2. Usuario solicita recuperación desde Login -> crea alerta para Dirección/Admin
    r_sol = cliente.post("/api/auth/solicitar-recuperacion", json={"usuario": "pedro.rec"})
    assert r_sol.status_code == 200, r_sol.text
    assert r_sol.json()["modo"] == "ALERTA_ADMIN"

    r_al = cliente.get("/api/alertas", headers=cab_dir)
    assert r_al.status_code == 200
    assert any(
        "recuperación" in (a.get("mensaje") or "").lower()
        for a in r_al.json().get("alertas_seguridad", [])
    )

    # 3. Director/Admin regenera clave temporal -> desbloquea cuenta y exige cambio de clave
    r_reg = cliente.post(f"/api/usuarios/{uid}/regenerar-clave-temporal", headers=cab_dir)
    assert r_reg.status_code == 200, r_reg.text
    clave_temp = r_reg.json()["password_temporal"]
    assert len(clave_temp) >= 10

    r_log = cliente.post("/api/auth/login", json={"usuario": "pedro.rec", "clave": clave_temp})
    assert r_log.status_code == 200, r_log.text
    assert r_log.json()["usuario"]["debe_cambiar_clave"] is True
    assert r_log.json()["usuario"]["cuenta_bloqueada"] is False
