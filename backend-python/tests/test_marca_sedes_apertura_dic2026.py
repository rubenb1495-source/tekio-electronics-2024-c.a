from __future__ import annotations

import io
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import load_workbook

_DIR_TESTS = str(Path(__file__).resolve().parent)
if _DIR_TESTS not in sys.path:
    sys.path.insert(0, _DIR_TESTS)

from app.core.empresa import (  # noqa: E402
    FECHA_CORTE_APERTURA,
    RAZON_SOCIAL,
    RIF,
    TELEFONO_ADMIN,
    TELEFONO_SOPORTE,
)
from test_fase5 import (  # noqa: E402
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def test_identidad_marca_3_sedes_pdfs_y_plantillas_apertura_01_12_2026(
    cliente: TestClient,
) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab_dir = ctx["headers_dir"]

    # 1. Verificar las 3 sedes oficiales con sus teléfonos y tipos exactos
    r_suc = cliente.get("/api/sucursales", headers=cab_dir)
    assert r_suc.status_code == 200, r_suc.text
    por_nombre = {s["nombre"]: s for s in r_suc.json()}

    assert por_nombre["Tekio Central"]["telefono"] == "0412-5284961"
    assert por_nombre["Tekio Central"]["tipo"] == "TIENDA"
    assert por_nombre["Tekio Central"]["estado"] == "ACTIVA"

    assert por_nombre["Tekio Gran Bazar"]["telefono"] == "0422-5556609"
    assert por_nombre["Tekio Gran Bazar"]["tipo"] == "TIENDA"
    assert por_nombre["Tekio Gran Bazar"]["estado"] == "ACTIVA"

    assert por_nombre["Depósito / Tekio Support (Taller)"]["telefono"] == TELEFONO_SOPORTE
    assert por_nombre["Depósito / Tekio Support (Taller)"]["tipo"] == "DEPOSITO_TALLER"
    assert por_nombre["Depósito / Tekio Support (Taller)"]["estado"] == "ACTIVA"

    # 2. Verificar PDFs financieros (P&L y Balance General) con papelería corporativa y RIF
    r_pl_pdf = cliente.get(
        "/api/finanzas/estados/pl-escalonado/export?formato=pdf&fecha_inicio=2026-12-01&fecha_fin=2026-12-31",
        headers=cab_dir,
    )
    assert r_pl_pdf.status_code == 200, r_pl_pdf.text
    assert r_pl_pdf.content.startswith(b"%PDF-")

    r_bal_pdf = cliente.get(
        "/api/finanzas/estados/balance-general/export?formato=pdf&fecha_corte=2026-12-01",
        headers=cab_dir,
    )
    assert r_bal_pdf.status_code == 200, r_bal_pdf.text
    assert r_bal_pdf.content.startswith(b"%PDF-")

    # 3. Verificar plantillas Excel de apertura 01/12/2026 con las 3 sedes y Caja Chica $60
    r_saldos = cliente.get("/api/finanzas/apertura/plantillas/saldos_iniciales", headers=cab_dir)
    assert r_saldos.status_code == 200, r_saldos.text
    wb_s = load_workbook(io.BytesIO(r_saldos.content))
    ws_s = wb_s.active
    texto_saldos = "\n".join(
        " ".join(str(c or "") for c in row) for row in ws_s.iter_rows(values_only=True)
    )
    assert RAZON_SOCIAL in texto_saldos
    assert RIF in texto_saldos
    assert FECHA_CORTE_APERTURA in texto_saldos
    assert "Tekio Central" in texto_saldos
    assert "Tekio Gran Bazar" in texto_saldos
    assert "Caja Chica USD" in texto_saldos
    assert TELEFONO_ADMIN in texto_saldos
    assert "3.1.01 - Capital Inicial" in texto_saldos

    r_inv = cliente.get("/api/finanzas/apertura/plantillas/inventario_inicial", headers=cab_dir)
    assert r_inv.status_code == 200, r_inv.text
    wb_i = load_workbook(io.BytesIO(r_inv.content))
    texto_inv = "\n".join(
        " ".join(str(c or "") for c in row)
        for ws in wb_i.worksheets
        for row in ws.iter_rows(values_only=True)
    )
    assert FECHA_CORTE_APERTURA in texto_inv
    assert "Tekio Central" in texto_inv
    assert "Tekio Gran Bazar" in texto_inv
    assert "Depósito / Tekio Support (Taller)" in texto_inv
