from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

_DIR_TESTS = str(Path(__file__).resolve().parent)
if _DIR_TESTS not in sys.path:
    sys.path.insert(0, _DIR_TESTS)

from app.servicios.apertura_plantillas import PLANTILLAS_APERTURA_META  # noqa: E402
from test_fase5 import (  # noqa: E402
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def test_ciclo_completo_apertura_01_12_2026_reset_zip_importacion_y_cuadre(
    cliente: TestClient,
) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]
    cab_as = ctx["headers_as"]

    # 1. RBAC: ASESORA bloqueada con 403 en apertura y reset
    assert cliente.get("/api/finanzas/apertura/estado", headers=cab_as).status_code == 403
    assert cliente.get("/api/finanzas/apertura/plantillas/zip", headers=cab_as).status_code == 403
    assert (
        cliente.post(
            "/api/admin/reset-apertura",
            headers=cab_as,
            json={"password": "Password123!", "frase_confirmacion": "REINICIAR TEKIO 01-12"},
        ).status_code
        == 403
    )

    # 2. Doble confirmación en reset: frase incorrecta -> 400; clave incorrecta -> 401
    r_bad_frase = cliente.post(
        "/api/admin/reset-apertura",
        headers=cab_dir,
        json={"password": "Tekio2026!", "frase_confirmacion": "OTRA FRASE"},
    )
    assert r_bad_frase.status_code == 400

    r_bad_pw = cliente.post(
        "/api/admin/reset-apertura",
        headers=cab_dir,
        json={"password": "ClaveIncorrecta", "frase_confirmacion": "REINICIAR TEKIO 01-12"},
    )
    assert r_bad_pw.status_code == 401

    # 3. Ejecutar reset a cero válido
    r_reset = cliente.post(
        "/api/admin/reset-apertura",
        headers=cab_dir,
        json={"password": "Tekio2026!", "frase_confirmacion": "REINICIAR TEKIO 01-12"},
    )
    assert r_reset.status_code == 200, r_reset.text
    reset_body = r_reset.json()
    assert reset_body["estado"] == "REINICIADO_APERTURA"
    assert reset_body["rif"] == "J-50637518-4"
    assert reset_body["fecha_corte_apertura"] == "2026-12-01"
    assert len(reset_body["sedes_conservadas"]) >= 3
    assert reset_body["correlativos_reiniciados"] is True
    assert Path(reset_body["respaldo_previo"]["archivo"]).exists()

    # 4. Descargar el .zip con las 6 planillas oficiales .xlsx
    r_zip = cliente.get("/api/finanzas/apertura/plantillas/zip", headers=cab_dir)
    assert r_zip.status_code == 200, r_zip.text
    assert "application/zip" in r_zip.headers["content-type"]
    zf = zipfile.ZipFile(io.BytesIO(r_zip.content))
    nombres_zip = set(zf.namelist())
    esperados = {meta["archivo"] for meta in PLANTILLAS_APERTURA_META.values()}
    assert nombres_zip == esperados

    # 5. Importar las 6 planillas en orden (preview + confirmar atómico) usando los .xlsx del .zip
    for tipo, meta in PLANTILLAS_APERTURA_META.items():
        contenido_xlsx = zf.read(meta["archivo"])
        files_param = {
            "archivo": (
                meta["archivo"],
                contenido_xlsx,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        }
        r_prev = cliente.post(
            f"/api/finanzas/apertura/importar/{tipo}/preview",
            headers=cab_dir,
            files=files_param,
        )
        assert r_prev.status_code == 200, f"Preview {tipo}: {r_prev.text}"
        prev = r_prev.json()
        assert prev["con_errores"] == 0, f"Errores en {tipo}: {prev}"
        assert prev["validas"] >= 1

        r_conf = cliente.post(
            f"/api/finanzas/apertura/importar/{tipo}/confirmar",
            headers=cab_dir,
            files=files_param,
        )
        assert r_conf.status_code == 201, f"Confirmar {tipo}: {r_conf.text}"
        assert r_conf.json()["fecha_contable"] == "2026-12-01"

    # 6. Verificar cuadre al 01/12/2026: Balance General Varianza $0.00 y P&L Diciembre $0.00
    r_est = cliente.get("/api/finanzas/apertura/estado", headers=cab_dir)
    assert r_est.status_code == 200, r_est.text
    est = r_est.json()
    assert all(p["cargado"] is True for p in est["pasos"])

    cuadre = est["cuadre"]
    assert cuadre["cuadrado"] is True
    assert cuadre["varianza_usd"] == 0.0
    assert cuadre["pl_diciembre_utilidad_neta_usd"] == 0.0
    assert cuadre["pl_diciembre_ingresos_usd"] == 0.0

    # Verificar que Activos - Pasivos == Patrimonio (y consignación $520 NO infló inventario propio: 280 + 310 = 590)
    assert cuadre["inventario_equipos_usd"] == 590.0
    assert cuadre["total_activos_usd"] > 0
    assert cuadre["total_pasivos_usd"] == 3400.0  # 1400 CxP + 2000 Préstamo
    assert round(cuadre["total_activos_usd"] - cuadre["total_pasivos_usd"], 2) == cuadre["patrimonio_capital_inicial_usd"]
