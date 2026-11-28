from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

_DIR_TESTS = str(Path(__file__).resolve().parent)
if _DIR_TESTS not in sys.path:
    sys.path.insert(0, _DIR_TESTS)

from test_fase5 import (  # noqa: E402
    _login,
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def test_paridad_alfa_cambio_clave_obligatorio_cierre_separado_y_paginacion(
    cliente: TestClient,
) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]

    # 1. Usuario nuevo con acceso nace con debe_cambiar_clave == True
    r_new = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": "Sofia Paridad",
            "username": "sofia.paridad",
            "correo": "sofia.paridad@tekio.com",
            "clave": "TempPassword1!",
            "rol": "LIDER",
            "sucursal_id": 1,
        },
    )
    assert r_new.status_code == 201, r_new.text
    uid = r_new.json()["id"]
    assert r_new.json()["debe_cambiar_clave"] is True

    # Al iniciar sesión, el payload de login y /perfil indican debe_cambiar_clave == True
    r_log = cliente.post(
        "/api/auth/login",
        json={"usuario": "sofia.paridad", "clave": "TempPassword1!"},
    )
    assert r_log.status_code == 200, r_log.text
    assert r_log.json()["usuario"]["debe_cambiar_clave"] is True
    cab_sofia = {"Authorization": f"Bearer {r_log.json()['token']}"}

    # Al cambiar contraseña propia, debe_cambiar_clave pasa a False
    r_chg = cliente.post(
        "/api/auth/cambiar-password",
        headers=cab_sofia,
        json={
            "clave_actual": "TempPassword1!",
            "clave_nueva": "NuevaClaveSegura2026!",
            "confirmar_clave": "NuevaClaveSegura2026!",
        },
    )
    assert r_chg.status_code == 200, r_chg.text
    r_perf = cliente.get("/api/auth/perfil", headers=cab_sofia)
    assert r_perf.status_code == 200
    assert r_perf.json()["debe_cambiar_clave"] is False

    # Tras reset temporal desde admin, vuelve a debe_cambiar_clave == True
    r_tmp = cliente.post(f"/api/usuarios/{uid}/generar-acceso-temporal", headers=cab_dir)
    assert r_tmp.status_code == 200, r_tmp.text
    r_perf2 = cliente.get("/api/auth/perfil", headers=cab_sofia)
    assert r_perf2.json()["debe_cambiar_clave"] is True

    # 2. Separación estricta Tienda vs Administración General en Tablero de Saldos de Cierre
    r_tab_lider = cliente.get("/api/finanzas/cierre-caja/tablero-saldos", headers=cab_sofia)
    assert r_tab_lider.status_code == 200, r_tab_lider.text
    body_lider = r_tab_lider.json()
    assert body_lider["ambito_usuario"] == "TIENDA"
    assert body_lider["tienda"] is not None
    assert body_lider["administracion_general"] is None

    r_tab_dir = cliente.get("/api/finanzas/cierre-caja/tablero-saldos", headers=cab_dir)
    assert r_tab_dir.status_code == 200, r_tab_dir.text
    body_dir = r_tab_dir.json()
    assert body_dir["ambito_usuario"] == "ADMINISTRACION_GENERAL"
    assert body_dir["administracion_general"] is not None
    assert "total_liquidez_consolidada_usd" in body_dir["administracion_general"]

    # 3. Límites unificados de por_pagina (sin 422)
    assert cliente.get("/api/catalogo?por_pagina=500", headers=cab_dir).status_code == 200
    assert cliente.get("/api/logistica/compras?por_pagina=250", headers=cab_dir).status_code == 200
    assert cliente.get("/api/tasas?por_pagina=250", headers=cab_dir).status_code == 200
