from __future__ import annotations

import base64
import re
import sys
import zlib
from pathlib import Path

from fastapi.testclient import TestClient

_DIR_TESTS = str(Path(__file__).resolve().parent)
if _DIR_TESTS not in sys.path:
    sys.path.insert(0, _DIR_TESTS)

from app.rutas.tasas import obtener_fecha_hoy  # noqa: E402
from test_fase5 import (  # noqa: E402
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def _extraer_texto_pdf(pdf_bytes: bytes) -> str:
    partes: list[str] = []
    for match in re.finditer(rb"stream[\r\n]+(.*?)[\r\n]*endstream", pdf_bytes, flags=re.DOTALL):
        bloque = match.group(1).strip()
        sin_fin = bloque[:-2] if bloque.endswith(b"~>") else bloque
        datos = bloque
        for dec in (
            lambda b: zlib.decompress(base64.a85decode(sin_fin)),
            lambda b: zlib.decompress(b),
            lambda b: base64.a85decode(sin_fin),
        ):
            try:
                datos = dec(bloque)
                break
            except Exception:
                continue
        texto = datos.decode("latin-1", errors="ignore")
        for lit in re.findall(r"\(([^()\\]*(?:\\.[^()\\]*)*)\)", texto):
            partes.append(lit)
    return " ".join(partes)


def _instrumento_divisas(cliente: TestClient, headers: dict[str, str]) -> int:
    resp = cliente.get("/api/finanzas/instrumentos", headers=headers)
    assert resp.status_code == 200, resp.text
    for inst in resp.json():
        if inst["moneda"] == "USD" and "efectivo" in inst["nombre"].lower():
            return int(inst["id"])
    return int(resp.json()[0]["id"])


def test_alerta_obligatoria_cargador_3_escenarios_y_nota_pdf(
    cliente: TestClient,
) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab = ctx["headers_dir"]
    hoy_str = obtener_fecha_hoy().isoformat()
    inst_usd = _instrumento_divisas(cliente, cab)

    # Crear SKU de cargador AC-CARG-65W con stock en sucursal 1
    r_art = cliente.post(
        "/api/catalogo",
        headers=cab,
        json={
            "sku": "AC-CARG-65W",
            "descripcion": "Cargador USB-C 65W Original",
            "tipo": "ACCESORIO",
            "categoria": "Cargadores",
            "precio_promo_usd": 25.0,
            "costo_estandar_usd": 12.0,
        },
    )
    assert r_art.status_code == 201, r_art.text
    cargador_id = r_art.json()["id"]

    # Comprar 2 equipos LISTO + 2 cargadores en sucursal 1
    r_comp = cliente.post(
        "/api/logistica/compras",
        headers=cab,
        json={
            "origen": "NACIONAL",
            "tipo_compra": "NACIONAL",
            "fecha": hoy_str,
            "llega_preparada": True,
            "equipos": [
                {
                    "serial": "SN-CARG-TEST-01",
                    "modelo": "Lenovo ThinkPad T14",
                    "configuracion": "16GB / 512GB",
                    "costo_compra_usd": 280.0,
                    "precio_promo_usd": 400.0,
                    "ubicacion_id": 1,
                    "estado": "LISTO",
                },
                {
                    "serial": "SN-CARG-TEST-02",
                    "modelo": "Dell Latitude 5420",
                    "configuracion": "16GB / 512GB",
                    "costo_compra_usd": 300.0,
                    "precio_promo_usd": 420.0,
                    "ubicacion_id": 1,
                    "estado": "LISTO",
                },
            ],
            "componentes": [
                {
                    "articulo_id": cargador_id,
                    "cantidad": 2,
                    "costo_unitario_usd": 12.0,
                    "ubicacion_id": 1,
                }
            ],
        },
    )
    assert r_comp.status_code == 201, r_comp.text
    r_eqs = cliente.get("/api/logistica/inventario/equipos?sucursal_id=1&estado=LISTO", headers=cab)
    assert r_eqs.status_code == 200
    eq1 = next(e for e in r_eqs.json() if e["serial"] == "SN-CARG-TEST-01")
    eq2 = next(e for e in r_eqs.json() if e["serial"] == "SN-CARG-TEST-02")

    # (a) Equipo solo SIN desbloquear (sin_cargador = false) -> HTTP 422 bloqueado
    r_bloq = cliente.post(
        "/api/ventas",
        headers=cab,
        json={
            "sucursal_id": 1,
            "items": [{"equipo_id": eq1["id"], "cantidad": 1, "precio_pactado_usd": 400.0}],
            "pagos": [{"instrumento_id": inst_usd, "monto_moneda_origen": 400.0}],
        },
    )
    assert r_bloq.status_code == 422, r_bloq.text
    assert "cargador" in r_bloq.json()["detail"].lower()

    # (b) Equipo + cargador en el carrito -> HTTP 201 directo sin alerta ni observación
    r_con_carg = cliente.post(
        "/api/ventas",
        headers=cab,
        json={
            "sucursal_id": 1,
            "items": [
                {"equipo_id": eq1["id"], "cantidad": 1, "precio_pactado_usd": 400.0},
                {"articulo_id": cargador_id, "cantidad": 1, "precio_pactado_usd": 25.0},
            ],
            "pagos": [{"instrumento_id": inst_usd, "monto_moneda_origen": 425.0}],
        },
    )
    assert r_con_carg.status_code == 201, r_con_carg.text
    v_con = r_con_carg.json()
    assert v_con["sin_cargador"] is False
    r_pdf_con = cliente.get(f"/api/ventas/{v_con['id']}/nota-pdf", headers=cab)
    assert r_pdf_con.status_code == 200
    assert "SIN cargador" not in _extraer_texto_pdf(r_pdf_con.content)

    # (c) Equipo solo CON desbloqueo (sin_cargador = true + motivo) -> HTTP 201 + constancia en PDF
    r_desbloq = cliente.post(
        "/api/ventas",
        headers=cab,
        json={
            "sucursal_id": 1,
            "sin_cargador": True,
            "motivo_sin_cargador": "Cliente ya tiene cargador USB-C",
            "items": [{"equipo_id": eq2["id"], "cantidad": 1, "precio_pactado_usd": 420.0}],
            "pagos": [{"instrumento_id": inst_usd, "monto_moneda_origen": 420.0}],
        },
    )
    assert r_desbloq.status_code == 201, r_desbloq.text
    v_sin = r_desbloq.json()
    assert v_sin["sin_cargador"] is True
    assert v_sin["motivo_sin_cargador"] == "Cliente ya tiene cargador USB-C"

    r_pdf_sin = cliente.get(f"/api/ventas/{v_sin['id']}/nota-pdf", headers=cab)
    assert r_pdf_sin.status_code == 200
    texto_pdf = _extraer_texto_pdf(r_pdf_sin.content)
    assert "Equipo entregado SIN cargador" in texto_pdf
    assert "Cliente ya tiene cargador USB-C" in texto_pdf
