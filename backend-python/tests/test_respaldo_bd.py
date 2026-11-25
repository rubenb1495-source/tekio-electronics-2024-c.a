from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import load_workbook

_DIR_TESTS = str(Path(__file__).resolve().parent)
if _DIR_TESTS not in sys.path:
    sys.path.insert(0, _DIR_TESTS)

from test_fase5 import (  # noqa: E402
    _login,
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def test_respaldo_completo_zip_solo_administracion_y_403_otros_roles(
    cliente: TestClient,
) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]  # DIRECCION (equivalente DIRECTOR) -> debe recibir 403
    cab_as = ctx["headers_as"]  # ASESORA -> debe recibir 403

    # Crear usuarios para ADMINISTRACION, LIDER y TECNICO
    for payload in (
        {
            "nombre": "Admin Respaldo",
            "correo": "admin.respaldo@tekio.com",
            "clave": "Password123!",
            "rol": "ADMINISTRACION",
            "sucursal_id": 1,
        },
        {
            "nombre": "Lider Respaldo",
            "correo": "lider.respaldo@tekio.com",
            "clave": "Password123!",
            "rol": "LIDER",
            "sucursal_id": 1,
        },
        {
            "nombre": "Tecnico Respaldo",
            "correo": "tecnico.respaldo@tekio.com",
            "clave": "Password123!",
            "rol": "TECNICO",
            "sucursal_id": 1,
        },
    ):
        r = cliente.post("/api/usuarios", headers=cab_dir, json=payload)
        assert r.status_code == 201, r.text

    cab_adm = _login(cliente, "admin.respaldo@tekio.com", "Password123!")
    cab_lid = _login(cliente, "lider.respaldo@tekio.com", "Password123!")
    cab_tec = _login(cliente, "tecnico.respaldo@tekio.com", "Password123!")

    # 1. Cualquier rol distinto a ADMINISTRACION recibe 403 Forbidden
    for cab_otro in (cab_dir, cab_lid, cab_as, cab_tec):
        assert cliente.get("/api/admin/respaldo/descargar", headers=cab_otro).status_code == 403
        assert cliente.get("/api/admin/respaldo/historial", headers=cab_otro).status_code == 403

    # 2. ADMINISTRACION descarga el .zip válido con backup_completo.json y resumen_legible_tekio.xlsx
    r_zip = cliente.get("/api/admin/respaldo/descargar", headers=cab_adm)
    assert r_zip.status_code == 200, r_zip.text
    assert r_zip.headers.get("content-type", "").startswith("application/zip")
    assert "respaldo_tekio_" in r_zip.headers.get("content-disposition", "")

    with zipfile.ZipFile(io.BytesIO(r_zip.content), "r") as zf:
        nombres = set(zf.namelist())
        assert "backup_completo.json" in nombres
        assert "resumen_legible_tekio.xlsx" in nombres

        # Validar JSON técnico con metadatos y conteos
        datos_json = json.loads(zf.read("backup_completo.json").decode("utf-8"))
        assert datos_json["metadatos"]["usuario"] == "Admin Respaldo"
        assert datos_json["metadatos"]["total_tablas"] >= 10
        assert "usuarios" in datos_json["tablas"]
        assert datos_json["metadatos"]["conteo_por_tabla"]["usuarios"] >= 4

        # Validar Excel legible con las 7 pestañas clave
        wb = load_workbook(io.BytesIO(zf.read("resumen_legible_tekio.xlsx")))
        hojas = set(wb.sheetnames)
        assert {
            "Saldos Cajas y Bancos",
            "Inventario Equipos",
            "Inventario Componentes",
            "Ventas y Servicios",
            "CxC y Cashea",
            "CxP Proveedores",
            "Personal",
        }.issubset(hojas)

    # 3. Historial refleja la descarga registrada en auditoria_sistema
    r_hist = cliente.get("/api/admin/respaldo/historial", headers=cab_adm)
    assert r_hist.status_code == 200, r_hist.text
    historial = r_hist.json()
    assert len(historial) >= 1
    assert historial[0]["usuario"] == "Admin Respaldo"
    assert historial[0]["archivo"].startswith("respaldo_tekio_")
    assert historial[0]["tamano_kb"] > 0
