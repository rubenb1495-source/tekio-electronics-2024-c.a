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

from test_fase5 import (  # noqa: E402
    _preparar_escenario_base,
    cliente,  # noqa: F401
)


def _extraer_texto_pdf(pdf_bytes: bytes) -> str:
    """Extrae texto legible de streams ASCII85/FlateDecode de ReportLab sin dependencias extra."""
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


def _obtener_instrumento_divisas(cliente: TestClient, headers: dict[str, str]) -> int:
    resp = cliente.get("/api/finanzas/instrumentos", headers=headers)
    assert resp.status_code == 200, resp.text
    for inst in resp.json():
        if inst["moneda"] == "USD" and "efectivo" in inst["nombre"].lower():
            return int(inst["id"])
    return int(resp.json()[0]["id"])


def test_etiqueta_envio_pdf_delivery_nacional_y_bloqueo_retiro_tienda(
    cliente: TestClient,
) -> None:
    ctx = _preparar_escenario_base(cliente)
    cab = ctx["headers_dir"]
    sucursal_id = 1
    r_tec = cliente.post(
        "/api/usuarios",
        headers=cab,
        json={
            "nombre": "Luis Tecnico",
            "correo": "luis.etiq@tekio.com",
            "clave": "Password123!",
            "rol": "TECNICO",
            "sucursal_id": sucursal_id,
        },
    )
    assert r_tec.status_code == 201, r_tec.text
    tecnico_id = r_tec.json()["id"]
    r_art = cliente.post(
        "/api/catalogo",
        headers=cab,
        json={
            "sku": "SRV-ETIQ-TEST",
            "descripcion": "Servicio de Configuración Express",
            "tipo": "SERVICIO",
            "categoria": "Servicios",
            "precio_promo_usd": 50.0,
            "costo_estandar_usd": 20.0,
        },
    )
    assert r_art.status_code == 201, r_art.text
    articulo_id = r_art.json()["id"]
    inst_usd = _obtener_instrumento_divisas(cliente, cab)

    # 1. Venta RETIRO_TIENDA -> debe devolver 400 Bad Request al pedir etiqueta
    r_tienda = cliente.post(
        "/api/ventas",
        headers=cab,
        json={
            "sucursal_id": sucursal_id,
            "tecnico_id": tecnico_id,
            "entrega": "RETIRO_TIENDA",
            "items": [{"articulo_id": articulo_id, "cantidad": 1, "precio_pactado_usd": 777.50}],
            "pagos": [{"instrumento_id": inst_usd, "monto_moneda_origen": 777.50}],
        },
    )
    assert r_tienda.status_code == 201, r_tienda.text
    venta_tienda = r_tienda.json()
    assert venta_tienda["tipo_entrega"] == "RETIRO_TIENDA"

    r_etiq_tienda = cliente.get(
        f"/api/ventas/{venta_tienda['id']}/etiqueta-envio-pdf",
        headers=cab,
    )
    assert r_etiq_tienda.status_code == 400
    assert "no tiene envío" in r_etiq_tienda.json()["detail"].lower()

    # 2. Venta DELIVERY -> 200 OK PDF Carta con FRÁGIL, destinatario, dirección, N-XXXX y SIN precio
    r_del = cliente.post(
        "/api/ventas",
        headers=cab,
        json={
            "sucursal_id": sucursal_id,
            "tecnico_id": tecnico_id,
            "entrega": "DELIVERY",
            "datos_entrega": {
                "nombre_recibe": "Carlos Mendoza",
                "telefono": "0414-9876543",
                "direccion": "Urb. El Viñedo Calle 138 Casa 12",
                "punto_referencia": "Frente a la panadería",
                "zona_municipio": "Valencia, Carabobo",
                "horario_instrucciones": "Entregar después de las 2pm",
            },
            "envio_destinatario_documento": "V-18222333",
            "envio_modalidad_pago": "PAGADO",
            "items": [{"articulo_id": articulo_id, "cantidad": 1, "precio_pactado_usd": 849.99}],
            "pagos": [{"instrumento_id": inst_usd, "monto_moneda_origen": 849.99}],
        },
    )
    assert r_del.status_code == 201, r_del.text
    venta_del = r_del.json()
    assert venta_del["tipo_entrega"] == "DELIVERY"
    assert venta_del["envio_destinatario_nombre"] == "Carlos Mendoza"
    assert venta_del["envio_agencia_courier"] == "Delivery Local"

    r_etiq_del = cliente.get(
        f"/api/ventas/{venta_del['id']}/etiqueta-envio-pdf?bultos=2",
        headers=cab,
    )
    assert r_etiq_del.status_code == 200, r_etiq_del.text
    assert r_etiq_del.headers["content-type"].startswith("application/pdf")
    assert "inline" in r_etiq_del.headers.get("content-disposition", "").lower()
    assert len(r_etiq_del.content) > 1000

    texto_del = _extraer_texto_pdf(r_etiq_del.content)
    assert "FRÁGIL" in texto_del or "FR\\301GIL" in texto_del or "FRAGIL" in texto_del.upper()
    assert "CARLOS MENDOZA" in texto_del.upper()
    assert "DELIVERY LOCAL" in texto_del.upper()
    assert "VIÑEDO" in texto_del.upper() or "VI\\321EDO" in texto_del.upper() or "CALLE 138" in texto_del.upper()
    assert venta_del["numero_venta"] in texto_del
    assert "BULTOS: 2" in texto_del.upper()
    # Seguridad del paquete: NO debe exponer el monto de la venta
    assert "849.99" not in texto_del
    assert "849,99" not in texto_del

    # 3. Venta ENVIO_NACIONAL -> 200 OK PDF Carta con FRÁGIL, courier MRW, agencia, N-XXXX y SIN precio
    r_env = cliente.post(
        "/api/ventas",
        headers=cab,
        json={
            "sucursal_id": sucursal_id,
            "tecnico_id": tecnico_id,
            "entrega": "ENVIO_NACIONAL",
            "envio_destinatario_nombre": "María Fernanda Rojas",
            "envio_destinatario_documento": "V-24555666",
            "envio_destinatario_telefono": "0412-5554433",
            "envio_agencia_courier": "MRW",
            "envio_direccion_o_agencia": "Agencia MRW Chacaíto Cod. 0105",
            "envio_ciudad_estado": "Caracas, Distrito Capital",
            "envio_referencia": "Retiro en taquilla principal",
            "envio_modalidad_pago": "COBRO_EN_DESTINO",
            "items": [{"articulo_id": articulo_id, "cantidad": 1, "precio_pactado_usd": 1295.75}],
            "pagos": [{"instrumento_id": inst_usd, "monto_moneda_origen": 1295.75}],
        },
    )
    assert r_env.status_code == 201, r_env.text
    venta_env = r_env.json()
    assert venta_env["tipo_entrega"] == "ENVIO_NACIONAL"
    assert venta_env["envio_agencia_courier"] == "MRW"
    assert venta_env["envio_modalidad_pago"] == "COBRO_EN_DESTINO"

    r_etiq_env = cliente.get(
        f"/api/ventas/{venta_env['id']}/etiqueta-envio-pdf",
        headers=cab,
    )
    assert r_etiq_env.status_code == 200, r_etiq_env.text
    assert r_etiq_env.headers["content-type"].startswith("application/pdf")
    assert len(r_etiq_env.content) > 1000

    texto_env = _extraer_texto_pdf(r_etiq_env.content)
    assert "FRÁGIL" in texto_env or "FR\\301GIL" in texto_env or "FRAGIL" in texto_env.upper()
    assert "MRW" in texto_env.upper()
    assert "MAR" in texto_env.upper() and "ROJAS" in texto_env.upper()
    assert "CHACA" in texto_env.upper()
    assert "COBRO EN DESTINO" in texto_env.upper()
    assert venta_env["numero_venta"] in texto_env
    # Seguridad del paquete: NO debe exponer el monto de la venta
    assert "1295.75" not in texto_env
    assert "1,295.75" not in texto_env
    assert "1.295,75" not in texto_env

    # 4. La Nota de Entrega PDF también sigue funcionando e incluye los datos de envío
    r_nota = cliente.get(f"/api/ventas/{venta_env['id']}/nota-pdf", headers=cab)
    assert r_nota.status_code == 200, r_nota.text
    assert r_nota.headers["content-type"].startswith("application/pdf")
    texto_nota = _extraer_texto_pdf(r_nota.content)
    assert "MRW" in texto_nota.upper()
    assert venta_env["numero_venta"] in texto_nota
