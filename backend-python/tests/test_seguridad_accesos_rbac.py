from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

_DIR_TESTS = str(Path(__file__).resolve().parent)
if _DIR_TESTS not in sys.path:
    sys.path.insert(0, _DIR_TESTS)

from test_fase5 import (  # noqa: E402
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def _contiene_campos_sensibles(objeto: Any) -> list[str]:
    encontrados: list[str] = []
    if isinstance(objeto, dict):
        for k, v in objeto.items():
            kl = str(k).lower()
            if (
                kl.startswith(("costo_", "margen_", "proveedor_"))
                or kl in {"costo", "margen", "proveedor", "ganancia_usd", "utilidad_usd"}
            ):
                encontrados.append(str(k))
            encontrados.extend(_contiene_campos_sensibles(v))
    elif isinstance(objeto, list):
        for item in objeto:
            encontrados.extend(_contiene_campos_sensibles(item))
    return encontrados


def test_accesos_usuarios_seguridad_y_rbac_integral(cliente: TestClient) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]

    # 1. Crear usuario con acceso (LIDER) y probar login por username y por email
    r_lider = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": "Valeria Comercial",
            "username": "valeria.com",
            "correo": "valeria.com@tekio.com",
            "clave": "ClaveSegura2026!",
            "rol": "LIDER",
            "tiene_acceso_sistema": True,
            "sucursal_id": 1,
        },
    )
    assert r_lider.status_code == 201, r_lider.text
    lider = r_lider.json()
    lider_id = lider["id"]
    assert lider["username"] == "valeria.com"
    assert lider["tiene_acceso_sistema"] is True

    # Login por username (mayúsculas/espacios)
    r_log_user = cliente.post(
        "/api/auth/login",
        json={"username": "  VALERIA.COM  ", "password": "ClaveSegura2026!"},
    )
    assert r_log_user.status_code == 200, r_log_user.text
    cab_lider = {"Authorization": f"Bearer {r_log_user.json()['token']}"}

    # Login por email
    r_log_mail = cliente.post(
        "/api/auth/login",
        json={"email": "VALERIA.COM@tekio.com", "password": "ClaveSegura2026!"},
    )
    assert r_log_mail.status_code == 200, r_log_mail.text

    # 2. Alta de personal SIN acceso al sistema ni correo obligatorio
    r_sin = cliente.post(
        "/api/usuarios",
        headers=cab_dir,
        json={
            "nombre": "Pedro Comisiones",
            "rol": "ASESORA",
            "modalidad": "ONLINE",
            "telefono": "0414-7778899",
            "tiene_acceso_sistema": False,
            "sucursal_id": 1,
        },
    )
    assert r_sin.status_code == 201, r_sin.text
    sin_acceso = r_sin.json()
    assert sin_acceso["tiene_acceso"] is False
    assert sin_acceso["tiene_acceso_sistema"] is False
    assert sin_acceso["correo"] is None
    assert sin_acceso["username"] is None

    # Rechazo 403 en login para personal sin acceso
    r_log_sin = cliente.post(
        "/api/auth/login",
        json={"usuario": "Pedro Comisiones", "clave": "CualquierClave123"},
    )
    assert r_log_sin.status_code == 403, r_log_sin.text

    # Aparición en /api/usuarios/operativos para selectores de POS/taller/comisiones
    r_ops = cliente.get("/api/usuarios/operativos", headers=cab_lider)
    assert r_ops.status_code == 200, r_ops.text
    assert any(
        u["id"] == sin_acceso["id"] and u["tiene_acceso"] is False
        for u in r_ops.json()
    )

    # 3. Cambio de contraseña propio en /api/auth/cambiar-password
    # 3a. Rechaza clave actual incorrecta (400)
    r_bad_act = cliente.post(
        "/api/auth/cambiar-password",
        headers=cab_lider,
        json={
            "clave_actual": "ClaveErrada999",
            "clave_nueva": "NuevaClaveSegura2026",
            "confirmar_clave": "NuevaClaveSegura2026",
        },
    )
    assert r_bad_act.status_code == 400, r_bad_act.text

    # 3b. Rechaza nueva clave menor a 8 caracteres (422)
    r_corta = cliente.post(
        "/api/auth/cambiar-password",
        headers=cab_lider,
        json={
            "clave_actual": "ClaveSegura2026!",
            "clave_nueva": "Corta7!",
            "confirmar_clave": "Corta7!",
        },
    )
    assert r_corta.status_code == 422, r_corta.text

    # 3c. Cambio exitoso (>= 8 caracteres)
    r_ok_pwd = cliente.post(
        "/api/auth/cambiar-password",
        headers=cab_lider,
        json={
            "clave_actual": "ClaveSegura2026!",
            "clave_nueva": "NuevaClaveSegura2026",
            "confirmar_clave": "NuevaClaveSegura2026",
        },
    )
    assert r_ok_pwd.status_code == 200, r_ok_pwd.text

    # 4. Bloqueo 423 al 5to intento fallido + alerta de seguridad + desbloqueo por DIRECCION
    for _ in range(4):
        r_fail = cliente.post(
            "/api/auth/login",
            json={"username": "valeria.com", "clave": "clave-mala"},
        )
        assert r_fail.status_code == 401, r_fail.text

    r_lock = cliente.post(
        "/api/auth/login",
        json={"username": "valeria.com", "clave": "clave-mala"},
    )
    assert r_lock.status_code == 423, r_lock.text
    assert "5 intentos fallidos" in r_lock.json()["detail"].lower()

    r_alertas = cliente.get("/api/alertas/resumen", headers=cab_dir)
    assert r_alertas.status_code == 200, r_alertas.text
    alerta_valeria = next(
        (a for a in r_alertas.json()["alertas_seguridad"] if a["usuario_id"] == lider_id),
        None,
    )
    assert alerta_valeria is not None
    assert alerta_valeria["bloqueado_en"] is not None

    r_desbloq = cliente.post(f"/api/usuarios/{lider_id}/desbloquear", headers=cab_dir)
    assert r_desbloq.status_code == 200, r_desbloq.text
    assert r_desbloq.json()["cuenta_bloqueada"] is False
    assert r_desbloq.json()["bloqueado_en"] is None

    # Login exitoso tras desbloqueo con la nueva clave
    r_relog = cliente.post(
        "/api/auth/login",
        json={"username": "valeria.com", "clave": "NuevaClaveSegura2026"},
    )
    assert r_relog.status_code == 200, r_relog.text
    cab_lider = {"Authorization": f"Bearer {r_relog.json()['token']}"}

    # 5. RBAC estricto para LIDER y ASESORA + anti-fuga de costos
    cab_as = ctx["headers_as"]
    for cab_op in (cab_lider, cab_as):
        assert cliente.get("/api/usuarios", headers=cab_op).status_code == 403
        assert cliente.get("/api/logistica/compras", headers=cab_op).status_code == 403
        assert cliente.get("/api/finanzas/tesoreria", headers=cab_op).status_code == 403
        assert cliente.get("/api/direccion/resumen", headers=cab_op).status_code == 403

        r_inv = cliente.get("/api/logistica/inventario/equipos", headers=cab_op)
        assert r_inv.status_code == 200, r_inv.text
        assert _contiene_campos_sensibles(r_inv.json()) == []

        r_cat = cliente.get("/api/catalogo", headers=cab_op)
        assert r_cat.status_code == 200, r_cat.text
        assert _contiene_campos_sensibles(r_cat.json()) == []
