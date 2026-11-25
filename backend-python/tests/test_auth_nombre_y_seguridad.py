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


def test_auth_por_nombre_bloqueo_persistente_6to_intento_alertas_y_cambiar_clave(
    cliente: TestClient,
) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]

    # Crear usuario con acceso SIN correo obligatorio, usando Nombre y username
    r_u = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": "Carlos Mendoza",
            "username": "carlos.mendoza",
            "tiene_acceso": True,
            "correo": "",
            "clave": "ClaveInicial2026",
            "rol": "ASESORA",
            "sucursal_id": 1,
        },
    )
    assert r_u.status_code == 201, r_u.text
    uid = r_u.json()["id"]

    # 1. Login exitoso usando el NOMBRE del usuario con mayúsculas/minúsculas distintas
    r_log_nom = cliente.post(
        "/api/auth/login",
        json={"usuario": "  cArLoS mEnDoZa  ", "password": "ClaveInicial2026"},
    )
    assert r_log_nom.status_code == 200, r_log_nom.text

    # 2. 4 intentos fallidos -> 401 indicando intentos restantes, 5to -> 423 + alerta en /api/alertas/resumen
    for intento in range(1, 5):
        r_bad = cliente.post(
            "/api/auth/login",
            json={"usuario": "Carlos Mendoza", "password": "clave-errada"},
        )
        assert r_bad.status_code == 401, r_bad.text
        restantes = 5 - intento
        assert str(restantes) in r_bad.json()["detail"]

    r_5to = cliente.post(
        "/api/auth/login",
        json={"usuario": "Carlos Mendoza", "password": "clave-errada"},
    )
    assert r_5to.status_code == 423, r_5to.text
    assert "bloqueado" in r_5to.json()["detail"].lower()

    r_al = cliente.get("/api/alertas/resumen", headers=cab_dir)
    assert r_al.status_code == 200, r_al.text
    assert any(a["usuario_id"] == uid for a in r_al.json()["alertas_seguridad"])

    # 3. Bloqueo persistente en un 6to intento AUNQUE se envíe la contraseña correcta
    r_6to = cliente.post(
        "/api/auth/login",
        json={"usuario": "Carlos Mendoza", "password": "ClaveInicial2026"},
    )
    assert r_6to.status_code == 423, r_6to.text

    # Desbloqueo por ADMIN (/api/personal/{id}/desbloquear)
    r_des = cliente.post(f"/api/personal/{uid}/desbloquear", headers=cab_dir)
    assert r_des.status_code == 200, r_des.text
    assert r_des.json()["cuenta_bloqueada"] is False

    # Alerta desaparece tras desbloqueo
    r_al_post = cliente.get("/api/alertas/resumen", headers=cab_dir)
    assert not any(a["usuario_id"] == uid for a in r_al_post.json()["alertas_seguridad"])

    # Login vuelve a funcionar
    r_log_ok = cliente.post(
        "/api/auth/login",
        json={"usuario": "Carlos Mendoza", "password": "ClaveInicial2026"},
    )
    assert r_log_ok.status_code == 200, r_log_ok.text
    cab_carlos = {"Authorization": f"Bearer {r_log_ok.json()['token']}"}

    # 4. Cambio de clave propio en /api/auth/cambiar-clave y login con la nueva clave
    r_chg = cliente.post(
        "/api/auth/cambiar-clave",
        headers=cab_carlos,
        json={
            "clave_actual": "ClaveInicial2026",
            "nueva_clave": "MiNuevaClave77",
            "confirmar_clave": "MiNuevaClave77",
        },
    )
    assert r_chg.status_code == 200, r_chg.text

    r_final = cliente.post(
        "/api/auth/login",
        json={"usuario": "carlos mendoza", "password": "MiNuevaClave77"},
    )
    assert r_final.status_code == 200, r_final.text
